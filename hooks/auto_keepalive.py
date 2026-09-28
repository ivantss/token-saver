#!/usr/bin/env python3
"""token-saver auto mode — UserPromptSubmit hook.

On each prompt typed by the user in an interactive session, reminds Claude to
arm one wake-up 55 min ahead. If the user goes quiet, the wake-up pings the
session (a cache read, ~0.1x) before the 1-hour cache expires; after 2 pings
it stops. Any new prompt re-arms from zero.

Off switch: the file ~/.claude/token-saver/disabled (see `/pause auto off`).
"""
import json
import os
import sys

PINGS = 2          # best cap measured on real logs: covers pauses up to ~3 h
DELAY = 3300       # 55 min, inside the 1-hour cache TTL

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
