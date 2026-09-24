---
status: Accepted
date: 2026-09-14
deciders: MohammedEl-sayedAhmed
---

# 11. Versioning policy refresh (supersedes ADR 0010)

## Context

ADR 0010 recorded the SemVer policy. The policy itself has held up, but
four of the facts it rests on were already stale when it was written or
have changed since:

- It gives the support window as Ubuntu 22.04+. The baseline is Ubuntu
  24.04+ for libadwaita 1.5. `README.md`, `docs/development.md` and the
  preflight error in `clipman/cli.py` all say so.
- It calls the toolkit GTK3 and lists the move to GTK4 as a future MAJOR
  trigger. The app has been GTK 4 + libadwaita since 1.1.0;
  `clipman/app.py` and `clipman/window.py` require Gtk 4.0, Adw 1 and
  Gdk 4.0.
- It says `scripts/bump-version.sh` rewrites `clipman/__init__.py`. The
  version literal moved to `clipman/_version.py` to break a CodeQL
  `py/cyclic-import`, and the script patches that file.
- Its D-Bus contract list covers two of the extension's four methods.
  `RestorePreviousFocus()` and `SetPaused(b paused)` are missing.

An Accepted ADR is not edited in place, so this record supersedes 0010
rather than correcting it.

## Decision

The SemVer 2.0.0 policy in ADR 0010 stands unchanged, including its
MINOR and PATCH triggers, the settings-key migration rule and the
no-public-Python-API caveat. Its factual premises are restated here.

**Support window.** Python 3.10 to 3.14, GNOME Shell 45 to 51 through
the bundled extension, app baseline Ubuntu 24.04+ with GNOME 46,
Wayland only. `requires-python` stays open at the top end so a newer
interpreter is not refused at install time; the classifiers name the
versions CI actually tests.

**Toolkit.** GTK 4 with libadwaita 1.5+. A future toolkit jump is still
a MAJOR trigger; the GTK3 to GTK4 trigger named in ADR 0010 is spent.

**D-Bus contract, in full.** Removing or renaming any of these, or
changing a signature without a compatibility shim, is a MAJOR trigger.

| Bus name | Object path | Methods |
|----------|-------------|---------|
| `com.clipman.Daemon` | `/com/clipman/Daemon` | `Toggle()`, `Show()`, `Hide()`, `Quit()`, `NewEntry(ss)` |
| `org.gnome.Shell.Extensions.clipman` | `/org/gnome/Shell/Extensions/clipman` | `SimulatePaste(s mode)`, `MoveWindowToCursor(s title)`, `RestorePreviousFocus()`, `SetPaused(b paused)` |

**Version-bearing files.** `scripts/bump-version.sh` rewrites
`pyproject.toml`, `clipman/_version.py`, `snap/snapcraft.yaml`,
`flathub/*.json`, `aur/PKGBUILD`, `CITATION.cff`, and adds a `<release>`
entry to `data/*.metainfo.xml`. The release workflow's pre-flight step
checks every one of them against the tag, and also requires a matching
`CHANGELOG.md` section. `extension/metadata.json` is deliberately left
alone: its integer counts the extension D-Bus contract, not the product
version.

## Consequences

**Positive**

- The policy names contracts that exist, so a packager reading it alone
  cannot miss two extension methods.
- The file list matches the script and the pre-flight check, so a
  release cannot quietly skip `CITATION.cff` or the AppStream metainfo.
- The support window matches the CI matrix and the code's own preflight.

**Negative**

- Two records now describe one policy. ADR 0010 stays on disk as the
  historical version, and a reader has to follow the supersession link.

## References

- ADR 0010 — Versioning policy, superseded by this record.
- ADR 0005 — Encode paste keystroke choice as a D-Bus argument.
- `scripts/bump-version.sh` and the pre-flight step in
  `.github/workflows/release.yml` are the sources for the file list.
