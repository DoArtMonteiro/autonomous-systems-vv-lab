// Geospatial view of the powered landing (M16). The same replay as the mission view (true
// trajectory, controller estimate, pad R5 and keep-out S2, the stage from the recorded true state,
// reference runs), placed on a validated geographic environment pack: terrain from Copernicus DEM
// GLO-30 and a Sentinel-2 true-colour image, on the east-north-up tangent plane at the pack origin.
//
// What is what:
// - simulated (from the record): every position, attitude, throttle, estimate and event;
// - geographic context (from the pack): terrain heights and the image; the simulation assumes flat
//   ground at z = 0 and computes nothing against this terrain;
// - world layer (schema v3 packs, world-layer.js): buildings, structures and vegetation with the
//   source of every height; their shapes and materials are illustrative;
// - illustrative rendering: the stage (stage-model.js), plume, sky, haze, sun direction, shadows,
//   the water shading where the pack's heights are at mean sea level and its image is dark, the
//   fine grain on the ground near the camera, the glow and dust where the plume meets the ground,
//   the pad surface, the neutral plane beyond the pack and the lift of the pad rings onto the
//   terrain.
//
// Model x, y, z are east, north, up of the pack frame (heading 0), so scene coordinates are model
// coordinates. The shell's vv-geo crate checks the pack origin and gives geodetic readouts.
//
// Cameras: each preset is a rule that gives a pose from the playback state (never from the
// previous frame), so a played descent cannot drift the camera. "Auto" picks one of the
// other rules from the stage's height above the pad, so it is a rule of the playback state too. Terrain clearance is applied to the
// drawn pose only. Changing preset eases between poses unless reduced motion is requested.

import * as THREE from '../../vendor/three/three.module.min.js';
import { CinemaRocket } from './rocket-cinema.js';
import { channelsOf, circlePoints, hexColour } from './rocket.js';
import { STAGE } from './stage-model.js';
import { lowerIndex, sampleAt } from '../dom.js';
import { terrainAt } from '../environments.js';
import { buildWorld } from './world-layer.js';

// Illustrative sun: no date or time of day is part of the model.
const SUN_AZIMUTH_DEG = 128; // clockwise from north
const SUN_ELEVATION_DEG = 27;
// Sky, haze and fog share these linear colours and go through the same tone mapping, so the
// landscape fades into the sky it is drawn against.
const HAZE = new THREE.Color(0xc4d4e4).multiplyScalar(1.3);
const ZENITH = new THREE.Color(0x2e64b4).multiplyScalar(1.25);
const SUN_HAZE = new THREE.Color(0xf6e3c2).multiplyScalar(1.45);
// Aerial perspective: fraction of haze 1 - exp(-d * AERIAL_K * exp(-h / AERIAL_H)), with h the mean
// height of the camera and the point above the pad: near the ground about 2.4 % at 2 km, 11 % at
// 10 km and 30 % at 30 km; thinner air above, so a view from 2 km up is hazed less.
const AERIAL_K = 1.2e-5;
const AERIAL_H = 2500;
const glsl3 = (c) => `vec3(${(c.isVector3 ? [c.x, c.y, c.z] : [c.r, c.g, c.b]).map((v) => v.toFixed(4)).join(', ')})`;
const EARTH_R = 6371000;
const deg = (d) => (d * Math.PI) / 180;

function sunDirection() {
  const az = deg(SUN_AZIMUTH_DEG);
  const el = deg(SUN_ELEVATION_DEG);
  return new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.cos(az) * Math.cos(el), Math.sin(el));
}

/** Unit vector at compass azimuth `az` (degrees from north, clockwise) and elevation `el`. */
function bearing(az, el) {
  return new THREE.Vector3(Math.sin(deg(az)) * Math.cos(deg(el)), Math.cos(deg(az)) * Math.cos(deg(el)), Math.sin(deg(el)));
}

const SKY_FRAG = `uniform vec3 sun; uniform vec3 zenith; uniform vec3 horizon; uniform vec3 sunHaze; varying vec3 vDir;
  void main() {
    vec3 d = normalize(vDir);
    float h = clamp(d.z, -0.2, 1.0);
    float mu = max(dot(d, sun), 0.0);
    // Zenith to a hazy horizon, warmer towards the sun, with a halo and a disc (illustration).
    vec3 c = mix(horizon, zenith, pow(max(h, 0.0), 0.36));
    vec3 hz = mix(horizon, sunHaze, pow(mu, 5.0) * 0.6);
    c = mix(c, hz, exp(-max(h, 0.0) * 14.0));
    c += sunHaze * (0.10 * pow(mu, 8.0) + 0.35 * pow(mu, 80.0)) + vec3(4.0, 3.7, 3.2) * pow(mu, 2400.0);
    if (h < 0.0) c = mix(hz, horizon * 0.85, clamp(-h * 5.0, 0.0, 1.0));
    gl_FragColor = vec4(c, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`;
const SKY_VERT = 'varying vec3 vDir; void main() { vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }';

function skyMaterial(depthTest) {
  return new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    // Drawn first and never depth-tested: with the logarithmic depth buffer a plain shader would
    // not share the depth encoding of the other materials.
    depthTest,
    fog: false,
    uniforms: { sun: { value: sunDirection() }, zenith: { value: ZENITH.clone() }, horizon: { value: HAZE.clone() }, sunHaze: { value: SUN_HAZE.clone() } },
    vertexShader: SKY_VERT,
    fragmentShader: SKY_FRAG,
  });
}

function skyDome(radius) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(radius, 48, 24), skyMaterial(false));
  m.renderOrder = -10;
  m.frustumCulled = false;
  return m;
}

