---
name: savings
description: Measure how many tokens prompt-cache expiry costs the user in Claude Code, from their local session logs, and what /pause strategies would save. Use when the user asks about cache cost, token waste, "how much would /pause save", or runs /savings.
---

# /savings — measure cache-expiry cost

Run, from this skill's base directory:

```
python3 <base directory>/token_saver.py $ARGUMENTS
```

On Windows, use `python` or `py` if `python3` is not found.

`--check [--days N]` (default 7 days) lists each keep-alive episode: pings,
quiet time, and the user's return — "kept" (cache read, tokens saved),
"not needed" (the cache would have held anyway), "REWRITTEN" (ping too late),
"none" (never came back). Ends with tokens not re-written and the net saving
after the pings' own cost.

`--api [--read-weight 0.05]` replays the logs as if billed on the API
(5-minute cache): auto keep-alive by ping cap, `/pause`, handoff, and the
1-hour cache option. Use 0.05 for Opus 5.5, 0.1 otherwise.

Options: `--days N` (last N days), `--cap-hours H`, `--resume-size T`,
`--json`. It reads `~/.claude/projects/**/*.jsonl` locally; nothing is sent
anywhere. It can take ~20 s on large histories.

Show the report as is, then add at most three lines:
- the biggest cost line (usually cache reads = context size × turns);
- which pause strategy wins for this user;
- one concrete habit (e.g. `/pause` before long breaks, `/compact` sooner).

Weights are API price ratios, not a bill; say so only if asked about money.
