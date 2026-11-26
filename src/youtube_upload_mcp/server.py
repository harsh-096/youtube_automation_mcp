"""YouTube Upload & Studio MCP Server — FastMCP entry point."""

import importlib
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


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_auth() -> dict:
    """Initiate OAuth 2.0 authentication flow.

    Opens a browser window for Google OAuth consent using your own
    client_secret.json. Required before using tools that access or modify
    your YouTube channel.
    """
    try:
        auth.authenticate()
        return {"status": "authenticated", "detail": auth.status()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_auth_status() -> dict:
    """Check current authentication status, scope profile, and daily quota usage."""
    return {
        "auth": auth.status(),
        "quota": quota.status(),
        "allowed_media_dir": str(get_allowed_media_dir()) if get_allowed_media_dir() else None,
    }


def _register_tools() -> None:
    """Import all tool modules so their @mcp.tool() decorators register."""
    for module_name in (
        "analytics",
        "channel",
        "comments",
        "playlists",
        "publishing",
        "reporting",
        "search",
        "transcripts",
    ):
        importlib.import_module(f"youtube_upload_mcp.tools.{module_name}")


_register_tools()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
