// Static source checks for the expert walkthrough (docs/usability/expert-walkthrough.md).
// Reads only files under desktop/studio/ui and prints results. It launches nothing, writes nothing and
// never touches the installed application or its data folders. Run from the repository root:
//   node docs/evidence/m19/usability/static_checks.mjs
// These are pattern checks over source text and CSS tokens. They are not an accessibility audit:
// assistive technology, contrast over images and the rendered page are out of scope.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const UI = 'desktop/studio/ui';
const read = (p) => readFileSync(join(UI, p), 'utf8');
const files = (dir, ext) => readdirSync(join(UI, dir), { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? files(join(dir, e.name), ext) : e.name.endsWith(ext) ? [join(dir, e.name)] : []));
const base = (f) => f.split(/[\\/]/).pop();

// ------------------------------------------------------------------ 1. contrast from the CSS tokens

function parseColour(v) {
  v = v.trim();
  let m = /^#([0-9a-f]{6})$/i.exec(v);
  if (m) { const n = parseInt(m[1], 16); return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 }; }
  m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+))?\s*\)$/i.exec(v);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  return null;
}
const over = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const tokens = read('css/tokens.css');
function block(selectorRe) {
  const out = {};
  for (const m of tokens.matchAll(selectorRe)) {
    for (const d of m[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim();
  }
  return out;
}
const rootBlocks = block(/:root(?:,\s*:root\[data-theme="dark"\])?\s*\{([^}]*)\}/g);
const darkOnly = block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/g);
const lightOnly = block(/:root\[data-theme="light"\]\s*\{([^}]*)\}/g);
const themes = { dark: { ...rootBlocks, ...darkOnly }, light: { ...rootBlocks, ...darkOnly, ...lightOnly } };
const col = (theme, name) => { const c = parseColour(themes[theme][name] || ''); if (!c) throw new Error(`no colour for ${theme} ${name}`); return c; };

const text = [];
const surf = (n) => (t) => col(t, n);
const wash = (n, bg) => (t) => over(col(t, n), col(t, bg));
for (const bg of ['--bg-0', '--bg-1', '--bg-2', '--bg-3']) {
  for (const fg of ['--fg-1', '--fg-2', '--fg-3']) text.push([fg, bg, surf(bg), 4.5, 'body and small text']);
}
for (const bg of ['--bg-0', '--bg-1', '--bg-2']) {
  text.push(['--accent', bg, surf(bg), 4.5, 'links and focus text']);
  for (const fg of ['--pass', '--fail', '--unsafe', '--neutral', '--fault']) text.push([fg, bg, surf(bg), 4.5, 'status text']);
  text.push(['--grade-explore', bg, surf(bg), 4.5, 'grade chip text']);
  for (const fg of ['--prov-sim', '--prov-ctx', '--prov-ill']) text.push([fg, bg, surf(bg), 4.5, 'provenance labels']);
}
for (const [fg, w] of [['--pass', '--pass-wash'], ['--fail', '--fail-wash'], ['--unsafe', '--unsafe-wash'], ['--neutral', '--neutral-wash'], ['--fault', '--fault-wash'], ['--accent', '--accent-wash']]) {
  for (const bg of ['--bg-1', '--bg-0']) text.push([fg, `${w} over ${bg}`, wash(w, bg), 4.5, 'verdict chips and badges']);
}
text.push(['--grade-explore', 'grade-explore 10% over --bg-1', (t) => over({ ...col(t, '--grade-explore'), a: 0.10 }, col(t, '--bg-1')), 4.5, 'grade-explore chip']);
text.push(['--fg-2', '--bg-3 (chip key label)', surf('--bg-3'), 4.5, '.vchip-k']);
text.push(['--accent-ink', '--accent (primary button)', (t) => col(t, '--accent'), 4.5, 'primary button label']);
const graphic = [];
for (const bg of ['--bg-0', '--bg-1']) {
  for (const fg of ['--obs', '--est', '--truth', '--limit', '--plume', '--fault', '--rule-strong']) graphic.push([fg, bg, surf(bg), 3, 'chart and scene lines, borders (non-text, 3:1)']);
}

