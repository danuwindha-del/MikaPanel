#!/usr/bin/env python3
"""Supervise local services, report actual readiness and stop children on exit."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def main():
    config = ROOT / "var/config.json"
    if not config.exists():
        raise SystemExit("Run python tools/configure.py first")
    for port in (8001, 8002):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(f"Port {port} already in use. Stop the existing instance before starting another.")
    pidfile = ROOT / "var/dev.pid"
    pidfile.write_text(str(os.getpid()))
    commands = [
        ("panel-web", "panel", ["runserver", "127.0.0.1:8001", "--noreload"]),
        ("shop-web", "shop", ["runserver", "127.0.0.1:8002", "--noreload"]),
        ("panel-worker", "panel", ["provision_worker", "--recover"]),
        ("shop-worker", "shop", ["fulfill_orders"]),
    ]
    children = []
    logs = []
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for name, service, args in commands:
            log = (ROOT / "var" / f"{name}.log").open("a")
            logs.append(log)
            children.append(subprocess.Popen([sys.executable, "tools/run.py", service, *args], cwd=ROOT, stdout=log, stderr=log))
        deadline = time.monotonic() + 25
        ready = set()
        while len(ready) < 2 and time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service stopped; inspect var/*-web.log and var/*-worker.log")
            for port, service in [(8001, "panel"), (8002, "shop")]:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/", timeout=1) as response:
                        data = json.load(response)
                        if data == {"status": "ok", "service": service}:
                            ready.add(service)
                except OSError:
                    pass
            time.sleep(.25)
        if len(ready) < 2:
            raise RuntimeError("Readiness deadline exceeded; inspect service logs")
        print("Both development apps and workers started; database health checks passed.", flush=True)
        print("Use Ctrl+C to stop. Credentials are in var/local-admin.json; never expose dev servers publicly.", flush=True)
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A child stopped; inspect var logs")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for log in logs:
            log.close()
        pidfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
