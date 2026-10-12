#!/usr/bin/env python3
"""Targeted repair of installer-managed BIND DNS; no dependency or database migrations."""
import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile

SOURCE = Path(__file__).resolve().parent.parent
DEST = Path("/opt/mikapanels")
CONFIG = Path("/etc/mikapanels")
FILES = ["hosting/dns_wire.py", "hosting/dns.py", "hosting/management/commands/rebuild_dns.py",
         "hosting/management/commands/provision_worker.py", "tools/system_services.py", "tools/check_dns.py"]


def open_dns_firewall():
    """Add DNS rules only when UFW is already active; never enable/reset it."""
    if not shutil.which("ufw"):
        print("UFW tidak terpasang. Pastikan firewall provider mengizinkan TCP/UDP 53.")
        return
    env = {**os.environ, "LC_ALL": "C"}
    state = subprocess.run(["ufw", "status"], check=True, capture_output=True, text=True, env=env)
    if "Status: active" in state.stdout:
        for protocol in ["udp", "tcp"]:
            subprocess.run(["ufw", "allow", "53/" + protocol], check=True, env=env)
        print("UFW aktif: TCP/UDP 53 diizinkan. Firewall provider tetap perlu diperiksa.")
    else:
        print("UFW tidak aktif; konfigurasi firewall dipertahankan. Periksa firewall provider.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--domain", help="Only an existing hosting domain; omit to rebuild all existing zones")
    args = parser.parse_args()
    if args.plan_only:
        print("Backup privat kode/config/SQLite panel; patch DNS dan log worker; hubungkan include zone BIND; validasi; restart named; publikasi ulang zone yang sudah ada; buka TCP/UDP 53 hanya bila UFW sudah aktif. Tidak membuat akun hosting, tidak mengubah kunci/API/pembayaran, dan tidak mengubah DNS Cloudflare/registrar.")
        return
    if os.geteuid() != 0:
        raise SystemExit("Jalankan sebagai root pada VPS.")
    release = Path("/etc/os-release").read_text()
    if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
        raise SystemExit("Helper hanya mendukung Ubuntu 24.04.")
    if SOURCE == DEST or not (DEST / ".venv/bin/python").exists() or not (CONFIG / "panel.env").exists():
        raise SystemExit("Gunakan clone source baru di luar /opt/mikapanels pada VPS instalasi MikaPanels.")
    from system_services import configure_dns, dns_preflight, load_environment, add_environment
    values = load_environment(CONFIG / "panel.env")
    if values.get("MIKA_SERVICE") != "panel" or values.get("MIKA_PROVISION_MODE") != "system":
        raise SystemExit("panel.env harus memakai service panel dan mode system.")
    bind_dir = Path(values.get("MIKA_BIND_DIR", "/etc/bind"))
    dns_preflight(bind_dir)
    for name in FILES:
        if not (SOURCE / name).is_file():
            raise SystemExit("Source patch DNS belum lengkap.")
    for name in ["named-checkzone", "named-checkconf", "rndc"]:
        if not shutil.which(name):
            raise SystemExit("BIND9 belum lengkap. Pasang bind9 dan bind9-utils sebelum perbaikan.")
    os.umask(0o007)
    with (CONFIG / "update.lock").open("a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Update/perbaikan lain masih berjalan.")
        backup = Path("/var/backups") / ("mikapanels-dns-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
        backup.mkdir(mode=0o700)
        with tarfile.open(backup / "dns-code-config.tar.gz", "w:gz") as archive:
            for name in FILES:
                path = DEST / name
                if path.exists():
                    archive.add(path, arcname="opt/mikapanels/" + name)
            archive.add(CONFIG / "panel.env", arcname="etc/mikapanels/panel.env")
            archive.add(bind_dir, arcname=str(bind_dir).lstrip("/"))
        data_dir = Path(values["MIKA_DATA_DIR"])
        database = data_dir / "panel.sqlite3"
        if not database.exists():
            raise SystemExit("Database panel belum ditemukan; perbaikan dihentikan.")
        with sqlite3.connect(database) as original, sqlite3.connect(backup / "panel.sqlite3") as copy:
            original.backup(copy)
        print(f"Cadangan privat: {backup}", flush=True)
        subprocess.run(["systemctl", "stop", "mika-provision"], check=True)
        try:
            for name in FILES:
                target = DEST / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / name, target)
                shutil.chown(target, user="root", group="root")
                target.chmod(0o644)
            # Preserve explicit service settings. If DNS is disabled, require the operator
            # to enable it rather than silently changing a deliberate configuration.
            values = add_environment(CONFIG / "panel.env", {"MIKA_DNS_ENABLED": "1"})
            if values["MIKA_DNS_ENABLED"] != "1":
                raise RuntimeError("DNS dinonaktifkan secara eksplisit pada panel.env. Ubah MIKA_DNS_ENABLED menjadi 1 lalu ulangi helper.")
            configure_dns(bind_dir)
            subprocess.run(["systemctl", "enable", "--now", "named"], check=True)
            subprocess.run(["systemctl", "restart", "named"], check=True)
            subprocess.run(["rndc", "status"], check=True, capture_output=True)
            open_dns_firewall()
            command = [str(DEST / ".venv/bin/python"), "manage.py", "rebuild_dns"]
            if args.domain:
                command += ["--domain", args.domain]
            base_env = {key: value for key, value in os.environ.items() if not key.startswith(("MIKA_", "MYCHA_", "TRIPAY_"))}
            subprocess.run(command, env={**base_env, **values}, cwd=DEST, check=True)
            print("Zone yang ada berhasil diperiksa. Jalankan tools/check_dns.py --domain DOMAIN untuk alamat NS/delegasi publik.")
            print("Bila nameserver belum punya A/glue atau port 53 diblokir provider, perbaiki pengaturan eksternal tersebut. Domain induk harus memiliki zone tersendiri.")
        except Exception:
            print(f"Perbaikan belum lengkap. Cadangan tersedia di {backup}; tidak ada restore database otomatis.", flush=True)
            raise
        finally:
            subprocess.run(["systemctl", "start", "mika-provision"], check=True)


if __name__ == "__main__":
    main()
