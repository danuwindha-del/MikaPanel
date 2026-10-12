import io
import struct
from unittest.mock import patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from hosting import dns
from hosting.dns_wire import encode_name, parse_response, zone_ready
from hosting.models import Account
from tools.check_dns import check_dns
from tools.repair_dns import open_dns_firewall


def packet(name="example.test", serial=7, status=0, authoritative=True):
    question = encode_name(name) + struct.pack("!HH", 6, 1)
    soa = encode_name("ns1.mychahost.my.id") + encode_name("hostmaster." + name) + struct.pack("!5I", serial, 3600, 900, 1209600, 300)
    record = b"\xc0\x0c" + struct.pack("!HHIH", 6, 1, 3600, len(soa)) + soa
    return struct.pack("!6H", 5342, 0x8000 | (0x400 if authoritative else 0) | status, 1, 1, 0, 0) + question + record


def test_dns_response_checks_authority_question_and_serial():
    response = parse_response(packet(), 5342, "example.test", "SOA")
    assert zone_ready(response, "example.test", 7, "ns1.mychahost.my.id")
    assert not zone_ready(response, "example.test", 8, "ns1.mychahost.my.id")
    assert not zone_ready(response, "sub.example.test", 7, "ns1.mychahost.my.id")
    assert not zone_ready(parse_response(packet(authoritative=False), 5342, "example.test", "SOA"), "example.test", 7, "ns1.mychahost.my.id")
    with pytest.raises(ValueError):
        parse_response(packet(), 10, "example.test", "SOA")
    with pytest.raises(ValueError):
        parse_response(packet(), 5342, "different.test", "SOA")


def test_dns_parser_rejects_short_packets_compression_loops_and_invalid_names():
    with pytest.raises(ValueError):
        parse_response(b"short", 5342, "example.test", "SOA")
    loop = struct.pack("!6H", 5342, 0x8400, 1, 0, 0, 0) + b"\xc0\x0c" + struct.pack("!HH", 6, 1)
    with pytest.raises(ValueError):
        parse_response(loop, 5342, "example.test", "SOA")
    with pytest.raises(ValueError):
        parse_response(packet()[:-3], 5342, "example.test", "SOA")
    for name in ["a\n.test", "a..test", "a" * 64 + ".test"]:
        with pytest.raises(ValueError):
            encode_name(name)


@pytest.mark.django_db
def test_publication_refuses_disconnected_include_and_restores_files(panel, account, tmp_path):
    panel.MIKA_PROVISION_MODE = "system"; panel.MIKA_DNS_ENABLED = True
    panel.MIKA_BIND_DIR = tmp_path / "bind"
    (panel.MIKA_BIND_DIR / "mika-zones").mkdir(parents=True)
    include = panel.MIKA_BIND_DIR / "mika-zones.conf"
    include.write_text("previous include")
    def command(*args):
        return type("Result", (), {"stdout": "localhost IN _default\n"})()
    with patch("hosting.dns.bind_command", side_effect=command):
        with pytest.raises(dns.DNSPublishError, match="include"):
            dns.publish(account)
    assert include.read_text() == "previous include"
    assert not (panel.MIKA_BIND_DIR / "mika-zones" / f"{account.system_user}.zone").exists()
    account.refresh_from_db()
    assert account.dns_state != "published"


@pytest.mark.django_db
def test_verification_fails_if_tcp_is_blocked_or_serial_is_stale(panel, account):
    account.dns_serial = 7
    response = parse_response(packet(account.domain), 5342, account.domain, "SOA")
    with patch("hosting.dns.bind_command"), patch("hosting.dns.query", side_effect=[response, ConnectionRefusedError()]), patch("hosting.dns.time.monotonic", side_effect=[0, 7]):
        with pytest.raises(dns.DNSPublishError, match="UDP dan TCP"):
            dns.verify_loaded(account)
    response["records"][0]["value"]["serial"] = 6
    with patch("hosting.dns.bind_command"), patch("hosting.dns.query", return_value=response), patch("hosting.dns.time.monotonic", side_effect=[0, 7]):
        with pytest.raises(dns.DNSPublishError):
            dns.verify_loaded(account)


@pytest.mark.django_db
def test_rebuild_does_not_create_parent_hosting_accounts(panel, account):
    before = Account.objects.count()
    with pytest.raises(CommandError, match="domain induk"):
        call_command("rebuild_dns", domain="example.test")
    assert Account.objects.count() == before
    call_command("rebuild_dns", domain=account.domain, stdout=io.StringIO())
    account.refresh_from_db()
    assert account.dns_state == "demo"
    assert Account.objects.count() == before


def test_nameserver_diagnostics_reports_missing_a_and_proxy_address(capsys):
    values = {"MIKA_SERVER_IP": "172.236.9.185", "MIKA_DNS_PRIMARY": "ns1.mychahost.my.id", "MIKA_DNS_SECONDARY": "ns2.mychahost.my.id"}
    responses = [{"status": "NXDOMAIN", "records": []}, {"status": "NOERROR", "records": [
        {"section": "answer", "name": "ns2.mychahost.my.id", "type": "A", "value": "104.16.0.1"}]}]
    with patch("tools.check_dns.query", side_effect=responses):
        assert check_dns(values) == 2
    output = capsys.readouterr().out
    assert "NXDOMAIN" in output and "DNS only" in output


def test_repair_firewall_preserves_inactive_ufw_and_only_adds_dns_rules():
    with patch("tools.repair_dns.shutil.which", return_value="/usr/sbin/ufw"), patch("tools.repair_dns.subprocess.run") as run:
        run.return_value.stdout = "Status: inactive"
        open_dns_firewall()
        assert run.call_count == 1
        run.reset_mock(); run.return_value.stdout = "Status: active"
        open_dns_firewall()
        assert [call.args[0] for call in run.call_args_list] == [["ufw", "status"], ["ufw", "allow", "53/udp"], ["ufw", "allow", "53/tcp"]]
