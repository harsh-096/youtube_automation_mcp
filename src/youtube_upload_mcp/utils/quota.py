"""Persistent, thread-safe client-side YouTube API quota tracker.

YouTube Data API v3 provides a default daily quota of 10,000 units that
resets at midnight Pacific Time (America/Los_Angeles).
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class QuotaExhaustedError(Exception):
    """Raised when a YouTube Data API operation would exceed the daily quota."""

    def __init__(self, used: int, requested: int, limit: int):
        self.used = used
        self.requested = requested
        self.limit = limit
        super().__init__(
            f"YouTube API quota exhausted: {used}/{limit} units used today "
            f"(requested {requested}). Resets at midnight Pacific Time."
        )


QUOTA_COSTS = {
    "list": 1,
    "insert": 50,
    "update": 50,
    "delete": 50,
    "search": 100,
    "video_insert": 1600,
    "caption_insert": 400,
    "caption_update": 450,
    "thumbnail_set": 50,
}


def _pacific_today() -> str:
    """Return current date in America/Los_Angeles (falls back to UTC if tzdata missing)."""
    try:
        tz = ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    return datetime.now(tz).date().isoformat()


class QuotaTracker:
    """Tracks daily YouTube Data API v3 quota usage with optional disk persistence."""

    def __init__(
        self,
        daily_limit: int = 10_000,
        state_path: str | Path | None = None,
    ):
        self.daily_limit = daily_limit
        self.state_path = Path(state_path) if state_path else None
        self._lock = threading.Lock()
        self._used = 0
        self._date = _pacific_today()
        self._load()

    def _load(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if data.get("date") == self._date and isinstance(data.get("used"), int):
                self._used = max(0, data["used"])
        except Exception:
            # Corrupted quota file should not crash the server
            self._used = 0

    def _save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"date": self._date, "used": self._used}, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.state_path.parent),
            prefix=".quota-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, self.state_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    def _reset_if_new_day(self) -> None:
        today = _pacific_today()
        if today != self._date:
            self._used = 0
            self._date = today
            self._save()

    def consume(self, operation: str, count: int = 1) -> int:
        """Consume quota units for an operation. Returns the cost consumed."""
        cost = QUOTA_COSTS.get(operation, 1) * max(1, count)
        with self._lock:
            self._reset_if_new_day()
            if self._used + cost > self.daily_limit:
                raise QuotaExhaustedError(self._used, cost, self.daily_limit)
            self._used += cost
            self._save()
            return cost

    @property
    def used(self) -> int:
        with self._lock:
            self._reset_if_new_day()
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            self._reset_if_new_day()
            return max(0, self.daily_limit - self._used)

    def status(self) -> dict:
        with self._lock:
            self._reset_if_new_day()
            return {
                "used": self._used,
                "remaining": max(0, self.daily_limit - self._used),
                "limit": self.daily_limit,
                "date_pt": self._date,
                "persisted": bool(self.state_path),
            }
