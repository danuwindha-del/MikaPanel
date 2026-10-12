import os
import shutil
import stat
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from .files import disk_usage
from .models import Account, AccountUsage, MetricSample, UsageSample


def collect_server():
    previous = MetricSample.objects.order_by("-created_at").first()
    now = timezone.now()
    if previous and (now - previous.created_at).total_seconds() < 25:
        return previous
    cpu = [int(n) for n in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
    total, idle = sum(cpu), cpu[3] + cpu[4]
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        memory[key] = int(value.split()[0]) * 1024
    root = settings.MIKA_HOSTING_ROOT if settings.MIKA_HOSTING_ROOT.exists() else settings.DATA_DIR
    disk = shutil.disk_usage(root)
    rx = tx = 0
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        interface, values = line.split(":")
        if interface.strip() != "lo":
            numbers = values.split()
            rx += int(numbers[0])
            tx += int(numbers[8])
    cpu_percent = rate = None
    if previous:
        elapsed = (now - previous.created_at).total_seconds()
        delta = total - previous.cpu_total
        if delta > 0:
            cpu_percent = min(100, max(0, (1 - (idle - previous.cpu_idle) / delta) * 100))
        rate = max(0, (rx + tx - previous.network_rx - previous.network_tx) / elapsed)
    sample = MetricSample.objects.create(cpu_total=total, cpu_idle=idle, cpu_percent=cpu_percent,
        memory_total=memory["MemTotal"], memory_used=memory["MemTotal"] - memory.get("MemAvailable", memory["MemFree"]),
        disk_total=disk.total, disk_used=disk.used, network_rx=rx, network_tx=tx, network_rate=rate,
        uptime_seconds=int(float(Path("/proc/uptime").read_text().split()[0])))
    MetricSample.objects.filter(created_at__lt=now - timedelta(days=2)).delete()
    return sample


def collect_account(account):
    if settings.MIKA_PROVISION_MODE == "system":
        from .provisioner import refresh_ssl
        refresh_ssl(account)
    usage, _ = AccountUsage.objects.get_or_create(account=account)
    try:
        usage.disk_bytes, usage.file_count = disk_usage(account)
    except (OSError, ValueError):
        return
    requests = errors = bandwidth = 0
    log = settings.MIKA_NGINX_LOG_DIR / f"mika-site-{account.system_user}.access.log"
    try:
        fd = os.open(log, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Invalid log type")
            if info.st_ino != usage.log_inode or info.st_size < usage.log_offset:
                usage.log_offset = 0
            usage.log_inode = info.st_ino
            stream.seek(usage.log_offset)
            for _ in range(100000):
                start = stream.tell()
                line = stream.readline(512)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    stream.seek(start)
                    break
                try:
                    _, status, size = line.decode("ascii").split()
                    status, size = int(status), int(size)
                    if 100 <= status <= 599 and size >= 0:
                        requests += 1
                        bandwidth += size
                        errors += int(status >= 400)
                except (ValueError, UnicodeError):
                    continue
            usage.log_offset = stream.tell()
    except (OSError, ValueError):
        pass
    usage.requests += requests
    usage.error_requests += errors
    usage.bandwidth_bytes += bandwidth
    usage.save()
    UsageSample.objects.create(account=account, requests=requests, errors=errors, bandwidth_bytes=bandwidth)
    account.usage_samples.filter(created_at__lt=timezone.now() - timedelta(days=2)).delete()


def collect_all():
    last = MetricSample.objects.order_by("-created_at").first()
    if last and (timezone.now() - last.created_at).total_seconds() < 25:
        return
    collect_server()
    for account in Account.objects.filter(status__in=["active", "suspended"]):
        collect_account(account)


def chart(values, width=640, height=170):
    values = [float(v or 0) for v in values]
    if not values:
        return {"line": "", "area": "", "max": 0}
    maximum = max(max(values), 1)
    points = [(i * width / max(len(values) - 1, 1), height - value / maximum * (height - 15)) for i, value in enumerate(values)]
    line = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return {"line": line, "area": line + f" L {points[-1][0]:.1f},{height} L 0,{height} Z", "max": max(values)}
