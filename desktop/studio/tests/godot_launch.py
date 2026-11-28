r"""The only way tests and scripts start Godot (the Cinematic View renderer).

Why this exists: Godot keeps its user data in `%APPDATA%\<custom_user_dir_name>` and its cache under
`%LOCALAPPDATA%`. The installed module's folder, `%APPDATA%\VV Lab Cinematic`, is shared with the
installed Studio. Every Godot run, headless or not, writes `logs/godot.log` and a rotated
`godot<timestamp>.log` there; a rendering run also writes the shader cache and the Vulkan pipeline
cache. On 2026-11-23 runs of the Cinematic tests and renders wrote into it
(docs/incidents/2026-11-23-webview2-profile.md).

Two layers, each enough on its own to keep a run out of that folder:

1. Name. The repository's `desktop/cinematic/project.godot` is the DEVELOPMENT project: its user
   folder name is `VV Lab Cinematic Dev`. Only `scripts/cinematic/package_module.py` stamps the release
   name when it packages the module. A run from the repository therefore writes into
   `%APPDATA%\VV Lab Cinematic Dev` even if nothing else is done.
2. Launch. This helper starts Godot with `APPDATA` and `LOCALAPPDATA` (and, off Windows, the XDG folders
   and `HOME`) pointing at one scratch token directory, in the CHILD environment only, refuses to start
   when the resolved user folder would lie in the installed `%APPDATA%\VV Lab Cinematic` or
   `%LOCALAPPDATA%\VV Lab Cinematic`, and writes the launch token (`VVLAB_DEV_LAUNCH`, `VVLAB_DEV_NONCE`)
   that the development project's first autoload (`scripts/guard.gd`) checks. Godot 4.7.2 was observed to
   honour `APPDATA` and `LOCALAPPDATA` this way (a probe project redirected: user data under the scratch
   `APPDATA`, cache under the scratch `LOCALAPPDATA`, nothing in the real `%APPDATA%`).

The autoload runs after Godot has started; Godot may already have created its log file and caches by
then, so the structural development name is the real protection and the autoload is defence in depth.

Godot started by the Studio (the Cinematic button) inherits the Studio's environment, which
`studio_launch.plan_launch` redirects the same way; the module it starts is a packaged one, with the
release name.

`tests/test_studio_isolation.py` tests the rules without starting Godot and fails if any script or test
starts Godot by another route. That lint guards against accidents, not adversaries.
"""

import json
import ntpath
import os
import secrets
import subprocess
import tempfile

import studio_launch as sl

CINEMATIC_APP_NAME = "VV Lab Cinematic"  # the installed module's user folder (custom_user_dir_name when packaged)
CINEMATIC_DEV_NAME = "VV Lab Cinematic Dev"  # custom_user_dir_name of desktop/cinematic/project.godot
APP_NAMES = (CINEMATIC_APP_NAME, CINEMATIC_DEV_NAME)
POSIX_REDIRECTS = ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "HOME")


class GodotPlan:
    def __init__(self, argv, env, scratch, user_dirs, root=None, token=None):
        self.argv = argv
        self.env = env
        self.scratch = scratch  # variable -> scratch folder, all inside `root`
        self.user_dirs = user_dirs  # app name -> resolved user data folder
        self.root = root  # the token directory
        self.token = token  # nonce, token_dir, paths and the protected folders

    @property
    def user_dir(self):
        return self.user_dirs[CINEMATIC_APP_NAME]

    @property
    def dev_user_dir(self):
        return self.user_dirs[CINEMATIC_DEV_NAME]


def protected_godot_roots(appdata, local_appdata, app_names=(CINEMATIC_APP_NAME,)):
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
    created = []
    try:
        root = make_scratch("TOKEN_DIR") if make_scratch else tempfile.mkdtemp(prefix="vv-godot-")
        created.append(root)
        env = dict(environ)
        names = ("APPDATA", "LOCALAPPDATA") + (POSIX_REDIRECTS if os.name != "nt" else ())
        scratch = {name: os.path.join(root, name.lower()) for name in names}
        env.update(scratch)
        # The installed module's folders, under the name it ships with, and the same names under the
        # development name (a scratch folder is never meant to be in either).
        roots = protected_godot_roots(appdata, local_appdata, (CINEMATIC_APP_NAME,))
        # Where Godot keeps user data and cache: APPDATA and LOCALAPPDATA on Windows, the XDG folders elsewhere.
        data_var, cache_var = ("APPDATA", "LOCALAPPDATA") if os.name == "nt" else ("XDG_DATA_HOME", "XDG_CACHE_HOME")
        user_dirs = {}
        for name in app_names:
            user = ntpath.join(env[data_var], name)
            user_dirs[name] = user
            for folder in (user, ntpath.join(env[cache_var], name), env[data_var], env[cache_var], root):
                if any(sl.is_under(folder, r) for r in roots) or sl.normalise(folder) in (sl.normalise(appdata), sl.normalise(local_appdata)):
                    raise sl.IsolationError(f"Godot's user folder would resolve to {folder}, the installed module's data or the real profile root")
        token = {"nonce": secrets.token_hex(16), "token_dir": root, "paths": dict(scratch),
                 "protected": protected_godot_roots(appdata, local_appdata, app_names)}
        env[sl.ENV_LAUNCH] = os.path.join(root, sl.TOKEN_FILE)
        env[sl.ENV_NONCE] = token["nonce"]
        return GodotPlan(list(argv), env, scratch, user_dirs, root, token)
    except BaseException:
        for folder in created:
            sl.remove_scratch(folder)
        raise


def write_token(plan):
    """Creates the token directory's folders and writes the launch token the development project reads."""
    for folder in [plan.root, *plan.scratch.values()]:
        os.makedirs(folder, exist_ok=True)
    with open(plan.env[sl.ENV_LAUNCH], "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan.token, f, indent=1)
        f.write("\n")


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
    plan = plan_godot(argv, os.environ if environ is None else environ, appdata, local_appdata)
    write_token(plan)
    return plan


def remove_scratch(folder):
    """Removes a scratch folder of a plan (only a `vv-` folder under the temporary folder)."""
    return sl.remove_scratch(folder)


def run(argv, **kw):
    """subprocess.run of Godot under plan_godot. Returns the CompletedProcess; the token directory is
    removed afterwards unless `keep_user_data=True` (then `result.godot_plan` names it)."""
    keep = kw.pop("keep_user_data", False)
    plan = _plan(argv, kw)
    try:
        result = subprocess.run(plan.argv, env=plan.env, **kw)
        result.godot_plan = plan
        return result
    finally:
        if not keep:
            sl.remove_scratch(plan.root)


def popen(argv, **kw):
    """subprocess.Popen of Godot under plan_godot. `proc.godot_plan` names the token directory; the
    caller removes it when done (`remove_scratch(proc.godot_plan.root)`)."""
    plan = _plan(argv, kw)
    proc = subprocess.Popen(plan.argv, env=plan.env, **kw)
    proc.godot_plan = plan
    return proc
