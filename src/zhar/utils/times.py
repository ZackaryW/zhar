"""Datetime helpers: UTC now, ISO-8601 parse/format, staleness and expiry checks."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


def parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 string (Z or +00:00 offset) into a UTC-aware datetime.

    Raises ValueError for unrecognisable input.
    """
    # Normalise the trailing 'Z' that Python's fromisoformat doesn't accept
    # prior to 3.11.
    normalised = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalised)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot parse datetime: {value!r}") from exc
    # Ensure UTC
    return dt.astimezone(timezone.utc)


def format_dt(dt: datetime) -> str:
    """Format a datetime as a compact ISO-8601 UTC string ending in 'Z',
    with no microsecond component."""
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_expired(expires_at: datetime | None) -> bool:
    """Return True if *expires_at* is set and is in the past."""
    if expires_at is None:
        return False
    return utcnow() >= expires_at


def is_stale(updated_at: datetime, threshold_days: int = 30) -> bool:
    """Return True if *updated_at* is older than *threshold_days*."""
    from datetime import timedelta
    return utcnow() - updated_at > timedelta(days=threshold_days)
