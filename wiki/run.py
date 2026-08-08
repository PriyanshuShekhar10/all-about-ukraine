#!/usr/bin/env python3
"""Orchestrate the wiki pipeline end-to-end.

Runs: gather -> synthesize -> resolve_links -> export, over a batch of terms.
Idempotent (skips work by status). Repeat to grow the wiki (red links get
queued by resolve_links each pass).

Usage:
    python wiki/run.py --limit 25        # process up to 25 new terms this pass
    python wiki/run.py --limit 25 --passes 3
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, str(HERE / script), *args]
    print(f"\n$ {' '.join(cmd[1:])}")
    result = subprocess.run(cmd, cwd=HERE)
    if result.returncode != 0:
        raise SystemExit(f"{script} failed with code {result.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25, help="terms per pass")
    ap.add_argument("--passes", type=int, default=1, help="growth passes")
    args = ap.parse_args()

    for p in range(1, args.passes + 1):
        print(f"\n===== PASS {p}/{args.passes} =====")
        run("gather.py", "--limit", str(args.limit))
        run("synthesize.py", "--limit", str(args.limit))
        run("resolve_links.py")
        run("export.py")
    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
