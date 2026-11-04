// Geospatial view of the powered landing (M16). The same replay as the mission view (true
// trajectory, controller estimate, pad R5 and keep-out S2, the stage from the recorded true state,
// reference runs), placed on a validated geographic environment pack: terrain from Copernicus DEM
// GLO-30 and a Sentinel-2 true-colour image, on the east-north-up tangent plane at the pack origin.
//
// What is what:
// - simulated (from the record): every position, attitude, throttle, estimate and event;
// - geographic context (from the pack): terrain heights and the image; the simulation assumes flat
//   ground at z = 0 and computes nothing against this terrain;
// - illustrative rendering: the stage body, plume, sky, sun direction, shadows, the neutral plane
//   beyond the pack and the lift of the pad rings onto the terrain so they stay visible.
//
// Model x, y, z are east, north, up of the pack frame (heading 0), so scene coordinates are model
// coordinates. The shell's vv-geo crate checks the pack origin and gives geodetic readouts.

import * as THREE from '../../vendor/three/three.module.min.js';
import { CinemaRocket } from './rocket-cinema.js';
import { channelsOf, circlePoints } from './rocket.js';
import { lowerIndex, sampleAt } from '../dom.js';
import { terrainAt } from '../environments.js';

// Illustrative sun: no date or time of day is part of the model.
const SUN_AZIMUTH_DEG = 128; // clockwise from north
const SUN_ELEVATION_DEG = 34;
const HORIZON = new THREE.Color(0xb9c7d3);
const ZENITH = new THREE.Color(0x3b6a9a);

function sunDirection() {
  const az = (SUN_AZIMUTH_DEG * Math.PI) / 180;
  const el = (SUN_ELEVATION_DEG * Math.PI) / 180;
  return new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.cos(az) * Math.cos(el), Math.sin(el));
}

