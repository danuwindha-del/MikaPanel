#!/usr/bin/env python3
"""Read-only diagnostics: systemd, Gunicorn, local Nginx TLS, public domain."""
from pathlib import Path
import subprocess
import sys

# Support running the file directly and importing it in tests.
if __package__:
    from .system_services import load_environment
    from .vps_health import probe_health
else:
    from system_services import load_environment
    from vps_health import probe_health


def main():
    failed = False
    for service, unit, port, key in [("panel", "mikapanels", 8001, "MIKA_PANEL_URL"), ("shop", "mychahost", 8002, "MYCHA_PUBLIC_URL")]:
        values = load_environment(Path(f"/etc/mikapanels/{service}.env"))
        state = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
        # Do not include arbitrary process output or EnvironmentFile values.
        print(f"{unit}: {'active' if state.returncode == 0 else 'tidak aktif'}")
        for label, kwargs in [("Gunicorn lokal", {"backend_port": port}), ("Nginx TLS lokal", {"local_https": True}), ("HTTPS domain", {})]:
            result = probe_health(values[key], service, **kwargs)
            print(f"{service} / {label}: {result.detail}")
            failed |= not result.ok
    if failed:
        print("Belum semua jalur sehat. Periksa journalctl -u mikapanels -u mychahost -u nginx; jangan mengulang instalasi atau menghapus data.")
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, subprocess.CalledProcessError):
        raise SystemExit("Konfigurasi belum dapat dibaca. Jalankan sebagai root pada VPS yang dipasang installer.")
