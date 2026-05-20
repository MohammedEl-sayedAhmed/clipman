# Release checklist

End-to-end runbook for cutting a Clipman release. The release pipeline
itself (`.github/workflows/release.yml`) is documented in
`docs/releases/README.md` and ADR 0004 — this file is the *human* steps
that lead up to pushing the tag.

## Preconditions

- Working tree on `main`, fully up to date with `origin/main`.
- `gh auth status` shows you logged in as `MohammedEl-sayedAhmed`.
- `SNAPCRAFT_STORE_CREDENTIALS` repo secret is still set (token is
  renewed yearly; the Snap Store will email a reminder ~30 days
  before expiry).
- PyPI trusted publisher is configured at
  https://pypi.org/manage/account/publishing — project
  `clipman-clipboard`, repo `clipman`, workflow `release.yml`,
  environment `pypi`. First-release-only.

## Cut a release

Assume you're going from `1.0.4` to `1.0.5`.

```bash
# 1. Sync.
git checkout main
git fetch origin --prune --tags
git reset --hard origin/main

# 2. Bump versions in lockstep.
./scripts/bump-version.sh 1.0.5
# This touches pyproject.toml, snap/snapcraft.yaml, flathub/*.json,
# aur/PKGBUILD, and clipman/__init__.py.

# 3. Promote the Unreleased section in CHANGELOG.md.
#    Open CHANGELOG.md and rename `## [Unreleased]` to
#    `## [1.0.5] - YYYY-MM-DD` (today's date). Add a fresh
#    `## [Unreleased]` block at the top.
$EDITOR CHANGELOG.md

# 4. Verify locally.
python3 -m unittest discover -s tests
ruff check clipman tests

# 5. Commit the bump.
git add pyproject.toml snap/snapcraft.yaml flathub/*.json aur/PKGBUILD \
        clipman/__init__.py CHANGELOG.md
git commit -m "chore: bump to 1.0.5"
git push origin main

# 6. Tag and push. This is the trigger.
git tag -s v1.0.5 -m "v1.0.5"   # or unsigned: git tag v1.0.5
git push origin v1.0.5
```

The tag push fires `release.yml`. Watch the run in the Actions tab —
each stage either annotates the failure or moves on:

1. **pre-flight** — confirms `pyproject.toml` and `snap/snapcraft.yaml`
   match the tag; extracts the matching `CHANGELOG.md` section.
2. **tests** — Python 3.10 / 3.11 / 3.12 matrix.
3. **build-pypi** — `python -m build`, uploads dist/ artifact.
4. **publish-pypi** — OIDC trusted publish.
5. **build-snap** — `snapcore/action-build`, uploads .snap artifact.
6. **publish-snap** — releases to the `stable` channel.
7. **bundle-extension** — `gnome-extensions pack` → versioned zip.
8. **github-release** — creates the GH Release with all artifacts and
   the auto-extracted CHANGELOG section as the body.

If a stage fails before publish, the tag is already on `origin` — you
can:

- Push a fix commit to `main`, delete the tag (`git push --delete
  origin v1.0.5 && git tag -d v1.0.5`), retag.
- Or workflow-dispatch the release with the existing tag once main is
  green.

## After the pipeline goes green

These steps aren't automatable today:

- **GNOME Extensions website** — download
  `clipman-extension-v1.0.5.zip` from the new GH Release and upload it
  at https://extensions.gnome.org/upload/. EGO has no programmatic
  upload API.
- **AUR** — bump `aur/PKGBUILD` (the bump script already did this) and
  push to the AUR remote if you maintain a separate AUR repo.
- **Flathub** — open a PR against the Flathub repo bumping the
  manifest source URL / commit. The in-repo manifest under `flathub/`
  is for reference only.

## Verify the release publicly

```bash
pip index versions clipman-clipboard | head -3
snap info clipman | grep tracking
gh release view v1.0.5 --json assets --jq '.assets[].name'
```

You should see the new version on PyPI within ~1 min of the publish
step, on the Snap Store stable channel within ~5 min, and the GH
Release listing wheel + sdist + snap + extension zip.

## Roll back

If a release is broken in a way users will notice:

- **PyPI**: you cannot delete or replace a published version. Bump
  patch (e.g. `1.0.6`) and re-cut.
- **Snap Store**: revert to the previous revision via
  `snapcraft revert clipman --revision=<prev>` or the Snap Store
  dashboard.
- **GH Release**: edit notes to add a "yanked" prefix and a pointer to
  the fixed release. Don't delete the tag.
