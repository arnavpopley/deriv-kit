from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Union

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

OPEN_IST = timedelta(hours=9, minutes=15)
CLOSE_IST = timedelta(hours=15, minutes=30)
SESSION_HOURS = 6.25
VOL_YEAR_TRADING_DAYS = 252.0
RATE_YEAR_DAYS = 365.25

_HOLIDAYS_2026 = {
    date(2026, 1, 15),
    date(2026, 1, 26),
    date(2026, 3, 3),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 5, 28),
    date(2026, 6, 26),
    date(2026, 9, 14),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 10),
    date(2026, 11, 24),
    date(2026, 12, 25),
}
_MUHURAT = date(2026, 11, 8)


def parse_iso_date(iso_date: str) -> date:
    if len(iso_date) < 10:
        raise ValueError("date must be YYYY-MM-DD")
    y = int(iso_date[0:4])
    m = int(iso_date[5:7])
    d = int(iso_date[8:10])
    try:
        return date(y, m, d)
    except ValueError as exc:
        raise ValueError(f"invalid calendar date: {iso_date}") from exc


def is_trading_day(ymd: Union[date, str]) -> bool:
    if isinstance(ymd, str):
        ymd = parse_iso_date(ymd)
    if ymd == _MUHURAT:
        return True
    if ymd.weekday() >= 5:
        return False
    return ymd not in _HOLIDAYS_2026


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _ist_date(utc: datetime) -> date:
    return _as_utc(utc).astimezone(IST).date()


def _ist_tod(utc: datetime) -> timedelta:
    ist = _as_utc(utc).astimezone(IST)
    return timedelta(hours=ist.hour, minutes=ist.minute, seconds=ist.second, microseconds=ist.microsecond)


def _ist_on(ymd: date, tod: timedelta) -> datetime:
    local = datetime(ymd.year, ymd.month, ymd.day, tzinfo=IST) + tod
    return local.astimezone(UTC).replace(microsecond=0)


def expiry_close(expiry_iso_date: str) -> datetime:
    return _ist_on(parse_iso_date(expiry_iso_date), CLOSE_IST)


def snap_as_of(now: datetime) -> datetime:
    utc = _as_utc(now).replace(microsecond=0)
    ymd = _ist_date(utc)
    tod = _ist_tod(utc)
    if is_trading_day(ymd):
        if tod >= CLOSE_IST:
            return _ist_on(ymd, CLOSE_IST)
        if tod >= OPEN_IST:
            return utc
    ymd = ymd - timedelta(days=1)
    while not is_trading_day(ymd):
        ymd = ymd - timedelta(days=1)
    return _ist_on(ymd, CLOSE_IST)


def format_ist(utc: datetime) -> str:
    ist = _as_utc(utc).astimezone(IST)
    return f"{ist:%Y-%m-%d %H:%M} IST"


def _trading_days_remaining(as_of: datetime, expiry: datetime) -> float:
    if as_of >= expiry:
        return 1.0 / (VOL_YEAR_TRADING_DAYS * 24.0)
    remaining = 0.0
    as_of_ymd = _ist_date(as_of)
    if is_trading_day(as_of_ymd):
        close = _ist_on(as_of_ymd, CLOSE_IST)
        if as_of < close:
            open_t = _ist_on(as_of_ymd, OPEN_IST)
            start = open_t if as_of < open_t else as_of
            hours = (close - start).total_seconds() / 3600.0
            remaining += min(max(hours / SESSION_HOURS, 0.0), 1.0)
    d = as_of_ymd + timedelta(days=1)
    expiry_ymd = _ist_date(expiry)
    while d <= expiry_ymd:
        if is_trading_day(d):
            remaining += 1.0
        d += timedelta(days=1)
    return max(remaining, 1.0 / (VOL_YEAR_TRADING_DAYS * 24.0))


@dataclass
class Clock:
    as_of: datetime | None = None
    expiry: datetime | None = None
    as_of_ist: str = ""
    expiry_ist: str = ""
    time_rate: float = 0.0
    time_vol: float = 0.0
    trading_days: float = 0.0
    snapped_to_close: bool = False


def clock_to_expiry(expiry_iso_date: str, as_of: datetime | None = None) -> Clock:
    if as_of is None:
        as_of = datetime.now(tz=UTC)
    raw = _as_utc(as_of).replace(microsecond=0)
    c = Clock()
    c.as_of = snap_as_of(as_of)
    c.snapped_to_close = c.as_of != raw
    c.expiry = expiry_close(expiry_iso_date)
    c.as_of_ist = format_ist(c.as_of)
    c.expiry_ist = format_ist(c.expiry)
    secs = (c.expiry - c.as_of).total_seconds()
    c.time_rate = max(secs / (RATE_YEAR_DAYS * 24.0 * 3600.0), 1.0 / (RATE_YEAR_DAYS * 24.0))
    c.trading_days = _trading_days_remaining(c.as_of, c.expiry)
    c.time_vol = c.trading_days / VOL_YEAR_TRADING_DAYS
    return c
