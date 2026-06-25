---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 7. In-app update-availability notifications

## Context

Clipman ships through five channels: PyPI, source / `install.sh`,
Snap, AUR, `.deb`/`.rpm` artifacts on the GitHub Release page, plus
the GNOME Extensions website (extension only). The Snap Store
auto-refreshes installed snaps; the others require the user to pull
updates manually. Today there is **no signal inside the running app**
that a new release exists — users discover updates only by visiting
GitHub, the AUR, or PyPI on their own initiative.

We want a low-friction, privacy-respecting nudge: when a newer
release is published, the running daemon should surface a small
in-app indicator the next time the user opens the popup. Concretely:

- *No telemetry.* The check must not send any user data, identifiers,
  cookies, or anything beyond what an anonymous web visitor would
  fetch.
- *No auto-update.* We notify and link; we don't download or install.
- *Opt-out friendly.* Snap users in particular don't need this — the
  Snap Store already refreshes installed snaps — so it should default
  off there. The same default applies if a Flatpak install ever exists
  (`$FLATPAK_ID` set), since a Flatpak-hosting store would refresh on
  its own.
- *No new system dependency.* The daemon must do this with what's
  already installed (Python 3.10+, stdlib).

## Decision

Implement a self-contained checker in `clipman/updates.py`:

- Reads `clipman.__version__` (new constant in `clipman/__init__.py`,
  matched to `pyproject.toml` by `scripts/bump-version.sh`).
- Performs an anonymous `GET
  https://api.github.com/repos/MohammedEl-sayedAhmed/clipman/releases/latest`
  with a `User-Agent: clipman/<version>` header and a 5-second
  timeout, using `urllib.request` from the stdlib.
- Parses the JSON, compares `tag_name` to `__version__` via
  `packaging.version.parse` when available, falling back to a tuple-
  of-ints comparator. Stores the result in the existing `settings`
  table under four keys: `check_for_updates`, `last_update_check`,
  `latest_known_version`, `dismissed_version`.

The daemon (`clipman/app.py`) schedules an initial check at +30s
after startup (so it doesn't slow login) and a recurring 24-hour
tick via `GLib.timeout_add_seconds`. The check runs on a background
`threading.Thread`; its callback is marshalled back to the GTK main
loop via `GLib.idle_add` so the UI never touches threading
primitives.

The UI (`clipman/window.py`) gains:

- A "Updates" row in the settings panel with a status label
  ("up to date" / "v1.0.5 available" / "(disabled)"), a Switch for
  opt-in/out, and a "Check now" button.
- A dismissible banner at the top of the popup, shown when
  `latest_known_version > __version__` and is not equal to
  `dismissed_version`. Clicking "Release notes" opens the GitHub
  release page in the default browser via `webbrowser.open`; the `×`
  writes `dismissed_version` so the banner stays gone for that
  specific version.

Per-install defaults: `check_for_updates` starts ON for
source / PyPI / AUR installs (`install_kind() == 'other'`) and OFF
for `$SNAP` / `$FLATPAK_ID` installs whose package manager already
auto-refreshes.

Snap's strict confinement blocks outbound HTTP by default, so
`snap/snapcraft.yaml` gains a `network` plug. Snap installs still
default OFF, but the plug is needed for the opt-in case (a user who
wants Clipman to also nudge them even though snap is refreshing).

## Consequences

**Positive**

- Source / PyPI / AUR users get a visible nudge inside Clipman
  itself — no out-of-band channel needed.
- Privacy posture is documentable in one paragraph: anonymous GET,
  no body, no params, no cookies, no analytics.
- Stdlib-only — no new pinned dependency surface.
- Opt-out is a single Switch; dismissal is per-version so the banner
  doesn't nag for a release the user has chosen to skip.

**Negative**

- Anonymous GitHub API has a 60-req/h IP-based rate limit. At one
  check per day per daemon this is irrelevant, but a misbehaving
  install of Clipman on a NATed network could share a budget. The
  24-hour rate limit in `should_check_now` makes that benign.
- Snap users who keep the default (off) and reinstall the snap won't
  know if there's a new clipman release outside the snap track; this
  is acceptable because they get their updates via the Snap Store.
- Adding `network` plug to the snap requires another manual review
  by the Snap Store team (one-time) before the next snap release.

## References

- Plan file: `~/.claude/plans/memoized-inventing-hopper.md`
- ADR 0003 (SHA-pin GitHub Actions) — referenced for the bump-script
  symmetry: `scripts/bump-version.sh` now also rewrites
  `clipman/__init__.py`.
