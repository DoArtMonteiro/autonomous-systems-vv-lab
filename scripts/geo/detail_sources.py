"""High-resolution sources for the detail layer of an environment pack (schema v2).

Each source is read once over HTTPS without an account and then sampled at geodetic latitude and
longitude arrays (degrees, WGS84).

    - NaipImagery: USDA NAIP orthoimagery from the Microsoft Planetary Computer STAC (collection
      `naip`); the blobs answer anonymous range requests.
    - TnmLidarDem: USGS 3DEP 1 m lidar DEM tiles found with The National Map API (heights NAVD88),
      returned as ellipsoidal heights with the NOAA GEOID18 model through PROJ.
    - WmsImagery: an orthoimage rendered by a WMS 1.3.0 GetMap in EPSG:4326, in tiles.
    - CogImagery: orthoimage GeoTIFF tiles at listed URLs (LINZ, swisstopo).
    - CogDem: bare-earth DEM GeoTIFF tiles at listed URLs, heights in a national vertical datum
      converted to ellipsoidal heights through PROJ (geoid grid required).
    - WcsDem: a DEM fetched with one WCS 2.0.1 GetCoverage (IGN Spain), then read as CogDem.
    - ArcgisExportImagery: an orthoimage rendered by an ArcGIS MapServer export (Norwegian Polar
      Institute), in tiles.

Horizontal datums: NAIP and 3DEP are on NAD83(2011); they are read here as if they were WGS84,
which displaces them by about 1 to 2 m on the ground. The national frames of the other sources
(NZGD2000, ETRS89, CH1903+) are likewise read as WGS84; each catalogue licence entry states the
resulting offset in its `accuracy` text, which goes into the manifest.
"""

import hashlib
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
from rasterio.merge import merge
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


def _mosaic(paths, lat0, lat1, lon0, lon1, margin, res, bands, resampling, nodata):
    """Abutting tiles of one CRS merged into a single array over the extent (plus `margin` in the
    tiles' units), at `res` (None: the tiles' own). Sampling one mosaic, rather than each tile in
    turn, leaves no gap along the tile edges, where bilinear sampling of a single tile stops half a
    pixel short. Returns the array, its transform and CRS, and the tiles used with their pixel size."""
    srcs, used = [], []
    try:
        for p in paths:
            s = rasterio.open(p)
            if _window(s, lat0, lat1, lon0, lon1, margin) is None:
                s.close()
                continue
            if srcs and s.crs != srcs[0].crs:
                raise SystemExit("tiles in different CRSs")
            srcs.append(s)
            used.append((p, abs(s.transform.a)))
        if not srcs:
            return None
        crs = srcs[0].crs
        tr = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
        r = res or abs(srcs[0].transform.a)
        x0, y1 = math.floor((min(xs) - margin) / r) * r, math.ceil((max(ys) + margin) / r) * r
        x1, y0 = math.ceil((max(xs) + margin) / r) * r, math.floor((min(ys) - margin) / r) * r
        arr, T = merge(srcs, bounds=(x0, y0, x1, y1), res=r, nodata=nodata, indexes=list(bands), resampling=resampling)
        return arr, T, crs, used
    finally:
        for s in srcs:
            s.close()


class CogImagery:
    """Orthoimage tiles published as cloud-optimised GeoTIFFs at known URLs (for example the LINZ
    `nz-imagery` bucket or the swisstopo SWISSIMAGE tiles), mosaicked over the detail extent at the
    texel size (area average, from the files' overviews where they have them)."""

    def __init__(self, urls, lat0, lat1, lon0, lon1, gsd_m, raw, bands=(1, 2, 3)):
        with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT=UA["User-Agent"], AWS_NO_SIGN_REQUEST="YES"):
            got = _mosaic(["/vsicurl/" + u for u in urls], lat0, lat1, lon0, lon1, 20, gsd_m, bands, Resampling.average, 0)
        if got is None:
            raise SystemExit("no imagery tile covers the detail extent")
        rgb, T, crs, used = got
        self.win = _Windows()
        self.win.add(rgb, T, crs, lambda v: np.nan_to_num(v).sum(axis=0) > 0)
        self.items = [{"url": p[len("/vsicurl/"):], "gsd_m": round(g, 4), "crs": str(crs)} for p, g in used]
        np.save(os.path.join(raw, "cog-mosaic.npy"), rgb)

    def sample(self, lat, lon):
        v, have = self.win.sample(lat, lon)
        return np.nan_to_num(v), have


