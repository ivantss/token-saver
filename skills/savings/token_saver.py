#!/usr/bin/env python3
"""token-saver — measure what prompt-cache expiry costs you in Claude Code.

Reads the session logs Claude Code writes to ~/.claude/projects/ (one .jsonl
per session), finds every turn that re-wrote the whole context because the
cache had expired during a pause, and estimates what three strategies would
have saved:

  keep-alive (announced)  ping the session before the cache expires, only on
                          pauses you actually came back from (upper bound);
  keep-alive (automatic)  ping every session after each turn, up to a cap —
                          including the many sessions that never resume;
  handoff + /clear        write a short resume note, /clear, and restart
                          from a small context.

Weights are relative to one uncached input token, from Anthropic API pricing
ratios: cache read x0.1, cache write x1.25 (5-min TTL) or x2 (1-hour TTL),
output x5. Subscription plans meter usage differently; treat the result as a
ranking of strategies, not as a bill.

Standard library only. Usage:
    python3 token_saver.py [--days N] [--cap-hours H] [--resume-size T] [--json]
"""
import argparse
import collections
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

W_READ, W_OUT = 0.1, 5.0
W_WRITE = {5: 1.25, 60: 2.0}
PING_MARGIN = 0.9          # ping at 90 % of the TTL (55 min for 1 h)
MIN_REWRITE = 20_000
ORDER = ["<1h", "1-3h", "3-8h", "8-24h", ">24h"]       # ignore small cache writes (normal turn growth)


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_sessions(root):
    """Yield (path, interactive, calls) per session file.

    calls = sorted list of (time, input, write5m, write1h, read, output),
    deduplicated on (message id, request id): Claude Code logs one line per
    content block with the same usage repeated.
    """
    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        seen, calls, interactive = set(), [], True
        try:
            with open(path, errors="ignore") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    m = d.get("message") or {}
                    u, ts = m.get("usage"), d.get("timestamp")
                    if not u or not ts:
                        continue
                    key = (m.get("id"), d.get("requestId"))
                    if key in seen:
                        continue
                    seen.add(key)
                    if d.get("isSidechain") or d.get("entrypoint", "cli") != "cli":
                        interactive = False
                    cc = u.get("cache_creation") or {}
                    w_all = u.get("cache_creation_input_tokens") or 0
                    w1 = cc.get("ephemeral_1h_input_tokens") or 0
                    w5 = (w_all - w1) if cc else w_all
                    calls.append((parse_ts(ts), u.get("input_tokens") or 0, w5, w1,
                                  u.get("cache_read_input_tokens") or 0,
                                  u.get("output_tokens") or 0))
        except OSError:
            continue
        if calls:
            calls.sort()
            yield path, interactive and "subagents" not in path, calls


def ttl_of(w5, w1):
    return 60 if w1 >= w5 else 5


