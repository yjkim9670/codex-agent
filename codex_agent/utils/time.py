"""Time helpers with KST normalization."""

import math
from datetime import datetime

from ..config import KST


def _parse_epoch_timestamp(value):
    numeric = None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            return None
    else:
        return None

    if not math.isfinite(numeric):
        return None
    if numeric <= 0:
        return None

    # Accept either epoch seconds or epoch milliseconds.
    if abs(numeric) >= 1_000_000_000_000:
        numeric /= 1000.0
    try:
        return datetime.fromtimestamp(numeric, tz=KST)
    except Exception:
        return None


def parse_timestamp(value):
    """Parse timestamps into KST-aware datetime objects."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        else:
            epoch_dt = _parse_epoch_timestamp(value)
            if epoch_dt is not None:
                dt = epoch_dt
            elif not isinstance(value, str):
                return None
            else:
                text = value.strip()
                if not text:
                    return None
                if text.endswith('Z'):
                    text = f'{text[:-1]}+00:00'
                if 'T' in text:
                    dt = datetime.fromisoformat(text)
                else:
                    dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def normalize_timestamp(value):
    if value is None:
        return datetime.now(KST).isoformat(timespec='seconds')
    if isinstance(value, str) and not value.strip():
        return datetime.now(KST).isoformat(timespec='seconds')
    parsed = parse_timestamp(value)
    if parsed is None:
        return datetime.now(KST).isoformat(timespec='seconds')
    return parsed.astimezone(KST).isoformat(timespec='seconds')
