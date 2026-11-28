r"""Live check that a development build, started through studio_launch, leaves the installed profile alone.

    python docs/evidence/m19/isolation/live_check.py --exe desktop/target/debug/vv-studio.exe --out docs/evidence/m19/isolation/result.json

Reads only metadata (path, size, modification time) of `%LOCALAPPDATA%\org.vvlab.studio` and
`%APPDATA%\org.vvlab.studio`; it never opens, writes or deletes anything there. Two listings are taken
a few seconds apart before the launch (a control, to show that the listing method is stable), then the
development executable is started once through studio_launch (scratch folders for every redirected
variable), left up for a few seconds and ended by its own PID, then the listing is taken again.
The listing hashes cover: relative path, kind, size (files only) and modification time in ns.
Run it with the installed Studio closed: a running installed Studio writes to its own profile.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "desktop", "studio", "tests"))
import studio_launch as sl  # noqa: E402


def listing(root):
    rows = []
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for n in sorted(files + dirs):
            p = os.path.join(d, n)
            try:
                st = os.lstat(p)
                isdir = os.path.isdir(p)
                rows.append(f"{os.path.relpath(p, root)}|{'D' if isdir else 'F'}|{'' if isdir else st.st_size}|{st.st_mtime_ns}")
            except OSError as e:
                rows.append(f"{os.path.relpath(p, root)}|ERR|{e}")
    text = "\n".join(sorted(rows)) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(rows)


def snapshot(roots):
    return {k: dict(zip(("sha256", "entries"), listing(r))) for k, r in roots.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=9477)
    a = ap.parse_args()
    local, roam = os.environ["LOCALAPPDATA"], os.environ["APPDATA"]
    exe = os.path.abspath(a.exe)
    roots = {"local": os.path.join(local, sl.RELEASE_IDENTIFIER), "roaming": os.path.join(roam, sl.RELEASE_IDENTIFIER)}
    running = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Process -Filter \"Name='vv-studio.exe'\" | Measure-Object).Count"],
                             capture_output=True, text=True).stdout.strip()
    if running != "0":
        sys.exit("a vv-studio.exe is running; close it first (this script never ends it)")
    control = snapshot(roots)
    time.sleep(5)
    before = snapshot(roots)
    dev_dir = os.path.join(local, sl.DEV_IDENTIFIER)
    if os.path.isdir(dev_dir) and not os.listdir(dev_dir):
        os.rmdir(dev_dir)  # our own, empty development folder: so the run shows whether the launch creates it
    env = dict(os.environ)
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"
    plan = sl.plan_launch(exe, env, local, roam, port=a.port, documents=os.path.join(os.environ["USERPROFILE"], "Documents"))
    scratch = dict(plan.scratch)
    proc = sl.launch(exe, {**env, **scratch}, a.port, wait_seconds=60)
    up = False
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/version", timeout=1)
                up = True
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        time.sleep(8)
        alive = proc.poll() is None
    finally:
        sl.stop(proc)
    time.sleep(5)
    name = os.path.basename(scratch["WEBVIEW2_USER_DATA_FOLDER"])
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -ne 'powershell.exe' -and $_.CommandLine -and $_.CommandLine -like '*" + name +
          "*' } | ForEach-Object { \"$($_.ProcessId) $($_.Name)\" }")
    left = [x for x in subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.split("\n") if x.strip()]
    after = snapshot(roots)
    dev_files = sum(len(f) for _, _, f in os.walk(dev_dir))
    top = sorted(os.listdir(scratch["WEBVIEW2_USER_DATA_FOLDER"])) if os.path.isdir(scratch["WEBVIEW2_USER_DATA_FOLDER"]) else None
    for v in scratch.values():
        shutil.rmtree(v, ignore_errors=True)
    with open(exe, "rb") as f:
        exe_sha = hashlib.sha256(f.read()).hexdigest()
    result = {
        "machine": {"os": platform.platform(), "python": platform.python_version()},
        "exe": os.path.basename(exe), "exe_sha256": exe_sha, "identifiers_in_exe": sorted(plan.identifiers),
        "roots": {"local": r"%LOCALAPPDATA%\org.vvlab.studio", "roaming": r"%APPDATA%\org.vvlab.studio"},
        "control_listings_identical": control == before,
        "before": before, "after": after, "installed_profile_identical": before == after,
        "devtools_endpoint_up": up, "alive_before_stop": alive, "ended_by_own_pid": True,
        "processes_left_on_scratch_profile": left,
        "scratch_redirected": sorted(scratch), "scratch_webview2_top_level": top,
        "devstudio_folder_exists_local": os.path.isdir(dev_dir), "devstudio_files_local": dev_files,
        "devstudio_folder_exists_roaming": os.path.isdir(os.path.join(roam, sl.DEV_IDENTIFIER)),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["installed_profile_identical"] and result["control_listings_identical"] and up else 1


if __name__ == "__main__":
    sys.exit(main())
