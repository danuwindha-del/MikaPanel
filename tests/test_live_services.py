"""Opt-in functional tests against an isolated MariaDB socket and real BIND binaries.

Never point MIKA_TEST_MYSQL_SOCKET at a production database. Tests create/drop schemas.
"""
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import base64
import secrets
import pytest
import pymysql
from hosting import dns
from hosting.databases import encrypt_password, provision, root_connection
from hosting.models import ManagedDatabase

pytestmark = pytest.mark.django_db


def test_live_mariadb_create_scope_password_rotation_delete(panel, account):
    path = os.environ.get("MIKA_TEST_MYSQL_SOCKET")
    if not path:
        pytest.skip("Isolated MariaDB socket not supplied")
    panel.MIKA_PROVISION_MODE = "system"
    panel.MIKA_MYSQL_ENABLED = True
    panel.MIKA_MYSQL_SOCKET = path
    database = ManagedDatabase(account=account, label="livecheck", password_ciphertext=encrypt_password("Live-fixture-2048!"))
    database.database_name = "mika_" + account.id.hex[:12] + "_livecheck"
    database.username = "mu" + database.id.hex[:16]
    database.save()
    account.database_count = 1; account.save()
    # This schema matches the unescaped '_' grant wildcard and must still be denied.
    alien = database.database_name.replace("_", "x", 1)
    with root_connection() as root, root.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{alien}`")
    def connect(password, schema=database.database_name):
        return pymysql.connect(unix_socket=path, user=database.username, password=password, database=schema, autocommit=True)
    try:
        provision(database, "db_create")
        with connect("Live-fixture-2048!") as connection, connection.cursor() as cursor:
            cursor.execute("CREATE TABLE verification (id INT)")
            cursor.execute("INSERT INTO verification VALUES (42)")
            cursor.execute("SELECT id FROM verification")
            assert cursor.fetchone() == (42,)
        with pytest.raises(pymysql.MySQLError):
            connect("Live-fixture-2048!", alien)
        with pytest.raises(pymysql.MySQLError):
            connect("Live-fixture-2048!", "mysql")
        database.password_ciphertext = encrypt_password("Rotated-live-fixture-4096!")
        database.save()
        provision(database, "db_rotate")
        with pytest.raises(pymysql.MySQLError):
            connect("Live-fixture-2048!")
        connect("Rotated-live-fixture-4096!").close()
        provision(database, "db_delete")
        provision(database, "db_delete")
        account.refresh_from_db(); database.refresh_from_db()
        assert account.database_count == 0 and database.state == "deleted"
        with pytest.raises(pymysql.MySQLError):
            connect("Rotated-live-fixture-4096!")
    finally:
        provision(database, "db_delete")
        with root_connection() as root, root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{alien}`")


