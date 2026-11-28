r"""The only way the Studio UI tests start a Studio executable.

Why this exists: the Studio keeps real data in the profile of the installed application
(`%LOCALAPPDATA%\org.vvlab.studio`, `%APPDATA%\org.vvlab.studio`; WebView2 keeps its browser profile
in the first of them). A development build that shared that identifier, started by a suite that did
not redirect `WEBVIEW2_USER_DATA_FOLDER`, wrote into it (docs/incidents/2026-11-23-webview2-profile.md).

Three layers. The first two each stop a write into the installed profile by themselves; the third
stops the tests from ending the wrong process; the tests keep all three in place.

1. Identity. The base `tauri.conf.json` has the development identifier `org.vvlab.devstudio`; only
   `tauri.release.conf.json`, applied by `desktop/build.ps1 -Release`, has `org.vvlab.studio`. A normal
   build therefore never has the installed profile's name. `embedded_identifiers` reads which of the
   two a given executable carries (Tauri compiles the identifier into the binary as a UTF-8 string).
2. Launch. `plan_launch` is pure. It points the folders the Studio is told to redirect at scratch
   folders (`WEBVIEW2_USER_DATA_FOLDER`, `VVLAB_LIBRARY`, `VVLAB_CONFIG`, `VVLAB_MODULES`) and raises
   when any variable, resolved path or `--user-data-dir` argument lies in the installed profile, or
   when the executable is the installed one, carries the release identifier or has no known one. Only
   the explicit `allow_release` flag (command line `--owner-allow-release-exe`) lifts the executable
   refusals; it never lifts the path refusals. `VVLAB_MODULES` is honoured by any build whose identifier
   is not the release one (the Studio keys it on identity, not on the build profile), so a development
   build, debug or release profile, keeps its Cinematic module folder in the launch's token directory.
   An executable started with the owner flag has the release identifier, ignores the variable and
   resolves the module folder to the installed profile. It also writes the single-use launch token that
   the development Studio's runtime guard requires (desktop/studio/src/guard.rs).
3. Teardown. Only the process this module started is killed, by PID. Nothing here or in the other
   scripts kills by image name: the owner's installed Studio has the same image name, `vv-studio.exe`.

`tests/test_studio_isolation.py` tests all of this without starting a Studio, and fails if a script
starts a Studio executable anywhere else or uses an image-name kill.
"""

import json
import ntpath
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request
import warnings

RELEASE_IDENTIFIER = "org.vvlab.studio"
DEV_IDENTIFIER = "org.vvlab.devstudio"
INSTALL_FOLDER = "VV Lab Studio"
LIBRARY_FOLDER = "VV Lab Library"
CINEMATIC_FOLDER = "VV Lab Cinematic"  # Godot user data of the Cinematic module
OWNER_FLAG = "--owner-allow-release-exe"

# Folders the Studio writes, by the variable that redirects them.
SCRATCH_VARIABLES = ("WEBVIEW2_USER_DATA_FOLDER", "VVLAB_LIBRARY", "VVLAB_CONFIG", "VVLAB_MODULES")
BROWSER_ARGUMENTS = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
ENV_LAUNCH = "VVLAB_DEV_LAUNCH"  # the launch token file, read and consumed by the Studio's runtime guard
ENV_NONCE = "VVLAB_DEV_NONCE"
TOKEN_FILE = "launch.json"
REFUSED_EXIT = 78  # exit code of a refused start (desktop/studio/src/guard.rs)
# Folder of each redirected variable inside the token directory.
TOKEN_SUBFOLDERS = {"WEBVIEW2_USER_DATA_FOLDER": "webview2", "VVLAB_LIBRARY": "library", "VVLAB_CONFIG": "config",
                    "VVLAB_MODULES": "modules", "APPDATA": "appdata", "LOCALAPPDATA": "localappdata"}


class IsolationError(RuntimeError):
    """A launch was refused because it could touch the installed application's data."""


