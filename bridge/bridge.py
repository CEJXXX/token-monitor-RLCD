"""RLCD bridge daemon.

GET /api/usage           -> live usage (cached 60s)
GET /api/usage?mock=1    -> deterministic mock payload, for firmware bring-up
GET /healthz             -> liveness

Run: `uv run bridge.py` or `uvicorn bridge:app --host 0.0.0.0 --port 7777`
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from schema import (
    ActiveBlock,
    Bucket,
    ClaudeUsage,
    ModelBreakdown,
    OtherAgentUsage,
    UsageReport,
)
from sources.claude_local import fetch_claude, fetch_other_agents


REFRESH_INTERVAL_SEC = int(os.environ.get("RLCD_REFRESH_SEC", "45"))
INCLUDE_OTHERS = os.environ.get("RLCD_INCLUDE_OTHERS", "1") != "0"
AUTH_TOKEN = os.environ.get("RLCD_AUTH_TOKEN") or None  # blank/unset = no auth

app = FastAPI(title="RLCD bridge", version="0.1.0")

_cache_lock = threading.Lock()
_cache: dict[str, object] = {"report": None, "ts": 0.0, "error": None}


def _build_live_report() -> UsageReport:
    claude = fetch_claude()
    others = fetch_other_agents() if INCLUDE_OTHERS else []
    return UsageReport(
        updated_at=datetime.now(timezone.utc),
        claude=claude,
        other=others,
    )


def _get_cached() -> tuple[UsageReport | None, str | None]:
    # Non-blocking: a background thread keeps the cache warm, so clients
    # (the ESP32, with a short HTTP timeout) never wait on a cold ccusage run.
    with _cache_lock:
        return _cache.get("report"), _cache.get("error")


def _refresh_once() -> None:
    try:
        rep = _build_live_report()
        with _cache_lock:
            _cache.update(report=rep, ts=time.time(), error=None)
    except Exception as e:
        with _cache_lock:
            _cache["error"] = f"{type(e).__name__}: {e}"


def _refresher_loop() -> None:
    while True:
        _refresh_once()
        time.sleep(REFRESH_INTERVAL_SEC)


_refresher_started = False


def _start_refresher() -> None:
    global _refresher_started
    if _refresher_started:
        return
    _refresher_started = True
    threading.Thread(target=_refresher_loop, name="usage-refresher", daemon=True).start()


def _mock_report() -> UsageReport:
    now = datetime.now(timezone.utc)
    return UsageReport(
        updated_at=now,
        source="mock",
        claude=ClaudeUsage(
            active_block=ActiveBlock(
                started_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
                ends_at=now.replace(hour=15, minute=0, second=0, microsecond=0),
                tokens_used=162_438,
                cost_usd=4.21,
                percent_used=0.62,
                minutes_remaining=134,
                projection_tokens=260_000,
                projection_cost_usd=6.80,
            ),
            weekly=Bucket(tokens_used=2_410_000, cost_usd=58.13, percent_used=0.41),
            today=Bucket(tokens_used=382_000, cost_usd=9.14),
            month=Bucket(tokens_used=8_400_000, cost_usd=187.22),
            lifetime=Bucket(tokens_used=18_200_000, cost_usd=214.07),
            by_model=[
                ModelBreakdown(model="claude-opus-4-7", tokens=12_900_000, cost_usd=180.00),
                ModelBreakdown(model="claude-sonnet-4-6", tokens=4_400_000, cost_usd=28.00),
                ModelBreakdown(model="claude-haiku-4-5", tokens=900_000, cost_usd=6.07),
            ],
        ),
        other=[
            OtherAgentUsage(
                agent="codex",
                today=Bucket(tokens_used=124_000, cost_usd=0.31),
                month=Bucket(tokens_used=1_800_000, cost_usd=4.40),
                lifetime=Bucket(tokens_used=5_200_000, cost_usd=11.90),
            ),
        ],
    )


@app.on_event("startup")
def _on_startup():
    _start_refresher()


@app.get("/healthz")
def healthz():
    return {"ok": True, "cache_age_sec": int(time.time() - float(_cache.get("ts", 0.0) or 0))}


def _check_auth(token_header: str | None, token_query: str | None) -> None:
    if AUTH_TOKEN is None:
        return
    presented = token_header or token_query
    if presented != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing token")


@app.get("/api/usage")
def get_usage(
    mock: int = Query(0),
    token: str | None = Query(None),
    x_rlcd_token: str | None = Header(None),
):
    _check_auth(x_rlcd_token, token)
    if mock:
        return _mock_report().model_dump(mode="json")
    rep, err = _get_cached()
    if rep is None:
        return JSONResponse(
            status_code=503,
            content={"error": err or "no data yet", "hint": "is ccusage installed and is ~/.claude populated?"},
        )
    payload = rep.model_dump(mode="json")
    if err:
        payload["stale"] = True
        payload["error"] = err
    return payload


def main():
    import uvicorn

    host = os.environ.get("RLCD_HOST", "0.0.0.0")
    port = int(os.environ.get("RLCD_PORT", "7777"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
