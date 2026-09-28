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

Options: `--days N` (last N days), `--cap-hours H`, `--resume-size T`,
`--json`. It reads `~/.claude/projects/**/*.jsonl` locally; nothing is sent
anywhere. It can take ~20 s on large histories.

Show the report as is, then add at most three lines:
- the biggest cost line (usually cache reads = context size × turns);
- which pause strategy wins for this user;
- one concrete habit (e.g. `/pause` before long breaks, `/compact` sooner).

Weights are API price ratios, not a bill; say so only if asked about money.
