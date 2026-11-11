import * as THREE from './vendor/three/three.module.min.js';
import { loadPack, loadRun, at, bench } from './common.js';

const t0 = performance.now();
const [p, run] = await Promise.all([loadPack(), loadRun()]);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(devicePixelRatio);
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.append(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9fb6cc);
scene.fog = new THREE.Fog(0x9fb6cc, 4000, 16000);
const cam = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 1, 60000);
cam.up.set(0, 0, 1);

// Terrain from the ENU grid.
const g = new THREE.BufferGeometry();
const n = p.cols * p.rows;
const pos = new Float32Array(n * 3);
const uv = new Float32Array(n * 2);
const L = p.m.extent_m;
for (let r = 0; r < p.rows; r++) for (let c = 0; c < p.cols; c++) {
  const i = r * p.cols + c;
  const e = p.x0 + c * p.s;
  const nn = p.y0 - r * p.s;
  pos.set([e, nn, p.up[i]], i * 3);
  uv.set([(e + L) / (2 * L), (nn + L) / (2 * L)], i * 2);
}
const idx = new Uint32Array((p.cols - 1) * (p.rows - 1) * 6);
let k = 0;
for (let r = 0; r < p.rows - 1; r++) for (let c = 0; c < p.cols - 1; c++) {
  const a = r * p.cols + c, b = a + 1, d = a + p.cols, e = d + 1;
  idx.set([a, d, b, b, d, e], k); k += 6;
}
g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
g.setIndex(new THREE.BufferAttribute(idx, 1));
g.computeVertexNormals();
const tex = await new THREE.TextureLoader().loadAsync('pack/image.jpg');
tex.colorSpace = THREE.SRGBColorSpace;
tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
const terrain = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95 }));
terrain.receiveShadow = true;
scene.add(terrain);
scene.add(new THREE.HemisphereLight(0xdde8ff, 0x30302a, 1.2));
const sun = new THREE.DirectionalLight(0xffffff, 2.5);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
scene.add(sun, sun.target);

// Trajectory and vehicle.
const pts = run.t.map((_, i) => new THREE.Vector3(run.px[i], run.py[i], run.pz[i]));
scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xffffff })));
const body = new THREE.Mesh(new THREE.CylinderGeometry(1.85, 1.85, 40, 32), new THREE.MeshStandardMaterial({ color: 0xe8e8e8, metalness: 0.3, roughness: 0.4 }));
body.geometry.rotateX(Math.PI / 2);
body.geometry.translate(0, 0, 20);
body.castShadow = true;
scene.add(body);

bench(t0, (time) => {
  const x = at(run, run.px, time), y = at(run, run.py, time), z = at(run, run.pz, time);
  body.position.set(x, y, z - 15);
  sun.position.set(x - 300, y - 500, z + 800);
  sun.target.position.set(x, y, z);
  cam.position.set(x + 120, y - 260, z + 40);
  cam.lookAt(x, y, z);
  renderer.render(scene, cam);
}, run);
