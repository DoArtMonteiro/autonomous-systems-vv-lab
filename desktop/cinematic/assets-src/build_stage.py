"""Generic, illustrative reusable first stage for the Cinematic View (not a replica of any real vehicle).

    blender --factory-startup --background --python build_stage.py -- <out.glb>

Axis: +z from the nozzle exit plane (z = 0) to the top of the interstage (z = 42 m), radius 1.85 m,
tank 3.2 to 35.5 m: the dimensions of desktop/studio/ui/js/scenes/stage-model.js, so the pose of the
record applies unchanged. glTF export turns +z into +y; the renderer's stage node turns +y onto the
body axis.

Hand-authored from code with fixed seeds: panel-lined painted skin with weld seams and soot, seven
Rao-style bells with a heat-tint texture, a heat shield, four lattice grid fins, four STOWED legs
(the run record has no landing-gear state, so they never deploy), cable raceway, cold-gas thrusters.
Nodes: Skin, Engines, HeatShield, GridFins, Legs, Details. No logos, no names.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

R = 1.85
L = 42.0
TANK0, TANK1 = 3.2, 35.5
W, H = 1024, 4096  # skin texture: u around, v along the axis (1 cm per texel along z)


def skin_textures():
    zz = ((np.arange(H, dtype=np.float32) + 0.5) / H * L)[:, None]
    uu = ((np.arange(W, dtype=np.float32) + 0.5) / W)[None, :]
    rng = np.random.default_rng(4242)
    # Panel grid: horizontal welds every 2.0 m on the tank, 4 long stringers; slight tone per panel.
    row = np.floor((zz - TANK0) / 2.0)
    col = np.floor(uu * 4.0 + 0.0)
    tone = (rng.random((40, 8)).astype(np.float32) - 0.5) * 0.11
    pt = tone[np.clip(row, 0, 39).astype(np.int32), np.clip(col, 0, 7).astype(np.int32)]
    zr = (zz - TANK0) % 2.0
    wz = np.minimum(zr, 2.0 - zr)                 # metres to the nearest weld
    ur = (uu * 4.0) % 1.0
    wu = np.minimum(ur, 1.0 - ur) * (2 * math.pi * R / 4.0)  # metres to the nearest stringer
    in_tank = ((zz > TANK0) & (zz < TANK1)).astype(np.float32)
    weld = (1.0 - C.smoothstep(0.004, 0.016, wz)) * in_tank
    seam = (1.0 - C.smoothstep(0.004, 0.014, wu)) * in_tank
    groove = np.clip(weld + 0.8 * seam, 0.0, 1.0)
    # Rivet-like bolt rows along the welds.
    bolt = ((1.0 - C.smoothstep(0.012, 0.022, np.abs(wz - 0.07))) * (np.sin(uu * 2 * math.pi * 120.0) > 0.55)) * in_tank
    micro = C.fbm(H, W, 64, 8, 11, 5)
    mid = C.fbm(H, W, 6, 3, 12, 4)
    # Soot: rises from the engine end; streaks stretched along z.
    streak = C.fbm(H, W, 8, 140, 13, 3)
    streak2 = C.fbm(H, W, 3, 40, 14, 3)
    base = np.clip(1.0 - (zz - 2.5) / 17.0, 0.0, 1.0) ** 1.7
    soot = np.clip(base * (0.25 + 1.05 * streak) + 0.30 * np.clip(1.0 - (zz - 2.5) / 5.0, 0, 1) + 0.55 * np.clip(streak2 - 0.62, 0, 1) * np.clip(1.0 - (zz - 3.0) / 30.0, 0, 1), 0.0, 0.93)
    # Light drip stains from the seams, all along the tank.
    drip = np.clip(C.fbm(H, W, 4, 90, 15, 3) - 0.6, 0.0, 1.0) * in_tank
    paint = np.array([0.60, 0.61, 0.62], np.float32)
    dirt = np.clip((C.fbm(H, W, 3, 120, 17, 3) - 0.52) * 2.2, 0.0, 0.45) * in_tank * (0.5 + 0.7 * C.fbm(H, W, 5, 3, 18, 3))
    sootc = np.array([0.050, 0.045, 0.040], np.float32)
    albedo = paint[None, None, :] * (1.0 + pt + (micro - 0.5) * 0.05 + (mid - 0.5) * 0.06)[..., None]
    albedo = albedo * (1.0 - 0.22 * groove[..., None]) * (1.0 - 0.10 * bolt[..., None]) * (1.0 - 0.35 * drip[..., None]) * (1.0 - 0.55 * dirt[..., None])
    # Baked ambient occlusion: dark strips beside the four stowed legs and under the grid-fin hinges.
    ao = np.zeros((H, W), np.float32)
    for k in range(4):
        du = np.abs(((uu - k * 0.25 + 0.5) % 1.0) - 0.5)
        ao = np.maximum(ao, np.exp(-(du / 0.035) ** 2) * ((zz > 3.0) & (zz < 14.6)))
        du2 = np.abs(((uu - (0.125 + k * 0.25) + 0.5) % 1.0) - 0.5)
        ao = np.maximum(ao, 0.8 * np.exp(-(du2 / 0.05) ** 2) * ((zz > 38.3) & (zz < 40.6)))
    albedo = albedo * (1.0 - 0.4 * ao[..., None])
    albedo = albedo * (1.0 - soot[..., None]) + sootc[None, None, :] * soot[..., None] * (0.7 + 0.6 * micro[..., None])
    # Engine section (below the tank): scorched dark metal with a bronze heat tint.
    eng = (1.0 - C.smoothstep(TANK0 - 0.1, TANK0 + 0.05, zz))
    heat = np.array([0.20, 0.12, 0.07], np.float32)
    ec = np.array([0.085, 0.080, 0.075], np.float32)[None, None, :] * (0.7 + 0.9 * micro[..., None])
    ec = ec + heat[None, None, :] * (C.fbm(H, W, 5, 12, 16, 3)[..., None] * 0.5) * np.clip(1.0 - zz / 2.6, 0, 1)[..., None]
    albedo = albedo * (1.0 - eng[..., None]) + ec * eng[..., None]
    # Interstage (above the tank): matte black with faint wear.
    top = C.smoothstep(TANK1 - 0.05, TANK1 + 0.05, zz)
    black = np.array([0.028, 0.029, 0.032], np.float32)[None, None, :] * (0.8 + 0.8 * micro[..., None] + 0.5 * mid[..., None])
    albedo = albedo * (1.0 - top[..., None]) + black * top[..., None]
    # Separation ring: a pale band at the top of the tank.
    ring = (1.0 - C.smoothstep(0.02, 0.06, np.abs(zz - (TANK1 - 0.18)))) * 0.25
    albedo = albedo * (1.0 - ring[..., None]) + np.array([0.12, 0.12, 0.13], np.float32) * ring[..., None]
    albedo = np.clip(albedo, 0.0, 1.0)
    rgba = np.concatenate([C.srgb(albedo), np.ones((H, W, 1), np.float32)], axis=-1)
    # Roughness (G) and metallic (B): satin paint, rougher where sooted, metal-ish in the engine section.
    rough = 0.24 + 0.55 * (mid - 0.5) + 0.45 * soot + 0.20 * groove + 0.14 * (micro - 0.5) + 0.35 * eng + 0.25 * top
    metal = np.clip(0.22 * eng + 0.05 * groove, 0.0, 1.0)
    orm = np.stack([np.ones_like(rough), np.clip(rough, 0.05, 1.0), metal, np.ones_like(rough)], axis=-1)
    hgt = -(groove * 1.0 + bolt * 0.4) + (micro - 0.5) * 0.05
    nrm = C.normal_from_height(hgt, 6.0)
    nrm = np.concatenate([nrm, np.ones((H, W, 1), np.float32)], axis=-1)
    return rgba, orm, nrm


def engine_texture():
    h, w = 512, 128
    v = ((np.arange(h, dtype=np.float32) + 0.5) / h)[:, None]   # 0 at the exit plane, 1 at the throat
    u = ((np.arange(w, dtype=np.float32) + 0.5) / w)[None, :]
    n = C.fbm(h, w, 12, 8, 21, 4)
    bands = 0.5 + 0.5 * np.sin(v * 38.0 + n * 3.0)
    exitc = np.array([0.16, 0.15, 0.14], np.float32)
    bronze = np.array([0.52, 0.34, 0.17], np.float32)
    violet = np.array([0.20, 0.22, 0.38], np.float32)
    throat = np.array([0.10, 0.09, 0.09], np.float32)
    k1 = C.smoothstep(0.05, 0.45, v)
    k2 = C.smoothstep(0.45, 0.8, v)
    k3 = C.smoothstep(0.82, 1.0, v)
    col = exitc * (1 - k1[..., None]) + bronze * k1[..., None]
    col = col * (1 - k2[..., None]) + violet * k2[..., None]
    col = col * (1 - k3[..., None]) + throat * k3[..., None]
    col = col * (0.75 + 0.5 * bands[..., None] * 0.6 + 0.35 * n[..., None])
    soot = np.clip(C.fbm(h, w, 3, 30, 22, 3) * 1.4 - 0.45, 0, 1) * (1.0 - k2)
    col = col * (1 - 0.65 * soot[..., None])
    rgba = np.concatenate([C.srgb(np.clip(col, 0, 1)), np.ones((h, w, 1), np.float32)], axis=-1)
    rough = np.clip(0.34 + 0.3 * soot + 0.12 * n, 0.1, 1.0)
    orm = np.stack([np.ones_like(rough), rough, np.full_like(rough, 0.95), np.ones_like(rough)], axis=-1)
    return rgba, orm


def build():
    C.reset()
    rgba, orm, nrm = skin_textures()
    a = C.make_image("skin_albedo", rgba, "sRGB", "PNG")
    o = C.make_image("skin_orm", orm, "Non-Color", "PNG")
    n = C.make_image("skin_normal", nrm, "Non-Color", "PNG")
    erg, eorm = engine_texture()
    ea = C.make_image("engine_albedo", erg, "sRGB", "PNG")
    eo = C.make_image("engine_orm", eorm, "Non-Color", "PNG")
    mats = {
        "Skin": C.textured("Skin", a, o, n, 1.0),
        "Engine": C.textured("Engine", ea, eo, None),
        "HeatShield": C.principled("HeatShield", (0.045, 0.042, 0.04), 0.82, 0.25),
        "Titanium": C.principled("Titanium", (0.30, 0.31, 0.33), 0.42, 0.9),
        "Carbon": C.principled("Carbon", (0.035, 0.037, 0.042), 0.55, 0.15),
        "Steel": C.principled("Steel", (0.55, 0.56, 0.58), 0.32, 1.0),
    }
    objs = []

    # Skin: engine section, tank, interstage, as hard-edged sections of one lathe object. UV: u around,
    # v = z / 42 (the skin texture covers the whole length).
    g = C.Geo()
    uvz = lambda u, z, r: (u, z / L)
    segs = 96
    g.lathe([(R * 1.015, 1.05), (R * 1.03, 1.9), (R * 1.0, 3.15)], segs, "Skin", uvz)              # engine skirt
    g.lathe([(R * 1.0, 3.15), (R * 1.0, TANK0 + 0.04)], segs, "Skin", uvz)                          # skirt to tank
    g.lathe([(R * 1.0, TANK0 + 0.04), (R * 1.003, TANK0 + 0.2), (R * 1.0, TANK0 + 0.36)], segs, "Skin", uvz)  # lower weld band
    g.lathe([(R * 1.0, TANK0 + 0.36), (R * 1.0, TANK1 - 0.2)], segs, "Skin", uvz)                   # tank
    g.lathe([(R * 1.0, TANK1 - 0.2), (R * 1.004, TANK1 - 0.12), (R * 1.0, TANK1)], segs, "Skin", uvz)  # separation ring
    g.lathe([(R * 1.0, TANK1), (R * 0.985, 38.5), (R * 0.97, 41.2), (R * 0.9, 41.7)], segs, "Skin", uvz)  # interstage taper
    g.lathe([(R * 0.9, 41.7), (R * 0.9, 42.0), (R * 0.0, 42.0)], segs, "Skin", uvz)                  # flat top cap
    g.lathe([(R * 1.015, 1.05), (R * 0.0, 1.05)], segs, "Skin", uvz, a0=0.0)                         # underside of the skirt (inside view)
    objs.append(g.build("Skin", mats))

    # Engines: seven Rao-style bells (exit plane z = 0), gimbal-free (the record has no gimbal channel).
    ge = C.Geo()
    prof = []
    for i in range(17):
        f = i / 16.0
        # Bell contour: narrow throat at the top, fast opening, then nearly parallel to the axis.
        r = 0.2 + 0.33 * (1.0 - f) ** 0.62
        prof.append((r, f * 2.05))
    ev = lambda u, z, r: (u, z / 2.05)
    spots = [(0.0, 0.0)] + [(1.12 * math.cos(k * math.pi / 3.0), 1.12 * math.sin(k * math.pi / 3.0)) for k in range(6)]
    # Each bell is a separate lathe offset to its spot (vertices are shifted after generation).
    for sx, sy in spots:
        start = len(ge.v)
        ge.lathe(prof, 40, "Engine", ev)
        ge.v[start:] = [(x + sx, y + sy, z) for (x, y, z) in ge.v[start:]]
        # Inner wall of the bell (so the nozzle reads as hollow from below): a slightly smaller reversed lathe.
        inner = [(r - 0.018, z) for r, z in prof]
        start = len(ge.v)
        ge.lathe(list(reversed(inner)), 40, "Engine", lambda u, z, r: (u, z / 2.05))
        ge.v[start:] = [(x + sx, y + sy, z) for (x, y, z) in ge.v[start:]]
    objs.append(ge.build("Engines", mats))

    # Heat shield: dark plate under the skirt with a perforated look (rings of bolts), and a thrust ring.
    gh = C.Geo()
    gh.lathe([(R * 0.98, 2.0), (R * 0.98, 2.12), (0.0, 2.12)], 64, "HeatShield")
    gh.lathe([(R * 0.98, 1.95), (R * 0.98, 2.0)], 64, "HeatShield")
    for k in range(7):
        sx, sy = spots[k]
        r0 = 0.62
        start = len(gh.v)
        gh.lathe([(r0, 2.12), (r0 * 0.92, 2.22)], 24, "HeatShield")
        gh.v[start:] = [(x + sx, y + sy, z) for (x, y, z) in gh.v[start:]]
    objs.append(gh.build("HeatShield", mats))

    # Grid fins: four lattice panels near the top, in the radial-axial plane, fixed (no fin state in the record).
    gf = C.Geo()
    fz, fh, rad0, rad1, thick = 39.4, 1.7, R + 0.18, R + 1.75, 0.16
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)

        def place(rc, zc, sr, sz, st):
            # radial centre, axial centre, radial size, axial size, tangential thickness
            gf.box((rc * ca, rc * sa, zc), (sr, st, sz), "Titanium", rot_z=a)

        rm = (rad0 + rad1) / 2
        bar = 0.07
        place(rm, fz - fh / 2 + bar / 2, rad1 - rad0, bar, thick)
        place(rm, fz + fh / 2 - bar / 2, rad1 - rad0, bar, thick)
        place(rad0 + bar / 2, fz, bar, fh, thick)
        place(rad1 - bar / 2, fz, bar, fh, thick)
        for j in range(1, 6):
            place(rad0 + (rad1 - rad0) * j / 6, fz, 0.035, fh - 2 * bar, thick * 0.85)
        for j in range(1, 5):
            place(rm, fz - fh / 2 + fh * j / 5, rad1 - rad0 - 2 * bar, 0.035, thick * 0.85)
        # Hinge housing on the body.
        gf.box(((R + 0.08) * ca, (R + 0.08) * sa, fz), (0.34, 0.5, 1.25), "Carbon", rot_z=a)
    objs.append(gf.build("GridFins", mats))

    # Legs, stowed along the lower body: strut, fairing, foot and brace (never deployed).
    gl = C.Geo()
    for k in range(4):
        a = k * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        gl.box(((R + 0.16) * ca, (R + 0.16) * sa, 8.6), (0.34, 0.52, 10.6), "Carbon", rot_z=a)
        gl.box(((R + 0.2) * ca, (R + 0.2) * sa, 13.6), (0.5, 0.62, 1.2), "Carbon", rot_z=a)                  # upper fairing
        gl.box(((R + 0.31) * ca, (R + 0.31) * sa, 3.35), (0.5, 0.72, 0.5), "Steel", rot_z=a)                 # foot pad
        gl.box(((R + 0.22) * ca, (R + 0.22) * sa, 5.2), (0.18, 0.2, 4.4), "Steel", rot_z=a + 0.0)            # brace
        gl.box(((R + 0.13) * ca, (R + 0.13) * sa, 4.6), (0.22, 0.46, 2.0), "Steel", rot_z=a)                 # lower strut
    objs.append(gl.build("Legs", mats))

    # Details: cable raceway, cold-gas thrusters, payload-adapter ring, interstage vents.
    gd = C.Geo()
    gd.box(((R + 0.06) * math.cos(0.4), (R + 0.06) * math.sin(0.4), (TANK0 + TANK1) / 2), (0.16, 0.24, TANK1 - TANK0 - 0.8), "Carbon", rot_z=0.4)
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4 + 0.0
        for dz in (-0.12, 0.12):
            gd.box(((R * 0.98 + 0.07) * math.cos(a + 0.5), (R * 0.98 + 0.07) * math.sin(a + 0.5), 40.7 + dz), (0.14, 0.14, 0.12), "Carbon", rot_z=a + 0.5)
    for k in range(8):
        a = k * math.pi / 4 + 0.2
        gd.box((R * 0.9 * math.cos(a), R * 0.9 * math.sin(a), 42.03), (0.22, 0.22, 0.07), "Titanium", rot_z=a)
    objs.append(gd.build("Details", mats))

    # Stable node order for the export.
    return objs


def main():
    out = C.script_args()[0]
    build()
    C.export_glb(out)
    print("exported", out, os.path.getsize(out), "bytes")


main()
