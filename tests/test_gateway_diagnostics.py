import io
from unittest.mock import Mock, patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_missing_key_never_calls_gateway(shop):
    shop.TRIPAY_API_KEY = ""
    output = io.StringIO()
    with patch("storefront.management.commands.check_tripay.requests.get") as get, pytest.raises(CommandError):
        call_command("check_tripay", stdout=output)
    get.assert_not_called()
    assert "TRIPAY_API_KEY: KOSONG" in output.getvalue()


def test_diagnostic_checks_channels_without_payment_or_key_output(shop):
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": [{"code": code, "active": True} for code in shop.PAYMENT_CHANNELS]}
    output = io.StringIO()
    with patch("storefront.management.commands.check_tripay.requests.get", return_value=response) as get:
        call_command("check_tripay", stdout=output)
    assert get.call_args.args[0] == "https://tripay.co.id/api-sandbox/merchant/payment-channel"
    assert get.call_args.kwargs.get("verify", True) is True
    assert "Tidak ada pembayaran yang dibuat" in output.getvalue()
    for value in (shop.TRIPAY_API_KEY, shop.TRIPAY_PRIVATE_KEY, shop.TRIPAY_MERCHANT_CODE):
        assert value not in output.getvalue()


def test_inactive_channel_is_reported(shop):
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": [{"code": "BRIVA", "active": False}]}
    output = io.StringIO()
    with patch("storefront.management.commands.check_tripay.requests.get", return_value=response), pytest.raises(CommandError):
        call_command("check_tripay", stdout=output)
    assert "BRIVA: TIDAK TERSEDIA" in output.getvalue()


def test_auth_error_does_not_echo_gateway_body(shop):
    response = Mock(status_code=403)
    response.json.return_value = {"message": shop.TRIPAY_API_KEY}
    output = io.StringIO()
    with patch("storefront.management.commands.check_tripay.requests.get", return_value=response), pytest.raises(CommandError, match="menolak akses"):
        call_command("check_tripay", stdout=output)
    assert shop.TRIPAY_API_KEY not in output.getvalue()
