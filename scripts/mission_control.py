"""Mission Control vertical slice: a local browser UI over the simulator adapter.

Runs only on 127.0.0.1. The page lets a user pick one of the stored missions,
choose a fault (Simple) or edit the supported parameters (Advanced), run the
existing Rust simulator through `sim_adapter.GroundVehicleAdapter`, and step
through the recorded states. Research mode shows the request, provenance,
contract results and replay output. Everything drawn comes from the run's
recorded artifacts; the ground vehicle is a 2D kinematic model and the page
says so.

Usage:  python scripts/mission_control.py [--port 8780] [--output-root runs/mission-control]

Security: binds 127.0.0.1 only, rejects requests whose Host or Origin is not
this server, accepts JSON bodies up to MAX_BODY_BYTES, runs one simulation at a
time, never echoes absolute paths, and builds the page DOM without innerHTML.
The port is bound exclusively, so a second server cannot share it, and every
successful response must pass `sim_adapter.check_result` before it is sent.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from m6_report import CSS
from sim_adapter import AdapterError, GroundVehicleAdapter, check_result

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY_BYTES = 16 * 1024
BUSY_WAIT_SECONDS = 5


class ExclusiveServer(ThreadingHTTPServer):
    # SO_REUSEADDR on Windows lets a second process bind a listening port and receive
    # some of its requests; ask for exclusive use there instead.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(port: int, output_root: Path, adapter: GroundVehicleAdapter) -> ThreadingHTTPServer:
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "MissionControl/1"
        timeout = 10  # a client that declares a body and never sends it cannot pin a thread

        def log_message(self, fmt: str, *args: Any) -> None:  # keep test output quiet
            return

        def _allowed(self) -> bool:
            port_now = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port_now}", f"localhost:{port_now}"}
            origin = self.headers.get("Origin")
            return self.headers.get("Host") in hosts and (origin is None or origin in {f"http://{h}" for h in hosts})

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: Any) -> None:
            text = json.dumps(value, sort_keys=True)
            # Never leak where runs, the binary or the repository live on this machine.
            # Longest paths first, so a run directory inside the repository becomes <runs>.
            for place, label in ((output_root, "<runs>"), (adapter.binary, "<vv-lab>"), (adapter.root, "<repo>")):
                if place is None:
                    continue
                place = Path(place).resolve()
                for path in (str(place).replace("\\", "\\\\"), str(place), place.as_posix()):
                    # Windows paths are case-insensitive; simulator stderr may change the case.
                    text = re.sub(re.escape(path), label, text, flags=re.IGNORECASE if sys.platform == "win32" else 0)
            self._send(status, text.encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            if not self._allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "requests must come from this local page"})
            if self.path == "/":
                return self._send(HTTPStatus.OK, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if self.path == "/app.js":
                return self._send(HTTPStatus.OK, APP_JS.encode("utf-8"), "text/javascript; charset=utf-8")
            if self.path == "/api/describe":
                return self._json(HTTPStatus.OK, adapter.describe())
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "requests must come from this local page"})
            if self.path != "/api/run":
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "send application/json"})
            try:
                length = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                length = -1
            if length < 0:
                return self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length required"})
            if length > MAX_BODY_BYTES:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"body over {MAX_BODY_BYTES} bytes"})
            try:
                request = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "body is not valid JSON"})
            if not lock.acquire(timeout=BUSY_WAIT_SECONDS):
                return self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "another simulation is running; try again shortly"})
            try:
                result = adapter.run(request, output_root, reuse=True)
            except AdapterError as error:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception:  # noqa: BLE001 - report without internals
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "simulation failed unexpectedly"})
            finally:
                lock.release()
            result.pop("run_dir", None)
            try:
                check_result(result)
            except AdapterError as error:
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"result failed the contract check: {error}"})
            return self._json(HTTPStatus.OK, result)

    server = ExclusiveServer(("127.0.0.1", port), Handler)
    server.adapter = adapter
    return server


PAGE = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mission Control</title>
<style>{CSS}
main{{max-width:1200px}}
.tabs{{display:flex;gap:6px;margin:12px 0}}
.tabs button[aria-selected="true"]{{border:2px solid var(--text);font-weight:700}}
button,select,input{{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);min-height:36px}}
button:focus-visible,select:focus-visible,input:focus-visible{{outline:2px solid var(--s1);outline-offset:2px}}
button.primary{{background:var(--s1);color:#fff;border-color:var(--s1);font-weight:700}}
button:disabled{{opacity:.6}}
fieldset{{border:1px solid var(--line);border-radius:10px;padding:12px;margin:12px 0}}
legend{{font-weight:700;padding:0 6px}}
.choices{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}}
.choice{{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;padding:8px}}
.choice input{{min-height:auto;margin-top:4px}}
.choice:has(input:checked){{border:2px solid var(--s1)}}
input[aria-invalid="true"]{{border:2px solid var(--bad)}}
.scroll table{{min-width:520px}}
.scroll td code{{white-space:nowrap}}
.unverified{{border:2px dashed var(--bad);border-radius:10px;padding:8px;margin:8px 0;min-width:0;overflow-wrap:anywhere}}
.unverified svg,#tick-view svg{{width:100%;height:auto}}
input:disabled,select:disabled{{opacity:.5}}
.physics{{border-left:4px solid var(--s1);padding:4px 10px;background:var(--panel);max-width:80ch}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin:12px 0}}
.card{{background:var(--panel);border-radius:10px;padding:10px}}
.card b{{display:block;font-size:18px}}
.ok{{color:var(--good)}}.bad{{color:var(--bad)}}.warn{{color:var(--warn)}}
.grid2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}}
@media (max-width:820px){{.grid2{{grid-template-columns:minmax(0,1fr)}}}}
.controls{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}}
input[type=range]{{flex:1;min-width:140px}}
.tick-nav{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.tick-nav button[aria-current]{{border:2px solid var(--text);font-weight:700}}
dl.kv{{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 12px;margin:0}}
dl.kv dt{{color:var(--muted)}}dl.kv dd{{margin:0;overflow-wrap:anywhere}}
@media (max-width:480px){{dl.kv{{grid-template-columns:minmax(0,1fr)}}}}
.seg{{stroke:var(--s1);stroke-width:3;stroke-linecap:round}}.seg.fb{{stroke:var(--s2);stroke-dasharray:6 4}}
.truth{{fill:var(--s1)}}.obs{{fill:none;stroke:var(--text2);stroke-width:2}}
.zone{{fill:var(--bad);fill-opacity:.12;stroke:var(--bad)}}.wp{{fill:none;stroke:var(--good);stroke-width:2}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.4 ui-monospace,Consolas,monospace}}
.alert{{border:2px solid var(--bad);border-radius:8px;padding:8px 12px}}
[hidden]{{display:none!important}}
</style></head>
<body><main>
<p class="meta">V&amp;V lab · Mission Control · local simulator runs on this computer</p>
<h1>Mission Control</h1>
<p class="physics" id="physics"><b>Ground vehicle, 2D kinematic model.</b> Positions are integer millimetres on a plane,
time advances in fixed ticks, and there are no dynamics or environment model. This is not a 3D or 6-DOF simulation.</p>
<div class="tabs" role="tablist" aria-label="Mode">
<button role="tab" id="tab-simple" aria-controls="panel-simple" aria-selected="true">Simple</button>
<button role="tab" id="tab-advanced" aria-controls="panel-advanced" aria-selected="false" tabindex="-1">Advanced</button>
<button role="tab" id="tab-research" aria-controls="panel-research" aria-selected="false" tabindex="-1">Research</button>
</div>
<section id="panel-simple" role="tabpanel" aria-labelledby="tab-simple"></section>
<section id="panel-advanced" role="tabpanel" aria-labelledby="tab-advanced" hidden></section>
<section id="panel-research" role="tabpanel" aria-labelledby="tab-research" hidden></section>
<p id="status" role="status" aria-live="polite" class="meta"></p>
<div id="error" role="alert"></div>
<section id="result" aria-label="Run result"></section>
<noscript>Mission Control needs JavaScript.</noscript>
<script src="/app.js"></script>
</main></body></html>
"""

