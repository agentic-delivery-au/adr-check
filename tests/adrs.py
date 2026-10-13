"""Build ADR text for tests."""

TEMPLATE = """\
---
status: {status}
date: 2026-03-12
supersedes: {supersedes}
superseded_by: {superseded_by}
---

# {number:04d}. {title}

## Context

The situation.

## Considered options

### One

- Good: it works.

## Decision

We will do it.

## Consequences

- It is done.
"""


def adr(
    number: int,
    *,
    status: str = "accepted",
    supersedes: list[int] | None = None,
    superseded_by: int | None = None,
    title: str = "A decision",
    h1_number: int | None = None,
) -> str:
    return TEMPLATE.format(
        status=status,
        supersedes=supersedes or [],
        superseded_by="" if superseded_by is None else superseded_by,
        number=number if h1_number is None else h1_number,
        title=title,
    )


def name(number: int, slug: str = "a-decision") -> str:
    return f"{number:04d}-{slug}.md"
