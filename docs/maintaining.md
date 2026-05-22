# Maintaining clipman

Counterpart to `CONTRIBUTING.md` (contributor view). This doc is the
governance/process view for whoever holds the maintainer commit bit —
how releases are cut, which versions stay supported, how user-facing
surfaces are deprecated, and how settings-table migrations are
sequenced across MINOR series.

## Release procedure

Cutting a release is a short, mostly mechanical sequence. The literal
step-by-step commands live in `docs/release-checklist.md` — that is the
runbook. This section is the higher-level shape of the workflow so a
new maintainer knows what they are about to invoke.

- Bump every version-bearing file in lockstep with
  `scripts/bump-version.sh X.Y.Z`. The script rewrites `pyproject.toml`,
  `snap/snapcraft.yaml`, `flathub/*.json`, `aur/PKGBUILD`, and
  `clipman/__init__.py` in a single pass so no channel drifts.
- Promote the `[Unreleased]` block in `CHANGELOG.md` to
  `[X.Y.Z] - YYYY-MM-DD` and add a fresh empty `[Unreleased]` block on
  top.
- Commit the bump, push `main`, then create and push the `vX.Y.Z` tag.
  The tag push is the trigger.
- `.github/workflows/release.yml` fires on the tag and, as of v1.0.6+,
  publishes to PyPI, the Snap Store `stable` channel, AUR, and the
  GitHub Release end-to-end. AUR publication was wired in with PR #39
  ("ci(release): auto-publish to AUR on tag push") on top of the AUR
  packaging refresh and `scripts/update-aur.sh` helper introduced in
  PR #38.
- The GNOME Extensions website upload at
  https://extensions.gnome.org/upload/ is the one step that remains
  manual — EGO has no programmatic upload API. Grab the
  `clipman-extension-vX.Y.Z.zip` asset off the new GitHub Release and
  upload it by hand.

Per-channel auth, so you know what to rotate when something expires:

- **PyPI** — OIDC trusted publishing, no token stored. The trusted
  publisher binding (project `clipman-clipboard`, workflow
  `release.yml`, environment `pypi`) is configured once per ADR 0004
  (`docs/adr/0004-pypi-trusted-publishing.md`).
- **Snap Store** — `SNAPCRAFT_STORE_CREDENTIALS` repository secret.
  Token expires yearly; the Snap Store emails a reminder roughly 30
  days out.
- **AUR** — an SSH-key secret added with PR #39 lets the workflow
  push to `ssh://aur@aur.archlinux.org/clipman.git`. Rotate by
  regenerating the keypair, registering the new public key on the AUR
  account, and updating the repository secret.
- **GitHub Release** — the workflow's default `GITHUB_TOKEN` (no
  separate PAT) creates the release entry and uploads assets.

## Support policy

- The **latest MINOR** and the **previous MINOR** of clipman receive
  bug fixes and security backports for **6 months** after the older
  MINOR's release date. Anything older than that is unsupported and
  will not receive further patch releases.
- Security fixes follow the disclosure window in `SECURITY.md`
  regardless of the support window above — a critical fix lands on
  every still-supported MINOR, and a sufficiently severe issue may
  trigger an out-of-band patch on an otherwise-EOL line.
- Currently supported lines (as of v1.0.6):
  - **1.0.x** — full support (latest MINOR; there is no previous
    MINOR yet because 1.0 is the only released MINOR line).

## Deprecation policy

- Anything user-facing — a CLI flag, a config key, a D-Bus method
  signature, a default behaviour — must ship in **at least one MINOR
  release with a deprecation warning** before removal. The warning
  goes wherever the user will actually see it: logged on daemon start
  for daemon/CLI surfaces, or rendered as a deprecation banner in the
  popup for UI-facing changes.
- Removal lands in the next MAJOR (or, if the MAJOR is far off, the
  MINOR after the warning shipped — whichever is later). Never remove
  in the same MINOR series the warning was introduced in.
- D-Bus surface deprecations follow the same one-MINOR-warning rule,
  with a try/except fallback for the older signature held for one
  MINOR series. ADR 0005
  (`docs/adr/0005-dbus-simulate-paste-mode-arg.md`) set the precedent:
  the daemon retries the no-arg `SimulatePaste()` call when the v5
  `SimulatePaste(s mode)` call raises against a v4 extension still
  loaded in Shell.

## Settings-key migration

The daemon stores user state in a SQLite `settings` table
(`~/.local/share/clipman/clipman.db`). Migrations have to assume some
users will skip MINOR releases, so:

- **Renaming a key**: read both the old name and the new name for one
  full MINOR series, but write only the new name. Drop the old-key
  read in the MINOR after that, by which point a fresh write has
  reasonably happened for every active user.
- **Adding a new key**: just add it. The read path already handles
  absence via per-key defaults, so no migration step is required.
- **Removing a key**: treat it as a user-facing deprecation
  (see above) — warn for one MINOR, then drop the read.
- **Changing the type or shape of a value**: same as a rename —
  write only the new shape, but accept both shapes on read for one
  MINOR series.

## Cross-reference

- Release runbook (literal commands): `docs/release-checklist.md`
- Versioning policy: `docs/adr/0010-versioning-policy.md` (added in
  the parallel docs overhaul)
- D-Bus deprecation precedent: `docs/adr/0005-dbus-simulate-paste-mode-arg.md`
- PyPI publishing model: `docs/adr/0004-pypi-trusted-publishing.md`
- Contributor-side workflow: `CONTRIBUTING.md`
- Security disclosure window: `SECURITY.md`
