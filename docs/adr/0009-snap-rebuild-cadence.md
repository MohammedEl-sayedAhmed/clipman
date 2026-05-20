---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 9. Weekly snap rebuild cadence

## Context

Clipman ships as a strict-confinement snap. The snap embeds
`stage-packages` resolved from the Ubuntu 22.04 (`core22`) archive at
build time — Python, GTK runtime, GObject bindings, image libraries,
etc. When any of those upstream packages gets a security fix, the
published snap continues to ship the pre-fix version until it is
rebuilt.

The Snap Store enforces this by emailing publishers on every USN that
touches a binary in their published snaps. Clipman's r5 (v1.0.4)
revision received multiple such notices in a short window for
`libavahi-client3`, `libavahi-common3`, `liblcms2-2`, etc. The fix is
always the same — "Simply rebuilding the snap will pull in the new
security updates and resolve this" — but doing it by hand on every
USN doesn't scale.

We need a way to keep the published snap fresh against upstream
security without coupling it to clipman's own release cadence.

## Decision

Add a scheduled GitHub Actions workflow
(`.github/workflows/snap-refresh.yml`) that rebuilds the snap and
publishes the new revision automatically.

- **Trigger**: weekly cron (`0 4 * * 1` — Monday 04:00 UTC). Also
  `workflow_dispatch` for manual reruns, and `push` /
  `pull_request` on snap-relevant paths to validate snap builds
  before merge.
- **Build**: `snapcore/action-build` produces the `.snap`, uploaded
  as a workflow artifact (14-day retention) regardless of whether
  the publish step runs.
- **Publish**: `snapcore/action-publish` uploads to the **edge**
  channel by default on the scheduled run. `workflow_dispatch`
  exposes a channel input (edge / beta / candidate / stable) and a
  `publish: true/false` toggle. Publish requires the
  `SNAPCRAFT_STORE_CREDENTIALS` secret; if it's absent the publish
  job exits with a `::warning::` instead of failing the workflow.
- **Channel choice**: edge is the auto-publish default so a broken
  rebuild doesn't immediately ship to stable. The maintainer can
  smoke-test edge and promote to stable manually (or via the tag
  release pipeline) once they're satisfied.
- **No version bump**: the rebuilt snap reuses the version field in
  `snap/snapcraft.yaml`. Snap Store assigns a fresh revision
  number; the user-visible version stays the same until the next
  proper release.

## Consequences

**Positive**

- USN notification emails get resolved automatically on the next
  Monday rebuild (worst-case one-week stale).
- Decouples security-patch rebuilds from clipman's own release
  cycle. The release pipeline (`release.yml`) still handles
  user-visible version bumps; this workflow just keeps the build
  fresh.
- Build failures surface as a regular workflow run, so packaging
  regressions show up via the same Actions tab as code-side CI.

**Negative**

- The maintainer must remember to promote edge → stable
  occasionally if they want stable to also stay fresh. Without
  promotion, only edge channel users get the rebuilt revision.
  Acceptable trade-off: stable promotion is a manual safety gate.
- Strict-confinement snaps that declare D-Bus slots (clipman has
  two — `com.clipman.Daemon` and `com.clipman.Clipman`) sometimes
  trigger Snap Store's manual review queue. The publish step
  succeeds in those cases but the new revision sits unreleased
  until a human reviews it. Documented; can't be automated away.
- `SNAPCRAFT_STORE_CREDENTIALS` is a long-lived token (≈1y
  lifetime). Mitigated by scoping the export-login to the clipman
  snap only and the `package_push`/`package_release` ACLs, and by
  the Snap Store's renewal-reminder emails.

## References

- PR #9 — the workflow.
- `snap/snapcraft.yaml` — the snap definition the workflow rebuilds.
- Upstream Snap Store policy:
  <https://forum.snapcraft.io/t/snap-store-security-update-emails/>
