#!/usr/bin/env python3
"""pause-all — end the day in every Claude Code tab of iTerm2 (macOS).

For each iTerm2 tab running `claude` and idle at an empty prompt:
  1. types `/pause tonight tag=<id>`: Claude writes a handoff note
     (~/.claude/handoffs/...-<id>.md) while the cache is still warm;
  2. once the note exists and the turn is over, types `/clear`;
  3. pre-fills (without sending) the morning message that resumes from the
     note. In the morning, press Enter in each tab: nothing to look up.

Skipped, and listed: busy tabs, tabs waiting on a question or permission,
tabs with a draft in the input, the tab running this script. `/clear` is
never sent if the note was not written. The old conversation stays
reachable with `claude --resume`.

    python3 pause_all.py --dry-run       # show what would happen
    python3 pause_all.py                 # do it
    python3 pause_all.py --only <iTerm session id>

Standard library only; needs iTerm2 and macOS Automation permission.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import uuid

HANDOFFS = os.path.expanduser("~/.claude/handoffs")
POLL = 5                 # seconds between checks
NOTE_TIMEOUT = 8 * 60    # per tab, for the note to be written
MAX_TABS = 100
WARM_MIN = 55            # a cache idle longer than this has expired (1-hour TTL)
MIN_CONTEXT = 40_000     # below this, a note is not worth it
MORNING = {
    "fr": "Reprise après la pause : lis {note}, résume en deux lignes où on en était, "
          "puis enchaîne sur la prochaine action.",
    "en": "Resume after the break: read {note}, sum up in two lines where we were, "
          "then go on with the next action.",
}

LIST = '''
tell application "iTerm2"
  set out to ""
  repeat with wi from 1 to count of windows
    set w to window wi
    repeat with ti from 1 to count of tabs of w
      set t to tab ti of w
      repeat with si from 1 to count of sessions of t
        set s to session si of t
        set out to out & (unique id of s) & "|||" & (tty of s) & "|||" & (name of s) & "|||" & wi & "," & ti & "," & si & linefeed
      end repeat
    end repeat
  end repeat
  return out
end tell'''

ON_SESSION = '''
on run argv
  set sid to item 1 of argv
  set n to count of argv
  set {wi, ti, si} to {item (n - 2) of argv as integer, item (n - 1) of argv as integer, item n of argv as integer}
  tell application "iTerm2"
    try
      set s to session si of tab ti of window wi
      if unique id of s is sid then
        %s
      end if
    end try
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if unique id of s is sid then
            %s
          end if
        end repeat
      end repeat
    end repeat
  end tell
  return ""
end run'''

def on_session(action):
    return ON_SESSION % (action, action)


CONTENTS = on_session("return contents of s")
NAME = on_session("return name of s")
TYPE = on_session('''if item 3 of argv is "1" then
              tell s to write text (item 2 of argv)
            else
              tell s to write text (item 2 of argv) newline NO
            end if
            return "ok"''')


def osa(script, *args):
    r = subprocess.run(["osascript", "-e", script, *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def sessions():
    out = []
    for line in osa(LIST).splitlines():
        parts = line.split("|||")
        if len(parts) == 4:
            out.append(dict(id=parts[0], tty=parts[1], name=parts[2], pos=parts[3].split(",")))
    return out


def claude_pid(tty):
    r = subprocess.run(["ps", "-o", "pid=,comm=", "-t", tty.replace("/dev/", "")],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        pid, _, comm = line.strip().partition(" ")
        if os.path.basename(comm.strip()) == "claude":
            return pid
    return None


def activity(pid):
    """(minutes since the session's last API call, context size) from
    ~/.claude/sessions/<pid>.json and the session transcript; (None, 0) if unknown."""
    try:
        with open(os.path.expanduser(f"~/.claude/sessions/{pid}.json")) as fh:
            sid = json.load(fh)["sessionId"]
    except (OSError, ValueError, KeyError):
        return None, 0
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    if not paths:
        return None, 0
    path = paths[0]
    age = (time.time() - os.path.getmtime(path)) / 60
    size = 0
    with open(path, "rb") as fh:
        fh.seek(max(0, os.path.getsize(path) - 400_000))
        for line in fh.read().decode("utf-8", "ignore").splitlines():
            if '"usage"' in line:
                try:
                    u = json.loads(line)["message"]["usage"]
                except (ValueError, KeyError, TypeError):
                    continue
                size = ((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                        + (u.get("cache_creation_input_tokens") or 0))
    return age, size


SEP = re.compile(r"^\s*─{10,}\s*$")


def input_box(contents):
    """Text typed in Claude Code's input box, or None if no input box is shown
    (a question, a permission dialog, or a menu is open)."""
    lines = [l.rstrip() for l in contents.splitlines() if l.strip()]
    seps = [i for i, l in enumerate(lines) if SEP.match(l)]
    if len(seps) < 2:
        return None
    box = lines[seps[-2] + 1:seps[-1]]
    m = re.match(r"^\s*[❯>]\s?(.*)$", box[0]) if box else None
    return " ".join([m.group(1)] + box[1:]).strip() if m else None


def state(s, probe=True):
    """'idle' (empty prompt, turn over), 'busy', 'draft', or 'dialog'."""
    name = osa(NAME, s["id"], *s["pos"]).strip()
    box = input_box(osa(CONTENTS, s["id"], *s["pos"]))
    if not name.startswith("✳"):
        return "busy"
    if box is None:
        return "dialog"
    if box and probe:
        # Claude Code may show a greyed prompt suggestion that is not typed
        # text. Type one character and read the box: a suggestion vanishes, a
        # draft keeps its text. Then erase the character.
        type_text(s, "x", send=False)
        time.sleep(0.8)
        after = input_box(osa(CONTENTS, s["id"], *s["pos"]))
        type_text(s, "\x7f", send=False)
        box = "" if after == "x" else box
    return "draft" if box else "idle"


def type_text(s, text, send):
    osa(TYPE, s["id"], text, "1" if send else "0", *s["pos"])


def note_for(tag):
    found = glob.glob(os.path.join(HANDOFFS, f"*-{tag}.md"))
    return max(found, key=os.path.getmtime) if found else None


def fmt_age(m):
    if m is None:
        return "?"
    return f"{m:.0f}m" if m < 90 else f"{m / 60:.0f}h" if m < 2880 else f"{m / 1440:.0f}d"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="list the tabs and what would happen")
    ap.add_argument("--only", help="one iTerm session id (unique id)")
    ap.add_argument("--all", action="store_true",
                    help="also tabs whose cache expired (the note then costs a full re-write)")
    ap.add_argument("--min-context", type=int, default=MIN_CONTEXT,
                    help="skip tabs whose context is smaller (tokens)")
    ap.add_argument("--concurrency", type=int, default=6, help="notes written at the same time (max 10)")
    ap.add_argument("--lang", choices=sorted(MORNING), default=None)
    a = ap.parse_args(argv)
    lang = a.lang or ("fr" if os.environ.get("LANG", "").lower().startswith("fr") else "en")
    me = os.environ.get("ITERM_SESSION_ID", "").split(":")[-1]
    conc = max(1, min(a.concurrency, 10))

    tabs, skipped = [], []
    for s in sessions()[:MAX_TABS]:
        if s["id"] == me or (a.only and s["id"] != a.only):
            continue
        pid = claude_pid(s["tty"])
        if not pid:
            continue
        age, size = activity(pid)
        st = state(s)
        if st == "idle" and size < a.min_context:
            st = "small"
        elif st == "idle" and not a.all and (age is None or age > WARM_MIN):
            st = "expired"
        s["info"] = f"{fmt_age(age):>6} {size // 1000:>5}k"
        (tabs if st == "idle" else skipped).append((s, st))
    for s, st in tabs + skipped:
        print(f"{'pause' if st == 'idle' else 'skip ' + st:13} {s['tty']:13} {s['info']}  {s['name'][:60]}")
    print("\nskip draft: text typed in the input · dialog: a question is open · "
          "expired: cache expired, use --all · small: < %dk tokens" % (MIN_CONTEXT // 1000))
    if a.dry_run or not tabs:
        print(f"{len(tabs)} tab(s) to pause, {len(skipped)} skipped." + (" (dry run)" if a.dry_run else ""))
        return

    done, failed = [], []
    queue = [s for s, _ in tabs]
    running = {}                                       # id -> (session, tag, start)
    while queue or running:
        while queue and len(running) < conc:
            s = queue.pop(0)
            if state(s) != "idle":                     # changed since the listing
                failed.append((s, "no longer idle"))
                continue
            tag = uuid.uuid4().hex[:8]
            type_text(s, f"/pause tonight tag={tag}", send=True)
            running[s["id"]] = (s, tag, time.time())
        time.sleep(POLL)
        for sid, (s, tag, start) in list(running.items()):
            note = note_for(tag)
            if note and state(s) == "idle":
                type_text(s, "/clear", send=True)
                time.sleep(3)
                type_text(s, MORNING[lang].format(note=note.replace(os.path.expanduser("~"), "~")),
                          send=False)
                done.append((s, note))
                del running[sid]
            elif time.time() - start > NOTE_TIMEOUT:
                failed.append((s, "no note after %d min, left as is" % (NOTE_TIMEOUT // 60)))
                del running[sid]

    print()
    for s, note in done:
        print(f"ok    {s['tty']:13} {os.path.basename(note)}")
    for s, why in failed:
        print(f"FAIL  {s['tty']:13} {why}")
    print(f"\n{len(done)} tab(s) paused, {len(failed)} failed, {len(skipped)} skipped. "
          "In the morning: press Enter in each tab.")


if __name__ == "__main__":
    sys.exit(main())
