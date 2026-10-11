#!/usr/bin/env python3
"""Write the contributors list in README.md from the merged pull requests.

Lists everyone whose pull request was merged, oldest first, with their
avatar, their name and links to those pull requests. It lists people
only: the maintainer, bots and AI tools are never listed (see
``is_listed``).

Run it after a first-time contributor's pull request is merged:

    python3 scripts/contributors.py          # rewrite the README list
    python3 scripts/contributors.py --check  # exit 1 if it is out of date

Only the text between the contributors markers changes, and nothing is
written when the GitHub API cannot be read. Uses GH_TOKEN or
GITHUB_TOKEN when set; the anonymous rate limit is enough without one.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "MohammedEl-sayedAhmed/clipman"
OWNER = REPO.split("/", 1)[0]
API = "https://api.github.com"
README = Path(__file__).resolve().parent.parent / "README.md"
START = "<!-- contributors:start -->"
END = "<!-- contributors:end -->"
UA = f"clipman-contributors/1.0 (+https://github.com/{REPO})"

# Logins never listed, in lower case: people who asked to be left out.
# "ghost" is the account GitHub shows for deleted users.
EXCLUDE = frozenset({"ghost"})
# A login containing one of these belongs to an AI tool, not a person.
AI_WORDS = ("claude", "anthropic", "copilot", "openai", "chatgpt")
PER_ROW = 6
AVATAR_PX = 80
# A person with more merged pull requests gets one link to all of them.
MAX_PR_LINKS = 3


def is_listed(user):
    """True when ``user`` (a GitHub API user object) may be listed."""
    login = (user.get("login") or "").lower()
    if not login or user.get("type") != "User" or login.endswith("[bot]"):
        return False
    if login == OWNER.lower() or login in EXCLUDE:
        return False
    return not any(word in login for word in AI_WORDS)


def collect(pulls):
    """People with a merged pull request, ordered by their first one.

    ``pulls`` are pull request objects from the GitHub API. Each person
    is a dict with ``login``, ``id`` and ``prs``, their sorted numbers.
    """
    people = {}
    for pull in pulls:
        user = pull.get("user") or {}
        if not pull.get("merged_at") or not is_listed(user):
            continue
        person = people.setdefault(
            user["id"], {"login": user["login"], "id": user["id"], "prs": []}
        )
        person["prs"].append(pull["number"])
    for person in people.values():
        person["prs"].sort()
    return sorted(people.values(), key=lambda person: person["prs"][0])


def _work(person):
    """Links to a person's merged pull requests."""
    login = html.escape(person["login"])
    prs = person["prs"]
    if len(prs) > MAX_PR_LINKS:
        return (f'<a href="https://github.com/{REPO}/pulls?q=is%3Apr'
                f'+is%3Amerged+author%3A{login}">{len(prs)} pull requests</a>')
    links = ", ".join(
        f'<a href="https://github.com/{REPO}/pull/{number}">#{number}</a>'
        for number in prs
    )
    return ("Pull request " if len(prs) == 1 else "Pull requests ") + links


def _cell(person):
    login = html.escape(person["login"])
    name = html.escape(person.get("name") or person["login"])
    avatar = (f"https://avatars.githubusercontent.com/u/{person['id']}"
              f"?v=4&amp;s={AVATAR_PX * 2}")
    return (
        f'<td align="center" valign="top" width="{100 / PER_ROW:.2f}%">'
        f'<a href="https://github.com/{login}">'
        f'<img src="{avatar}" width="{AVATAR_PX}" height="{AVATAR_PX}" '
        f'alt="{name}"/><br/><b>{name}</b></a><br/>'
        f"<sub>{_work(person)}</sub></td>"
    )


def render_block(people):
    """The HTML that goes between the README markers."""
    if not people:
        return "<p>No outside contributions yet.</p>"
    rows = []
    for i in range(0, len(people), PER_ROW):
        cells = "\n    ".join(_cell(person) for person in people[i:i + PER_ROW])
        rows.append(f"  <tr>\n    {cells}\n  </tr>")
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def replace_block(text, block):
    """``text`` with the part between the markers replaced by ``block``,
    or None unless it has exactly one start marker before one end
    marker."""
    start, end = text.find(START), text.find(END)
    if text.count(START) != 1 or text.count(END) != 1 or end < start:
        return None
    return text[:start + len(START)] + "\n" + block + "\n" + text[end:]


def _get_json(url):
    """The decoded JSON at ``url``, or None when it cannot be read."""
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    credential = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    request = urllib.request.Request(url, headers=headers)
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            error = exc
            time.sleep(2 * (attempt + 1))
    print(f"Could not read {url}: {error}", file=sys.stderr)
    return None


def fetch_pulls():
    """Every closed pull request, or None when the API cannot be read."""
    pulls, page = [], 1
    while True:
        batch = _get_json(f"{API}/repos/{REPO}/pulls?state=closed"
                          f"&sort=created&direction=asc&per_page=100&page={page}")
        if not isinstance(batch, list):
            return None
        pulls += batch
        if len(batch) < 100:
            return pulls
        page += 1


def add_names(people):
    """Give each person their profile name, or their login when it has
    none. Return False when a profile cannot be read."""
    for person in people:
        user = _get_json(f"{API}/users/{person['login']}")
        if not isinstance(user, dict):
            return False
        person["name"] = (user.get("name") or "").strip() or person["login"]
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when README.md is out of date; change nothing")
    args = parser.parse_args(argv)

    pulls = fetch_pulls()
    people = collect(pulls) if pulls is not None else None
    if people is None or not add_names(people):
        print("README.md was left as it is.", file=sys.stderr)
        return 2
    text = README.read_text(encoding="utf-8")
    new = replace_block(text, render_block(people))
    if new is None:
        print(f"README.md needs one {START} and one {END} line.",
              file=sys.stderr)
        return 2
    if new == text:
        print(f"README.md is up to date: {len(people)} contributors.")
        return 0
    if args.check:
        print("README.md is out of date: run scripts/contributors.py.",
              file=sys.stderr)
        return 1
    README.write_text(new, encoding="utf-8")
    print(f"README.md updated: {len(people)} contributors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