class CogDem:
    """Terrain tiles (bare-earth DEM) published as GeoTIFFs at known URLs or local paths, with heights
    in a national vertical datum. `vertical_crs` is the compound CRS of the tiles (their projected CRS
    plus the vertical datum, for example EPSG:2193+7839) and `ellipsoidal_crs` the 3D geographic CRS
    its heights are converted to (for example EPSG:4959); PROJ finds the geoid grid, and the
    conversion fails rather than fall back to a transformation without it."""

    def __init__(self, urls, vertical_crs, ellipsoidal_crs, lat0, lat1, lon0, lon1, raw):
        paths = []
        with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT=UA["User-Agent"], AWS_NO_SIGN_REQUEST="YES"):
            for url in urls:
                if "!/" in url:
                    # A GeoTIFF inside a zip archive (NPI publishes its models so): the archive is
                    # downloaded once into the raw folder and read from there.
                    zurl, inner = url.split("!/", 1)
                    local = os.path.join(raw, os.path.basename(zurl))
                    if not os.path.exists(local):
                        with urllib.request.urlopen(urllib.request.Request(zurl, headers=UA), timeout=600) as r, open(local + ".part", "wb") as f:
                            while True:
                                b = r.read(1 << 20)
                                if not b:
                                    break
                                f.write(b)
                        os.replace(local + ".part", local)
                    path = "/vsizip/" + local.replace("\\", "/") + "/" + inner
                else:
                    path = url if os.path.exists(url) else "/vsicurl/" + url
                paths.append((path, url))
            got = _mosaic([p for p, _u in paths], lat0, lat1, lon0, lon1, 10, None, (1,), Resampling.nearest, -32767.0)
        if got is None:
            raise SystemExit("no DEM tile covers the detail extent")
        zz, T, crs, used = got
        z = zz[0].astype(np.float32)
        # Each source's own no-data value is replaced by the mosaic's (-32767); heights below -1000 m are none.
        z[z < -1000] = np.nan
        self.win = _Windows()
        self.win.add(z[None], T, crs, lambda v: np.isfinite(v[0]))
        url_of = dict(paths)
        self.tiles = [{"item": os.path.basename(url_of[p]), "url": url_of[p] if not os.path.exists(url_of[p]) else None,
                       "res_m": round(g, 4), "crs": str(crs)} for p, g in used]
        np.save(os.path.join(raw, "dem-mosaic.npy"), z)
        self.to_xy = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self.vert = pyproj.Transformer.from_crs(vertical_crs, ellipsoidal_crs, always_xy=True, only_best=True)
        self.vertical_crs, self.ellipsoidal_crs = vertical_crs, ellipsoidal_crs
        self.description = None

    def h_ellipsoid(self, lat, lon, fallback):
        """Ellipsoidal heights; where the DEM has no value `fallback(lat, lon)` is used."""
        v, have = self.win.sample(lat, lon)
        H = np.where(have, v[0], 0.0)
        X, Y = self.to_xy.transform(lon, lat)
        _x, _y, h = self.vert.transform(X, Y, H)
        h = np.asarray(h, dtype=np.float64)
        if not np.isfinite(h[have]).all():
            raise SystemExit(f"the {self.vertical_crs} to {self.ellipsoidal_crs} conversion failed (is the PROJ network enabled?)")
        if have.any() and np.allclose(h[have], H[have], atol=1e-6):
            raise SystemExit(f"the {self.vertical_crs} to {self.ellipsoidal_crs} conversion applied no geoid")
        # The operation PROJ actually used (with its geoid grid), known only after a transform.
        self.description = self.vert.get_last_used_operation().description
        if not have.all():
            h = np.where(have, h, fallback(lat, lon))
        return h


