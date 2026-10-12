"""Root-level website file operations. Use dirfd/O_NOFOLLOW to reject symlink races."""
import os
import re
from contextlib import contextmanager
from pathlib import Path
from django.conf import settings

MAX_FILE = 10 * 1024 * 1024


def public_path(account):
    return settings.MIKA_HOSTING_ROOT / account.system_user / "public"


def safe_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) or ".." in name:
        raise ValueError("Nama file tidak valid; gunakan huruf, angka, titik, dan tanda hubung.")
    return name


@contextmanager
def directory(account):
    path = public_path(account)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield fd
    finally:
        os.close(fd)


def listing(account):
    with directory(account) as fd:
        entries = []
        for name in sorted(os.listdir(fd)):
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                import stat
                if stat.S_ISREG(st.st_mode) and not name.startswith("."):
                    entries.append({"name": name, "size": st.st_size})
            except FileNotFoundError:
                continue
        return entries


def read_file(account, name):
    with directory(account) as fd:
        f = os.open(safe_name(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(f, "rb") as stream:
            import stat
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Hanya file reguler yang didukung.")
            data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise ValueError("File terlalu besar (maksimal 10 MB).")
            return data


def write_file(account, name, data):
    name = safe_name(name)
    if len(data) > MAX_FILE:
        raise ValueError("File terlalu besar (maksimal 10 MB).")
    root = public_path(account)
    used = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    with directory(account) as fd:
        import stat
        try:
            existing = os.stat(name, dir_fd=fd, follow_symlinks=False)
            old_size = existing.st_size if stat.S_ISREG(existing.st_mode) else 0
        except FileNotFoundError:
            old_size = 0
        if used - old_size + len(data) > account.plan.disk_mb * 1024 * 1024:
            raise ValueError("Batas upload penyimpanan paket terlampaui.")
        flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            f = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o664, dir_fd=fd)
            created = True
        except FileExistsError:
            f = os.open(name, flags, dir_fd=fd)
            created = False
        with os.fdopen(f, "wb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Hanya file reguler yang didukung.")
            if created:
                os.fchmod(stream.fileno(), 0o664)
            stream.truncate(0)
            stream.write(data)
