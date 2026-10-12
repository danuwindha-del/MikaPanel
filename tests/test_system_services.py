from pathlib import Path
from unittest.mock import patch
import pytest
from tools.system_services import configure_services, dns_preflight, load_environment, add_environment
from tools.update_vps import source_files


def test_authoritative_service_configuration_idempotent_and_preserves_zone_include(tmp_path):
    bind = tmp_path / "bind"
    bind.mkdir()
    (bind / "named.conf.local").write_text("// stock Ubuntu config\n")
    (bind / "named.conf.options").write_text('options { directory "/var/cache/bind"; dnssec-validation auto; listen-on-v6 { any; }; };')
    with patch("tools.system_services.subprocess.run") as run:
        configure_services(bind, tmp_path / "mysql", tmp_path / "nginx")
        (bind / "mika-zones.conf").write_text('zone "example.test" { type primary; file "/managed/example.zone"; };')
        configure_services(bind, tmp_path / "mysql", tmp_path / "nginx")
    assert (bind / "named.conf.local").read_text().count('include "') == 1
    assert 'zone "example.test"' in (bind / "mika-zones.conf").read_text()
    assert "recursion no;" in (bind / "named.conf.options").read_text()
    assert "allow-transfer { none; }" in (bind / "named.conf.options").read_text()
    assert "bind-address=127.0.0.1" in (tmp_path / "mysql/60-mikapanels.cnf").read_text()
    assert run.call_count == 4


def test_custom_dns_configuration_not_overwritten(tmp_path):
    bind = tmp_path / "bind"; bind.mkdir()
    local = bind / "named.conf.local"
    local.write_text('zone "existing.test" { type primary; file "/private/custom"; };')
    with pytest.raises(RuntimeError, match="zone khusus"):
        dns_preflight(bind)
    assert local.read_text().startswith('zone "existing.test"')


def test_environment_additions_preserve_secrets_without_printing(tmp_path, capsys):
    path = tmp_path / "panel.env"
    path.write_text('MIKA_SECRET_KEY="fixture-secret-preserved"\nMIKA_DNS_PRIMARY="ns1.custom.test"\n')
    result = add_environment(path, {"MIKA_DNS_PRIMARY": "ns1.new.test", "MIKA_DNS_ENABLED": "1"})
    assert result["MIKA_DNS_PRIMARY"] == "ns1.custom.test"
    assert load_environment(path)["MIKA_SECRET_KEY"] == "fixture-secret-preserved"
    assert path.read_text().count("MIKA_SECRET_KEY=") == 1
    assert "fixture-secret-preserved" not in capsys.readouterr().out


def test_upgrade_source_files_exclude_runtime_and_credentials(tmp_path):
    for name in ["manage.py", "hosting/models.py", "var/config.json", ".venv/bin/python", ".git/config", ".env.production"]:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("fixture")
    assert {str(path.relative_to(tmp_path)) for path in source_files(tmp_path)} == {"manage.py", "hosting/models.py"}


def test_inherited_shell_settings_do_not_hide_missing_flags_or_cross_service_secrets(tmp_path, monkeypatch):
    path = tmp_path / "panel.env"
    path.write_text('MIKA_SERVICE="panel"\n')
    monkeypatch.setenv("MIKA_DNS_ENABLED", "0")
    monkeypatch.setenv("TRIPAY_PRIVATE_KEY", "fixture-other-service")
    values = load_environment(path)
    assert values == {"MIKA_SERVICE": "panel"}
    add_environment(path, {"MIKA_DNS_ENABLED": "1"})
    assert load_environment(path)["MIKA_DNS_ENABLED"] == "1"
    assert 'MIKA_DNS_ENABLED="1"' in path.read_text()
    assert "fixture-other-service" not in path.read_text()


def test_additions_do_not_join_previous_last_line_or_partially_write_invalid_values(tmp_path):
    path = tmp_path / "panel.env"
    path.write_text('MIKA_SERVICE="panel"')
    add_environment(path, {"MIKA_DNS_ENABLED": "1"})
    assert load_environment(path) == {"MIKA_SERVICE": "panel", "MIKA_DNS_ENABLED": "1"}
    before = path.read_bytes()
    with pytest.raises(ValueError):
        add_environment(path, {"MIKA_MYSQL_ENABLED": "1", "BAD VALUE": "unsafe"})
    assert path.read_bytes() == before
