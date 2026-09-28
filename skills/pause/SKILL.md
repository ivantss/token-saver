---
name: pause
description: Pause the current Claude Code session without paying to rebuild the prompt cache. Built for subscription plans (1-hour cache); has an API mode (5-minute cache). `/pause <duration>` (e.g. 45m, 2h, 6h, tonight). Short announced pause → capped keep-alive pings. Long or unknown pause → handoff note + /clear. Use when the user says "pause", "brb", "back in…", "I'm stepping away".
---

# /pause — keep the cache, or restart light

Why: Claude Code caches the conversation prefix. After the cache TTL with no
request, the next turn re-writes the whole context (cost ≈ 2× per token for a
1-hour cache, 1.25× for a 5-minute one). A request that reuses the cache costs
≈ 0.1× (0.05× on Opus 5.5) and resets the TTL.
So a cheap ping before expiry saves the rewrite — but only if the user really
comes back. For long or uncertain pauses, a short handoff note + `/clear`
saves more.

Reply in the user's language. Keep every message to one or two lines.

## 0. Auto mode switch

`/pause auto off` → create the empty file `~/.claude/token-saver/disabled`;
reply "Auto mode off." `/pause auto on` → delete that file; reply "Auto mode
on." `/pause auto` → say whether the file exists. Nothing else.

(Auto mode = a hook that makes every turn arm one wake-up: 55 min ahead, 2
pings max, on a subscription; 4.5 min ahead, 3 pings max, on the API. An explicit `/pause <duration>` below overrides it for this break.)

## 1. Read the duration

Parse `$ARGUMENTS` into minutes. If it says "keep" / "ping", force keep-alive;
if it says "note" / "handoff", force the handoff.

**Empty argument**: do nothing before asking. Call `AskUserQuestion` (one
question, header "Pause"):
- "Under 1 h" — the cache holds, nothing to do.
- "1 h to 4 h" — keep-alive pings (default 2 h → 3 pings).
- "Over 4 h / not sure" — handoff note + /clear.

On a 5-minute cache (step 2), offer instead: "Under 5 min", "5 to 45 min"
(default 20 min → 5 pings), "Over 45 min / not sure".

## 2. Check the cache TTL

The `ScheduleWakeup` tool description states the session's prompt-cache TTL.
- **1 hour** (subscription plans, or API with `CLAUDE_CODE_PROMPT_CACHE_TTL=1h`):
  plan table, ping interval D = 3300 s.
- **5 minutes** (API key, Bedrock, Vertex): API table, D = 270 s.
- Unknown: ask nothing, use the API table.

Plan table (1-hour cache):

| Pause | Action |
|---|---|
| ≤ 55 min | Nothing to do. Reply "Cache valid until ~HH:MM." and stop. |
| 56 min – 4 h | **Keep-alive**: N = ⌈minutes / 55⌉ pings, N ≤ 4. |
| > 4 h, "tonight", "tomorrow", unknown | **Handoff**. |

API table (5-minute cache — a ping costs a cache read, a rewrite 1.25×, so
about 10 pings are worth one saved rewrite):

| Pause | Action |
|---|---|
| ≤ 4 min | Nothing to do. Reply "Cache valid until ~HH:MM." and stop. |
| 5 – 45 min | **Keep-alive**: N = ⌈minutes / 4.5⌉ pings, N ≤ 10. |
| > 45 min, "tonight", unknown | **Handoff**. |

Never in a headless session (`claude -p`, SDK, `CLAUDE_INVOKED_BY` set): reply
that /pause does not apply.

## 3a. Keep-alive

1. Invoke the `loop` skill **without an interval** (self-paced mode) with the
   prompt `pause-ping remaining=N`.
2. On each firing of `pause-ping remaining=K`:
   - call **no** tool other than `ScheduleWakeup`; write nothing beyond "ok";
   - if K > 1: `ScheduleWakeup(delaySeconds=D, prompt="/loop pause-ping remaining=K-1", noop=true, reason="keeping the prompt cache warm during an announced pause")`;
   - if K ≤ 1: `ScheduleWakeup(stop=true)`.
   The `/loop ` prefix is required: it re-enters the loop skill.
3. Before the first `ScheduleWakeup`, tell the user in one line:
   "Cache kept until ~HH:MM (N pings). Send any message to stop."
4. **When the user comes back** (first message that is not a firing): call
   `ScheduleWakeup(stop=true)` before anything else, then handle the message.

## 3b. Handoff note + /clear

1. Write `~/.claude/handoffs/YYYY-MM-DD-HHMM-<topic>.md` (≤ 60 lines). Use
   only what is already in the conversation — do not read files to write it.
   - **Task**: one sentence.
   - **Working directory**.
   - **Done**: bullets, with commits / files changed.
   - **Decisions**: what was settled, and why, one line each.
   - **In progress**: the exact step that was interrupted.
   - **Next action**: the exact command or edit.
   - **Don't redo**: dead ends, traps hit.
   - **Files to reread**: paths + useful line ranges (max 5).
2. Reply in two lines only:
   ```
   Note: <path>
   Run /clear, then on return: "resume from <path>"
   ```

## Rules

- Never more than 4 pings (plan) or 10 pings (API). A loop without a cap is a bug.
- Do not explain the mechanism unless asked.
