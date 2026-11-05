"""Runs a spike page in Microsoft Edge (same Chromium/ANGLE engine family as WebView2) and prints JSON."""
import json
import subprocess
import sys
import time

import psutil
from playwright.sync_api import sync_playwright

page_name, port, runs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
query = sys.argv[4] if len(sys.argv) > 4 else ""
srv = subprocess.Popen([sys.executable, "server.py", "site", str(port)])
time.sleep(1.0)
out = []
try:
    with sync_playwright() as pw:
        for k in range(runs):
            b = pw.chromium.launch(channel="msedge", headless=False, args=["--window-size=1440,900", "--disable-features=CalculateNativeWinOcclusion"])
            ctx = b.new_context(viewport={"width": 1440, "height": 860})
            pg = ctx.new_page()
            reqs, console = [], []
            pg.on("request", lambda r: reqs.append(r.url))
            pg.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            t = time.time()
            pg.goto(f"http://127.0.0.1:{port}/{page_name}.html{query}")
            pg.wait_for_function("() => window.__bench || (window.__errors && window.__errors.length)", timeout=120000)
            wall = time.time() - t
            res = pg.evaluate("() => ({bench: window.__bench || null, tiles_loaded_ms: window.__tiles_loaded_ms || null, csp: window.__cspViolations, errors: window.__errors || [], gl: (() => { const c = document.createElement('canvas').getContext('webgl2'); const x = c && c.getExtension('WEBGL_debug_renderer_info'); return x ? c.getParameter(x.UNMASKED_RENDERER_WEBGL) : null; })()})")
            procs = [p for p in psutil.process_iter(["name", "cmdline", "memory_info"]) if p.info["name"] == "msedge.exe" and any("playwright" in a for a in (p.info["cmdline"] or []))]
            ws = sum(p.info["memory_info"].rss for p in procs) / 1048576
            priv = sum(p.memory_full_info().private for p in procs) / 1048576
            gpu = [p for p in procs if any("--type=gpu-process" in a for a in (p.info["cmdline"] or []))]
            res.update({"run": k + 1, "wall_to_bench_end_s": round(wall, 2), "processes": len(procs), "working_set_mb": round(ws, 1), "private_mb": round(priv, 1),
                        "gpu_process_private_mb": round(sum(p.memory_full_info().private for p in gpu) / 1048576, 1),
                        "requests": len(reqs), "non_local_requests": [u for u in reqs if not u.startswith(f"http://127.0.0.1:{port}/") and not u.startswith("data:") and not u.startswith("blob:")],
                        "bytes_hint": None, "console": console[:10]})
            pg.screenshot(path=f"shot-{page_name}-{k + 1}.png")
            out.append(res)
            b.close()
finally:
    srv.terminate()
print(json.dumps(out, indent=1))
