#!/usr/bin/env python3
"""Upgrade installer-managed MikaPanels without replacing secrets or hosting files."""
import argparse
import fcntl
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.request
import json
from urllib.parse import urlsplit

SOURCE = Path(__file__).resolve().parent.parent
DEST = Path("/opt/mikapanels")
CONFIG = Path("/etc/mikapanels")
SERVICES = ["mikapanels", "mychahost", "mika-provision", "mycha-orders"]
EXCLUDED = {".git", ".venv", ".venv-update", "var", "__pycache__", ".pytest_cache", ".env", ".ruff_cache"}


def source_files(source):
    for path in source.rglob("*"):
        parts = path.relative_to(source).parts
        if path.is_file() and not path.is_symlink() and not any(part in EXCLUDED or part.startswith(".env") or part.endswith(".egg-info") for part in parts):
            yield path


def run(args, env=None):
    subprocess.run(args, check=True, cwd=DEST, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    options = parser.parse_args()
    if options.plan_only:
        print("Ubuntu 24.04: backup kode, environment, SQLite, BIND/MySQL/Nginx; pasang BIND9/MariaDB/PHP MySQL; update dependensi dengan hash; hentikan empat layanan; migrasi; collectstatic; konfigurasi DNS authoritative; refresh hosting lama; mulai layanan dan periksa health. Data website dan kunci Tripay dipertahankan. Buka TCP/UDP 53 dan arahkan nameserver secara terpisah.")
        return
    if os.geteuid() != 0:
        raise SystemExit("Jalankan sebagai root pada VPS.")
    release = Path("/etc/os-release").read_text()
    if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
        raise SystemExit("Helper hanya mendukung Ubuntu 24.04.")
    if SOURCE == DEST or not (DEST / ".venv/bin/python").exists() or not (CONFIG / "panel.env").exists():
        raise SystemExit("Gunakan clone source baru, di luar /opt/mikapanels, pada VPS yang sudah dipasang installer.")
    update_lock = (CONFIG / "update.lock").open("a")
    os.fchmod(update_lock.fileno(), 0o600)
    try:
        fcntl.flock(update_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Updater lain sedang berjalan. Tunggu proses tersebut selesai.")
    if (DEST / ".venv-update").exists():
        raise SystemExit(".venv-update sudah ada dari update sebelumnya. Periksa folder dan cadangan sebelum mencoba ulang.")
    from system_services import dns_preflight, configure_services, load_environment, add_environment
    dns_preflight()
    environments = {service: load_environment(CONFIG / f"{service}.env") for service in ["panel", "shop"]}
    shop_domain = urlsplit(environments["panel"]["MYCHA_PUBLIC_URL"]).hostname or ""
    if len(shop_domain) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", shop_domain):
        raise SystemExit("Domain toko pada environment tidak valid.")
    backup = Path("/var/backups") / ("mikapanels-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    backup.mkdir(mode=0o700)
    print(f"Cadangan privat: {backup}", flush=True)
    with tarfile.open(backup / "code-and-config.tar.gz", "w:gz") as archive:
        for path in source_files(DEST):
            archive.add(path, arcname="opt/mikapanels/" + str(path.relative_to(DEST)), recursive=False)
        for path in [CONFIG, Path("/etc/bind"), Path("/etc/mysql"), Path("/etc/nginx"), Path("/etc/php/8.3/fpm/pool.d")]:
            if path.exists():
                archive.add(path, arcname=str(path).lstrip("/"))
    for service, values in environments.items():
        data = Path(values["MIKA_DATA_DIR"])
        for path in data.glob("*.sqlite3"):
            with sqlite3.connect(path) as connection, sqlite3.connect(backup / f"{service}-{path.name}") as copy:
                connection.backup(copy)
    print("Menyiapkan BIND9, MariaDB, dan driver PHP MySQL…", flush=True)
    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", "bind9", "bind9-utils", "mariadb-server", "php8.3-mysql"])
    # Install into a new venv first; an installation failure leaves the live code intact.
    staged = DEST / ".venv-update"
    run(["python3.12", "-m", "venv", str(staged)])
    run([str(staged / "bin/pip"), "install", "--require-hashes", "-r", str(SOURCE / "requirements.lock")])
    run(["systemctl", "stop", *SERVICES])
    # Snapshot again after writers stop, so rollback includes the latest transactions.
    for service, values in environments.items():
        for path in Path(values["MIKA_DATA_DIR"]).glob("*.sqlite3"):
            with sqlite3.connect(path) as connection, sqlite3.connect(backup / f"{service}-{path.name}") as copy:
                connection.backup(copy)
    # A venv contains absolute shebangs. Build at the final path after retaining the old one.
    shutil.move(DEST / ".venv", backup / "old-venv")
    try:
        run(["python3.12", "-m", "venv", str(DEST / ".venv")])
        run([str(DEST / ".venv/bin/pip"), "install", "--require-hashes", "-r", str(SOURCE / "requirements.lock")])
        for path in source_files(SOURCE):
            target = DEST / path.relative_to(SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            target.chmod(0o755 if os.access(path, os.X_OK) else 0o644)
            shutil.chown(target, user="root", group="root")
        configure_services()
        for service, values in environments.items():
            values = add_environment(CONFIG / f"{service}.env", {"MIKA_DNS_ENABLED": "1", "MIKA_MYSQL_ENABLED": "1",
                "MIKA_DNS_PRIMARY": "ns1." + shop_domain, "MIKA_DNS_SECONDARY": "ns2." + shop_domain})
            env = {**os.environ, **values}
            for command in [["migrate", "--noinput"], ["collectstatic", "--noinput"], ["check"]]:
                run([str(DEST / ".venv/bin/python"), "manage.py", *command], env)
            if service == "panel":
                run([str(DEST / ".venv/bin/python"), "manage.py", "initialize_features", "--refresh"], env)
            run(["chown", "-R", "mika:mika", values["MIKA_DATA_DIR"]])
            for path in Path(values["MIKA_DATA_DIR"]).glob("*.sqlite3"):
                path.chmod(0o660)
        run(["systemctl", "enable", "--now", "named", "mariadb"])
        run(["systemctl", "restart", "named", "mariadb", "php8.3-fpm"])
        run(["systemctl", "start", *SERVICES])
        run(["systemctl", "is-active", *SERVICES, "named", "mariadb"])
        for service, values in environments.items():
            url = values["MIKA_PANEL_URL" if service == "panel" else "MYCHA_PUBLIC_URL"].rstrip("/") + "/health/"
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        result = json.load(response)
                    if result == {"status": "ok", "service": service}:
                        break
                except (OSError, ValueError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Health {service} belum sesuai; periksa journalctl.")
                time.sleep(1)
            print(f"Health {service}: OK")
    except Exception:
        print(f"Update berhenti. Cadangan kode, konfigurasi, database, dan venv lama ada di {backup}. Periksa pesan terakhir sebelum melanjutkan; tidak ada rollback database otomatis.", file=sys.stderr)
        raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    print("Update selesai. Hosting lama disegarkan oleh worker. Buka port TCP/UDP 53 dan pasang A record ns1/ns2 serta delegasi domain pelanggan sesuai docs/DNS.md.")


if __name__ == "__main__":
    main()
