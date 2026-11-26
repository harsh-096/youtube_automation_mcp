"""Tests for multi-account management, isolation, and validation."""

import json

import pytest

from youtube_upload_mcp.accounts import AccountManager
from youtube_upload_mcp.utils.validators import ValidationError


def _make_secret(path, client_id="cid-123"):
    path.write_text(
        json.dumps({"installed": {"client_id": client_id, "client_secret": "sec"}}),
        encoding="utf-8",
    )


def test_default_account_uses_base_config_dir(tmp_path):
    mgr = AccountManager(base_config_dir=tmp_path)
    assert mgr.active_account == "default"
    assert mgr.active_auth.config_dir == tmp_path
    assert mgr.active_quota.state_path == tmp_path / "quota.json"


def test_add_and_switch_accounts_isolates_tokens_and_quotas(tmp_path):
    default_secret = tmp_path / "default_secret.json"
    second_secret = tmp_path / "second_secret.json"
    _make_secret(default_secret, "cid-default")
    _make_secret(second_secret, "cid-second")

    mgr = AccountManager(
        base_config_dir=tmp_path,
        explicit_client_secret=default_secret,
    )

    mgr.active_quota.consume("video_insert")
    assert mgr.active_quota.used == 1600

    added = mgr.add_account("account2", client_secret_path=str(second_secret), switch=True)
    assert added["account"] == "account2"
    assert added["active"] is True
    assert added["client_secret_copied"] is True
    assert mgr.active_account == "account2"
    expected_secret = tmp_path / "accounts" / "account2" / "client_secret.json"
    assert mgr.active_auth.client_secret_path == expected_secret
    assert mgr.active_quota.used == 0

    mgr.active_quota.consume("search")
    assert mgr.active_quota.used == 100

    mgr.switch_account("default")
    assert mgr.active_account == "default"
    assert mgr.active_quota.used == 1600

    listing = mgr.list_accounts()
    assert listing["total"] == 2
    by_name = {a["name"]: a for a in listing["accounts"]}
    assert by_name["default"]["active"] is True
    assert by_name["default"]["quota_used"] == 1600
    assert by_name["account2"]["active"] is False
    assert by_name["account2"]["quota_used"] == 100
    assert by_name["account2"]["has_client_secret"] is True


@pytest.mark.parametrize("bad_name", ["", "../escape", "a/b", "bad name", ".hidden"])
def test_rejects_invalid_account_names(tmp_path, bad_name):
    mgr = AccountManager(base_config_dir=tmp_path)
    with pytest.raises(ValidationError):
        mgr.add_account(bad_name)


def test_rejects_reserved_default_in_add_account(tmp_path):
    mgr = AccountManager(base_config_dir=tmp_path)
    with pytest.raises(ValidationError, match="reserved"):
        mgr.add_account("default")


def test_rejects_invalid_client_secret_file(tmp_path):
    bad_file = tmp_path / "not_a_secret.json"
    bad_file.write_text(json.dumps({"hello": "world"}), encoding="utf-8")

    mgr = AccountManager(base_config_dir=tmp_path)
    with pytest.raises(ValidationError, match="Google OAuth client_secret.json"):
        mgr.add_account("brand", client_secret_path=str(bad_file))


def test_switch_to_nonexistent_account_fails(tmp_path):
    mgr = AccountManager(base_config_dir=tmp_path)
    with pytest.raises(ValidationError, match="does not exist"):
        mgr.switch_account("missing")
