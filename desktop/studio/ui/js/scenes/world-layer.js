// World layer of an environment pack (schema v3): what stands on the terrain, drawn from the pack's
// features.json and vegetation.bin. Geographic context only: nothing here reaches the simulation.
//
// What is what (the sources panel says the same):
// - building and lidar-structure footprints and heights are data: OpenStreetMap footprints
//   (ODbL) and lidar outlines, each height tagged with its source (lidar, OSM tag, OSM levels or a
//   default estimate); walls, flat roofs and their materials are illustrative, roof colours are
//   sampled from the pack image by the builder;
// - point structures (towers, masts, lighthouses) are OSM positions with a lidar, tagged or
//   default height; their shape is illustrative;
// - vegetation positions and heights are lidar crowns and shrub clumps; species, crown shapes
//   and the colour detail are illustrative (the base colour is the image colour at the point).
//
// Rendering: buildings in one merged mesh, vegetation as instanced meshes in 256 m tiles: near the
// camera a dark core with alpha-tested foliage cards, further away one lumpy crown, none beyond
// VEG_FAR.
// Deterministic: every per-instance variation is a hash of the record's position.

import * as THREE from '../../vendor/three/three.module.min.js';
import { terrainAt } from '../environments.js';

const TILE = 256;
const VEG_NEAR = 700; // m: detailed crowns closer than this
const VEG_FAR = 3200; // m: no vegetation drawn beyond this
// Linear luminance given to plant colours (a sunlit leaf albedo of about 0.1).
const FOLIAGE_LUM = 0.11;
/** An 8-bit sRGB channel as linear [0, 1]. */
const lin = (v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };

/** Deterministic hash in [0, 1) of two integers. */
function hash2(a, b) {
  let h = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** A lumpy crown: an icosphere displaced by a fixed pattern, centred at height `cz`, radii (rx, rz). */
function crownGeometry(detail, cz, rx, rz, seed) {
  const g = new THREE.IcosahedronGeometry(1, detail);
  const p = g.getAttribute('position');
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i).normalize();
    const n = 0.8 + 0.2 * Math.sin(v.x * 5.1 + seed) * Math.sin(v.y * 4.3 + 2 * seed) * Math.sin(v.z * 3.7 + 1.3) + 0.06 * Math.sin(v.x * 13.0 + v.y * 11.0 + seed);
    p.setXYZ(i, v.x * rx * n, v.y * rx * n, cz + v.z * rz * n);
  }
  // Smooth normals from the ellipsoid (a crown reads as foliage, not as facets).
  const nr = g.getAttribute('normal');
  for (let i = 0; i < p.count; i++) {
    v.set(p.getX(i) / rx, p.getY(i) / rx, (p.getZ(i) - cz) / rz).normalize();
    nr.setXYZ(i, v.x, v.y, v.z);
  }
  // Darker underside (self-shadowing of a dense crown, illustration).
  const c = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) {
    const k = 0.5 + 0.5 * THREE.MathUtils.clamp((p.getZ(i) - (cz - rz)) / (2 * rz), 0, 1);
    c[3 * i] = c[3 * i + 1] = c[3 * i + 2] = k;
  }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  return g;
}

function trunkGeometry() {
  const g = new THREE.CylinderGeometry(0.035, 0.055, 0.42, 6, 1, true);
  g.rotateX(Math.PI / 2);
  g.translate(0, 0, 0.21);
  const n = g.getAttribute('position').count;
  const c = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { c[3 * i] = 0.5; c[3 * i + 1] = 0.4; c[3 * i + 2] = 0.3; }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  return g;
}

/** Concatenates non-indexed copies of geometries with position, normal and color. */
function merge(geos) {
  const parts = geos.map((g) => (g.index ? g.toNonIndexed() : g));
  const total = parts.reduce((a, g) => a + g.getAttribute('position').count, 0);
  const out = new THREE.BufferGeometry();
  for (const name of ['position', 'normal', 'color']) {
    const arr = new Float32Array(total * 3);
    let o = 0;
    for (const g of parts) { const a = g.getAttribute(name).array; arr.set(a, o); o += a.length; }
    out.setAttribute(name, new THREE.BufferAttribute(arr, 3));
  }
  for (const g of parts) g.dispose();
  return out;
}

