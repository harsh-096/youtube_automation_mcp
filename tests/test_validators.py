"""Tests for security and input validators."""

import pytest

from youtube_upload_mcp.utils.validators import (
    ValidationError,
    validate_googleapis_download_url,
    validate_media_path,
    validate_privacy_status,
    validate_youtube_id,
)


class TestValidateYouTubeId:
    def test_valid_ids(self):
        assert validate_youtube_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert validate_youtube_id("UC_x5XG1OV2P6uZZ5FSM9Ttw") == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        assert validate_youtube_id("abc.123-xyz") == "abc.123-xyz"

    @pytest.mark.parametrize(
        "bad_id",
        [
            "",
            "   ",
            "vid1;country==US",
            "vid1,vid2",
            "vid1==foo",
            "../etc/passwd",
            "vid with spaces",
            "a" * 129,
        ],
    )
    def test_rejects_injection_and_malformed_ids(self, bad_id):
        with pytest.raises(ValidationError):
            validate_youtube_id(bad_id, "video_id")


class TestValidatePrivacyStatus:
    @pytest.mark.parametrize("status", ["private", "public", "unlisted"])
    def test_valid_statuses(self, status):
        assert validate_privacy_status(status) == status

    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            validate_privacy_status("friends_only")


class TestValidateMediaPath:
    def test_valid_file(self, tmp_path):
        video = tmp_path / "demo.mp4"
        video.write_bytes(b"video-data")
        resolved = validate_media_path(str(video))
        assert resolved == video.resolve()

    def test_enforces_allowed_dir(self, tmp_path):
        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"
        allowed.mkdir()
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("do-not-upload")

        with pytest.raises(ValidationError, match="outside YOUTUBE_MCP_ALLOWED_MEDIA_DIR"):
            validate_media_path(str(secret), allowed_dir=allowed)

    def test_enforces_max_bytes(self, tmp_path):
        thumb = tmp_path / "thumb.png"
        thumb.write_bytes(b"x" * 100)
        with pytest.raises(ValidationError, match="exceeds maximum allowed"):
            validate_media_path(str(thumb), max_bytes=50)

    def test_rejects_directory(self, tmp_path):
        with pytest.raises(ValidationError, match="not a regular file"):
            validate_media_path(str(tmp_path))


class TestValidateGoogleApisDownloadUrl:
    def test_allows_trusted_googleapis_https(self):
        url = "https://youtubereporting.googleapis.com/v1/media/REPORT123?alt=media"
        assert validate_googleapis_download_url(url) == url

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://youtubereporting.googleapis.com/report.csv",
            "https://evil.com/steal-token",
            "https://googleapis.com.evil.com/report.csv",
            "https://user:pass@youtubereporting.googleapis.com/report.csv",
            "https://127.0.0.1/report.csv",
            "https://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "",
        ],
    )
    def test_blocks_untrusted_urls(self, bad_url):
        with pytest.raises(ValidationError):
            validate_googleapis_download_url(bad_url)
