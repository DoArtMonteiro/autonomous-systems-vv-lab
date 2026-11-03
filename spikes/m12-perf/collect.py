"""Copy the M12 audit measurements from runs/m12-perf into docs/evidence/m12-perf, sanitised.

Removes absolute paths (repository root and user profile become `<repo>` and `<home>`), drops the
job IO counters (the Job Object did not populate them on the audit machine, so they are not
measurements) and keeps at most 40 time samples per report.

usage: python spikes/m12-perf/collect.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "runs" / "m12-perf"
DST = ROOT / "docs" / "evidence" / "m12-perf"
DROP = {"io_read_mb", "io_write_mb"}


def scrub(value, subs):
    if isinstance(value, dict):
        return {k: scrub(v, subs) for k, v in value.items() if k not in DROP}
    if isinstance(value, list):
        return [scrub(v, subs) for v in value]
    if isinstance(value, str):
        for old, new in subs:
            value = value.replace(old, new).replace(old.replace("\\", "/"), new)
        return value
    return value


def main() -> None:
    home = os.environ.get("USERPROFILE", str(Path.home()))
    subs = [(str(ROOT), "<repo>"), (home, "<home>")]
    user = os.environ.get("USERNAME", Path(home).name)
    DST.mkdir(parents=True, exist_ok=True)
    names = sorted(SRC.glob("*.json"))
    for p in names:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data.get("samples"), list) and len(data["samples"]) > 40:
            step = -(-len(data["samples"]) // 40)
            data["samples"] = data["samples"][::step]
        text = json.dumps(scrub(data, subs), indent=1, ensure_ascii=False) + "\n"
        if user and user.lower() in text.lower():
            raise SystemExit(f"{p.name}: still contains the user name")
        (DST / p.name).write_text(text, encoding="utf-8")
    for csv in sorted(SRC.glob("gpu-*.csv")):
        (DST / csv.name).write_text(csv.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{len(names)} reports copied to {DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
