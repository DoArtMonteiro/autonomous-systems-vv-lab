r"""Builds a geographic environment pack for V&V Lab Studio from public, keyless sources.

A pack is the geographic context of a replay: a terrain height grid and a true-colour image on a
regular grid of a local east-north-up (ENU) tangent plane, plus a manifest that names the origin,
the datums, the sources, their licences and the SHA-256 of every file. Studio never downloads
anything; packs are built here, on purpose, by a person who runs this command.

    python -m venv .geovenv && .geovenv\Scripts\pip install rasterio pyproj numpy pillow
    .geovenv\Scripts\python scripts/geo/build_environment.py --env cape-canaveral --out desktop/environments

Sources (fetched over HTTPS from public AWS Open Data buckets, no account or key):
  - Copernicus DEM GLO-30 (copernicus-dem-30m), a digital surface model, heights relative to EGM2008.
  - Sentinel-2 L2A true-colour image (TCI) of one scene, located with the Earth Search STAC API.
  - The EGM2008 geoid undulation at the origin, through PROJ (us_nga_egm08_25 grid, PROJ CDN).

Geometry. For every grid node (e, n) the script finds the terrain point whose exact ENU east and
north are (e, n): it starts from the tangent-plane point, converts it to geodetic coordinates,
samples the DEM there and iterates until the ENU east/north of (lat, lon, h_DEM) match to 1 mm. The
stored value is that point's ENU up component, so the curvature of the Earth and the tilt of the
local vertical are in the heights. Image texels use the same construction, so the image is
registered on the terrain. ENU is computed with pyproj (WGS84, EPSG:4978/4979); the Studio's Rust
georeference crate is tested against the nodes stored here (independent implementation).
"""

import argparse
import datetime
import hashlib
import io
import json
import math
import os
import sys
import urllib.request

import numpy as np
import pyproj
import rasterio
from PIL import Image
from rasterio.env import Env
from rasterio.merge import merge
from rasterio.windows import from_bounds

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detail_sources  # noqa: E402

DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif"
STAC = "https://earth-search.aws.element84.com/v1/search"

ENVIRONMENTS = {
    "cape-canaveral": {
        "name": "Cape Canaveral coast, Florida",
        "summary": "Low, flat barrier coast on the Atlantic. The simulation's pad centre is placed at the centre of a circular hard-standing visible in the detail image, measured on that image (about 2 m). The facility is not modelled and the simulated pad is not that facility.",
        "site_note": "The detail image is an aerial photograph of an existing landing facility. The simulated vehicle, pad and mission are generic: they are not that facility, its operations or its operator, and imply no affiliation.",
        "lat": 28.48573, "lon": -80.54302,
        "half_extent_m": 9000.0, "dem_spacing_m": 30.0, "image_spacing_m": 10.0,
        "s2_items": ["S2B_T17RNM_20251115T160505_L2A"],
        "heading_deg": 0.0,
        # Detail layer: USGS 3DEP 1 m lidar DEM sampled every 4 m and NAIP 2023 (0.3 m) at 0.5 m.
        "detail": {"half_extent_m": 1024.0, "dem_spacing_m": 4.0, "image_spacing_m": 0.5, "blend_m": 192.0,
                   "dem": {"kind": "tnm-1m"}, "imagery": {"kind": "naip", "year": 2023}},
    },
    "santa-maria-azores": {
        "name": "Santa Maria, Azores",
        "summary": "Volcanic island with cliffs and a plateau. The simulation's pad centre is placed in an open pasture on the eastern uplands, read from the 2024 orthophoto; the slopes around it break the flat-ground assumption of the simulation, which the Studio states. No launch or landing facility is there or is implied.",
        "lat": 36.98645, "lon": -25.10763,
        "half_extent_m": 9000.0, "dem_spacing_m": 30.0, "image_spacing_m": 10.0,
        "s2_items": ["S2A_T26SPF_20250423T123128_L2A", "S2A_T26SPG_20250423T123128_L2A"],
        "heading_deg": 0.0,
        # Detail layer: the 2024 orthophoto of the Azores government (8 cm flight) rendered at 0.5 m
        # by its WMS; heights stay those of Copernicus GLO-30 (no keyless high-resolution DEM).
        "detail": {"half_extent_m": 1024.0, "dem_spacing_m": 8.0, "image_spacing_m": 0.5, "blend_m": 192.0,
                   "dem": {"kind": "base"},
                   "imagery": {"kind": "wms", "licence": "azores-orto-2024", "year": 2024,
                               "url": "https://ambiente.azores.gov.pt/qgisserver/sma/orto2024/qgis_mapserv.fcgi", "layer": "ortofotomapa_2024_sma"}},
    },
    "spaceport-america": {
        "name": "Spaceport America, New Mexico",
        "summary": "High desert basin of the Jornada del Muerto at about 1400 m. The simulation's pad centre is placed on open desert ground, read from the detail image. Nearly flat around the pad, so the flat-ground assumption of the simulation holds well here.",
        "site_note": "The detail image covers part of an existing commercial spaceport. The simulated vehicle, pad and mission are generic: they are not that spaceport, its facilities or its operations, and imply no affiliation.",
        "lat": 32.99000, "lon": -106.96000,
        "half_extent_m": 9000.0, "dem_spacing_m": 30.0, "image_spacing_m": 10.0,
        "s2_items": ["S2C_T13SCS_20250430T180009_L2A", "S2B_T13SCS_20250415T180113_L2A"],
        "heading_deg": 0.0,
        "detail": {"half_extent_m": 1024.0, "dem_spacing_m": 4.0, "image_spacing_m": 0.5, "blend_m": 192.0,
                   "dem": {"kind": "tnm-1m"}, "imagery": {"kind": "naip", "year": 2022}},
    },
}