/** A leaf-clump texture: grey leaves of varied tone on transparent ground (tinted per instance). */
function leafTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  let seed = 977;
  const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  for (let k = 0; k < 900; k++) {
    // Denser towards the centre, so a card fades out at its rim.
    const a = rnd() * Math.PI * 2; const r = Math.sqrt(rnd()) * 118 * (0.55 + 0.45 * rnd());
    const x = 128 + Math.cos(a) * r; const y = 128 + Math.sin(a) * r;
    const v = Math.round(150 + 105 * rnd() - (r / 118) * 50);
    g.fillStyle = `rgb(${v},${v},${Math.round(v * 0.92)})`;
    g.save();
    g.translate(x, y);
    g.rotate(rnd() * Math.PI);
    g.beginPath();
    g.ellipse(0, 0, 3.5 + 4 * rnd(), 1.6 + 1.8 * rnd(), 0, 0, Math.PI * 2);
    g.fill();
    g.restore();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/**
 * Foliage cards for a crown centred at height `cz` with radii (rx, rz): `n` quads of leaf texture
 * spread through the crown, with normals that point out of the crown (soft, rounded lighting).
 */
function cardGeometry(n, cz, rx, rz, seed) {
  const pos = []; const nor = []; const uv = []; const col = [];
  let s0 = seed;
  const rnd = () => { s0 = (s0 * 16807) % 2147483647; return s0 / 2147483647; };
  const v = new THREE.Vector3(); const a = new THREE.Vector3(); const b = new THREE.Vector3(); const nn = new THREE.Vector3();
  for (let k = 0; k < n; k++) {
    // Card centre inside the crown, larger cards near the core.
    const th = rnd() * Math.PI * 2; const ph = Math.acos(2 * rnd() - 1); const rr = 0.25 + 0.5 * rnd();
    const cx = Math.sin(ph) * Math.cos(th) * rx * rr; const cy = Math.sin(ph) * Math.sin(th) * rx * rr; const cc = cz + Math.cos(ph) * rz * rr;
    const size = (0.75 + 0.35 * rnd()) * Math.max(rx, rz);
    // A random orientation for the card plane.
    v.set(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).normalize();
    a.set(0, 0, 1).cross(v);
    if (a.lengthSq() < 1e-4) a.set(1, 0, 0);
    a.normalize();
    b.copy(v).cross(a).normalize();
    const corners = [[-1, -1, 0, 0], [1, -1, 1, 0], [1, 1, 1, 1], [-1, -1, 0, 0], [1, 1, 1, 1], [-1, 1, 0, 1]];
    for (const [i, j, u, w] of corners) {
      const x = cx + (a.x * i + b.x * j) * size * 0.5;
      const y = cy + (a.y * i + b.y * j) * size * 0.5;
      const z = cc + (a.z * i + b.z * j) * size * 0.5;
      pos.push(x, y, z);
      nn.set(x / rx, y / rx, (z - cz) / rz).normalize();
      nor.push(nn.x, nn.y, nn.z);
      uv.push(u, w);
      const ao = 0.55 + 0.45 * THREE.MathUtils.clamp((z - (cz - rz)) / (2 * rz), 0, 1);
      col.push(ao, ao, ao);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  return g;
}

/** Scales the vertex colours of `g` by `f` (the shaded inside of a crown). */
function darken(g, f) {
  const c = g.getAttribute('color').array;
  for (let i = 0; i < c.length; i++) c[i] *= f;
  return g;
}

/**
 * Unit tree and unit shrub (1 m tall, 1 m across). Near: a dark core (with the trunk) and foliage
 * cards; far: a single lumpy crown.
 */
function archetypes() {
  return {
    tree: { core: darken(merge([trunkGeometry(), crownGeometry(1, 0.64, 0.36, 0.26, 1.7)]), 0.6), cards: cardGeometry(14, 0.64, 0.5, 0.36, 4021), far: merge([trunkGeometry(), crownGeometry(0, 0.64, 0.5, 0.36, 1.7)]) },
    shrub: { core: darken(merge([crownGeometry(1, 0.42, 0.36, 0.4, 0.4)]), 0.6), cards: cardGeometry(10, 0.46, 0.5, 0.5, 733), far: merge([crownGeometry(0, 0.44, 0.5, 0.56, 0.4)]) },
  };
}

/** One merged mesh of extruded footprints: walls (illustrative tint) and flat roofs (image colour). */
function footprintGeometry(pack, list) {
  const pos = []; const nor = []; const col = [];
  const wall = new THREE.Color(); const roof = new THREE.Color(); const tmp = new THREE.Color();
  const concrete = new THREE.Color().setRGB(0.5, 0.49, 0.46);
  const pale = new THREE.Color().setRGB(0.62, 0.63, 0.64);
  for (const b of list) {
    const r = b.ring_dm;
    const n = r.length / 2;
    const xs = new Array(n); const ys = new Array(n);
    let gmin = Infinity; let gsum = 0;
    for (let i = 0; i < n; i++) {
      xs[i] = r[2 * i] / 10; ys[i] = r[2 * i + 1] / 10;
      const g = terrainAt(pack, xs[i], ys[i]) ?? 0;
      gmin = Math.min(gmin, g); gsum += g;
    }
    const base = gmin - 0.4;
    // An estimated height (no lidar and no OSM tag) is drawn at most 3.5 m tall and in a paler,
    // greyer tone, so it does not look like a measured building.
    const est = b.hs === 'default';
    const top = gsum / n + (est ? Math.min(3.5, b.h_dm / 10) : b.h_dm / 10);
    roof.setRGB(lin(b.roof[0]), lin(b.roof[1]), lin(b.roof[2]));
    if (est) roof.lerp(pale, 0.35);
    // Walls: the roof colour pulled towards a neutral concrete (illustration).
    wall.copy(roof).lerp(est ? pale : concrete, 0.6);
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const dx = xs[j] - xs[i]; const dy = ys[j] - ys[i];
      const len = Math.hypot(dx, dy) || 1;
      const nx = dy / len; const ny = -dx / len; // outward for a counter-clockwise ring
      const quad = [[xs[i], ys[i], base], [xs[j], ys[j], base], [xs[j], ys[j], top], [xs[i], ys[i], base], [xs[j], ys[j], top], [xs[i], ys[i], top]];
      for (const [x, y, z] of quad) {
        pos.push(x, y, z); nor.push(nx, ny, 0);
        // Darker towards the ground (contact shadow, illustration).
        tmp.copy(wall).multiplyScalar(z === base ? 0.6 : 1.0);
        col.push(tmp.r, tmp.g, tmp.b);
      }
    }
    const contour = xs.map((x, i) => new THREE.Vector2(x, ys[i]));
    for (const t of THREE.ShapeUtils.triangulateShape(contour, [])) {
      for (const k of t) { pos.push(xs[k], ys[k], top); nor.push(0, 0, 1); col.push(roof.r, roof.g, roof.b); }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.computeBoundingSphere();
  return g;
}

/**
 * Builds the world layer of `pack` (decoded by environments.js). `envMap` lights the materials;
 * `patch(material)` lets the scene add its atmosphere to them. Returns {group, update(camera
 * position), dispose(), stats()} or null when the pack has no world layer.
 */
export function buildWorld(pack, envMap, patch = () => {}) {
  const w = pack.world;
  if (!w || (!w.features && !w.vegetation)) return null;
  const group = new THREE.Group();
  group.name = 'world-layer';
  const materials = []; const geometries = []; const instanced = []; const textures = [];
  const counts = { buildings: 0, lidar_structures: 0, structures: 0, trees: 0, shrubs: 0, tiles: 0 };

  if (w.features) {
    const f = w.features;
    const list = [...f.buildings, ...f.lidar_structures];
    counts.buildings = f.buildings.length;
    counts.lidar_structures = f.lidar_structures.length;
    if (list.length) {
      const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.86, metalness: 0.0, envMap, envMapIntensity: 0.5 });
      patch(m);
      const g = footprintGeometry(pack, list);
      const mesh = new THREE.Mesh(g, m);
      mesh.castShadow = true; mesh.receiveShadow = true;
      mesh.name = 'footprints';
      group.add(mesh);
      materials.push(m); geometries.push(g);
    }
    // Point structures: a tapered column (illustrative shape at the mapped position and height).
    const sm = new THREE.MeshStandardMaterial({ color: 0xd9d8d2, roughness: 0.6, metalness: 0.1, envMap, envMapIntensity: 0.6 });
    patch(sm);
    materials.push(sm);
    for (const s of f.structures) {
      const h = s.h_dm / 10; const r = s.r_dm / 10;
      const x = s.x_dm / 10; const y = s.y_dm / 10;
      const g = new THREE.CylinderGeometry(r * 0.7, r, h, 14, 1);
      g.rotateX(Math.PI / 2);
      g.translate(x, y, (terrainAt(pack, x, y) ?? 0) + h / 2);
      const mesh = new THREE.Mesh(g, sm);
      mesh.castShadow = true; mesh.receiveShadow = true;
      group.add(mesh);
      geometries.push(g);
      counts.structures++;
    }
  }

  const tiles = [];
  if (w.vegetation) {
    const v = w.vegetation;
    const arch = archetypes();
    for (const k of ['tree', 'shrub']) geometries.push(arch[k].core, arch[k].cards, arch[k].far);
    const vm = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0, envMap, envMapIntensity: 0.3 });
    const leaves = leafTexture();
    // Leaves of the cards are lighter than the image colour seen from above (sunlit foliage);
    // alpha to coverage smooths their edges with the multisampled frame.
    const cm = new THREE.MeshStandardMaterial({ vertexColors: true, map: leaves, alphaTest: 0.45, alphaToCoverage: true, side: THREE.DoubleSide, roughness: 0.9, metalness: 0, envMap, envMapIntensity: 0.45 });
    cm.color.setScalar(1.2);
    patch(vm);
    patch(cm);
    materials.push(vm, cm);
    textures.push(leaves);
    const byTile = new Map();
    for (let i = 0; i < v.n; i++) {
      const key = `${Math.floor(v.x[i] / TILE)},${Math.floor(v.y[i] / TILE)}`;
      if (!byTile.has(key)) byTile.set(key, { tree: [], shrub: [] });
      byTile.get(key)[v.kind[i] === 1 ? 'tree' : 'shrub'].push(i);
    }
    const mat = new THREE.Matrix4(); const q = new THREE.Quaternion(); const sc = new THREE.Vector3(); const p = new THREE.Vector3();
    const up = new THREE.Vector3(0, 0, 1); const c = new THREE.Color();
    for (const [key, sets] of byTile) {
      const [tx, ty] = key.split(',').map(Number);
      const centre = new THREE.Vector3((tx + 0.5) * TILE, (ty + 0.5) * TILE, 0);
      centre.z = terrainAt(pack, centre.x, centre.y) ?? 0;
      const tile = { centre, levels: [] };
      for (const kind of ['tree', 'shrub']) {
        const idx = sets[kind];
        if (!idx.length) continue;
        const near = new THREE.InstancedMesh(arch[kind].core, vm, idx.length);
        const cards = new THREE.InstancedMesh(arch[kind].cards, cm, idx.length);
        const far = new THREE.InstancedMesh(arch[kind].far, vm, idx.length);
        idx.forEach((i, j) => {
          const hx = Math.round(v.x[i] * 10); const hy = Math.round(v.y[i] * 10);
          const jitter = hash2(hx, hy);
          q.setFromAxisAngle(up, jitter * Math.PI * 2);
          // Crown diameter from the record, no wider than 1.7 times the height plus 0.8 m (the
          // lidar clump of a low shrub is a 3 m block, not one plant).
          const d = Math.min(2 * v.r[i] * (0.9 + 0.2 * hash2(hy, hx)), v.h[i] * 1.7 + 0.8);
          sc.set(d, d * (0.85 + 0.3 * jitter), v.h[i]);
          p.set(v.x[i], v.y[i], (terrainAt(pack, v.x[i], v.y[i]) ?? 0) - 0.15);
          mat.compose(p, q, sc);
          near.setMatrixAt(j, mat);
          // The hue of the image at the crown, at the brightness of sunlit foliage (an aerial
          // photograph sees crowns darker than their lit side), with a small deterministic spread.
          const r0 = lin(v.rgb[3 * i]); const g0 = lin(v.rgb[3 * i + 1]); const b0 = lin(v.rgb[3 * i + 2]);
          const lum = 0.2126 * r0 + 0.7152 * g0 + 0.0722 * b0;
          const k = Math.min(5, (FOLIAGE_LUM * (0.8 + 0.4 * hash2(hx + 7, hy - 3))) / Math.max(lum, 1e-3));
          c.setRGB(Math.min(1, r0 * k), Math.min(1, g0 * k), Math.min(1, b0 * k));
          near.setColorAt(j, c);
        });
        // The cards and the coarse crowns share the instance data of the cores.
        for (const m of [cards, far]) { m.instanceMatrix = near.instanceMatrix; m.instanceColor = near.instanceColor; }
        for (const m of [near, cards, far]) {
          m.computeBoundingSphere();
          m.castShadow = true; m.receiveShadow = false;
          m.visible = false;
          group.add(m);
        }
        tile.levels.push({ near, cards, far });
        instanced.push(near);
        counts[kind === 'tree' ? 'trees' : 'shrubs'] += idx.length;
      }
      tiles.push(tile);
    }
    counts.tiles = tiles.length;
  }

  let drawn = 0;
  const tiers = [0, 0, 0];
  function update(cam) {
    drawn = 0;
    tiers.fill(0);
    for (const t of tiles) {
      const d = Math.hypot(cam.x - t.centre.x, cam.y - t.centre.y, cam.z - t.centre.z) - TILE * 0.71;
      const tier = d < VEG_NEAR ? 0 : d < VEG_FAR ? 1 : 2;
      for (const l of t.levels) {
        l.near.visible = tier === 0;
        l.cards.visible = tier === 0;
        l.far.visible = tier === 1;
        if (tier < 2) drawn += l.near.count;
        tiers[tier] += l.near.count;
      }
    }
  }

  function dispose() {
    for (const g of geometries) g.dispose();
    for (const m of materials) m.dispose();
    for (const t of textures) t.dispose();
    for (const m of instanced) m.dispose();
  }

  return { group, update, dispose, stats: () => ({ ...counts, vegetation_in_range: drawn, vegetation_tiers: [...tiers] }) };
}
