# token-saver

A Claude Code plugin that stops you paying to rebuild the prompt cache after a break.

- **`/pause`** — before stepping away: keeps the cache warm for a short break, or writes a handoff note so you can `/clear` and restart light after a long one.
- **`/savings`** — reads your local Claude Code logs and tells you what cache expiry actually costs you, and which strategy would save the most.
- **Auto mode** — the same keep-alive, without asking: after each of your messages, a ping is armed before the cache expires.

## Two approaches: subscription or API

Claude Code's cache does not last the same time depending on how you pay. token-saver was **built for subscription plans**, and has a separate mode for the API. It picks the right one by itself.

| | [Subscription (Pro / Max)](#approach-1--subscription-pro--max) | [API (key, Bedrock, Vertex)](#approach-2--api-key-bedrock-vertex) |
|---|---|---|
| Cache lifetime | 1 hour | 5 minutes |
| Auto mode | ping every 55 min, 2 pings max (~3 h) | ping every 4.5 min, 3 pings max (~18 min) |
| `/pause` keep-alive | breaks of 1 h – 4 h (≤ 4 pings) | breaks of 5 – 45 min (≤ 10 pings) |
| `/pause` handoff + `/clear` | breaks > 4 h | breaks > 45 min |
| What you save | usage-limit headroom | money |
| Measured gain, auto mode | +1 % | +1 % to +5.5 % (depends on the model) |

Detection: API mode is on when `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK` or `CLAUDE_CODE_USE_VERTEX` is set, unless `CLAUDE_CODE_PROMPT_CACHE_TTL=1h`. Otherwise, subscription mode. Commands:

| Command | Effect |
|---|---|
| `/pause mode plan` | force subscription mode |
| `/pause mode api` | force API mode |
| `/pause mode detect` | back to automatic detection (default) |
| `/pause mode` | show the current mode |
| `/pause auto off` / `/pause auto on` | turn auto mode (the automatic pings) off / back on |

The environment variable `TOKEN_SAVER_MODE=plan|api` also forces a mode; it wins over `/pause mode`. Remove it to go back to detection.

## The problem

Claude Code caches your conversation. Each turn re-reads the context from the cache at ~0.1× the normal input price (0.05× on Opus 5.5). But the cache expires after a period with no request (1 hour on subscription plans, 5 minutes on the API). When you come back, the next turn **re-writes the whole context** at 1.25–2× — on a 500k-token session, that is the cost of ~20 normal turns, paid at once.

Two ways out:

| Strategy | How | Pays off when |
|---|---|---|
| **Keep-alive** | a tiny turn before expiry re-reads the cache and resets its timer | you really come back soon |
| **Handoff + `/clear`** | a ≤ 60-line resume note, then a fresh session | long or uncertain breaks |

Pinging *every* session automatically loses tokens: most sessions never resume. So the caps are low, and `/pause` pings longer only when you announce a break.

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

Auto mode:

- Plugin install: on by default (`hooks/hooks.json`).
- Short install: add to `~/.claude/settings.json`, under `hooks`:
  ```json
  "UserPromptSubmit": [{ "hooks": [{ "type": "command", "timeout": 5,
    "command": "python3 /path/to/token-saver/hooks/auto_keepalive.py" }] }]
  ```
- Off / on: `/pause auto off`, `/pause auto on`. An explicit `/pause <duration>` overrides it for one break only; your next message re-arms auto mode.

Works on macOS, Linux and Windows. The analyzer also runs on its own (Python 3.8+, standard library only; on Windows use `python` or `py`):

```
python3 skills/savings/token_saver.py [--days 30] [--cap-hours 3] [--resume-size 30000] [--json]
python3 skills/savings/token_saver.py --api [--read-weight 0.05]   # replay as API billing
```

Keep-alive uses Claude Code's built-in `/loop` self-paced mode (`ScheduleWakeup`). It stops at your first message and is never used in headless (`claude -p`, SDK) sessions. Limit: a turn that uses no tool does not re-arm auto mode; the wake-up armed by an earlier turn still fires.

---

## Approach 1 — Subscription (Pro / Max)

1-hour cache. This is what token-saver was built for.

### Why it's worth it

Take a 400k-token session and a 1 h 30 coffee-and-meeting break.

| | Without token-saver | With auto mode |
|---|---|---|
| Before the break | context already in cache | same — already paid, identical on both sides |
| During the break | nothing | 1 ping = 400k read from cache ×0.1 = **40k** |
| First turn back | cache expired → 400k re-written ×2 = **800k** | cache still warm → 400k read ×0.1 = **40k** |
| Cost of the break | **800k** | **80k** |

(Weighted tokens, relative to one uncached input token. The session's cost before the break is the same in both columns, so it is left out.)

One break, 10× cheaper — usage-limit headroom you get back.

- **You don't have to think about it.** Nobody types `/pause` before a meeting. Auto mode arms the ping for you and stops by itself (2 pings max, ~3 h), so a session you abandon costs at most two cheap reads.
- **It never pings for nothing when you're active.** Every message re-arms the timer; pings only fire after 55 min of silence.
- **You can see what it saved.** `/savings --check` lists each break, whether the cache was kept, the tokens not re-written, and the net gain after the pings' own cost.
- **Its limits are measured, not assumed.** On two months of real logs, pinging longer than ~3 h, or every session blindly, loses tokens — that's why the caps are where they are.

### Usage

```
/pause 45m      # cache holds, nothing to do
/pause 2h       # 3 keep-alive pings, stops as soon as you type
/pause tonight  # handoff note in ~/.claude/handoffs/, then /clear
/pause          # asks you
```

### Measured on one heavy user (2 months, 87k API calls)

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

Auto mode with its 2-ping cap: **+1 %** net (automatic pings on sessions that never resume included), versus a loss for longer caps.

Takeaways: cache expiry costs a few percent; the handoff beats pinging on long breaks; and the biggest line by far is **context size × number of turns** — keep sessions small. Run `/savings` to get your own numbers.

---

## Approach 2 — API (key, Bedrock, Vertex)

5-minute cache. Every break over 5 minutes means a rewrite, so pings must be frequent and short-lived.

### Why it's worth it

Same 400k-token session on Opus 5.5 (cache read 0.05×), a 15-minute break.

| | Without token-saver | With auto mode |
|---|---|---|
| During the break | nothing | 3 pings = 3 × 400k × 0.05 = **60k** |
| First turn back | cache expired → 400k re-written ×1.25 = **500k** | cache still warm → 400k × 0.05 = **20k** |
| Cost of the break | **500k** | **80k** |

One break, 6× cheaper — in money.

### Usage

```
/pause 3m       # cache holds, nothing to do
/pause 20m      # 5 keep-alive pings (one every 4.5 min), stops as soon as you type
/pause 1h       # handoff note in ~/.claude/handoffs/, then /clear
/pause          # asks you
```

Beyond ~45 min, pings cost more than the rewrite they avoid (a rewrite ≈ 10 pings at 0.1×), so `/pause` writes a handoff note instead.

### Measured: the same logs, replayed as API billing

`token_saver.py --api` replays the two months of logs above as if billed on the API with a 5-minute cache. Saving, in % of the whole bill:

| Strategy | Cache read 0.1× | Cache read 0.05× (Opus 5.5) |
|---|---|---|
| Auto keep-alive, 1 ping (4.5 min) | +0.8 % | +2.9 % |
| Auto keep-alive, 2 pings (9 min) | **+1.0 %** | +4.9 % |
| Auto keep-alive, 3 pings (13.5 min) — default | +0.4 % | **+5.5 %** |
| Auto keep-alive, 6 pings (27 min) | −2.9 % | +4.9 % |
| Auto keep-alive, 12 pings (54 min) | −11.5 % | +0.1 % |
| `/pause` on announced breaks (upper bound) | +7.7 % | +13.3 % |
| Handoff + `/clear` on breaks > 1 h | +4.2 % | +5.6 % |
| Switch to the 1-hour cache (`CLAUDE_CODE_PROMPT_CACHE_TTL=1h`) | −2.9 % | −3.3 % |

Takeaways:

- Short automatic pings pay; long ones lose.
- Announcing breaks with `/pause` pays most.
- Switching the API to the 1-hour cache costs more than it saves: every cache write goes from 1.25× to 2×, not only the ones after a break.
- The default cap of 3 pings is tuned for Opus 5.5. With 0.1× reads, 2 pings is best. Run `/savings --api` (add `--read-weight 0.05` for Opus 5.5) for your own numbers.

---

## How the numbers are computed

- Source: `~/.claude/projects/**/*.jsonl`, deduplicated per API request. Nothing leaves your machine.
- A *rewrite after pause* = a turn that came after more than the cache TTL of silence and wrote > 20k tokens to the cache.
- Weights relative to one uncached input token (Anthropic API price ratios): cache read 0.1 (0.05 on Opus 5.5, `--read-weight`), cache write 1.25 (5 min) / 2 (1 h), output 5.
- *Announced* keep-alive is an upper bound: it assumes you ping only on breaks you came back from.
- *Automatic* keep-alive also counts wasted pings on interactive sessions that never resumed. Sub-agents and headless sessions are excluded.
- *API replay*: each return after more than 5 min of silence is re-billed as a rewrite; recorded pings are removed first and the replay decides the pings.
- Subscription plans meter usage their own way: read subscription results as a ranking of strategies, not a bill.

## License

MIT
