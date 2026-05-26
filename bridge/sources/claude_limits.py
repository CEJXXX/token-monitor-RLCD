"""Read real Claude Pro/Max window utilization.

Anthropic has no clean usage endpoint; the numbers Claude Code's /usage shows
come from `anthropic-ratelimit-unified-*` response headers on an authenticated
call. That call needs the OAuth token in ~/.claude/.credentials.json, which is
root-owned here. So a root systemd timer (scripts/rlcd-claude-limits.py) makes
the call and writes the parsed values to LIMITS_FILE; this module just reads it.
"""
from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone

from schema import ClaudeLimits

LIMITS_FILE = os.environ.get("RLCD_LIMITS_FILE", "/run/rlcd/claude-limits.json")
STALE_AFTER = int(os.environ.get("RLCD_LIMITS_STALE", "600"))  # 10 min


def fetch_limits() -> ClaudeLimits | None:
    try:
        d = json.load(open(LIMITS_FILE))
    except Exception:
        return None
    u5 = d.get("util_5h")
    u7 = d.get("util_7d")
    if u5 is None or u5 < 0:
        return ClaudeLimits(status=str(d.get("status", "unavailable")))
    age = time.time() - float(d.get("ts", 0))
    status = "ok" if age < STALE_AFTER else "stale"

    def ts(key: str) -> datetime | None:
        v = d.get(key)
        return datetime.fromtimestamp(int(v), tz=timezone.utc) if v else None

    return ClaudeLimits(
        util_5h=float(u5),
        util_7d=float(u7) if u7 is not None else None,
        reset_5h=ts("reset_5h"),
        reset_7d=ts("reset_7d"),
        status=status,
    )
