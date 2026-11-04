import * as Cesium from './vendor/cesium/index.js';
import { loadPack, loadRun, at, heightAt, bench } from './common.js';

const t0 = performance.now();
const [p, run] = await Promise.all([loadPack(), loadRun()]);
const o = p.m.origin;
const h0 = o.h_ellipsoid_m;
const originC = Cesium.Cartesian3.fromDegrees(o.lon_deg, o.lat_deg, h0);
const enu = Cesium.Transforms.eastNorthUpToFixedFrame(originC);
const inv = Cesium.Matrix4.inverse(enu, new Cesium.Matrix4());
const L = p.m.extent_m;

const scratchC = new Cesium.Cartesian3();
const scratchL = new Cesium.Cartesian3();
function ellipsoidHeight(lonRad, latRad) {
  Cesium.Cartesian3.fromRadians(lonRad, latRad, h0, Cesium.Ellipsoid.WGS84, scratchC);
  Cesium.Matrix4.multiplyByPoint(inv, scratchC, scratchL);
  if (Math.abs(scratchL.x) > L || Math.abs(scratchL.y) > L) return o.geoid_undulation_m; // sea level outside the pack
  return h0 + (heightAt(p, scratchL.x, scratchL.y) - scratchL.z);
}

const tiling = new Cesium.GeographicTilingScheme();
const W = 65;
const terrainProvider = new Cesium.CustomHeightmapTerrainProvider({
  width: W, height: W, tilingScheme: tiling,
  callback(x, y, level) {
    const r = tiling.tileXYToRectangle(x, y, level);
    const out = new Float32Array(W * W);
    for (let j = 0; j < W; j++) for (let i = 0; i < W; i++) {
      const lon = r.west + (i / (W - 1)) * (r.east - r.west);
      const lat = r.north - (j / (W - 1)) * (r.north - r.south);
      out[j * W + i] = ellipsoidHeight(lon, lat);
    }
    return out;
  },
});

const widget = new Cesium.CesiumWidget('c', {
  baseLayer: false, terrainProvider, useDefaultRenderLoop: false, shadows: true, skyAtmosphere: new Cesium.SkyAtmosphere(),
});
const scene = widget.scene;
scene.globe.enableLighting = true;
scene.globe.depthTestAgainstTerrain = true;
// Corners of the pack in geodetic coordinates, for the image rectangle (approximation for the spike).
const corner = (e, n) => Cesium.Cartographic.fromCartesian(Cesium.Matrix4.multiplyByPoint(enu, new Cesium.Cartesian3(e, n, 0), new Cesium.Cartesian3()));
const sw = corner(-L, -L), ne = corner(L, L);
const layer = await Cesium.SingleTileImageryProvider.fromUrl('pack/image.jpg', { rectangle: new Cesium.Rectangle(sw.longitude, sw.latitude, ne.longitude, ne.latitude) });
scene.imageryLayers.addImageryProvider(layer);

const pts = run.t.map((_, i) => Cesium.Matrix4.multiplyByPoint(enu, new Cesium.Cartesian3(run.px[i], run.py[i], run.pz[i]), new Cesium.Cartesian3()));
scene.primitives.add(new Cesium.Primitive({
  geometryInstances: new Cesium.GeometryInstance({ geometry: new Cesium.PolylineGeometry({ positions: pts, width: 2 }) }),
  appearance: new Cesium.PolylineMaterialAppearance({ material: Cesium.Material.fromType('Color', { color: Cesium.Color.WHITE }) }),
}));
const body = scene.primitives.add(new Cesium.Primitive({
  geometryInstances: new Cesium.GeometryInstance({ geometry: new Cesium.CylinderGeometry({ length: 40, topRadius: 1.85, bottomRadius: 1.85 }), attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.LIGHTGRAY) } }),
  appearance: new Cesium.PerInstanceColorAppearance({ flat: false }), asynchronous: false,
}));

// Wait until the globe has loaded what the first view needs.
const startTime = run.t[0];
const setFrame = (time) => {
  const local = new Cesium.Cartesian3(at(run, run.px, time), at(run, run.py, time), at(run, run.pz, time));
  const world = Cesium.Matrix4.multiplyByPoint(enu, local, new Cesium.Cartesian3());
  body.modelMatrix = Cesium.Matrix4.multiplyByTranslation(enu, new Cesium.Cartesian3(local.x, local.y, local.z + 5), new Cesium.Matrix4());
  scene.camera.lookAt(world, new Cesium.HeadingPitchRange(Cesium.Math.toRadians(-25), Cesium.Math.toRadians(-8), 290));
  widget.render();
};
setFrame(startTime);
let waited = 0;
while (!scene.globe.tilesLoaded && waited < 30000) { setFrame(startTime); await new Promise((r) => requestAnimationFrame(r)); waited = performance.now() - t0; }
window.__tiles_loaded_ms = Math.round(performance.now() - t0);
bench(t0, setFrame, run);
