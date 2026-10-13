# Repo rules

Some rules are enforced by tooling; follow all of them regardless.

## pre-commit

All commits go through [pre-commit](https://pre-commit.com). Config: `.pre-commit-config.yaml`.

- Install once after cloning: `pre-commit install` (sets up both the `pre-commit` and `commit-msg`
  hooks).
- Do not use `git commit --no-verify`. If a hook fails, fix the cause.
- Markdown is formatted by **mdformat**: GFM plus footnotes, prose wrapped at **100 columns**.
  Settings live in `.mdformat.toml`.
- Markdown is also linted by **markdownlint**, for semantic issues mdformat doesn't catch (heading
  structure, etc.). Settings live in `.markdownlint.jsonc`.
- Python is linted and formatted by **Ruff** and type-checked by **Pyrefly**, both run as hooks and
  both configured in `pyproject.toml`. See [Python](#python).
- Other hooks: trailing-whitespace (markdown hard breaks preserved), end-of-file-fixer, check-yaml,
  check-merge-conflict, check-added-large-files, mixed-line-ending (LF), actionlint (workflow
  expressions, runner labels, and shellcheck over `run:` scripts), shellcheck over tracked `.sh`
  files, the `bootstrap_repo` unit tests, betterleaks secret scanning (`.betterleaks.toml` holds
  what the repo treats as benign).
- Run against everything with `pre-commit run --all-files`; bump hook versions with
  `pre-commit autoupdate`. CI re-runs the full hook suite on every PR.

## Python

Python code follows the Google Python style guide except where the configuration in `pyproject.toml`
says otherwise. Ruff and Pyrefly enforce most of it, so it is checked rather than remembered. What
the tools cannot check: annotations on all code outside `tests/`, `%`-style logging placeholders,
and TODOs that carry an issue link and nothing else.

The rule selection, `line-length`, `quote-style`, `D417` and Pyrefly's `preset = "strict"` are the
deliberate part, and a repo created from this template starts on them. Selecting extra rules on top
is fine; removing a selected rule to make existing code pass is not. Suppress a specific line with a
named code and a reason (`# noqa: ANN001  # signature fixed by the SDK`), never a blanket `# noqa`.

One package, at `src/hello_world/`, with `tests/` alongside it. The example is there to be replaced:
rename the package, rename it in `known-first-party` and `[project]`, and write your own. Commands:

```bash
uv sync                    # after cloning, and after changing dependencies
uv run pytest
uv run ruff check .
uv run pyrefly check src   # the path scopes the check -- see the comment in pyproject.toml
```

Dependencies are pinned exactly and moved by Dependabot. Changing one means re-running `uv lock` and
committing `uv.lock`; CI uses `--locked` and fails if the two disagree.

## Brevity

These cover the repo's own files and the prose around a change.

No comment where the code already says it. A comment restating the line goes stale, then misleads.
Comment only the non-obvious why: a constraint invisible from the line, a workaround, an override of
an upstream default. One line.

Reasoning goes in the issue or the PR description, not the file. Squash merge makes the description
the commit body, so it is permanent and reachable from `git blame`.

PR descriptions are proportionate. A typo fix needs a sentence; no body at all where the subject and
diff already tell the story. Testing carries evidence, not process.

## Scope of a change

One concern per pull request, refactoring in its own.

Do not reformat or rename what the task did not touch. Prettier rewraps whole files here, so one
unrelated edit produces a diff nobody can read.

No drive-by fixes. Open an issue.

No summary or report documents. The PR description is the record.

Flag scope growth before writing the code, not after.

## Commits and pull requests

The rules that come up most often:

Conventional Commits, subject line 72 characters or fewer, lowercase, no trailing period. The scope
is the affected area of the repo — for example `feat(pre-commit): add hook for X`. The commitizen
`commit-msg` hook enforces the length.

Squash merge. This repo is configured so the PR title becomes the commit subject and the PR
description becomes the commit body, so both are permanent. Write them for someone reading `git log`
in a year. The `Lint PR` workflow checks the title; for a single-commit PR the title must match that
commit.

One branch per PR, cut from `main`, named with the agent's own prefix — `claude/…`, or `ai/…` for an
agent without a prefix of its own. Concurrent agents get a worktree each.

Do not push to `main`, force-push a shared branch, or merge your own PR. The merge is the one point
where a person reads the change before it lands.

Every PR references an issue with `Fixes: #n`, or `Refs: #n` where several PRs land against one
issue. No issue means create one first; a one-line issue is enough.

Agent-assisted work carries a `Co-authored-by` trailer at the end of the PR description. The
identity is the agent's own, not always Claude:

| Agent          | Trailer identity                                            |
| -------------- | ----------------------------------------------------------- |
| Claude Code    | `Claude <noreply@anthropic.com>`                            |
| GitHub Copilot | `generated by GitHub, ...+Copilot@users.noreply.github.com` |

No model name and no version, so that `git log` can answer how much of the repo was written with an
agent — a string that changes with every model release cannot be counted. Add a row when another
agent starts being used. A trailer on a branch commit is discarded by the squash, so the description
is the only place it survives.

## Getting to green

CI must be green before a pull request goes for review. Work that is not there yet goes in a draft.

- Do not commit with `--no-verify`, or otherwise skip the hooks.
- Do not delete, skip, or comment out a failing test. Fix the code, or say in the PR why the test
  itself was wrong.
- Do not weaken a lint rule, widen a suppression, or lower a threshold to make existing code pass.
  Adding a rule is fine; removing one is a discussion, not a commit.
