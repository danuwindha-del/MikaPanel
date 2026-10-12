#!/usr/bin/env python3
"""Create local demo configuration without emitting generated passwords or keys."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

ROOT = Path(__file__).resolve().parent.parent
console = Console()


def save_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)


def main():
    parser = argparse.ArgumentParser(description="MikaPanels local demo setup")
    parser.add_argument("--non-interactive", action="store_true")
    options = parser.parse_args()
    console.print(Panel("[bold]MikaPanels + MychaHost[/bold]\nSetup lingkungan pengembangan lokal", border_style="cyan"))
    var = ROOT / "var"
    var.mkdir(exist_ok=True, mode=0o700)
    config_path = var / "config.json"
    if config_path.exists():
        console.print("Konfigurasi dipertahankan; gunakan tools/run.py untuk migrasi atau menjalankan layanan.")
        return
    email = "admin@example.test" if options.non_interactive else Prompt.ask("Email administrator", default="admin@example.test")
    password = secrets.token_urlsafe(20) if options.non_interactive else Prompt.ask("Password admin (minimal 12 karakter)", password=True)
    if len(password) < 12:
        raise SystemExit("Password minimal 12 karakter")
    common = {"MIKA_DEBUG": "1", "MIKA_API_TOKEN": secrets.token_urlsafe(48), "MIKA_DATA_DIR": str(var),
              "MIKA_HOSTING_ROOT": str(var / "sites"), "MIKA_PROVISION_MODE": "demo",
              "MIKA_SERVER_IP": "127.0.0.1", "MIKA_ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
              "MIKA_PANEL_URL": "http://127.0.0.1:8001", "MYCHA_PUBLIC_URL": "http://127.0.0.1:8002",
              "TRIPAY_MODE": "sandbox", "TRIPAY_API_KEY": "", "TRIPAY_PRIVATE_KEY": "", "TRIPAY_MERCHANT_CODE": ""}
    config = {service: {**common, "MIKA_SERVICE": service, "MIKA_SECRET_KEY": secrets.token_urlsafe(64)} for service in ("panel", "shop")}
    save_private(config_path, config)
    save_private(var / "local-admin.json", {"username": "admin", "email": email, "password": password})
    for service in config:
        env = {**os.environ, **config[service], "MIKA_BOOTSTRAP_EMAIL": email, "MIKA_BOOTSTRAP_PASSWORD": password}
        for command in (["migrate", "--noinput"], ["seed_catalog"], ["bootstrap_admin"]):
            subprocess.run([sys.executable, str(ROOT / "manage.py"), *command], env=env, cwd=ROOT, check=True)
    console.print("[green]Setup selesai.[/green] Kredensial lokal tersimpan di var/local-admin.json (izin 0600). Jangan commit atau bagikan file ini.")
    console.print("Panel: python tools/run.py panel runserver 127.0.0.1:8001\nShop:  python tools/run.py shop runserver 127.0.0.1:8002")


if __name__ == "__main__":
    main()