/**
 * Adds aerial perspective to a lit material's shaders: the fragment fades towards the haze colour
 * of the sky in its view direction with distance (illustration; replaces three.js fog for the
 * landscape so that it matches the sky dome).
 */
function aerial(sh) {
  const sun = sunDirection();
  sh.vertexShader = sh.vertexShader
    .replace('#include <common>', '#include <common>\nvarying vec3 vAerialW;')
    .replace('#include <project_vertex>', '#include <project_vertex>\nvAerialW = (vec4(mvPosition.xyz, 0.0) * viewMatrix).xyz;');
  sh.fragmentShader = sh.fragmentShader
    .replace('#include <common>', '#include <common>\nvarying vec3 vAerialW;')
    // Applied to the linear light before tone mapping, as the sky dome is.
    .replace('#include <opaque_fragment>', `{
      float fd = length(vAerialW);
      vec3 vd = vAerialW / max(fd, 1e-3);
      float hm = max(0.0, cameraPosition.z + 0.5 * vAerialW.z);
      float fk = 1.0 - exp(-fd * ${AERIAL_K.toExponential(3)} * exp(-hm / ${AERIAL_H.toFixed(1)}));
      float mu = max(dot(vd, ${glsl3(sun)}), 0.0);
      vec3 fc = mix(${glsl3(HAZE)}, ${glsl3(SUN_HAZE)}, pow(mu, 5.0) * 0.6);
      outgoingLight = mix(outgoingLight, fc, fk);
    }
    #include <opaque_fragment>`)
    .replace('#include <fog_fragment>', '');
}

/** Wraps a material's onBeforeCompile so that `aerial` is applied after it. */
function withAerial(m) {
  const prev = m.onBeforeCompile;
  m.fog = false;
  m.onBeforeCompile = (sh, r) => { if (prev) prev.call(m, sh, r); aerial(sh); };
  const key = m.customProgramCacheKey ? m.customProgramCacheKey.bind(m) : () => '';
  m.customProgramCacheKey = () => `${key()}|aerial-3`;
  return m;
}

/**
 * Terrain mesh of the pack, with a per-vertex flag `sea` where the height is at mean sea level
 * (EGM2008 zero, within 0.6 m once the tangent plane's curvature and the origin height are added
 * back). The flag only steers the illustrative water shading.
 */
function terrainGeometry(p, g0 = p, L = p.m.extent_m, heightAt = (i) => g0.up[i]) {
  const n = g0.cols * g0.rows;
  const pos = new Float32Array(n * 3);
  const uv = new Float32Array(n * 2);
  const sea = new Float32Array(n);
  const h0 = p.m.origin && Number.isFinite(p.m.origin.orthometric_height_m) ? p.m.origin.orthometric_height_m : null;
  for (let r = 0; r < g0.rows; r++) {
    const nn = g0.y0 - r * g0.s;
    for (let c = 0; c < g0.cols; c++) {
      const i = r * g0.cols + c;
      const e = g0.x0 + c * g0.s;
      const z = heightAt(i, e, nn);
      pos[i * 3] = e; pos[i * 3 + 1] = nn; pos[i * 3 + 2] = z;
      uv[i * 2] = (e + L) / (2 * L); uv[i * 2 + 1] = (nn + L) / (2 * L);
      if (h0 !== null) sea[i] = Math.abs(z + h0 + (e * e + nn * nn) / (2 * EARTH_R)) < 0.6 ? 1 : 0;
    }
  }
  p = g0;
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
  g.setAttribute('sea', new THREE.BufferAttribute(sea, 1));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeVertexNormals();
  g.computeBoundingSphere();
  return g;
}

/** Terrain material: the image, plus a smooth reflective finish where the sea flag is set and the image is dark. */
// `detail`: {half, blend} of the pack's detail layer and `baseL` the base half-extent. The base
// discards its fragments inside the detail square; the detail layer is opaque and, over its blend
// margin, crossfades its image into the base image with the same weight as its heights blend into
// the base grid (see terrainAt), so surfaces and colours meet at the edge.
function terrainMaterial(envMap, detail, role, baseL) {
  const m = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0, color: 0xffffff, envMap, envMapIntensity: 0.55 });
  const half = detail ? detail.half.toFixed(3) : '0.0';
  const blend = detail ? Math.max(detail.blend, 1e-3).toFixed(3) : '1.0';
  const L = (baseL || 1).toFixed(3);
  m.userData.baseMap = { value: null };
  // The detail layer also gets a fine grain near the camera, so the 0.5 m texels do not read as
  // blur at a few tens of metres (illustration, at most +-7 % of the image colour).
  const fade = role === 'detail' ? `
        float dIn = ${half} - max(abs(vXY.x), abs(vXY.y));
        vec4 under = texture2D(baseMap, (vXY + ${L}) / (2.0 * ${L}));
        diffuseColor.rgb = mix(under.rgb, diffuseColor.rgb, clamp(dIn / ${blend}, 0.0, 1.0));
        float gk = (1.0 - smoothstep(40.0, 320.0, length(vViewPosition))) * 0.07;
        float gn = vvNoise(vXY * 2.3) * 0.55 + vvNoise(vXY * 7.9) * 0.3 + vvNoise(vXY * 23.0) * 0.15;
        diffuseColor.rgb *= 1.0 + gk * (gn - 0.5) * 2.0;` : '';
  const noise = role === 'detail' ? `
float vvHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vvNoise(vec2 p) { vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(vvHash(i), vvHash(i + vec2(1.0, 0.0)), f.x), mix(vvHash(i + vec2(0.0, 1.0)), vvHash(i + vec2(1.0, 1.0)), f.x), f.y); }` : '';
  // Two metres of overlap hide the hairline where the two triangulations meet.
  const clip = detail && role !== 'detail' ? `if (max(abs(vXY.x), abs(vXY.y)) < ${half} - 2.0) discard;` : '';
  m.onBeforeCompile = (sh) => {
    if (role === 'detail') sh.uniforms.baseMap = m.userData.baseMap;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float sea;\nvarying float vSea;\nvarying vec2 vXY;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvSea = sea;\nvXY = position.xy;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying float vSea;\nvarying vec2 vXY;\nfloat waterMask = 0.0;\n${role === 'detail' ? 'uniform sampler2D baseMap;' : ''}${noise}`)
      .replace('#include <alphatest_fragment>', `#include <alphatest_fragment>\n${clip}`)
      .replace('#include <map_fragment>', `#include <map_fragment>
        // Aerial images are exposed brightly: bring their colours towards ground albedos.
        diffuseColor.rgb *= 0.8;${fade}
        float lum = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
        waterMask = smoothstep(0.5, 0.95, vSea) * (1.0 - smoothstep(0.035, 0.11, lum));
        diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * 0.35 + vec3(0.006, 0.026, 0.042), waterMask);`)
      .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.14, waterMask);')
      .replace('#include <lights_fragment_maps>', '#include <lights_fragment_maps>\nradiance *= mix(1.0, 1.25, waterMask);');
  };
  m.customProgramCacheKey = () => `vv-terrain-5-${role || 'base'}-${half}-${blend}-${L}`;
  return withAerial(m);
}

