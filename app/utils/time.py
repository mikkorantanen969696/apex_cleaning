from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings


def parse_local_datetime(text: str) -> datetime | None:
    text = text.strip()
    if not text:
        return None
    patterns = ["%d.%m.%Y %H:%M", "%d.%m.%y %H:%M"]
    for pattern in patterns:
        try:
            local_dt = datetime.strptime(text, pattern).replace(tzinfo=ZoneInfo(settings.business_tz))
            return local_dt.astimezone(ZoneInfo("UTC"))
        except Exception:
            continue
    return None


def format_utc_as_local(dt: datetime | None) -> str:
    if not dt:
        return "—"
    try:
        local = dt.astimezone(ZoneInfo(settings.business_tz))
        return local.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt.strftime("%d.%m.%Y %H:%M")

