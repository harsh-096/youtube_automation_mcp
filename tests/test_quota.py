"""Tests for persistent quota tracker."""

import json

import pytest

from youtube_upload_mcp.utils.quota import QuotaExhaustedError, QuotaTracker


def test_quota_persists_across_restarts(tmp_path):
    quota_file = tmp_path / "quota.json"

    tracker1 = QuotaTracker(daily_limit=10_000, state_path=quota_file)
    tracker1.consume("video_insert")
    tracker1.consume("list", count=5)
    assert tracker1.used == 1605
    assert quota_file.exists()

    tracker2 = QuotaTracker(daily_limit=10_000, state_path=quota_file)
    assert tracker2.used == 1605
    assert tracker2.remaining == 8395


def test_quota_hard_fails_when_exhausted(tmp_path):
    quota_file = tmp_path / "quota.json"
    tracker = QuotaTracker(daily_limit=1650, state_path=quota_file)
    tracker.consume("video_insert")

    with pytest.raises(QuotaExhaustedError):
        tracker.consume("search")
    assert tracker.used == 1600


def test_quota_resets_when_date_changes(tmp_path):
    quota_file = tmp_path / "quota.json"
    quota_file.write_text(json.dumps({"date": "1999-01-01", "used": 9999}), encoding="utf-8")

    tracker = QuotaTracker(daily_limit=10_000, state_path=quota_file)
    assert tracker.used == 0
    assert tracker.remaining == 10_000
