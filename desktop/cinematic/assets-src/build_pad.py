"""Illustrative landing pad for the Cinematic View: concrete slab textures and the pad's props.

    blender --factory-startup --background --python build_pad.py -- <out dir>

Writes pad_albedo.png (RGBA, alpha = the slab's soft edge), pad_normal.png and pad_orm.png (G rough,
B metal) for a decal of 80 x 80 m centred on the pad centre (2048 px: 3.9 cm per texel), and
pad_props.glb: a floodlight mast, a flush edge light and a tall marker. Everything is generated from
code with fixed seeds. The geometry of the real pad is not modelled: this is an illustration whose
rings (landing radius 10 m, keep-out 50 m) come from the run record and are drawn separately.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import bpy  # noqa: E402

N = 2048
EXTENT = 80.0           # metres covered by the decal
SLAB_R = 36.5           # radius of the concrete slab
APRON_R = 39.0


def save(img, path):
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()


def textures(out):
    x = ((np.arange(N, dtype=np.float32) + 0.5) / N - 0.5) * EXTENT
    X, Y = np.meshgrid(x, x)                    # X east (columns), Y north (rows, bottom first)
    r = np.hypot(X, Y)
    ang = np.arctan2(Y, X)
    edge_n = C.fbm(N, N, 6, 6, 31, 4, wrap_u=False)
    mottle = C.fbm(N, N, 10, 10, 32, 5, wrap_u=False)
    fine = C.fbm(N, N, 160, 160, 33, 3, wrap_u=False)
    mid = C.fbm(N, N, 40, 40, 34, 4, wrap_u=False)
    # Slab and apron: a soft, slightly irregular edge.
    rr = r + (edge_n - 0.5) * 3.0
    slab = 1.0 - C.smoothstep(SLAB_R - 1.0, SLAB_R + 0.4, rr)
    apron = (1.0 - C.smoothstep(APRON_R - 1.5, APRON_R + 1.5, rr)) * (1.0 - slab)
    alpha = np.clip(slab + apron * 0.85, 0.0, 1.0)
    # Expansion joints: a 7.5 m grid on the slab, shifted so a joint does not cross the centre.
    jx = (X + 3.75) % 7.5
    jx = np.minimum(jx, 7.5 - jx)
    jy = (Y + 3.75) % 7.5
    jy = np.minimum(jy, 7.5 - jy)
    joint = np.clip(1.0 - C.smoothstep(0.02, 0.07, jx), 0, 1) + np.clip(1.0 - C.smoothstep(0.02, 0.07, jy), 0, 1)
    joint = np.clip(joint, 0, 1) * slab
    # Per-slab tone.
    sx = np.floor((X + 3.75) / 7.5).astype(np.int32) + 20
    sy = np.floor((Y + 3.75) / 7.5).astype(np.int32) + 20
    tone = ((sx * 73856093) ^ (sy * 19349663)) % 1000 / 1000.0
    tone = (tone - 0.5) * 0.12
    # Cracks: thin lines where a ridged noise is near zero, in a sparse mask.
    crk = np.abs(C.fbm(N, N, 14, 14, 35, 4, wrap_u=False) - 0.5)
    crack = (1.0 - C.smoothstep(0.004, 0.011, crk)) * C.smoothstep(0.52, 0.66, C.fbm(N, N, 5, 5, 36, 3, wrap_u=False)) * slab
    # Exhaust staining: radial streaks from the centre, a scorched core, and a few oil spots.
    a_noise = 0.5 + 0.5 * np.sin(ang * 23.0 + 6.0 * C.fbm(N, N, 4, 4, 38, 3, wrap_u=False)) * np.sin(ang * 7.0 + 3.0)
    blast = np.exp(-r / 13.0) * (0.55 + 0.6 * a_noise) * (0.7 + 0.5 * mid)
    scorch = np.clip(np.exp(-(r / 6.5) ** 2) * 0.55 + blast * 0.50, 0.0, 0.82)
    oil = np.clip((C.fbm(N, N, 22, 22, 39, 3, wrap_u=False) - 0.70) * 6.0, 0.0, 1.0) * slab * (1.0 - np.exp(-r / 8.0))
    # Markings (paint): landing ring r = 10 m, outer dashed ring r = 24 m, crosshair, four corner ticks.
    def ring(rad, w):
        return 1.0 - C.smoothstep(w * 0.5, w * 0.5 + 0.06, np.abs(r - rad))
    paint = ring(10.0, 0.7) + ring(3.0, 0.35)
    dashed = ring(24.0, 0.45) * (np.sin(ang * 48.0) > 0.0)
    cross = (1.0 - C.smoothstep(0.15, 0.22, np.abs(X))) * (np.abs(Y) < 10.0) + (1.0 - C.smoothstep(0.15, 0.22, np.abs(Y))) * (np.abs(X) < 10.0)
    ticks = 0.0
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        u = X * math.cos(a) + Y * math.sin(a)
        v = -X * math.sin(a) + Y * math.cos(a)
        ticks = np.maximum(ticks, (np.abs(v) < 0.5) * (u > 29.0) * (u < 35.0))
    paint = np.clip(paint + dashed + ticks + cross, 0.0, 1.0)
    wear = C.smoothstep(0.30, 0.75, C.fbm(N, N, 90, 90, 40, 3, wrap_u=False) + 0.35 * (1.0 - blast))
    paint = paint * wear * (1.0 - 0.7 * scorch) * slab
    # Albedo.
    conc = np.array([0.43, 0.42, 0.40], np.float32)
    base = conc[None, None, :] * (1.0 + tone[..., None] + (mottle - 0.5)[..., None] * 0.28 + (mid - 0.5)[..., None] * 0.14 + (fine - 0.5)[..., None] * 0.22)
    base = base * (1.0 - 0.55 * joint[..., None]) * (1.0 - 0.6 * crack[..., None])
    soot = np.array([0.045, 0.040, 0.037], np.float32)
    base = base * (1.0 - scorch[..., None]) + soot[None, None, :] * scorch[..., None] * (0.8 + 0.5 * fine[..., None])
    base = base * (1.0 - 0.7 * oil[..., None]) + np.array([0.03, 0.03, 0.035], np.float32) * 0.7 * oil[..., None]
    pc = np.array([0.82, 0.82, 0.78], np.float32)
    base = base * (1.0 - paint[..., None]) + pc[None, None, :] * paint[..., None]
    ap = np.array([0.27, 0.27, 0.27], np.float32)[None, None, :] * (0.85 + 0.3 * mottle[..., None])
    col = np.where(slab[..., None] > 0.01, base, ap)
    rgba = np.concatenate([C.srgb(np.clip(col, 0, 1)), alpha[..., None]], axis=-1)
    rough = np.clip(0.80 - 0.05 * (fine - 0.5) + 0.12 * scorch - 0.45 * oil - 0.2 * paint + 0.1 * joint, 0.05, 1.0)
    orm = np.stack([np.ones_like(rough), rough, np.zeros_like(rough), np.ones_like(rough)], axis=-1)
    hgt = -(joint * 1.0 + crack * 0.7) * 0.8 + (fine - 0.5) * 0.12 + (mottle - 0.5) * 0.05
    nrm = C.normal_from_height(hgt, 3.0)
    nrm = np.concatenate([nrm, np.ones((N, N, 1), np.float32)], axis=-1)
    for name, arr, cs in (("pad_albedo", rgba, "sRGB"), ("pad_normal", nrm, "Non-Color"), ("pad_orm", orm, "Non-Color")):
        img = C.make_image(name, arr, cs, "PNG")
        save(img, os.path.join(out, name + ".png"))


def props(out):
    C.reset()
    mats = {
        "Pole": C.principled("Pole", (0.30, 0.31, 0.33), 0.45, 0.85),
        "Lamp": C.principled("Lamp", (0.9, 0.9, 0.85), 0.3, 0.0),
        "Base": C.principled("Base", (0.40, 0.40, 0.38), 0.8, 0.0),
        "Marker": C.principled("Marker", (0.85, 0.35, 0.08), 0.6, 0.0),
    }
    gm = C.Geo()
    gm.lathe([(0.55, 0.0), (0.55, 0.4), (0.36, 0.5), (0.22, 0.8), (0.17, 15.5), (0.22, 16.0)], 20, "Pole")
    gm.box((0.0, 0.0, 16.4), (2.2, 1.0, 0.6), "Lamp")
    gm.box((0.0, 0.0, 16.05), (2.3, 1.1, 0.14), "Pole")
    ob = gm.build("Mast", mats)
    ge = C.Geo()
    ge.lathe([(0.34, 0.0), (0.34, 0.1), (0.28, 0.13), (0.0, 0.13)], 20, "Base")
    ge.lathe([(0.12, 0.13), (0.12, 0.16), (0.0, 0.16)], 14, "Lamp")
    oe = ge.build("EdgeLight", mats)
    gk = C.Geo()
    gk.lathe([(0.25, 0.0), (0.25, 0.25), (0.06, 0.3), (0.05, 2.4), (0.0, 2.45)], 12, "Pole")
    gk.box((0.0, 0.0, 2.2), (0.5, 0.05, 0.5), "Marker")
    ok = gk.build("Marker", mats)
    # Place the objects apart (they are instanced by name at run time, each at its own origin).
    C.export_glb(os.path.join(out, "pad_props.glb"), [ob, oe, ok])


def main():
    out = C.script_args()[0]
    os.makedirs(out, exist_ok=True)
    C.reset()
    textures(out)
    props(out)
    print("pad assets written to", out)


main()
