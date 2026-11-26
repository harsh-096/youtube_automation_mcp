# YouTube Upload & Studio MCP Server (`youtube-upload-mcp`)

A **security-hardened** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for uploading videos to YouTube and managing your channel, playlists, comments, analytics, SEO, transcripts, and bulk reports.

## Security & Safety Features

Built from the ground up with guardrails for AI-assisted channel management:

- **MCP Tool Safety Annotations (`ToolAnnotations`):** Every tool declares `readOnlyHint`, `destructiveHint`, and `idempotentHint` so MCP clients prompt before write/delete operations.
- **Explicit Confirmation for Irreversible Deletions:** `youtube_delete_video`, `youtube_delete_playlist`, `youtube_remove_from_playlist`, and `youtube_delete_comment` require `confirm=True` (default `False` returns a dry-run warning).
- **Private-by-Default Publishing:** `youtube_upload_video` and `youtube_create_playlist` default to `privacy_status="private"`.
- **SSRF & Token-Leak Protection:** `youtube_reporting_download` strictly enforces `https://*.googleapis.com` URLs (including across HTTP redirects) so OAuth Bearer tokens cannot be sent to untrusted hosts.
- **Scoped OAuth Profiles:** Choose `YOUTUBE_MCP_SCOPE_PROFILE`:
  - `full` (default): all 46 tools
  - `upload_only`: read channel + upload videos only (no delete/comment/revenue scopes)
  - `read_only`: read-only channel and analytics
- **Multi-Account Isolation:** Manage multiple YouTube channels/Google Cloud projects using `youtube_add_account`, `youtube_switch_account`, and `youtube_list_accounts` (each profile gets its own isolated `token.json` and `quota.json` under `~/.youtube-mcp/accounts/<name>/`).
- **Optional Media Directory Allowlist:** Set `YOUTUBE_MCP_ALLOWED_MEDIA_DIR` to restrict video and thumbnail uploads to a specific folder.
- **Persistent Daily Quota Tracking:** Tracks the 10,000-unit daily YouTube Data API v3 quota in `~/.youtube-mcp/quota.json` (resetting at midnight Pacific Time) so server restarts do not lose quota state.
- **Input Validation:** Sanitizes YouTube IDs before Analytics filter queries and enforces YouTube's 2 MB limit on custom thumbnails.

---

## Prerequisites

- Python 3.11+
- A Google Cloud project with:
  - **YouTube Data API v3**
  - **YouTube Analytics API**
  - **YouTube Reporting API**
- OAuth 2.0 **Desktop App** credentials (`client_secret.json`)

### Google Cloud Setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Enable **YouTube Data API v3**, **YouTube Analytics API**, and **YouTube Reporting API** in **APIs & Services > Library**.
3. Configure **APIs & Services > OAuth consent screen** (External) and add your YouTube channel owner Google account as a **Test User**.
4. Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID > Desktop app**.
5. Download the JSON file and save it as `~/.youtube-mcp/client_secret.json` (or set `YOUTUBE_MCP_CLIENT_SECRET`).

---

## Installation

```bash
git clone <your-repo-url>
cd youtube-upload-mcp
python -m venv .venv
```

Activate the virtual environment and install:

