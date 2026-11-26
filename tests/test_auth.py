"""Tests for auth module and scope profiles."""

import json
from unittest.mock import MagicMock

import pytest

from youtube_upload_mcp.auth import SCOPE_PROFILES, AuthError, YouTubeAuth, resolve_scopes


def _write_token(tmp_path, scopes, expiry="2099-01-01T00:00:00Z"):
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({
            "token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "client_id": "fake-client-id",
            "client_secret": "fake-client-secret",
            "scopes": scopes,
            "expiry": expiry,
        }),
        encoding="utf-8",
    )
    return token_path


def test_scope_profiles():
    assert "https://www.googleapis.com/auth/youtube.upload" in resolve_scopes("upload_only")
    assert "https://www.googleapis.com/auth/youtube" not in resolve_scopes("upload_only")
    assert resolve_scopes("read_only") == SCOPE_PROFILES["read_only"]

    with pytest.raises(AuthError, match="Unknown scope profile"):
        resolve_scopes("admin_all")


def test_missing_client_secret_raises_auth_error(tmp_path):
    yt_auth = YouTubeAuth(
        config_dir=tmp_path,
        client_secret_path=tmp_path / "missing.json",
    )
    with pytest.raises(AuthError, match="client_secret.json not found"):
        yt_auth.authenticate()


def test_cached_token_with_insufficient_scopes_is_invalidated(tmp_path):
    token_path = _write_token(tmp_path, SCOPE_PROFILES["read_only"])
    yt_auth = YouTubeAuth(
        config_dir=tmp_path,
        client_secret_path=tmp_path / "missing.json",
        scope_profile="full",
    )

    with pytest.raises(AuthError, match="client_secret.json not found"):
        yt_auth.authenticate()

    assert not token_path.exists()


def test_cached_token_matching_profile_is_accepted(tmp_path):
    _write_token(tmp_path, SCOPE_PROFILES["upload_only"])
    yt_auth = YouTubeAuth(config_dir=tmp_path, scope_profile="upload_only")

    creds = yt_auth.authenticate()
    assert creds.valid
    assert yt_auth.status()["authenticated"] is True
    assert yt_auth.status()["scope_profile"] == "upload_only"


def test_save_token_creates_file(tmp_path):
    yt_auth = YouTubeAuth(config_dir=tmp_path)
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = json.dumps({"token": "t"})
    yt_auth._save_token(mock_creds)
    assert (tmp_path / "token.json").exists()
