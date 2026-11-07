r"""Adds the three-dimensional world layer to an environment pack (schema vv-geo-environment.v3).

The terrain and image of a pack show the ground; this layer adds what stands on it:

  - buildings: OpenStreetMap footprints (ODbL), extruded to a height whose source is recorded per
    building: `lidar` (the 90th percentile of the lidar canopy height model inside the footprint),
    `osm-height` (the `height` tag), `osm-levels` (`building:levels` x 3.2 m + 1 m) or `default`
    (a fixed height per kind, an estimate);
  - lidar structures: raised, non-vegetated objects in the lidar that no OSM footprint covers,
    outlined from 1 m cells (surveyed height, footprint from the cell outline);
  - tall structures: OSM towers, masts, lighthouses and water towers (point features);
  - vegetation: one record per lidar crown or shrub clump where the canopy height model is raised and
    the cell is vegetated (NAIP near-infrared NDVI, or the share of multiple lidar returns). The
    position and height come from the lidar; the drawn shape is illustrative. Where a pack has no
    lidar, no vegetation is generated: the layer never invents surveyed-looking vegetation.

Nothing here feeds the simulation. The layer is geographic context, drawn by the Studio.

    geovenv\Scripts\python scripts/geo/build_features.py --env cape-canaveral

reads the lidar project and NAIP year from the entry's `world` block in catalogue.json; the same
can be given by hand with --pack, --ept, --ept-project and --naip-year.

Sources (keyless, public):
  - OpenStreetMap through the Overpass API (ODbL 1.0); the response timestamp is recorded.
  - USGS 3DEP lidar point clouds, Entwine Point Tile copies on AWS Open Data (usgs-lidar-public),
    U.S. Public Domain. Only the octree nodes over the lidar extent and down to about 1 m spacing
    are fetched, node by node, so memory stays bounded.
  - NAIP near-infrared and red bands (Planetary Computer), U.S. Public Domain.

Outputs `features.json` and `vegetation.bin` in the pack and rewrites `environment.json` as v3 with
their sizes, SHA-256 and provenance. Raw downloads go to <pack>/../../.geo-raw/<id>/features.
"""

import argparse
import concurrent.futures as cf
import datetime
import hashlib
import json
import math
import os
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pyproj
import rasterio
import rasterio.features
from PIL import Image
from rasterio.env import Env
from shapely import contains_xy
from shapely.geometry import Polygon, shape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_environment import Frame  # noqa: E402

UA = {"User-Agent": "vv-lab-geo-build/1.0 (environment pack builder)"}
OVERPASS = "https://overpass-api.de/api/interpreter"
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"

FEATURES_FILE = "features.json"
VEGETATION_FILE = "vegetation.bin"
VEG_RECORD = struct.Struct("<hhHBBBBBB")  # x dm, y dm, h cm, crown radius dm, kind, r, g, b, pad
LEVEL_M = 3.2
DEFAULT_HEIGHT_M = {"house": 6.0, "residential": 6.0, "detached": 6.0, "garage": 3.0, "shed": 3.0, "roof": 4.0,
                    "hangar": 14.0, "warehouse": 9.0, "industrial": 9.0, "commercial": 8.0, "storage_tank": 10.0}
STRUCTURE_KINDS = {"tower", "mast", "lighthouse", "water_tower", "chimney", "silo", "communications_tower"}
STRUCTURE_DEFAULT = {"tower": (20.0, 1.5), "mast": (30.0, 0.6), "lighthouse": (30.0, 3.5), "water_tower": (35.0, 7.0),
                     "chimney": (25.0, 1.5), "silo": (15.0, 4.0), "communications_tower": (40.0, 1.0)}

LICENCES = {
    "osm": {
        "provider": "OpenStreetMap contributors, through the Overpass API",
        "product": "Building footprints and tall structures (OpenStreetMap data as of the recorded timestamp)",
        "licence": "Open Data Commons Open Database License (ODbL) 1.0. features.json is a derived database of OpenStreetMap data and is made available under the ODbL. https://www.openstreetmap.org/copyright",
        "attribution": "Buildings and structures: © OpenStreetMap contributors, ODbL 1.0",
        "credit": "© OpenStreetMap contributors",
        "access": "Overpass API https://overpass-api.de/api/interpreter (no account)",
    },
    "3dep-lpc": {
        "provider": "U.S. Geological Survey, 3D Elevation Program, lidar point cloud; Entwine Point Tile copy on AWS Open Data",
        "product": "Lidar point cloud {project} (heights above the lidar ground, 1 m cells)",
        "licence": "U.S. Public Domain: \"USGS-authored or produced data and information are considered to be in the U.S. Public Domain.\" https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
        "attribution": "Lidar: U.S. Geological Survey, 3D Elevation Program",
        "credit": "USGS 3DEP lidar",
        "access": "s3://usgs-lidar-public (Entwine Point Tiles, no account)",
    },
    "naip-nir": {
        "provider": "USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP); Planetary Computer copy",
        "product": "NAIP {year} red and near-infrared bands (vegetation index only; not drawn)",
        "licence": "Public domain under the FSA web policy (see the detail image source).",
        "attribution": "Imagery: USDA FPAC Business Center, Geospatial Enterprise Operations, NAIP {year}",
        "credit": "USDA NAIP {year}",
        "access": "Planetary Computer STAC, collection naip (anonymous range requests)",
    },
}


