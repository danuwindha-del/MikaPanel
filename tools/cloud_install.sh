#!/bin/sh
set -eu
cd /workspace/MikaPanel
if [ ! -x /workspace/.venvs/mikapanels/bin/python ]; then
    python3 -m venv /workspace/.venvs/mikapanels
fi
/workspace/.venvs/mikapanels/bin/pip install --require-hashes -r requirements.lock
/workspace/.venvs/mikapanels/bin/python tools/configure.py --non-interactive
for mika_service in panel shop; do
    /workspace/.venvs/mikapanels/bin/python tools/run.py "$mika_service" migrate --noinput
    /workspace/.venvs/mikapanels/bin/python tools/run.py "$mika_service" seed_catalog
    /workspace/.venvs/mikapanels/bin/python tools/run.py "$mika_service" collectstatic --noinput
    /workspace/.venvs/mikapanels/bin/python tools/run.py "$mika_service" check
done
/workspace/.venvs/mikapanels/bin/python tools/test.py -q
