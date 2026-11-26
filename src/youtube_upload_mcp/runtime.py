"""Shared FastMCP app instance, auth, quota tracker, and tool annotations."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from youtube_upload_mcp.auth import YouTubeAuth
from youtube_upload_mcp.utils.quota import QuotaTracker

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

IDEMPOTENT_WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

DESTRUCTIVE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=True,
)

mcp = FastMCP(
    "YouTube Upload & Studio MCP Server",
    instructions=(
        "Security-hardened MCP server for YouTube video uploads, channel management, "
        "analytics, SEO, transcripts, and bulk reporting."
    ),
)

_config_dir = os.environ.get("YOUTUBE_MCP_CONFIG_DIR")
_daily_quota = int(os.environ.get("YOUTUBE_MCP_DAILY_QUOTA", "10000"))

auth = YouTubeAuth(
    client_secret_path=os.environ.get("YOUTUBE_MCP_CLIENT_SECRET"),
    config_dir=_config_dir,
    api_key=os.environ.get("YOUTUBE_API_KEY"),
    scope_profile=os.environ.get("YOUTUBE_MCP_SCOPE_PROFILE"),
)

quota = QuotaTracker(
    daily_limit=_daily_quota,
    state_path=auth.config_dir / "quota.json",
)


def get_allowed_media_dir() -> Path | None:
    """Return configured upload media directory allowlist, if set."""
    raw = os.environ.get("YOUTUBE_MCP_ALLOWED_MEDIA_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else None
