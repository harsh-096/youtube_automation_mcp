"""Response formatting utilities for LLM consumption."""

import re

_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def _parse_duration_parts(iso_duration: str) -> tuple[int, int, int] | None:
    if not iso_duration:
        return None
    match = _DURATION_RE.match(iso_duration)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours, minutes, seconds


def format_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT1H2M3S) to human-readable format."""
    parsed = _parse_duration_parts(iso_duration)
    if parsed is None:
        return "unknown"
    hours, minutes, seconds = parsed
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def format_count(n: int | str) -> str:
    """Format large numbers with K/M/B suffixes."""
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def is_likely_short(iso_duration: str) -> bool:
    """Heuristic: videos <= 60 seconds are likely Shorts."""
    parsed = _parse_duration_parts(iso_duration)
    if parsed is None:
        return False
    hours, minutes, seconds = parsed
    if hours > 0:
        return False
    return (minutes * 60 + seconds) <= 60


def format_video_summary(video: dict) -> dict:
    """Extract and format key fields from a YouTube Data API video resource."""
    snippet = video.get("snippet", {})
    stats = video.get("statistics", {})
    content = video.get("contentDetails", {})
    duration_iso = content.get("duration", "")

    return {
        "id": video.get("id"),
        "title": snippet.get("title"),
        "channel": snippet.get("channelTitle"),
        "published_at": snippet.get("publishedAt"),
        "duration": format_duration(duration_iso),
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
        "description": snippet.get("description", "")[:500],
        "tags": snippet.get("tags", []),
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        "is_short": is_likely_short(duration_iso),
    }