LICENCES = {
    "copernicus-dem": {
        "provider": "European Space Agency and European Union (Copernicus programme); WorldDEM-30 produced by DLR and Airbus",
        "product": "Copernicus DEM GLO-30 (digital surface model, 1 arc-second; vertical datum EGM2008, EPSG 3855; horizontal WGS84-G1150, EPSG 4326)",
        "licence": "Licence for the use of the Copernicus WorldDEM-30: free of charge; reproduction, distribution, communication to the public and adaptation are permitted (Art. 4, 5), with the notices of Art. 6; no endorsement may be implied and later users are bound by the same obligations. https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf",
        "attribution": "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.",
        "access": "AWS Open Data, s3://copernicus-dem-30m (no account)",
        "credit": "Copernicus WorldDEM-30 © DLR e.V. 2010-2014, © Airbus 2014-2018",
    },
    "sentinel-2": {
        "provider": "European Union, Copernicus Sentinel-2 (ESA), Level-2A processing; cloud-optimised copy by Element 84 on AWS Open Data",
        "product": "Sentinel-2 Level-2A true-colour image (TCI, 10 m)",
        "licence": "Legal notice on the use of Copernicus Sentinel data and service information (European Commission): free, full and open access, including reproduction, distribution, communication to the public, adaptation and combination; users waive claims for damages. https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
        "attribution": "Contains modified Copernicus Sentinel data {year}",
        "access": "Earth Search STAC API https://earth-search.aws.element84.com/v1, collection sentinel-2-c1-l2a (no account)",
    },
    "egm2008": {
        "provider": "U.S. National Geospatial-Intelligence Agency, EGM2008, through the PROJ data grid us_nga_egm08_25",
        "product": "Geoid undulation at the origin (EGM2008 to the WGS84 ellipsoid)",
        "licence": "Public domain (U.S. Government work); PROJ-data grid redistributed under its stated terms. https://cdn.proj.org",
        "attribution": "EGM2008, NGA",
        "access": "PROJ network grid (cdn.proj.org)",
        "credit": "EGM2008, NGA",
    },
}

DETAIL_LICENCES = {
    "azores-orto-2024": {
        "provider": "Secretaria Regional do Ambiente e Ação Climática, Governo dos Açores (SRAAC), through its WMS",
        "product": "Ortofotomapa de Santa Maria 2024 (flight of July and August 2024, 8 cm ground sampling), rendered by the WMS at the texel size",
        "licence": "CC BY 4.0, as stated in the ISO metadata record 3dbb1054-1690-43a5-b7d7-1835d5f64ef5 of the IDEiA catalogue (sma.idea.azores.gov.pt/geonetwork): \"Acesso público sem restrições\"; \"Licença de utilização - CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)\". No separate terms page was found; the licence comes from that record only.",
        "attribution": "Ortofotomapa de Santa Maria 2024 © SRAAC/Governo dos Açores, CC BY 4.0, modified (resampled and colour-balanced)",
        "credit": "Ortofoto 2024 © SRAAC/Governo dos Açores, CC BY 4.0",
        "access": "WMS 1.3.0 https://ambiente.azores.gov.pt/qgisserver/sma/orto2024/qgis_mapserv.fcgi, layer ortofotomapa_2024_sma (no account)",
    },
    "tnm-1m": {
        "provider": "U.S. Geological Survey, 3D Elevation Program (3DEP), through The National Map",
        "product": "USGS 1 m lidar digital elevation model (bare earth; heights NAVD88, converted here to NAD83(2011) ellipsoidal heights with the NOAA GEOID18 model)",
        "licence": "U.S. Public Domain: \"USGS-authored or produced data and information are considered to be in the U.S. Public Domain.\" https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
        "attribution": "Elevation: U.S. Geological Survey, 3D Elevation Program",
        "credit": "USGS 3DEP lidar",
        "access": "The National Map API https://tnmaccess.nationalmap.gov/api/v1/products and s3://prd-tnm (no account)",
    },
    "naip": {
        "provider": "USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (National Agriculture Imagery Program); cloud-optimised copy on the Microsoft Planetary Computer",
        "product": "NAIP orthoimagery (red, green, blue bands)",
        "licence": "Public domain under the FSA web policy: \"Public domain information may be freely distributed or copied, but use of appropriate byline/photo/image credits is requested.\" https://www.fsa.usda.gov/help/policies-and-links. No NAIP-specific licence document was found; the Planetary Computer gives no licence link.",
        "attribution": "Imagery: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations, NAIP {year}",
        "credit": "USDA NAIP {year}",
        "access": "Planetary Computer STAC https://planetarycomputer.microsoft.com/api/stac/v1, collection naip (anonymous range requests)",
    },
}

