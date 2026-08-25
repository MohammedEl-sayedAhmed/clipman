# Agent & contributor working guide

Conventions for working on clipman with any AI coding assistant (or by
hand). Everything here was learned the hard way; follow it and the repo's
automation stays quiet. Tool-agnostic on purpose — nothing below assumes a
specific assistant.

## Identity & attribution — hard rules

- All git/GitHub actions (commits, pushes, PRs, issues, reviews) are made
  as **MohammedEl-sayedAhmed**. A local pre-push hook enforces an identity
  allowlist; never bypass it or act under any other account.
- **No AI attribution anywhere**: no `Co-Authored-By:` lines for bots or
  assistants, no "Generated with …" trailers, no robot emojis in commits,
  PRs, or issues. If one slips in, amend before pushing.
- Never reference private, client, or employer projects in code, comments,
  commits, PRs, or docs. Describe borrowed patterns generically.

## Git workflow

- `git fetch origin --prune` **before any base-vs-branch operation**
  (rebase, merge, PR status check). `main` moves fast via daily bots;
  branch protection requires branches to be up to date, so serial PRs are
  the norm: merge one, pull, rebase/branch the next.
- **One clean commit per PR.** Verify locally before pushing; amend fixups
  into the single commit rather than pushing then patching. Never push a
  commit you haven't verified ("no broken-commit spam").
- Squash-merge PRs once checks pass, then pull main and continue. Merged
  head branches auto-delete (`delete-merged-branch.yml`).
- Dependabot PRs that fall behind: comment `@dependabot recreate`
  (cleaner than `rebase`).
- Code-scanning (GHAS) review threads on a PR must be handled **before
  merge**: reply, resolve the thread, dismiss the underlying alert.
- When a PR addresses an existing issue, also comment on the issue with
  the PR link and a one-line summary.
- `clipman/window.py` is the god-file; serialize PRs that touch it.
- For non-trivial work: write a rigorous plan and get maintainer alignment
  **before** executing; then implement in self-verifying loops (verify each
  step actually works before moving on). Consolidate fixes that can only be
  verified on real hardware/Wayland into a single PR so the maintainer
  tests once.

## Verification recipes

- Use the **system Python** (`/usr/bin/python3`) — project venvs lack the
  `gi` bindings.
- Full suite: `CLIPMAN_REQUIRE_GTK4=1 xvfb-run -a /usr/bin/python3 -m pytest -q`
  (CI equivalent: `xvfb-run -a python -m unittest discover -s tests`).
- Lint scope matches CI exactly: `ruff check clipman tests`.
- Headless visual checks: `xvfb-run -a /usr/bin/python3 scripts/screenshot.py`
  renders the real window/preferences to PNG. Caveat: `Adw.Dialog` content
  can't be captured through the xvfb harness ("empty render node") — snapshot
  the dialog's child widget, or verify on a real display.
- The CodeQL **security-baseline gate** fails PRs on *new* findings —
  historically `py/empty-except`, `py/multiple-definition`,
  `py/implicit-string-concatenation-in-list`,
  `py/returning-tuples-with-varying-lengths`, `py/cyclic-import`. Write
  around these proactively (e.g. sentinel objects instead of
  variable-shape returns, `+`-concatenation instead of implicit string
  juxtaposition in lists).
- GTK CSS is not web CSS: no `:empty`, no `text-transform`. A bad selector
  aborts the whole stylesheet at runtime (theme-parser error), which CI
  won't catch — screenshot-verify CSS changes.

## Platform gotchas (Wayland/GNOME)

- Mutter has **no virtual-keyboard protocol**: `wtype` cannot inject keys.
  Paste simulation goes through the GNOME Shell extension's Clutter virtual
  device (`SimulatePaste` over D-Bus).
- A background daemon **cannot set the Wayland clipboard** via
  `Gdk.Clipboard.set()` (needs an input-focus serial). Use `wl-copy`
  (transient surface + persistent fork) instead.
- Only the Shell can focus/refocus windows on Wayland: window activation,
  focus restore, and dash/alt-tab hiding all route through the extension.
