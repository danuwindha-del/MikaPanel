"""Read-only health probes; preserve TLS verification and never print response bodies."""
from dataclasses import dataclass
import http.client
import json
import socket
import ssl
import time
from urllib.parse import urlsplit


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    detail: str


class LoopbackHTTPSConnection(http.client.HTTPSConnection):
    """Connect locally while checking the configured hostname's certificate and SNI."""
    def connect(self):
        raw = socket.create_connection(("127.0.0.1", self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def probe_health(base_url, service, *, backend_port=None, local_https=False, timeout=5):
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        return HealthResult(False, "URL layanan tidak valid")
    host = parsed.hostname
    headers = {"Host": parsed.netloc}
    if backend_port:
        connection = http.client.HTTPConnection("127.0.0.1", backend_port, timeout=timeout)
        headers["X-Forwarded-Proto"] = "https"
    elif parsed.scheme == "https":
        cls = LoopbackHTTPSConnection if local_https else http.client.HTTPSConnection
        connection = cls(host, parsed.port or 443, timeout=timeout, context=ssl.create_default_context())
    elif local_https:
        return HealthResult(False, "Pemeriksaan TLS lokal membutuhkan URL HTTPS")
    else:
        connection = http.client.HTTPConnection(host, parsed.port or 80, timeout=timeout)
    try:
        connection.request("GET", parsed.path.rstrip("/") + "/health/", headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return HealthResult(False, f"HTTP {response.status}")
        body = response.read(4097)
        if len(body) > 4096:
            return HealthResult(False, "Respons health terlalu besar")
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            return HealthResult(False, "Respons bukan JSON health")
        if data != {"status": "ok", "service": service}:
            return HealthResult(False, "Identitas/status service pada respons tidak sesuai")
        return HealthResult(True, "OK")
    except ssl.SSLCertVerificationError:
        return HealthResult(False, "Sertifikat TLS tidak lolos verifikasi")
    except socket.gaierror:
        return HealthResult(False, "Resolusi DNS domain gagal")
    except ConnectionRefusedError:
        return HealthResult(False, "Koneksi ditolak; port layanan belum menerima koneksi")
    except TimeoutError:
        return HealthResult(False, "Koneksi/respons timeout")
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return HealthResult(False, f"Koneksi gagal ({type(exc).__name__})")
    finally:
        connection.close()


def wait_health(base_url, service, *, backend_port=None, deadline_seconds=30):
    deadline = time.monotonic() + deadline_seconds
    while True:
        remaining = max(.1, deadline - time.monotonic())
        result = probe_health(base_url, service, backend_port=backend_port, timeout=min(5, remaining))
        if result.ok or time.monotonic() >= deadline:
            return result
        time.sleep(max(0, min(1, deadline - time.monotonic())))
