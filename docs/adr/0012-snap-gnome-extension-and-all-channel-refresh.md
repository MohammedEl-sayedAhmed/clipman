---
status: Accepted
date: 2026-09-14
deciders: MohammedEl-sayedAhmed
---

# 12. Snap on the GNOME extension, with an all-channel weekly refresh (supersedes ADR 0009)

## Context

ADR 0009 set the weekly snap rebuild cadence. Its trigger, its build
step, its credential handling and its no-version-bump rule are all
still accurate. Three of its statements are not:

- It describes a `core22` base with the GTK runtime, Python, the GObject
  bindings and the image libraries resolved from the Ubuntu archive as
  `stage-packages`. Every archive security update to that stack, most
  often libcurl reaching us through libappstream, then landed in the
  Snap Store's daily scan as our problem.
- It says the scheduled run publishes to `edge` only, so that a broken
  rebuild cannot reach stable.
- It therefore lists manual promotion from edge to stable as a standing
  chore for the maintainer.

## Decision

**Base and runtime.** The snap builds on `core24` with
`extensions: [gnome]`. The GTK 4 and libadwaita stack, Python, the
GObject bindings, the gdk-pixbuf loaders, the icon themes and the
compiled GSettings schemas all come from Canonical's `gnome-46-2404`
content snap, which Canonical patches. The only `stage-packages` entry
is `wtype`; `wl-clipboard` is built from source. A `cleanup` part primes
away anything `core24` or `gnome-46-2404` already ships. The part does
not run `craftctl default`, so the repository checkout is not dumped
into the package. Confinement stays `strict`, with the two D-Bus slots
from ADR 0009 unchanged.

**Channels.** The weekly run refreshes every published channel, not just
edge. The safety property is no longer "edge only" but the mapping from
channel to source ref:

| Channel | Source ref |
|---------|------------|
| `edge` | `main` |
| `beta`, `candidate`, `stable` | the latest release tag |

Publishing a `main` build to stable would leak unreleased work, so the
tag lookup fails the job rather than falling back to `main` when it
cannot resolve a release. A `workflow_dispatch` run picks the source ref
from the channel the maintainer chose, by the same mapping.

## Consequences

**Positive**

- The GTK stack is off our vulnerability-scan surface entirely. The
  recurring Snap Store security mail about archive packages we merely
  restaged stops at the source.
- Stable stays patched without anyone remembering to promote a build.
- The channel-to-ref mapping is enforced in the workflow, so the
  dangerous combination is unreachable rather than merely discouraged.

**Negative**

- The snap now depends on Canonical's `gnome-46-2404` content snap being
  present and current on the user's system. That is the normal case on
  a GNOME desktop, and snapd pulls it in, but it is a runtime dependency
  we do not control.
- A bad release tag now reaches stable on the next cron run rather than
  waiting for a manual promotion. The release pipeline's own gating is
  what prevents that, so the two are coupled.

## References

- ADR 0009 — Weekly snap rebuild cadence, superseded by this record.
- `snap/snapcraft.yaml` and `.github/workflows/snap-refresh.yml` are the
  sources for everything above.
