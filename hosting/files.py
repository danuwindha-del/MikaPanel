"""Website access: open every directory segment with dirfd + O_NOFOLLOW."""
import io
import os
import re
import stat
import zipfile
from contextlib import contextmanager
from django.conf import settings

MAX_FILE = 10 * 1024 * 1024
MAX_BACKUP = 50 * 1024 * 1024


def public_path(account):
    return settings.MIKA_HOSTING_ROOT / account.system_user / 'public'


def safe_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'\.?[A-Za-z0-9][A-Za-z0-9_.-]{0,126}', name) or '..' in name:
        raise ValueError('Nama tidak valid; gunakan huruf, angka, titik, dan tanda hubung.')
    return name


def path_parts(path):
    if not isinstance(path, str) or path.startswith('/') or '\\' in path:
        raise ValueError('Path tidak valid.')
    parts = path.split('/') if path else []
    if len(parts) > 16:
        raise ValueError('Folder terlalu dalam.')
    return [safe_name(part) for part in parts]


@contextmanager
def directory(account, path=''):
    fd = os.open(public_path(account), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path_parts(path):
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


@contextmanager
def parent(account, path):
    parts = path_parts(path)
    if not parts:
        raise ValueError('Nama file/folder diperlukan.')
    with directory(account, '/'.join(parts[:-1])) as fd:
        yield fd, parts[-1]


def listing(account, path=''):
    with directory(account, path) as fd:
        entries = []
        for name in sorted(os.listdir(fd)):
            try:
                safe_name(name)
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISREG(entry.st_mode) or stat.S_ISDIR(entry.st_mode):
                    entries.append({'name': name, 'size': entry.st_size, 'is_dir': stat.S_ISDIR(entry.st_mode),
                                    'path': '/'.join(filter(None, [path, name])), 'modified': entry.st_mtime})
            except (FileNotFoundError, ValueError):
                continue
        return sorted(entries, key=lambda entry: (not entry['is_dir'], entry['name']))


def read_file(account, path):
    with parent(account, path) as (fd, name):
        f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(f, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Hanya file reguler yang didukung.')
            data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise ValueError('File terlalu besar (maksimal 10 MB).')
            return data


def disk_usage(account):
    total = count = 0
    with directory(account) as root:
        def walk(fd, depth=0):
            nonlocal total, count
            if depth > 32 or count > 100000:
                raise ValueError('Batas pemindaian file tercapai.')
            for name in os.listdir(fd):
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):
                        total += info.st_size
                        count += 1
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            walk(child, depth + 1)
                        finally:
                            os.close(child)
                except FileNotFoundError:
                    continue
        walk(root)
    return total, count


def write_file(account, path, data):
    if len(data) > MAX_FILE:
        raise ValueError('File terlalu besar (maksimal 10 MB).')
    used, _ = disk_usage(account)
    with parent(account, path) as (fd, name):
        try:
            existing = os.stat(name, dir_fd=fd, follow_symlinks=False)
            old_size = existing.st_size if stat.S_ISREG(existing.st_mode) else 0
        except FileNotFoundError:
            old_size = 0
        if used - old_size + len(data) > account.plan.disk_mb * 1024 * 1024:
            raise ValueError('Batas upload penyimpanan paket terlampaui.')
        flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            f = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o664, dir_fd=fd)
            created = True
        except FileExistsError:
            f = os.open(name, flags, dir_fd=fd)
            created = False
        with os.fdopen(f, 'wb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Hanya file reguler tanpa hard link yang dapat diedit.')
            if created:
                os.fchmod(stream.fileno(), 0o664)
            stream.truncate(0)
            stream.write(data)


def create_directory(account, path):
    with parent(account, path) as (fd, name):
        os.mkdir(name, mode=0o2775, dir_fd=fd)
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            os.fchmod(child, 0o2775)
        finally:
            os.close(child)


def delete(account, path):
    with parent(account, path) as (fd, name):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            os.rmdir(name, dir_fd=fd)
        elif stat.S_ISREG(info.st_mode):
            os.unlink(name, dir_fd=fd)
        else:
            raise ValueError('Symlink atau file khusus tidak dapat dikelola.')


def rename(account, path, new_name):
    new_name = safe_name(new_name)
    with parent(account, path) as (fd, old_name):
        info = os.stat(old_name, dir_fd=fd, follow_symlinks=False)
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError('File khusus tidak dapat diganti nama.')
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        libc.renameat2.restype = ctypes.c_int
        if libc.renameat2(fd, old_name.encode(), fd, new_name.encode(), 1) != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))


def backup_zip(account):
    buffer = io.BytesIO()
    total = count = 0
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        def walk(path='', depth=0):
            nonlocal total, count
            if depth > 16:
                raise ValueError('Backup melebihi kedalaman folder yang didukung.')
            for item in listing(account, path):
                if item['is_dir']:
                    archive.writestr(item['path'] + '/', b'')
                    walk(item['path'], depth + 1)
                else:
                    count += 1
                    if count > 5000 or total + item['size'] > MAX_BACKUP:
                        raise ValueError('Backup web dibatasi 50 MB dan 5000 file.')
                    data = read_file(account, item['path'])
                    total += len(data)
                    if total > MAX_BACKUP:
                        raise ValueError('Backup terlalu besar.')
                    archive.writestr(item['path'], data)
        walk()
    buffer.seek(0)
    return buffer


def extract_zip(account, data, target=''):
    path_parts(target)
    if len(data) > MAX_FILE:
        raise ValueError('ZIP maksimal 10 MB sebelum ekstraksi.')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > 1000 or sum(m.file_size for m in members) > MAX_BACKUP:
            raise ValueError('ZIP dibatasi 1000 entri dan 50 MB setelah ekstraksi.')
        seen = set()
        for member in members:
            parts = path_parts(member.filename.rstrip('/'))
            if not parts or member.filename in seen:
                raise ValueError('ZIP berisi nama kosong atau duplikat.')
            seen.add(member.filename)
            mode = member.external_attr >> 16
            if (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or member.file_size > MAX_FILE or member.flag_bits & 1
                    or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                raise ValueError('ZIP berisi file khusus, terenkripsi, atau terlalu besar.')
        for member in members:
            path = '/'.join(filter(None, [target, member.filename.rstrip('/')]))
            parts = path_parts(path)
            for size in range(1, len(parts) if not member.is_dir() else len(parts) + 1):
                folder = '/'.join(parts[:size])
                try:
                    create_directory(account, folder)
                except FileExistsError:
                    with directory(account, folder):
                        pass
            if not member.is_dir():
                write_file(account, path, archive.read(member))
