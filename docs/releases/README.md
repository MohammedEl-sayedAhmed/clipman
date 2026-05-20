# Release notes

GitHub Releases are the authoritative home for Clipman's release notes.
They are **auto-generated** by `.github/workflows/release.yml` from the
matching `## [x.y.z]` section in `CHANGELOG.md` whenever a `v*.*.*` tag
is pushed.

## How a release happens

1. Bump versions with `./scripts/bump-version.sh <new-version>` —
   updates `pyproject.toml`, `snap/snapcraft.yaml`, `flathub/*.json`,
   and `aur/PKGBUILD` in one shot.
2. Rename the `## [Unreleased]` section in `CHANGELOG.md` to
   `## [<new-version>] - YYYY-MM-DD`.
3. Commit, tag (`git tag v<new-version>`), and push (`git push --tags`).
4. The `release.yml` workflow takes over — see the diagram below.

## Pipeline shape

```mermaid
flowchart TD
    classDef trigger fill:#dbeafe,stroke:#3b82f6,color:#1e40af
    classDef gate    fill:#fef3c7,stroke:#d97706,color:#92400e
    classDef build   fill:#dcfce7,stroke:#16a34a,color:#166534
    classDef publish fill:#ede9fe,stroke:#7c3aed,color:#5b21b6
    classDef final   fill:#fee2e2,stroke:#dc2626,color:#991b1b

    Tag["push tag v*.*.*"]:::trigger
    PF["pre-flight<br/>tag/version sanity<br/>+ extract CHANGELOG section"]:::gate
    Tests["tests<br/>Python 3.10 / 3.11 / 3.12"]:::gate

    BPyPI["build-pypi<br/>wheel + sdist"]:::build
    BSnap["build-snap"]:::build
    BExt["bundle-extension<br/>versioned zip"]:::build

    PPyPI["publish-pypi<br/>OIDC trusted publishing"]:::publish
    PSnap["publish-snap<br/>stable channel"]:::publish

    Release["github-release<br/>attaches wheel + sdist + snap + extension zip<br/>body = extracted CHANGELOG section"]:::final

    Tag --> PF --> Tests
    Tests --> BPyPI
    Tests --> BSnap
    Tests --> BExt
    BPyPI --> PPyPI
    BSnap --> PSnap
    BExt --> Release
    PPyPI --> Release
    PSnap --> Release
```

## Why CHANGELOG.md drives the release body

- One source of truth: `CHANGELOG.md` ships with the source tarball
  and PyPI sdist, so users who never visit the GitHub UI still see the
  same notes.
- Reviewable in a PR: release notes are part of the diff that lands on
  `main`, not a free-text field edited after the fact.
- Auditable: the tag's release body is exactly the section that was
  committed at the tag — no out-of-band edits.

## Related decisions

- **ADR 0004** — *PyPI publishing via OIDC trusted publishing*. The
  `publish-pypi` job has no long-lived token; PyPI must have a
  matching trusted-publisher entry registered manually.
- **ADR 0003** — *Pin all third-party GitHub Actions to commit SHAs*.
  Every action in `release.yml` is SHA-pinned with a version comment.
- **ADR 0006** — *Solo-friendly branch protection on `main`*. The
  same required status checks gate the commit that the release tag
  points at.
