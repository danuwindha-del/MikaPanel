#!/usr/bin/env bash
# Apply the manual hosting feature to an installer-managed VPS. No database/configuration changes.
set -euo pipefail

mika_source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mika_target_dir=/opt/mikapanels
mika_files=(
  hosting/forms.py
  hosting/services.py
  hosting/views.py
  hosting/admin.py
  config/panel_urls.py
  templates/panel/create_account.html
  templates/panel/dashboard.html
  static/css/app.css
)

for mika_file in "${mika_files[@]}"; do
  test -f "$mika_source_dir/$mika_file"
done

if [[ ${1:-} == --plan-only ]]; then
  printf 'Pembaruan hosting manual: %s file kode/template ke %s; backup kode lama, restart mikapanels, dan periksa health. Database dan konfigurasi tidak diubah.\n' "${#mika_files[@]}" "$mika_target_dir"
  exit 0
fi
if [[ $# -ne 0 ]]; then
  printf 'Pemakaian: bash tools/update_manual_hosting.sh [--plan-only]\n' >&2
  exit 1
fi
if [[ $EUID -ne 0 ]]; then
  printf 'Jalankan melalui sudo/root pada VPS yang sudah dipasang installer.\n' >&2
  exit 1
fi
if [[ ! -f "$mika_target_dir/manage.py" || ! -x "$mika_target_dir/.venv/bin/python" || ! -f /etc/mikapanels/panel.env ]]; then
  printf 'Instalasi MikaPanels di /opt/mikapanels belum ditemukan. Tidak ada file yang diubah.\n' >&2
  exit 1
fi

mika_backup_dir=$(mktemp -d /var/backups/mikapanels-manual.XXXXXX)
printf 'Cadangan kode sebelum pembaruan: %s\n' "$mika_backup_dir"
for mika_file in "${mika_files[@]}"; do
  if [[ -f "$mika_target_dir/$mika_file" ]]; then
    mkdir -p "$mika_backup_dir/$(dirname -- "$mika_file")"
    cp -p "$mika_target_dir/$mika_file" "$mika_backup_dir/$mika_file"
  fi
done
for mika_file in "${mika_files[@]}"; do
  install -D -o root -g root -m 644 "$mika_source_dir/$mika_file" "$mika_target_dir/$mika_file"
done

# Load the installer-generated, root-owned environment without printing secret values.
set -a
source /etc/mikapanels/panel.env
set +a
cd "$mika_target_dir"
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check
systemctl restart mikapanels
systemctl is-active --quiet mikapanels
.venv/bin/python - <<'PY'
import json
import os
import time
import urllib.error
import urllib.request

url = os.environ["MIKA_PANEL_URL"].rstrip("/") + "/health/"
deadline = time.monotonic() + 30
while True:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.load(response)
        if data == {"status": "ok", "service": "panel"}:
            break
    except (OSError, ValueError):
        pass
    if time.monotonic() >= deadline:
        raise SystemExit("Kode telah diperbarui, tetapi health MikaPanels belum sesuai. Periksa log mikapanels; cadangan kode tersedia pada lokasi di atas.")
    time.sleep(1)
print("Health MikaPanels: OK")
PY
printf 'Pembaruan selesai. Cadangan kode: %s\n' "$mika_backup_dir"
printf 'Buka dashboard MikaPanels > Buat hosting, atau /admin/hosting/account/add/.\n'
