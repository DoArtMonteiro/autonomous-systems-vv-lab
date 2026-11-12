// Mission view of the powered landing: the Rocket3D scene with a calmer, cinematic presentation for
// the mission player. It draws exactly what Rocket3D draws (true trajectory, navigation estimate,
// pad R5 and keep-out S2, the stage at the cursor from the recorded true state and applied throttle)
// plus the true trajectories of the other runs of the same mission as reference lines. The ground
// disc and range rings are a backdrop for scale, not model data. The stage (stage-model.js) is an
// illustration: the model has no vehicle length, gear or fins. Position and attitude are interpolated
// between the 0.1 s samples for display only.

import * as THREE from '../../vendor/three/three.module.min.js';
import { Rocket3D, channelsOf, circlePoints, hexColour } from './rocket.js';
import { lowerIndex, sampleAt } from '../dom.js';
import { buildStage } from './stage-model.js';

const RINGS_M = [25, 50, 100, 250, 500, 1000, 2000];

function cssColour(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function groundTexture(inner, outer) {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(256, 256, 0, 256, 256, 256);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.55, outer);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 512, 512);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class CinemaRocket extends Rocket3D {
  lights(s) {
    s.add(new THREE.HemisphereLight(0xd6dee8, 0x0a0d12, 1.5));
    const key = new THREE.DirectionalLight(0xffffff, 2.6);
    key.position.set(-700, -900, 1500);
    s.add(key);
    const rim = new THREE.DirectionalLight(0xa9c8ff, 1.1);
    rim.position.set(800, 900, 250);
    s.add(rim);
  }

  build() {
    super.build();
    const s = this.s;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    // Backdrop: a softly lit ground disc and range rings around the pad (scale only).
    this.groundDisc = new THREE.Mesh(new THREE.CircleGeometry(6000, 96), new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
    this.groundDisc.position.set(this.pad.cx, this.pad.cy, -0.2);
    s.add(this.groundDisc);
    this.rings = RINGS_M.map((r) => {
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(circlePoints(this.pad.cx, this.pad.cy, r, 160)), new THREE.LineBasicMaterial({ transparent: true }));
      s.add(l);
      return l;
    });
    const spokes = [];
    for (let k = 0; k < 4; k++) {
      const a = (k * Math.PI) / 2;
      spokes.push(new THREE.Vector3(this.pad.cx + 25 * Math.cos(a), this.pad.cy + 25 * Math.sin(a), 0.03), new THREE.Vector3(this.pad.cx + 2000 * Math.cos(a), this.pad.cy + 2000 * Math.sin(a), 0.03));
    }
    this.spokes = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(spokes), new THREE.LineBasicMaterial({ transparent: true }));
    s.add(this.spokes);
    const m = 3;
    this.cross = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(this.pad.cx - m, this.pad.cy, 0.06), new THREE.Vector3(this.pad.cx + m, this.pad.cy, 0.06),
      new THREE.Vector3(this.pad.cx, this.pad.cy - m, 0.06), new THREE.Vector3(this.pad.cx, this.pad.cy + m, 0.06)]), new THREE.LineBasicMaterial());
    s.add(this.cross);
    // A darker band on the body and a glow around the plume (illustration).
    const band = new THREE.CylinderGeometry(1.9, 1.9, 1.4, 24);
    band.rotateZ(-Math.PI / 2);
    band.translate(31, 0, 0);
    this.band = new THREE.Mesh(band, new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0.3 }));
    this.vehicle.add(this.band);
    const glow = new THREE.ConeGeometry(2.6, 1, 20, 1, true);
    glow.rotateZ(Math.PI / 2);
    glow.translate(-0.5, 0, 0);
    this.glow = new THREE.Mesh(glow, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    this.vehicle.add(this.glow);
    // The illustrative stage replaces the plain body; the plain meshes stay for the theme code.
    this.envRT = this.environmentMap();
    this.stage = buildStage(this.envRT ? this.envRT.texture : null);
    for (const o of [this.bodyMesh, this.noseMesh, this.band, this.plume, this.glow]) o.visible = false;
    this.vehicle.add(this.stage.group);
    // Reference runs: their true centre-of-mass trajectories and a marker at the cursor.
    this.ghosts = (this.opts.ghosts || []).map((g) => {
      const n = g.ch.times.length;
      const pts = [];
      for (let i = 0; i < n; i++) if (g.ch.px && g.ch.px[i] !== null) pts.push(new THREE.Vector3(g.ch.px[i], g.ch.py[i], g.ch.pz[i]));
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: new THREE.Color(g.colour), transparent: true, opacity: 0.75 }));
      const mg = new THREE.BufferGeometry();
      mg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(3), 3));
      const marker = new THREE.Points(mg, new THREE.PointsMaterial({ color: new THREE.Color(g.colour), size: 8, sizeAttenuation: false }));
      s.add(line, marker);
      return { ...g, line, marker };
    });
    this.applyTheme();
    this.preset(this.opts.preset || 'follow', true);
  }

  /** A prefiltered environment for the stage's paint and metal: a soft studio gradient here. */
  environmentMap() {
    const pm = new THREE.PMREMGenerator(this.renderer);
    const env = new THREE.Scene();
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      vertexShader: 'varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'varying vec3 vDir; void main() { float h = vDir.z; vec3 c = mix(vec3(0.10, 0.11, 0.13), vec3(0.78, 0.84, 0.92), smoothstep(-0.2, 0.9, h)); gl_FragColor = vec4(c, 1.0); }',
    });
    env.add(new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16), mat));
    const rt = pm.fromScene(env, 0.02);
    env.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    pm.dispose();
    return rt;
  }

  applyTheme() {
    super.applyTheme();
    if (!this.groundDisc) return;
    this.grid.visible = false;
    this.s.fog = new THREE.FogExp2(hexColour('--bg-0'), 0.00016);
    if (this.groundDisc.material.map) this.groundDisc.material.map.dispose();
    this.groundDisc.material.map = groundTexture(cssColour('--scene-ground-in', '#1b232d'), cssColour('--scene-ground-out', '#0d1117'));
    this.groundDisc.material.needsUpdate = true;
    const ring = hexColour('--rule-strong');
    for (const r of this.rings) { r.material.color = ring; r.material.opacity = 0.55; }
    this.spokes.material.color = ring;
    this.spokes.material.opacity = 0.35;
    this.cross.material.color = hexColour('--fg-2');
    this.band.material.color = hexColour('--vehicle-band');
    this.glow.material.color = hexColour('--plume');
    this.requestRender();
  }

  preset(mode, initial) {
    if (!this.ok) return;
    if (mode === 'pad') {
      // A long-lens camera standing beside the pad that keeps the stage in frame.
      this.mode = 'pad';
      this.camera.position.set(this.pad.cx + 110, this.pad.cy - 190, 4);
      this.track();
      if (!initial) this.requestRender();
      return;
    }
    this.camera.fov = 40;
    if (mode === 'wide') {
      super.preset('side', initial);
      this.mode = 'wide';
      return;
    }
    super.preset(mode, initial);
    if (mode === 'follow') {
      this.followOffset = new THREE.Vector3(48, -112, 18);
      this.camera.position.copy(this.controls.target).add(this.followOffset);
      this.controls.update();
    }
  }

  dispose() {
    if (!this.ok) return;
    if (this.stage) for (const m of this.stage.materials) for (const k of ['map', 'alphaMap']) if (m[k]) m[k].dispose();
    if (this.envRT) this.envRT.dispose();
    if (this.groundDisc && this.groundDisc.material && this.groundDisc.material.map) this.groundDisc.material.map.dispose();
    super.dispose();
  }

  track() {
    const target = this.cur ? this.cur.clone() : new THREE.Vector3(this.pad.cx, this.pad.cy, 70);
    target.z = Math.max(target.z, 8);
    this.controls.target.copy(target);
    const d = this.camera.position.distanceTo(target);
    this.camera.fov = Math.min(40, Math.max(2.5, (2 * Math.atan(55 / d) * 180) / Math.PI));
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  setTime(t) {
    super.setTime(t);
    if (!this.ok || !this.glow) return;
    if (this.mode === 'pad') this.track();
    this.glow.visible = false;
    this.plume.visible = false;
    this.stage.setThrottle(this.plumeLength || 0);
    for (const g of this.ghosts) {
      const at = (a) => (a ? sampleAt(g.ch.times, a, t) : null);
      const x = at(g.ch.px); const y = at(g.ch.py); const z = at(g.ch.pz);
      g.marker.visible = x !== null && y !== null && z !== null;
      if (g.marker.visible) {
        const p = g.marker.geometry.getAttribute('position');
        p.setXYZ(0, x, y, z);
        p.needsUpdate = true;
      }
    }
  }
}

/**
 * Mounts the mission view of run `active` among `models`; the others are reference lines in
 * `colours[i]`. Returns {ok, dispose, redraw, preset(mode), mode}.
 */
export function mountCinema(host, models, active, cursor, colours) {
  const model = models[active];
  const ch = channelsOf(model);
  const ghosts = models.map((m, i) => (i === active ? null : { ch: channelsOf(m), colour: colours[i] })).filter(Boolean);
  const r3 = new CinemaRocket(host, model, ch, { ghosts, preset: 'follow' });
  const unsub = cursor.subscribe((t) => r3.setTime(t));
  r3.setTime(cursor.t);
  return {
    ok: r3.ok,
    dispose: () => { unsub(); r3.dispose(); },
    redraw: () => { r3.applyTheme(); r3.setTime(cursor.t); },
    preset: (m) => r3.preset(m),
    get mode() { return r3.mode; },
    index: (t) => lowerIndex(ch.times, t),
  };
}