def get(url, data=None, timeout=180, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            # Busy public servers answer 429, 502, 503 or 504: wait and ask again.
            if e.code not in (429, 502, 503, 504) or k == tries - 1:
                raise
            time.sleep(20 * (k + 1))


def sha256(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------------- pack terrain
class PackImage:
    """Colour of the pack's drawn ground at ENU points (detail image where it covers, else base)."""

    def __init__(self, pack, m):
        def img(meta, name):
            im = np.asarray(Image.open(os.path.join(pack, name)).convert("RGB"), dtype=np.float32)
            return {"a": im, "s": meta["spacing_m"], "x0": meta["first_texel_centre_m"][0], "y0": meta["first_texel_centre_m"][1]}
        self.base = img(m["image"], m["image"]["file"])
        d = next((l for l in m.get("layers", []) if l["role"] == "detail"), None)
        self.detail = img(d["image"], d["image"]["file"]) if d else None
        self.half = d["extent_m"] if d else 0.0

    @staticmethod
    def _at(g, e, n):
        c = np.clip(np.round((e - g["x0"]) / g["s"]).astype(int), 0, g["a"].shape[1] - 1)
        r = np.clip(np.round((g["y0"] - n) / g["s"]).astype(int), 0, g["a"].shape[0] - 1)
        return g["a"][r, c]

    def rgb(self, e, n):
        e = np.asarray(e, dtype=np.float64)
        n = np.asarray(n, dtype=np.float64)
        out = self._at(self.base, e, n)
        if self.detail is not None:
            ins = np.maximum(np.abs(e), np.abs(n)) < self.half - 1
            if ins.any():
                out[ins] = self._at(self.detail, e[ins], n[ins])
        return out


# ---------------------------------------------------------------------------------- OpenStreetMap
def overpass(lat, lon, radius, raw):
    # Raw caches are keyed by the origin too, so a moved origin never reuses another extent.
    path = os.path.join(raw, f"overpass-{lat:.6f}-{lon:.6f}-{radius:.0f}.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    q = f"""[out:json][timeout:120];
(
  way["building"](around:{radius:.0f},{lat},{lon});
  relation["building"]["type"="multipolygon"](around:{radius:.0f},{lat},{lon});
  way["man_made"~"^(storage_tank|silo|water_tower|lighthouse|tower|chimney)$"](around:{radius:.0f},{lat},{lon});
  node["man_made"~"^(tower|mast|lighthouse|water_tower|chimney|silo|communications_tower)$"](around:{radius:.0f},{lat},{lon});
);
out geom;"""
    d = json.loads(get(OVERPASS, urllib.parse.urlencode({"data": q}).encode()))
    json.dump(d, open(path, "w", encoding="utf-8"))
    return d


def parse_height(tags):
    v = tags.get("height") or tags.get("building:height")
    if v:
        try:
            s = v.strip().lower().replace(",", ".")
            if s.endswith("ft") or s.endswith("'"):
                return float(s.rstrip("ft' ").strip()) * 0.3048
            return float(s.split()[0].rstrip("m"))
        except ValueError:
            return None
    return None


def parse_levels(tags):
    v = tags.get("building:levels")
    if v:
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------------- lidar (EPT)
class EptRaster:
    """Rasterises an Entwine Point Tile point cloud onto 1 m ENU cells over [-half, half]^2."""

    def __init__(self, base, frame, undulation_m, half, cell, raw, max_depth):
        self.base, self.frame, self.half, self.cell = base.rstrip("/"), frame, half, cell
        self.n = int(round(2 * half / cell))
        self.dsm = np.full((self.n, self.n), -np.inf, dtype=np.float32)
        self.gsum = np.zeros((self.n, self.n), dtype=np.float64)
        self.gcnt = np.zeros((self.n, self.n), dtype=np.int32)
        self.cnt = np.zeros((self.n, self.n), dtype=np.int32)
        self.multi = np.zeros((self.n, self.n), dtype=np.int32)
        self.raw = os.path.join(raw, "ept")
        os.makedirs(self.raw, exist_ok=True)
        self.und = undulation_m
        self.ept = json.loads(get(self.base + "/ept.json"))
        if self.ept["srs"].get("horizontal") != "3857":
            raise SystemExit("only EPSG:3857 EPT sources are supported")
        self.to_geod = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        self.from_geod = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        self.max_depth = max_depth
        # ENU square -> geodetic corners -> 3857 bounding box (with a margin).
        es = np.array([-half, half, half, -half]) * 1.02
        ns = np.array([-half, -half, half, half]) * 1.02
        lat, lon, _ = frame.to_geod(es, ns, np.zeros(4))
        x, y = self.from_geod.transform(lon, lat)
        self.bx = (min(x), min(y), max(x), max(y))
        self.points = 0
        self.nodes = []

    def _nb(self, key):
        b = self.ept["bounds"]
        d, X, Y, _Z = map(int, key.split("-"))
        s = (b[3] - b[0]) / 2 ** d
        return (b[0] + X * s, b[1] + Y * s, b[0] + (X + 1) * s, b[1] + (Y + 1) * s)

    def _hit(self, key):
        q = self._nb(key)
        return q[0] < self.bx[2] and q[2] > self.bx[0] and q[1] < self.bx[3] and q[3] > self.bx[1]

    def keys(self):
        path = os.path.join(self.raw, f"hierarchy-{self.frame.lat:.6f}-{self.frame.lon:.6f}-{self.max_depth}.json")
        if os.path.exists(path):
            return json.load(open(path))
        allh = {}
        todo = ["0-0-0-0"]
        while todo:
            k = todo.pop()
            sub = json.loads(get(f"{self.base}/ept-hierarchy/{k}.json"))
            for k2, v in sub.items():
                if int(k2.split("-")[0]) > self.max_depth or not self._hit(k2):
                    continue
                if v == -1:
                    if k2 != k:
                        todo.append(k2)
                elif v > 0:
                    allh[k2] = v
        json.dump(allh, open(path, "w"))
        return allh

    def _fetch(self, key):
        path = os.path.join(self.raw, key + ".laz")
        if not os.path.exists(path):
            b = get(f"{self.base}/ept-data/{key}.laz")
            tmp = path + ".part"
            open(tmp, "wb").write(b)
            os.replace(tmp, path)
        return path

    def run(self):
        cache = os.path.join(self.raw, f"rasters-{self.frame.lat:.6f}-{self.frame.lon:.6f}-{self.max_depth}-{self.half:.0f}.npz")
        if os.path.exists(cache):
            z = np.load(cache)
            self.ground, self.chm, self.multi_frac, self.covered = z["ground"], z["chm"], z["multi_frac"], z["covered"]
            self.points, self.nodes = int(z["points"]), [str(k) for k in z["nodes"]]
            return self
        import laspy
        keys = sorted(self.keys(), key=lambda k: (int(k.split("-")[0]), k))
        print(f"lidar: {len(keys)} nodes to depth {self.max_depth}", flush=True)
        with cf.ThreadPoolExecutor(6) as ex:
            futs = {ex.submit(self._fetch, k): k for k in keys}
            for i, f in enumerate(cf.as_completed(futs)):
                k = futs[f]
                las = laspy.read(f.result())
                cls = np.asarray(las.classification)
                keep = (cls != 7) & (cls != 18)
                x = np.asarray(las.x)[keep]
                y = np.asarray(las.y)[keep]
                z = np.asarray(las.z)[keep]
                cls = cls[keep]
                nret = np.asarray(las.number_of_returns)[keep]
                lon, lat = self.to_geod.transform(x, y)
                enu = self.frame.to_enu(lat, lon, z + self.und)
                c = np.floor((enu[:, 0] + self.half) / self.cell).astype(np.int64)
                r = np.floor((self.half - enu[:, 1]) / self.cell).astype(np.int64)
                ok = (c >= 0) & (r >= 0) & (c < self.n) & (r < self.n)
                c, r, z, cls, nret = c[ok], r[ok], z[ok].astype(np.float32), cls[ok], nret[ok]
                np.maximum.at(self.dsm, (r, c), z)
                np.add.at(self.cnt, (r, c), 1)
                np.add.at(self.multi, (r, c), (nret > 1).astype(np.int32))
                g = cls == 2
                np.add.at(self.gsum, (r[g], c[g]), z[g])
                np.add.at(self.gcnt, (r[g], c[g]), 1)
                self.points += int(ok.sum())
                self.nodes.append(k)
                if i % 100 == 0:
                    print(f"  {i + 1}/{len(keys)} nodes, {self.points} points", flush=True)
        # Ground: mean of ground returns per cell; holes (under canopy, buildings) filled by
        # repeated 3x3 averaging from the known cells, which keep their values.
        filled = np.where(self.gcnt > 0, self.gsum / np.maximum(self.gcnt, 1), np.nan)
        median = np.nanmedian(filled)
        for _ in range(64):
            unknown = ~np.isfinite(filled)
            if not unknown.any():
                break
            gs = box3(np.where(unknown, 0.0, filled))
            ws = box3((~unknown).astype(np.float64))
            grow = unknown & (ws > 0)
            filled[grow] = gs[grow] / ws[grow]
        filled[~np.isfinite(filled)] = median
        self.ground = filled.astype(np.float32)
        dsm = np.where(np.isfinite(self.dsm), self.dsm, self.ground)
        self.chm = np.clip(dsm - self.ground, 0, 200).astype(np.float32)
        self.multi_frac = np.where(self.cnt > 0, self.multi / np.maximum(self.cnt, 1), 0).astype(np.float32)
        self.covered = self.cnt > 0
        np.savez_compressed(cache, ground=self.ground, chm=self.chm, multi_frac=self.multi_frac, covered=self.covered, points=self.points, nodes=np.array(self.nodes))
        return self


def box3(a):
    p = np.pad(a, 1, mode="edge")
    s = np.zeros_like(a, dtype=np.float64)
    for dr in (0, 1, 2):
        for dc in (0, 1, 2):
            s += p[dr:dr + a.shape[0], dc:dc + a.shape[1]]
    return s


def maxfilter(a, r):
    p = np.pad(a, r, mode="edge")
    out = np.full_like(a, -np.inf)
    for dr in range(2 * r + 1):
        for dc in range(2 * r + 1):
            out = np.maximum(out, p[dr:dr + a.shape[0], dc:dc + a.shape[1]])
    return out


def naip_ndvi(frame, half, cell, year, raw):
    """NDVI on the lidar cells from the NAIP red and near-infrared bands (nan where not covered)."""
    path = os.path.join(raw, f"ndvi-{frame.lat:.6f}-{frame.lon:.6f}-{year}-{half:.0f}.npy")
    meta = path + ".json"
    if os.path.exists(path) and os.path.exists(meta):
        return np.load(path), json.load(open(meta))
    n = int(round(2 * half / cell))
    cs = (np.arange(n) + 0.5) * cell - half
    E, N = np.meshgrid(cs, -cs)
    lat, lon, _ = frame.to_geod(E, N, np.zeros_like(E))
    lat0, lat1, lon0, lon1 = float(lat.min()), float(lat.max()), float(lon.min()), float(lon.max())
    body = json.dumps({"collections": ["naip"], "bbox": [lon0, lat0, lon1, lat1], "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z", "limit": 50}).encode()
    req = urllib.request.Request(PC_STAC, data=body, headers={**UA, "Content-Type": "application/json"})
    feats = sorted(json.loads(urllib.request.urlopen(req, timeout=120).read())["features"], key=lambda f: f["id"])
    ndvi = np.full(E.shape, np.nan, dtype=np.float32)
    items = []
    with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT=UA["User-Agent"]):
        for f in feats:
            href = f["assets"]["image"]["href"]
            with rasterio.open("/vsicurl/" + href) as src:
                if src.count < 4:
                    continue
                tr = pyproj.Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                x, y = tr.transform(lon, lat)
                inv = ~src.transform
                col, row = inv * (x, y)
                inside = (col >= 0) & (row >= 0) & (col < src.width) & (row < src.height) & np.isnan(ndvi)
                if not inside.any():
                    continue
                c0, c1 = int(col[inside].min()), int(col[inside].max()) + 1
                r0, r1 = int(row[inside].min()), int(row[inside].max()) + 1
                win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
                scale = abs(src.transform.a) / cell
                oh, ow = max(2, int(round(win.height * scale))), max(2, int(round(win.width * scale)))
                red, nir = src.read([1, 4], window=win, out_shape=(2, oh, ow), resampling=rasterio.enums.Resampling.average).astype(np.float32)
                cc = np.clip(((col - c0) * scale).astype(int), 0, ow - 1)
                rr = np.clip(((row - r0) * scale).astype(int), 0, oh - 1)
                rv, nv = red[rr, cc], nir[rr, cc]
                v = (nv - rv) / np.maximum(nv + rv, 1)
                valid = inside & ((nv + rv) > 0)
                ndvi[valid] = v[valid]
                items.append({"item": f["id"], "acquired": f["properties"].get("datetime")})
    np.save(path, ndvi)
    json.dump(items, open(meta, "w"))
    return ndvi, items


# ---------------------------------------------------------------------------------- assembly
def ring_dm(poly):
    xs, ys = poly.exterior.coords.xy
    pts = list(zip(xs, ys))[:-1]
    if not Polygon(pts).exterior.is_ccw:
        pts = pts[::-1]
    return [int(round(v * 10)) for p in pts for v in p]


def rasterize(polys, shape_, T):
    return rasterio.features.rasterize(((p, 1) for p in polys), out_shape=shape_, transform=T, fill=0, dtype="uint8").astype(bool)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=None, help="id in catalogue.json: reads its world block (lidar, NAIP year) and defaults --pack to desktop/environments/<id>")
    ap.add_argument("--pack", default=None)
    ap.add_argument("--radius", type=float, default=4500.0, help="OSM radius around the origin (m)")
    ap.add_argument("--ept", default=None, help="EPT root URL of a lidar point cloud covering the detail layer")
    ap.add_argument("--ept-project", default=None, help="name of the lidar project, for the manifest")
    ap.add_argument("--ept-depth", type=int, default=10)
    ap.add_argument("--lidar-half", type=float, default=None, help="half extent of the lidar layer (default: the detail layer's)")
    ap.add_argument("--naip-year", type=int, default=None)
    ap.add_argument("--raw", default=None)
    args = ap.parse_args()
    if args.env:
        from build_environment import ENVIRONMENTS
        if args.env not in ENVIRONMENTS:
            raise SystemExit(f"{args.env} is not in catalogue.json")
        wcfg = ENVIRONMENTS[args.env].get("world", {})
        args.ept = args.ept or wcfg.get("ept")
        args.ept_project = args.ept_project or wcfg.get("ept_project")
        args.naip_year = args.naip_year or wcfg.get("naip_year")
        args.radius = wcfg.get("osm_radius_m", args.radius)
        args.pack = args.pack or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "desktop", "environments", args.env)
    if not args.pack:
        raise SystemExit("give --env or --pack")

    pack = os.path.abspath(args.pack)
    mpath = os.path.join(pack, "environment.json")
    m = json.load(open(mpath, encoding="utf-8"))
    pid = m["id"]
    raw = args.raw or os.path.join(os.path.dirname(os.path.dirname(pack)), ".geo-raw", pid, "features")
    os.makedirs(raw, exist_ok=True)
    o = m["origin"]
    frame = Frame(o["lat_deg"], o["lon_deg"], o["h_ellipsoid_m"])
    und = o["geoid_undulation_m"]
    image = PackImage(pack, m)
    L = m["extent_m"]
    detail = next((l for l in m.get("layers", []) if l["role"] == "detail"), None)
    lidar_half = args.lidar_half or (detail["extent_m"] if detail else 1024.0)
    cell = 1.0

    lid = None
    ndvi = None
    ndvi_items = []
    if args.ept:
        lid = EptRaster(args.ept, frame, und, lidar_half, cell, raw, args.ept_depth).run()
        print(f"lidar: {lid.points} points in {len(lid.nodes)} nodes; covered {lid.covered.mean():.3f}", flush=True)
        if args.naip_year:
            ndvi, ndvi_items = naip_ndvi(frame, lidar_half, cell, args.naip_year, raw)
            print(f"ndvi: {np.isfinite(ndvi).mean():.3f} covered", flush=True)

    # ---- OSM
    osm = overpass(o["lat_deg"], o["lon_deg"], args.radius, raw)
    osm_base = osm.get("osm3s", {}).get("timestamp_osm_base")

    def to_enu(lat, lon):
        return frame.to_enu(np.asarray(lat), np.asarray(lon), np.full(len(lat), o["h_ellipsoid_m"]))[:, :2]

    structures, footprints = [], []
    skipped = 0
    for el in osm["elements"]:
        tags = el.get("tags", {})
        mm = tags.get("man_made")
        if el["type"] == "node":
            if mm not in STRUCTURE_KINDS:
                continue
            xy = to_enu([el["lat"]], [el["lon"]])[0]
            if max(abs(xy[0]), abs(xy[1])) > L - 50:
                continue
            structures.append({"id": f"n{el['id']}", "kind": mm, "xy": xy, "tags": tags})
            continue
        rings = []
        if el["type"] == "way":
            g = el.get("geometry") or []
            if len(g) >= 4 and g[0] == g[-1]:
                rings.append(g)
            else:
                skipped += 1
        else:
            for mem in el.get("members", []):
                g = mem.get("geometry") or []
                if mem.get("role") == "outer" and len(g) >= 4 and g[0] == g[-1]:
                    rings.append(g)
            if not rings:
                skipped += 1
        for g in rings:
            xy = to_enu([p["lat"] for p in g], [p["lon"] for p in g])
            if np.abs(xy).max() > L - 50:
                continue
            poly = Polygon(xy).buffer(0)
            if poly.is_empty or poly.area < 6:
                continue
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda q: q.area)
            kind = tags.get("building") if tags.get("building") else (mm or "yes")
            footprints.append({"id": f"{el['type'][0]}{el['id']}", "poly": poly, "tags": tags, "kind": kind})

    T = rasterio.Affine(cell, 0, -lidar_half, 0, -cell, lidar_half)
    if lid is not None:
        # Roughness of the canopy: standard deviation of the canopy height in 3 x 3 cells. Roofs
        # are smooth and give single returns; crowns are rough or give multiple returns.
        mean = box3(lid.chm) / 9
        rough = np.sqrt(np.maximum(box3(lid.chm.astype(np.float64) ** 2) / 9 - mean ** 2, 0))
        lidar_veg = (lid.multi_frac >= 0.3) | (rough >= 0.45)
        green = np.nan_to_num(ndvi, nan=-1) >= 0.18 if ndvi is not None else np.zeros(lid.chm.shape, bool)
        veg_cell = (lid.chm >= 0.6) & (green | lidar_veg)
        planar = (rough < 0.35) & (lid.multi_frac < 0.2) & ~green
        fp_mask = rasterize([f["poly"].buffer(1.5) for f in footprints], lid.chm.shape, T) if footprints else np.zeros(lid.chm.shape, bool)

    buildings = []
    hs_counts = {}
    for f in footprints:
        poly = f["poly"]
        h, hs = None, None
        if lid is not None and max(abs(v) for v in poly.bounds) < lidar_half - 2:
            inner = poly.buffer(-0.5)
            if not inner.is_empty and inner.area >= 4:
                msk = rasterize([inner], lid.chm.shape, T) & lid.covered
                if msk.sum() >= 4:
                    h, hs = float(np.percentile(lid.chm[msk], 90)), "lidar"
                    if h < 1.5:
                        h, hs = None, None  # not standing at the lidar date: fall back to the tags
        if h is None:
            th = parse_height(f["tags"])
            lv = parse_levels(f["tags"])
            if th:
                h, hs = th, "osm-height"
            elif lv:
                h, hs = lv * LEVEL_M + 1.0, "osm-levels"
            else:
                h, hs = DEFAULT_HEIGHT_M.get(f["kind"], 5.0), "default"
        h = float(min(max(h, 2.0), 160.0))
        inner = poly.buffer(-1.0) if poly.area > 30 else poly
        if inner.is_empty:
            inner = poly
        sx, sy = np.meshgrid(np.linspace(poly.bounds[0], poly.bounds[2], 7), np.linspace(poly.bounds[1], poly.bounds[3], 7))
        sel = contains_xy(inner, sx.ravel(), sy.ravel())
        if sel.any():
            px, py = sx.ravel()[sel], sy.ravel()[sel]
        else:
            cx, cy = poly.representative_point().coords[0]
            px, py = np.array([cx]), np.array([cy])
        rgb = np.median(image.rgb(px, py), axis=0)
        simp = poly.simplify(0.3, preserve_topology=True)
        if simp.is_empty or simp.geom_type != "Polygon":
            simp = poly
        buildings.append({"id": f["id"], "kind": f["kind"], "h_dm": int(round(h * 10)), "hs": hs, "roof": [int(v) for v in rgb], "ring_dm": ring_dm(simp)})
        hs_counts[hs] = hs_counts.get(hs, 0) + 1

    lidar_structs = []
    if lid is not None:
        raised = (lid.chm >= 2.5) & ~fp_mask & lid.covered & (planar | ~veg_cell)
        # Drop isolated cells (noise, wires, vehicles): keep cells with at least 4 raised neighbours.
        raised &= box3(raised.astype(np.float64)) >= 5
        k = 0
        for geom, _v in rasterio.features.shapes(raised.astype(np.int32), mask=raised, transform=T, connectivity=4):
            poly = shape(geom)
            if poly.area < 16:
                continue
            k += 1
            msk = rasterize([poly], lid.chm.shape, T)
            # A structure is mostly smooth single-return surface; a rough patch is vegetation.
            if planar[msk].mean() < 0.6:
                continue
            h = float(np.percentile(lid.chm[msk], 90))
            simp = Polygon(poly.exterior).simplify(0.7, preserve_topology=True)
            if simp.is_empty or simp.geom_type != "Polygon":
                continue
            cx, cy = simp.representative_point().coords[0]
            rgb = image.rgb(np.array([cx]), np.array([cy]))[0]
            lidar_structs.append({"id": f"lidar-{k}", "kind": "lidar-structure", "h_dm": int(round(min(h, 160) * 10)), "hs": "lidar", "roof": [int(v) for v in rgb], "ring_dm": ring_dm(simp)})
        print(f"lidar structures: {len(lidar_structs)}", flush=True)

    out_structs = []
    for s in structures:
        th = parse_height(s["tags"])
        dh, rad = STRUCTURE_DEFAULT.get(s["kind"], (20.0, 1.5))
        h, hs = (th, "osm-height") if th else (dh, "default")
        x, y = s["xy"]
        if lid is not None and abs(x) < lidar_half - 6 and abs(y) < lidar_half - 6:
            c = int((x + lidar_half) / cell)
            r = int((lidar_half - y) / cell)
            win = lid.chm[max(0, r - 3):r + 4, max(0, c - 3):c + 4]
            if win.size and win.max() >= 3:
                h, hs = float(win.max()), "lidar"
        out_structs.append({"id": s["id"], "kind": s["kind"], "x_dm": int(round(x * 10)), "y_dm": int(round(y * 10)), "h_dm": int(round(min(h, 300) * 10)), "r_dm": int(round(rad * 10)), "hs": hs, "name": s["tags"].get("name")})

    # ---- vegetation
    veg = bytearray()
    veg_n = {"tree": 0, "shrub": 0}
    if lid is not None:
        chm = np.where(veg_cell & ~fp_mask, lid.chm, 0).astype(np.float32)
        sm = (box3(chm) / 9).astype(np.float32)
        # Trees (>= 4 m): local maxima of the smoothed canopy in a 7 m window.
        peak = (sm >= 4.0) & (sm >= maxfilter(sm, 3)) & veg_cell
        rejected_thin = 0
        for r, c in zip(*np.nonzero(peak)):
            h = float(chm[max(0, r - 1):r + 2, max(0, c - 1):c + 2].max())
            win = chm[max(0, r - 6):r + 7, max(0, c - 6):c + 7] >= 0.5 * h
            # A crown fills the cells around its top; a wire or a pole does not.
            core = chm[max(0, r - 2):r + 3, max(0, c - 2):c + 3] >= 0.5 * h
            # With a near-infrared band, a crown must also be green (a lattice pylon is not).
            green_top = ndvi is None or np.nanmean(ndvi[max(0, r - 2):r + 3, max(0, c - 2):c + 3]) >= 0.12
            if core.mean() < 0.5 or win.sum() < 6 or not green_top:
                rejected_thin += 1
                continue
            crown = min(8.0, max(1.5, math.sqrt(win.sum() / math.pi) * cell))
            x = -lidar_half + (c + 0.5) * cell
            y = lidar_half - (r + 0.5) * cell
            rgb = image.rgb(np.array([x]), np.array([y]))[0]
            veg += VEG_RECORD.pack(int(round(x * 10)), int(round(y * 10)), int(round(min(h, 60) * 100)), int(round(crown * 10)), 1, int(rgb[0]), int(rgb[1]), int(rgb[2]), 0)
            veg_n["tree"] += 1
        # Shrubs (0.6 to 4 m): one clump per 3 m block with at least 4 vegetated cells, at the
        # block's highest cell, with the block's 90th-percentile height.
        B = 3
        nb = chm.shape[0] // B
        blk = chm[:nb * B, :nb * B].reshape(nb, B, nb, B).transpose(0, 2, 1, 3).reshape(nb, nb, B * B)
        vc = (blk >= 0.6).sum(axis=2)
        # Sparse desert shrubs are a few cells each: a clump needs 3 vegetated cells of 9.
        tallblk = sm[:nb * B, :nb * B].reshape(nb, B, nb, B).max(axis=(1, 3)) >= 4.0
        for bi, bj in zip(*np.nonzero((vc >= 3) & ~tallblk)):
            vals = blk[bi, bj]
            h = float(np.percentile(vals[vals >= 0.6], 90))
            a = int(np.argmax(vals))
            r, c = bi * B + a // B, bj * B + a % B
            x = -lidar_half + (c + 0.5) * cell
            y = lidar_half - (r + 0.5) * cell
            crown = min(2.6, 0.9 + 0.25 * vc[bi, bj])
            rgb = image.rgb(np.array([x]), np.array([y]))[0]
            veg += VEG_RECORD.pack(int(round(x * 10)), int(round(y * 10)), int(round(min(h, 4.0) * 100)), int(round(crown * 10)), 0, int(rgb[0]), int(rgb[1]), int(rgb[2]), 0)
            veg_n["shrub"] += 1
        print(f"vegetation: {veg_n}; thin tall objects rejected: {rejected_thin}", flush=True)
        np.save(os.path.join(raw, "chm.npy"), lid.chm)

    features = {
        "schema": "vv-geo-features.v1",
        "units": "decimetres on the pack's ENU plane; heights above the drawn terrain",
        "osm_timestamp": osm_base,
        "buildings": buildings,
        "lidar_structures": lidar_structs,
        "structures": out_structs,
    }
    fb = json.dumps(features, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    open(os.path.join(pack, FEATURES_FILE), "wb").write(fb)
    vpath = os.path.join(pack, VEGETATION_FILE)
    if veg:
        open(vpath, "wb").write(bytes(veg))
    elif os.path.exists(vpath):
        os.remove(vpath)

    # ---- manifest v3
    def add_source(sid, lic, **fmt):
        m["sources"] = [s for s in m["sources"] if s.get("layer") != f"world:{sid}"]
        m["sources"].append({**{k: v.format(**fmt) for k, v in lic.items()}, "layer": f"world:{sid}"})
    add_source("osm", LICENCES["osm"])
    if lid is not None:
        add_source("3dep-lpc", LICENCES["3dep-lpc"], project=args.ept_project or args.ept.rstrip("/").rsplit("/", 1)[-1])
    if ndvi_items:
        add_source("naip-nir", LICENCES["naip-nir"], year=args.naip_year)
    world = {
        "features": {
            "file": FEATURES_FILE, "bytes": len(fb), "sha256": sha256(fb),
            "buildings": len(buildings), "lidar_structures": len(lidar_structs), "structures": len(out_structs),
            "height_sources": hs_counts, "osm_radius_m": args.radius, "osm_timestamp": osm_base, "osm_skipped": skipped,
            "licence": "ODbL 1.0 (derived database of OpenStreetMap data)",
            "accuracy": "OSM footprints as mapped by contributors (typically 1 to 3 m). Lidar heights are the 90th percentile of first-surface heights above the lidar ground inside the footprint, from 1 m cells; the lidar date may differ from the image and OSM dates. Walls, roof shapes and materials are illustrative; roof colours are sampled from the pack image.",
        },
    }
    if lid is not None:
        world["lidar"] = {
            "source": "3dep-lpc", "project": args.ept_project, "ept": args.ept, "max_depth": args.ept_depth,
            "half_extent_m": lidar_half, "cell_m": cell, "points": lid.points, "nodes": len(lid.nodes),
            "covered_fraction": round(float(lid.covered.mean()), 4),
            "vegetation_rule": "canopy height >= 0.6 m and (NAIP NDVI >= 0.18, or >= 30 % multiple returns, or a canopy roughness >= 0.45 m in 3 x 3 cells); a lidar structure is a raised region (>= 2.5 m, >= 16 m2) outside OSM footprints whose cells are at least 60 % smooth (roughness < 0.35 m), single-return (< 20 % multiple returns) and not green",
            "horizontal_note": "The point cloud is used in EPSG:3857 as published; heights above ground are differences within the point cloud, so its vertical datum cancels.",
        }
    if veg:
        world["vegetation"] = {
            "file": VEGETATION_FILE, "bytes": len(veg), "sha256": sha256(bytes(veg)),
            "record": "12 bytes, little-endian: int16 x dm, int16 y dm, uint16 height cm, uint8 crown radius dm, uint8 kind (0 shrub clump, 1 tree), uint8 r, g, b (image colour at the point), uint8 0",
            "count": veg_n["tree"] + veg_n["shrub"], "trees": veg_n["tree"], "shrubs": veg_n["shrub"],
            "accuracy": "Positions and heights from the lidar canopy height model (1 m cells); trees are local maxima in a 7 m window, shrubs one clump per 3 m block with at least 3 vegetated cells; a tall top whose 5 x 5 cells are less than half filled, or with fewer than 6 cells above half its height (a wire or a pole), or, with NAIP near-infrared, a top whose 5 x 5 cells have a mean NDVI below 0.12 (a lattice pylon), is not a tree. Species, crown shape and colour detail are illustrative.",
        }
    m["schema"] = "vv-geo-environment.v3"
    m["world"] = world
    m["built"]["features_by"] = "scripts/geo/build_features.py"
    m["built"]["features_date"] = datetime.date.today().isoformat()
    open(mpath, "w", encoding="utf-8", newline="\n").write(json.dumps(m, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(world, indent=1)[:3000])


if __name__ == "__main__":
    main()