```bash
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# macOS / Linux
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## MCP Client Configuration

Example configuration for Claude Desktop, Claude Code, Cursor, Antigravity, or any MCP client:

**Windows:**

```json
{
  "mcpServers": {
    "youtube": {
      "command": "C:/path/to/youtube-upload-mcp/.venv/Scripts/youtube-upload-mcp.exe",
      "env": {
        "YOUTUBE_MCP_CLIENT_SECRET": "C:/Users/you/.youtube-mcp/client_secret.json",
        "YOUTUBE_MCP_SCOPE_PROFILE": "full",
        "YOUTUBE_MCP_ALLOWED_MEDIA_DIR": "C:/Users/you/Videos/ToUpload"
      }
    }
  }
}
```

**macOS / Linux:**

```json
{
  "mcpServers": {
    "youtube": {
      "command": "/path/to/youtube-upload-mcp/.venv/bin/youtube-upload-mcp",
      "env": {
        "YOUTUBE_MCP_CLIENT_SECRET": "/home/you/.youtube-mcp/client_secret.json",
        "YOUTUBE_MCP_SCOPE_PROFILE": "full",
        "YOUTUBE_MCP_ALLOWED_MEDIA_DIR": "/home/you/Videos/ToUpload"
      }
    }
  }
}
```

> **Tip:** If you only want an AI assistant to upload videos and read stats without deletion or comment permissions, set `"YOUTUBE_MCP_SCOPE_PROFILE": "upload_only"`.

---

## Testing & Verification

### 1. Run Automated Tests & Linter (No Google Account Needed)

```bash
pytest -v
ruff check src tests
```

### 2. Test the MCP Server Interactively with MCP Inspector

If you have Node.js installed, you can inspect and call all 43 tools in a browser UI before connecting an AI client:

```powershell
# Windows (PowerShell)
npx @modelcontextprotocol/inspector C:\path\to\youtube-upload-mcp\.venv\Scripts\youtube-upload-mcp.exe
```

```bash
# macOS / Linux
npx @modelcontextprotocol/inspector /path/to/youtube-upload-mcp/.venv/bin/youtube-upload-mcp
```

### 3. Safe Live End-to-End Test Checklist

Once your `client_secret.json` is in place (`~/.youtube-mcp/client_secret.json`), test in this order:

1. Call `youtube_auth`: opens your browser to sign in with the Google account that owns your channel and saves `~/.youtube-mcp/token.json`.
2. Call `youtube_auth_status`: confirms authentication, active `scope_profile`, and remaining daily quota.
3. Call `youtube_get_channel` with `mine=True`: verifies read access to your channel.
4. Call `youtube_upload_video` with a short test `.mp4` (it defaults to `privacy_status="private"` so nothing goes public until you publish it in YouTube Studio).

### 4. Using Multiple YouTube Accounts

You can register and switch between multiple channels in one server session:

1. Call `youtube_add_account(account="account2", client_secret_path="/path/to/second/client_secret.json")`
2. Call `youtube_auth` to sign in with your second Google account (tokens and daily quota are saved separately under `~/.youtube-mcp/accounts/account2/`).
3. Call `youtube_list_accounts` to view all accounts and their remaining quota, or `youtube_switch_account(account="default")` to switch back.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_MCP_CLIENT_SECRET` | `~/.youtube-mcp/client_secret.json` | Path to Google OAuth Desktop App JSON |
| `YOUTUBE_MCP_CONFIG_DIR` | `~/.youtube-mcp` | Directory for `token.json`, `quota.json`, and `accounts/` |
| `YOUTUBE_MCP_ACCOUNT` | `default` | Initial active account profile (`default` or named account) |
| `YOUTUBE_MCP_SCOPE_PROFILE` | `full` | `full`, `upload_only`, or `read_only` |
| `YOUTUBE_MCP_ALLOWED_MEDIA_DIR` | *(unset)* | Optional folder allowlist for video/thumbnail uploads |
| `YOUTUBE_MCP_DAILY_QUOTA` | `10000` | Daily quota limit enforced client-side |
| `YOUTUBE_API_KEY` | *(unset)* | Optional API key for public-only lookups |

---

## Tools Reference (46 Tools)

- **Auth & Accounts (5):** `youtube_auth`, `youtube_auth_status`, `youtube_list_accounts`, `youtube_switch_account`, `youtube_add_account`
- **Channel & Video (3):** `youtube_get_channel`, `youtube_list_videos`, `youtube_get_video`
- **Publishing (4):** `youtube_upload_video`, `youtube_update_video`, `youtube_set_thumbnail`, `youtube_delete_video`
- **Playlists (6):** `youtube_list_playlists`, `youtube_create_playlist`, `youtube_update_playlist`, `youtube_delete_playlist`, `youtube_add_to_playlist`, `youtube_remove_from_playlist`
- **Comments (4):** `youtube_list_comments`, `youtube_post_comment`, `youtube_reply_to_comment`, `youtube_delete_comment`
- **Search & SEO (4):** `youtube_search`, `youtube_search_suggestions`, `youtube_trending`, `youtube_get_categories`
- **Transcripts (2):** `youtube_list_captions`, `youtube_get_transcript`
- **Analytics (13):** `youtube_analytics_overview`, `youtube_analytics_top_videos`, `youtube_analytics_top_shorts`, `youtube_analytics_video_detail`, `youtube_analytics_traffic_sources`, `youtube_analytics_demographics`, `youtube_analytics_geography`, `youtube_analytics_daily`, `youtube_analytics_day_of_week`, `youtube_analytics_content_type_breakdown`, `youtube_analytics_revenue`, `youtube_analytics_revenue_by_video`, `youtube_analytics_retention`
- **Bulk Reporting (5):** `youtube_reporting_list_types`, `youtube_reporting_create_job`, `youtube_reporting_list_jobs`, `youtube_reporting_list_reports`, `youtube_reporting_download`

---

## License

MIT
