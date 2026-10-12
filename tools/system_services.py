"""System configuration shared by the Ubuntu installer and upgrade helper."""
from pathlib import Path
import re
import subprocess

MARKER = "# Managed by MikaPanels"


def clean_config(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)//.*$|#.*$", "", text).strip()


def dns_preflight(bind_dir=Path("/etc/bind")):
    """Do not take over an existing custom BIND installation."""
    local = bind_dir / "named.conf.local"
    options = bind_dir / "named.conf.options"
    if local.exists() and MARKER not in local.read_text() and clean_config(local.read_text()):
        raise RuntimeError("BIND memiliki zone khusus. Integrasikan include mika-zones.conf secara manual sebelum update; konfigurasi tidak ditimpa.")
    if options.exists() and MARKER not in options.read_text():
        stock = clean_config(options.read_text())
        stock = re.sub(r'\s+', '', stock)
        allowed = {
            'options{directory"/var/cache/bind";dnssec-validationauto;listen-on-v6{any;};};',
            'options{directory"/var/cache/bind";dnssec-validationauto;};',
        }
        if stock not in allowed:
            raise RuntimeError("BIND memiliki options khusus. Simpan dan integrasikan konfigurasi authoritative sebelum update; konfigurasi tidak ditimpa.")


def configure_services(bind_dir=Path("/etc/bind"), mysql_dir=Path("/etc/mysql/mariadb.conf.d"), nginx_dir=Path("/etc/nginx/conf.d")):
    dns_preflight(bind_dir)
    (bind_dir / "mika-zones").mkdir(mode=0o755, exist_ok=True)
    include = bind_dir / "mika-zones.conf"
    if not include.exists():
        include.write_text(MARKER + "\n")
    local = bind_dir / "named.conf.local"
    content = local.read_text() if local.exists() else ""
    if 'include "' + str(include) + '";' not in content:
        local.write_text(content + f'\n{MARKER}\ninclude "{include}";\n')
    (bind_dir / "named.conf.options").write_text(MARKER + '\noptions {\n    directory "/var/cache/bind";\n    recursion no;\n    allow-query { any; };\n    allow-transfer { none; };\n    dnssec-validation auto;\n    listen-on { any; };\n    listen-on-v6 { none; };\n};\n')
    mysql_dir.mkdir(parents=True, exist_ok=True)
    (mysql_dir / "60-mikapanels.cnf").write_text(MARKER + '\n[mysqld]\nbind-address=127.0.0.1\n')
    nginx_dir.mkdir(parents=True, exist_ok=True)
    (nginx_dir / "mika-logging.conf").write_text("log_format mika '$msec $status $body_bytes_sent';\n")
    (bind_dir / "mika-zones").chmod(0o755)
    for path in [include, local, bind_dir / "named.conf.options", mysql_dir / "60-mikapanels.cnf", nginx_dir / "mika-logging.conf"]:
        path.chmod(0o644)
    for command in [["named-checkconf"], ["nginx", "-t"]]:
        subprocess.run(command, check=True)


def load_environment(path):
    """Load the trusted installer EnvironmentFile without displaying values."""
    result = subprocess.run(["bash", "-c", 'set -a; source "$1"; env -0', "mika-env", str(path)], check=True, capture_output=True)
    return {key.decode(): value.decode() for entry in result.stdout.split(b"\0") if entry and b"=" in entry
            for key, value in [entry.split(b"=", 1)] if key.startswith((b"MIKA_", b"MYCHA_", b"TRIPAY_"))}


def add_environment(path, values):
    existing = load_environment(path)
    missing = {k: v for k, v in values.items() if k not in existing}
    # All additions here are non-secret hostnames, flags, and paths.
    with path.open("a") as stream:
        for key, value in missing.items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]+", key) or not re.fullmatch(r"[A-Za-z0-9_./:-]+", str(value)):
                raise ValueError("Unsafe configuration addition")
            stream.write(f'{key}="{value}"\n')
    return {**existing, **missing}
