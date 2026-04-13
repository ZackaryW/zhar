"""TDD: zhar.utils.times — datetime helpers and staleness checks."""
from datetime import datetime, timedelta, timezone
import pytest
from zhar.utils.times import utcnow, is_expired, is_stale, parse_dt, format_dt


class TestUtcnow:
    def test_returns_datetime(self):
        assert isinstance(utcnow(), datetime)

    def test_is_timezone_aware(self):
        dt = utcnow()
        assert dt.tzinfo is not None

    def test_is_utc(self):
        dt = utcnow()
        assert dt.utcoffset().total_seconds() == 0


class TestParseDt:
    def test_parses_iso8601_utc(self):
        dt = parse_dt("2025-04-07T10:22:00Z")
        assert dt.year == 2025
        assert dt.month == 4
        assert dt.day == 7

    def test_result_is_timezone_aware(self):
        dt = parse_dt("2025-04-07T10:22:00Z")
        assert dt.tzinfo is not None

    def test_parses_with_offset(self):
        dt = parse_dt("2025-04-07T10:22:00+00:00")
        assert dt.hour == 10

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError):
            parse_dt("not-a-date")


class TestFormatDt:
    def test_round_trip(self):
        original = "2025-04-07T10:22:00Z"
        dt = parse_dt(original)
        formatted = format_dt(dt)
        assert parse_dt(formatted) == dt

    def test_output_ends_with_z(self):
        dt = datetime(2025, 4, 7, 10, 22, 0, tzinfo=timezone.utc)
        assert format_dt(dt).endswith("Z")

    def test_output_has_no_microseconds(self):
        dt = datetime(2025, 4, 7, 10, 22, 0, 999999, tzinfo=timezone.utc)
        assert "." not in format_dt(dt)


class TestIsExpired:
    def test_none_expires_at_never_expires(self):
        assert is_expired(expires_at=None) is False

    def test_past_datetime_is_expired(self):
        past = utcnow() - timedelta(seconds=1)
        assert is_expired(expires_at=past) is True

    def test_future_datetime_is_not_expired(self):
        future = utcnow() + timedelta(hours=1)
        assert is_expired(expires_at=future) is False


class TestIsStale:
    def test_recently_updated_is_not_stale(self):
        recent = utcnow() - timedelta(days=1)
        assert is_stale(updated_at=recent, threshold_days=7) is False

    def test_old_node_is_stale(self):
        old = utcnow() - timedelta(days=30)
        assert is_stale(updated_at=old, threshold_days=7) is True

    def test_exact_threshold_is_stale(self):
        exact = utcnow() - timedelta(days=7, seconds=1)
        assert is_stale(updated_at=exact, threshold_days=7) is True