APP_JS = r"""
'use strict';
const SCHEMA = 'vv-sim-run-request.v1', MODEL = 'ground-vehicle-2d';
const $ = id => document.getElementById(id);
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k instanceof Node ? k : String(k));
  return n;
}
const SVGNS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  for (const k of kids) n.append(k instanceof Node ? k : String(k));
  return n;
}
const pt = p => p ? `(${p.x_mm}, ${p.y_mm}) mm` : 'none';
const act = a => !a ? 'none' : (a.distance_mm === 0 ? 'hold (0 mm)' : `${a.heading || 'no heading'} ${a.distance_mm} mm`);
const moved = k => k.truth.x_mm !== k.truth_from.x_mm || k.truth.y_mm !== k.truth_from.y_mm;
const dist = k => Math.round(Math.hypot(k.truth.x_mm - k.truth_from.x_mm, k.truth.y_mm - k.truth_from.y_mm));

const state = {describe: null, result: null, tick: null, timer: null, busy: false, ui: null};

// Simple-mode fault presets. Each maps to adapter overrides; nothing else is sent.
const PRESETS = [
  {id: 'default', label: 'Mission default', help: 'Keep the faults stored with the mission.', overrides: {}},
  {id: 'none', label: 'No faults', help: 'Clear GPS dropouts and actuator faults.', overrides: {gps_dropout: 'none', actuator_fault: 'none'}},
  {id: 'gps', label: 'GPS outage, ticks 4 to 7', help: 'GPS samples are dropped from tick 4 to 7; no actuator fault.',
    overrides: {gps_dropout: {start_tick: 4, end_tick: 7}, actuator_fault: 'none'}},
  {id: 'delayed', label: 'Delayed command at tick 4', help: 'The command issued at tick 4 executes 3 ticks late; no GPS outage.',
    overrides: {gps_dropout: 'none', actuator_fault: {kind: 'delayed_movement', start_tick: 4, end_tick: 4, probability_permille: 1000, delay_ticks: 3}}},
  {id: 'lost', label: 'Commands lost at ticks 3 to 4', help: 'Movement commands at ticks 3 and 4 are not executed; no GPS outage.',
    overrides: {gps_dropout: 'none', actuator_fault: {kind: 'lost_movement', start_tick: 3, end_tick: 4, probability_permille: 1000}}},
];

function setStatus(text) { $('status').textContent = text; }
function setError(text) {
  $('error').replaceChildren(text ? el('p', {class: 'alert', id: 'error-text'}, el('b', {}, 'Could not run: '), text) : '');
}
// Adapter error prefixes mapped to the Advanced field that caused them.
const FIELD_FOR_ERROR = [
  ['gps_dropout.start_tick', 'adv-gps-start'], ['gps_dropout.end_tick', 'adv-gps-end'], ['gps_dropout', 'adv-gps-start'],
  ['actuator_fault.start_tick', 'adv-act-start'], ['actuator_fault.end_tick', 'adv-act-end'],
  ['actuator_fault.probability_permille', 'adv-act-p'], ['actuator_fault.delay_ticks', 'adv-act-delay'], ['seed', 'adv-seed'],
];
function markField(message) {
  document.querySelectorAll('[aria-invalid]').forEach(n => { n.removeAttribute('aria-invalid'); n.removeAttribute('aria-describedby'); });
  const old = $('field-error'); if (old) old.remove();
  if (!message || $('panel-advanced').hidden) return;
  const hit = FIELD_FOR_ERROR.find(([prefix]) => message.startsWith(prefix));
  const input = hit && $(hit[1]);
  if (input) {
    (input.closest('label') || input).after(el('p', {class: 'alert', id: 'field-error'}, message));
    input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', 'field-error'); input.focus();
  }
}
// Plain description of what was run, from the validated request.
function describeRun(r) {
  const o = r.request.overrides, w = x => x === null ? 'mission default' : x === 'none' ? 'none' : `ticks ${x.start_tick} to ${x.end_tick}`;
  const f = o.actuator_fault, act = f === null ? 'mission default' : f === 'none' ? 'none' : `${f.kind.replaceAll('_', ' ')} ${w(f)}`;
  return `${r.request.mission} · GPS dropout: ${w(o.gps_dropout)} · actuator fault: ${act} · seed ${r.request.seed} · ${r.request.controller} · run ${r.run_id}`;
}

async function runRequest(body) {
  if (state.busy) return;
  state.busy = true; setError(''); setStatus('Running the simulator…');
  document.querySelectorAll('button.primary').forEach(b => { b.disabled = true; b.setAttribute('aria-busy', 'true'); });
  try {
    const resp = await fetch('/api/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await resp.json().catch(() => ({error: `server answered ${resp.status} without JSON`}));
    if (resp.ok && (typeof data.run_id !== 'string' || !data.verdict)) {
      data.error = 'the server answered without a run id or verdict; nothing from that answer is shown';
    }
    if (!resp.ok || data.error) {
      setError(data.error || `server answered ${resp.status}`);
      markField(data.error || '');
      setStatus(state.result ? `Nothing was run. The result below is still the previous run ${state.result.run_id}.` : '');
      return;
    }
    if (state.timer) clearInterval(state.timer);
    state.timer = null; state.result = data; state.tick = null;
    markField('');
    setStatus(data.verdict.status === 'verified'
      ? `Run ${data.run_id} finished${data.reused ? ' (stored run regenerated and compared)' : ''}. Evidence verified.`
      : `Run ${data.run_id}: the stored run does not match a fresh regeneration or its replay. Nothing below is verified evidence.`);
    drawResult(); drawResearch();
    $('result-heading').focus();
  } catch (e) {
    setError('the local server did not respond. Is mission_control.py still running?');
    setStatus(state.result ? `The result below is still the previous run ${state.result.run_id}.` : '');
  } finally {
    state.busy = false;
    document.querySelectorAll('button.primary').forEach(b => { b.disabled = false; b.removeAttribute('aria-busy'); });
  }
}

// ---------------------------------------------------------------- modes
function selectTab(name) {
  syncMission(name === 'advanced' ? 'simple' : 'advanced');
  for (const t of ['simple', 'advanced', 'research']) {
    const on = t === name;
    $('tab-' + t).setAttribute('aria-selected', on ? 'true' : 'false');
    $('tab-' + t).setAttribute('tabindex', on ? '0' : '-1');
    $('panel-' + t).hidden = !on;
  }
}
function wireTabs() {
  const names = ['simple', 'advanced', 'research'];
  names.forEach((name, i) => {
    const tab = $('tab-' + name);
    tab.addEventListener('click', () => selectTab(name));
    tab.addEventListener('keydown', e => {
      const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!d) return;
      const next = names[(i + d + names.length) % names.length];
      selectTab(next); $('tab-' + next).focus(); e.preventDefault();
    });
  });
}

function drawSimple() {
  const missions = state.describe.capabilities.missions;
  const missionSet = el('fieldset', {}, el('legend', {}, '1. Choose a mission'),
    el('div', {class: 'choices'}, missions.map((m, i) => el('label', {class: 'choice'},
      el('input', {type: 'radio', name: 'simple-mission', value: m.id, checked: i === missions.length - 1}),
      el('span', {}, el('b', {}, m.id), el('br'), el('span', {class: 'meta'}, `${m.steps} ticks of ${m.tick_ms} ms. ${m.description}`))))));
  const faultSet = el('fieldset', {}, el('legend', {}, '2. Choose what goes wrong'),
    el('div', {class: 'choices'}, PRESETS.map((p, i) => el('label', {class: 'choice'},
      el('input', {type: 'radio', name: 'simple-fault', value: p.id, checked: i === 0}),
      el('span', {}, el('b', {}, p.label), el('br'), el('span', {class: 'meta'}, p.help))))));
  const run = el('button', {class: 'primary', onclick: () => {
    const mission = document.querySelector('input[name=simple-mission]:checked').value;
    const preset = PRESETS.find(p => p.id === document.querySelector('input[name=simple-fault]:checked').value);
    runRequest({schema: SCHEMA, model: MODEL, mission, seed: 42, controller: 'dominant_axis', overrides: preset.overrides});
  }}, '3. Run simulation');
  $('panel-simple').replaceChildren(missionSet, faultSet,
    el('p', {class: 'meta'}, 'Simple mode uses seed 42 and the dominant_axis controller. Advanced mode changes them.'), run);
}

function num(id, label, value, min, max) {
  return el('label', {}, label + ' ', el('input', {type: 'number', id, value, min, max, step: 1, inputmode: 'numeric'}));
}
function drawAdvanced() {
  const caps = state.describe.capabilities;
  const mission = el('select', {id: 'adv-mission'}, caps.missions.map(m => el('option', {value: m.id}, m.id)));
  const controller = el('select', {id: 'adv-controller'}, caps.controllers.map(c => el('option', {value: c}, c)));
  const gpsMode = el('select', {id: 'adv-gps-mode'}, ['mission default', 'none', 'custom'].map(v => el('option', {value: v}, v)));
  const actMode = el('select', {id: 'adv-act-mode'}, ['mission default', 'none', 'custom'].map(v => el('option', {value: v}, v)));
  const kind = el('select', {id: 'adv-act-kind'}, caps.actuator_fault_kinds.map(k => el('option', {value: k}, k)));
  // Parameter fields only apply in custom mode; delay only for delayed_movement.
  const gate = () => {
    const gps = gpsMode.value === 'custom', a = actMode.value === 'custom';
    for (const id of ['adv-gps-start', 'adv-gps-end']) $(id).disabled = !gps;
    for (const id of ['adv-act-start', 'adv-act-end', 'adv-act-p']) $(id).disabled = !a;
    kind.disabled = !a;
    $('adv-act-delay').disabled = !(a && kind.value === 'delayed_movement');
  };
  gpsMode.addEventListener('change', gate); actMode.addEventListener('change', gate); kind.addEventListener('change', gate);
  const run = el('button', {class: 'primary', onclick: () => {
    const v = id => $(id).value, n = id => Number($(id).value);
    const overrides = {};
    if (v('adv-gps-mode') === 'none') overrides.gps_dropout = 'none';
    if (v('adv-gps-mode') === 'custom') overrides.gps_dropout = {start_tick: n('adv-gps-start'), end_tick: n('adv-gps-end')};
    if (v('adv-act-mode') === 'none') overrides.actuator_fault = 'none';
    if (v('adv-act-mode') === 'custom') {
      overrides.actuator_fault = {kind: v('adv-act-kind'), start_tick: n('adv-act-start'), end_tick: n('adv-act-end'), probability_permille: n('adv-act-p')};
      if (v('adv-act-kind') === 'delayed_movement') overrides.actuator_fault.delay_ticks = n('adv-act-delay');
    }
    runRequest({schema: SCHEMA, model: MODEL, mission: v('adv-mission'), seed: n('adv-seed'), controller: v('adv-controller'), overrides});
  }}, 'Run simulation');
  $('panel-advanced').replaceChildren(
    el('p', {}, 'Every field is validated by the adapter and again by the Rust library; values outside the declared ranges are refused with a message.'),
    el('fieldset', {}, el('legend', {}, 'Mission and controller'),
      el('div', {class: 'controls'}, el('label', {}, 'Mission ', mission), num('adv-seed', 'Seed', 42, 0, Number.MAX_SAFE_INTEGER),
        el('label', {}, 'Controller ', controller))),
    el('fieldset', {}, el('legend', {}, 'GPS dropout'),
      el('div', {class: 'controls'}, el('label', {}, 'Mode ', gpsMode), num('adv-gps-start', 'Start tick', 4, 0, 200), num('adv-gps-end', 'End tick', 7, 0, 200))),
    el('fieldset', {}, el('legend', {}, 'Actuator fault'),
      el('div', {class: 'controls'}, el('label', {}, 'Mode ', actMode), el('label', {}, 'Kind ', kind),
        num('adv-act-start', 'Start tick', 4, 0, 200), num('adv-act-end', 'End tick', 4, 0, 200),
        num('adv-act-p', 'Probability (per mille)', 1000, 0, 1000), num('adv-act-delay', 'Delay ticks (delayed only)', 3, 1, 200)),
      el('p', {class: 'meta'}, '"mission default" keeps the faults stored with the mission; the fields below apply only in "custom" mode.')),
    run);
  gate();
}
// Keep the mission choice consistent between Simple and Advanced.
function syncMission(from) {
  const simple = document.querySelector('input[name=simple-mission]:checked'), adv = $('adv-mission');
  if (!simple || !adv) return;
  if (from === 'simple') adv.value = simple.value;
  else { const r = document.querySelector(`input[name=simple-mission][value="${adv.value}"]`); if (r) r.checked = true; }
}

function drawResearch() {
  const r = state.result;
  if (!r) { $('panel-research').replaceChildren(el('p', {}, 'Run a simulation first; this panel then shows the exact request, provenance hashes, contract results and replay output.')); return; }
  const kv = obj => el('dl', {class: 'kv'}, Object.entries(obj).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, el('code', {}, String(v)))]));
  const p = r.provenance;
  $('panel-research').replaceChildren(
    el('h2', {}, `Run ${r.run_id}`),
    el('h3', {}, 'Request (as validated by the adapter)'), el('pre', {}, JSON.stringify(r.request, null, 2)),
    el('h3', {}, 'Provenance'), kv({adapter: r.adapter, model: r.model.id, source_sha256: p.source_sha256, manifest_sha256: p.manifest_sha256,
      binary_sha256: p.binary_sha256, controller_id: p.controller_id}),
    el('h3', {}, 'Input and artifact sha256'), kv(Object.assign({}, r.inputs, p.artifacts)),
    el('h3', {}, 'Verdict'), el('p', {class: r.verdict.status === 'verified' ? 'ok' : 'bad'},
      r.verdict.status === 'verified' ? 'Verified: replay matched and no integrity problem was found.' : `Rejected: ${r.verdict.reasons.join('; ')}`),
    el('h3', {}, 'Replay'), el('p', {class: r.replay.status === 'verified' ? 'ok' : 'bad'},
      r.replay.status === 'verified' ? 'Verified: vv-lab replay-m4 recomputed this run and exited 0.' : `Replay ${r.replay.status}: ${r.replay.stderr || r.replay.detail || ''}`),
    el('pre', {}, r.replay.stdout || ''),
    el('h3', {}, 'Integrity'), el('p', {class: r.integrity.problems.length ? 'bad' : 'ok'}, r.integrity.problems.length ? r.integrity.problems.join('; ') : r.reused ? 'All files match a fresh regeneration of this request.' : 'All artifact hashes match the manifest.'),
    el('h3', {}, 'Contract results (verification.json)'),
    el('div', {class: 'scroll'}, el('table', {}, el('thead', {}, el('tr', {}, ['contract', 'outcome', 'trigger → deadline → violation', 'detail'].map(h => el('th', {}, h)))),
      el('tbody', {}, r.contracts.map(c => el('tr', {}, el('td', {}, el('code', {}, c.id)), el('td', {class: c.outcome === 'FAIL' ? 'bad' : c.outcome === 'PASS' ? 'ok' : 'warn'}, c.outcome),
        el('td', {}, `${c.trigger_tick ?? 'none'} → ${c.deadline_tick ?? 'none'} → ${c.violation_tick ?? 'none'}`), el('td', {}, c.detail || '')))))));
}

// ---------------------------------------------------------------- result
function story(r) {
  const timed = [];  // [tick, text], sorted by tick below
  for (const x of r.transitions) if (x.subsystem === 'safety') timed.push([x.tick, `Tick ${x.tick}: safety ${x.from} → ${x.to} (${x.reason}).`]);
  const dropped = r.states.filter(k => k.gps_dropped).map(k => k.tick);
  if (dropped.length) timed.push([dropped[0], `GPS samples dropped at ticks ${dropped.join(', ')}.`]);
  for (const e of r.actuator_events) if (e.kind !== 'fault_window_active') timed.push([e.tick, `Tick ${e.tick}: actuator ${e.kind.replaceAll('_', ' ')} (command from tick ${e.source_command_tick}).`]);
  for (const k of r.states) if (k.safety_state === 'fallback' && moved(k)) timed.push([k.tick, `Tick ${k.tick}: the vehicle moved ${dist(k)} mm while in fallback; the controller commanded ${act(k.action)}.`]);
  for (const c of r.contracts) if (c.outcome === 'FAIL') timed.push([c.violation_tick, `Tick ${c.violation_tick}: temporal contract ${c.id} violated.`]);
  for (const f of r.invariant_failures) timed.push([f.tick, `Tick ${f.tick}: safety invariant ${f.name} violated.`]);
  const out = timed.sort((a, b) => a[0] - b[0]).map(([, t]) => t);
  if (!r.contracts.some(c => c.outcome === 'FAIL') && !r.invariant_failures.length) out.push('No contract or invariant was violated.');
  const m = r.mission;
  out.push(m ? `Mission ${m.outcome}${m.reason ? ' (' + m.reason + ')' : ''}: ${m.distance_to_next_waypoint_mm} mm short of the waypoint after ${r.states.length} ticks, ${m.fallback_ticks} of them in fallback.`
    : 'Mission outcome not recorded.');
  return out;
}

function mapSvg(r, upto) {
  const g = r.geometry, pts = r.states.flatMap(k => [k.truth_from, k.truth, k.observed && k.observed.position].filter(Boolean));
  if (g) { pts.push(...g.waypoints); if (g.start) pts.push(g.start); }
  const xs = pts.map(p => p.x_mm), ys = pts.map(p => p.y_mm), pad = 600;
  let x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
  const w = x1 - x0, h = y1 - y0;
  if (h < 0.4 * w) { const e = (0.4 * w - h) / 2; y0 -= e; y1 += e; }
  if (w < 0.4 * h) { const e = (0.4 * h - w) / 2; x0 -= e; x1 += e; }
  const spanX = x1 - x0, spanY = y1 - y0, s = Math.min(480 / spanX, 320 / spanY), W = spanX * s, H = spanY * s;
  const X = p => ((p.x_mm - x0) * s).toFixed(1), Y = p => (H - (p.y_mm - y0) * s).toFixed(1);
  const cur = r.states.find(k => k.tick === upto);
  const svg = sv('svg', {viewBox: `0 0 ${W.toFixed(0)} ${H.toFixed(0)}`, role: 'img', style: `max-width:${Math.ceil(W)}px`,
    'aria-label': `Top-down 2D view at tick ${upto}: true position ${cur ? pt(cur.truth) : 'none'}, ${cur ? cur.safety_state : ''}`});
  svg.append(sv('rect', {x: 0, y: 0, width: W, height: H, fill: 'none', stroke: 'var(--line)'}));
  if (g && g.restricted_zone && g.restricted_zone.length) svg.append(sv('polygon', {class: 'zone', points: g.restricted_zone.map(p => `${X(p)},${Y(p)}`).join(' ')}));
  if (g) for (const wp of g.waypoints) { svg.append(sv('circle', {class: 'wp', cx: X(wp), cy: Y(wp), r: Math.max(5, (g.arrival_radius_mm || 0) * s)})); svg.append(sv('text', {x: +X(wp) - 24, y: +Y(wp) - 10, class: 'axis'}, 'waypoint')); }
  if (g && g.start) svg.append(sv('text', {x: +X(g.start) - 12, y: +Y(g.start) + 18, class: 'axis'}, 'start'));
  for (const k of r.states.filter(k => k.tick <= upto)) if (moved(k))
    svg.append(sv('line', {class: 'seg' + (k.safety_state === 'fallback' ? ' fb' : ''), x1: X(k.truth_from), y1: Y(k.truth_from), x2: X(k.truth), y2: Y(k.truth)}));
  if (cur) {
    if (cur.observed && cur.observed.position) svg.append(sv('rect', {class: 'obs', x: +X(cur.observed.position) - 6, y: +Y(cur.observed.position) - 6, width: 12, height: 12}));
    svg.append(sv('circle', {class: 'truth', cx: X(cur.truth), cy: Y(cur.truth), r: 7}));
    if (cur.safety_state === 'fallback') svg.append(sv('text', {x: 8, y: 16, class: 'lab'}, 'FALLBACK'));
  }
  // The zone is not used for fitting, so the path stays legible; say so when it lies outside the view.
  const z = g && g.restricted_zone && g.restricted_zone.length ? g.restricted_zone : null;
  const zx = z && z.map(p => p.x_mm), zy = z && z.map(p => p.y_mm);
  const off = z && (Math.min(...zx) > x1 || Math.max(...zx) < x0 || Math.min(...zy) > y1 || Math.max(...zy) < y0);
  svg.append(sv('text', {x: 6, y: H - 6, class: 'axis'}, `2D top-down view, ${Math.round(spanX)} mm wide, y up`));
  if (off) svg.append(sv('text', {x: 6, y: H - 20, class: 'axis'}, `restricted zone x ${Math.min(...zx)}–${Math.max(...zx)}, y ${Math.min(...zy)}–${Math.max(...zy)} mm: off-canvas`));
  return svg;
}

function tickCard(r, k) {
  const a = k.actuation, none = 'not recorded for this tick';
  const firing = r.contracts.filter(c => c.outcome === 'FAIL' && c.violation_tick === k.tick).map(c => c.id).concat(r.invariant_failures.filter(f => f.tick === k.tick).map(f => f.name));
  const ob = k.observed;
  return el('dl', {class: 'kv'},
    el('dt', {}, 'safety / mission'), el('dd', {}, `${k.safety_state} / ${k.mission_state}`),
    el('dt', {}, 'commanded (controller)'), el('dd', {}, act(k.action)),
    el('dt', {}, 'realized (actuator)'), el('dd', {}, a ? act(a.realized_action) : none),
    el('dt', {}, 'true position'), el('dd', {}, `${pt(k.truth_from)} → ${pt(k.truth)}`),
    el('dt', {}, 'observation used'), el('dd', {}, ob ? `${pt(ob.position)}, sample tick ${ob.sample_tick}, ${ob.fresh ? 'fresh' : 'stale'}` : 'none'),
    el('dt', {}, 'GPS'), el('dd', {}, k.gps_dropped ? 'sample dropped' : 'no drop recorded'),
    el('dt', {}, 'violations at this tick'), el('dd', {class: firing.length ? 'bad' : ''}, firing.length ? firing.join(', ') : 'none'),
    el('dt', {}, 'raw event'), el('dd', {}, el('code', {}, `events.json #${k.event_sequence}`)));
}

function drawResult() {
  const r = state.result;
  if (!r || !r.states.length) { $('result').replaceChildren(r ? el('p', {class: 'bad'}, 'The run produced no recorded states.') : ''); return; }
  const ticks = r.states.map(k => k.tick);
  if (!ticks.includes(state.tick)) {
    const fails = r.contracts.filter(c => c.outcome === 'FAIL').map(c => c.violation_tick).concat(r.invariant_failures.map(f => f.tick)).filter(t => t != null);
    state.tick = fails.length ? Math.min(...fails) : ticks[0];
  }
  const sum = r.summary || {}, failed = r.contracts.filter(c => c.outcome === 'FAIL').length;
  const verified = r.verdict.status === 'verified';
  const card = (label, value, cls) => el('div', {class: 'card'}, el('span', {class: 'meta'}, label), el('b', {class: cls}, value));
  const label = el('b', {id: 'tick-label', role: 'status', 'aria-live': 'polite'});
  const slider = el('input', {type: 'range', min: 0, max: ticks.length - 1, 'aria-label': 'Tick', 'aria-describedby': 'tick-label', oninput: e => setTick(ticks[+e.target.value])});
  const playBtn = el('button', {'aria-pressed': 'false', onclick: () => (state.timer ? stop() : play())}, 'play');
  const view = el('div', {id: 'tick-view'});
  state.ui = {r, ticks, label, slider, playBtn, view};
  const withheld = 'withheld: stored files differ from regeneration';
  const details = [
    el('div', {class: 'panel'}, el('b', {}, 'What happened'), el('ol', {}, story(r).map(s => el('li', {}, s))),
      el('p', {class: 'meta'}, 'Each line is computed from the recorded transitions, tick results and verification records of this run.')),
    el('div', {class: 'controls'}, el('button', {'aria-label': 'Previous tick', onclick: () => stepBy(-1)}, '◀ step'), playBtn,
      el('button', {'aria-label': 'Next tick', onclick: () => stepBy(1)}, 'step ▶'), slider, label),
    view,
    el('p', {class: 'meta'}, 'The drawing shows recorded per-tick positions of a 2D kinematic model: blue segments are recorded moves, dashed orange while in fallback; the filled dot is the true position and the hollow square the observation the controller used. The red outline is the restricted zone; when it lies outside the view, the drawing names its coordinates instead. Nothing is interpolated between ticks.')];
  $('result').replaceChildren(
    el('h2', {id: 'result-heading', tabindex: '-1'}, verified ? 'Result' : 'Result: REJECTED evidence'),
    el('p', {class: 'meta'}, describeRun(r)),
    el('p', {class: verified ? 'ok' : 'alert'}, verified
      ? `Evidence verified: vv-lab replay-m4 re-ran this run with the build named in Research and exited 0${r.reused ? '; every stored file also matches a fresh regeneration' : ''}. This confirms the evidence, not that the mission passed.`
      : `Not verified evidence. The stored run does not match what this request and build produce: ${r.verdict.reasons.join('; ')}.`),
    el('div', {class: 'cards'},
      card('Mission outcome', verified ? (r.mission ? r.mission.outcome : 'unknown') : withheld, verified && r.mission && r.mission.outcome === 'completed' ? 'ok' : 'warn'),
      card('Safety invariants', verified ? (sum.safety_status || 'unknown') : withheld, verified && sum.safety_status === 'passed' ? 'ok' : 'bad'),
      card('Temporal contracts', verified ? `${sum.contracts_passed ?? '?'} passed, ${failed} failed, ${sum.contracts_inconclusive ?? 0} inconclusive` : withheld, verified && !failed ? 'ok' : 'bad')),
    ...(verified ? details : [el('section', {class: 'unverified', 'aria-label': 'Unverified stored data'},
      el('b', {class: 'bad'}, 'UNVERIFIED stored data, shown for diagnosis only'), details)]));
  renderTick();
}

function renderTick() {
  const ui = state.ui; if (!ui) return;
  const idx = ui.ticks.indexOf(state.tick), k = ui.r.states[idx]; if (!k) return;
  const fid = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute('data-fid');
  ui.slider.value = idx;
  ui.label.setAttribute('aria-live', state.timer ? 'off' : 'polite');
  ui.label.textContent = `tick ${state.tick} of ${ui.ticks[ui.ticks.length - 1]}`;
  ui.slider.setAttribute('aria-valuetext', `tick ${state.tick}: ${k.safety_state}, commanded ${act(k.action)}, moved ${dist(k)} mm`);
  ui.playBtn.textContent = state.timer ? 'pause' : 'play';
  ui.playBtn.setAttribute('aria-pressed', state.timer ? 'true' : 'false');
  const nav = el('div', {class: 'tick-nav', role: 'group', 'aria-labelledby': 'tick-nav-label'}, el('span', {class: 'meta', id: 'tick-nav-label'}, 'Jump to tick'),
    ui.r.states.map(s => el('button', {'data-fid': `nav-${s.tick}`, 'aria-current': s.tick === state.tick ? 'step' : null,
      'aria-label': `Show tick ${s.tick}: ${s.safety_state}${s.gps_dropped ? ', GPS dropped' : ''}${moved(s) ? ', moved' : ''}`, onclick: () => setTick(s.tick)}, String(s.tick))));
  ui.view.replaceChildren(el('div', {class: 'grid2'}, el('div', {class: 'panel'}, mapSvg(ui.r, state.tick)), el('div', {class: 'panel'}, tickCard(ui.r, k))), nav);
  if (fid) { const n = ui.view.querySelector(`[data-fid="${fid}"]`); if (n) n.focus(); }
}
function setTick(t) { state.tick = t; renderTick(); }
function stepBy(d) { const t = state.ui.ticks, i = t.indexOf(state.tick); setTick(t[Math.max(0, Math.min(t.length - 1, i + d))]); }
function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; renderTick(); }
function play() {
  const t = state.ui.ticks;
  if (t.indexOf(state.tick) >= t.length - 1) state.tick = t[0];
  state.timer = setInterval(() => { const i = t.indexOf(state.tick); if (i >= t.length - 1) { stop(); return; } setTick(t[i + 1]); }, 700);
  renderTick();
}

async function boot() {
  wireTabs();
  try {
    const resp = await fetch('/api/describe');
    state.describe = await resp.json();
  } catch (e) { setError('could not load the simulator description from the local server.'); return; }
  $('physics').append(' ', el('span', {class: 'meta'}, `Model ${state.describe.model.id}; adapter contract ${state.describe.schema}.`));
  drawSimple(); drawAdvanced(); drawResearch();
}
boot();
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--output-root", default=str(ROOT / "runs" / "mission-control"))
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        print("error: --port must be in [1024, 65535]", file=sys.stderr)
        return 2
    server = make_server(args.port, Path(args.output_root), GroundVehicleAdapter())
    print(f"Mission Control on http://127.0.0.1:{args.port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
