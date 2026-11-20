import datetime as _dt
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


def _split_parts(dt):
    """TBC-style {date, time, datetime, timestamp, iso} dict."""
    return {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(dt.timestamp()),
        "iso": dt.isoformat(),
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
    }


class DateAndTimeLib:
    def now(self, timezone_or_fmt=None):
        """TBC: returns dict with date/time when given a timezone name.
        If given a strftime format string (no '/'), returns formatted string.
        """
        tz_name = timezone_or_fmt
        # Timezone path: "Asia/Dhaka", "UTC", ...
        if tz_name and (
            (isinstance(tz_name, str) and "/" in tz_name)
            or str(tz_name).upper() in ("UTC", "GMT")
        ):
            try:
                if ZoneInfo:
                    dt = _dt.datetime.now(ZoneInfo(str(tz_name)))
                else:
                    dt = _dt.datetime.utcnow()
                return _split_parts(dt)
            except Exception:
                pass
        # Explicit format string
        if tz_name and isinstance(tz_name, str) and "%" in tz_name:
            return _dt.datetime.utcnow().strftime(tz_name)
        # Default: TBC dict (UTC)
        return _split_parts(_dt.datetime.utcnow())

    def utcnow(self):
        from backend.sandbox.tbs_compat import hybrid
        n = _dt.datetime.utcnow()
        return hybrid(n.strftime("%Y-%m-%d %H:%M:%S"), _split_parts(n))

    def date_now(self):
        # TBC bots often do: today = DateAndTime.date_now(); today['date']
        return _split_parts(_dt.datetime.utcnow())

    def time(self):
        return int(_dt.datetime.utcnow().timestamp())

    def today(self, fmt="%Y-%m-%d"):
        return _dt.date.today().strftime(fmt)

    def add_seconds(self, seconds, base=None):
        base_dt = _dt.datetime.utcnow() if base is None else _dt.datetime.fromisoformat(str(base))
        return (base_dt + _dt.timedelta(seconds=seconds)).isoformat()

    def add_days(self, days, base=None):
        base_dt = _dt.datetime.utcnow() if base is None else _dt.datetime.fromisoformat(str(base))
        return (base_dt + _dt.timedelta(days=days)).isoformat()

    def timestamp(self):
        return int(_dt.datetime.utcnow().timestamp())

    def parse(self, value, fmt="%Y-%m-%d %H:%M:%S"):
        return _dt.datetime.strptime(value, fmt).isoformat()
