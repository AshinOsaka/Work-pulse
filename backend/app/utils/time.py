from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware current UTC time. Never use naive datetimes."""
    return datetime.now(UTC)
