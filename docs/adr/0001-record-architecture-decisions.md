---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 1. Record architecture decisions

## Context

Clipman has accumulated several non-obvious choices in its CI, packaging,
and IPC layers (CodeQL baseline ratchet, OIDC-based PyPI publishing,
D-Bus interface design, etc.). Without a written record, every revisit
of those areas re-litigates the same trade-offs and risks reversing
intentional choices.

We need a lightweight, in-repo home for those decisions that:

- lives next to the code (so it travels with the repo and is reviewed
  in the same PR flow);
- is short, readable, and easy to add to;
- doesn't require a separate tool or static-site generator.

## Decision

Adopt [MADR](https://adr.github.io/madr/) (Markdown Architecture
Decision Records) for all significant architecture and infrastructure
decisions.

- Records live under `docs/adr/`.
- File names follow `NNNN-kebab-case-title.md`, monotonically numbered.
- Each record has YAML frontmatter (`status`, `date`, `deciders`) and
  three sections: **Context**, **Decision**, **Consequences**.
- Status values: `Proposed`, `Accepted`, `Deprecated`, `Superseded by
  NNNN`. Once a record is `Accepted`, do not edit the original;
  supersede it with a new ADR that links back.
- `docs/adr/README.md` is the index, with one-line summaries.

## Consequences

**Positive**

- Reviewers and future maintainers get the "why" inline with the code.
- Each non-trivial PR can cite an ADR instead of repeating rationale
  in the PR body.
- The index doubles as onboarding documentation for the project's
  CI/security posture.

**Negative**

- Every architecturally significant PR now carries a small extra cost:
  authoring or amending an ADR.
- Records can drift from reality if not maintained; the `Superseded by`
  status is the only way to deprecate, which requires discipline.
