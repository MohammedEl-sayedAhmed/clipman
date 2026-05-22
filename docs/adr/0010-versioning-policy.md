---
status: Accepted
date: 2026-05-22
deciders: MohammedEl-sayedAhmed
---

# 10. Versioning policy

## Context

Clipman has shipped through eight 1.0.x releases on PyPI, Snap, AUR,
and the GitHub Releases page (`.deb` / `.rpm` / AppImage artifacts),
plus an out-of-band cadence for the GNOME Shell extension on
extensions.gnome.org. (Flathub is not a current channel — a manifest
is kept under `flathub/` for possible future use, but there is no
submission in flight.) Until now the meaning of each version bump has
lived only in the maintainer's head and in the release-checklist
prose. That worked while the public surface was small, but it has
grown:

- Two D-Bus interfaces with explicit contracts — `com.clipman.Daemon`
  at `/com/clipman/Daemon` (methods: `Toggle`, `Show`, `Hide`, `Quit`,
  `NewEntry(ss)`) and `org.gnome.Shell.Extensions.clipman` at
  `/org/gnome/Shell/Extensions/clipman` (methods: `SimulatePaste(s mode)`,
  `MoveWindowToCursor(s title)`).
- A SQLite database at `~/.local/share/clipman/clipman.db` (WAL mode)
  with a `settings` table whose keys (e.g. `check_for_updates`,
  `last_update_check`, `latest_known_version`, `dismissed_version` —
  see ADR 0007) are read by both the daemon and any future external
  tooling.
- A documented support window: Python 3.10–3.12, GNOME Shell 45–48,
  Ubuntu 22.04+.
- A toolkit choice (GTK3) that downstream packagers depend on.

Without a written policy, downstreams (AUR, Snap, distro packagers,
plus any future Flathub submission) cannot tell from a tag alone
whether a release will require a rebuild against new system libraries,
a schema migration, or a new extension version. They also cannot tell whether the extension's
`metadata.json` `version` integer — bumped 4→5 in ADR 0005 — is the
same concept as the product's tag, which it is not.

## Decision

Adopt [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
for the product tag `vX.Y.Z`, with the trigger list below tailored to
clipman's specific public surface.

**MAJOR (`X` bump) — backward-incompatible change to a public contract:**

- Removing or renaming any method on `com.clipman.Daemon`
  (`Toggle`, `Show`, `Hide`, `Quit`, `NewEntry`) or on
  `org.gnome.Shell.Extensions.clipman` (`SimulatePaste`,
  `MoveWindowToCursor`). Changing the signature of an existing method
  without a compatibility shim also counts.
- A SQLite schema change in `~/.local/share/clipman/clipman.db` that
  has no auto-migration path on first launch of the new daemon.
- Dropping a supported Python version (e.g. dropping 3.10).
- Dropping a supported GNOME Shell version from the documented range.
- Renaming a settings key in the SQLite `settings` table without a
  backward-compatible read shim that maps the old name to the new one.
- Relocating the data directory `~/.local/share/clipman/` to a
  different path without a one-shot migration on startup.
- Switching the GTK toolkit (currently GTK3 — chosen for Ubuntu 22.04+
  compatibility — to GTK4).

**MINOR (`Y` bump) — additive, backward-compatible change:**

- Adding a new method to either D-Bus interface, or adding an optional
  argument behind a try-with-arg / retry-without-arg fallback. This
  follows the precedent in ADR 0005, where `SimulatePaste()` gained an
  `s mode` argument and the daemon shipped a `try / except
  DBusException` retry with the old no-argument signature. The
  extension's `metadata.json` `version` integer bumped 4→5 (its own
  contract counter for downstream consumers), but the product tag was
  still a MINOR bump because daemons paired with an unupgraded v4
  extension kept working.
- Adding a new settings key with a sensible default for callers that
  don't write it.
- New user-visible features (UI rows, keystroke recipes, etc.) that
  don't touch the contracts above.
- Acceptance into a new install channel (e.g. Flathub stable) where
  the channel's presence is itself a user-visible feature.

**PATCH (`Z` bump) — no change to any public contract:**

- Bug fixes.
- Internal refactors of `clipman/database.py`, `clipman/window.py`,
  `clipman/dbus_service.py`, etc. that don't change observable
  behavior on the contracts.
- Dependency bumps with no surface change (most Dependabot PRs).
- Docs, CI, packaging-script changes that don't ship code changes to
  users.

**The extension's `metadata.json` `version` integer is a separate
concept** from the product tag. It is the extension's D-Bus contract
version, intended for downstream consumers of the
`org.gnome.Shell.Extensions.clipman` interface, and is bumped on
D-Bus contract changes only. It is monotonically increasing but
unrelated to product SemVer — see ADR 0005.

**No-public-Python-API caveat:** clipman is an end-user application.
The only public contracts that this policy covers are:

1. The two D-Bus interfaces above.
2. The SQLite `settings` table keys.
3. The on-disk data directory layout at `~/.local/share/clipman/`.

Internal Python modules (`clipman.database`, `clipman.window`,
`clipman.app`, `clipman.dbus_service`, `clipman.updates`, etc.) are
**not** a public API. They may change in any release, including
PATCH, without a deprecation cycle. Users who import clipman as a
library do so at their own risk.

## Consequences

**Positive**

- Downstream packagers can predict from a tag alone whether a rebuild
  needs a schema-migration test pass, an extension refresh, or a
  toolkit jump.
- The tag scheme stays `vX.Y.Z` — no change to `git tag`, GitHub
  Releases, or the install channels — so existing tooling
  (`scripts/bump-version.sh`, the release workflows, `update-aur.sh`)
  continues to work unchanged. `scripts/bump-version.sh X.Y.Z` keeps
  rewriting `pyproject.toml`, `snap/snapcraft.yaml`, `flathub/*.json`,
  `aur/PKGBUILD`, and `clipman/__init__.py` in lockstep.
- The release-checklist and maintaining flow stay unchanged; this ADR
  just documents which of MAJOR / MINOR / PATCH applies to a given
  diff before the bump happens.

**Negative / trade-offs**

- A future MAJOR is now a documented event, not a quiet bump. The
  next time a trigger above fires, a new ADR has to spell out the
  break, the migration story, and the supersession of any older
  decision.
- Renaming a settings key now has a real cost: the read shim has to
  live for at least one MINOR cycle before the old name can be
  retired in the next MAJOR.
- The extension's `version` integer and the product tag will keep
  drifting apart over time. This is intentional but means release
  notes have to call out the extension version explicitly whenever it
  bumps.

## References

- [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
- ADR 0005 — Encode paste keystroke choice as a D-Bus argument
  (precedent for try-with-arg / retry-without-arg as a MINOR-grade
  compatibility shim).
- ADR 0007 — In-app update-availability notifications (introduced
  the four `check_for_updates` / `last_update_check` /
  `latest_known_version` / `dismissed_version` settings keys this
  policy now covers).
- `scripts/bump-version.sh` — single source of truth for cross-file
  version consistency.
