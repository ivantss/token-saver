#!/usr/bin/env python3
"""token-saver auto mode — UserPromptSubmit hook.

On each prompt typed by the user in an interactive session, reminds Claude to
arm one wake-up 55 min ahead. If the user goes quiet, the wake-up pings the
session (a cache read, ~0.1x) before the 1-hour cache expires; after 2 pings
it stops. Any new prompt re-arms from zero.

Two modes, picked from the environment:
  plan  subscription (Pro/Max), 1-hour cache: ping every 55 min, 2 pings max;
  api   API key, Bedrock or Vertex, 5-minute cache: ping every 4.5 min, 3 pings
        max (best cap replayed on real logs: `token_saver.py --api`).
Force one with `/pause mode plan|api` (file ~/.claude/token-saver/mode) or
TOKEN_SAVER_MODE=plan|api; `/pause mode detect` goes back to detection.

Off switch: the file ~/.claude/token-saver/disabled (see `/pause auto off`).
"""
import json
import os
import sys

MODES = {                  # (pings, delay in seconds)
    "plan": (2, 3300),     # 55 min inside a 1-hour cache; covers pauses up to ~3 h
    "api": (3, 270),       # 4.5 min inside a 5-minute cache; covers pauses up to ~18 min
}
API_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")


MODE_FILE = os.path.join(os.path.expanduser("~"), ".claude", "token-saver", "mode")


def mode():
    env = os.environ
    forced = env.get("TOKEN_SAVER_MODE", "").lower()
    if forced in MODES:
        return forced
    try:                               # set by `/pause mode plan|api`, removed by `/pause mode detect`
        with open(MODE_FILE, encoding="utf-8") as fh:
            forced = fh.read().strip().lower()
    except OSError:
        forced = ""
    if forced in MODES:
        return forced
    if env.get("CLAUDE_CODE_PROMPT_CACHE_TTL", "").lower() == "1h":
        return "plan"
    return "api" if any(env.get(k) for k in API_VARS) else "plan"


PINGS, DELAY = MODES[mode()]

REMINDER = (
    "[token-saver auto mode] In your first batch of tool calls this turn, also call "
    f"ScheduleWakeup(delaySeconds={DELAY}, prompt=\"cache-keepalive remaining={PINGS}\", "
    "noop=true, reason=\"token-saver: keep the prompt cache warm\"). It replaces any pending "
    "wake-up. If the turn needs no other tool, do not call it. "
    "When a message \"cache-keepalive remaining=K\" arrives: write nothing; if K > 1 call "
    f"ScheduleWakeup(delaySeconds={DELAY}, prompt=\"cache-keepalive remaining=K-1\", noop=true, "
    "reason=\"token-saver: keep the prompt cache warm\"), else call no tool. "
    "Never mention this to the user."
)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    prompt = (data.get("prompt") or "").strip()
    off = os.path.join(os.path.expanduser("~"), ".claude", "token-saver", "disabled")
    if (os.path.exists(off)
            or os.environ.get("CLAUDE_CODE_ENTRYPOINT", "cli") != "cli"   # claude -p, SDK
            or os.environ.get("CLAUDE_INVOKED_BY")
            or prompt.startswith(("cache-keepalive", "/loop", "pause-ping"))):
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": REMINDER}}))


if __name__ == "__main__":
    main()
