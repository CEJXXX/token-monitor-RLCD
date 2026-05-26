"""Current weather from open-meteo (free, no API key).

Defaults to Shenzhen. Cached in-process so we don't hit the API on every
background refresh.
"""
from __future__ import annotations

import os
import time
import json
import urllib.request

from schema import Weather

LAT = float(os.environ.get("RLCD_WEATHER_LAT", "22.5431"))
LON = float(os.environ.get("RLCD_WEATHER_LON", "114.0579"))
CITY = os.environ.get("RLCD_WEATHER_CITY", "SHENZHEN")
TTL = int(os.environ.get("RLCD_WEATHER_TTL", "600"))  # 10 min

# WMO weather code -> (short label, icon key)
_WMO = {
    0: ("Clear", "clear"), 1: ("Clear", "clear"), 2: ("Partly", "partly"),
    3: ("Cloudy", "cloud"), 45: ("Fog", "fog"), 48: ("Fog", "fog"),
    51: ("Drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Rain", "rain"),
    56: ("Drizzle", "rain"), 57: ("Drizzle", "rain"),
    61: ("Rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy", "rain"),
    66: ("Rain", "rain"), 67: ("Rain", "rain"),
    71: ("Snow", "snow"), 73: ("Snow", "snow"), 75: ("Snow", "snow"),
    77: ("Snow", "snow"), 80: ("Showers", "rain"), 81: ("Showers", "rain"),
    82: ("Storm", "rain"), 85: ("Snow", "snow"), 86: ("Snow", "snow"),
    95: ("Storm", "rain"), 96: ("Storm", "rain"), 99: ("Storm", "rain"),
}

_cache: dict[str, object] = {"w": None, "ts": 0.0}


def fetch_weather() -> Weather | None:
    now = time.time()
    if _cache["w"] is not None and now - float(_cache["ts"]) < TTL:
        return _cache["w"]  # type: ignore
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,weather_code&timezone=Asia/Shanghai"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        cur = d["current"]
        code = int(cur["weather_code"])
        label, icon = _WMO.get(code, ("Cloudy", "partly"))
        w = Weather(
            temp_c=round(float(cur["temperature_2m"]), 1),
            code=code,
            condition=label,
            icon=icon,
            city=CITY,
        )
        _cache.update(w=w, ts=now)
        return w
    except Exception:
        return _cache["w"]  # type: ignore  # last good, or None
