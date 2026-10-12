#!/usr/bin/env python3
"""Guided install for a fresh, dedicated Ubuntu 24.04 VPS. Never run in onboarding container."""
import argparse
import getpass
import ipaddress
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()
SOURCE = Path(__file__).resolve().parent.parent
DEST = Path("/opt/mikapanels")
CONFIG = Path("/etc/mikapanels")
DATA = Path("/var/lib/mikapanels")


def prompt_admin_password():
    from django.conf import settings as password_settings
    from django.contrib.auth.password_validation import get_password_validators, validate_password
    from django.core.exceptions import ValidationError
    # Installer runs before service configuration exists. Validators do not need a database.
    if not password_settings.configured:
        password_settings.configure(USE_I18N=False)
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    from common.password_policy import PASSWORD_VALIDATORS
    validators = get_password_validators(PASSWORD_VALIDATORS)
    reasons = {
        "password_too_short": "Password terlalu pendek. Minimal 12 karakter. Silakan ketik ulang.",
        "password_too_common": "Password terlalu umum. Gunakan password yang lebih unik.",
        "password_entirely_numeric": "Password tidak boleh hanya berisi angka.",
    }
    console.print("Buat password baru untuk akun admin panel/toko. Ketikan password tidak ditampilkan di terminal.")
    while True:
        password = getpass.getpass("Password admin (minimal 12 karakter): ")
        try:
            validate_password(password, password_validators=validators)
        except ValidationError as exc:
            for error in exc.error_list:
                console.print(reasons.get(error.code, "Password belum memenuhi aturan keamanan."), style="red", markup=False)
            continue
        confirmation = getpass.getpass("Ulangi password: ")
        if password != confirmation:
            console.print("Kedua password tidak sama. Silakan ketik ulang password dan konfirmasinya.", style="red")
            continue
        return password


def run(args, env=None):
    console.print(f"[dim]Menjalankan: {args[0]}[/dim]")
    subprocess.run(args, check=True, env=env, cwd=DEST if DEST.exists() else SOURCE)