const fmt = (x) => x.toFixed(2);
const lines = [];
const fails = { dark: [], light: [] };
lines.push('1. Contrast (WCAG 2.x relative luminance), from desktop/studio/ui/css/tokens.css, washes composited over the stated surface');
lines.push('   Thresholds: 4.5:1 for text (the interface sets most text at 12 px, so the large-text 3:1 rule is not applied), 3:1 for non-text marks.');
for (const theme of ['dark', 'light']) {
  lines.push(`   Theme ${theme}:`);
  for (const [fg, bgName, bg, min, use] of [...text, ...graphic]) {
    const r = ratio(col(theme, fg), bg(theme));
    if (r < min) fails[theme].push(`${fg} on ${bgName} = ${fmt(r)} (< ${min}), ${use}`);
  }
  lines.push(`     pairs checked: ${text.length + graphic.length}; below threshold: ${fails[theme].length}`);
  for (const f of fails[theme]) lines.push(`       FAIL ${f}`);
}
lines.push('   Reference values:');
const q = (theme, fg, bgName, bg) => `${theme}: ${fg} on ${bgName} = ${fmt(ratio(col(theme, fg), bg(theme)))}`;
for (const t of ['dark', 'light']) {
  lines.push(`     ${q(t, '--fg-3', '--bg-1', surf('--bg-1'))}`);
  lines.push(`     ${q(t, '--fg-3', '--bg-3', surf('--bg-3'))}`);
  lines.push(`     ${q(t, '--pass', '--pass-wash over --bg-1', wash('--pass-wash', '--bg-1'))}`);
  lines.push(`     ${q(t, '--fail', '--fail-wash over --bg-1', wash('--fail-wash', '--bg-1'))}`);
  lines.push(`     ${q(t, '--unsafe', '--unsafe-wash over --bg-1', wash('--unsafe-wash', '--bg-1'))}`);
  lines.push(`     ${q(t, '--neutral', '--neutral-wash over --bg-1', wash('--neutral-wash', '--bg-1'))}`);
  lines.push(`     ${q(t, '--grade-explore', '--bg-1', surf('--bg-1'))}`);
  lines.push(`     ${t}: --pass against --fail, as the two adjacent hues of a chip pair = ${fmt(ratio(col(t, '--pass'), col(t, '--fail')))} (luminance ratio; low means the hues differ by hue, not by lightness)`);
}
lines.push('   Not computable from tokens: text over --hud or --glass on the 3D scene, geospatial imagery and the Cinematic View (depends on the picture behind).');

// ------------------------------------------------------------------ 2. markup and keyboard patterns

const js = files('js', '.js');
const src = Object.fromEntries(js.map((f) => [f, read(f)]));
const all = Object.values(src).join('\n');
const count = (re, s = all) => (s.match(re) || []).length;
const html = read('index.html');
lines.push('');
lines.push('2. Markup and keyboard patterns in desktop/studio/ui/js (pattern counts over source text, not a rendered-DOM audit)');
lines.push(`   html lang attribute: ${/<html lang="en"/.test(html) ? 'lang="en" present' : 'MISSING'}`);
lines.push(`   skip link to main: ${/class="skip" href="#view"/.test(html) ? 'present' : 'MISSING'}; main has tabindex=-1: ${/<main id="view" tabindex="-1">/.test(html)}`);
lines.push(`   positive tabindex values: ${count(/tabindex['"]?\s*:\s*['"]?[1-9]/g)}`);
lines.push(`   <img> elements created in JS: ${count(/h\('img'/g)}; all with alt="" (decorative): ${count(/h\('img',\s*\{[^}]*alt:\s*''/g) === count(/h\('img'/g)}`);
lines.push(`   role="radio" buttons: ${count(/role:\s*'radio'/g)}; aria-checked writes: ${count(/aria-checked/g)}`);
lines.push(`   role="tab": ${count(/role:\s*'tab'/g)}; aria-selected writes: ${count(/aria-selected/g)}`);
lines.push(`   aria-live regions: ${count(/aria-live/g)}; role="alert": ${count(/role:\s*'alert'/g)}; role="status": ${count(/role:\s*'status'/g)}`);
const iconOnly = [];
for (const [f, s] of Object.entries(src)) {
  for (const m of s.matchAll(/h\('button',\s*\{([^}]*)\},\s*icon\('[\w-]+'\)\)/g)) iconOnly.push([f, /aria-label/.test(m[1])]);
}
lines.push(`   icon-only <button> elements: ${iconOnly.length}; without aria-label: ${iconOnly.filter(([, ok]) => !ok).length}`);
const clickNonButton = [];
for (const [f, s] of Object.entries(src)) {
  for (const m of s.matchAll(/h\('(div|span|li|p|section|article|figure|td|tr|svg)',\s*\{([^}]*)\}/g)) {
    if (/onclick|onmousedown|onpointerdown/.test(m[2])) clickNonButton.push(`${f.replace(/\\/g, '/')}: <${m[1]}> ${m[2].slice(0, 60).replace(/\s+/g, ' ')}`);
  }
}
lines.push(`   click handlers on non-interactive tags (div, span, li, p, ...): ${clickNonButton.length}`);
for (const c of clickNonButton) lines.push(`     ${c}`);
lines.push(`   role="slider" elements: ${count(/role:\s*'slider'/g)}; files that define one and also handle keydown: ${Object.entries(src).filter(([, s]) => /role:\s*'slider'/.test(s) && /keydown/.test(s)).map(([f]) => base(f)).join(', ') || 'none'}`);
const ui = src[join('js', 'ui.js')] || '';
lines.push(`   modal: role="dialog" with aria-modal: ${/role:\s*'dialog'[^)]*'aria-modal': 'true'/.test(ui)}; Escape handled: ${/e\.key === 'Escape'/.test(ui)}; Tab trap: ${/e\.key === 'Tab'/.test(ui)}`);
lines.push(`   verdict chip with the safety note only in title= (player.js): ${/verdictChip\(safetyText, safetyTone, 'Safety rules', SAFETY_NOTE\)/.test(all) ? 'yes' : 'no'}`);
lines.push(`   title= attributes in views (tooltip text, not available to touch or most keyboard users): ${count(/\btitle:/g, Object.entries(src).filter(([f]) => f.includes('views')).map(([, s]) => s).join('\n'))}`);

