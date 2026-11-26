"""OAuth 2.0 authentication for YouTube APIs with configurable scope profiles."""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPE_PROFILES: dict[str, list[str]] = {
    "full": [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    ],
    "upload_only": [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
    ],
    "read_only": [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ],
}

DEFAULT_CONFIG_DIR = Path.home() / ".youtube-mcp"
TOKEN_FILE = "token.json"


class AuthError(Exception):
    """Raised when authentication configuration or OAuth flow fails."""


def resolve_scopes(profile: str | None = None) -> list[str]:
    """Return the OAuth scope list for the requested profile name."""
    selected = (profile or os.environ.get("YOUTUBE_MCP_SCOPE_PROFILE") or "full").strip().lower()
    if selected not in SCOPE_PROFILES:
        valid = ", ".join(sorted(SCOPE_PROFILES))
        raise AuthError(f"Unknown scope profile {selected!r}. Must be one of: {valid}.")
    return list(SCOPE_PROFILES[selected])


class YouTubeAuth:
    """Manages OAuth 2.0 credentials and builds YouTube API service clients."""

    def __init__(
        self,
        client_secret_path: str | Path | None = None,
        config_dir: str | Path | None = None,
        api_key: str | None = None,
        scope_profile: str | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.token_path = self.config_dir / TOKEN_FILE
        self.scope_profile = (
            scope_profile or os.environ.get("YOUTUBE_MCP_SCOPE_PROFILE") or "full"
        ).strip().lower()
        self.scopes = resolve_scopes(self.scope_profile)
        self._credentials: Credentials | None = None

        if client_secret_path:
            self.client_secret_path = Path(client_secret_path).expanduser()
        else:
            env_path = os.environ.get("YOUTUBE_MCP_CLIENT_SECRET")
            if env_path:
                self.client_secret_path = Path(env_path).expanduser()
            else:
                self.client_secret_path = self.config_dir / "client_secret.json"

        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")

    def _load_token(self) -> Credentials | None:
        """Load saved credentials from token file without overriding recorded scopes."""
        if not self.token_path.exists():
            return None
        try:
            return Credentials.from_authorized_user_file(str(self.token_path))
        except Exception:
            return None

    def _save_token(self, creds: Credentials) -> None:
        """Save credentials to token file with restrictive permissions where supported."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.config_dir, 0o700)
        except OSError:
            pass

        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            pass

    def _has_required_scopes(self, creds: Credentials | None) -> bool:
        """Return True if cached credentials cover every scope in the active profile."""
        if creds is None:
            return False
        granted = set(creds.scopes or [])
        return set(self.scopes).issubset(granted)

    def _invalidate_token_file(self) -> None:
        """Remove stale token so a fresh OAuth flow can overwrite it."""
        try:
            self.token_path.unlink(missing_ok=True)
        except OSError:
            pass

    def authenticate(self) -> Credentials:
        """Get valid credentials, refreshing or running OAuth flow if needed."""
        creds = self._load_token()

        if creds and creds.valid and self._has_required_scopes(creds):
            self._credentials = creds
            return creds

        if creds and creds.expired and creds.refresh_token and self._has_required_scopes(creds):
            try:
                creds.refresh(Request())
                self._save_token(creds)
                self._credentials = creds
                return creds
            except Exception:
                pass

        if creds is not None and not self._has_required_scopes(creds):
            self._invalidate_token_file()

        if not self.client_secret_path.exists():
            raise AuthError(
                f"client_secret.json not found at {self.client_secret_path}. "
                "Download OAuth Desktop App credentials from Google Cloud Console "
                "and place them at this path, or set YOUTUBE_MCP_CLIENT_SECRET."
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secret_path), self.scopes
            )
            creds = flow.run_local_server(port=0)
            self._save_token(creds)
            self._credentials = creds
            return creds
        except Exception as e:
            raise AuthError(f"OAuth flow failed: {e}") from e

    @property
    def credentials(self) -> Credentials:
        """Get current credentials, authenticating if needed."""
        if self._credentials and self._credentials.valid and self._has_required_scopes(
            self._credentials
        ):
            return self._credentials
        return self.authenticate()

    def build_youtube_service(self):
        """Build a YouTube Data API v3 service client."""
        return build("youtube", "v3", credentials=self.credentials)

    def build_youtube_analytics_service(self):
        """Build a YouTube Analytics API service client."""
        return build("youtubeAnalytics", "v2", credentials=self.credentials)

    def build_youtube_reporting_service(self):
        """Build a YouTube Reporting API service client."""
        return build("youtubereporting", "v1", credentials=self.credentials)

    def build_public_youtube_service(self):
        """Build a YouTube Data API client using API key only (public data)."""
        if not self.api_key:
            raise AuthError(
                "No API key available. Set YOUTUBE_API_KEY env var for public-only access."
            )
        return build("youtube", "v3", developerKey=self.api_key)

    def status(self) -> dict:
        """Return current auth status without exposing secret tokens."""
        creds = self._load_token()
        if creds and creds.valid:
            return {
                "authenticated": True,
                "scope_profile": self.scope_profile,
                "has_required_scopes": self._has_required_scopes(creds),
                "scopes": creds.scopes or [],
                "token_path": str(self.token_path),
                "expired": False,
            }
        if creds and creds.expired:
            return {
                "authenticated": False,
                "scope_profile": self.scope_profile,
                "expired": True,
                "has_refresh_token": bool(creds.refresh_token),
                "token_path": str(self.token_path),
            }
        return {
            "authenticated": False,
            "scope_profile": self.scope_profile,
            "token_exists": self.token_path.exists(),
            "client_secret_exists": self.client_secret_path.exists(),
            "client_secret_path": str(self.client_secret_path),
        }
