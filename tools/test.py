#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="mika-tests-") as data:
    env = {**os.environ, "MIKA_SECRET_KEY": "isolated-test-secret-not-for-production", "MIKA_DEBUG": "1",
           "MIKA_DATA_DIR": data, "MIKA_SERVICE": "panel"}
    result = subprocess.run([sys.executable, "-m", "pytest", *sys.argv[1:]], env=env, cwd=ROOT)
    raise SystemExit(result.returncode)