function skyDome(radius) {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    // Drawn first and never depth-tested: with the logarithmic depth buffer a plain shader would
    // not share the depth encoding of the other materials.
    depthTest: false,
    fog: false,
    uniforms: { sun: { value: sunDirection() }, zenith: { value: ZENITH }, horizon: { value: HORIZON } },
    vertexShader: 'varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `uniform vec3 sun; uniform vec3 zenith; uniform vec3 horizon; varying vec3 vDir;
      void main() {
        float h = clamp(vDir.z, -0.2, 1.0);
        vec3 c = mix(horizon, zenith, pow(max(h, 0.0), 0.55));
        float mu = max(dot(normalize(vDir), sun), 0.0);
        c += vec3(1.0, 0.92, 0.78) * (0.22 * pow(mu, 8.0) + 0.9 * pow(mu, 900.0));
        if (h < 0.0) c = mix(horizon, horizon * 0.82, clamp(-h * 5.0, 0.0, 1.0));
        gl_FragColor = vec4(c, 1.0);
      }`,
  });
  const m = new THREE.Mesh(new THREE.SphereGeometry(radius, 48, 24), mat);
  m.renderOrder = -10;
  m.frustumCulled = false;
  return m;
}

function terrainGeometry(p) {
  const n = p.cols * p.rows;
  const pos = new Float32Array(n * 3);
  const uv = new Float32Array(n * 2);
  const L = p.m.extent_m;
  for (let r = 0; r < p.rows; r++) {
    const nn = p.y0 - r * p.s;
    for (let c = 0; c < p.cols; c++) {
      const i = r * p.cols + c;
      const e = p.x0 + c * p.s;
      pos[i * 3] = e; pos[i * 3 + 1] = nn; pos[i * 3 + 2] = p.up[i];
      uv[i * 2] = (e + L) / (2 * L); uv[i * 2 + 1] = (nn + L) / (2 * L);
    }
  }
  const idx = new Uint32Array((p.cols - 1) * (p.rows - 1) * 6);
  let k = 0;
  for (let r = 0; r < p.rows - 1; r++) {
    for (let c = 0; c < p.cols - 1; c++) {
      const a = r * p.cols + c; const b = a + 1; const d = a + p.cols; const e = d + 1;
      idx[k++] = a; idx[k++] = d; idx[k++] = b; idx[k++] = b; idx[k++] = d; idx[k++] = e;
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeVertexNormals();
  g.computeBoundingSphere();
  return g;
}

/** Mean colour of the image border, for the neutral plane beyond the pack (illustration). */
async function edgeColour(bitmap) {
  const c = document.createElement('canvas');
  c.width = c.height = 32;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(bitmap, 0, 0, 32, 32);
  const d = g.getImageData(0, 0, 32, 32).data;
  let r = 0; let gg = 0; let b = 0; let n = 0;
  for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) {
    if (x > 0 && y > 0 && x < 31 && y < 31) continue;
    const i = (y * 32 + x) * 4; r += d[i]; gg += d[i + 1]; b += d[i + 2]; n++;
  }
  return new THREE.Color(`rgb(${Math.round(r / n)}, ${Math.round(gg / n)}, ${Math.round(b / n)})`);
}

export class GeoRocket extends CinemaRocket {
  lights(s) {
    this.hemi = new THREE.HemisphereLight(0xdfe9f5, 0x4a4438, 1.35);
    s.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xfff4e6, 3.1);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    const sc = this.sun.shadow.camera;
    sc.left = -140; sc.right = 140; sc.top = 140; sc.bottom = -140; sc.near = 10; sc.far = 4000;
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.6;
    s.add(this.sun, this.sun.target);
  }

  build() {
    super.build();
    const s = this.s;
    const p = this.opts.pack;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMappingExposure = 1.0;
    // The engineering backdrop gives way to the landscape.
    for (const o of [this.groundDisc, this.spokes, this.cross, ...(this.rings || [])]) if (o) o.visible = false;
    // Terrain.
    this.terrainMat = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0, color: 0xffffff });
    this.terrain = new THREE.Mesh(terrainGeometry(p), this.terrainMat);
    this.terrain.receiveShadow = true;
    s.add(this.terrain);
    // Beyond the pack: a neutral plane at the lowest edge height (no data there).
    let edgeMin = Infinity;
    for (let c = 0; c < p.cols; c++) edgeMin = Math.min(edgeMin, p.up[c], p.up[(p.rows - 1) * p.cols + c]);
    for (let r = 0; r < p.rows; r++) edgeMin = Math.min(edgeMin, p.up[r * p.cols], p.up[r * p.cols + p.cols - 1]);
    this.beyondMat = new THREE.MeshStandardMaterial({ roughness: 1, color: 0x4d5a63 });
    // Four quads around the square pack, out to the horizon.
    const L = p.m.extent_m;
    const big = 90000;
    const quads = [[-big, L, big, big], [-big, -big, big, -L], [-big, -L, -L, L], [L, -L, big, L]];
    const qg = new THREE.BufferGeometry();
    const qp = [];
    for (const [x0, y0, x1, y1] of quads) qp.push(x0, y0, 0, x1, y0, 0, x1, y1, 0, x0, y0, 0, x1, y1, 0, x0, y1, 0);
    qg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(qp), 3));
    qg.computeVertexNormals();
    this.beyond = new THREE.Mesh(qg, this.beyondMat);
    this.beyond.position.z = edgeMin - 0.6;
    s.add(this.beyond);
    // Sky.
    this.sky = skyDome(80000);
    s.add(this.sky);
    // Pad rings lifted onto the terrain (the model has them on z = 0).
    const drape = (pts, lift) => pts.map((v) => new THREE.Vector3(v.x, v.y, (terrainAt(p, v.x, v.y) ?? 0) + lift));
    if (this.padRing) this.padRing.geometry.setFromPoints(drape(circlePoints(this.pad.cx, this.pad.cy, this.pad.land), 0.35));
    if (this.padDisc) this.padDisc.position.z = (terrainAt(p, this.pad.cx, this.pad.cy) ?? 0) + 0.25;
    if (this.keepRing) {
      this.keepRing.geometry.setFromPoints(drape(circlePoints(this.pad.cx, this.pad.cy, this.pad.keep, 192), 0.4));
      this.keepRing.computeLineDistances();
    }
    // Ground track of the true nozzle plane, draped (a projection for reading the path).
    const ch = this.ch;
    const gt = [];
    for (let i = 0; i < ch.times.length; i++) {
      if (ch.nx && ch.nx[i] !== null && ch.ny[i] !== null) gt.push(new THREE.Vector3(ch.nx[i], ch.ny[i], (terrainAt(p, ch.nx[i], ch.ny[i]) ?? 0) + 0.6));
    }
    this.groundTrack = new THREE.Line(new THREE.BufferGeometry().setFromPoints(gt), new THREE.LineDashedMaterial({ dashSize: 5, gapSize: 4, transparent: true, opacity: 0.9 }));
    this.groundTrack.computeLineDistances();
    s.add(this.groundTrack);
    // Estimate error at the cursor: a segment from the true centre of mass to the estimate.
    const eg = new THREE.BufferGeometry();
    eg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    this.errSeg = new THREE.Line(eg, new THREE.LineBasicMaterial({ transparent: true, opacity: 0.95 }));
    this.errSeg.visible = false;
    s.add(this.errSeg);
    // Event markers at the recorded true position of the instant (fault onsets, detections,
    // violations), so the place of an event can be read on the landscape.
    this.eventMarks = [];
    const sev = { fault: '--fault', detection: '--accent', violation: '--unsafe', warning: '--fail' };
    const seen = new Set();
    const evs = [...(this.model.events || [])].filter((e) => sev[e.severity] && Number.isFinite(e.t));
    for (const f of this.model.record.request.faults || []) evs.push({ t: f.start, severity: 'fault', label: `fault ${f.kind} starts` });
    for (const e of evs) {
      const key = `${e.severity}@${e.t.toFixed(2)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const at = (a) => (a ? sampleAt(ch.times, a, e.t) : null);
      const x = at(ch.px); const y = at(ch.py); const z = at(ch.pz);
      if (x === null || y === null || z === null) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(new Float32Array([x, y, z]), 3));
      const m = new THREE.Points(g, new THREE.PointsMaterial({ size: 11, sizeAttenuation: false, transparent: true, opacity: 0.95, depthTest: false }));
      m.userData = { token: sev[e.severity], t: e.t, label: e.label };
      m.renderOrder = 5;
      this.eventMarks.push(m);
      s.add(m);
    }
    this.camera.near = 1;
    this.camera.far = 120000;
    this.camera.updateProjectionMatrix();
    this.applyTheme();
  }

  async attachImage(blob) {
    const bitmap = await createImageBitmap(blob, { imageOrientation: 'flipY' });
    if (this.disposed) { bitmap.close(); return; }
    const tex = new THREE.Texture(bitmap);
    tex.flipY = false;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.needsUpdate = true;
    this.terrainMat.map = tex;
    this.terrainMat.needsUpdate = true;
    const edge = await edgeColour(bitmap);
    if (this.disposed) return;
    this.beyondMat.color = edge;
    this.bitmap = bitmap;
    this.renderer.compile(this.s, this.camera);
    this.requestRender();
  }

  applyTheme() {
    super.applyTheme();
    if (!this.terrain) return;
    // Daylight scene regardless of the interface theme: the image is a daylight photograph.
    this.grid.visible = false;
    this.s.fog = new THREE.Fog(HORIZON.clone(), 6000, 52000);
    this.s.background = HORIZON.clone();
    this.groundTrack.material.color = new THREE.Color(0xffffff);
    this.errSeg.material.color = new THREE.Color(this.cssColour('--est', '#e6cf55'));
    for (const m of this.eventMarks) m.material.color = new THREE.Color(this.cssColour(m.userData.token, '#ffffff'));
    this.requestRender();
  }

  cssColour(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  preset(mode, initial) {
    if (!this.ok) return;
    if (mode === 'wide') {
      // An elevated oblique view: the whole descent above the landscape it is placed on.
      this.mode = 'wide';
      const top = this.box ? this.box.max.z : 3000;
      const d = top * 1.35;
      this.camera.fov = 40;
      this.controls.target.set(this.pad.cx, this.pad.cy, top * 0.42);
      this.camera.position.set(this.pad.cx + 0.5 * d, this.pad.cy - 0.95 * d, top * 0.62);
      this.camera.updateProjectionMatrix();
      this.controls.update();
      if (!initial) this.requestRender();
      return;
    }
    if (mode === 'overhead') {
      this.mode = 'overhead';
      // Wide enough that the 10 m image reads as context (not as blur around the pad).
      const span = Math.max(3200, this.box ? Math.max(this.box.max.x - this.box.min.x, this.box.max.y - this.box.min.y) * 2.2 : 3200);
      this.camera.fov = 40;
      this.controls.target.set(this.pad.cx, this.pad.cy, 0);
      this.camera.position.set(this.pad.cx, this.pad.cy - span * 0.02, span / (2 * Math.tan((20 * Math.PI) / 180)));
      this.camera.updateProjectionMatrix();
      this.controls.update();
      if (!initial) this.requestRender();
      return;
    }
    super.preset(mode, initial);
    // The base presets reset the clip planes for the engineering scene; keep the landscape's.
    this.camera.near = 1;
    this.camera.far = 120000;
    this.camera.updateProjectionMatrix();
    if (mode === 'follow') {
      // A longer, slightly higher chase so the 10 m image reads as landscape, not as blur.
      this.followOffset = new THREE.Vector3(150, -330, 95);
      this.camera.position.copy(this.controls.target).add(this.followOffset);
      this.controls.update();
    }
    this.keepAboveTerrain();
  }

  keepAboveTerrain() {
    const p = this.opts.pack;
    const c = this.camera.position;
    const g = terrainAt(p, c.x, c.y);
    if (g !== null && c.z < g + 3) {
      c.z = g + 3;
      this.controls.update();
    }
  }

  setTime(t) {
    super.setTime(t);
    if (!this.ok || !this.terrain) return;
    const ch = this.ch;
    const times = ch.times;
    const at = (a) => (a ? sampleAt(times, a, t) : null);
    // Sun and its shadow frustum follow the stage.
    const cur = this.cur || new THREE.Vector3();
    const dir = sunDirection();
    this.sun.target.position.copy(cur);
    this.sun.position.copy(cur).addScaledVector(dir, 1500);
    this.sun.target.updateMatrixWorld();
    for (const o of [this.bodyMesh, this.noseMesh, this.band]) if (o) o.castShadow = true;
    // Estimate error at the cursor, when an estimate sample exists.
    const ex = at(ch.ex); const ey = at(ch.ey); const ez = at(ch.ez);
    this.errSeg.visible = ex !== null && ey !== null && ez !== null;
    if (this.errSeg.visible) {
      const a = this.errSeg.geometry.getAttribute('position');
      a.setXYZ(0, cur.x, cur.y, cur.z);
      a.setXYZ(1, ex, ey, ez);
      a.needsUpdate = true;
    }
    // The drop line ends on the terrain, not on z = 0.
    const g = terrainAt(this.opts.pack, cur.x, cur.y);
    if (g !== null) {
      const dp = this.drop.geometry.getAttribute('position');
      dp.setXYZ(1, cur.x, cur.y, g);
      dp.needsUpdate = true;
      this.drop.computeLineDistances();
    }
    // An event marker appears when the playback reaches its instant.
    for (const m of this.eventMarks) m.visible = t >= m.userData.t - 1e-9;
    this.keepAboveTerrain();
    this.lastIndex = lowerIndex(times, t);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    if (this.terrainMat && this.terrainMat.map) this.terrainMat.map.dispose();
    if (this.bitmap) this.bitmap.close();
    super.dispose();
    // The context is gone: no late frame (an image decode or a cursor tick) may render again.
    this.ok = false;
  }
}

