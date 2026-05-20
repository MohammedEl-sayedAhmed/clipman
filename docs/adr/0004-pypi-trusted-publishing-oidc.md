---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 4. PyPI publishing via OIDC trusted publishing (no long-lived token)

## Context

The tag-triggered release pipeline (PR #16) needs to push a wheel +
sdist to PyPI. Three viable mechanisms exist:

1. **`PYPI_API_TOKEN` repo secret** — historically the default. A
   long-lived token with upload scope sits in GitHub Secrets. Leak
   risk: any workflow with `secrets:` access (including a malicious
   PR from a fork if not gated) can read it, and a compromised
   maintainer token persists until manually rotated.
2. **Project-scoped trusted publisher (OIDC)** — PyPI verifies a
   short-lived OIDC token GitHub mints per-job, scoped to a specific
   repository + workflow + environment. No long-lived secret exists.
3. **Manual upload from a workstation** — defeats the purpose of an
   automated pipeline.

## Decision

Use **OIDC trusted publishing** (option 2) for the `clipman-clipboard`
project on PyPI.

- The `publish-pypi` job in `.github/workflows/release.yml` requests
  an OIDC token via `permissions: id-token: write`, scoped **only** to
  that job. Every other job in the workflow has `contents: read`.
- The job runs inside a GitHub *environment* named `pypi`, which
  gives a single stop-button between the tag push and the upload
  (and a place to add a manual approval gate later without changing
  the workflow).
- The upload step is `pypa/gh-action-pypi-publish` pinned to a SHA
  (see ADR 0003). The action negotiates the OIDC exchange with PyPI
  automatically.
- A *pending publisher* must be registered manually at
  <https://pypi.org/manage/account/publishing/> before the first
  release. The fields are documented in the PR #16 body and in
  `docs/releases/README.md`. After the first successful release the
  entry becomes a regular trusted publisher.

## Consequences

**Positive**

- **No long-lived PyPI credential exists anywhere in this repo or in
  GitHub Secrets.** A repo-wide secrets leak cannot push to PyPI.
- The OIDC token is single-use, scoped to one job in one workflow,
  and expires in minutes.
- The `pypi` environment is the natural place to add a manual
  approval step or environment-level restrictions later, without
  rewriting the workflow.

**Negative / trade-offs**

- **One-time manual setup** at pypi.org is unavoidable and cannot be
  automated from this repo. A new maintainer would need to repeat
  it (or be added as a PyPI project collaborator with publish
  rights).
- The workflow filename (`release.yml`), workflow job name, and
  environment name (`pypi`) are baked into the trusted-publisher
  config on PyPI. Renaming any of them silently breaks the publish
  step until the PyPI side is updated.
- If GitHub's OIDC infrastructure has an outage during a release,
  the publish step fails. There is no fall-back token to use
  manually — by design.
