# token-saver

A Claude Code plugin that stops you paying to rebuild the prompt cache after a break.

- **`/pause`** — before stepping away: keeps the cache warm for a short break, or writes a handoff note so you can `/clear` and restart light after a long one.
- **`/savings`** — reads your local Claude Code logs and tells you what cache expiry actually costs you, and which strategy would save the most.

## The problem

Claude Code caches your conversation. Each turn re-reads the context from the cache at ~0.1× the normal input price. But the cache expires after a period with no request (1 hour on subscription plans, 5 minutes otherwise). When you come back, the next turn **re-writes the whole context** at 1.25–2× — on a 500k-token session, that is the cost of ~20 normal turns, paid at once.

Two ways out:

| Strategy | How | Pays off when |
|---|---|---|
| **Keep-alive** | a tiny turn every 55 min re-reads the cache and resets its timer (0.1× each) | you really come back within a few hours |
| **Handoff + `/clear`** | a ≤ 60-line resume note, then a fresh session | long or uncertain breaks |

Pinging *every* session automatically loses tokens: most sessions never resume. So `/pause` only pings when you announce a short break.

## Measured on one heavy user (2 months, 87k API calls)

```
Total        2.4B weighted tokens (input-token equivalents)
  cache reads             52.2 %   <- context size x turns
  output                  15.9 %
  rewrites after pause     8.7 %   (494 rewrites, 112.1M tokens)

What each strategy would have saved:
  keep-alive, announced pauses only    106.0M  (4.3 %)
  keep-alive, automatic (3 h cap)        9.1M  (0.4 %)
  handoff note + /clear                170.2M  (7.0 %, resume at 30.0k)
```

Takeaways: cache expiry costs a few percent; the handoff beats pinging on long breaks; and the biggest line by far is **context size × number of turns** — keep sessions small.

Run `/savings` to get your own numbers.

## Install

**Short commands (`/pause`, `/savings`)** — copy the skills into `~/.claude/skills/`:

```
git clone https://github.com/ivantss/token-saver
python3 token-saver/install.py        # Windows: python or py
```

**Or as a plugin** — commands get the plugin prefix (`/token-saver:pause`, `/token-saver:savings`); Claude Code always namespaces plugin commands:

```
/plugin marketplace add ivantss/token-saver
/plugin install token-saver@token-saver
```

Restart Claude Code after either. You can also just say "pause for 2h".

Works on macOS, Linux and Windows. The analyzer also runs on its own (Python 3.8+, standard library only; on Windows use `python` or `py`):

```
python3 skills/savings/token_saver.py [--days 30] [--cap-hours 3] [--resume-size 30000] [--json]
```

## Usage

```
/pause 45m      # cache holds, nothing to do
/pause 2h       # 3 keep-alive pings, stops as soon as you type
/pause tonight  # handoff note in ~/.claude/handoffs/, then /clear
/pause          # asks you
```

(Installed as a plugin: `/token-saver:pause`, `/token-saver:savings`.)

Keep-alive uses Claude Code's built-in `/loop` self-paced mode (`ScheduleWakeup`). It is capped at 4 pings and stops at your first message. It is never used in headless (`claude -p`) sessions.

## How the numbers are computed

- Source: `~/.claude/projects/**/*.jsonl`, deduplicated per API request. Nothing leaves your machine.
- A *rewrite after pause* = a turn that came after more than the cache TTL of silence and wrote > 20k tokens to the cache.
- Weights relative to one uncached input token (Anthropic API price ratios): cache read 0.1, cache write 1.25 (5 min) / 2 (1 h), output 5.
- *Announced* keep-alive is an upper bound: it assumes you ping only on breaks you came back from.
- *Automatic* keep-alive also counts wasted pings on interactive sessions that never resumed. Sub-agents and headless sessions are excluded.
- Subscription plans meter usage their own way: read the result as a ranking of strategies, not a bill.

## License

MIT
