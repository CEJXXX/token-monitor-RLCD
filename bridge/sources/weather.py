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


def _condition(code: int, cloud_cover: float, precip: float) -> tuple[str, str]:
    """Refine WMO code with cloud_cover (%) and precipitation (mm) for better accuracy."""
    # Precipitation beats cloud cover
    if precip >= 0.3:
        if code in (71, 73, 75, 77, 85, 86):
            return "Snow", "snow"
        if precip >= 2.0 or code in (65, 82):
            return "Heavy", "rain"
        return "Rain", "rain"
    if precip > 0:
        return "Drizzle", "rain"
    # No precip: use cloud cover for clearer sky states
    if code in (45, 48):
        return "Fog", "fog"
    if code in (95, 96, 99):
        return "Storm", "rain"
    if cloud_cover < 20:
        return "Clear", "clear"
    if cloud_cover < 50:
        return "Partly", "partly"
    if cloud_cover < 85:
        return "Cloudy", "cloud"
    return "Overcast", "cloud"


def fetch_weather() -> Weather | None:
    now = time.time()
    if _cache["w"] is not None and now - float(_cache["ts"]) < TTL:
        return _cache["w"]  # type: ignore
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,weather_code,cloud_cover,precipitation&timezone=Asia/Shanghai"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        cur = d["current"]
        code = int(cur["weather_code"])
        cloud = float(cur.get("cloud_cover") or 0)
        precip = float(cur.get("precipitation") or 0)
        label, icon = _condition(code, cloud, precip)
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
