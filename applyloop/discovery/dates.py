from datetime import UTC, datetime


def parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string to a timezone-aware UTC datetime (assume UTC if naive)."""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
