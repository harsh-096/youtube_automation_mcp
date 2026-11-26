"""Shared FastMCP app instance, multi-account runtime proxies, and tool annotations."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from youtube_upload_mcp.accounts import AccountManager

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


class _ActiveAuthProxy:
    """Delegates attribute access to the currently active account's YouTubeAuth."""

    def __init__(self, manager: AccountManager):
        self._manager = manager

    def __getattr__(self, item: str):
        return getattr(self._manager.active_auth, item)


class _ActiveQuotaProxy:
    """Delegates attribute access to the currently active account's QuotaTracker."""

    def __init__(self, manager: AccountManager):
        self._manager = manager

    def __getattr__(self, item: str):
        return getattr(self._manager.active_quota, item)


mcp = FastMCP(
    "YouTube Upload & Studio MCP Server",
    instructions=(
        "Security-hardened MCP server for YouTube video uploads, channel management, "
        "analytics, SEO, transcripts, and bulk reporting."
    ),
)

_config_dir = os.environ.get("YOUTUBE_MCP_CONFIG_DIR")
_daily_quota = int(os.environ.get("YOUTUBE_MCP_DAILY_QUOTA", "10000"))
_initial_account = os.environ.get("YOUTUBE_MCP_ACCOUNT", "default")

account_manager = AccountManager(
    base_config_dir=_config_dir,
    explicit_client_secret=os.environ.get("YOUTUBE_MCP_CLIENT_SECRET"),
    api_key=os.environ.get("YOUTUBE_API_KEY"),
    scope_profile=os.environ.get("YOUTUBE_MCP_SCOPE_PROFILE"),
    daily_quota=_daily_quota,
    initial_account=_initial_account,
)

auth = _ActiveAuthProxy(account_manager)
quota = _ActiveQuotaProxy(account_manager)


def get_allowed_media_dir() -> Path | None:
    """Return configured upload media directory allowlist, if set."""
    raw = os.environ.get("YOUTUBE_MCP_ALLOWED_MEDIA_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else None
