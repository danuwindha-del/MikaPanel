from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import ssl
import threading
from unittest.mock import patch
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from tools.vps_health import probe_health


@contextmanager
def server(body=None, status=200, tls=None):
    captured = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.append((self.path, dict(self.headers)))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body if body is not None else json.dumps({"status": "ok", "service": "panel"}).encode())
        def log_message(self, *args):
            pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if tls:
        httpd.socket = tls.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port, captured
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_local_backend_health_with_production_host_and_forwarded_https():
    with server() as (port, captured):
        result = probe_health("https://panel.example.test", "panel", backend_port=port)
        assert result.ok
        assert captured == [("/health/", {"Accept-Encoding": "identity", "Host": "panel.example.test", "X-Forwarded-Proto": "https"})]


@pytest.mark.parametrize("status,body,expected", [
    (502, b"private fixture response", "HTTP 502"),
    (301, b"private fixture response", "HTTP 301"),
    (200, b"private fixture response", "Respons bukan JSON health"),
    (200, b'{"status":"ok","service":"shop"}', "Identitas/status service pada respons tidak sesuai"),
])
def test_health_failure_is_specific_without_echoing_body(status, body, expected):
    with server(body, status) as (port, _):
        result = probe_health("https://panel.example.test", "panel", backend_port=port)
    assert not result.ok and result.detail == expected
    assert "private fixture" not in result.detail


def test_credentials_in_url_are_rejected_without_echoing():
    result = probe_health("https://user:private-fixture@panel.example.test", "panel")
    assert not result.ok and "private-fixture" not in result.detail


def test_dns_failure_is_reported():
    with patch("http.client.HTTPSConnection.connect", side_effect=socket.gaierror("fixture dns failure")):
        result = probe_health("https://panel.example.test", "panel")
    assert not result.ok and result.detail == "Resolusi DNS domain gagal"


def test_loopback_https_uses_domain_sni_and_enforces_hostname_verification(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "panel.example.test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("panel.example.test")]), critical=False)
        .sign(key, hashes.SHA256()))
    cert_file = tmp_path / "cert.pem"; key_file = tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_file, key_file)
    seen = []
    tls.set_servername_callback(lambda connection, name, context: seen.append(name))
    trusted_context = ssl.create_default_context(cafile=str(cert_file))
    with server(tls=tls) as (port, _), patch("tools.vps_health.ssl.create_default_context", return_value=trusted_context):
        assert probe_health(f"https://panel.example.test:{port}", "panel", local_https=True).ok
        mismatch = probe_health(f"https://wrong.example.test:{port}", "panel", local_https=True)
    assert not mismatch.ok and "TLS" in mismatch.detail
    assert seen == ["panel.example.test", "wrong.example.test"]
