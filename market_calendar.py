#!/usr/bin/env python3
"""NYSE regular holiday and US Eastern session helpers (no third-party deps)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day):
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _easter_sunday(year):
    """Gregorian Easter date (Meeus/Jones/Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def holidays(year):
    """NYSE's recurring full-day holidays for a calendar year."""
    days = set()
    for y in (year - 1, year, year + 1):
        days.add(_observed(date(y, 1, 1)))  # captures Dec 31 observance
        days.add(_nth_weekday(y, 1, 0, 3))  # Martin Luther King Jr. Day
        days.add(_nth_weekday(y, 2, 0, 3))  # Washington's Birthday
        days.add(_easter_sunday(y) - timedelta(days=2))  # Good Friday
        days.add(_last_weekday(y, 5, 0))  # Memorial Day
        if y >= 2022:
            days.add(_observed(date(y, 6, 19)))  # Juneteenth
        days.add(_observed(date(y, 7, 4)))
        days.add(_nth_weekday(y, 9, 0, 1))  # Labor Day
        days.add(_nth_weekday(y, 11, 3, 4))  # Thanksgiving
        days.add(_observed(date(y, 12, 25)))
    return {day for day in days if day.year == year}


def early_closes(year):
    """Common recurring 13:00 ET NYSE closes (not emergency closures)."""
    days = set()
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    days.add(thanksgiving + timedelta(days=1))
    july_3 = date(year, 7, 3)
    if july_3.weekday() < 5 and july_3 not in holidays(year):
        days.add(july_3)
    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < 5 and christmas_eve not in holidays(year):
        days.add(christmas_eve)
    return {day for day in days if day.weekday() < 5 and day not in holidays(year)}


def is_trading_day(day):
    return day.weekday() < 5 and day not in holidays(day.year)


def _next_trading_day(day):
    candidate = day + timedelta(days=1)
    for _ in range(15):
        if is_trading_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    raise RuntimeError("could not find a trading day")


def market_status(now=None):
    """Return session text and countdown to the next real session boundary."""
    now = now or datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)
    day = now.date()
    minute = now.hour * 60 + now.minute
    is_holiday = day in holidays(day.year)
    trading_day = is_trading_day(day)
    early_close = day in early_closes(day.year)
    regular_close = 13 * 60 if early_close else 16 * 60

    def at(hour, minute=0):
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if not trading_day:
        if is_holiday:
            name, cls = "Closed 休市 · NYSE假日", "closed"
        else:
            name, cls = "Closed 休市 · 周末", "closed"
        next_transition = datetime.combine(_next_trading_day(day), time(4, 0), tzinfo=ET)
        transition_label = "下次盘前"
    elif minute < 4 * 60:
        name, cls = "Closed 休市", "closed"
        next_transition, transition_label = at(4), "盘前开始"
    elif minute < 9 * 60 + 30:
        name, cls = "Pre-Market 盘前", "pre"
        next_transition, transition_label = at(9, 30), "常规开盘"
    elif minute < regular_close:
        name = "Regular 盘中" + (" · 提前收市" if early_close else "")
        cls = "open"
        next_transition = at(regular_close // 60, regular_close % 60)
        transition_label = "提前收市" if early_close else "收盘"
    elif minute < 20 * 60:
        name = "After-Hours 盘后" + (" · 提前收市日" if early_close else "")
        cls = "after"
        next_transition, transition_label = at(20), "盘后结束"
    else:
        name, cls = "Closed 休市", "closed"
        next_day = _next_trading_day(day)
        next_transition = datetime.combine(next_day, time(4, 0), tzinfo=ET)
        transition_label = "下次盘前"

    # Round up to a whole minute and clamp defensively: stale clock ticks can
    # never expose a negative countdown, even at a session boundary.
    seconds_left = max(0, int((next_transition - now).total_seconds()))
    remaining = (seconds_left + 59) // 60
    countdown = "· %s %dh %02dm" % (transition_label, remaining // 60, remaining % 60)
    return {"label": name, "class": cls, "countdown": countdown,
            "holiday": is_holiday, "early_close": early_close,
            "as_of": now.isoformat(), "next_transition": next_transition.isoformat()}
