// Scene renderer for kind "rocket-3d": the powered-landing stage. A three.js view of the true
// trajectory, the pad with the landing radius (R5) and the keep-out ring (S2), the navigation
// estimate when recorded, and the stage at the cursor with its recorded attitude; plus precise 2D
// top and profile views. The model has no vehicle length: the drawn body is an illustration.

import * as THREE from '../../vendor/three/three.module.min.js';
import { OrbitControls } from '../../vendor/three/OrbitControls.js';
import { h, clear, lowerIndex, sampleAt, num, timeText } from '../dom.js';
import { cssVar } from '../charts.js';
import { runDash } from '../model.js';
import { Plot2D, polyline, extent } from './plot2d.js';

const BODY_LENGTH = 40; // illustration only
const BODY_RADIUS = 1.85;

function chan(model, id) {
  const c = id && model.byId.get(id);
  return c ? c.values : null;
}

function channelsOf(model) {
  const sc = model.record.scene.channels || {};
  const pos = sc.position || ['pos_x', 'pos_y', 'pos_z'];
  const noz = sc.nozzle_position || ['base_x', 'base_y', 'altitude'];
  const att = sc.attitude || ['q_w', 'q_x', 'q_y', 'q_z'];
  const tb = sc.timebase && model.timebases[sc.timebase] ? sc.timebase : model.primary;
  return {
    times: model.timebases[tb] || [],
    px: chan(model, pos[0]), py: chan(model, pos[1]), pz: chan(model, pos[2]),
    nx: chan(model, noz[0]), ny: chan(model, noz[1]), nz: chan(model, noz[2]),
    qw: chan(model, att[0]), qx: chan(model, att[1]), qy: chan(model, att[2]), qz: chan(model, att[3]),
    ex: chan(model, 'est_x'), ey: chan(model, 'est_y'), ez: chan(model, 'est_z'),
    throttle: chan(model, 'act_throttle'),
    thrust: chan(model, sc.thrust || 'thrust_n'),
    engine: chan(model, sc.engine_state || 'engine_state'),
    padDist: chan(model, 'pad_distance'),
    vz: chan(model, 'vel_z'), vh: chan(model, 'vel_h'), tilt: chan(model, 'tilt_deg'),
  };
}

function padOf(scene) {
  const p = scene.pad || {};
  return {
    cx: Array.isArray(p.centre_m) ? p.centre_m[0] : 0,
    cy: Array.isArray(p.centre_m) ? p.centre_m[1] : 0,
    land: typeof p.landing_radius_m === 'number' ? p.landing_radius_m : null,
    keep: typeof p.keep_out_radius_m === 'number' ? p.keep_out_radius_m : null,
  };
}

function hexColour(name) {
  return new THREE.Color(cssVar(name) || '#888888');
}

function circlePoints(cx, cy, r, n = 128) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    pts.push(new THREE.Vector3(cx + r * Math.cos(a), cy + r * Math.sin(a), 0.05));
  }
  return pts;
}

function circle2d(ctx, P, cx, cy, r) {
  ctx.beginPath();
  ctx.arc(P.x(cx), P.y(cy), r * P.scale, 0, Math.PI * 2);
  ctx.stroke();
}

// ---------------------------------------------------------------------------- 3D view

class Rocket3D {
  constructor(host, model, ch) {
    this.host = host;
    this.model = model;
    this.ch = ch;
    this.scene = model.record.scene;
    this.mode = 'follow';
    this.ok = true;
    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch (e) {
      this.ok = false;
      host.append(h('p', { class: 'empty' }, 'The 3D view needs WebGL, which is not available here. The top and profile views below are complete.'));
      return;
    }
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    this.renderer.domElement.setAttribute('role', 'img');
    this.renderer.domElement.setAttribute('aria-label', 'Three-dimensional view of the landing: true trajectory, pad, keep-out ring and the stage at the cursor. Drag to orbit, wheel to zoom.');
    this.renderer.domElement.tabIndex = 0;
    host.append(this.renderer.domElement);
    const s = new THREE.Scene();
    this.s = s;
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.5, 40000);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.addEventListener('change', () => this.requestRender());
    this.controls.addEventListener('start', () => { this.userMoved = true; });
    s.add(new THREE.HemisphereLight(0xffffff, 0x404040, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-300, -500, 800);
    s.add(sun);
    this.build();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
  }

