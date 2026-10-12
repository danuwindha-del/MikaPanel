"""Opt-in functional tests against an isolated MariaDB socket and real BIND binaries.

Never point MIKA_TEST_MYSQL_SOCKET at a production database. Tests create/drop schemas.
"""
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
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
