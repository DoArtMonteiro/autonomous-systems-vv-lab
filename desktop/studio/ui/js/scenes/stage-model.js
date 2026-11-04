// Illustrative first-stage model for the mission and geospatial views (M16). The powered-landing
// model is a rigid body with no length, no landing gear and no control surfaces: everything here is
// drawn only so the recorded position, attitude and throttle can be read at a realistic scale.
// Nothing in this geometry moves with anything the model does not record: the legs and the fins
// never deploy, and the plume length follows the applied throttle only.
//
// Body frame: +x along the stage axis from the nozzle exit plane (x = 0), as in rocket.js.

import * as THREE from '../../vendor/three/three.module.min.js';

export const STAGE = {
  radius: 1.85, // m, as the engineering body
  length: 42, // m, nozzle exit plane to the top of the interstage
  tank: [3.2, 35.5], // x range of the painted tank section
};

function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** Faint panel seams and soot streaks on the tank paint (illustration). */
function tankTextures() {
  const map = canvasTexture(256, 1024, (g, w, h) => {
    g.fillStyle = '#eef1f4';
    g.fillRect(0, 0, w, h);
    g.fillStyle = 'rgba(70, 80, 92, 0.18)';
    for (let k = 1; k < 9; k++) g.fillRect(0, Math.round((k * h) / 9), w, 2); // ring seams
    g.fillRect(Math.round(w * 0.25), 0, 2, h); // raceway seam
    g.fillStyle = 'rgba(40, 48, 56, 0.55)';
    g.fillRect(Math.round(w * 0.25) - 3, 0, 8, h); // cable raceway
    // Weathering of a returning stage (illustration): soot rising from the engine end in uneven
    // streaks, heaviest near the engines. Deterministic: fixed pseudo-random sequence.
    const soot = g.createLinearGradient(0, h, 0, h * 0.45);
    soot.addColorStop(0, 'rgba(52, 44, 38, 0.62)');
    soot.addColorStop(0.35, 'rgba(60, 52, 46, 0.28)');
    soot.addColorStop(1, 'rgba(60, 52, 46, 0)');
    g.fillStyle = soot;
    g.fillRect(0, 0, w, h);
    let seed = 4242;
    const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
    for (let k = 0; k < 70; k++) {
      const x = rnd() * w; const top = h * (0.35 + 0.6 * rnd()); const wd = 2 + rnd() * 9;
      const st = g.createLinearGradient(0, h, 0, top);
      st.addColorStop(0, `rgba(48, 40, 34, ${0.12 + 0.22 * rnd()})`);
      st.addColorStop(1, 'rgba(48, 40, 34, 0)');
      g.fillStyle = st;
      g.fillRect(x, top, wd, h - top);
    }
  });
  map.wrapS = THREE.RepeatWrapping;
  return { map };
}

/** Lattice of a grid fin as an alpha texture. */
function latticeTexture() {
  const t = canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = '#000';
    g.fillRect(0, 0, w, h);
    g.strokeStyle = '#fff';
    g.lineWidth = 7;
    g.strokeRect(4, 4, w - 8, h - 8);
    g.lineWidth = 4;
    for (let k = -w; k < 2 * w; k += 18) {
      g.beginPath(); g.moveTo(k, 0); g.lineTo(k + h, h); g.stroke();
      g.beginPath(); g.moveTo(k + h, 0); g.lineTo(k, h); g.stroke();
    }
  });
  t.colorSpace = THREE.NoColorSpace;
  return t;
}

function along(geo) {
  // Three.js lathe and cylinder geometries are built along +y: turn them to +x.
  geo.rotateZ(-Math.PI / 2);
  return geo;
}

/**
 * Builds the stage. Returns {group, materials, shadowCasters, plume, setThrottle(len)}.
 * `envMap` (optional) is a prefiltered environment for the paint and the metal.
 */
