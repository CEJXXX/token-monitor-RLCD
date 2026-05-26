# bridge

Python FastAPI daemon that spawns `ccusage` to surface local Claude (and other
LLM-agent) usage data as JSON over HTTP, for the RLCD device to render.

## Prereqs

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or any venv tool
- Node + `npx` available (we shell out to `ccusage` via `npx -y ccusage@latest`)
- A populated `~/.claude/projects/` (Claude Code has been used on this machine)

## Run

```bash
uv sync                       # one-time
uv run python bridge.py       # serves on :7777
curl http://localhost:7777/api/usage | jq
curl 'http://localhost:7777/api/usage?mock=1' | jq   # canned data for firmware bring-up
curl http://localhost:7777/healthz
```

## Endpoints

- `GET /healthz` — liveness + cache age.
- `GET /api/usage` — full usage report (cached `RLCD_CACHE_TTL` seconds, default 60).
- `GET /api/usage?mock=1` — deterministic mock payload, lets you develop firmware
  without poking ccusage.

## Response shape

```jsonc
{
  "updated_at": "2026-05-25T03:30:00Z",
  "source": "ccusage",
  "claude": {
    "active_block": {                  // current 5h billing window (Claude Pro/Max + API)
      "started_at": "...", "ends_at": "...",
      "tokens_used": 112006509, "cost_usd": 77.39,
      "tokens_limit": null, "percent_used": null,    // null unless RLCD_BLOCK_LIMIT_USD set
      "minutes_remaining": 91,
      "projection_tokens": 166M, "projection_cost_usd": 113.23
    },
    "weekly":   { "tokens_used": ..., "cost_usd": ..., "percent_used": null },
    "today":    { "tokens_used": ..., "cost_usd": ... },
    "month":    { "tokens_used": ..., "cost_usd": ... },
    "lifetime": { "tokens_used": ..., "cost_usd": ... },
    "by_model": [
      { "model": "claude-opus-4-7",    "tokens": ..., "cost_usd": ... },
      { "model": "claude-sonnet-4-6",  "tokens": ..., "cost_usd": ... }
    ]
  },
  "other": [
    { "agent": "codex", "today": {...}, "month": {...}, "lifetime": {...} }
  ]
}
```

## Configuration (env vars)

| Var | Default | Notes |
| --- | --- | --- |
| `RLCD_HOST` | `0.0.0.0` | bind address |
| `RLCD_PORT` | `7777` | bind port |
| `RLCD_REFRESH_SEC` | `45` | background refresh interval. A daemon thread reruns ccusage this often and caches the result; `/api/usage` always returns the cached value instantly (a cold ccusage run takes ~12s, so clients must never block on it) |
| `RLCD_INCLUDE_OTHERS` | `1` | set `0` to skip codex/gemini/copilot probes |
| `RLCD_AUTH_TOKEN` | unset | if set, requests must carry `X-RLCD-Token: <value>` (or `?token=<value>`). Required when bridge is reachable from anything beyond loopback. `/healthz` is always open. |
| `RLCD_WEEKLY_LIMIT_USD` | unset | if set (e.g. `100`), `weekly.percent_used` is computed |
| `RLCD_BLOCK_LIMIT_USD` | unset | same for the 5h window |
| `CCUSAGE_CMD` | `npx -y ccusage@latest` | override if you `npm i -g ccusage` and want `ccusage` directly |
| `DEEPSEEK_API_KEY` | unset | enables the `deepseek` block (balance from `/user/balance`). Keep it in a 600-perm `EnvironmentFile`, not the unit. |
| `RLCD_WEATHER_LAT` / `_LON` / `_CITY` | Shenzhen | open-meteo location for the `weather` block |
| `RLCD_LIMITS_FILE` | `/run/rlcd/claude-limits.json` | where the root limits helper writes real 5h/7d utilization |

### Real Claude 5h/7d utilization

`claude.limits` (the numbers Claude Code's `/usage` shows) come from
`anthropic-ratelimit-unified-*` headers on an authenticated call, which needs
the OAuth token in root's `~/.claude/.credentials.json`. A root systemd timer
runs `scripts/rlcd-claude-limits.py` every 3 min, writes
`/run/rlcd/claude-limits.json`, and this daemon (running as your user) reads it:

```bash
sudo install -m 0755 scripts/rlcd-claude-limits.py /usr/local/sbin/rlcd-claude-limits.py
sudo cp scripts/rlcd-claude-limits.{service,timer} /etc/systemd/system/
sudo systemctl enable --now rlcd-claude-limits.timer
```

Each run costs one 1-token Haiku message (negligible). If the OAuth token
expires and Claude Code isn't running to refresh it, `limits.status` goes
`stale`/`err` and the device keeps showing the last good values.

> Anthropic does **not** publish your Pro/Max plan's 5h or weekly limits via API.
> The percent fields stay `null` unless you tell the bridge what your limit is via
> the env vars above.

## Install as a systemd `--user` unit

```bash
../scripts/install-bridge-linux.sh
journalctl --user -u rlcd-bridge -f
```

## Verification

1. `curl :7777/healthz` returns `{"ok": true}`.
2. `curl :7777/api/usage?mock=1` returns the canned shape — useful for offline UI work.
3. `curl :7777/api/usage` shows numbers that match `npx ccusage blocks --active` /
   `npx ccusage claude daily` for today.
4. After running a Claude Code session for ~1 min, `active_block.tokens_used`
   in the next response (≤ `RLCD_CACHE_TTL` seconds later) goes up.
