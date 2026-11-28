r"""The only way tests and scripts start Godot (the Cinematic View renderer).

Why this exists: Godot keeps its user data in `%APPDATA%\<custom_user_dir_name>` (here
`%APPDATA%\VV Lab Cinematic`, set in `desktop/cinematic/project.godot`) and its cache under
`%LOCALAPPDATA%`. That folder is shared with the installed Studio's Cinematic module. Every Godot run,
headless or not, writes `logs/godot.log` and a rotated `godot<timestamp>.log` there; a rendering run
also writes the shader cache and the Vulkan pipeline cache. On 2026-11-23 runs of the Cinematic tests
and renders wrote into it (docs/incidents/2026-11-23-webview2-profile.md).

What this does: starts Godot with `APPDATA` and `LOCALAPPDATA` (and, off Windows, the XDG folders and
`HOME`) pointing at scratch folders in the CHILD environment only, and refuses to start when the
resolved user folder would lie in the installed `%APPDATA%\VV Lab Cinematic` or
`%LOCALAPPDATA%\VV Lab Cinematic`. Godot 4.7.2 was observed to honour `APPDATA` and `LOCALAPPDATA` this
way (a probe project with its own user folder name, redirected: user data under the scratch `APPDATA`,
cache under the scratch `LOCALAPPDATA`, nothing in the real `%APPDATA%`).

Godot started by the Studio (the Cinematic button) inherits the Studio's environment, which
`studio_launch.plan_launch` redirects the same way.

`tests/test_studio_isolation.py` tests the rules without starting Godot and fails if any script or test
starts Godot by another route. That lint guards against accidents, not adversaries.
"""

import ntpath
import os
import subprocess
import tempfile

import studio_launch as sl

CINEMATIC_APP_NAME = "VV Lab Cinematic"  # config/custom_user_dir_name of desktop/cinematic/project.godot
APP_NAMES = (CINEMATIC_APP_NAME,)
POSIX_REDIRECTS = ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "HOME")


class GodotPlan:
    def __init__(self, argv, env, scratch, user_dirs):
        self.argv = argv
        self.env = env
        self.scratch = scratch  # variable -> scratch folder
        self.user_dirs = user_dirs  # app name -> resolved user data folder

    @property
    def user_dir(self):
        return self.user_dirs[CINEMATIC_APP_NAME]


def protected_godot_roots(appdata, local_appdata, app_names=APP_NAMES):
    """The user data and cache folders of the installed Cinematic module."""
    roots = []
    for name in app_names:
        roots += [ntpath.join(appdata, name), ntpath.join(local_appdata, name)]
    return roots


def plan_godot(argv, environ, appdata, local_appdata, *, make_scratch=None, app_names=APP_NAMES):
    """Decides how to start Godot with `argv`, or raises sl.IsolationError. `appdata` and `local_appdata`
    are the real folders of this user, from which the installed module's folders are derived."""
    if not appdata or not local_appdata:
        raise sl.IsolationError("APPDATA and LOCALAPPDATA must be known to check a Godot launch")
    if not argv:
        raise sl.IsolationError("empty Godot command line")
    make = make_scratch or (lambda name: tempfile.mkdtemp(prefix=f"vv-godot-{name.lower()}-"))
    created = []
    try:
        env = dict(environ)
        scratch = {}
        for name in ("APPDATA", "LOCALAPPDATA") + (POSIX_REDIRECTS if os.name != "nt" else ()):
            scratch[name] = make(name)
            created.append(scratch[name])
            env[name] = scratch[name]
        roots = protected_godot_roots(appdata, local_appdata, app_names)
        # Where Godot keeps user data and cache: APPDATA and LOCALAPPDATA on Windows, the XDG folders elsewhere.
        data_var, cache_var = ("APPDATA", "LOCALAPPDATA") if os.name == "nt" else ("XDG_DATA_HOME", "XDG_CACHE_HOME")
        user_dirs = {}
        for name in app_names:
            user = ntpath.join(env[data_var], name)
            user_dirs[name] = user
            for folder in (user, ntpath.join(env[cache_var], name), env[data_var], env[cache_var]):
                if any(sl.is_under(folder, r) for r in roots) or sl.normalise(folder) in (sl.normalise(appdata), sl.normalise(local_appdata)):
                    raise sl.IsolationError(f"Godot's user folder would resolve to {folder}, the installed module's data or the real profile root")
        return GodotPlan(list(argv), env, scratch, user_dirs)
    except BaseException:
        for folder in created:
            sl.remove_scratch(folder)
        raise


def real_roots(environ=None):
    """The real user data and cache roots: APPDATA and LOCALAPPDATA on Windows; off Windows the XDG data
    and cache folders, or their defaults under the home folder."""
    environ = os.environ if environ is None else environ
    if os.name == "nt":
        return environ.get("APPDATA", ""), environ.get("LOCALAPPDATA", "")
    home = os.path.expanduser("~")
    return (environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"),
            environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"))


def _plan(argv, kw):
    environ = kw.pop("env", None)
    appdata, local_appdata = real_roots()
    return plan_godot(argv, os.environ if environ is None else environ, appdata, local_appdata)


def remove_scratch(folder):
    """Removes a scratch folder of a plan (only a `vv-` folder under the temporary folder)."""
    return sl.remove_scratch(folder)


def run(argv, **kw):
    """subprocess.run of Godot under plan_godot. Returns the CompletedProcess; the scratch folders are
    removed afterwards unless `keep_user_data=True` (then `result.godot_plan` names them)."""
    keep = kw.pop("keep_user_data", False)
    plan = _plan(argv, kw)
    try:
        result = subprocess.run(plan.argv, env=plan.env, **kw)
        result.godot_plan = plan
        return result
    finally:
        if not keep:
            for folder in plan.scratch.values():
                sl.remove_scratch(folder)


def popen(argv, **kw):
    """subprocess.Popen of Godot under plan_godot. `proc.godot_plan` names the scratch folders; the
    caller removes them when done (they are temporary folders)."""
    plan = _plan(argv, kw)
    proc = subprocess.Popen(plan.argv, env=plan.env, **kw)
    proc.godot_plan = plan
    return proc
