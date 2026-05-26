#!/usr/bin/env python3
"""Write real Claude Pro/Max window utilization to /run/rlcd/claude-limits.json.

Runs as root (via rlcd-claude-limits.timer) because the OAuth token lives in
root's ~/.claude/.credentials.json. Makes a minimal authenticated /v1/messages
call and parses the `anthropic-ratelimit-unified-*` response headers — the same
data Claude Code's /usage shows. The bridge (running as a normal user) just
reads the JSON file.

Cost: one 1-token Haiku message per run; negligible.
"""
import json, os, time, urllib.request

CRED = os.environ.get("RLCD_CRED", "/root/.claude/.credentials.json")
OUT = os.environ.get("RLCD_LIMITS_FILE", "/run/rlcd/claude-limits.json")


def load_prev():
    try:
        return json.load(open(OUT))
    except Exception:
        return {}


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    prev = load_prev()
    try:
        tok = json.load(open(CRED))["claudeAiOauth"]["accessToken"]
    except Exception as e:
        prev["status"] = f"err:cred:{e}"; prev["ts"] = int(time.time())
        _write(prev); return

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "."}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={
            "authorization": f"Bearer {tok}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            h = r.headers

        def f(name, cast=float, default=None):
            v = h.get(name)
            return cast(v) if v is not None else default

        out = {
            "util_5h": f("anthropic-ratelimit-unified-5h-utilization"),
            "util_7d": f("anthropic-ratelimit-unified-7d-utilization"),
            "reset_5h": f("anthropic-ratelimit-unified-5h-reset", int),
            "reset_7d": f("anthropic-ratelimit-unified-7d-reset", int),
            "status": "ok",
            "ts": int(time.time()),
        }
        _write(out)
    except Exception as e:
        # keep last-good values, just flag the error + timestamp
        prev["status"] = f"err:{type(e).__name__}"; prev["ts"] = int(time.time())
        _write(prev)


def _write(d):
    tmp = OUT + ".tmp"
    json.dump(d, open(tmp, "w"))
    os.replace(tmp, OUT)
    os.chmod(OUT, 0o644)


if __name__ == "__main__":
    main()
