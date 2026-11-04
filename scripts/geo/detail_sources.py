"""High-resolution sources for the detail layer of an environment pack (schema v2).

Each source is read once over HTTPS without an account and then sampled at geodetic latitude and
longitude arrays (degrees, WGS84).

    - NaipImagery: USDA NAIP orthoimagery from the Microsoft Planetary Computer STAC (collection
      `naip`); the blobs answer anonymous range requests.
    - TnmLidarDem: USGS 3DEP 1 m lidar DEM tiles found with The National Map API (heights NAVD88),
      returned as ellipsoidal heights with the NOAA GEOID18 model through PROJ.
    - WmsImagery: an orthoimage rendered by a WMS 1.3.0 GetMap in EPSG:4326, in tiles.

Horizontal datums: NAIP and 3DEP are on NAD83(2011); they are read here as if they were WGS84,
which displaces them by about 1 to 2 m on the ground. The manifest states it.
"""

import io
import json
import math
import os
import urllib.parse
import urllib.request

import numpy as np
import pyproj
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.env import Env
from rasterio.windows import from_bounds

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
UA = {"User-Agent": "vv-lab-environment-builder"}


def _get_json(url, data=None):
    headers = dict(UA)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def bilinear(arr, x, y):
    """Samples arr[bands, row, col] at fractional pixel-centre coordinates (x = col, y = row).
    Returns the values and a mask of the points inside the array. NaN stays NaN."""
    h, w = arr.shape[-2:]
    x0 = np.clip(np.floor(x).astype(int), 0, w - 2)
    y0 = np.clip(np.floor(y).astype(int), 0, h - 2)
    fx = np.clip(x - x0, 0, 1)
    fy = np.clip(y - y0, 0, 1)
    v = (arr[:, y0, x0] * (1 - fx) * (1 - fy) + arr[:, y0, x0 + 1] * fx * (1 - fy)
         + arr[:, y0 + 1, x0] * (1 - fx) * fy + arr[:, y0 + 1, x0 + 1] * fx * fy)
    inside = (x >= 0) & (y >= 0) & (x <= w - 1) & (y <= h - 1)
    return v, inside


class _Windows:
    """Raster windows in their own CRS, read once, sampled at geodetic points (first window wins)."""

    def __init__(self):
        self.parts = []

    def add(self, arr, transform, crs, valid):
        self.parts.append((arr.astype(np.float32), ~transform, pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True), valid))

    def sample(self, lat, lon):
        out = np.full((self.parts[0][0].shape[0],) + np.shape(lat), np.nan, dtype=np.float64)
        have = np.zeros(np.shape(lat), dtype=bool)
        for arr, inv, tr, valid in self.parts:
            X, Y = tr.transform(lon, lat)
            col, row = inv * (X, Y)
            v, ok = bilinear(arr, col - 0.5, row - 0.5)
            take = ok & valid(v) & ~have
            out[:, take] = v[:, take]
            have |= take
        return out, have


def _window(src, lat0, lat1, lon0, lon1, margin):
    tr = pyproj.Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
    b = src.bounds
    left, right = max(min(xs) - margin, b.left), min(max(xs) + margin, b.right)
    bottom, top = max(min(ys) - margin, b.bottom), min(max(ys) + margin, b.top)
    if left >= right or bottom >= top:
        return None
    return from_bounds(left, bottom, right, top, src.transform).round_offsets().round_lengths()


class NaipImagery:
    def __init__(self, lat0, lat1, lon0, lon1, year, gsd_m, raw):
        d = _get_json(PC_STAC, {"collections": ["naip"], "bbox": [lon0, lat0, lon1, lat1], "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z", "limit": 50})
        feats = sorted(d["features"], key=lambda f: f["id"])
        if not feats:
            raise SystemExit(f"no NAIP {year} item covers the detail extent")
        self.items = []
        self.win = _Windows()
        with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT=UA["User-Agent"]):
            for f in feats:
                href = f["assets"]["image"]["href"]
                with rasterio.open("/vsicurl/" + href) as src:
                    w = _window(src, lat0, lat1, lon0, lon1, 20)
                    if w is None:
                        continue
                    # Read at the target texel size (area average), not at the native 0.3 to 0.6 m.
                    scale = abs(src.transform.a) / gsd_m
                    shape = (3, max(2, int(round(w.height * scale))), max(2, int(round(w.width * scale))))
                    rgb = src.read([1, 2, 3], window=w, out_shape=shape, resampling=Resampling.average)
                    T = src.window_transform(w) * rasterio.Affine.scale(w.width / shape[2], w.height / shape[1])
                    self.win.add(rgb, T, src.crs, lambda v: np.nan_to_num(v).sum(axis=0) > 0)
                    self.items.append({"item": f["id"], "url": href, "acquired": f["properties"].get("datetime"), "gsd_m": f["properties"].get("gsd"), "crs": str(src.crs)})
                    np.save(os.path.join(raw, f"{f['id']}-window.npy"), rgb)
        self.year = year

    def sample(self, lat, lon):
        v, have = self.win.sample(lat, lon)
        return np.nan_to_num(v), have