def env_file(path, values):
    # Systemd EnvironmentFile supports quoted values; no shell evaluation.
    def quote(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`') + '"'
    text = "\n".join(f"{key}={quote(value)}" for key, value in values.items()) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)
    shutil.chown(path, user="root", group="mika")


def validate_domain(value):
    value = value.strip().lower()
    if len(value) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
        raise SystemExit("Domain tidak valid")
    return value


def unit(name, description, service, command, root=False):
    user = "root" if root else "mika"
    content = f"""[Unit]
Description={description}
After=network-online.target nginx.service
Wants=network-online.target
[Service]
Type=simple
User={user}
Group=mika
WorkingDirectory={DEST}
EnvironmentFile={CONFIG}/{service}.env
ExecStart={DEST}/.venv/bin/{command}
Restart=on-failure
RestartSec=5
UMask=0007
PrivateTmp=true
{'NoNewPrivileges=true' if not root else ''}
[Install]
WantedBy=multi-user.target
"""
    path = Path("/etc/systemd/system") / f"{name}.service"
    if path.exists():
        raise SystemExit(f"Unit sudah ada: {path}; konfigurasi tidak ditimpa")
    path.write_text(content)


def main():
    parser = argparse.ArgumentParser(description="MikaPanels guided VPS installer")
    parser.add_argument("--plan-only", action="store_true", help="Show supported platform and operations without modifying system")
    options = parser.parse_args()
    console.print(Panel("[bold cyan]MikaPanels[/bold cyan] × [bold magenta]MychaHost[/bold magenta]\nInstaller VPS Ubuntu 24.04 · Nginx · PHP-FPM · Python", border_style="cyan"))
    if options.plan_only:
        console.print("Pada VPS Ubuntu 24.04 baru: memasang dependensi OS, menyalin aplikasi ke /opt/mikapanels, membuat user mika, dua database, empat layanan systemd, proxy Nginx, dan sertifikat TLS via Certbot. Konfigurasi Tripay dimasukkan melalui prompt tersembunyi. Konfigurasi yang sudah ada tidak ditimpa.")
        return
    if os.geteuid() != 0:
        raise SystemExit("Jalankan dengan sudo menggunakan Python .venv proyek.")
    os_release = Path("/etc/os-release").read_text()
    if 'ID=ubuntu' not in os_release or 'VERSION_ID="24.04"' not in os_release:
        raise SystemExit("Installer ini hanya mendukung Ubuntu 24.04.")
    if CONFIG.exists() or DATA.exists() or (DEST.exists() and DEST.resolve() != SOURCE):
        raise SystemExit("Instalasi/konfigurasi sudah ada. Backup dan gunakan prosedur upgrade; installer tidak menimpa data.")
    if not Confirm.ask("VPS ini khusus hosting dan Anda ingin memasang layanan sistem?", default=False):
        return
    panel_domain = validate_domain(Prompt.ask("Domain panel", default="panel.example.com"))
    shop_domain = validate_domain(Prompt.ask("Domain toko", default="host.example.com"))
    if panel_domain == shop_domain:
        raise SystemExit("Domain panel dan toko harus berbeda")
    server_ip = Prompt.ask("IP publik VPS")
    ip = ipaddress.ip_address(server_ip)
    if ip.version != 4:
        raise SystemExit("Versi awal installer memakai IPv4")
    email = Prompt.ask("Email admin dan Let's Encrypt")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("Email tidak valid")
    password = prompt_admin_password()
    mode = Prompt.ask("Mode Tripay", choices=["sandbox", "production"], default="sandbox")
    merchant = Prompt.ask("Kode merchant Tripay (boleh kosong)", default="")
    api_key = getpass.getpass("API key Tripay (boleh kosong): ")
    private_key = getpass.getpass("Private key Tripay (boleh kosong): ")
    channels = Prompt.ask("Channel aktif merchant (pisahkan koma)", default="BRIVA,BNIVA,QRIS")
    if not re.fullmatch(r"[A-Z0-9_]+(?:,[A-Z0-9_]+)*", channels):
        raise SystemExit("Daftar channel tidak valid")
    if any([merchant, api_key, private_key]) and not all([merchant, api_key, private_key]):
        raise SystemExit("Tripay membutuhkan ketiga kredensial; isi semuanya atau kosongkan semuanya.")
    table = Table("Komponen", "Konfigurasi")
    for name, value in [("Panel", panel_domain), ("Toko", shop_domain), ("Server", server_ip), ("Tripay", mode), ("Data", str(DATA))]:
        table.add_row(name, value)
    console.print(table)
    console.print("DNS kedua domain harus sudah mengarah ke IP VPS. Port 80/443 harus dibuka di firewall VPS/provider. Installer tidak mengubah firewall.")
    if not Confirm.ask("Jalankan instalasi dan penerbitan TLS sekarang?", default=False):
        return
    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", "python3.12-venv", "nginx", "php8.3-fpm", "php8.3-cli", "certbot", "python3-certbot-nginx", "ca-certificates"])
    import pwd
    try:
        pwd.getpwnam("mika")
        raise SystemExit("User mika sudah ada; periksa sebelum instalasi")
    except KeyError:
        pass
    run(["useradd", "--system", "--home-dir", str(DATA), "--shell", "/usr/sbin/nologin", "--user-group", "mika"])
    if SOURCE != DEST:
        shutil.copytree(SOURCE, DEST, ignore=shutil.ignore_patterns(".git", ".venv", "var", "__pycache__", ".pytest_cache", ".env*"))
    # Application code remains root-owned, never writable by the web service or tenant.
    run(["chown", "-R", "root:root", str(DEST)])
    run(["python3.12", "-m", "venv", str(DEST / ".venv")])
    run([str(DEST / ".venv/bin/pip"), "install", "--require-hashes", "-r", str(DEST / "requirements.lock")])
    CONFIG.mkdir(mode=0o750)
    shutil.chown(CONFIG, user="root", group="mika")
    DATA.mkdir(mode=0o2770)
    shutil.chown(DATA, user="mika", group="mika")
    sites = Path("/srv/mika-hosting")
    if sites.exists():
        raise SystemExit("/srv/mika-hosting sudah ada; periksa sebelum melanjutkan")
    sites.mkdir(mode=0o755)
    token = secrets.token_urlsafe(48)
    common = {"MIKA_DEBUG": "0", "MIKA_API_TOKEN": token, "MIKA_PROVISION_MODE": "system", "MIKA_HOSTING_ROOT": str(sites),
              "MIKA_PANEL_URL": f"https://{panel_domain}", "MYCHA_PUBLIC_URL": f"https://{shop_domain}", "MIKA_SERVER_IP": server_ip,
              "MIKA_CERTBOT_EMAIL": email}
    for service, domain in [("panel", panel_domain), ("shop", shop_domain)]:
        directory = DATA / service
        directory.mkdir(mode=0o2770)
        shutil.chown(directory, user="mika", group="mika")
        values = {**common, "MIKA_SERVICE": service, "MIKA_SECRET_KEY": secrets.token_urlsafe(64),
                  "MIKA_DATA_DIR": str(directory), "MIKA_ALLOWED_HOSTS": domain + ",127.0.0.1,localhost",
                  "MIKA_CSRF_ORIGINS": f"https://{domain}"}
        if service == "shop":
            values.update({"TRIPAY_MODE": mode, "TRIPAY_MERCHANT_CODE": merchant, "TRIPAY_API_KEY": api_key,
                           "TRIPAY_PRIVATE_KEY": private_key, "TRIPAY_CHANNELS": channels})
        env_file(CONFIG / f"{service}.env", values)
        env = {**os.environ, **values, "MIKA_BOOTSTRAP_EMAIL": email, "MIKA_BOOTSTRAP_PASSWORD": password}
        for command in (["migrate", "--noinput"], ["seed_catalog"], ["bootstrap_admin"], ["collectstatic", "--noinput"]):
            run([str(DEST / ".venv/bin/python"), "manage.py", *command], env)
        run(["chown", "-R", "mika:mika", str(directory)])
        for database in directory.glob("*.sqlite3"):
            database.chmod(0o660)
    unit("mikapanels", "MikaPanels web", "panel", "gunicorn config.wsgi:application --bind 127.0.0.1:8001 --workers 2 --timeout 60")
    unit("mychahost", "MychaHost web", "shop", "gunicorn config.wsgi:application --bind 127.0.0.1:8002 --workers 2 --timeout 60")
    unit("mika-provision", "Mika root provisioning worker", "panel", "python manage.py provision_worker --recover", root=True)
    unit("mycha-orders", "Mycha paid order reconciliation", "shop", "python manage.py fulfill_orders")
    for domain, port, name in [(panel_domain, 8001, "panel"), (shop_domain, 8002, "shop")]:
        vhost = Path(f"/etc/nginx/conf.d/mika-{name}.conf")
        if vhost.exists():
            raise SystemExit(f"Nginx config already exists: {vhost}")
        vhost.write_text(f"""server {{
    listen 80;
    server_name {domain};
    client_max_body_size 12m;
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
}}
""")
    run(["nginx", "-t"])
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "nginx", "php8.3-fpm", "mikapanels", "mychahost", "mika-provision", "mycha-orders"])
    run(["systemctl", "reload", "nginx"])
    run(["certbot", "--nginx", "--non-interactive", "--agree-tos", "--redirect", "-m", email, "-d", panel_domain, "-d", shop_domain])
    hook = Path("/etc/letsencrypt/renewal-hooks/deploy/mikapanels-nginx")
    hook.write_text("#!/bin/sh\nset -eu\n/usr/sbin/nginx -t\n/bin/systemctl reload nginx\n")
    hook.chmod(0o755)
    import requests
    for domain in [panel_domain, shop_domain]:
        response = requests.get(f"https://{domain}/health/", timeout=20)
        response.raise_for_status()
        if response.json().get("status") != "ok":
            raise SystemExit("Readiness check failed")
    console.print(Panel(f"Panel: https://{panel_domain}\nToko: https://{shop_domain}\nUsername: admin\nCallback Tripay: https://{shop_domain}/payments/tripay/callback/\nKonfigurasi: {CONFIG}\nPengaturan kuota filesystem, backup lengkap, SMTP, dan isolasi tenant perlu diselesaikan sebelum produksi publik.", title="Instalasi selesai", border_style="green"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        console.print("[red]Instalasi berhenti. Periksa keluaran perintah terakhir; data/konfigurasi tidak dihapus. Gunakan panduan pemulihan sebelum menjalankan kembali.[/red]")
        raise SystemExit(1)