/**
 * Mounts the geospatial view of run `active` among `models` on the decoded `pack`. Returns
 * {ok, dispose, redraw, preset(mode), mode, ready (Promise), stats()}.
 */
export function mountGeo(host, models, active, cursor, colours, pack) {
  const model = models[active];
  const ch = channelsOf(model);
  const ghosts = models.map((m, i) => (i === active ? null : { ch: channelsOf(m), colour: colours[i] })).filter(Boolean);
  const r3 = new GeoRocket(host, model, ch, { ghosts, preset: 'follow', pack, gl: { logarithmicDepthBuffer: true } });
  if (!r3.ok) return { ok: false, dispose: () => {}, redraw: () => {}, preset: () => {}, ready: Promise.resolve(), stats: () => null };
  const unsub = cursor.subscribe((t) => r3.setTime(t));
  r3.setTime(cursor.t);
  const ready = r3.attachImage(pack.image).then(() => r3.setTime(cursor.t));
  return {
    ok: true,
    ready,
    dispose: () => { unsub(); r3.dispose(); },
    redraw: () => { r3.applyTheme(); r3.setTime(cursor.t); },
    preset: (m) => { r3.preset(m); r3.setTime(cursor.t); },
    get mode() { return r3.mode; },
    stats: () => ({ renders: r3.rendered || 0, triangles: r3.renderer.info.render.triangles, geometries: r3.renderer.info.memory.geometries, textures: r3.renderer.info.memory.textures }),
  };
}
