"""Source posting dates, independent of fetch/index time."""
from datetime import date, datetime, timedelta, timezone
import math
import re


def posted_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value <= 0:
            return None
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value).strip()
    if text.lower() in {'', 'nan', 'nat', 'recently', 'unknown', 'none'}:
        return None
    match = re.fullmatch(r'(\d+)\s*(hour|day|week|month)s?\s+ago', text.lower())
    if match:
        return datetime.now(timezone.utc) - timedelta(hours=int(match[1]) * {'hour': 1, 'day': 24, 'week': 168, 'month': 720}[match[2]])
    try:
        return posted_datetime(datetime.fromisoformat(text.replace('Z', '+00:00')))
    except ValueError:
        return None


def posted_iso(value):
    parsed = posted_datetime(value)
    return parsed.isoformat().replace('+00:00', 'Z') if parsed else ''