GEOD = pyproj.CRS("EPSG:4979")
ECEF = pyproj.CRS("EPSG:4978")
TO_ECEF = pyproj.Transformer.from_crs(GEOD, ECEF, always_xy=True)
TO_GEOD = pyproj.Transformer.from_crs(ECEF, GEOD, always_xy=True)


def enu_basis(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    e = np.array([-math.sin(lo), math.cos(lo), 0.0])
    n = np.array([-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)])
    u = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    return np.stack([e, n, u])  # rows: e, n, u


class Frame:
    def __init__(self, lat, lon, h):
        self.lat, self.lon, self.h = lat, lon, h
        self.o = np.array(TO_ECEF.transform(lon, lat, h))
        self.R = enu_basis(lat, lon)

    def to_enu(self, lat, lon, h):
        x, y, z = TO_ECEF.transform(lon, lat, h)
        d = np.stack([x - self.o[0], y - self.o[1], z - self.o[2]], axis=-1)
        return d @ self.R.T

    def to_geod(self, e, n, u):
        d = np.stack([e, n, u], axis=-1) @ self.R
        lon, lat, h = TO_GEOD.transform(d[..., 0] + self.o[0], d[..., 1] + self.o[1], d[..., 2] + self.o[2])
        return lat, lon, h


class Dem:
    """Copernicus GLO-30 heights in a window, sampled bilinearly at pixel centres."""

    def __init__(self, lat0, lon0, lat1, lon1, raw_dir):
        tiles = []
        for la in range(math.floor(lat0), math.floor(lat1) + 1):
            for lo in range(math.floor(lon0), math.floor(lon1) + 1):
                ns = f"N{la:02d}" if la >= 0 else f"S{-la:02d}"
                ew = f"E{lo:03d}" if lo >= 0 else f"W{-lo:03d}"
                tiles.append(f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM")
        srcs, found, missing = [], [], []
        with Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            for t in tiles:
                try:
                    srcs.append(rasterio.open("/vsicurl/" + DEM_URL.format(t=t)))
                    found.append(t)
                except rasterio.errors.RasterioIOError:
                    # The product has no tile where the whole degree square is open sea.
                    missing.append(t)
            if not srcs:
                raise SystemExit("no DEM tile covers the extent")
            try:
                # Bounds snapped to the source pixel grid, so the mosaic is not resampled.
                tr = srcs[0].transform
                res = abs(tr.a)
                pad = 4 * res
                snap = lambda v, o: o + math.floor((v - o) / res) * res
                left = snap(lon0 - pad, tr.c)
                top = tr.f - math.floor((tr.f - (lat1 + pad)) / res) * res
                right = snap(lon1 + pad, tr.c) + res
                bottom = tr.f - math.ceil((tr.f - (lat0 - pad)) / res) * res
                z, T = merge(srcs, bounds=(left, bottom, right, top), res=res, nodata=-32768.0)
                self.z = z[0].astype(np.float64)
                self.T = T
                self.tags = srcs[0].tags()
                for s in srcs:
                    if abs(abs(s.transform.a) - res) > 1e-12:
                        raise SystemExit("DEM tiles with different resolutions")
            finally:
                for s in srcs:
                    s.close()
        self.tile = " + ".join(found)
        self.missing = missing
        self.url = " ".join(DEM_URL.format(t=t) for t in found)
        hole = self.z == -32768.0
        if hole.any() and not missing:
            raise SystemExit("the DEM mosaic has holes")
        # Squares without a tile are open sea: height 0 m above EGM2008.
        self.z[hole] = 0.0
        self.sea_fill_fraction = float(hole.mean())
        np.save(os.path.join(raw_dir, "dem-window.npy"), self.z)
        if not np.isfinite(self.z).all():
            raise SystemExit("the DEM window has missing values")

    def sample(self, lat, lon):
        inv = ~self.T
        col, row = inv * (lon, lat)
        x = col - 0.5
        y = row - 0.5
        x0 = np.clip(np.floor(x).astype(int), 0, self.z.shape[1] - 2)
        y0 = np.clip(np.floor(y).astype(int), 0, self.z.shape[0] - 2)
        fx = np.clip(x - x0, 0, 1)
        fy = np.clip(y - y0, 0, 1)
        z = self.z
        return (z[y0, x0] * (1 - fx) * (1 - fy) + z[y0, x0 + 1] * fx * (1 - fy)
                + z[y0 + 1, x0] * (1 - fx) * fy + z[y0 + 1, x0 + 1] * fx * fy)


def surface_points(frame, dem, N, e, n):
    """Terrain points whose exact ENU east/north are (e, n). Returns lat, lon, H (EGM2008) and up."""
    ge, gn = e.astype(np.float64).copy(), n.astype(np.float64).copy()
    u = np.zeros_like(ge)
    for _ in range(10):
        lat, lon, _h = frame.to_geod(ge, gn, u)
        H = dem.sample(lat, lon)
        enu = frame.to_enu(lat, lon, H + N)
        de, dn = enu[..., 0] - e, enu[..., 1] - n
        u = enu[..., 2]
        err = float(np.hypot(de, dn).max())
        if err < 1e-3:
            return lat, lon, H, u, err
        ge, gn = ge - de, gn - dn
    raise SystemExit(f"surface points did not converge (residual {err:.4f} m)")


def surface_points_h(frame, h_of, e, n):
    """As surface_points, for a source that gives ellipsoidal heights h_of(lat, lon) directly."""
    ge, gn = e.astype(np.float64).copy(), n.astype(np.float64).copy()
    u = np.zeros_like(ge)
    for _ in range(10):
        lat, lon, _h = frame.to_geod(ge, gn, u)
        h = h_of(lat, lon)
        enu = frame.to_enu(lat, lon, h)
        de, dn = enu[..., 0] - e, enu[..., 1] - n
        u = enu[..., 2]
        err = float(np.hypot(de, dn).max())
        if err < 1e-3:
            return lat, lon, h, u, err
        ge, gn = ge - de, gn - dn
    raise SystemExit(f"detail surface points did not converge (residual {err:.4f} m)")


def lattice_geodetic(frame, h_of, L, sp, step):
    """Geodetic latitude and longitude of every texel centre of a (2L/sp)^2 image, from exact surface
    points on a lattice every `step` texels, bilinearly interpolated between them. Over a lattice
    cell (`step * sp` metres) the error of the interpolation is far below a millimetre."""
    n = int(round(2 * L / sp))
    m = n // step + 1
    ax = -L + sp / 2 + np.arange(m) * step * sp
    E, N = np.meshgrid(ax, ax[::-1])
    lat, lon, _h, _u, err = surface_points_h(frame, h_of, E, N)

    def rows(r0, r1):
        r = np.arange(r0, r1)[:, None] / step
        c = np.arange(n)[None, :] / step
        i0 = np.clip(np.floor(r).astype(int), 0, m - 2)
        j0 = np.clip(np.floor(c).astype(int), 0, m - 2)
        fr, fc = r - i0, c - j0

        def interp(a):
            return (a[i0, j0] * (1 - fr) * (1 - fc) + a[i0, j0 + 1] * (1 - fr) * fc
                    + a[i0 + 1, j0] * fr * (1 - fc) + a[i0 + 1, j0 + 1] * fr * fc)
        return interp(lat), interp(lon)
    return n, rows, err


def build_detail(cfg, frame, hd, imagery, out, base_img):
    """Writes detail-height.u16 and detail-image.jpg; returns the layer block, checks and grid."""
    d = cfg["detail"]
    L = d["half_extent_m"]
    s = d["dem_spacing_m"]
    k = int(round(L / s))
    axis = np.arange(-k, k + 1) * s
    E, N = np.meshgrid(axis, axis[::-1])
    lat, lon, h, U, err = surface_points_h(frame, hd, E, N)
    print(f"detail grid {U.shape}, max horizontal residual {err * 1000:.3f} mm", file=sys.stderr)
    scale = 0.01
    offset = float(math.floor(U.min()) - 1)
    q = np.round((U - offset) / scale)
    if q.max() > 65535:
        raise SystemExit("detail relief exceeds the 16-bit range at 1 cm")
    hbytes = q.astype("<u2").tobytes()
    with open(os.path.join(out, "detail-height.u16"), "wb") as f:
        f.write(hbytes)
    checks = []
    for (r, c) in [(0, 0), (0, 2 * k), (2 * k, 0), (2 * k, 2 * k), (k, k), (k // 3, k + k // 2)]:
        checks.append({"lat_deg": float(lat[r, c]), "lon_deg": float(lon[r, c]), "h_ellipsoid_m": float(h[r, c]),
                       "enu_m": [float(E[r, c]), float(N[r, c]), float(U[r, c])], "layer": "detail"})
    si = d["image_spacing_m"]
    n, rows, ierr = lattice_geodetic(frame, hd, L, si, 16)
    img = np.zeros((n, n, 3), dtype=np.uint8)
    have = np.zeros((n, n), dtype=bool)
    for r0 in range(0, n, 256):
        la, lo = rows(r0, min(n, r0 + 256))
        v, ok = imagery.sample(la, lo)
        img[r0:r0 + la.shape[0]] = np.clip(np.round(v), 0, 255).astype(np.uint8).transpose(1, 2, 0)
        # Near-black texels are the source's padding (often JPEG-compressed, so not exactly 0).
        have[r0:r0 + la.shape[0]] = ok & (v.sum(axis=0) >= 24)
    # The base image under every detail texel (bilinear on the base ENU grid).
    Lb, sb = base_img["half"], base_img["spacing"]
    ax = -L + si / 2 + np.arange(n) * si
    col = (ax + Lb) / sb - 0.5
    row = (Lb - ax) / sb - 0.5
    bimg = base_img["rgb"].astype(np.float32).transpose(2, 0, 1)
    under = np.zeros((n, n, 3), dtype=np.float32)
    for r0 in range(0, n, 256):
        R, C = np.meshgrid(row[r0:r0 + 256], col, indexing="ij")
        bv, _ok = detail_sources.bilinear(bimg, C, R)
        under[r0:r0 + R.shape[0]] = bv.transpose(1, 2, 0)
    # Colour balance: per-channel tone curves that give the detail image, averaged on 10 m blocks,
    # the distribution of the base image there, so the two meet without a change of tone. Texels the detail
    # source does not cover take the base image.
    blk = max(1, int(round(sb / si)))
    m = (n // blk) * blk
    def blocks(a):
        return a[:m, :m].reshape(m // blk, blk, m // blk, blk, -1).mean(axis=(1, 3))
    dv = blocks(img.astype(np.float32))
    bv = blocks(under)
    hv = blocks(have[..., None].astype(np.float32))[..., 0] > 0.99
    fit = []
    out_img = img.astype(np.float32)
    qs = np.linspace(0, 100, 33)
    for c in range(3):
        # Histogram matching of the 10 m blocks: a monotone tone curve per channel, applied to
        # every texel, keeps the detail and takes the tones of the base image.
        xq = np.percentile(dv[..., c][hv], qs)
        yq = np.percentile(bv[..., c][hv], qs)
        xq = np.maximum.accumulate(xq + np.arange(len(xq)) * 1e-6)
        fit.append([[round(float(a), 2) for a in xq], [round(float(b), 2) for b in yq]])
        out_img[..., c] = np.interp(out_img[..., c], xq, yq)
    out_img[~have] = under[~have]
    img = np.clip(np.round(out_img), 0, 255).astype(np.uint8)
    filled = float((~have).mean())
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, "JPEG", quality=86, optimize=True, progressive=True)
    ibytes = buf.getvalue()
    with open(os.path.join(out, "detail-image.jpg"), "wb") as f:
        f.write(ibytes)
    layer = {
        "role": "detail",
        "extent_m": L,
        "blend_m": d["blend_m"],
        "height": {"file": "detail-height.u16", "encoding": "uint16-le", "scale_m": scale, "offset_m": offset,
                   "columns": int(U.shape[1]), "rows": int(U.shape[0]), "spacing_m": s, "first_node_m": [float(-k * s), float(k * s)],
                   "order": "row-major, row 0 at the north edge, column 0 at the west edge", "bytes": len(hbytes), "sha256": sha256(hbytes),
                   "min_up_m": round(float(U.min()), 2), "max_up_m": round(float(U.max()), 2)},
        "image": {"file": "detail-image.jpg", "columns": n, "rows": n, "spacing_m": si, "first_texel_centre_m": [-L + si / 2, L - si / 2],
                  "nodata_fraction": 0.0, "base_fill_fraction": round(filled, 5), "colour_fit": fit, "bytes": len(ibytes), "sha256": sha256(ibytes),
                  "processing": "Area-averaged to the texel size from the source, bilinear resampling onto the ENU grid, per-channel tone curves (colour_fit: 33 percentiles of the detail and of the base image on 10 m blocks, linearly interpolated) matching the detail image to the base image, texels without source data filled from the base image, JPEG quality 86.",
                  "geodetic_lattice_residual_mm": round(ierr * 1000, 3)},
        "note": f"Within {d['blend_m']:g} m of the edge of this layer the drawn heights blend linearly into the base grid and the image fades into the base image, so the two surfaces meet. That margin is a display adjustment of the context data.",
    }
    return layer, checks, (E, N, U, lat, lon)


def stac_item(item_id):
    req = urllib.request.Request(STAC, data=json.dumps({"ids": [item_id], "collections": ["sentinel-2-c1-l2a"]}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    if len(d["features"]) != 1:
        raise SystemExit(f"STAC item {item_id} not found")
    return d["features"][0]


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=sorted(ENVIRONMENTS), required=True)
    ap.add_argument("--out", required=True, help="parent directory of the pack")
    ap.add_argument("--raw", default=None, help="directory for the downloaded windows (default: <out>/../.geo-raw)")
    a = ap.parse_args()
    cfg = ENVIRONMENTS[a.env]
    out = os.path.join(a.out, a.env)
    raw = a.raw or os.path.join(os.path.dirname(os.path.abspath(a.out)), ".geo-raw", a.env)
    os.makedirs(out, exist_ok=True)
    os.makedirs(raw, exist_ok=True)

    pyproj.network.set_network_enabled(True)
    # only_best: fail rather than fall back silently to a transform without the geoid grid.
    geoid = pyproj.Transformer.from_crs("EPSG:4326+3855", "EPSG:4979", always_xy=True, only_best=True)
    lat0, lon0 = cfg["lat"], cfg["lon"]
    L = cfg["half_extent_m"]
    # Geographic bounds of the extent, with margin.
    dlat = (L * 1.6) / 111000.0
    dlon = (L * 1.6) / (111000.0 * math.cos(math.radians(lat0)))
    dem = Dem(lat0 - dlat, lon0 - dlon, lat0 + dlat, lon0 + dlon, raw)
    H0 = float(dem.sample(np.array(lat0), np.array(lon0)))
    N0 = float(geoid.transform(lon0, lat0, 0.0)[2])
    corners = [geoid.transform(lon0 + sx * dlon / 1.6, lat0 + sy * dlat / 1.6, 0.0)[2] for sx in (-1, 1) for sy in (-1, 1)]
    N_spread = float(max(corners) - min(corners))
    det = cfg.get("detail")
    hd = imagery = det_dem_items = None
    if det:
        # The origin goes on the finest layer: the detail terrain.
        Ld = det["half_extent_m"] * 1.25
        dl, dn_ = Ld / 111000.0, Ld / (111000.0 * math.cos(math.radians(lat0)))
        box = (lat0 - dl, lat0 + dl, lon0 - dn_, lon0 + dn_)
        if det["dem"]["kind"] == "tnm-1m":
            src = detail_sources.TnmLidarDem(*box, raw)
            # Open water has no lidar value: there the base DEM (sea at 0 m above EGM2008) is used.
            hd = lambda la, lo: src.h_ellipsoid(la, lo, lambda a, b: dem.sample(a, b) + N0)  # noqa: E731
            det_dem_items = src.tiles
        else:
            hd = lambda la, lo: dem.sample(la, lo) + N0  # noqa: E731
        if det["imagery"]["kind"] == "naip":
            imagery = detail_sources.NaipImagery(*box, det["imagery"]["year"], det["image_spacing_m"], raw)
        else:
            im = det["imagery"]
            imagery = detail_sources.WmsImagery(im["url"], im["layer"], *box, det["image_spacing_m"], raw)
        h_ell0 = float(hd(np.array([lat0]), np.array([lon0]))[0])
        H0 = h_ell0 - N0
    frame = Frame(lat0, lon0, H0 + N0)

    # Height grid.
    s = cfg["dem_spacing_m"]
    k = int(round(L / s))
    axis = np.arange(-k, k + 1) * s
    E, Nn = np.meshgrid(axis, axis[::-1])  # row 0 is the north edge
    lat, lon, H, U, err = surface_points(frame, dem, N0, E, Nn)
    print(f"height grid {U.shape}, max horizontal residual {err * 1000:.3f} mm", file=sys.stderr)
    scale = 0.01
    offset = float(math.floor(U.min()) - 1)
    q = np.round((U - offset) / scale)
    if q.max() > 65535:
        raise SystemExit("relief exceeds the 16-bit range at 1 cm")
    hbytes = q.astype("<u2").tobytes()
    with open(os.path.join(out, "height.u16"), "wb") as f:
        f.write(hbytes)

    # Check nodes for the Rust crate: geodetic point and its ENU, a sparse subset.
    checks = []
    for (r, c) in [(0, 0), (0, 2 * k), (2 * k, 0), (2 * k, 2 * k), (k, k), (k // 2, k + k // 3), (k + k // 4, k // 5)]:
        checks.append({"lat_deg": float(lat[r, c]), "lon_deg": float(lon[r, c]), "h_ellipsoid_m": float(H[r, c] + N0),
                       "enu_m": [float(E[r, c]), float(Nn[r, c]), float(U[r, c])]})

    # Image: the first item that has data at a texel wins; the next items fill its gaps.
    items = [stac_item(i) for i in cfg["s2_items"]]
    si = cfg["image_spacing_m"]
    ki = int(round(L / si))
    iax = np.arange(-ki, ki) * si + si / 2
    IE, IN = np.meshgrid(iax, iax[::-1])
    ilat, ilon, _IH, _IU, ierr = surface_points(frame, dem, N0, IE, IN)
    px = np.zeros((3,) + IE.shape)
    have = np.zeros(IE.shape, dtype=bool)
    used = []
    for item in items:
        href = item["assets"]["visual"]["href"]
        with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open("/vsicurl/" + href) as d:
                to_img = pyproj.Transformer.from_crs("EPSG:4326", d.crs, always_xy=True)
                X, Y = to_img.transform(ilon, ilat)
                w = from_bounds(X.min() - 50, Y.min() - 50, X.max() + 50, Y.max() + 50, d.transform).round_offsets().round_lengths()
                # Boundless: texels outside the scene read as 0 (no data), never as shifted pixels.
                rgb = d.read(window=w, boundless=True, fill_value=0).astype(np.float64)
                T = d.window_transform(w)
                img_crs = str(d.crs)
        np.save(os.path.join(raw, f"{item['id']}-window.npy"), rgb.astype(np.uint8))
        col, row = (~T) * (X, Y)
        x = col - 0.5
        y = row - 0.5
        x0 = np.clip(np.floor(x).astype(int), 0, rgb.shape[2] - 2)
        y0 = np.clip(np.floor(y).astype(int), 0, rgb.shape[1] - 2)
        fx = np.clip(x - x0, 0, 1)[None]
        fy = np.clip(y - y0, 0, 1)[None]
        corners = [rgb[:, y0, x0], rgb[:, y0, x0 + 1], rgb[:, y0 + 1, x0], rgb[:, y0 + 1, x0 + 1]]
        valid = np.all([c.sum(axis=0) > 0 for c in corners], axis=0)
        val = corners[0] * (1 - fx) * (1 - fy) + corners[1] * fx * (1 - fy) + corners[2] * (1 - fx) * fy + corners[3] * fx * fy
        take = valid & ~have
        px[:, take] = val[:, take]
        have |= take
        used.append({"item": item["id"], "url": href, "acquired": item["properties"]["datetime"],
                     "cloud_cover_percent": item["properties"].get("eo:cloud_cover"), "crs": img_crs,
                     "texel_fraction": round(float(take.mean()), 4)})
    nodata = ~have
    img = np.clip(np.round(px), 0, 255).astype(np.uint8).transpose(1, 2, 0)
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, "JPEG", quality=88, optimize=True, progressive=True)
    ibytes = buf.getvalue()
    with open(os.path.join(out, "image.jpg"), "wb") as f:
        f.write(ibytes)

    layers = []
    if det:
        layer, dchecks, (Ed, Nd, Ud, dlat_g, dlon_g) = build_detail(cfg, frame, hd, imagery, out, {"rgb": img, "half": L, "spacing": si})
        det_fill = float(1.0 - src.win.sample(dlat_g, dlon_g)[1].mean()) if det_dem_items is not None else 0.0
        layers.append(layer)
        for c in checks:
            c["layer"] = "base"
        checks += dchecks

    # Registration check: the DEM land mask against the image water mask, best shift within 300 m.
    land = dem.sample(ilat, ilon) > 1.0
    f32 = img.astype(np.float32)
    water = (f32.mean(axis=2) < 60) & (f32[..., 2] >= f32[..., 0])
    dry = ~water & have
    step = 3
    best = None
    for dy in range(-30, 31, step):
        for dx in range(-30, 31, step):
            a_ = np.roll(np.roll(land, dy, axis=0), dx, axis=1)[40:-40:2, 40:-40:2]
            b_ = dry[40:-40:2, 40:-40:2]
            ok = have[40:-40:2, 40:-40:2]
            agree = float((a_ == b_)[ok].mean())
            if best is None or agree > best[0]:
                best = (agree, dx, dy)
    zero = float((land == dry)[40:-40:2, 40:-40:2][have[40:-40:2, 40:-40:2]].mean())
    registration = {"agreement_at_zero_shift": round(zero, 4), "best_agreement": round(best[0], 4),
                    "best_shift_east_m": best[1] * si, "best_shift_north_m": -best[2] * si,
                    "method": "Fraction of texels where the DEM says land (> 1 m) and the image is not dark water, at zero shift and at the best shift on a 30 m lattice within 300 m."}
    print("registration", registration, file=sys.stderr)

    # Relief around the origin, against the simulation's flat ground at z = 0.
    def relief(radius):
        # Inside the detail layer the relief is read from it (the terrain drawn there).
        if det and radius < det["half_extent_m"] - det["blend_m"]:
            m = np.hypot(Ed, Nd) <= radius
            return {"radius_m": radius, "min_up_m": round(float(Ud[m].min()), 2), "max_up_m": round(float(Ud[m].max()), 2)}
        m = np.hypot(E, Nn) <= radius
        return {"radius_m": radius, "min_up_m": round(float(U[m].min()), 2), "max_up_m": round(float(U[m].max()), 2)}

    years = sorted({u["acquired"][:4] for u in used})
    s2 = dict(LICENCES["sentinel-2"])
    s2["attribution"] = s2["attribution"].format(year=", ".join(years))
    s2["credit"] = s2["attribution"]
    extra_sources = []
    extra_accuracy = []
    if det:
        if det["dem"]["kind"] == "tnm-1m":
            extra_sources.append({**DETAIL_LICENCES["tnm-1m"], "layer": "detail", "items": det_dem_items, "water_fill_fraction": round(det_fill, 4),
                                  "water_fill_note": "Detail nodes where the lidar DEM has no value (open water) take the base DEM height there."})
            extra_accuracy.append(f"Detail layer ({2 * det['half_extent_m'] / 1000:g} km square around the origin): heights from the USGS 1 m lidar DEM, a bare-earth model, sampled every {det['dem_spacing_m']:g} m. NAVD88 heights are converted with GEOID18 to NAD83(2011) ellipsoidal heights and used as WGS84 heights, which differ by about a metre; the origin is on this surface.")
        if det["imagery"]["kind"] == "naip":
            years = sorted({(i["acquired"] or "")[:4] for i in imagery.items})
            lic = dict(DETAIL_LICENCES["naip"])
            lic["attribution"] = lic["attribution"].format(year=", ".join(years))
            lic["credit"] = lic["credit"].format(year=", ".join(years))
            extra_sources.append({**lic, "layer": "detail", "items": imagery.items})
            extra_accuracy.append(f"Detail image: NAIP {', '.join(years)} at {det['image_spacing_m']:g} m per texel (source {imagery.items[0]['gsd_m']} m). NAIP and 3DEP are on NAD83(2011) and are read here as WGS84, a horizontal offset of about 1 to 2 m.")
        if det["imagery"]["kind"] == "wms":
            lic = DETAIL_LICENCES[det["imagery"]["licence"]]
            extra_sources.append({**lic, "layer": "detail", "requests": len(imagery.requests), "request_example": imagery.requests[0]})
            extra_accuracy.append(f"Detail image: the {det['imagery']['year']} orthophoto rendered by its WMS at {det['image_spacing_m']:g} m per texel, in EPSG:4326 tiles resampled onto the ENU grid. Its georeferencing is the publisher's; a residual offset of a few metres against the base layers cannot be excluded.")
        if det["dem"]["kind"] == "base":
            extra_accuracy.append(f"Detail heights are the base Copernicus GLO-30 surface sampled every {det['dem_spacing_m']:g} m: the detail layer adds image resolution, not terrain resolution.")
        extra_accuracy.append(f"Within {det['blend_m']:g} m of the edge of the detail layer the drawn heights blend into the base grid and the detail image fades into the base image; this display adjustment is the only change made to the context data.")
    manifest = {
        "schema": "vv-geo-environment.v2" if det else "vv-geo-environment.v1",
        "id": a.env,
        "name": cfg["name"],
        "summary": cfg["summary"],
        **({"site_note": cfg["site_note"]} if cfg.get("site_note") else {}),
        "built": {"by": "scripts/geo/build_environment.py", "date": datetime.date.today().isoformat(),
                  "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str, "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__},
        "origin": {
            "lat_deg": lat0, "lon_deg": lon0,
            "h_ellipsoid_m": round(H0 + N0, 3),
            "orthometric_height_m": round(H0, 3),
            "geoid_undulation_m": round(N0, 3),
            "geoid_undulation_spread_m": round(N_spread, 3),
            "note": ("The simulation's pad centre (model origin, z = 0) is placed on the detail terrain at this point; the orthometric height is that ellipsoidal height minus the EGM2008 undulation. " if det else "The simulation's pad centre (model origin, z = 0) is placed on the DEM surface at this point. ") + "The geoid undulation is treated as constant over the extent (its spread across the corners is given).",
        },
        "frame": {
            "kind": "enu-tangent-plane",
            "ellipsoid": "WGS84",
            "axes": {"x": "east", "y": "north", "z": "up"},
            "heading_deg": cfg["heading_deg"],
            "note": "Model x, y, z map to east, north, up of the tangent plane at the origin. Terrain heights are ENU up, so they include the curvature of the Earth.",
        },
        "extent_m": L,
        "height": {
            "file": "height.u16", "encoding": "uint16-le", "scale_m": scale, "offset_m": offset,
            "columns": int(U.shape[1]), "rows": int(U.shape[0]), "spacing_m": s,
            "first_node_m": [float(-k * s), float(k * s)],
            "order": "row-major, row 0 at the north edge, column 0 at the west edge",
            "bytes": len(hbytes), "sha256": sha256(hbytes),
            "min_up_m": round(float(U.min()), 2), "max_up_m": round(float(U.max()), 2),
        },
        "image": {
            "file": "image.jpg", "columns": int(img.shape[1]), "rows": int(img.shape[0]), "spacing_m": si,
            "first_texel_centre_m": [float(iax[0]), float(iax[-1])],
            "nodata_fraction": round(float(nodata.mean()), 4),
            "registration": registration,
            "bytes": len(ibytes), "sha256": sha256(ibytes),
            "processing": "Bilinear resampling of the TCI asset onto the ENU grid, JPEG quality 88. No colour editing.",
        },
        "layers": layers,
        "relief": [relief(10.0), relief(50.0), relief(500.0), relief(3000.0)],
        "accuracy": [
            "Copernicus GLO-30 is a surface model: heights include buildings and vegetation canopy. Its stated absolute vertical accuracy is better than 4 m (90 % linear error); it does not resolve pads, roads or ground conditions.",
            "The 10 m image does not resolve structures; it is context only.",
            "The simulation assumes flat ground at z = 0 and computes no interaction with this terrain. Where the terrain rises above z = 0 the drawn trajectory may pass through it; this is a property of the geographic placement, not of the simulated flight.",
            "Horizontal registration of image and terrain follows the sources' georeferencing; Sentinel-2 L2A geolocation is of the order of 10 m.",
        ] + extra_accuracy,
        "sources": [
            {**LICENCES["copernicus-dem"], "item": dem.tile, "url": dem.url, "raster_tags": dem.tags,
             "absent_tiles": dem.missing, "sea_fill_fraction": round(dem.sea_fill_fraction, 4),
             "sea_fill_note": "The product has no tile for a degree square of open sea; those squares are filled with 0 m above EGM2008."},
            {**s2, "items": used},
            LICENCES["egm2008"],
        ] + extra_sources,
        "checks": checks,
        "check_note": "Geodetic points of grid nodes and their ENU coordinates computed with pyproj; the Rust georeference crate must reproduce them within 1 mm.",
    }
    if not det:
        manifest.pop("layers")
    with open(os.path.join(out, "environment.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({"out": out, "height_bytes": len(hbytes), "image_bytes": len(ibytes), "H0": H0, "N0": N0, "relief": manifest["relief"], "image_residual_mm": ierr * 1000}, indent=1))


if __name__ == "__main__":
    main()
