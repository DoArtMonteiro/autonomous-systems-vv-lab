// Scene renderers keyed by record.scene.kind. A record whose kind is "none" or unknown simply has no
// scene; every other view of the run still works. A renderer is
//   { title, mount(host, model, cursor, ctx) -> {dispose(), resize?()},
//     compare?(host, models, colours, labels, cursor) -> {dispose()} }
// and must draw only what the record contains (interpolation between samples is display only and
// must be stated in its legend).

import { rocket3d } from './rocket.js';
import { ground2d } from './ground.js';
import { ascent } from './ascent.js';

const registry = new Map([
  ['rocket-3d', rocket3d],
  ['ground-2d', ground2d],
  ['ascent', ascent],
]);

export function sceneFor(record) {
  const kind = record && record.scene && typeof record.scene.kind === 'string' ? record.scene.kind : 'none';
  return registry.get(kind) || null;
}

export function sceneKind(record) {
  return record && record.scene && typeof record.scene.kind === 'string' ? record.scene.kind : 'none';
}