  build() {
    const { ch } = this;
    const pad = padOf(this.scene);
    this.pad = pad;
    const n = ch.times.length;
    // Ground grid in the x-y plane (z up).
    this.grid = new THREE.GridHelper(2000, 40);
    this.grid.rotation.x = Math.PI / 2;
    this.s.add(this.grid);
    // Pad disc (landing radius, R5) and keep-out ring (S2).
    if (pad.land) {
      this.padDisc = new THREE.Mesh(new THREE.CircleGeometry(pad.land, 64), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.35 }));
      this.padDisc.position.set(pad.cx, pad.cy, 0.02);
      this.s.add(this.padDisc);
      this.padRing = new THREE.Line(new THREE.BufferGeometry().setFromPoints(circlePoints(pad.cx, pad.cy, pad.land)), new THREE.LineBasicMaterial());
      this.s.add(this.padRing);
    }
    if (pad.keep) {
      const g = new THREE.BufferGeometry().setFromPoints(circlePoints(pad.cx, pad.cy, pad.keep, 192));
      this.keepRing = new THREE.Line(g, new THREE.LineDashedMaterial({ dashSize: 4, gapSize: 3 }));
      this.keepRing.computeLineDistances();
      this.s.add(this.keepRing);
    }
    // True trajectory of the centre of mass, with injected fault windows coloured.
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    this.windows = (this.model.record.request.faults || []).map((f) => [f.start, f.end]);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = ch.px ? ch.px[i] ?? 0 : 0;
      pos[i * 3 + 1] = ch.py ? ch.py[i] ?? 0 : 0;
      pos[i * 3 + 2] = ch.pz ? ch.pz[i] ?? 0 : 0;
    }
    const tg = new THREE.BufferGeometry();
    tg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    tg.setAttribute('color', new THREE.BufferAttribute(col, 3));
    this.trajColours = col;
    this.traj = new THREE.Line(tg, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55 }));
    this.s.add(this.traj);
    const done = new THREE.BufferGeometry();
    done.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.done = new THREE.Line(done, new THREE.LineBasicMaterial());
    this.s.add(this.done);
    // Navigation estimate, when recorded.
    if (ch.ex && ch.ey && ch.ez) {
      const pts = [];
      for (let i = 0; i < n; i++) if (ch.ex[i] !== null && ch.ey[i] !== null && ch.ez[i] !== null) pts.push(new THREE.Vector3(ch.ex[i], ch.ey[i], ch.ez[i]));
      const eg = new THREE.BufferGeometry().setFromPoints(pts);
      this.est = new THREE.Line(eg, new THREE.LineDashedMaterial({ dashSize: 12, gapSize: 8 }));
      this.est.computeLineDistances();
      this.s.add(this.est);
    }
    // Stage (illustration): body along +x_B from the nozzle exit plane, plume along -x_B.
    this.vehicle = new THREE.Group();
    const body = new THREE.CylinderGeometry(BODY_RADIUS, BODY_RADIUS, BODY_LENGTH, 24);
    body.rotateZ(-Math.PI / 2);
    body.translate(BODY_LENGTH / 2, 0, 0);
    this.bodyMesh = new THREE.Mesh(body, new THREE.MeshStandardMaterial({ roughness: 0.6, metalness: 0.1 }));
    const nose = new THREE.ConeGeometry(BODY_RADIUS, 5, 24);
    nose.rotateZ(-Math.PI / 2);
    nose.translate(BODY_LENGTH + 2.5, 0, 0);
    this.noseMesh = new THREE.Mesh(nose, new THREE.MeshStandardMaterial({ roughness: 0.6 }));
    const plume = new THREE.ConeGeometry(1.4, 1, 20, 1, true);
    plume.rotateZ(Math.PI / 2);
    plume.translate(-0.5, 0, 0);
    this.plume = new THREE.Mesh(plume, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.75, side: THREE.DoubleSide }));
    this.vehicle.add(this.bodyMesh, this.noseMesh, this.plume);
    this.s.add(this.vehicle);
    // Screen-size marker and a drop line to the ground, so the stage is findable from afar.
    const mg = new THREE.BufferGeometry();
    mg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(3), 3));
    this.marker = new THREE.Points(mg, new THREE.PointsMaterial({ size: 9, sizeAttenuation: false }));
    this.s.add(this.marker);
    const dg = new THREE.BufferGeometry();
    dg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    this.drop = new THREE.Line(dg, new THREE.LineDashedMaterial({ dashSize: 6, gapSize: 6, transparent: true, opacity: 0.6 }));
    this.s.add(this.drop);
    // Touchdown point, when the record states one.
    const td = this.scene.touchdown && this.scene.touchdown.nozzle_position_m;
    if (Array.isArray(td)) {
      const tdg = new THREE.BufferGeometry();
      tdg.setAttribute('position', new THREE.BufferAttribute(new Float32Array([td[0], td[1], 0.1]), 3));
      this.tdMark = new THREE.Points(tdg, new THREE.PointsMaterial({ size: 7, sizeAttenuation: false }));
      this.s.add(this.tdMark);
    }
    this.box = new THREE.Box3().setFromBufferAttribute(tg.getAttribute('position'));
    this.box.expandByPoint(new THREE.Vector3(pad.cx, pad.cy, 0));
    this.applyTheme();
    this.preset('follow', true);
  }

  applyTheme() {
    if (!this.ok) return;
    const truth = hexColour('--truth');
    const dim = hexColour('--truth-dim');
    const fault = hexColour('--fault');
    const n = this.ch.times.length;
    for (let i = 0; i < n; i++) {
      const t = this.ch.times[i];
      const c = this.windows.some(([a, b]) => t >= a && t <= b) ? fault : dim;
      this.trajColours[i * 3] = c.r; this.trajColours[i * 3 + 1] = c.g; this.trajColours[i * 3 + 2] = c.b;
    }
    this.traj.geometry.getAttribute('color').needsUpdate = true;
    this.done.material.color = truth;
    if (this.est) this.est.material.color = hexColour('--est');
    if (this.padDisc) { this.padDisc.material.color = hexColour('--pass'); this.padRing.material.color = hexColour('--pass'); }
    if (this.keepRing) this.keepRing.material.color = hexColour('--unsafe');
    this.bodyMesh.material.color = hexColour('--vehicle');
    this.noseMesh.material.color = hexColour('--vehicle');
    this.plume.material.color = hexColour('--plume');
    this.marker.material.color = hexColour('--accent');
    this.drop.material.color = hexColour('--fg-3');
    if (this.tdMark) this.tdMark.material.color = hexColour('--accent');
    const gridMain = hexColour('--rule-strong');
    const gridSub = hexColour('--rule');
    const mats = Array.isArray(this.grid.material) ? this.grid.material : [this.grid.material];
    this.grid.geometry.dispose();
    this.s.remove(this.grid);
    this.grid = new THREE.GridHelper(2000, 40, gridMain, gridSub);
    this.grid.rotation.x = Math.PI / 2;
    this.s.add(this.grid);
    for (const m of mats) m.dispose();
    this.requestRender();
  }

  preset(mode, initial) {
    if (!this.ok) return;
    this.mode = mode;
    const c = this.box.getCenter(new THREE.Vector3());
    const size = this.box.getSize(new THREE.Vector3());
    const fov = (this.camera.fov * Math.PI) / 180;
    if (mode === 'pad') {
      const r = Math.max(60, (this.pad.keep || 50) * 2.2);
      this.controls.target.set(this.pad.cx, this.pad.cy, 8);
      this.camera.position.set(this.pad.cx + r * 0.6, this.pad.cy - r, r * 0.45);
    } else if (mode === 'side') {
      const d = (size.z / 2 / Math.tan(fov / 2)) * 1.15;
      this.controls.target.copy(c);
      this.camera.position.set(c.x, c.y - d, c.z);
    } else if (mode === 'follow') {
      this.followOffset = new THREE.Vector3(70, -140, 35);
      if (this.cur) this.controls.target.copy(this.cur);
      else this.controls.target.set(c.x, c.y, this.box.max.z);
      this.camera.position.copy(this.controls.target).add(this.followOffset);
    }
    this.camera.near = 0.5;
    this.camera.far = 40000;
    this.camera.updateProjectionMatrix();
    this.controls.update();
    if (!initial) this.requestRender();
  }

  setTime(t) {
    if (!this.ok) return;
    const { ch } = this;
    const times = ch.times;
    if (!times.length) return;
    const i = lowerIndex(times, t);
    const at = (arr) => (arr ? sampleAt(times, arr, t) : null);
    const nx = at(ch.nx); const ny = at(ch.ny); const nz = at(ch.nz);
    const px = at(ch.px); const py = at(ch.py); const pz = at(ch.pz);
    // Attitude: slerp between the two recorded samples (display only).
    const q = new THREE.Quaternion();
    const qa = ch.qw ? new THREE.Quaternion(ch.qx[i], ch.qy[i], ch.qz[i], ch.qw[i]) : new THREE.Quaternion();
    if (ch.qw && i < times.length - 1 && ch.qw[i + 1] !== null) {
      const qb = new THREE.Quaternion(ch.qx[i + 1], ch.qy[i + 1], ch.qz[i + 1], ch.qw[i + 1]);
      const f = (t - times[i]) / (times[i + 1] - times[i] || 1);
      q.slerpQuaternions(qa.normalize(), qb.normalize(), Math.min(1, Math.max(0, f)));
    } else q.copy(qa.normalize());
    if (nx !== null && ny !== null && nz !== null) this.vehicle.position.set(nx, ny, nz);
    this.vehicle.quaternion.copy(q);
    const thr = ch.throttle ? ch.throttle[i] : null;
    const on = ch.engine ? ch.engine[i] === 1 : thr > 0;
    const len = on && thr ? 6 + 22 * thr : 0;
    this.plume.visible = len > 0;
    this.plume.scale.set(len || 1, 1, 1);
    this.cur = new THREE.Vector3(px ?? nx ?? 0, py ?? ny ?? 0, pz ?? nz ?? 0);
    const mp = this.marker.geometry.getAttribute('position');
    mp.setXYZ(0, this.cur.x, this.cur.y, this.cur.z);
    mp.needsUpdate = true;
    const dp = this.drop.geometry.getAttribute('position');
    dp.setXYZ(0, this.cur.x, this.cur.y, this.cur.z);
    dp.setXYZ(1, this.cur.x, this.cur.y, 0);
    dp.needsUpdate = true;
    this.drop.computeLineDistances();
    this.done.geometry.setDrawRange(0, i + 1);
    if (this.mode === 'follow') {
      const delta = this.cur.clone().sub(this.controls.target);
      this.controls.target.add(delta);
      this.camera.position.add(delta);
      this.controls.update();
    }
    this.requestRender();
  }

  requestRender() {
    if (this.pending || !this.ok) return;
    this.pending = requestAnimationFrame(() => {
      this.pending = 0;
      this.renderer.render(this.s, this.camera);
    });
  }

  resize() {
    if (!this.ok) return;
    const w = Math.max(10, this.host.clientWidth);
    const hgt = Math.max(10, this.host.clientHeight);
    this.renderer.setSize(w, hgt, true);
    this.camera.aspect = w / hgt;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  dispose() {
    if (!this.ok) return;
    this.ro.disconnect();
    if (this.pending) cancelAnimationFrame(this.pending);
    this.controls.dispose();
    this.s.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
    });
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }
}