- On GNOME 49+ `Meta.Window.hide_from_window_list()` is real API (the code
  feature-detects it); before 49 the extension monkey-patches the tab-list /
  app-list functions instead.

## Design source of truth

- The UI must match the mockups in `docs/design/` (`main-window.html`,
  `preferences.html`, `states.html`) with tokens in
  `docs/design/tokens.css`. Dark palette: Catppuccin Mocha; light palette:
  "warm stone" (deliberately *not* Catppuccin Latte — its muted text fails
  WCAG AA on white). Check contrast (4.5:1 text, 3:1 large/graphical)
  before shipping color changes.
- Colors flow through `@define-color` tokens injected by `window.py`
  (`@clip_dim`, `@type_*`, accent overrides) — never hardcode a hex in
  `style.css` when a token exists.
- Prefer inline **Mermaid** diagrams (rendered natively on GitHub) in PRs,
  issues, and docs.

## Release chain (v-tag driven)

1. `scripts/bump-version.sh <ver>` updates pyproject, `_version.py`, snap,
   flathub, AUR, `CITATION.cff`.
2. Update `CHANGELOG.md` (rename `[Unreleased]` → `[<ver>] - <date>`).
3. Release PR → squash-merge.
4. **Create the tag via the GitHub API** (`gh api .../git/refs`), not
   `git push --tags`: the identity pre-push hook rejects tags pointing at
   GitHub's squash commits.
5. The tag triggers `release.yml`: PyPI (OIDC), Snap Store, AUR push,
   GitHub Release marked Latest.
6. **extensions.gnome.org has no publish API** — if `extension/` changed,
   bump the integer `version` in `extension/metadata.json` (mandatory for
   any e.g.o. upload; stale versions serve stale code) and upload the zip
   manually at https://extensions.gnome.org/upload/ (listing 9407, UUID
   `clipman@clipman.com`). Zip layout: `extension.js` + `metadata.json` at
   the archive root.
7. PyPI/store pages render the **README snapshot from the release** —
   README fixes reach PyPI only via the next release.
8. Snap Store security emails ("built with packages that have since
   received security updates", USN-…) are resolved by any rebuild and
   now **self-heal**: the weekly `snap-refresh` cron rebuilds every
   published channel (stable/candidate/beta from the latest release
   tag, edge from main — never publish a main build to stable, it
   would leak unreleased code). The snap uses `extensions: [gnome]`,
   so the GTK stack (and its libcurl-via-libappstream tail, the old
   recurring offender) lives in Canonical's gnome-46-2404 content snap
   and is off our scan surface entirely; only `wtype` (+ wl-clipboard,
   built from source) is ours. For an immediate fix, dispatch
   `snap-refresh.yml` with the target channel — the channel choice
   picks the right source ref automatically.

## Bots & automation

- `refresh-numbers.yml` (daily 06:00 UTC + on push to its own paths)
  refreshes marketing counters, the self-hosted star-history SVGs, and the
  downloads history, then opens an auto-merge PR. Its outputs are
  **deterministic on unchanged inputs** — keep them that way or the bot
  opens junk PRs every day.
- The bot authenticates with the `NUMBERS_TOKEN` fine-grained PAT (falls
  back to `GITHUB_TOKEN`). Reason: GitHub never triggers workflows for
  events made with the default `GITHUB_TOKEN`, so bot-opened PRs would get
  zero required checks and stall forever. If the PAT expires, that exact
  symptom returns (numbers PR stuck `BLOCKED`, "no checks reported");
  fallback unblock: re-author the head commit under the maintainer's
  identity and force-push.
- Numbers can legitimately *decrease* (PyPI mirrors, deleted stars);
  don't treat a small dip as a bug.
- The star chart is self-hosted (`scripts/refresh_stats.py` →
  `docs/assets/star-history-*.svg`) because star-history.com's public
  embed rate-limits (503) behind GitHub's camo proxy. Don't reintroduce
  the external embed.

## Support window

Python 3.10–3.12 · GNOME Shell 45–50 (app baseline: Ubuntu 24.04+/GNOME 46)
· Wayland-native. Keep README badges, `README` requirements,
ADR-0010, `SECURITY.md`, and `extension/metadata.json` in agreement when
this changes.