export function buildStage(envMap) {
  const R = STAGE.radius;
  const group = new THREE.Group();
  const paint = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.42, metalness: 0.02, envMap, envMapIntensity: 0.9, ...tankTextures() });
  const carbon = new THREE.MeshStandardMaterial({ color: 0x1a1d21, roughness: 0.62, metalness: 0.15, envMap, envMapIntensity: 0.6 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x6b7077, roughness: 0.32, metalness: 0.85, envMap, envMapIntensity: 1.0, side: THREE.DoubleSide });
  const shield = new THREE.MeshStandardMaterial({ color: 0x3a3d42, roughness: 0.8, metalness: 0.2, envMap, envMapIntensity: 0.4 });
  const materials = [paint, carbon, metal, shield];
  const casters = [];
  const add = (mesh) => { group.add(mesh); casters.push(mesh); return mesh; };

  // Engines: a hexagonal cluster of seven bells under a heat shield.
  const bellProfile = [];
  for (let i = 0; i <= 12; i++) {
    const f = i / 12;
    bellProfile.push(new THREE.Vector2(0.24 + 0.32 * Math.pow(1 - f, 1.6), f * 2.0)); // exit at y = 0
  }
  const bell = along(new THREE.LatheGeometry(bellProfile, 28));
  const spots = [[0, 0]];
  for (let k = 0; k < 6; k++) spots.push([1.18 * Math.cos((k * Math.PI) / 3), 1.18 * Math.sin((k * Math.PI) / 3)]);
  for (const [y, z] of spots) {
    const b = new THREE.Mesh(bell, metal);
    b.position.set(0, y, z);
    add(b);
  }
  // Heat shield and engine section skirt.
  const skirt = along(new THREE.CylinderGeometry(R * 1.02, R * 1.06, 1.3, 48, 1, true));
  skirt.translate(2.55, 0, 0);
  add(new THREE.Mesh(skirt, shield));
  const plate = along(new THREE.CircleGeometry(R * 1.02, 48));
  plate.rotateY(-Math.PI / 2);
  plate.translate(1.95, 0, 0);
  add(new THREE.Mesh(plate, shield));

  // Tank section.
  const [t0, t1] = STAGE.tank;
  const tank = along(new THREE.CylinderGeometry(R, R, t1 - t0, 64, 1, true));
  tank.translate((t0 + t1) / 2, 0, 0);
  add(new THREE.Mesh(tank, paint));
  // A thin dark ring where the tank meets the skirt and the interstage.
  for (const x of [t0 + 0.15, t1 - 0.1]) {
    const ring = along(new THREE.CylinderGeometry(R * 1.008, R * 1.008, 0.3, 64, 1, true));
    ring.translate(x, 0, 0);
    add(new THREE.Mesh(ring, carbon));
  }

  // Interstage, open at the top with a dark cap a little below the rim.
  const inter = along(new THREE.CylinderGeometry(R * 1.005, R * 1.005, STAGE.length - t1, 64, 1, true));
  inter.translate((t1 + STAGE.length) / 2, 0, 0);
  add(new THREE.Mesh(inter, carbon));
  const cap = along(new THREE.CircleGeometry(R, 48));
  cap.rotateY(Math.PI / 2);
  cap.translate(STAGE.length - 0.6, 0, 0);
  group.add(new THREE.Mesh(cap, shield));

  // Four lattice fins near the top, fixed (the model has no control surfaces).
  const lattice = latticeTexture();
  const finMat = new THREE.MeshStandardMaterial({ color: 0x8d939a, roughness: 0.5, metalness: 0.7, alphaMap: lattice, alphaTest: 0.5, side: THREE.DoubleSide, envMap, envMapIntensity: 0.8 });
  materials.push(finMat);
  for (let k = 0; k < 4; k++) {
    const a = (k * Math.PI) / 2 + Math.PI / 4;
    // The lattice faces along the axis and stands out radially from the interstage.
    const fg = new THREE.PlaneGeometry(1.3, 1.5);
    fg.rotateY(Math.PI / 2);
    const fin = new THREE.Mesh(fg, finMat);
    fin.position.set(STAGE.length - 2.2, (R + 0.75) * Math.cos(a), (R + 0.75) * Math.sin(a));
    fin.rotation.x = a;
    add(fin);
  }

  // Four landing legs, stowed along the lower body (the model has no landing gear).
  const legShape = new THREE.Shape();
  legShape.moveTo(0, 0); legShape.lineTo(11.5, 0); legShape.lineTo(11.5, 0.22); legShape.lineTo(1.4, 0.55); legShape.lineTo(0, 0.55);
  const legGeo = new THREE.ExtrudeGeometry(legShape, { depth: 0.75, bevelEnabled: false });
  legGeo.translate(0, 0, -0.375);
  for (let k = 0; k < 4; k++) {
    const a = (k * Math.PI) / 2;
    const leg = new THREE.Mesh(legGeo, carbon);
    leg.position.set(2.0, R * Math.cos(a), R * Math.sin(a));
    leg.rotation.x = a; // the leg's y (radial) points outwards
    add(leg);
  }

  // Plume: a short bright core and a long faint outer cone, length from the applied throttle.
  const plume = new THREE.Group();
  const fade = canvasTexture(4, 256, (g, w, h) => {
    const gr = g.createLinearGradient(0, h, 0, 0); // v = 1 at the nozzle
    gr.addColorStop(0, 'rgba(255,255,255,1)');
    gr.addColorStop(0.35, 'rgba(255,255,255,0.55)');
    gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, w, h);
  });
  fade.colorSpace = THREE.NoColorSpace;
  const coneMat = (colour, opacity) => new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity, alphaMap: fade, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  const outerMat = coneMat(0xff9a3c, 0.55);
  const coreMat = coneMat(0xfff1d0, 0.9);
  materials.push(outerMat, coreMat);
  const cone = (r, open) => {
    // Apex away from the nozzle: the cone runs from x = 0 (base, at the exit plane) to x = -1.
    const g = new THREE.ConeGeometry(r, 1, 28, 1, open);
    g.rotateZ(Math.PI / 2);
    g.translate(-0.5, 0, 0);
    return g;
  };
  const outer = new THREE.Mesh(cone(2.3, true), outerMat);
  const core = new THREE.Mesh(cone(1.25, true), coreMat);
  plume.add(outer, core);
  plume.renderOrder = 4;
  group.add(plume);

  const glowTex = canvasTexture(64, 64, (g, w, h) => {
    const gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    gr.addColorStop(0, 'rgba(255,230,190,1)');
    gr.addColorStop(0.4, 'rgba(255,160,70,0.35)');
    gr.addColorStop(1, 'rgba(255,140,50,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, w, h);
  });
  const glowMat = new THREE.SpriteMaterial({ map: glowTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false });
  materials.push(glowMat);
  const glow = new THREE.Sprite(glowMat);
  glow.scale.set(9, 9, 1);
  glow.position.set(-1.2, 0, 0);
  plume.add(glow);

  /** Plume length in metres from the applied throttle (0 hides it). */
  function setThrottle(len) {
    plume.visible = len > 0;
    if (!plume.visible) return;
    outer.scale.set(len, 1, 1);
    core.scale.set(Math.max(3, len * 0.32), 1, 1);
    const k = Math.min(1, len / 28);
    glow.scale.set(6 + 6 * k, 6 + 6 * k, 1);
  }
  return { group, materials, shadowCasters: casters, plume, setThrottle };
}
