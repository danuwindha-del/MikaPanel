#!/usr/bin/env bash
# Compatibility entry point: old targeted patches cannot safely install new migrations.
set -euo pipefail
mika_source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$mika_source_dir/tools/update_vps.py" "$@"
