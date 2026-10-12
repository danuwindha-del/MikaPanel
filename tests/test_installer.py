import io
from unittest.mock import patch
from rich.console import Console
from tools import install_vps


def test_short_password_retries_without_exposing_input():
    output = io.StringIO()
    strong = "Unique-fixture-installer-2048!"
    with patch.object(install_vps, "console", Console(file=output)), patch.object(
        install_vps.getpass, "getpass", side_effect=["short-input", strong, strong]
    ):
        assert install_vps.prompt_admin_password() == strong
    assert "Minimal 12 karakter" in output.getvalue()
    assert "short-input" not in output.getvalue() and strong not in output.getvalue()


def test_confirmation_mismatch_retries():
    output = io.StringIO()
    first = "Unique-fixture-first-2048!"
    second = "Unique-fixture-second-4096!"
    with patch.object(install_vps, "console", Console(file=output)), patch.object(
        install_vps.getpass, "getpass", side_effect=[first, "mismatch", second, second]
    ):
        assert install_vps.prompt_admin_password() == second
    assert "Kedua password tidak sama" in output.getvalue()
    assert first not in output.getvalue() and second not in output.getvalue()


def test_numeric_password_rejected_before_install():
    output = io.StringIO()
    strong = "Unique-fixture-installer-2048!"
    with patch.object(install_vps, "console", Console(file=output)), patch.object(
        install_vps.getpass, "getpass", side_effect=["93827164502918374650", strong, strong]
    ):
        assert install_vps.prompt_admin_password() == strong
    assert "tidak boleh hanya berisi angka" in output.getvalue()
