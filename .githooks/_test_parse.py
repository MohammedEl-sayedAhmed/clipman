#!/usr/bin/env python3
"""TSV parser for the test harness — emits one TAB-delimited row per case.

The `input` field can contain literal newlines (commit messages with bodies);
we encode them as `\n` so a single `read -r` line keeps the whole record.
The shell-side `decode_input` reverses this with `printf %b`.
"""

import json
import sys


def encode(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\t", " ").replace("\n", "\\n")


def main(path: str) -> int:
    with open(path) as f:
        data = json.load(f)
    for i, t in enumerate(data):
        cols = [
            str(i),
            t["category"],
            t["expected_outcome"],
            encode(t["reason"]),
            encode(t["input"]),
        ]
        print("\t".join(cols))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