class TnmLidarDem:
    def __init__(self, lat0, lat1, lon0, lon1, raw):
        q = urllib.parse.urlencode({"datasets": "Digital Elevation Model (DEM) 1 meter", "bbox": f"{lon0},{lat0},{lon1},{lat1}", "max": 50})
        d = _get_json(f"{TNM_API}?{q}")
        items = sorted(d["items"], key=lambda i: i["downloadURL"])
        if not items:
            raise SystemExit("no USGS 1 m DEM tile covers the detail extent")
        self.tiles = []
        self.win = _Windows()
        with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT=UA["User-Agent"]):
            for it in items:
                url = it["downloadURL"]
                with rasterio.open("/vsicurl/" + url) as src:
                    w = _window(src, lat0, lat1, lon0, lon1, 10)
                    if w is None:
                        continue
                    nd = src.nodata if src.nodata is not None else -999999.0
                    z = src.read(1, window=w, boundless=True, fill_value=nd).astype(np.float32)
                    z[z == nd] = np.nan
                    self.win.add(z[None], src.window_transform(w), src.crs, lambda v: np.isfinite(v[0]))
                    self.tiles.append({"item": it["title"], "url": url, "published": it.get("publicationDate"), "crs": str(src.crs)})
                    np.save(os.path.join(raw, os.path.basename(url) + "-window.npy"), z)
        # NAVD88 heights to NAD83(2011) ellipsoidal heights with GEOID18 (PROJ grid us_noaa_g2018u0).
        self.geoid = pyproj.Transformer.from_crs("EPSG:6318+5703", "EPSG:6319", always_xy=True, only_best=True)

    def h_ellipsoid(self, lat, lon, fallback):
        """Ellipsoidal heights; where the lidar has no value (open water) `fallback(lat, lon)` is used
        and counted in `self.filled` (points) out of `self.asked`."""
        v, have = self.win.sample(lat, lon)
        H = np.where(have, v[0], 0.0)
        _x, _y, h = self.geoid.transform(lon, lat, H)
        h = np.asarray(h, dtype=np.float64)
        if not np.isfinite(h[have]).all():
            raise SystemExit("the GEOID18 conversion failed (is the PROJ network enabled?)")
        if not have.all():
            h = np.where(have, h, fallback(lat, lon))
        self.filled = int((~have).sum())
        self.asked = int(have.size)
        return h


class WmsImagery:
    """GetMap tiles of a WMS 1.3.0 layer in EPSG:4326 (axis order latitude, longitude)."""

    def __init__(self, url, layer, lat0, lat1, lon0, lon1, gsd_m, raw, tile_px=2048, fmt="image/jpeg"):
        lat_c = math.radians((lat0 + lat1) / 2)
        dlat = gsd_m / 111320.0
        dlon = gsd_m / (111320.0 * math.cos(lat_c))
        ny = int(math.ceil((lat1 - lat0) / dlat))
        nx = int(math.ceil((lon1 - lon0) / dlon))
        img = np.zeros((3, ny, nx), dtype=np.uint8)
        self.requests = []
        for ty in range(0, ny, tile_px):
            for tx in range(0, nx, tile_px):
                h = min(tile_px, ny - ty)
                w = min(tile_px, nx - tx)
                top = lat1 - ty * dlat
                bottom = top - h * dlat
                left = lon0 + tx * dlon
                right = left + w * dlon
                q = urllib.parse.urlencode({"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": layer, "STYLES": "", "CRS": "EPSG:4326",
                                            "BBOX": f"{bottom},{left},{top},{right}", "WIDTH": w, "HEIGHT": h, "FORMAT": fmt})
                full = f"{url}{'&' if '?' in url else '?'}{q}"
                with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=180) as r:
                    data = r.read()
                    ctype = r.headers.get("Content-Type", "")
                if not ctype.startswith("image/"):
                    raise SystemExit(f"WMS answered {ctype}: {data[:200]!r}")
                a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).transpose(2, 0, 1)
                img[:, ty:ty + h, tx:tx + w] = a[:, :h, :w]
                self.requests.append(full)
        np.save(os.path.join(raw, f"wms-{layer}-window.npy"), img)
        self.img = img.astype(np.float32)
        self.lat1, self.lon0, self.dlat, self.dlon = lat1, lon0, dlat, dlon

    def sample(self, lat, lon):
        col = (lon - self.lon0) / self.dlon
        row = (self.lat1 - lat) / self.dlat
        v, have = bilinear(self.img, col - 0.5, row - 0.5)
        return v, have & (v.sum(axis=0) > 0)
