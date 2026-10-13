---
status: accepted
date: 2026-10-08
supersedes: []
superseded_by:
---

# 0001. Record architecture decisions

> In the context of a small team whose repos outlive the people who chose their shape, facing the
> loss of the reasons behind decisions, we decided for MADR-lite ADRs in each repo's `docs/adr/` and
> neglected a central log and plain Nygard records, to keep the reasons next to the code, accepting
> that a CI check must enforce the rules and that the check does not exist yet.

## Context

Recorded retrospectively. The team made this decision first and recorded it here afterwards.

The team's code outlasts the memory of why it looks the way it does. Reasons live in ticket threads,
chat and people's heads, and they are the first thing lost when someone moves on. Agents now read
the repos as well, and an agent that finds an old choice but not its reversal can act on the wrong
one.

The team needs a place to record architecturally significant decisions that stays true as the code
changes, that a person can read in full and that a script can check.

## Considered options

### Template

- MADR-lite: Nygard's sections plus Considered options, so rejected options stay on record. Against
  it: the team maintains its own template.
- Plain Nygard: shortest, but loses the reasoning for the options not taken.
- Full MADR: more fields than a small team will fill in, and its `date` means "last updated".

### Location

- Per repo, in `docs/adr/`: each record sits beside its code and goes through the same pull request.
  Against it: no single list across repos.
- One central log: one place to search, but it needs a gatekeeper for numbers and drifts from the
  code.

### Guardrails

- Status in frontmatter plus a CI check, adopted. Against it: one more thing to build and maintain.
- A `superseded/` subfolder: rejected, because it breaks inbound links.
- A generated index of accepted ADRs: not adopted, because the log is small enough to read.

## Decision

We will record each architecturally significant decision as a MADR-lite ADR in its repo's
`docs/adr/`, numbered separately in each repo, with its status in frontmatter. We will never edit a
merged ADR to match new reality, and will record a change of mind as a new ADR that supersedes the
old one. We will have CI check each ADR's format, numbering, supersession links and unchanged body,
with a check planned. The ADR guidelines set out the rules in full.

## Consequences

- The reasons for a choice stay beside the code and go through review with it.
- Every significant change carries the extra work of an ADR, and deciding what is significant needs
  judgement.
- Until the check ships, reviewers enforce the rules by hand.
- No script can notice a decision that changed without a superseding ADR.
