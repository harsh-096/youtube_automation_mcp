"""Input and security validators for YouTube MCP tools."""

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")
_VALID_PRIVACY = frozenset({"private", "public", "unlisted"})
_ALLOWED_REPORTING_HOSTS = frozenset({"youtubereporting.googleapis.com"})


class ValidationError(ValueError):
    """Raised when tool input fails safety or format validation."""


def validate_youtube_id(value: str, label: str = "id") -> str:
    """Validate a YouTube resource ID to prevent filter/parameter injection."""
    cleaned = (value or "").strip()
    if not cleaned or not _ID_PATTERN.match(cleaned):
        raise ValidationError(
            f"Invalid {label}: expected 1-128 alphanumeric, '_', '-', or '.' characters."
        )
    return cleaned


def validate_privacy_status(privacy_status: str) -> str:
    """Validate YouTube video or playlist privacy status."""
    if privacy_status not in _VALID_PRIVACY:
        allowed = ", ".join(sorted(_VALID_PRIVACY))
        raise ValidationError(
            f"Invalid privacy_status {privacy_status!r}. Must be one of: {allowed}."
        )
    return privacy_status


def validate_media_path(
    file_path: str,
    allowed_dir: str | Path | None = None,
    max_bytes: int | None = None,
) -> Path:
    """Resolve and validate a local media file path for upload.

    Args:
        file_path: Path provided by the caller.
        allowed_dir: Optional base directory allowlist. When set, the resolved
            file must reside inside this directory.
        max_bytes: Optional maximum file size in bytes (e.g., 2 MB for thumbnails).
    """
    if not file_path or not file_path.strip():
        raise ValidationError("file_path must not be empty.")

    resolved = Path(file_path).expanduser().resolve()

    if allowed_dir:
        base = Path(allowed_dir).expanduser().resolve()
        if not resolved.is_relative_to(base):
            raise ValidationError(
                f"Access denied: {resolved} is outside YOUTUBE_MCP_ALLOWED_MEDIA_DIR ({base})."
            )

    if not resolved.exists():
        raise ValidationError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise ValidationError(f"Path is not a regular file: {resolved}")

    if max_bytes is not None:
        size = resolved.stat().st_size
        if size > max_bytes:
            raise ValidationError(
                f"File size ({size} bytes) exceeds maximum allowed ({max_bytes} bytes)."
            )

    return resolved


def validate_googleapis_download_url(download_url: str) -> str:
    """Ensure reporting download URLs only point to trusted HTTPS Google API hosts.

    Prevents SSRF and OAuth Bearer token leakage to arbitrary domains.
    """
    if not download_url or not download_url.strip():
        raise ValidationError("download_url must not be empty.")

    parsed = urlparse(download_url.strip())
    if parsed.scheme.lower() != "https":
        raise ValidationError("download_url must use https://.")
    if parsed.username or parsed.password:
        raise ValidationError("download_url must not contain embedded credentials.")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValidationError("download_url is missing a valid hostname.")

    # Reject raw IP addresses even if somehow crafted
    try:
        ipaddress.ip_address(host)
        raise ValidationError("download_url must use a Google API domain, not an IP address.")
    except ValueError:
        pass

    is_allowed = host in _ALLOWED_REPORTING_HOSTS or host.endswith(".googleapis.com")
    if not is_allowed:
        raise ValidationError(
            f"Blocked untrusted download host {host!r}. "
            "Only *.googleapis.com HTTPS URLs are permitted."
        )

    return download_url.strip()
