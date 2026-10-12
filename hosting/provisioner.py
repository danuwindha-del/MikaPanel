"""Local demo backend and Ubuntu provisioning. Only the dedicated worker runs as root."""
import html
import os
import re
import subprocess
import ipaddress
from pathlib import Path

from django.conf import settings
from .validation import domain_name


def run(*args):
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=180 if args[0] == "certbot" else 60)


def seed_index(index, domain, uid=None, gid=None):
    # Never follow, truncate, chmod, or chown a tenant-controlled pre-existing index (including symlinks).
    try:
        fd = os.open(index, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o664)
    except FileExistsError:
        return
    with os.fdopen(fd, "w") as stream:
        os.fchmod(stream.fileno(), 0o664)
        if uid is not None:
            os.fchown(stream.fileno(), uid, gid)
        stream.write(f"<!doctype html><html lang='id'><meta charset='utf-8'><title>{html.escape(domain)}</title><body style='background:#090d1b;color:#eee;font-family:system-ui;padding:10%'><h1>Website Anda sudah aktif ✨</h1><p>{html.escape(domain)} · Powered by MikaPanels</p></body></html>")


def nginx_config(account, suspended=False):
    domain = domain_name(account.domain)
    user = account.system_user
    root = settings.MIKA_HOSTING_ROOT / user / "public"
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(root)):
        raise ValueError("Unsafe hosting root")
    php = ""
    if account.kind == "php":
        php = f"""
    location ~ \\.php$ {{
        try_files $uri =404;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_pass unix:/run/php/{user}.sock;
    }}
"""
    tls = ""
    cert = Path("/etc/letsencrypt/live") / domain
    if (cert / "fullchain.pem").exists() and (cert / "privkey.pem").exists():
        tls = f"""    listen 443 ssl;
    ssl_certificate {cert}/fullchain.pem;
    ssl_certificate_key {cert}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
"""
    rules = "\n".join(f"    deny {ipaddress.ip_network(rule.network, strict=False)};" for rule in account.blocked_ips.all())
    headers = '    add_header X-Content-Type-Options "nosniff" always;\n    add_header X-Frame-Options "SAMEORIGIN" always;' if account.security_headers else ""
    redirect_https = '    if ($scheme = http) { return 301 https://$host$request_uri; }' if tls and account.force_https else ""
    fallback = "/index.php?$args" if account.kind == "php" else "=404"
    return f"""server {{
    listen 80;
{tls}
    server_name {domain} www.{domain};
    root {root};
    index index.php index.html;
    client_max_body_size 10m;
    access_log {settings.MIKA_NGINX_LOG_DIR}/mika-site-{user}.access.log mika;
    autoindex {'on' if account.directory_listing else 'off'};
    disable_symlinks on from=$document_root;
{headers}
{rules}
{redirect_https}
    {'return 503;' if suspended else ''}
    location / {{ try_files $uri $uri/ {fallback}; }}
    location ^~ /.well-known/acme-challenge/ {{ allow all; }}
    location ~ /\\. {{ deny all; }}
{php if php else '    location ~ \\.php$ { return 404; }'}
}}
"""


