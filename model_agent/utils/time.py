"""Time helpers with KST normalization."""

from datetime import datetime

from ..config import KST


def parse_timestamp(value):
    """Parse timestamps into KST-aware datetime objects."""
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        elif 'T' in value:
            dt = datetime.fromisoformat(value)
        else:
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def normalize_timestamp(value):
    if not value:
        return datetime.now(KST).isoformat(timespec='seconds')
    try:
        if isinstance(value, datetime):
            dt = value
        elif 'T' in value:
            dt = datetime.fromisoformat(value)
        else:
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).isoformat(timespec='seconds')
    except Exception:
        return datetime.now(KST).isoformat(timespec='seconds')