class WcsDem(CogDem):
    """A DEM served by an OGC WCS 2.0.1 GetCoverage in a projected CRS (GeoTIFF), fetched once for the
    detail extent and then read as a local tile."""

    def __init__(self, url, coverage, vertical_crs, ellipsoidal_crs, lat0, lat1, lon0, lon1, raw, margin_m=50.0):
        crs = pyproj.CRS(vertical_crs).sub_crs_list[0]
        tr = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
        x0, x1 = math.floor((min(xs) - margin_m) / 100) * 100, math.ceil((max(xs) + margin_m) / 100) * 100
        y0, y1 = math.floor((min(ys) - margin_m) / 100) * 100, math.ceil((max(ys) + margin_m) / 100) * 100
        q = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"), ("COVERAGEID", coverage),
             ("SUBSET", f"x({x0},{x1})"), ("SUBSET", f"y({y0},{y1})"), ("FORMAT", "image/tiff")]
        full = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(q)}"
        path = os.path.join(raw, f"wcs-{coverage}-{x0}-{y0}-{x1}-{y1}.tif")
        if not os.path.exists(path):
            with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=300) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
            if not ctype.startswith("image/tiff"):
                raise SystemExit(f"WCS answered {ctype}: {data[:200]!r}")
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
        super().__init__([path], vertical_crs, ellipsoidal_crs, lat0, lat1, lon0, lon1, raw)
        self.tiles[0]["url"] = full
        self.tiles[0]["item"] = coverage
        self.requests = [full]


class ArcgisExportImagery:
    """An orthoimage rendered by an ArcGIS MapServer `export` request in a projected CRS, in tiles
    of at most `tile_px` pixels (the server's maximum image size)."""

    def __init__(self, url, crs, lat0, lat1, lon0, lon1, gsd_m, raw, tile_px=4096):
        tr = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
        x0, y1 = min(xs) - 20, max(ys) + 20
        nx = int(math.ceil((max(xs) + 20 - x0) / gsd_m))
        ny = int(math.ceil((y1 - (min(ys) - 20)) / gsd_m))
        img = np.zeros((3, ny, nx), dtype=np.uint8)
        epsg = pyproj.CRS(crs).to_epsg()
        self.requests = []
        for ty in range(0, ny, tile_px):
            for tx in range(0, nx, tile_px):
                h = min(tile_px, ny - ty)
                w = min(tile_px, nx - tx)
                left, top = x0 + tx * gsd_m, y1 - ty * gsd_m
                q = urllib.parse.urlencode({"bbox": f"{left},{top - h * gsd_m},{left + w * gsd_m},{top}", "bboxSR": epsg, "imageSR": epsg,
                                            "size": f"{w},{h}", "format": "jpg", "f": "image"})
                full = f"{url.rstrip('/')}/export?{q}"
                # The cache key is the request itself, so a moved origin never reuses old tiles.
                path = os.path.join(raw, f"arcgis-{hashlib.sha256(full.encode()).hexdigest()[:16]}.jpg")
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        data = f.read()
                else:
                    with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=300) as r:
                        data = r.read()
                        ctype = r.headers.get("Content-Type", "")
                    if not ctype.startswith("image/"):
                        raise SystemExit(f"ArcGIS export answered {ctype}: {data[:200]!r}")
                    with open(path, "wb") as f:
                        f.write(data)
                a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).transpose(2, 0, 1)
                # The server may return a pixel more or less than asked for the same bounding box;
                # the image is then resampled to the asked size, so it still spans that box.
                if abs(a.shape[1] - h) > 1 or abs(a.shape[2] - w) > 1:
                    raise SystemExit(f"ArcGIS export returned {a.shape[1:]} pixels, asked {(h, w)}")
                if a.shape[1:] != (h, w):
                    a = np.asarray(Image.fromarray(a.transpose(1, 2, 0)).resize((w, h), Image.BILINEAR)).transpose(2, 0, 1)
                img[:, ty:ty + h, tx:tx + w] = a
                self.requests.append(full)
        self.win = _Windows()
        self.win.add(img, rasterio.Affine(gsd_m, 0, x0, 0, -gsd_m, y1), crs, lambda v: np.nan_to_num(v).sum(axis=0) > 0)

    def sample(self, lat, lon):
        v, have = self.win.sample(lat, lon)
        return np.nan_to_num(v), have


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