// ---------------------------------------------------------------------------- 2D views

function topView(host, runs, pad, opts = {}) {
  // runs: [{ch, colour, label}]
  let zoom = opts.zoom || 'all';
  const all = () => {
    const xs = [pad.cx - (pad.keep || 10), pad.cx + (pad.keep || 10)];
    const ys = [pad.cy - (pad.keep || 10), pad.cy + (pad.keep || 10)];
    for (const r of runs) { if (r.ch.nx) xs.push(...r.ch.nx); if (r.ch.ny) ys.push(...r.ch.ny); }
    const [x0, x1] = extent([xs.filter((v) => v !== null)], 0.06);
    const [y0, y1] = extent([ys.filter((v) => v !== null)], 0.06);
    return { xmin: x0, xmax: x1, ymin: y0, ymax: y1 };
  };
  const padView = () => {
    const r = (pad.keep || 50) * 1.15;
    return { xmin: pad.cx - r, xmax: pad.cx + r, ymin: pad.cy - r, ymax: pad.cy + r };
  };
  const plot = new Plot2D(host, {
    equal: true,
    label: 'Top view: nozzle-plane track over the pad, with the landing radius and the keep-out ring',
    drawStatic: (ctx, P) => {
      ctx.lineWidth = 1.4;
      if (pad.keep) { ctx.strokeStyle = P.colour('--unsafe'); ctx.setLineDash([6, 4]); circle2d(ctx, P, pad.cx, pad.cy, pad.keep); ctx.setLineDash([]); }
      if (pad.land) {
        ctx.fillStyle = P.colour('--pass-wash');
        ctx.beginPath(); ctx.arc(P.x(pad.cx), P.y(pad.cy), pad.land * P.scale, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = P.colour('--pass'); circle2d(ctx, P, pad.cx, pad.cy, pad.land);
      }
      ctx.font = `11px ${P.colour('--sans')}`;
      ctx.fillStyle = P.colour('--fg-2');
      ctx.textAlign = 'left';
      if (pad.land) ctx.fillText(`R5 ${num(pad.land)} m`, P.x(pad.cx + pad.land * 0.72) + 3, P.y(pad.cy + pad.land * 0.72) - 3);
      if (pad.keep) ctx.fillText(`S2 ${num(pad.keep)} m`, P.x(pad.cx + pad.keep * 0.72) + 3, P.y(pad.cy + pad.keep * 0.72) - 3);
      for (const r of runs) {
        if (r.ch.ex && r.ch.ey && r.showEst) {
          ctx.strokeStyle = r.estColour || P.colour('--est'); ctx.lineWidth = 1.3; ctx.setLineDash([5, 4]);
          polyline(ctx, P, r.ch.ex, r.ch.ey); ctx.setLineDash([]);
        }
        if (r.ch.nx && r.ch.ny) {
          ctx.strokeStyle = r.colour || P.colour('--truth-dim'); ctx.lineWidth = 1.8; ctx.setLineDash(r.dash || []);
          polyline(ctx, P, r.ch.nx, r.ch.ny); ctx.setLineDash([]);
          const n = r.ch.nx.length - 1;
          ctx.fillStyle = r.colour || P.colour('--truth');
          ctx.beginPath(); ctx.arc(P.x(r.ch.nx[n]), P.y(r.ch.ny[n]), 3.5, 0, Math.PI * 2); ctx.fill();
        }
      }
    },
    drawDynamic: (ctx, P, t) => {
      for (const r of runs) {
        if (!r.ch.nx) continue;
        const x = sampleAt(r.ch.times, r.ch.nx, t);
        const y = sampleAt(r.ch.times, r.ch.ny, t);
        if (x === null || y === null) continue;
        if (!r.colour) {
          const i = lowerIndex(r.ch.times, t);
          ctx.strokeStyle = P.colour('--truth'); ctx.lineWidth = 2;
          polyline(ctx, P, [...r.ch.nx.slice(0, i + 1), x], [...r.ch.ny.slice(0, i + 1), y]);
        }
        ctx.fillStyle = r.colour || P.colour('--accent');
        ctx.beginPath(); ctx.arc(P.x(x), P.y(y), 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = P.colour('--bg-0'); ctx.lineWidth = 1.5; ctx.stroke();
      }
    },
  });
  plot.setView(zoom === 'pad' ? padView() : all());
  return {
    plot,
    setZoom: (z) => { zoom = z; plot.setView(zoom === 'pad' ? padView() : all()); },
  };
}

function profileView(host, runs, pad) {
  const plot = new Plot2D(host, {
    equal: false,
    label: 'Profile: altitude against horizontal distance from the pad centre',
    drawStatic: (ctx, P) => {
      ctx.lineWidth = 1.2;
      if (pad.land) { ctx.strokeStyle = P.colour('--pass'); ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(P.x(pad.land), P.y(P.ymin)); ctx.lineTo(P.x(pad.land), P.y(P.ymax)); ctx.stroke(); }
      if (pad.keep && pad.keep < P.xmax) { ctx.strokeStyle = P.colour('--unsafe'); ctx.setLineDash([6, 4]); ctx.beginPath(); ctx.moveTo(P.x(pad.keep), P.y(P.ymin)); ctx.lineTo(P.x(pad.keep), P.y(P.ymax)); ctx.stroke(); }
      ctx.setLineDash([]);
      for (const r of runs) {
        if (!r.ch.padDist || !r.ch.nz) continue;
        ctx.strokeStyle = r.colour || P.colour('--truth-dim'); ctx.lineWidth = 1.8; ctx.setLineDash(r.dash || []);
        polyline(ctx, P, r.ch.padDist, r.ch.nz); ctx.setLineDash([]);
      }
    },
    drawDynamic: (ctx, P, t) => {
      for (const r of runs) {
        if (!r.ch.padDist || !r.ch.nz) continue;
        const x = sampleAt(r.ch.times, r.ch.padDist, t);
        const y = sampleAt(r.ch.times, r.ch.nz, t);
        if (x === null || y === null) continue;
        if (!r.colour) {
          const i = lowerIndex(r.ch.times, t);
          ctx.strokeStyle = P.colour('--truth'); ctx.lineWidth = 2;
          polyline(ctx, P, [...r.ch.padDist.slice(0, i + 1), x], [...r.ch.nz.slice(0, i + 1), y]);
        }
        ctx.fillStyle = r.colour || P.colour('--accent');
        ctx.beginPath(); ctx.arc(P.x(x), P.y(y), 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = P.colour('--bg-0'); ctx.lineWidth = 1.5; ctx.stroke();
      }
    },
  });
  const xs = [0, pad.land || 0];
  const ys = [0];
  for (const r of runs) { if (r.ch.padDist) xs.push(...r.ch.padDist); if (r.ch.nz) ys.push(...r.ch.nz); }
  const [, x1] = extent([xs.filter((v) => v !== null)], 0.05);
  const [, y1] = extent([ys.filter((v) => v !== null)], 0.04);
  plot.setView({ xmin: 0, xmax: x1, ymin: 0, ymax: y1 });
  return { plot };
}

// ---------------------------------------------------------------------------- mount

function seg(label, options, current, onPick) {
  const el = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': label });
  for (const [v, text] of options) {
    el.append(h('button', {
      type: 'button', class: 'seg-btn', role: 'radio', 'aria-checked': String(v === current), dataset: { v },
      onclick: (e) => {
        for (const b of el.children) b.setAttribute('aria-checked', String(b === e.currentTarget));
        onPick(v);
      },
    }, text));
  }
  return el;
}

function mount(host, model, cursor) {
  clear(host);
  const ch = channelsOf(model);
  const scene = model.record.scene;
  const pad = padOf(scene);
  const hasEst = Boolean(ch.ex && ch.ey && ch.ez);
  let view = host.clientWidth < 620 ? '3d' : 'split';
  const readout = h('div', { class: 'scene-readout mono overlay', 'aria-live': 'off' });
  const v3 = h('div', { class: 'r3d' });
  const vTop = h('div', { class: 'r2d' });
  const vProf = h('div', { class: 'r2d' });
  const panes = h('div', { class: ['rocket-panes', `view-${view}`] },
    h('figure', { class: 'pane-3d' }, v3, readout),
    h('div', { class: 'pane-2d' },
      h('figure', { class: 'pane-top' }, h('figcaption', null, h('b', null, 'Top view'), 'east and north of the nozzle plane, m'), vTop),
      h('figure', { class: 'pane-prof' }, h('figcaption', null, h('b', null, 'Profile'), 'altitude against distance from the pad, m'), vProf)));
  const camSeg = seg('Camera preset', [['follow', 'Follow'], ['pad', 'Pad'], ['side', 'Side']], 'follow', (m) => r3.preset(m));
  const viewSeg = seg('Scene layout', [['split', '3D + plots'], ['3d', '3D'], ['top', 'Top'], ['prof', 'Profile']], view, (v) => {
    view = v;
    panes.className = `rocket-panes view-${v}`;
    camSeg.hidden = v === 'top' || v === 'prof';
  });
  const zoomSeg = seg('Top view extent', [['all', 'Track'], ['pad', 'Pad']], 'all', (z) => top.setZoom(z));
  const bar = h('div', { class: 'scene-bar' }, h('h2', { class: 'pane-title' }, 'Scene'), h('span', { class: 'dim small' }, 'pad frame, x east, y north, z up, m'), h('div', { class: 'spacer' }), viewSeg, camSeg, zoomSeg);
  const legendItems = h('ul', { class: 'scene-legend' },
    h('li', null, h('span', { class: 'lg lg-truth' }), 'true trajectory'),
    hasEst ? h('li', null, h('span', { class: 'lg lg-est' }), 'navigation estimate') : null,
    (model.record.request.faults || []).length ? h('li', null, h('span', { class: 'lg lg-fault' }), 'injected fault window') : null,
    h('li', null, h('span', { class: 'lg lg-goal' }), pad.land ? `R5 landing radius ${num(pad.land)} m` : 'pad'),
    pad.keep ? h('li', null, h('span', { class: 'lg lg-zone' }), `S2 keep-out ${num(pad.keep)} m`) : null,
    h('li', { title: `The model has no vehicle length; the ${BODY_LENGTH} m body is drawn for orientation. The plume points along the body axis with a length from the applied throttle; the gimbal deflection is not drawn. Position and attitude are interpolated between the 0.1 s samples for display only.` }, h('span', { class: 'lg lg-veh' }), 'stage: illustration (no length in the model), interpolated between samples for display; plume from applied throttle, gimbal not drawn'));
  const legend = h('details', { class: 'scene-key', open: host.clientHeight > 380 },
    h('summary', null, h('span', { class: 'key-text' }, h('span', { class: 'lg lg-truth' }), 'true trajectory, pad R5 and S2; stage is an illustration, interpolated between samples for display')),
    legendItems);
  host.append(bar, panes, h('div', { class: 'scene-foot' }, legend));
  const r3 = new Rocket3D(v3, model, ch);
  const top = topView(vTop, [{ ch, showEst: hasEst }], pad);
  const prof = profileView(vProf, [{ ch }], pad);
  const engineText = ['off', 'on', 'cut', 'flameout'];
  const unsub = cursor.subscribe((t) => {
    r3.setTime(t);
    top.plot.drawTop(t);
    prof.plot.drawTop(t);
    const i = lowerIndex(ch.times, t);
    if (i < 0) return;
    const v = (a, d = 4) => (a && a[i] !== null && a[i] !== undefined ? num(a[i], d) : 'n/a');
    readout.replaceChildren(
      h('span', null, `sample ${timeText(ch.times[i], 's')}`), h('span', null, `alt ${v(ch.nz, 5)} m`), h('span', null, `vz ${v(ch.vz)} m/s`), h('span', null, `vh ${v(ch.vh)} m/s`),
      h('span', null, `tilt ${v(ch.tilt, 3)}°`), h('span', null, `throttle ${v(ch.throttle, 3)}`), h('span', null, `engine ${ch.engine && ch.engine[i] !== null ? engineText[ch.engine[i]] || ch.engine[i] : 'n/a'}`), h('span', null, `pad ${v(ch.padDist)} m`));
  });
  r3.setTime(cursor.t);
  top.plot.drawTop(cursor.t);
  prof.plot.drawTop(cursor.t);
  return {
    dispose: () => { unsub(); r3.dispose(); top.plot.dispose(); prof.plot.dispose(); },
    redraw: () => { r3.applyTheme(); top.plot.redraw(); prof.plot.redraw(); },
  };
}

function compare(host, models, colours, labels, cursor) {
  clear(host);
  const runs = models.map((m, i) => ({ ch: channelsOf(m), colour: colours[i], dash: runDash(i), label: labels[i] }));
  const pad = padOf(models[0].record.scene);
  const vTop = h('div', { class: 'r2d' });
  const vProf = h('div', { class: 'r2d' });
  const zoomSeg = seg('Top view extent', [['all', 'Track'], ['pad', 'Pad']], 'all', (z) => top.setZoom(z));
  host.append(
    h('div', { class: 'scene-bar' }, h('h3', null, 'Trajectories'), h('span', { class: 'dim small' }, 'nozzle plane, pad frame, m; dot at the cursor'), h('div', { class: 'spacer' }), zoomSeg),
    h('div', { class: 'cmp-scene-panes' },
      h('figure', { class: 'pane-top' }, h('figcaption', null, h('b', null, 'Top view'), 'east and north, m'), vTop),
      h('figure', { class: 'pane-prof' }, h('figcaption', null, h('b', null, 'Profile'), 'altitude against distance from the pad, m'), vProf)));
  const top = topView(vTop, runs, pad);
  const prof = profileView(vProf, runs, pad);
  const unsub = cursor ? cursor.subscribe((t) => { top.plot.drawTop(t); prof.plot.drawTop(t); }) : () => {};
  return { dispose: () => { unsub(); top.plot.dispose(); prof.plot.dispose(); } };
}

export const rocket3d = { title: 'Powered landing, 3D', mount, compare };