def analyze(root, days, cap_hours, resume_size, now=None):
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days) if days else datetime.min.replace(tzinfo=timezone.utc)
    tot = collections.Counter()
    rewrites, tails = [], []
    first = last = None
    n_sessions = 0
    for path, interactive, calls in load_sessions(root):
        calls = [c for c in calls if c[0] >= since]
        if not calls:
            continue
        n_sessions += 1
        first = min(first or calls[0][0], calls[0][0])
        last = max(last or calls[-1][0], calls[-1][0])
        for i, (t, inp, w5, w1, rd, out) in enumerate(calls):
            tot["input"] += inp; tot["write_5m"] += w5; tot["write_1h"] += w1
            tot["read"] += rd; tot["output"] += out; tot["calls"] += 1
            if i == 0:
                continue
            ttl = ttl_of(w5, w1)
            gap = (t - calls[i - 1][0]).total_seconds() / 60
            written = w5 + w1
            if gap > ttl and written > MIN_REWRITE and written > rd:
                rewrites.append(dict(gap=gap, ttl=ttl, size=written, interactive=interactive))
        if interactive:
            t, inp, w5, w1, rd, out = calls[-1]
            tails.append(dict(t=t, size=inp + w5 + w1 + rd + out, ttl=ttl_of(w5, w1)))

    weighted_total = (tot["input"] + W_WRITE[5] * tot["write_5m"] + W_WRITE[60] * tot["write_1h"]
                      + W_READ * tot["read"] + W_OUT * tot["output"])
    rw_weighted = sum(r["size"] * W_WRITE[r["ttl"]] for r in rewrites)

    announced = auto = handoff = 0.0
    avoided = 0
    ping_reads = 0
    for r in rewrites:
        if not r["interactive"]:
            continue
        C, ttl, gap = r["size"], r["ttl"], r["gap"]
        interval = ttl * PING_MARGIN
        n = int(gap // interval)
        gain = C * (W_WRITE[ttl] - W_READ) - n * W_READ * C
        if gain > 0:
            announced += gain
            avoided += 1
        if gap <= cap_hours * 60:
            auto += gain
            ping_reads += n * C
        else:
            ncap = int(cap_hours * 60 // interval)
            auto -= ncap * W_READ * C
            ping_reads += ncap * C
        handoff += max(0, C - resume_size) * W_WRITE[ttl]
    # automatic pings also fire on sessions that never come back
    for s in tails:
        if (now - s["t"]).total_seconds() > cap_hours * 3600:
            ncap = int(cap_hours * 60 // (s["ttl"] * PING_MARGIN))
            auto -= ncap * W_READ * s["size"]
            ping_reads += ncap * s["size"]

    buckets = collections.Counter()
    for r in rewrites:
        g = r["gap"]
        label = ("<1h" if g < 60 else "1-3h" if g < 180 else "3-8h" if g < 480
                 else "8-24h" if g < 1440 else ">24h")
        buckets[label] += r["size"]

    pct = lambda x: round(100 * x / weighted_total, 1) if weighted_total else 0.0
    return {
        "period": {"from": first.isoformat() if first else None,
                   "to": last.isoformat() if last else None,
                   "sessions": n_sessions, "api_calls": tot["calls"]},
        "raw_tokens": {k: tot[k] for k in ("input", "write_5m", "write_1h", "read", "output")},
        "weighted_total": round(weighted_total),
        "share_pct": {
            "cache_reads": pct(W_READ * tot["read"]),
            "output": pct(W_OUT * tot["output"]),
            "rewrites_after_pause": pct(rw_weighted),
        },
        "rewrites_after_pause": {"count": len(rewrites),
                                 "tokens": sum(r["size"] for r in rewrites),
                                 "weighted": round(rw_weighted),
                                 "tokens_by_pause_length": dict(buckets)},
        "strategies": {
            "keepalive_announced": {"weighted_saving": round(announced), "pct": pct(announced),
                                    "rewrites_avoided": avoided},
            "keepalive_automatic": {"weighted_saving": round(auto), "pct": pct(auto),
                                    "cap_hours": cap_hours, "ping_read_tokens": ping_reads},
            "handoff_clear": {"weighted_saving": round(handoff), "pct": pct(handoff),
                              "resume_size": resume_size},
        },
    }


def fmt(n):
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}"
    return f"{n:.0f}"


def report(r):
    p, s, st = r["period"], r["share_pct"], r["strategies"]
    rw = r["rewrites_after_pause"]
    out = [
        f"Period       {(p['from'] or '?')[:10]} -> {(p['to'] or '?')[:10]}  "
        f"({p['sessions']} sessions, {p['api_calls']} API calls)",
        f"Total        {fmt(r['weighted_total'])} weighted tokens (input-token equivalents)",
        f"  cache reads            {s['cache_reads']:5.1f} %   <- context size x turns",
        f"  output                 {s['output']:5.1f} %",
        f"  rewrites after pause   {s['rewrites_after_pause']:5.1f} %   "
        f"({rw['count']} rewrites, {fmt(rw['tokens'])} tokens)",
        "",
        "What each strategy would have saved:",
        f"  keep-alive, announced pauses only   {fmt(st['keepalive_announced']['weighted_saving']):>7}"
        f"  ({st['keepalive_announced']['pct']} %)",
        f"  keep-alive, automatic ({st['keepalive_automatic']['cap_hours']} h cap)     "
        f"{fmt(st['keepalive_automatic']['weighted_saving']):>7}  ({st['keepalive_automatic']['pct']} %)",
        f"  handoff note + /clear               {fmt(st['handoff_clear']['weighted_saving']):>7}"
        f"  ({st['handoff_clear']['pct']} %, resume at {fmt(st['handoff_clear']['resume_size'])})",
        "",
        "Rewritten tokens by pause length: "
        + ", ".join(f"{k} {fmt(v)}" for k, v in sorted(rw["tokens_by_pause_length"].items(),
                                               key=lambda kv: ORDER.index(kv[0]))),
    ]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=int, default=0, help="only the last N days (0 = all)")
    ap.add_argument("--cap-hours", type=float, default=3, help="ping cap for the automatic strategy")
    ap.add_argument("--resume-size", type=int, default=30_000, help="context size after handoff + /clear")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.projects_dir):
        sys.exit(f"no Claude Code logs at {a.projects_dir}")
    r = analyze(a.projects_dir, a.days, a.cap_hours, a.resume_size)
    print(json.dumps(r, indent=2) if a.json else report(r))


if __name__ == "__main__":
    main()