def query(domain, kind, port):
    identifier = 5342
    encoded = b"".join(bytes([len(label)]) + label.encode() for label in domain.split(".")) + b"\0"
    packet = struct.pack("!6H", identifier, 0, 1, 0, 0, 0) + encoded + struct.pack("!HH", kind, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.settimeout(.3)
        connection.sendto(packet, ("127.0.0.1", port))
        data = connection.recv(4096)
    header = struct.unpack("!6H", data[:12])
    assert header[0] == identifier and header[1] & 0xF == 0 and header[1] & 0x400
    def skip_name(offset):
        while data[offset]:
            if data[offset] & 0xC0:
                return offset + 2
            offset += data[offset] + 1
        return offset + 1
    offset = skip_name(12) + 4
    answers = []
    for _ in range(header[3]):
        offset = skip_name(offset)
        record_kind, _, _, length = struct.unpack("!HHIH", data[offset:offset + 10])
        offset += 10
        answers.append((record_kind, data[offset:offset + length]))
        offset += length
    return answers


def test_live_bind_zone_validation_and_authoritative_answers(panel, account, tmp_path):
    root = os.environ.get("MIKA_TEST_BIND_ROOT")
    if not root:
        pytest.skip("Real BIND binaries not supplied")
    root = Path(root)
    dns.ensure_records(account)
    account.dns_records.create(kind="AAAA", name="ipv6", value="2001:db8::42", ttl=600)
    account.dns_records.create(kind="MX", name="@", value="mail.example.test.", priority=10, ttl=600)
    account.dns_records.create(kind="TXT", name="_verify", value='Unicode café; quote " safe', ttl=600)
    zone = tmp_path / "hosting.zone"
    zone.write_text(dns.render_zone(account))
    env = {**os.environ, "LD_LIBRARY_PATH": str(root / "usr/lib/x86_64-linux-gnu")}
    subprocess.run([str(root / "usr/bin/named-checkzone"), account.domain, str(zone)], env=env, check=True, capture_output=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0)); port = listener.getsockname()[1]
    config = tmp_path / "named.conf"
    config.write_text(f'options {{ directory "{tmp_path}"; recursion no; listen-on port {port} {{ 127.0.0.1; }}; listen-on-v6 {{ none; }}; pid-file "{tmp_path}/named.pid"; session-keyfile "{tmp_path}/session.key"; }}; controls {{ }}; zone "{account.domain}" {{ type primary; file "{zone}"; }};')
    subprocess.run([str(root / "usr/bin/named-checkconf"), str(config)], env=env, check=True, capture_output=True)
    with (tmp_path / "named.log").open("w") as log:
        server = subprocess.Popen([str(root / "usr/sbin/named"), "-g", "-c", str(config), "-n", "1", "-U", "1"], env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    answers = query(account.domain, 1, port)
                    break
                except socket.timeout:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise AssertionError(log.name + ": BIND failed to answer")
            assert (1, socket.inet_aton(panel.MIKA_SERVER_IP)) in answers
            assert any(kind == 5 for kind, _ in query("www." + account.domain, 1, port))
            assert (28, socket.inet_pton(socket.AF_INET6, "2001:db8::42")) in query("ipv6." + account.domain, 28, port)
            assert any(kind == 15 and payload[:2] == b"\0\x0a" for kind, payload in query(account.domain, 15, port))
            assert any(kind == 16 and b"caf\xc3\xa9" in payload for kind, payload in query("_verify." + account.domain, 16, port))
        finally:
            server.terminate(); server.wait(timeout=10)


@pytest.mark.parametrize("connected_include", [True, False])
def test_live_bind_publication_reconfig_serial_udp_tcp_and_missing_include(panel, account, tmp_path, monkeypatch, connected_include):
    from hosting.dns_wire import query as wire_query, zone_ready
    root = os.environ.get("MIKA_TEST_BIND_ROOT")
    if not root:
        pytest.skip("Real BIND binaries not supplied")
    root = Path(root)
    env = {**os.environ, "LD_LIBRARY_PATH": str(root / "usr/lib/x86_64-linux-gnu")}
    def free_port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]
    dns_port, control_port = free_port(), free_port()
    panel.MIKA_PROVISION_MODE = "system"
    panel.MIKA_DNS_ENABLED = True
    panel.MIKA_DNS_PORT = dns_port
    panel.MIKA_BIND_DIR = tmp_path / "bind"
    panel.MIKA_BIND_DIR.mkdir()
    include = panel.MIKA_BIND_DIR / "mika-zones.conf"
    include.write_text("")
    secret = base64.b64encode(secrets.token_bytes(32)).decode()
    key = f'key "mika-test" {{ algorithm hmac-sha256; secret "{secret}"; }};'
    config = tmp_path / "named.conf"
    config.write_text(key + f' options {{ directory "{tmp_path}"; recursion no; listen-on port {dns_port} {{ 127.0.0.1; }}; listen-on-v6 {{ none; }}; pid-file "{tmp_path}/named.pid"; session-keyfile "{tmp_path}/session.key"; }}; controls {{ inet 127.0.0.1 port {control_port} allow {{ 127.0.0.1; }} keys {{ "mika-test"; }}; }};' + (f'include "{include}";' if connected_include else ""))
    rndc_config = tmp_path / "rndc.conf"
    rndc_config.write_text(key + f' options {{ default-server 127.0.0.1; default-port {control_port}; default-key "mika-test"; }};')
    config.chmod(0o600); rndc_config.chmod(0o600)
    def bind_command(*args):
        name, *rest = args
        if name == "rndc":
            command = [str(root / "usr/sbin/rndc"), "-c", str(rndc_config), *rest]
        elif name == "named-checkconf":
            command = [str(root / "usr/bin/named-checkconf"), *rest, str(config)]
        else:
            command = [str(root / "usr/bin/named-checkzone"), *rest]
        return subprocess.run(command, check=True, env=env, capture_output=True, text=True, timeout=20)
    monkeypatch.setattr(dns, "bind_command", bind_command)
    with (tmp_path / "publication.log").open("w") as log:
        server = subprocess.Popen([str(root / "usr/sbin/named"), "-g", "-c", str(config), "-n", "1", "-U", "1"], env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    bind_command("rndc", "status")
                    break
                except subprocess.CalledProcessError:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise AssertionError("Isolated BIND control channel failed: " + log.name)
                    time.sleep(.1)
            if not connected_include:
                with pytest.raises(dns.DNSPublishError, match="include"):
                    dns.publish(account)
                assert include.read_text() == ""
                account.refresh_from_db()
                assert account.dns_state != "published"
                assert wire_query("127.0.0.1", account.domain, port=dns_port)["status"] == "REFUSED"
                return
            dns.publish(account)
            account.refresh_from_db()
            assert account.dns_state == "published"
            for tcp in [False, True]:
                response = wire_query("127.0.0.1", account.domain, port=dns_port, tcp=tcp)
                assert zone_ready(response, account.domain, account.dns_serial, panel.MIKA_DNS_PRIMARY)
            account.dns_records.filter(name="@", kind="A").update(value="203.0.113.42")
            dns.enqueue_sync(account)
            dns.publish(account)
            account.refresh_from_db()
            assert account.dns_serial == 2 and account.dns_state == "published"
            for tcp in [False, True]:
                response = wire_query("127.0.0.1", account.domain, "A", port=dns_port, tcp=tcp)
                assert any(record["value"] == "203.0.113.42" for record in response["records"])
            # A failed verification restores the previously published zone file/config
            # and reloads the previous records; a reload acknowledgement alone is insufficient.
            previous_zone = (panel.MIKA_BIND_DIR / "mika-zones" / f"{account.system_user}.zone").read_text()
            account.dns_records.filter(name="@", kind="A").update(value="203.0.113.99")
            dns.enqueue_sync(account)
            def failed_verification(account):
                raise dns.DNSPublishError("fixture verification failure")
            monkeypatch.setattr(dns, "verify_loaded", failed_verification)
            with pytest.raises(dns.DNSPublishError, match="fixture"):
                dns.publish(account)
            assert (panel.MIKA_BIND_DIR / "mika-zones" / f"{account.system_user}.zone").read_text() == previous_zone
            assert any(record["value"] == "203.0.113.42" for record in wire_query("127.0.0.1", account.domain, "A", port=dns_port)["records"])
            account.refresh_from_db()
            assert account.dns_state == "pending"
        finally:
            server.terminate(); server.wait(timeout=10)