def process(account, action):
    if action not in {"create", "suspend", "resume", "ssl", "refresh"}:
        raise ValueError("Unknown provisioning action")
    domain_name(account.domain)
    user = account.system_user
    if not re.fullmatch(r"mh[a-f0-9]{12}", user):
        raise ValueError("Unsafe system user")
    root = settings.MIKA_HOSTING_ROOT / user
    production = settings.MIKA_PROVISION_MODE == "system"
    if settings.MIKA_PROVISION_MODE not in {"system", "demo"}:
        raise ValueError("Unknown provisioning mode")
    if production and os.geteuid() != 0:
        raise PermissionError("System worker must run as root")
    if action == "ssl":
        if not production:
            raise ValueError("SSL requires system provisioning and public DNS")
        if not settings.MIKA_CERTBOT_EMAIL:
            raise ValueError("MIKA_CERTBOT_EMAIL is required")
        run("certbot", "certonly", "--webroot", "-w", str(root / "public"), "--non-interactive",
            "--agree-tos", "-m", settings.MIKA_CERTBOT_EMAIL, "-d", account.domain, "-d", f"www.{account.domain}")
        refresh_ssl(account)
        if not account.ssl_enabled:
            raise ValueError("Certificate not found after issuance")
        account.force_https = True
        account.save(update_fields=["force_https"])
    if action == "create":
        if production:
            import pwd
            try:
                existing = pwd.getpwnam(user)
                if existing.pw_dir != str(root):
                    raise ValueError("Existing system account has a different home")
            except KeyError:
                run("useradd", "--system", "--home-dir", str(root), "--shell", "/usr/sbin/nologin", "--user-group", user)
            # Tenant must NOT join shared mika group; that group is for panel file operations only.
        (root / "public").mkdir(parents=True, exist_ok=True)
        (root / "tmp").mkdir(exist_ok=True)
        index = root / "public" / "index.html"
        if production:
            import grp
            identity = pwd.getpwnam(user)
            seed_index(index, account.domain, identity.pw_uid, grp.getgrnam("mika").gr_gid)
            run("chown", "root:mika", str(root))
            run("chmod", "0755", str(root))
            run("chown", f"{user}:mika", str(root / "public"))
            run("chmod", "2775", str(root / "public"))
            run("chown", f"{user}:{user}", str(root / "tmp"))
            run("chmod", "0700", str(root / "tmp"))
        else:
            seed_index(index, account.domain)
    if production:
        logging = Path("/etc/nginx/conf.d/mika-logging.conf")
        logging.write_text("log_format mika '$msec $status $body_bytes_sent';\n")
        target = Path("/etc/nginx/conf.d") / f"mika-site-{user}.conf"
        previous = target.read_text() if target.exists() else None
        config = nginx_config(account, suspended=action == "suspend" or (action == "refresh" and account.status == "suspended"))
        target.write_text(config)
        try:
            run("nginx", "-t")
        except Exception:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(previous)
            raise
        if account.kind == "php":
            if not 1 <= account.plan.php_workers <= 20 or not 32 <= account.plan.memory_mb <= 2048:
                raise ValueError("PHP plan limits out of range")
            pool = Path("/etc/php/8.3/fpm/pool.d") / f"{user}.conf"
            pool.write_text(f"""[{user}]
user = {user}
group = {user}
listen = /run/php/{user}.sock
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
pm = ondemand
pm.max_children = {account.plan.php_workers}
pm.process_idle_timeout = 10s
clear_env = yes
security.limit_extensions = .php
php_admin_value[memory_limit] = {account.plan.memory_mb}M
php_admin_value[open_basedir] = {root}/public:{root}/tmp:/run/mysqld
php_admin_value[upload_tmp_dir] = {root}/tmp
php_admin_value[session.save_path] = {root}/tmp
php_admin_value[disable_functions] = exec,passthru,shell_exec,system,proc_open,popen
""")
            run("php-fpm8.3", "-t")
            run("systemctl", "reload", "php8.3-fpm")
        run("systemctl", "reload", "nginx")
    if action == "create":
        from .dns import ensure_records, publish
        ensure_records(account)
        if settings.MIKA_DNS_ENABLED or settings.MIKA_PROVISION_MODE == "demo":
            publish(account)
    if action == "refresh":
        return account.status
    return "suspended" if action == "suspend" else "active"


def refresh_ssl(account):
    from cryptography import x509
    from django.utils import timezone
    from .models import Account
    cert = Path("/etc/letsencrypt/live") / domain_name(account.domain) / "fullchain.pem"
    try:
        info = x509.load_pem_x509_certificate(cert.read_bytes())
        expires = info.not_valid_after_utc
        enabled = expires > timezone.now()
    except (OSError, ValueError):
        expires, enabled = None, False
    Account.objects.filter(pk=account.pk).update(ssl_enabled=enabled, ssl_expires_at=expires)
    account.ssl_enabled, account.ssl_expires_at = enabled, expires