def add_arguments(parser):
    """Registers the owner-only flag on a script's argument parser."""
    parser.add_argument(
        OWNER_FLAG,
        dest="owner_allow_release_exe",
        action="store_true",
        help="owner only: allow the installed or release-identifier executable (it uses the installed profile for modules)",
    )


def _expand(value, environ):
    """Expands %NAME% against `environ` (case-insensitive), as the Windows shell would."""
    lookup = {k.lower(): v for k, v in environ.items()}
    return re.sub(r"%([^%]+)%", lambda m: lookup.get(m.group(1).lower(), m.group(0)), value)


def normalise(path, environ=None):
    """A comparable form of a Windows path: absolute, real, lower case, single backslashes, no
    trailing separator, no device prefix, no trailing dots or spaces in any component. A network
    path (double backslash or double slash followed by a server) or a device path that does not continue
    with a drive letter (UNC, Volume{...}, GLOBALROOT, PhysicalDrive) raises IsolationError: it could name
    the installed profile by another route and is never a scratch folder."""
    if environ is not None:
        path = _expand(path, environ)
    unc = path.replace("/", "\\")
    device = unc[:4] in ("\\\\?\\", "\\\\.\\")
    if unc.startswith("\\\\") and (not device or not re.match(r"[A-Za-z]:(\\|$)", unc[4:])):
        # A network path, `UNC\...`, `Volume{...}`, `GLOBALROOT\...` or any other device path: only a drive letter is accepted.
        raise IsolationError(f"network or device path refused: {path}")
    if os.name == "nt":
        path = os.path.realpath(path)
    path = ntpath.normpath(ntpath.abspath(path))
    if path.startswith("\\\\?\\"):
        path = path[4:]
    drive, rest = ntpath.splitdrive(path)
    parts = [p.rstrip(" .") for p in rest.split("\\")]
    return ntpath.normcase(drive + "\\".join(parts)).rstrip("\\")


def is_under(path, root):
    path, root = normalise(path), normalise(root)
    return path == root or path.startswith(root + "\\")


def protected_roots(local_appdata, appdata, documents=None):
    """The data of the installed application: the two profile folders and the research library.
    `documents` is one Documents folder or several (the known folder can be redirected)."""
    roots = [ntpath.join(local_appdata, RELEASE_IDENTIFIER), ntpath.join(appdata, RELEASE_IDENTIFIER)]
    if isinstance(documents, str):
        documents = [documents]
    for folder in documents or ():
        if folder:
            roots.append(ntpath.join(folder, LIBRARY_FOLDER))
    return roots


FOLDERID_DOCUMENTS = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"


