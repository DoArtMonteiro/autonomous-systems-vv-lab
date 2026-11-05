"""Regression tests of the environment pack pipeline (scripts/geo) that need its third-party libraries.

They are skipped when rasterio, pyproj or numpy are not installed (the pack builder runs in its own
virtual environment, see scripts/geo/build_environment.py). No network.
"""

import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, "scripts", "geo")
HAVE = all(importlib.util.find_spec(m) for m in ("rasterio", "pyproj", "numpy", "PIL"))


@unittest.skipUnless(HAVE, "the pack builder's libraries (rasterio, pyproj, numpy, pillow) are not installed")
class CopernicusTiles(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, GEO)
        import build_environment
        self.be = build_environment

    def tearDown(self):
        sys.path.remove(GEO)

    def test_tiles_above_50_degrees_keep_their_non_square_pixels(self):
        """Copernicus GLO-30 has 3 arc-second longitude and 1 arc-second latitude spacing between
        70 and 80 degrees north. The window must keep both spacings, not resample to square pixels."""
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        rx, ry = 3 / 3600, 1 / 3600
        with tempfile.TemporaryDirectory() as d:
            for lo in (15, 16):
                name = f"Copernicus_DSM_COG_10_N78_00_E{lo:03d}_00_DEM"
                cols, rows = 1200, 3600
                lon = lo + (np.arange(cols) + 0.5) * rx
                lat = 79 - (np.arange(rows) + 0.5) * ry
                LON, LAT = np.meshgrid(lon, lat)
                z = (100 * (LON - 15) + 1000 * (LAT - 78)).astype(np.float32)
                with rasterio.open(os.path.join(d, name + ".tif"), "w", driver="GTiff", width=cols, height=rows, count=1, dtype="float32",
                                   crs="EPSG:4326", transform=from_origin(lo, 79, rx, ry), nodata=-32768.0) as w:
                    w.write(z, 1)
            dem = self.be.Dem(78.15, 15.6, 78.25, 16.2, d, source=os.path.join(d, "{t}.tif"))
            self.assertAlmostEqual(dem.T.a, rx, places=12)
            self.assertAlmostEqual(-dem.T.e, ry, places=12)
            self.assertEqual(dem.missing, [])
            # Bilinear sampling of a plane is exact: the heights come back where they were written.
            for la, lo in [(78.2, 15.7), (78.21, 16.05), (78.17, 15.99)]:
                want = 100 * (lo - 15) + 1000 * (la - 78)
                got = float(dem.sample(np.array(la), np.array(lo)))
                self.assertAlmostEqual(got, want, delta=1e-3)


@unittest.skipUnless(HAVE, "the pack builder's libraries (rasterio, pyproj, numpy, pillow) are not installed")
class Catalogue(unittest.TestCase):
    def test_every_detail_source_names_a_known_kind_and_licence(self):
        sys.path.insert(0, GEO)
        try:
            import build_environment as be
        finally:
            sys.path.remove(GEO)
        for env_id, cfg in be.ENVIRONMENTS.items():
            det = cfg.get("detail")
            if not det:
                continue
            self.assertIn(det["dem"]["kind"], ("tnm-1m", "base", "cog", "wcs"), env_id)
            self.assertIn(det["imagery"]["kind"], ("naip", "wms", "cog", "arcgis"), env_id)
            for k in ("dem", "imagery"):
                lic = det[k].get("licence")
                if det[k]["kind"] in ("cog", "wcs", "wms", "arcgis"):
                    self.assertIn(lic, be.DETAIL_LICENCES, env_id)
                    for f in ("provider", "product", "licence", "attribution"):
                        self.assertTrue(be.DETAIL_LICENCES[lic][f].strip(), (env_id, lic, f))
            # The detail grid must span the layer exactly (the validator refuses anything else).
            self.assertEqual((det["half_extent_m"] / det["dem_spacing_m"]) % 1, 0, env_id)
            self.assertEqual((2 * det["half_extent_m"] / det["image_spacing_m"]) % 1, 0, env_id)
            self.assertLessEqual(len(cfg["summary"]), 600, env_id)


if __name__ == "__main__":
    unittest.main()
