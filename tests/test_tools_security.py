"""Tests for MCP tool behavior, safety guardrails, and annotations."""

import asyncio
import runpy
from unittest.mock import MagicMock, patch

from youtube_upload_mcp.runtime import mcp as runtime_mcp
from youtube_upload_mcp.server import mcp


class TestToolAnnotations:
    def test_all_registered_tools_have_annotations(self):
        tools = asyncio.run(mcp.list_tools())
        assert len(tools) >= 46
        by_name = {tool.name: tool for tool in tools}

        for tool in tools:
            assert tool.annotations is not None, f"{tool.name} is missing ToolAnnotations"

        assert by_name["youtube_delete_video"].annotations.destructiveHint is True
        assert by_name["youtube_delete_playlist"].annotations.destructiveHint is True
        assert by_name["youtube_delete_comment"].annotations.destructiveHint is True
        assert by_name["youtube_remove_from_playlist"].annotations.destructiveHint is True

        assert by_name["youtube_get_channel"].annotations.readOnlyHint is True
        assert by_name["youtube_list_accounts"].annotations.readOnlyHint is True
        assert by_name["youtube_analytics_overview"].annotations.readOnlyHint is True
        assert by_name["youtube_upload_video"].annotations.readOnlyHint is False

    def test_running_server_as_main_registers_all_tools(self):
        with patch.object(runtime_mcp, "run"):
            ns = runpy.run_module("youtube_upload_mcp.server", run_name="__main__")
        tools = asyncio.run(ns["mcp"].list_tools())
        assert len(tools) >= 46


class TestPublishingSafety:
    @patch("youtube_upload_mcp.tools.publishing.MediaFileUpload")
    @patch("youtube_upload_mcp.tools.publishing.auth")
    @patch("youtube_upload_mcp.tools.publishing.quota")
    def test_upload_defaults_to_private(self, mock_quota, mock_auth, mock_media, tmp_path):
        from youtube_upload_mcp.tools.publishing import youtube_upload_video

        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"mp4-bytes")

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        mock_yt.videos().insert().execute.return_value = {
            "id": "vid_123",
            "snippet": {"title": "Clip"},
            "status": {"privacyStatus": "private"},
        }

        result = youtube_upload_video(file_path=str(video_file), title="Clip")
        assert result["id"] == "vid_123"
        assert result["privacy"] == "private"
        mock_quota.consume.assert_called_once_with("video_insert")

    @patch("youtube_upload_mcp.tools.publishing.quota")
    def test_upload_blocked_outside_allowed_media_dir(
        self, mock_quota, tmp_path, monkeypatch
    ):
        from youtube_upload_mcp.tools.publishing import youtube_upload_video

        allowed = tmp_path / "media"
        outside = tmp_path / "private"
        allowed.mkdir()
        outside.mkdir()
        secret_file = outside / "secret.mp4"
        secret_file.write_bytes(b"secret")

        monkeypatch.setenv("YOUTUBE_MCP_ALLOWED_MEDIA_DIR", str(allowed))
        result = youtube_upload_video(file_path=str(secret_file), title="Leak")
        assert "error" in result
        assert "YOUTUBE_MCP_ALLOWED_MEDIA_DIR" in result["error"]
        mock_quota.consume.assert_not_called()

    @patch("youtube_upload_mcp.tools.publishing.quota")
    def test_thumbnail_rejects_over_2mb(self, mock_quota, tmp_path):
        from youtube_upload_mcp.tools.publishing import youtube_set_thumbnail

        big_img = tmp_path / "huge.png"
        big_img.write_bytes(b"0" * (2 * 1024 * 1024 + 1))

        result = youtube_set_thumbnail("vid_123", str(big_img))
        assert "error" in result
        assert "exceeds maximum allowed" in result["error"]
        mock_quota.consume.assert_not_called()

    @patch("youtube_upload_mcp.tools.publishing.auth")
    @patch("youtube_upload_mcp.tools.publishing.quota")
    def test_delete_video_requires_confirm(self, mock_quota, mock_auth):
        from youtube_upload_mcp.tools.publishing import youtube_delete_video

        dry = youtube_delete_video("vid_123")
        assert dry["deleted"] is False
        assert dry["confirmation_required"] is True
        mock_quota.consume.assert_not_called()
        mock_auth.build_youtube_service.assert_not_called()

        mock_yt = MagicMock()
        mock_auth.build_youtube_service.return_value = mock_yt
        real = youtube_delete_video("vid_123", confirm=True)
        assert real["deleted"] is True
        mock_quota.consume.assert_called_once_with("delete")


class TestPlaylistAndCommentConfirmations:
    @patch("youtube_upload_mcp.tools.playlists.auth")
    @patch("youtube_upload_mcp.tools.playlists.quota")
    def test_delete_playlist_requires_confirm(self, mock_quota, mock_auth):
        from youtube_upload_mcp.tools.playlists import youtube_delete_playlist

        res = youtube_delete_playlist("PL123")
        assert res["deleted"] is False
        assert res["confirmation_required"] is True
        mock_quota.consume.assert_not_called()

    @patch("youtube_upload_mcp.tools.comments.auth")
    @patch("youtube_upload_mcp.tools.comments.quota")
    def test_delete_comment_requires_confirm(self, mock_quota, mock_auth):
        from youtube_upload_mcp.tools.comments import youtube_delete_comment

        res = youtube_delete_comment("cmt_123")
        assert res["deleted"] is False
        assert res["confirmation_required"] is True
        mock_quota.consume.assert_not_called()


class TestReportingAndAnalyticsSecurity:
    @patch("youtube_upload_mcp.tools.reporting.auth")
    def test_reporting_download_blocks_untrusted_host(self, mock_auth):
        from youtube_upload_mcp.tools.reporting import youtube_reporting_download

        res = youtube_reporting_download("https://attacker.example/steal")
        assert "error" in res
        assert "Blocked untrusted download host" in res["error"]
        mock_auth.credentials.assert_not_called()

    @patch("youtube_upload_mcp.tools.reporting.urllib.request.build_opener")
    @patch("youtube_upload_mcp.tools.reporting.auth")
    def test_reporting_download_allows_googleapis(self, mock_auth, mock_opener):
        from youtube_upload_mcp.tools.reporting import youtube_reporting_download

        mock_auth.credentials.token = "tok123"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"video_id,views\nabc,10\n"
        mock_resp.__enter__.return_value = mock_resp
        mock_opener.return_value.open.return_value = mock_resp

        res = youtube_reporting_download(
            "https://youtubereporting.googleapis.com/v1/media/rep1?alt=media"
        )
        assert res["row_count"] == 1
        assert res["columns"] == "video_id,views"

    @patch("youtube_upload_mcp.tools.analytics.auth")
    def test_analytics_rejects_filter_injection(self, mock_auth):
        from youtube_upload_mcp.tools.analytics import youtube_analytics_video_detail

        res = youtube_analytics_video_detail("vid1;country==US")
        assert "error" in res
        mock_auth.build_youtube_analytics_service.assert_not_called()