def known_documents_folder():
    """The Windows Documents known folder (SHGetKnownFolderPath), or None with a warning when the call
    fails or this is not Windows. Never silent: a wrong answer here would leave the library unprotected."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        folder_id = (ctypes.c_byte * 16)(*uuid.UUID(FOLDERID_DOCUMENTS).bytes_le)
        out = ctypes.c_wchar_p()
        get = ctypes.windll.shell32.SHGetKnownFolderPath
        get.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        status = get(ctypes.byref(folder_id), 0, None, ctypes.byref(out))
        value = out.value
        ctypes.windll.ole32.CoTaskMemFree(out)
        if status == 0 and value:
            return value
        warnings.warn(f"SHGetKnownFolderPath(Documents) returned {status & 0xFFFFFFFF:#010x}; only the user-profile guess protects the library", RuntimeWarning, stacklevel=2)
    except Exception as e:  # noqa: BLE001
        warnings.warn(f"cannot resolve the Documents known folder ({e!r}); only the user-profile guess protects the library", RuntimeWarning, stacklevel=2)
    return None


def documents_folders():
    """The Documents folders whose `VV Lab Library` the Studio would use: the Windows known folder (it can
    be redirected, to OneDrive for example) and the default under the user profile as a second guard."""
    found = []
    known = known_documents_folder()
    if known:
        found.append(known)
    if os.environ.get("USERPROFILE"):
        found.append(os.path.join(os.environ["USERPROFILE"], "Documents"))
    if not found:
        raise IsolationError("no Documents folder is known (no known folder, no USERPROFILE): the research library cannot be protected")
    return list(dict.fromkeys(found))


def embedded_identifiers(exe):
    """Which known identifiers the executable carries. Tauri compiles `identifier` into the binary
    as UTF-8; UTF-16 is searched too. `org.vvlab.devstudio` does not contain `org.vvlab.studio`,
    so the two never match each other."""
    with open(exe, "rb") as f:
        data = f.read()
    found = set()
    for ident in (RELEASE_IDENTIFIER, DEV_IDENTIFIER):
        if ident.encode("utf-8") in data or ident.encode("utf-16-le") in data:
            found.add(ident)
    return found


class LaunchPlan:
    def __init__(self, exe, env, scratch, identifiers, redirects=None, token_dir=None, token=None):
        self.exe = exe
        self.env = env
        self.scratch = scratch
        self.identifiers = identifiers
        self.redirects = redirects or {}  # APPDATA and LOCALAPPDATA of the child, for Godot's user data
        self.token_dir = token_dir  # the one folder that holds everything this launch writes, and the token
        self.token = token  # nonce, token_dir and the path of every redirected variable


def _mentions(value, roots, environ):
    """True when `value` (a path, a list of paths or a command line) names one of `roots`."""
    text = _expand(value, environ).replace("/", "\\").lower()
    needles = set()
    for root in roots:
        needles.add(normalise(root))
        needles.add(ntpath.normcase(ntpath.normpath(root)))
    for needle in needles:
        for m in re.finditer(re.escape(needle), text):
            tail = text[m.end():m.end() + 1]
            if tail in ("", "\\", ";", '"', "'", " ", "\t"):
                return True
    return False


def remove_scratch(folder):
    """Removes a scratch folder this module's helpers created. It refuses (returns False) anything that is
    not a folder whose first component under the temporary folder starts with `vv-`: a drive or profile
    root, the temporary folder itself, a path elsewhere. Returns True when it removed the folder."""
    try:
        real = os.path.normcase(os.path.realpath(folder))
        temp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    except (OSError, ValueError, TypeError):
        return False
    rel = os.path.relpath(real, temp) if os.path.splitdrive(real)[0] == os.path.splitdrive(temp)[0] else ".."
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if not parts or parts[0] in (".", "..") or not parts[0].startswith("vv-"):
        return False
    for protected in (os.environ.get("USERPROFILE"), os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA"), os.path.expanduser("~")):
        if protected and real == os.path.normcase(os.path.realpath(protected)):
            return False
    shutil.rmtree(real, ignore_errors=True)
    return True


def plan_launch(exe, environ, local_appdata, appdata, *, port=None, allow_release=False,
                documents=None, identifier_reader=embedded_identifiers, make_scratch=None):
    """Decides how to start `exe`, or raises IsolationError. Touches no real profile; with the default
    arguments it reads `exe` once and creates scratch folders for the variables `environ` leaves unset.
    When it refuses after creating folders, it removes them."""
    created = []
    try:
        return _plan_launch(exe, environ, local_appdata, appdata, port, allow_release, documents, identifier_reader, make_scratch, created)
    except BaseException:
        for folder in created:
            remove_scratch(folder)
        raise


def _plan_launch(exe, environ, local_appdata, appdata, port, allow_release, documents, identifier_reader, make_scratch, created):
    if not local_appdata or not appdata:
        raise IsolationError("LOCALAPPDATA and APPDATA must be known to check the launch")
    roots = protected_roots(local_appdata, appdata, documents)
    install = ntpath.join(local_appdata, INSTALL_FOLDER)

    exe_path = normalise(exe)
    if not allow_release:
        if is_under(exe_path, install):
            raise IsolationError(f"{exe} is in the installed application folder; only the owner may start it ({OWNER_FLAG})")
        try:
            ids = identifier_reader(exe)
        except OSError as e:
            raise IsolationError(f"cannot read {exe} to check its identifier: {e}") from e
        if RELEASE_IDENTIFIER in ids:
            raise IsolationError(f"{exe} carries the release identifier {RELEASE_IDENTIFIER}; build it without -Release or pass {OWNER_FLAG}")
        if DEV_IDENTIFIER not in ids:
            raise IsolationError(f"{exe} carries neither known identifier; its provenance is unknown")
    else:
        ids = None

    env = dict(environ)
    # Everything the caller or the shell already set must stay out of the installed profile.
    for name, value in environ.items():
        if _mentions(value, roots, environ):
            raise IsolationError(f"{name} points into the installed application's data: {value}")
    args = environ.get(BROWSER_ARGUMENTS, "")
    if "user-data-dir" in args.lower():
        raise IsolationError(f"{BROWSER_ARGUMENTS} sets a user data directory, which would override the scratch profile: {args}")

    # A folder the caller already chose for one of these variables is replaced below, but one that lies
    # in the installed data is a mistake worth refusing loudly, whatever way it is spelled.
    for name in SCRATCH_VARIABLES:
        value = environ.get(name)
        if value and any(is_under(_expand(value, environ), r) for r in roots):
            raise IsolationError(f"{name} resolves into the installed application's data: {value}")
    # One token directory per launch holds every folder the Studio writes and the launch token. The
    # development Studio's runtime guard (desktop/studio/src/guard.rs) refuses to start unless each of
    # these variables is the value recorded in the token and lies inside the token directory, so folders
    # chosen by the caller are replaced by folders under it.
    root = make_scratch("TOKEN_DIR") if make_scratch else tempfile.mkdtemp(prefix="vv-launch-")
    created.append(root)
    scratch = {name: os.path.join(root, TOKEN_SUBFOLDERS[name]) for name in SCRATCH_VARIABLES}
    redirects = {name: os.path.join(root, TOKEN_SUBFOLDERS[name]) for name in ("APPDATA", "LOCALAPPDATA")}
    env.update(scratch)
    for name in SCRATCH_VARIABLES:
        if any(is_under(env[name], r) for r in roots):
            raise IsolationError(f"{name} resolves into the installed application's data: {env[name]}")
    if port is not None and BROWSER_ARGUMENTS not in env:
        env[BROWSER_ARGUMENTS] = f"--remote-debugging-port={port}"
    # Godot, when the Studio starts the Cinematic View, keeps its user data under APPDATA and its cache
    # under LOCALAPPDATA (read from the environment). The Studio and WebView2 take their folders from the
    # known-folder API and from the variables above, so redirecting these two for the child only sends
    # the Cinematic View's user data to the token directory. See godot_launch.py.
    for name, folder in redirects.items():
        env[name] = folder
        for real in (appdata, local_appdata):
            if (is_under(folder, ntpath.join(real, CINEMATIC_FOLDER)) or any(is_under(folder, r) for r in roots)
                    or normalise(folder) in (normalise(appdata), normalise(local_appdata))):
                raise IsolationError(f"{name} for the child resolves to {folder}, the installed data or the real profile root")
    token = {"nonce": secrets.token_hex(16), "token_dir": root, "paths": {**scratch, **redirects}}
    env[ENV_LAUNCH] = os.path.join(root, TOKEN_FILE)
    env[ENV_NONCE] = token["nonce"]
    return LaunchPlan(os.path.abspath(exe), env, scratch, ids, redirects, root, token)


def write_token(plan):
    """Creates the token directory's folders and writes the single-use launch token the guard reads."""
    for folder in [plan.token_dir, *plan.token["paths"].values()]:
        os.makedirs(folder, exist_ok=True)
    with open(plan.env[ENV_LAUNCH], "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan.token, f, indent=1)
        f.write("\n")


def same_exe_running(exe):
    """PIDs of running processes whose executable path is exactly `exe`. Read-only. The single-instance
    plugin would hand a second launch of the same identifier to the first one."""
    ps = "Get-CimInstance Win32_Process -Filter \"Name='{}'\" | ForEach-Object {{ \"$($_.ProcessId)|$($_.ExecutablePath)\" }}".format(
        os.path.basename(exe).replace("'", "''"))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    mine = normalise(exe)
    pids = []
    for line in out.splitlines():
        pid, _, path = line.partition("|")
        if pid.strip().isdigit() and path and normalise(path) == mine:
            pids.append(int(pid))
    return pids


def launch(exe, env, port, *, allow_release=False, wait_seconds=20):
    """Starts `exe` under `plan_launch` and returns the Popen. Waits for the DevTools port when
    `wait_seconds` is positive. A Studio from the same executable already running is an error: it is
    never killed here."""
    plan = plan_launch(
        os.path.abspath(os.path.expandvars(exe)), env,
        os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", ""),
        port=port, allow_release=allow_release,
        documents=documents_folders(),
    )
    running = same_exe_running(plan.exe)
    if running:
        remove_scratch(plan.token_dir)
        raise IsolationError(f"{plan.exe} is already running (PID {', '.join(map(str, running))}); close it, this script never kills it")
    write_token(plan)
    proc = subprocess.Popen([plan.exe], env=plan.env)
    # The token directory holds every temporary folder of the child (the redirected APPDATA and
    # LOCALAPPDATA and the scratch ones for WEBVIEW2_USER_DATA_FOLDER, VVLAB_LIBRARY, VVLAB_CONFIG,
    # VVLAB_MODULES) and the token; stop() removes it.
    proc.launch_plan = plan
    proc.redirect_dirs = [plan.token_dir]
    proc.godot_appdata = plan.redirects.get("APPDATA")  # where a Godot started by this Studio writes its user data
    proc.spawn_time = time.time()  # for start-up measurements: the checks above are not part of the start
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    return proc


def stop(proc):
    """Ends the process this module started, and only that one, and removes its temporary folders."""
    if proc is None:
        return
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
    for folder in getattr(proc, "redirect_dirs", []):
        # WebView2's child processes can keep files open for a moment after the Studio ends: retry briefly.
        for _ in range(20):
            if not remove_scratch(folder) or not os.path.exists(folder):
                break
            time.sleep(0.5)


def guard_probe(exe, env, *, args=("--guard-only",), timeout=30):
    """Runs a DEVELOPMENT executable with `args` (by default `--guard-only`: the runtime guard prints its
    decision and exits before Tauri) in exactly the environment `env`, and returns the CompletedProcess.
    For the guard's tests only: the executable must carry the development identifier (checked), and the
    environment is the caller's, so tests pass disposable folders. With another argument list the
    executable would start normally if the guard allowed it; it is killed at `timeout`."""
    exe = os.path.abspath(exe)
    ids = embedded_identifiers(exe)
    if RELEASE_IDENTIFIER in ids or DEV_IDENTIFIER not in ids:
        raise IsolationError(f"{exe} is not a development build (identifiers {sorted(ids)}); the guard probe refuses it")
    return subprocess.run([exe, *args], env=env, capture_output=True, text=True, timeout=timeout)


def child_pids(parent_pid, name_prefix):
    """Processes started by `parent_pid` whose name starts with `name_prefix` (Godot launched by the
    Studio, for example); never other processes of the same name."""
    ps = (f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={int(parent_pid)}' | "
          f"Where-Object {{ $_.Name -like '{name_prefix}*' }} | ForEach-Object {{ $_.ProcessId }}")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def kill_pid(pid):
    subprocess.run(["taskkill", "/F", "/PID", str(int(pid))], capture_output=True)
