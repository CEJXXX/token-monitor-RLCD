"""Current weather — Caiyun (彩云天气) primary, open-meteo fallback.

Set CAIYUN_API_KEY to use Caiyun; otherwise falls back to open-meteo (no key needed).
Caiyun URL format: /v2.6/{token}/{lon},{lat}/realtime  (note: lon first)
"""
from __future__ import annotations

import os
import time
import json
import urllib.request

from schema import Weather

CAIYUN_KEY = os.environ.get("CAIYUN_API_KEY") or None
LAT  = float(os.environ.get("RLCD_WEATHER_LAT",  "22.5431"))
LON  = float(os.environ.get("RLCD_WEATHER_LON",  "114.0579"))
CITY = os.environ.get("RLCD_WEATHER_CITY", "SHENZHEN")
# Caiyun has a finite total quota — default once/day; open-meteo is unlimited — default 10 min
_DEFAULT_TTL = 86400 if CAIYUN_KEY else 600
TTL = int(os.environ.get("RLCD_WEATHER_TTL", str(_DEFAULT_TTL)))

# Caiyun skycon -> (short label, icon key)
_SKYCON: dict[str, tuple[str, str]] = {
    "CLEAR_DAY":           ("Clear",  "clear"),
    "CLEAR_NIGHT":         ("Clear",  "clear"),
    "PARTLY_CLOUDY_DAY":   ("Partly", "partly"),
    "PARTLY_CLOUDY_NIGHT": ("Partly", "partly"),
    "CLOUDY":              ("Cloudy", "cloud"),
    "LIGHT_RAIN":          ("Rain",   "rain"),
    "MODERATE_RAIN":       ("Rain",   "rain"),
    "HEAVY_RAIN":          ("Heavy",  "rain"),
    "STORM_RAIN":          ("Storm",  "rain"),
    "FOG":                 ("Fog",    "fog"),
    "LIGHT_SNOW":          ("Snow",   "snow"),
    "MODERATE_SNOW":       ("Snow",   "snow"),
    "HEAVY_SNOW":          ("Snow",   "snow"),
    "STORM_SNOW":          ("Snow",   "snow"),
    "DUST":                ("Haze",   "fog"),
    "SAND":                ("Haze",   "fog"),
    "WIND":                ("Windy",  "cloud"),
}

# open-meteo WMO code -> (label, icon) — used only when CAIYUN_API_KEY is unset
_WMO: dict[int, tuple[str, str]] = {
    0: ("Clear", "clear"), 1: ("Clear", "clear"), 2: ("Partly", "partly"),
    3: ("Cloudy", "cloud"), 45: ("Fog", "fog"), 48: ("Fog", "fog"),
    51: ("Drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Rain", "rain"),
    61: ("Rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy", "rain"),
    71: ("Snow", "snow"), 73: ("Snow", "snow"), 75: ("Snow", "snow"),
    80: ("Rain", "rain"), 81: ("Rain", "rain"), 82: ("Heavy", "rain"),
    85: ("Snow", "snow"), 86: ("Snow", "snow"),
    95: ("Storm", "rain"), 96: ("Storm", "rain"), 99: ("Storm", "rain"),
}

_cache: dict[str, object] = {"w": None, "ts": 0.0}


def _openmeteo_condition(code: int, cloud_cover: float, precip: float) -> tuple[str, str]:
    if code in (45, 48):
        return "Fog", "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow", "snow"
    if precip >= 2.0:
        return "Heavy", "rain"
    if precip >= 0.3:
        return "Rain", "rain"
    if precip > 0:
        return "Drizzle", "rain"
    if cloud_cover < 20:
        return "Clear", "clear"
    if cloud_cover < 50:
        return "Partly", "partly"
    if cloud_cover < 85:
        return "Cloudy", "cloud"
    return "Overcast", "cloud"


def _fetch_caiyun() -> Weather | None:
    url = f"https://api.caiyunapp.com/v2.6/{CAIYUN_KEY}/{LON},{LAT}/realtime"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        rt = d["result"]["realtime"]
        skycon = rt.get("skycon", "")
        label, icon = _SKYCON.get(skycon, ("Cloudy", "cloud"))
        return Weather(
            temp_c=round(float(rt["temperature"]), 1),
            code=0,
            condition=label,
            icon=icon,
            city=CITY,
        )
    except Exception:
        return None


def _fetch_openmeteo() -> Weather | None:
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,weather_code,cloud_cover,precipitation&timezone=Asia/Shanghai"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        cur = d["current"]
        code   = int(cur["weather_code"])
        cloud  = float(cur.get("cloud_cover") or 0)
        precip = float(cur.get("precipitation") or 0)
        label, icon = _openmeteo_condition(code, cloud, precip)
        return Weather(
            temp_c=round(float(cur["temperature_2m"]), 1),
            code=code,
            condition=label,
            icon=icon,
            city=CITY,
        )
    except Exception:
        return None


def fetch_weather() -> Weather | None:
    now = time.time()
    if _cache["w"] is not None and now - float(_cache["ts"]) < TTL:
        return _cache["w"]  # type: ignore

    w = _fetch_caiyun() if CAIYUN_KEY else _fetch_openmeteo()
    if w is not None:
        _cache.update(w=w, ts=now)
    return w or _cache["w"]  # type: ignore
