#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in {"panel", "shop"}:
        raise SystemExit("Usage: python tools/run.py {panel|shop} <manage.py command> [args]")
    path = ROOT / "var" / "config.json"
    if not path.exists():
        raise SystemExit("Run python tools/configure.py first")
    env = {**os.environ, **json.loads(path.read_text())[sys.argv[1]]}
    # Explicit caller overrides are useful for isolated test DBs and sandbox credentials.
    for key, value in os.environ.items():
        if key.startswith(("MIKA_", "MYCHA_", "TRIPAY_")):
            env[key] = value
    env["MIKA_SERVICE"] = sys.argv[1]
    os.chdir(ROOT)
    os.execve(sys.executable, [sys.executable, str(ROOT / "manage.py"), *sys.argv[2:]], env)


if __name__ == "__main__":
    main()
