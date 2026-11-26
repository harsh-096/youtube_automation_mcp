"""YouTube Upload & Studio MCP Server: FastMCP entry point."""

import importlib

from youtube_upload_mcp.runtime import (
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    auth,
    get_allowed_media_dir,
    mcp,
    quota,
)


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
