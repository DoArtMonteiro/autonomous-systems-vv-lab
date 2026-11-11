"""Shared helpers of the Blender asset scripts (run inside Blender: blender --factory-startup --background --python <script>).

Everything these scripts write is generated from code with fixed seeds (the CC0 files in
assets/cc0 are separate, with their own provenance): no downloaded asset in the scripts, no randomness without a
seed, so running a script twice gives byte-identical files (the build checks this).
"""

import math
import sys

import bpy
import numpy as np


def script_args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# --- noise -----------------------------------------------------------------------------------------

def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def vnoise(h, w, ch, cw, seed, wrap_u=True):
    """Value noise on an h x w grid with ch x cw cells (u, the second axis, wraps when wrap_u)."""
    rng = np.random.default_rng(seed)
    g = rng.random((ch + 2, cw + 1 if wrap_u else cw + 2)).astype(np.float32)
    if wrap_u:
        g[:, cw] = g[:, 0]
    ys = np.linspace(0, ch, h, endpoint=False, dtype=np.float32)
    xs = np.linspace(0, cw, w, endpoint=False, dtype=np.float32)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    fy = _smooth(ys - y0)[:, None]
    fx = _smooth(xs - x0)[None, :]
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h, w, ch, cw, seed, octaves=4, wrap_u=True):
    out = np.zeros((h, w), np.float32)
    amp = 0.5
    tot = 0.0
    for o in range(octaves):
        out += amp * vnoise(h, w, ch * 2 ** o, cw * 2 ** o, seed + 101 * o, wrap_u)
        tot += amp
        amp *= 0.5
    return out / tot


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def normal_from_height(hgt, strength, texel_ratio=1.0):
    """OpenGL-convention tangent-space normal map (RGB 0..1) of a height field (rows are v, up)."""
    dv, du = np.gradient(hgt)
    n = np.stack([-du * strength, -dv * strength * texel_ratio, np.ones_like(hgt)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


# --- images and materials -------------------------------------------------------------------------

def make_image(name, rgba, colorspace="sRGB", fmt="PNG"):
    """A packed Blender image from a float array of shape (h, w, 4), row 0 at the bottom (v = 0).

    The array holds the values to store in the file (already display-encoded for sRGB)."""
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.colorspace_settings.name = colorspace
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(np.ascontiguousarray(rgba, np.float32).ravel())
    img.file_format = fmt
    img.pack()
    return img


def srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def principled(name, colour=(0.8, 0.8, 0.8), rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*colour, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def textured(name, albedo=None, orm=None, normal=None, normal_strength=1.0):
    """Principled material with an albedo image, an ORM-like image (G roughness, B metallic) and a normal map."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    if albedo is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = albedo
        t.interpolation = "Linear"
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    if orm is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = orm
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])
    if normal is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = normal
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(t.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


# --- geometry -------------------------------------------------------------------------------------

class Geo:
    """Accumulates vertices, faces and per-loop UVs for one object (one material slot per name)."""

    def __init__(self):
        self.v = []
        self.f = []
        self.uv = []      # per face: list of (u, v) per corner
        self.mat = []     # per face: material slot index
        self.flat = []    # per face: True for flat shading
        self.slots = []

    def slot(self, name):
        if name not in self.slots:
            self.slots.append(name)
        return self.slots.index(name)

    def add_face(self, idx, uvs, mat, flat):
        self.f.append(tuple(idx))
        self.uv.append(uvs)
        self.mat.append(self.slot(mat))
        self.flat.append(flat)

    def lathe(self, profile, segs, mat, uv=None, flat=False, a0=0.0):
        """Surface of revolution about +z of [(radius, z), ...]. uv(u, z, r) -> (u', v') per vertex."""
        base = len(self.v)
        n = len(profile)
        for r, z in profile:
            for s in range(segs):
                a = a0 + 2 * math.pi * s / segs
                self.v.append((r * math.cos(a), r * math.sin(a), z))
        uvf = uv or (lambda u, z, r: (u, z))
        for i in range(n - 1):
            for s in range(segs):
                s1 = (s + 1) % segs
                idx = [base + i * segs + s, base + i * segs + s1, base + (i + 1) * segs + s1, base + (i + 1) * segs + s]
                us = [s / segs, (s + 1) / segs, (s + 1) / segs, s / segs]
                zr = [profile[i], profile[i], profile[i + 1], profile[i + 1]]
                self.add_face(idx, [uvf(us[k], zr[k][1], zr[k][0]) for k in range(4)], mat, flat)

    def box(self, centre, size, mat, rot_z=0.0, tilt=None, uv_scale=1.0):
        """Flat-shaded box. size = (x, y, z) extents; rot_z rotates about z; tilt = (axis, angle) about a
        local axis through the centre applied first."""
        sx, sy, sz = (size[0] / 2, size[1] / 2, size[2] / 2)
        pts = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz), (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
        out = []
        for p in pts:
            x, y, z = p
            if tilt is not None:
                ax, ang = tilt
                c, s = math.cos(ang), math.sin(ang)
                if ax == "x":
                    y, z = y * c - z * s, y * s + z * c
                elif ax == "y":
                    x, z = x * c + z * s, -x * s + z * c
                else:
                    x, y = x * c - y * s, x * s + y * c
            c, s = math.cos(rot_z), math.sin(rot_z)
            out.append((centre[0] + x * c - y * s, centre[1] + x * s + y * c, centre[2] + z))
        base = len(self.v)
        self.v.extend(out)
        quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        for q in quads:
            self.add_face([base + k for k in q], [(0, 0), (1, 0), (1, 1), (0, 1)], mat, True)

    def build(self, name, materials):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.v, [], self.f)
        mesh.update()
        for sname in self.slots:
            mesh.materials.append(materials[sname])
        mesh.polygons.foreach_set("material_index", self.mat)
        sharp = mesh.attributes.new("sharp_face", "BOOLEAN", "FACE")
        sharp.data.foreach_set("value", self.flat)
        uvl = mesh.uv_layers.new(name="UVMap")
        flat_uv = []
        for corner_uvs in self.uv:
            for u, v in corner_uvs:
                flat_uv.extend((u, v))
        uvl.data.foreach_set("uv", flat_uv)
        mesh.update()
        ob = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def export_glb(path, objects=None):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in (objects or bpy.context.scene.objects):
        ob.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_image_format="AUTO",
        export_apply=True, export_yup=True, export_extras=False, export_cameras=False, export_lights=False,
        export_animations=False, export_texcoords=True, export_normals=True, export_tangents=False,
        export_materials="EXPORT",
    )
