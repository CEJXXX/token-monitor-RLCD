"""Pull Claude usage from local ccusage subprocess.

ccusage parses Claude Code's ~/.claude/projects/**/*.jsonl session logs and
emits JSON aggregations. We shell out instead of re-implementing the parser
so we inherit upstream fixes for free.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from schema import ActiveBlock, Bucket, ClaudeUsage, ModelBreakdown, OtherAgentUsage


CCUSAGE_CMD = os.environ.get("CCUSAGE_CMD", "npx -y ccusage@latest")
# 5h window with claude only; daily/monthly include all agents by default
DEFAULT_TIMEOUT = 60

# Optional limit overrides (Anthropic doesn't publish plan limits programmatically)
WEEKLY_LIMIT_USD = float(os.environ.get("RLCD_WEEKLY_LIMIT_USD", "0")) or None
BLOCK_LIMIT_USD = float(os.environ.get("RLCD_BLOCK_LIMIT_USD", "0")) or None


def _run(args: list[str]) -> dict[str, Any]:
    cmd = CCUSAGE_CMD.split() + args
    env = os.environ.copy()
    env.setdefault("npm_config_cache", "/tmp/.npm-cache")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ccusage failed ({' '.join(args)}): {proc.stderr.strip()[:400]}"
        )
    return json.loads(proc.stdout)


def _bucket(tokens: int, cost: float, limit_usd: float | None = None) -> Bucket:
    pct = (cost / limit_usd) if (limit_usd and limit_usd > 0) else None
    return Bucket(
        tokens_used=int(tokens),
        cost_usd=round(float(cost), 4),
        tokens_limit=None,
        percent_used=round(pct, 4) if pct is not None else None,
    )


def _parse_active_block(blocks_json: dict[str, Any]) -> ActiveBlock | None:
    for blk in blocks_json.get("blocks", []):
        if blk.get("isActive") and not blk.get("isGap"):
            start = datetime.fromisoformat(blk["startTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(blk["endTime"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            minutes_left = max(0, int((end - now).total_seconds() // 60))
            tokens = int(blk.get("totalTokens", 0))
            cost = float(blk.get("costUSD", 0.0))
            projection = blk.get("projection") or {}
            pct = (cost / BLOCK_LIMIT_USD) if BLOCK_LIMIT_USD else None
            return ActiveBlock(
                started_at=start,
                ends_at=end,
                tokens_used=tokens,
                cost_usd=round(cost, 4),
                tokens_limit=None,
                percent_used=round(pct, 4) if pct is not None else None,
                minutes_remaining=minutes_left,
                projection_tokens=projection.get("totalTokens"),
                projection_cost_usd=projection.get("totalCost"),
            )
    return None


def _period_of(e: dict[str, Any]) -> str:
    # Field name differs by command:
    #   unified `ccusage daily`         -> period (YYYY-MM-DD)
    #   agent `ccusage <agent> daily`   -> date   (YYYY-MM-DD)
    #   agent `ccusage <agent> monthly` -> month  (YYYY-MM)
    return e.get("period") or e.get("date") or e.get("month") or ""


def _sum_period(entries: list[dict[str, Any]]) -> tuple[int, float]:
    tokens = sum(int(e.get("totalTokens", 0)) for e in entries)
    cost = round(sum(float(e.get("totalCost", 0.0)) for e in entries), 4)
    return tokens, cost


def _aggregate_model_breakdown(daily_entries: list[dict[str, Any]], top_n: int = 5) -> list[ModelBreakdown]:
    agg: dict[str, dict[str, float]] = {}
    for e in daily_entries:
        for mb in e.get("modelBreakdowns", []) or []:
            name = mb.get("modelName") or "unknown"
            d = agg.setdefault(name, {"tokens": 0, "cost": 0.0})
            d["tokens"] += sum(
                int(mb.get(k, 0))
                for k in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens")
            )
            d["cost"] += float(mb.get("cost", 0.0))
    rows = [
        ModelBreakdown(model=k, tokens=int(v["tokens"]), cost_usd=round(v["cost"], 4))
        for k, v in agg.items()
    ]
    rows.sort(key=lambda r: r.cost_usd, reverse=True)
    return rows[:top_n]


def _model_tokens_today(daily_entries: list[dict[str, Any]], substr: str, today_str: str) -> int:
    """Sum tokens for models whose name contains `substr` in today's entry."""
    total = 0
    for e in daily_entries:
        if _period_of(e) != today_str:
            continue
        for mb in e.get("modelBreakdowns", []) or []:
            if substr in (mb.get("modelName") or "").lower():
                total += sum(
                    int(mb.get(k, 0))
                    for k in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens")
                )
    return total


def fetch_claude() -> tuple[ClaudeUsage, int]:
    """Build a ClaudeUsage by spawning ccusage three times.

    Returns (claude_usage, deepseek_today_tokens) — the second value is the
    DeepSeek-model token count for today, extracted from the same ccusage data.
    """
    blocks_json = _run(["blocks", "--active", "--json"])
    daily_full = _run(["claude", "daily", "--json"])
    monthly_full = _run(["claude", "monthly", "--json"])

    daily_entries = daily_full.get("daily", []) or []
    monthly_entries = monthly_full.get("monthly", []) or []

    # Today: daily entry whose period == today (YYYY-MM-DD)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_entries = [e for e in daily_entries if _period_of(e) == today_str]
    today_tok, today_cost = _sum_period(today_entries)

    # Weekly: last 7 calendar days
    week_cutoff = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    week_entries = [e for e in daily_entries if _period_of(e) >= week_cutoff]
    week_tok, week_cost = _sum_period(week_entries)

    # Month: current month
    month_str = datetime.now().strftime("%Y-%m")
    month_entries = [e for e in monthly_entries if _period_of(e) == month_str]
    month_tok, month_cost = _sum_period(month_entries)

    # Lifetime: sum of all daily entries (could also use totals field)
    life_tok, life_cost = _sum_period(daily_entries)

    usage = ClaudeUsage(
        active_block=_parse_active_block(blocks_json),
        weekly=_bucket(week_tok, week_cost, WEEKLY_LIMIT_USD),
        today=_bucket(today_tok, today_cost),
        month=_bucket(month_tok, month_cost),
        lifetime=_bucket(life_tok, life_cost),
        by_model=_aggregate_model_breakdown(daily_entries),
    )
    ds_today = _model_tokens_today(daily_entries, "deepseek", today_str)
    return usage, ds_today


def fetch_other_agents() -> list[OtherAgentUsage]:
    """Best-effort per-agent breakdown for codex/gemini/copilot using ccusage daily --instances.

    Returns [] silently if no other agents have any data.
    """
    out: list[OtherAgentUsage] = []
    for agent in ("codex", "gemini", "copilot"):
        try:
            daily = _run([agent, "daily", "--json"])
            monthly = _run([agent, "monthly", "--json"])
        except Exception:
            continue
        daily_entries = daily.get("daily", []) or []
        monthly_entries = monthly.get("monthly", []) or []
        if not daily_entries:
            continue
        today_str = datetime.now().strftime("%Y-%m-%d")
        month_str = datetime.now().strftime("%Y-%m")
        today_e = [e for e in daily_entries if _period_of(e) == today_str]
        month_e = [e for e in monthly_entries if _period_of(e) == month_str]
        out.append(
            OtherAgentUsage(
                agent=agent,
                today=_bucket(*_sum_period(today_e)),
                month=_bucket(*_sum_period(month_e)),
                lifetime=_bucket(*_sum_period(daily_entries)),
            )
        )
    return out
