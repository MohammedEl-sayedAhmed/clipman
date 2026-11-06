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
  `clipman/_version.py`, `snap/snapcraft.yaml`, `flathub/*.json`,
  `aur/PKGBUILD`, `CITATION.cff`, and `data/*.metainfo.xml` in a single
  pass so no channel drifts. The extension's `metadata.json` integer is
  left alone on purpose — it counts the D-Bus contract, not the
  product version.
- Promote the `[Unreleased]` block in `CHANGELOG.md` to
  `[X.Y.Z] - YYYY-MM-DD` and add a fresh empty `[Unreleased]` block on
  top.
- Land the bump as a squash-merged release PR, then create the `vX.Y.Z`
  tag through the GitHub API (`gh api .../git/refs`) on the merged
  commit. The identity pre-push hook rejects a locally pushed tag that
  points at a squash commit. Creating the tag is the trigger.
- `.github/workflows/release.yml` fires on the tag and, as of v1.0.6+,
  publishes to PyPI, the Snap Store `stable` channel, AUR, and the
  GitHub Release end-to-end. The full job DAG, secrets matrix, and
  SHA-pinning policy are documented in
  [docs/ci-cd.md](ci-cd.md#release-pipeline-end-to-end).
- The extension goes to extensions.gnome.org through the site's API
  (`ego-upload.yml`, which `release.yml` calls when `extension/` changed
  since the previous release). It needs the `EGO_USERNAME` and
  `EGO_PASSWORD` secrets. To upload a missed release, run "Upload to
  extensions.gnome.org" from the Actions tab with its tag. e.g.o. still
  reviews each upload before users get it.
- The listing's name, description, URL and donation links come from
  `extension/metadata.json`: every upload resets them, so edit them
  there, not on the website. The icon and the screenshot are set only
  on the website, from the listing page while logged in as the owner.

Per-channel auth, so you know what to rotate when something expires:

- **PyPI** — OIDC trusted publishing, no token stored. The trusted
  publisher binding (project `clipman-clipboard`, workflow
  `release.yml`, environment `pypi`) is configured once per ADR 0004
  (`docs/adr/0004-pypi-trusted-publishing-oidc.md`).
- **Snap Store** — `SNAPCRAFT_STORE_CREDENTIALS` repository secret.
  Token expires yearly; the Snap Store emails a reminder roughly 30
  days out.
- **AUR** — an SSH-key secret added with PR #39 lets the workflow
  push to `ssh://aur@aur.archlinux.org/clipman-clipboard.git`. Rotate by
  regenerating the keypair, registering the new public key on the AUR
  account, and updating the repository secret.
- **extensions.gnome.org** — `EGO_USERNAME` and `EGO_PASSWORD`
  repository secrets, the login of the account that owns the
  extension. Update them when that password changes. Each upload
  ends by revoking the account's API tokens, so a `gnome-extensions
  upload` login on your own machine asks for the password again; the
  website login is not affected.
- **Snap Store metrics** — `SNAP_METRICS_CREDENTIALS`, a login that
  can only read metrics, for the daily stats job. It expires yearly,
  like the release login.
- **GitHub Release** — the workflow's default `GITHUB_TOKEN` (no
  separate PAT) creates the release entry and uploads assets.

## Support policy

- The **latest MINOR** of clipman receives bug fixes and security
  fixes. Older lines are unsupported and do not get patch releases, as
  the table in `SECURITY.md` says.
- Security fixes follow the disclosure window in `SECURITY.md`
  regardless of the support window above — a critical fix lands on
  every still-supported MINOR, and a sufficiently severe issue may
  trigger an out-of-band patch on an otherwise-EOL line.
- Currently supported lines (as of v1.3.0), matching the table in
  `SECURITY.md`:
  - **1.3.x** — full support (latest MINOR).
  - **1.2.x** and older — unsupported. 1.2.1 was the last 1.2.x
    release, and no 1.1.x patch release was ever made.

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
  (`docs/adr/0005-paste-mode-as-dbus-arg.md`) set the precedent:
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
- Release pipeline reference (job DAG, secrets, SHA-pin policy): `docs/ci-cd.md`
- Versioning policy: `docs/adr/0011-versioning-policy-refresh.md`
  (supersedes `0010-versioning-policy.md`)
- D-Bus deprecation precedent: `docs/adr/0005-paste-mode-as-dbus-arg.md`
- PyPI publishing model: `docs/adr/0004-pypi-trusted-publishing-oidc.md`
- Contributor-side workflow: `CONTRIBUTING.md`
- Security disclosure window: `SECURITY.md`
