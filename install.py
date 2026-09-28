#!/usr/bin/env python3
"""Install /pause and /savings as personal skills (short names, no plugin prefix).

    python3 install.py            # copy skills to ~/.claude/skills/
    python3 install.py --remove   # remove them
"""
import os
import shutil
import sys

SKILLS = ("pause", "savings")
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
dst = os.path.join(os.path.expanduser("~"), ".claude", "skills")

for name in SKILLS:
    target = os.path.join(dst, name)
    if os.path.exists(target):
        shutil.rmtree(target)
    if "--remove" in sys.argv:
        print(f"removed /{name}")
        continue
    shutil.copytree(os.path.join(src, name), target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"installed /{name} -> {target}")
if "--remove" not in sys.argv:
    print("Restart Claude Code to use /pause and /savings.")
