from datetime import datetime, timezone


def format_date(dt_str: str) -> str:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))  # handle trailing Z
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # assume already UTC if naive
    return dt.astimezone(timezone.utc).isoformat()