/** Ground beyond the pack (illustration): vertex colours from the pack's edge, water where `sea`. */
function beyondMaterial(envMap) {
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0, envMap, envMapIntensity: 0.55 });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
attribute float sea;
varying float vSea;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
vSea = sea;`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
varying float vSea;
float waterMask = 0.0;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
waterMask = smoothstep(0.5, 0.95, vSea);
diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * 0.5 + vec3(0.008, 0.03, 0.05), waterMask);`)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
roughnessFactor = mix(roughnessFactor, 0.45, waterMask);`);
  };
  m.customProgramCacheKey = () => 'vv-beyond-1';
  return withAerial(m);
}

/** Colour of `bitmap` (flipped: row 0 south) at the pack points `edge` (x, y pairs), as linear RGB. */
function edgeColours(bitmap, edge, L, out) {
  const n = 128;
  const c = document.createElement('canvas');
  c.width = c.height = n;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(bitmap, 0, 0, n, n);
  const d = g.getImageData(0, 0, n, n).data;
  const col = new THREE.Color();
  for (let i = 0; i < edge.length / 2; i++) {
    const u = (edge[2 * i] + L) / (2 * L); const v = (edge[2 * i + 1] + L) / (2 * L);
    const px = Math.min(n - 1, Math.max(0, Math.floor(u * n))); const py = Math.min(n - 1, Math.max(0, Math.floor(v * n)));
    const k = (py * n + px) * 4;
    col.setRGB(d[k] / 255, d[k + 1] / 255, d[k + 2] / 255, THREE.SRGBColorSpace);
    out[3 * i] = col.r; out[3 * i + 1] = col.g; out[3 * i + 2] = col.b;
  }
}

/** Concrete with faint joints and the painted R5 circle, for the illustrative pad surface. */
function padTexture(apron, land) {
  const c = document.createElement('canvas');
  c.width = c.height = 1024;
  const g = c.getContext('2d');
  const px = (m) => (m / (2 * apron)) * 1024;
  g.fillStyle = '#b9b6ae';
  g.fillRect(0, 0, 1024, 1024);
  // Deterministic speckle (no unseeded randomness anywhere in the Studio).
  let s = 1234567;
  const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  for (let k = 0; k < 9000; k++) {
    const v = 150 + Math.floor(rnd() * 70);
    g.fillStyle = `rgba(${v},${v - 2},${v - 8},0.35)`;
    g.fillRect(rnd() * 1024, rnd() * 1024, 2, 2);
  }
  g.strokeStyle = 'rgba(80,80,76,0.35)';
  g.lineWidth = 2;
  for (let m = -apron; m <= apron; m += 6) {
    g.beginPath(); g.moveTo(512 + px(m), 0); g.lineTo(512 + px(m), 1024); g.stroke();
    g.beginPath(); g.moveTo(0, 512 + px(m)); g.lineTo(1024, 512 + px(m)); g.stroke();
  }
  g.strokeStyle = 'rgba(250,250,246,0.92)';
  if (land) {
    g.lineWidth = Math.max(4, px(0.6));
    g.beginPath(); g.arc(512, 512, px(land), 0, Math.PI * 2); g.stroke();
  }
  g.lineWidth = Math.max(4, px(0.8));
  const arm = px(Math.max(3, (land || 10) * 0.45));
  g.beginPath(); g.moveTo(512 - arm, 512); g.lineTo(512 + arm, 512); g.moveTo(512, 512 - arm); g.lineTo(512, 512 + arm); g.stroke();
  // Fade the rim into the terrain.
  const fade = g.createRadialGradient(512, 512, 430, 512, 512, 512);
  fade.addColorStop(0, 'rgba(0,0,0,0)');
  fade.addColorStop(1, 'rgba(0,0,0,1)');
  g.globalCompositeOperation = 'destination-out';
  g.fillStyle = fade;
  g.fillRect(0, 0, 1024, 1024);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

export class GeoRocket extends CinemaRocket {
  lights(s) {
    this.hemi = new THREE.HemisphereLight(0xdfe9f5, 0x4a4438, 0.62);
    s.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xfff0dc, 2.9);
    this.sun.castShadow = true;
    // One 4096-texel shadow map that follows the subject: about 0.19 m a texel over the 780 m
    // around the stage (and the ground along its sun ray), or 0.68 m over the 2.8 km around the
    // pad in the wide presets (see setTime).
    this.sun.shadow.mapSize.set(4096, 4096);
    const sc = this.sun.shadow.camera;
    sc.left = -390; sc.right = 390; sc.top = 390; sc.bottom = -390; sc.near = 10; sc.far = 6000;
    // Bias in depth units of the 6 km frustum: about 0.3 m; normal bias in metres.
    this.sun.shadow.bias = -0.00005;
    this.sun.shadow.normalBias = 0.15;
    s.add(this.sun, this.sun.target);
  }

  /** The stage and the water reflect the same illustrative sky that is drawn. */
  environmentMap() {
    const pm = new THREE.PMREMGenerator(this.renderer);
    const env = new THREE.Scene();
    const dome = new THREE.Mesh(new THREE.SphereGeometry(10, 48, 24), skyMaterial(true));
    env.add(dome);
    // A ground hemisphere in a neutral landscape tone, so the lower half of the stage is not lit by sky.
    const ground = new THREE.Mesh(new THREE.SphereGeometry(9.5, 32, 16, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x4b5345, side: THREE.BackSide }));
    ground.rotation.x = Math.PI / 2;
    env.add(ground);
    const rt = pm.fromScene(env, 0.01);
    env.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    pm.dispose();
    return rt;
  }

  build() {
    super.build();
    const s = this.s;
    const p = this.opts.pack;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMappingExposure = 0.92;
    // The engineering backdrop gives way to the landscape.
    for (const o of [this.groundDisc, this.spokes, this.cross, ...(this.rings || [])]) if (o) o.visible = false;
    // Terrain.
    const env = this.envRT ? this.envRT.texture : null;
    this.terrainMat = terrainMaterial(env, p.detail, 'base', p.m.extent_m);
    this.terrain = new THREE.Mesh(terrainGeometry(p), this.terrainMat);
    this.terrain.receiveShadow = true;
    s.add(this.terrain);
    if (p.detail) {
      // The detail layer, with the heights the shell uses (blended into the base at its edge).
      this.detailMat = terrainMaterial(env, p.detail, 'detail', p.m.extent_m);
      this.detail = new THREE.Mesh(terrainGeometry(p, p.detail, p.detail.half, (i, e, n) => terrainAt(p, e, n)), this.detailMat);
      this.detail.receiveShadow = true;
      s.add(this.detail);
    }
    // World layer: buildings, structures and lidar vegetation (schema v3 packs).
    this.world = buildWorld(p, env, withAerial);
    if (this.world) s.add(this.world.group);
    // Where the plume meets the ground: a warm glow and a pale dust disc (illustration, from the
    // applied throttle and the nozzle's height above the drawn terrain only).
    this.groundGlow = new THREE.PointLight(0xffa860, 0, 140, 1.6);
    s.add(this.groundGlow);
    const dust = document.createElement('canvas');
    dust.width = dust.height = 128;
    const dg = dust.getContext('2d');
    const gr = dg.createRadialGradient(64, 64, 8, 64, 64, 64);
    gr.addColorStop(0, 'rgba(235,225,205,0.0)');
    gr.addColorStop(0.45, 'rgba(235,225,205,0.75)');
    gr.addColorStop(1, 'rgba(235,225,205,0)');
    dg.fillStyle = gr;
    dg.fillRect(0, 0, 128, 128);
    this.dustTex = new THREE.CanvasTexture(dust);
    this.dustTex.colorSpace = THREE.SRGBColorSpace;
    this.dust = new THREE.Mesh(new THREE.CircleGeometry(1, 48), new THREE.MeshBasicMaterial({ map: this.dustTex, transparent: true, depthWrite: false, opacity: 0 }));
    this.dust.renderOrder = 3;
    this.dust.visible = false;
    s.add(this.dust);
    // Beyond the pack there is no data. The ground continues as an extension of the pack's own
    // edge (illustration): open water at mean sea level where the edge is sea, elsewhere the edge
    // height and the colour of the image at the nearest edge point. Fog hides it with distance.
    const sea = this.terrain.geometry.getAttribute('sea').array;
    const L = p.m.extent_m;
    const big = 90000;
    const quads = [[-big, L, big, big], [-big, -big, big, -L], [-big, -L, -L, L], [L, -L, big, L]];
    const h0 = p.m.origin && Number.isFinite(p.m.origin.orthometric_height_m) ? p.m.origin.orthometric_height_m : 0;
    const edgeNode = (x, y) => {
      const c = Math.round((Math.min(L, Math.max(-L, x)) - p.x0) / p.s);
      const r = Math.round((p.y0 - Math.min(L, Math.max(-L, y))) / p.s);
      return Math.min(p.rows - 1, Math.max(0, r)) * p.cols + Math.min(p.cols - 1, Math.max(0, c));
    };
    const qp = []; const qs = []; const qe = [];
    const seg = 40;
    for (const [x0, y0, x1, y1] of quads) {
      // Geometric spacing: dense near the pack, sparse towards the horizon.
      const sx = (k) => x0 + (x1 - x0) * k; const sy = (k) => y0 + (y1 - y0) * k;
      const f = (i) => (i / seg) ** 2;
      const near = (v0, v1) => Math.abs(v0) <= L + 1 ? 0 : Math.abs(v1) <= L + 1 ? 1 : -1;
      const gx = []; const gy = [];
      for (let i = 0; i <= seg; i++) {
        const kx = near(x0, x1) === 0 ? f(i) : near(x0, x1) === 1 ? 1 - f(seg - i) : i / seg;
        const ky = near(y0, y1) === 0 ? f(i) : near(y0, y1) === 1 ? 1 - f(seg - i) : i / seg;
        gx.push(sx(kx)); gy.push(sy(ky));
      }
      for (let i = 0; i < seg; i++) for (let j = 0; j < seg; j++) {
        const a0 = [gx[i], gy[j]]; const a1 = [gx[i + 1], gy[j]]; const a2 = [gx[i + 1], gy[j + 1]]; const a3 = [gx[i], gy[j + 1]];
        for (const [x, y] of [a0, a1, a2, a0, a2, a3]) {
          const k = edgeNode(x, y);
          const w = sea[k];
          // Water follows the curvature of the tangent plane, as the pack's own sea heights do.
          const z = w ? -h0 - (x * x + y * y) / (2 * EARTH_R) - 0.25 : p.up[k] - 0.3;
          qp.push(x, y, z); qs.push(w); qe.push(Math.min(L, Math.max(-L, x)), Math.min(L, Math.max(-L, y)));
        }
      }
    }
    const qg = new THREE.BufferGeometry();
    qg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(qp), 3));
    qg.setAttribute('sea', new THREE.BufferAttribute(new Float32Array(qs), 1));
    qg.setAttribute('color', new THREE.BufferAttribute(new Float32Array(qs.length * 3).fill(0.3), 3));
    qg.computeVertexNormals();
    this.beyondEdge = new Float32Array(qe);
    this.beyondMat = beyondMaterial(this.envRT ? this.envRT.texture : null);
    this.beyond = new THREE.Mesh(qg, this.beyondMat);
    s.add(this.beyond);
    // Sky.
    this.sky = skyDome(80000);
    s.add(this.sky);
    // Illustrative pad surface draped on the terrain under the R5 ring (no facility is modelled).
    // A pack with a detail image shows the ground as photographed: no surface is drawn over it.
    if (!p.detail) {
      const apron = Math.max(24, (this.pad.land || 10) * 1.9);
      const pg = new THREE.RingGeometry(0.01, apron, 96, 24);
      const pa = pg.getAttribute('position');
      for (let i = 0; i < pa.count; i++) {
        const x = this.pad.cx + pa.getX(i); const y = this.pad.cy + pa.getY(i);
        pa.setXYZ(i, x, y, (terrainAt(p, x, y) ?? 0) + 0.12);
      }
      pg.computeVertexNormals();
      this.padSurface = new THREE.Mesh(pg, new THREE.MeshStandardMaterial({ map: padTexture(apron, this.pad.land), transparent: true, roughness: 0.92, metalness: 0, polygonOffset: true, polygonOffsetFactor: -2 }));
      this.padSurface.receiveShadow = true;
      s.add(this.padSurface);
    }
    if (this.padDisc) this.padDisc.visible = false;
    // Pad rings lifted onto the terrain (the model has them on z = 0).
    const drape = (pts, lift) => pts.map((v) => new THREE.Vector3(v.x, v.y, (terrainAt(p, v.x, v.y) ?? 0) + lift));
    if (this.padRing) this.padRing.geometry.setFromPoints(drape(circlePoints(this.pad.cx, this.pad.cy, this.pad.land), 0.35));
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
    for (const m of this.stage.shadowCasters) m.castShadow = true;
    // The screen-size marker would sit on the illustrated body: keep it only for distant views.
    this.marker.material.size = 7;
    this.camera.near = 1;
    this.camera.far = 120000;
    this.camera.updateProjectionMatrix();
    // User orbiting in a tracking preset changes that preset's offset, not the rule.
    this.controls.addEventListener('start', () => { this.dragging = true; this.transition = null; });
    this.controls.addEventListener('end', () => { this.dragging = false; });
    this.controls.addEventListener('change', () => {
      if (this.dragging && this.mode === 'follow') this.followOffset = this.camera.position.clone().sub(this.controls.target);
      if (this.world) this.world.update(this.camera.position);
    });
    this.applyTheme();
  }

  async texture(blob) {
    const bitmap = await createImageBitmap(blob, { imageOrientation: 'flipY' });
    if (this.disposed) { bitmap.close(); return null; }
    const tex = new THREE.Texture(bitmap);
    tex.flipY = false;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.needsUpdate = true;
    (this.bitmaps = this.bitmaps || []).push(bitmap);
    // Once on the GPU the decoded image is not needed again (the scene never re-uploads it):
    // release it so the CPU copy of a 4096-texel image does not stay in memory.
    tex.onUpdate = () => { bitmap.close(); };
    return tex;
  }

  async attachImage(pack) {
    const tex = await this.texture(pack.image);
    if (!tex) return;
    this.terrainMat.map = tex;
    this.terrainMat.needsUpdate = true;
    const cattr = this.beyond.geometry.getAttribute('color');
    edgeColours(tex.image, this.beyondEdge, pack.m.extent_m, cattr.array);
    cattr.needsUpdate = true;
    if (this.disposed) return;
    if (this.detail && pack.detail) {
      const dt = await this.texture(pack.detail.image);
      if (!dt) return;
      this.detailMat.map = dt;
      this.detailMat.userData.baseMap.value = tex;
      this.detailMat.needsUpdate = true;
    }
    this.renderer.compile(this.s, this.camera);
    this.requestRender();
  }

  applyTheme() {
    super.applyTheme();
    if (!this.terrain) return;
    // Daylight scene regardless of the interface theme: the image is a daylight photograph.
    this.grid.visible = false;
    // Fog for what the aerial perspective does not cover (the stage, lines, markers).
    this.s.fog = new THREE.FogExp2(HAZE.clone(), 2.6e-5);
    this.s.background = HAZE.clone();
    this.groundTrack.material.color = new THREE.Color(0xffffff);
    this.errSeg.material.color = new THREE.Color(this.cssColour('--est', '#e6cf55'));
    for (const m of this.eventMarks) m.material.color = new THREE.Color(this.cssColour(m.userData.token, '#ffffff'));
    this.requestRender();
  }

  cssColour(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  ground(x, y) {
    return terrainAt(this.opts.pack, x, y) ?? 0;
  }

  /** The point a tracking camera aims at: mid-body on the recorded stage axis. */
  aimPoint() {
    if (!this.vehicle) return new THREE.Vector3(this.pad.cx, this.pad.cy, 20);
    const axis = new THREE.Vector3(1, 0, 0).applyQuaternion(this.vehicle.quaternion);
    return this.vehicle.position.clone().addScaledVector(axis, STAGE.length * 0.45);
  }

  /** Pose {pos, target, fov} of preset `mode` at the current playback state. */
  pose(mode) {
    if (mode === 'director') return this.pose(this.directorShot || this.directorPick());
    const aim = this.aimPoint();
    const pad = new THREE.Vector3(this.pad.cx, this.pad.cy, 0);
    if (mode === 'follow') {
      // A chase camera on the sun side, close enough that the stage is the subject of the frame.
      const off = this.followOffset || bearing(152, 7).multiplyScalar(190);
      return { pos: aim.clone().add(off), target: aim, fov: 30 };
    }
    if (mode === 'pad') {
      // An observer 10 m above the ground 420 m from the pad, following with a long lens that
      // keeps about 2.4 stage lengths in frame. The bearing is the first of a fixed list with a
      // clear line of sight over the terrain to the pad (chosen once per scene).
      const at = this.observerPoint();
      const d = at.distanceTo(aim);
      const fov = Math.min(40, Math.max(3, (2 * Math.atan((STAGE.length * 1.2) / d) * 180) / Math.PI));
      // While the stage is low over the horizon, frame the horizon too: the stage sits in the upper
      // third and the landscape gives it scale. Higher up an observer only sees sky, which is kept.
      const flat = Math.hypot(aim.x - at.x, aim.y - at.y);
      const elev = (Math.atan2(aim.z - at.z, flat) * 180) / Math.PI;
      if (elev > 0 && elev < 22) {
        const wide = Math.max(fov, Math.min(40, elev * 1.9 + 6));
        const down = ((elev - wide * 0.18) * Math.PI) / 180;
        const target = new THREE.Vector3(aim.x, aim.y, at.z + Math.tan(Math.max(0, down)) * flat);
        return { pos: at, target, fov: wide };
      }
      return { pos: at, target: aim, fov };
    }
    if (mode === 'closeup') {
      // At the pad: a raised camera beside the landing area, for the touchdown at full scale with
      // the ground around the pad in view.
      // From the north-east, 20 m up (about 8 degrees above the pad, so the pad surface and the
      // stage's shadow read), with a longer lens: the sun on the camera's left, the shadow
      // across the frame and the land behind the pad in view.
      const at = pad.clone().addScaledVector(bearing(38, 0), 150);
      at.z = this.ground(at.x, at.y) + 20;
      // The pad waits in the lower half of the frame while the stage is high (it enters from
      // the top); the view then follows it down and settles on it at the pad.
      const g0 = this.ground(this.pad.cx, this.pad.cy);
      const tgt = aim.clone();
      tgt.z = Math.min(Math.max(tgt.z, g0 + 17), g0 + 24);
      tgt.x = this.pad.cx + (tgt.x - this.pad.cx) * 0.5;
      tgt.y = this.pad.cy + (tgt.y - this.pad.cy) * 0.5;
      const fov = Math.min(40, (2 * Math.atan((STAGE.length * 0.95) / at.distanceTo(tgt)) * 180) / Math.PI);
      return { pos: at, target: tgt, fov };
    }
    if (mode === 'wide') {
      // An elevated oblique view: the whole descent above the landscape it is placed on.
      const top = this.box ? this.box.max.z : 3000;
      const d = top * 1.35;
      return { pos: new THREE.Vector3(this.pad.cx + 0.5 * d, this.pad.cy - 0.95 * d, top * 0.62), target: new THREE.Vector3(this.pad.cx, this.pad.cy, top * 0.42), fov: 40 };
    }
    // Overhead: wide enough that the 10 m image reads as context (not as blur around the pad).
    const span = Math.max(3200, this.box ? Math.max(this.box.max.x - this.box.min.x, this.box.max.y - this.box.min.y) * 2.2 : 3200);
    return { pos: new THREE.Vector3(this.pad.cx, this.pad.cy - span * 0.02, span / (2 * Math.tan(deg(20)))), target: pad, fov: 40 };
  }

  /** Height of the stage's nozzle plane above the drawn terrain under it (m), or null. */
  nozzleHeight() {
    if (!this.vehicle) return null;
    const p = this.vehicle.position;
    return p.z - this.ground(p.x, p.y);
  }

  /** Glow and dust where the plume meets the ground (illustration from throttle and height). */
  groundEffect() {
    if (!this.dust) return;
    const h = this.nozzleHeight();
    const len = this.plumeLength || 0;
    const reach = 70;
    const on = h !== null && len > 0 && h < reach;
    this.dust.visible = on;
    this.groundGlow.intensity = 0;
    if (!on) return;
    const p = this.vehicle.position;
    const k = (1 - Math.max(0, h) / reach) * Math.min(1, len / 28);
    const g = this.ground(p.x, p.y);
    const r = 8 + 34 * k;
    this.dust.position.set(p.x, p.y, g + 0.25);
    this.dust.scale.set(r, r, 1);
    this.dust.material.opacity = 0.55 * k;
    this.groundGlow.position.set(p.x, p.y, g + Math.max(2, Math.min(h, 30) * 0.4));
    this.groundGlow.intensity = 9000 * k;
  }

  /** The shot "Auto" uses at the current playback state, from the stage's height above the pad. */
  directorPick() {
    const h = this.vehicle ? this.vehicle.position.z - this.ground(this.pad.cx, this.pad.cy) : 0;
    if (h > 1400) return 'wide';
    if (h > 260) return 'follow';
    if (h > 55) return 'pad';
    return 'closeup';
  }

  /** Tallest vegetation record within `r` m of (x, y) in the world layer, or 0. */
  canopyAt(x, y, r) {
    const v = this.opts.pack.world && this.opts.pack.world.vegetation;
    if (!v) return 0;
    let h = 0;
    for (let i = 0; i < v.n; i++) if (Math.abs(v.x[i] - x) < r && Math.abs(v.y[i] - y) < r && v.h[i] > h) h = v.h[i];
    return h;
  }

  /** Ground observer for the "From the ground" camera: 420 m out, 10 m up (a mast or a roof), on the first clear bearing. */
  observerPoint() {
    if (this.observer) return this.observer.clone();
    const BEARINGS = [160, 200, 120, 240, 80, 280, 40, 320, 0];
    const pad = new THREE.Vector3(this.pad.cx, this.pad.cy, this.ground(this.pad.cx, this.pad.cy) + 6);
    let pick = null;
    for (const b of BEARINGS) {
      const at = new THREE.Vector3(this.pad.cx, this.pad.cy, 0).addScaledVector(bearing(b, 0), 420);
      // Stand clear of the vegetation: 12 m above the ground or 8 m above the canopy within 40 m.
      at.z = this.ground(at.x, at.y) + Math.max(12, this.canopyAt(at.x, at.y, 40) + 8);
      let clear = true;
      for (let k = 1; k < 40 && clear; k++) {
        const q = at.clone().lerp(pad, k / 40);
        if (this.ground(q.x, q.y) > q.z + 0.5) clear = false;
      }
      if (clear) { pick = { at, b }; break; }
    }
    if (!pick) {
      // No clear line at ground level: stand on the default bearing, raised above the obstruction.
      const at = new THREE.Vector3(this.pad.cx, this.pad.cy, 0).addScaledVector(bearing(BEARINGS[0], 0), 420);
      at.z = this.ground(at.x, at.y) + 40;
      pick = { at, b: BEARINGS[0], raised: true };
    }
    this.observer = pick.at;
    this.observerInfo = { bearing_deg: pick.b, raised: !!pick.raised };
    return pick.at.clone();
  }

  preset(mode, initial) {
    if (!this.ok) return;
    const known = ['director', 'follow', 'pad', 'closeup', 'wide', 'overhead'];
    const next = known.includes(mode) ? mode : 'follow';
    const reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (next === 'follow') this.followOffset = null;
    this.userMoved = false;
    if (!initial && !reduce && this.terrain) {
      this.transition = { from: { pos: this.camera.position.clone(), target: this.controls.target.clone(), fov: this.camera.fov }, t0: performance.now(), dur: 700 };
    } else this.transition = null;
    this.mode = next;
    this.camera.near = 1;
    this.camera.far = 120000;
    if (!this.terrain) return; // called from the base build, before the landscape exists
    this.place();
    if (!initial) this.requestRender();
  }

  /** Puts the camera at the current preset's pose (eased from the previous one while it changes). */
  place() {
    if (this.dragging) return;
    if (this.mode === 'director') {
      // A change of shot eases like a change of preset (unless reduced motion is requested).
      const shot = this.directorPick();
      if (this.directorShot && shot !== this.directorShot && !this.transition) {
        const reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!reduce) this.transition = { from: { pos: this.camera.position.clone(), target: this.controls.target.clone(), fov: this.camera.fov }, t0: performance.now(), dur: 1100 };
      }
      this.directorShot = shot;
    }
    const free = this.userMoved && this.mode !== 'follow' && this.mode !== 'pad' && this.mode !== 'closeup' && this.mode !== 'director' && !this.transition;
    if (free) return; // a static preset the user has orbited stays where the user left it
    const want = this.pose(this.mode);
    let { pos, target, fov } = want;
    if (this.transition) {
      const k = Math.min(1, (performance.now() - this.transition.t0) / this.transition.dur);
      const e = ease(k);
      const f = this.transition.from;
      pos = f.pos.clone().lerp(want.pos, e);
      target = f.target.clone().lerp(want.target, e);
      fov = f.fov + (want.fov - f.fov) * e;
      if (k >= 1) this.transition = null;
      else this.animate();
    }
    // Terrain clearance on the drawn pose only.
    const g = this.ground(pos.x, pos.y);
    if (pos.z < g + 3) pos = pos.clone().setZ(g + 3);
    this.camera.position.copy(pos);
    this.controls.target.copy(target);
    this.camera.fov = fov;
    this.camera.updateProjectionMatrix();
    this.controls.update();
    // Vegetation detail follows the drawn camera, including during a transition.
    if (this.world) this.world.update(this.camera.position);
  }

  animate() {
    if (this.animFrame) return;
    this.animFrame = requestAnimationFrame(() => {
      this.animFrame = 0;
      if (!this.ok || this.disposed) return;
      this.place();
      this.requestRender();
    });
  }

  setTime(t) {
    // The base classes would move the camera by their own rules; this class owns the camera.
    const mode = this.mode;
    this.mode = 'geo';
    super.setTime(t);
    this.mode = mode;
    if (!this.ok || !this.terrain) return;
    const ch = this.ch;
    const times = ch.times;
    const at = (a) => (a ? sampleAt(times, a, t) : null);
    // Sun and its shadow frustum: around the stage (which also covers the ground along its sun
    // ray), or around the pad for the wide presets.
    const cur = this.cur || new THREE.Vector3();
    const dir = sunDirection();
    const wideMode = this.mode === 'wide' || this.mode === 'overhead' || (this.mode === 'director' && this.directorShot === 'wide');
    const ext = wideMode ? 1400 : 390;
    const sc = this.sun.shadow.camera;
    if (sc.right !== ext) {
      sc.left = -ext; sc.right = ext; sc.top = ext; sc.bottom = -ext;
      sc.updateProjectionMatrix();
    }
    const centre = wideMode ? new THREE.Vector3(this.pad.cx, this.pad.cy, this.ground(this.pad.cx, this.pad.cy)) : cur;
    this.sun.target.position.copy(centre);
    this.sun.position.copy(centre).addScaledVector(dir, 3000);
    this.sun.target.updateMatrixWorld();
    this.groundEffect();
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
    // At the end of a run whose requirements failed, the pad ring takes the failure colour: the
    // upright stage is drawn for orientation, the contact itself is not modelled.
    const failed = this.model.record && this.model.record.outcome && this.model.record.outcome.status !== 'success';
    if (this.padRing) this.padRing.material.color = hexColour(failed && t >= times[times.length - 1] - 1e-9 ? '--fail' : '--pass');
    // An event marker appears when the playback reaches its instant.
    for (const m of this.eventMarks) m.visible = t >= m.userData.t - 1e-9;
    this.place();
    // The point marker helps find the stage from afar; up close it would sit on the body.
    this.marker.visible = this.camera.position.distanceTo(cur) > 900;
    this.lastIndex = lowerIndex(times, t);
    this.requestRender();
  }

  /** How tall the stage is drawn, as a fraction of the viewport height (for acceptance checks). */
  stageScreenFraction() {
    if (!this.vehicle) return null;
    const axis = new THREE.Vector3(1, 0, 0).applyQuaternion(this.vehicle.quaternion);
    const a = this.vehicle.position.clone().project(this.camera);
    const b = this.vehicle.position.clone().addScaledVector(axis, STAGE.length).project(this.camera);
    // Only a stage wholly in front of the camera and inside the frame has a meaningful size.
    if ([a, b].some((v) => Math.abs(v.x) > 1 || Math.abs(v.y) > 1 || v.z > 1 || v.z < -1)) return null;
    return Math.abs(a.y - b.y) / 2;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    if (this.animFrame) cancelAnimationFrame(this.animFrame);
    if (this.terrainMat && this.terrainMat.map) this.terrainMat.map.dispose();
    if (this.padSurface) this.padSurface.material.map.dispose();
    if (this.detailMat && this.detailMat.map) this.detailMat.map.dispose();
    if (this.world) this.world.dispose();
    if (this.dustTex) this.dustTex.dispose();
    for (const b of this.bitmaps || []) b.close();
    // The 4096 shadow map is a render target the light owns and every texture a material holds is
    // its own GPU allocation; neither goes with geometry and material disposal (M16.2 left about
    // 65 MB of GPU memory behind after leaving the scene).
    if (this.sun && this.sun.shadow && this.sun.shadow.map) { this.sun.shadow.map.dispose(); this.sun.shadow.map = null; }
    if (this.s) {
      const seen = new Set();
      this.s.traverse((o) => {
        for (const m of Array.isArray(o.material) ? o.material : o.material ? [o.material] : []) {
          for (const v of Object.values(m)) if (v && v.isTexture && !seen.has(v)) { seen.add(v); v.dispose(); }
          for (const u of Object.values(m.uniforms || {})) if (u && u.value && u.value.isTexture && !seen.has(u.value)) { seen.add(u.value); u.value.dispose(); }
        }
      });
    }
    if (this.renderer) this.renderer.renderLists.dispose();
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
  r3.preset('follow', true);
  const unsub = cursor.subscribe((t) => r3.setTime(t));
  r3.setTime(cursor.t);
  const ready = r3.attachImage(pack).then(() => r3.setTime(cursor.t));
  const v3 = (v) => [Math.round(v.x * 10) / 10, Math.round(v.y * 10) / 10, Math.round(v.z * 10) / 10];
  return {
    ok: true,
    ready,
    dispose: () => { unsub(); r3.dispose(); },
    redraw: () => { r3.applyTheme(); r3.setTime(cursor.t); },
    preset: (m) => { r3.preset(m); r3.setTime(cursor.t); },
    get mode() { return r3.mode; },
    stats: () => ({
      renders: r3.rendered || 0, triangles: r3.renderer.info.render.triangles, geometries: r3.renderer.info.memory.geometries, textures: r3.renderer.info.memory.textures,
      camera: r3.ok ? { mode: r3.mode, position: v3(r3.camera.position), target: v3(r3.controls.target), fov: Math.round(r3.camera.fov * 10) / 10, distance: r3.cur ? Math.round(r3.camera.position.distanceTo(r3.cur)) : null, stageFraction: (() => { const f = r3.stageScreenFraction(); return f === null ? null : Math.round(f * 1000) / 1000; })(), observer: r3.observerInfo || null, shot: r3.mode === 'director' ? r3.directorShot || null : null } : null,
      world: r3.world ? r3.world.stats() : null,
    }),
  };
}
