"""Business-hours arithmetic for SLAs.

`dealers.business_hours` format (all keys optional; missing dict -> DEFAULT):
    {"mon": ["09:00", "19:00"], ..., "sat": ["09:00", "19:00"], "sun": null}
Times are local to `tz` (default Asia/Kolkata). A day with null / missing key is closed.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT: dict[str, list[str] | None] = {
    **{d: ["09:00", "19:00"] for d in DAYS[:6]},
    "sun": None,
}
IST = ZoneInfo("Asia/Kolkata")


def _parse(schedule: dict | None) -> dict[int, tuple[time, time] | None]:
    src = schedule if schedule else DEFAULT
    out: dict[int, tuple[time, time] | None] = {}
    for i, day in enumerate(DAYS):
        span = src.get(day)
        if not span or len(span) != 2:
            out[i] = None
            continue
        try:
            start, end = time.fromisoformat(span[0]), time.fromisoformat(span[1])
        except ValueError:
            out[i] = None
            continue
        out[i] = (start, end) if end > start else None
    if all(v is None for v in out.values()):
        return _parse(DEFAULT)  # a fully closed / broken schedule must not stall SLAs forever
    return out


def add_business_hours(
    start: datetime, hours: float, schedule: dict | None = None, tz: ZoneInfo = IST
) -> datetime:
    """`start` + `hours` of open time. Returns an aware datetime in `tz`."""
    spans = _parse(schedule)
    remaining = timedelta(hours=hours)
    cur = start.astimezone(tz)
    for _ in range(366):  # bounded: at most a year of days
        span = spans[cur.weekday()]
        if span is not None:
            open_at = cur.replace(hour=span[0].hour, minute=span[0].minute, second=0, microsecond=0)
            close_at = cur.replace(
                hour=span[1].hour, minute=span[1].minute, second=0, microsecond=0
            )
            if cur < open_at:
                cur = open_at
            if cur < close_at:
                available = close_at - cur
                if remaining <= available:
                    return cur + remaining
                remaining -= available
        nxt = (cur + timedelta(days=1)).date()
        cur = datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz)
    raise RuntimeError("business hours never open")
