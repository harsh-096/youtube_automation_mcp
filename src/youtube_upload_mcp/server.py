"""YouTube Upload & Studio MCP Server: FastMCP entry point."""

import importlib

from youtube_upload_mcp.runtime import (
    IDEMPOTENT_WRITE_ANNOTATIONS,
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    account_manager,
    auth,
    get_allowed_media_dir,
    mcp,
    quota,
)
from youtube_upload_mcp.utils.validators import ValidationError


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_auth() -> dict:
    """Initiate OAuth 2.0 authentication flow for the active account.

    Opens a browser window for Google OAuth consent using the active account's
    client_secret.json. Required before using tools that access or modify
    your YouTube channel.
    """
    try:
        auth.authenticate()
        return {
            "status": "authenticated",
            "account": account_manager.active_account,
            "detail": auth.status(),
        }
    except Exception as e:
        return {"status": "error", "account": account_manager.active_account, "detail": str(e)}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_auth_status() -> dict:
    """Check active account, authentication status, scope profile, and daily quota usage."""
    return {
        "active_account": account_manager.active_account,
        "auth": auth.status(),
        "quota": quota.status(),
        "allowed_media_dir": str(get_allowed_media_dir()) if get_allowed_media_dir() else None,
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_list_accounts() -> dict:
    """List all configured YouTube accounts, auth state, and remaining daily quota."""
    return account_manager.list_accounts()


@mcp.tool(annotations=IDEMPOTENT_WRITE_ANNOTATIONS)
def youtube_switch_account(account: str = "default") -> dict:
    """Switch the active YouTube account profile for subsequent tool calls.

    Args:
        account: Account profile name (e.g., "default", "gaming", "account2").
    """
    try:
        return account_manager.switch_account(account)
    except ValidationError as e:
        return {"error": str(e)}


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_add_account(
    account: str,
    client_secret_path: str | None = None,
    switch: bool = True,
) -> dict:
    """Add a new named YouTube account profile with isolated tokens and quota.

    Args:
        account: Profile name (e.g., "account2", "brand_channel").
        client_secret_path: Optional path to a Google OAuth client_secret.json
            file to copy into this account's profile directory. If omitted,
            falls back to the default client_secret.json.
        switch: If True (default), switch the active account to the new profile.
    """
    try:
        return account_manager.add_account(
            account,
            client_secret_path=client_secret_path,
            switch=switch,
        )
    except ValidationError as e:
        return {"error": str(e)}


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
