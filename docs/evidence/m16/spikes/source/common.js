// Shared spike helpers: pack + record loading, ENU sampling, benchmark loop.
export async function loadPack() {
  const m = await (await fetch('pack/environment.json')).json();
  const buf = await (await fetch('pack/height.u16')).arrayBuffer();
  const q = new Uint16Array(buf);
  const h = m.height;
  const up = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) up[i] = q[i] * h.scale_m + h.offset_m;
  return { m, up, cols: h.columns, rows: h.rows, s: h.spacing_m, x0: h.first_node_m[0], y0: h.first_node_m[1] };
}

export function heightAt(p, e, n) {
  const fx = (e - p.x0) / p.s;
  const fy = (p.y0 - n) / p.s;
  const c = Math.max(0, Math.min(p.cols - 2, Math.floor(fx)));
  const r = Math.max(0, Math.min(p.rows - 2, Math.floor(fy)));
  const tx = Math.min(1, Math.max(0, fx - c));
  const ty = Math.min(1, Math.max(0, fy - r));
  const a = p.up[r * p.cols + c], b = p.up[r * p.cols + c + 1], d = p.up[(r + 1) * p.cols + c], g = p.up[(r + 1) * p.cols + c + 1];
  return a * (1 - tx) * (1 - ty) + b * tx * (1 - ty) + d * (1 - tx) * ty + g * tx * ty;
}

export async function loadRun() {
  const r = await (await fetch('data/nominal.json')).json();
  const by = new Map(r.channels.map((c) => [c.id, c.values]));
  const t = r.timebases[r.channels[0].timebase];
  return { t, px: by.get('pos_x'), py: by.get('pos_y'), pz: by.get('pos_z'), qw: by.get('q_w'), qx: by.get('q_x'), qy: by.get('q_y'), qz: by.get('q_z') };
}

export function at(run, arr, time) {
  const t = run.t;
  let i = 0;
  while (i + 1 < t.length && t[i + 1] <= time) i++;
  if (i + 1 >= t.length) return arr[t.length - 1];
  const f = (time - t[i]) / (t[i + 1] - t[i]);
  return arr[i] + (arr[i + 1] - arr[i]) * f;
}

/** Runs `frame(simTime)` on every animation frame for `seconds`, then stores timings. */
export function bench(t0Load, frame, run, seconds = 10) {
  const firstFrame = performance.now() - t0Load;
  const iv = [];
  let last = 0;
  const start = performance.now();
  const span = run.t[run.t.length - 1] - run.t[0];
  function loop(now) {
    if (last) iv.push(now - last);
    last = now;
    const k = (now - start) / (seconds * 1000);
    frame(run.t[0] + Math.min(1, k) * span);
    if (k < 1) requestAnimationFrame(loop);
    else {
      const s = [...iv].sort((a, b) => a - b);
      const q = (p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
      window.__bench = { first_frame_ms: Math.round(firstFrame), frames: iv.length, mean_ms: +(iv.reduce((a, b) => a + b, 0) / iv.length).toFixed(2), p50_ms: +q(0.5).toFixed(2), p95_ms: +q(0.95).toFixed(2), p99_ms: +q(0.99).toFixed(2), max_ms: +s[s.length - 1].toFixed(2), over_33ms: iv.filter((x) => x > 33.4).length, heap_mb: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null };
    }
  }
  requestAnimationFrame(loop);
}