// ------------------------------------------------------------------ 3. CSS: motion, focus, small type

const css = files('css', '.css');
const cssSrc = Object.fromEntries(css.map((f) => [f, read(f)]));
lines.push('');
lines.push('3. CSS patterns in desktop/studio/ui/css');
const kf = [];
for (const [f, s] of Object.entries(cssSrc)) for (const m of s.matchAll(/@keyframes\s+([\w-]+)/g)) kf.push([f, m[1]]);
const guardedFiles = Object.entries(cssSrc).filter(([, s]) => /prefers-reduced-motion/.test(s)).map(([f]) => f);
lines.push(`   @keyframes defined: ${kf.length} (${kf.map(([f, n]) => `${base(f)}:${n}`).join(', ')})`);
lines.push(`   files with a prefers-reduced-motion block: ${guardedFiles.map(base).join(', ')}`);
const unguarded = kf.filter(([f]) => !guardedFiles.includes(f));
lines.push(`   keyframes in files with no reduced-motion block: ${unguarded.length ? unguarded.map(([f, n]) => `${base(f)}:${n}`).join(', ') : 'none'}`);
lines.push(`   smooth scroll guarded by a reduced-motion test (discover.js): ${/behavior: reducedMotion\(\)/.test(all)}; playback autoplay guarded (player.js): ${/prefers-reduced-motion: reduce\)'\)\.matches\) cursor\.play\(\)/.test(all)}`);
lines.push(`   global :focus-visible rule (app.css): ${/:focus-visible\s*\{\s*outline:\s*2px/.test(cssSrc[join('css', 'app.css')] || '')}`);
const noOutline = [];
for (const [f, s] of Object.entries(cssSrc)) for (const m of s.matchAll(/([^{}]+)\{[^}]*outline:\s*(?:none|0)\b[^}]*\}/g)) noOutline.push(`${base(f)}: ${m[1].trim().replace(/\s+/g, ' ').slice(0, 70)}`);
lines.push(`   rules that remove the outline: ${noOutline.length}`);
for (const n of noOutline) lines.push(`     ${n}`);
const small = [];
for (const [f, s] of Object.entries(cssSrc)) {
  for (const m of s.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const d = /font(?:-size)?:\s*(?:[\w ]*\s)?(\d+(?:\.\d+)?)px/.exec(m[2]);
    if (d && Number(d[1]) < 12) small.push(`${base(f)}: ${m[1].trim().replace(/\s+/g, ' ').slice(0, 60)} -> ${d[1]}px`);
  }
}
lines.push(`   declarations with text below 12 px: ${small.length}`);
for (const s of small) lines.push(`     ${s}`);
const hides = [];
for (const m of cssSrc[join('css', 'mission.css')].matchAll(/@media \(max-height: 720px\) \{([\s\S]*?)\n\}/g)) hides.push(m[1].trim().replace(/\s+/g, ' '));
lines.push(`   mission.css, window height <= 720 px: ${hides.join(' | ') || 'no rule found'}`);

console.log(lines.join('\n'));
