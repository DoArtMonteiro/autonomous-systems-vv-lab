// Geographic environments (M16), as the interface sees them. The shell validates every pack (sizes,
// SHA-256, grid, attributed sources and the pack's own geodetic check points) before it lists it,
// and re-hashes each file it hands over. Nothing here touches the network: bytes arrive over IPC.
// What is cached: the listing, the decoded height grid and the image blob of a pack (CPU memory,
// about 2 MB each), and placed tracks per run. GPU resources belong to the scene that uses them
// and are released when it is disposed.

import { api, logUiError } from './api.js';

let listing = null; // Promise of {environments, rejected, imported_dir, network}
const packs = new Map(); // id -> Promise of pack
const tracks = new Map(); // `${id}|${runId}` -> Promise of track

export function listEnvironments(reload = false) {
  if (!listing || reload) {
    listing = api.listEnvironments().catch((e) => {
      listing = null;
      throw e;
    });
  }
  return listing;
}

export function forgetEnvironments() {
  listing = null;
  packs.clear();
  tracks.clear();
}

function bytesOf(b) {
  if (b instanceof ArrayBuffer) return b;
  if (ArrayBuffer.isView(b)) return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
  return new Uint8Array(b).buffer;
}

/** Decoded pack: manifest facts, ENU up heights (Float32Array) and the image as a Blob. */
export function loadPack(id) {
  if (!packs.has(id)) {
    const p = (async () => {
      const list = await listEnvironments();
      const m = list.environments.find((e) => e.id === id);
      if (!m) throw { kind: 'invalid', message: `The environment “${id}” is not installed or did not validate.` };
      const [hb, ib] = await Promise.all([api.environmentFile(id, 'height.u16'), api.environmentFile(id, 'image.jpg')]);
      const h = m.height;
      const raw = new Uint16Array(bytesOf(hb));
      if (raw.length !== h.columns * h.rows) throw { kind: 'invalid', message: 'The height grid does not have the declared size.' };
      const up = new Float32Array(raw.length);
      for (let i = 0; i < raw.length; i++) up[i] = raw[i] * h.scale_m + h.offset_m;
      const image = new Blob([bytesOf(ib)], { type: 'image/jpeg' });
      return { id, m, up, cols: h.columns, rows: h.rows, s: h.spacing_m, x0: h.first_node_m[0], y0: h.first_node_m[1], image };
    })();
    p.catch((e) => { packs.delete(id); logUiError(`environment ${id}: ${e && e.message ? e.message : JSON.stringify(e)}`); });
    packs.set(id, p);
  }
  return packs.get(id);
}

/** ENU up of the terrain at (east, north) on the drawn triangles (as vv-geo); null outside. */
export function terrainAt(p, e, n) {
  const fx = (e - p.x0) / p.s;
  const fy = (p.y0 - n) / p.s;
  if (!(fx >= 0 && fy >= 0 && fx <= p.cols - 1 && fy <= p.rows - 1)) return null;
  const c = Math.min(p.cols - 2, Math.floor(fx));
  const r = Math.min(p.rows - 2, Math.floor(fy));
  const tx = fx - c;
  const ty = fy - r;
  const at = (rr, cc) => p.up[rr * p.cols + cc];
  const a = at(r, c); const b = at(r, c + 1); const d = at(r + 1, c); const g = at(r + 1, c + 1);
  // The mesh splits each cell into (a, d, b) and (b, d, g); interpolate on the same triangles.
  return tx + ty <= 1 ? a + (b - a) * tx + (d - a) * ty : g + (d - g) * (1 - tx) + (b - g) * (1 - ty);
}

/** The run placed on the pack by the shell's georeference layer (vv-geo), cached. */
export function trackOf(id, runId) {
  const k = `${id}|${runId}`;
  if (!tracks.has(k)) {
    const p = api.geoTrack(id, runId);
    p.catch(() => tracks.delete(k));
    tracks.set(k, p);
  }
  return tracks.get(k);
}

/** The attribution lines a pack requires, for the scene credit. */
export function creditOf(m) {
  return (m.sources || []).map((s) => s.attribution).filter(Boolean);
}

/** Size in MB with one decimal. */
export function mb(bytes) {
  return `${(bytes / 1048576).toFixed(1)} MB`;
}
