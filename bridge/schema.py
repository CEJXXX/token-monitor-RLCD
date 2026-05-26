from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ActiveBlock(BaseModel):
    started_at: datetime
    ends_at: datetime
    tokens_used: int
    cost_usd: float
    tokens_limit: Optional[int] = None
    percent_used: Optional[float] = None
    minutes_remaining: int
    projection_tokens: Optional[int] = None
    projection_cost_usd: Optional[float] = None


class Bucket(BaseModel):
    tokens_used: int
    cost_usd: float
    percent_used: Optional[float] = None
    tokens_limit: Optional[int] = None


class ModelBreakdown(BaseModel):
    model: str
    tokens: int
    cost_usd: float


class ClaudeLimits(BaseModel):
    # Real Pro/Max window utilization, from anthropic-ratelimit-unified-* headers
    # (same data Claude Code's /usage shows). 0..1, or None if unavailable.
    util_5h: Optional[float] = None
    util_7d: Optional[float] = None
    reset_5h: Optional[datetime] = None
    reset_7d: Optional[datetime] = None
    status: str = "unavailable"   # "ok" | "stale" | "unavailable" | "err:..."


class ClaudeUsage(BaseModel):
    active_block: Optional[ActiveBlock] = None
    weekly: Bucket
    today: Bucket
    month: Bucket
    lifetime: Bucket
    by_model: list[ModelBreakdown] = Field(default_factory=list)
    limits: Optional[ClaudeLimits] = None


class OtherAgentUsage(BaseModel):
    agent: str
    today: Bucket
    month: Bucket
    lifetime: Bucket


class Weather(BaseModel):
    temp_c: Optional[float] = None
    code: Optional[int] = None
    condition: str = ""          # short English label, e.g. "Cloudy"
    icon: str = ""               # one of: clear/partly/cloud/rain/snow/fog
    city: str = ""


class DeepSeek(BaseModel):
    balance: Optional[float] = None
    currency: str = "CNY"
    granted: Optional[float] = None
    topped: Optional[float] = None
    today_tokens: int = 0        # deepseek-model tokens today (via ccusage)
    available: bool = False


class UsageReport(BaseModel):
    updated_at: datetime
    source: str = "ccusage"
    claude: ClaudeUsage
    other: list[OtherAgentUsage] = Field(default_factory=list)
    weather: Optional[Weather] = None
    deepseek: Optional[DeepSeek] = None
