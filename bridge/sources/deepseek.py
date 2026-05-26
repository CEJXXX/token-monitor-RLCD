"""DeepSeek account balance from the official API.

DeepSeek exposes /user/balance (balance only — no usage/history endpoint).
Token usage for DeepSeek *models* run through Claude Code is read separately
from ccusage and passed in as `today_tokens`.
"""
from __future__ import annotations

import os
import json
import time
import urllib.request

from schema import DeepSeek

API_KEY = os.environ.get("DEEPSEEK_API_KEY") or None
TTL = int(os.environ.get("RLCD_DEEPSEEK_TTL", "300"))  # 5 min

_cache: dict[str, object] = {"d": None, "ts": 0.0}


def fetch_deepseek(today_tokens: int = 0) -> DeepSeek | None:
    if API_KEY is None:
        return None
    now = time.time()
    cached = _cache["d"]
    if cached is not None and now - float(_cache["ts"]) < TTL:
        cached.today_tokens = today_tokens  # type: ignore
        return cached  # type: ignore
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        infos = d.get("balance_infos") or [{}]
        b0 = infos[0]
        ds = DeepSeek(
            balance=float(b0.get("total_balance", 0) or 0),
            currency=b0.get("currency", "CNY"),
            granted=float(b0.get("granted_balance", 0) or 0),
            topped=float(b0.get("topped_up_balance", 0) or 0),
            today_tokens=today_tokens,
            available=bool(d.get("is_available", False)),
        )
        _cache.update(d=ds, ts=now)
        return ds
    except Exception:
        if cached is not None:
            cached.today_tokens = today_tokens  # type: ignore
        return cached  # type: ignore
