# Local git hooks

This repo ships **opt-in** local git hooks at [`.githooks/`](../.githooks/)
that catch two specific classes of mistake before they leave the
maintainer's machine:

1. **Wrong-account commits/pushes** — the maintainer has multiple GitHub
   logins on one machine; the hooks refuse commits whose git identity
   is not on a personal allowlist.
2. **AI-tool footprints** — Claude/Anthropic attributions, robot emojis,
   `Co-Authored-By: Claude`, "Generated with Claude Code", etc.

`scripts/dev-setup.sh` installs them in every clone. The footprint checks
(2) apply to everyone: this project keeps AI-tool attribution out of its
history, and CI enforces the same rule on every pull request (see
[Pull requests](#pull-requests)). The account checks (1) run only in the
maintainer's own clone and never question a contributor's name, email,
fork, or co-authors.

## Install

From the repo root:

```sh
scripts/install-hooks.sh
```

This sets `git config core.hooksPath .githooks` for the current clone
only — no global side effects, no dependencies installed. Re-running is
idempotent.

## Maintainer mode

The account checks (1) only make sense in the maintainer's clone, so the
hooks run in one of two modes:

- **Maintainer mode:** every check below.
- **Contributor mode:** only the footprint and trailer checks. Your own
  name, email, fork, and co-authors are never questioned.

`install-hooks.sh` picks the mode from the clone's git identity: an
identity on the allowlist means maintainer mode, any other identity
contributor mode. Pass `--maintainer` or `--contributor` to choose, or
change it later:

```sh
git config clipman.hooks.maintainer true    # or false
```

When the setting is missing (no git identity at install time, or a clone
set up before the setting existed), a clone whose `origin`, as configured,
belongs to an allowlisted account counts as the maintainer's.

## Pull requests

The `Footprints` workflow (`.github/workflows/footprints.yml`) runs
`scripts/check-footprints.sh` on every pull request. It uses the same
checks as the hooks (`scan_commit_content` in `.githooks/_lib.sh`) on each
commit's trailers, message and added lines, and also scans the pull
request's title and description. The description of a pull request
opened by a bot is skipped, because Dependabot quotes upstream release
notes. It never looks at who you are. So the rule holds even for someone
who never installed the hooks or skipped them with `--no-verify`.

## What gets checked

| Hook | When it runs | What it does |
|---|---|---|
| `commit-msg` | After you save the commit message | Scans the message for AI footprints (Claude/Anthropic/🤖). Rejects trailers (`Co-Authored-By:`, `Signed-off-by:`, …) from an AI-assistant vendor domain, or that borrow an allowlisted handle on an address that doesn't back it up. Everyone else's trailers pass. |
| `pre-commit` | Before the commit-msg editor opens | Scans the **added** lines in your staged diff for footprints. In maintainer mode, also compares your active git identity (config, env vars, `GIT_AUTHOR_IDENT`) against the allowlist. |
| `pre-push` | Before commits leave the machine | Scans each commit being pushed (trailers, message, added lines). In maintainer mode, also checks each commit's author and committer, refuses a push whose real destination belongs to an account outside the allowlist, and refuses when the `gh` CLI's active account is outside it. |

The push check looks at the URL the push actually goes to, after any
`insteadOf` / `pushInsteadOf` rewrite. Rewrite rules for other hosts (a
work GitLab, say) never affect it.

## The allowlist

Default allowed account name:

- `MohammedEl-sayedAhmed`

Override with an env var (one-off or via shell rc):

```sh
export CLIPMAN_HOOKS_ALLOW="MohammedEl-sayedAhmed another-account"
```

Git identities and gh logins match by case-insensitive substring. A push
URL's owner segment must match exactly, so a repo named
`MohammedEl-sayedAhmed-mirror` under another account does not pass.

## Bypass

Genuine emergencies only:

```sh
git commit --no-verify         # skip commit-msg + pre-commit
git push   --no-verify         # skip pre-push
```

## Uninstall

```sh
git config --unset core.hooksPath
```

The `.githooks/` directory stays in place (it's tracked); you just stop
pointing git at it.

## How it stays in sync

`core.hooksPath` points at the **tracked** `.githooks/` directory. When
you `git pull` updates to the hook scripts, your installed hooks update
automatically. No re-install needed.

## Testing the hooks

```sh
scripts/dev.sh hooks-test      # or: .githooks/_test.sh
```

The corpus (`.githooks/_test_corpus.json`) lists real footprint patterns,
adversarial edge cases, and outside contributors' commits. A case that is
a commit message runs through the real `commit-msg` hook. A case that
describes a clone (identity, `gh` login, URL rewrites, mode) runs through
the real `pre-commit` and `pre-push` hooks in a throwaway repo, with a
temporary HOME so your own git settings never affect the result. Every
commit-message case also becomes a real commit for
`scripts/check-footprints.sh`, which must reach the same verdict as
`commit-msg`, so the local hooks and the pull-request check never drift
apart. Unit tests for the identity and push-URL matching follow. CI runs
the whole suite on every pull request.

## Known limitations

These hooks defend against **accidental** mistakes (wrong active account,
Claude Code's emitted footprint slipping into a commit). They are **not**
adversarial defenses. A user who *wants* to bypass can always do so:

- `git commit --no-verify` / `git push --no-verify`
- `git config --unset core.hooksPath`
- Submitting via GitHub web UI or `gh pr merge` — those paths never invoke
  the local pre-push hook
- Unicode obfuscation in commit messages — zero-width spaces in `Claude` /
  `anthropic` are stripped before scanning, but homoglyphs (Cyrillic `С`,
  Greek `ο`, accented Latin `ą`) defeat the ASCII regex set
- A footprint added to a `*.bin` or other binary file (the pre-commit
  staged-diff scan reads text-only diffs)

Why this is fine: the hooks are for **the maintainer's own** workflow.
The maintainer isn't trying to outwit themselves. Claude Code emits a
specific, plain-ASCII footprint (`Co-Authored-By: Claude
<noreply@anthropic.com>`, `Generated with [Claude Code](...)`, 🤖) — the
hooks catch that.

## What runs where

| Check | Local hooks | CI (every pull request) |
|---|---|---|
| AI-tool footprints: messages, trailers, added lines | Yes, every clone | Yes (`Footprints`) |
| Footprints in the pull request title and description | — | Yes (`Footprints`) |
| Git identity, push URL, gh account, commit authors | Maintainer's clone only | Never |

The footprint rule is the project's own rule (AGENTS.md), so it applies
to every contributor, and CI makes sure of it. The local hooks catch the
same things earlier, before anything leaves the machine. The account
checks exist only to stop the maintainer pushing from the wrong account,
so they never gate anyone else's pull request. CI also runs the hooks'
own test suite, which checks the hook code.
