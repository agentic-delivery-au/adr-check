# adr-check

Checks the architecture decision records (ADRs) in a repository's `docs/adr/` directory. It keeps
the records uniform, links superseded decisions to their replacements, and, in CI, stops anyone
rewriting a decision that has already been merged.

An ADR is a short Markdown file that records one significant decision and the reasons for it. The
format this tool checks is a small variant of [MADR](https://adr.github.io/madr/): Michael Nygard's
sections plus a list of the options considered.

## What it checks

Files in the ADR directory that are not ADRs do not fail the check. It skips `README.md` and any
file that does not end in `.md`, and it ignores subdirectories. Every other Markdown file is
checked, so a badly named ADR fails instead of disappearing. A symlink in place of an ADR is an
error, because the check would otherwise validate the file it points at.

### In the working tree

These checks need only the files in front of you. They run in both modes.

- **Filename.** `NNNN-kebab-title.md`: four digits, then lowercase words joined by hyphens, for
  example `0007-use-managed-identities.md`.
- **Frontmatter.** A YAML block between `---` lines holding exactly four keys, and no others:
  - `status`: one of `proposed`, `accepted`, `rejected` or `superseded`.
  - `date`: an ISO date such as `2026-03-12`.
  - `supersedes`: a list of ADR numbers, such as `[7]`, or empty.
  - `superseded_by`: one ADR number, or empty.
- **Title.** An H1 of the form `# 0007. Title`, where the number matches the filename.
- **Sections.** Four H2 headings: `## Context`, `## Considered options`, `## Decision` and
  `## Consequences`. Headings inside code fences and HTML comments do not count.
- **Supersession links.** They must agree in both directions. If `0009` supersedes `0007`, then
  `0007` has `status: superseded` and `superseded_by: 9`. An ADR with `superseded_by` must have
  `status: superseded`, and a `superseded` ADR must name its successor. A link to a missing ADR, to
  the ADR itself, or to a rejected successor fails.
- **Duplicate numbers.** Two files may not share a number. A `supersedes` or `superseded_by` that
  names a number two ADRs share also fails, because it is ambiguous.

### Against the base branch

`--mode ci` adds checks that compare your branch with the branch it merges into. Merged decisions
are a record of what the team knew at the time, so they stay put.

- **Merged ADRs are immutable.** The body of an ADR on the base branch may not change, and the
  frontmatter may change only from `accepted` to `superseded` with `superseded_by` set. A pull
  request labelled `adr-correction` may fix a typo or a link in the body. The label does not allow a
  frontmatter change.
- **`proposed` ADRs may change.** A `proposed` ADR on the base branch is not settled, so these rules
  do not protect it.
- **No deletions or renames.** ADRs are never deleted, and never renamed. The one exception is the
  renumbering repair. If two branches took the same number, one ADR may change its filename number
  and its H1 number, and nothing else. ADRs that point at it may then update their `supersedes` or
  `superseded_by` to the new number.
- **No reused numbers.** A new ADR may not take a number the base branch already uses, including one
  the base took after you branched.
- **Symlinks on main need an override.** A symlinked ADR already on the base branch cannot be
  repaired through this check. Replacing it with a regular file reports a type change, and deleting
  it reports a deletion. Neither is allowed, and `adr-correction` lifts neither, so a person must
  override the required check for that pull request.
- **No `proposed` on the main branch.** With `--merging-to-main`, any ADR with `status: proposed`
  fails. `proposed` exists only on a branch.

## Usage

Pick the form that suits the repository. All three run the same checks. Replace the placeholder
versions with a current release.

### Pre-commit hook

The repository ships a [pre-commit](https://pre-commit.com) hook. Add it to
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/agentic-delivery-au/adr-check
    rev: vX.Y.Z
    hooks:
      - id: adr-check
```

The hook runs when a file under `docs/adr/` changes. It passes no filenames, because the rules look
across the whole directory. It sets `language_version: python3.14`, because the package needs Python
3.14 or newer and pre-commit would otherwise build it on its own interpreter. The machine needs a
`python3.14` executable on `PATH`.

If you would rather install a released package than clone this repository, use a local hook:

```yaml
repos:
  - repo: local
    hooks:
      - id: adr-check
        name: adr-check
        entry: adr-check
        language: python
        language_version: python3.14
        additional_dependencies: [adr-check==X.Y.Z]
        files: ^docs/adr/
        pass_filenames: false
```

The hook checks the working tree only. It cannot see the base branch, so it cannot catch an edit to
a merged ADR, a deleted file or a number that the base branch already holds. CI catches those.

### In CI

Run the package from PyPI with [uv](https://docs.astral.sh/uv/). The checkout must hold the full
history, because the check compares your branch with its base:

```bash
uvx adr-check==X.Y.Z --mode ci --base-ref origin/main --labels "$LABELS" --merging-to-main
```

On GitHub, the composite action wraps that command and fills in its inputs from the event:

```yaml
name: adr-check

on:
  pull_request:
    types: [opened, reopened, synchronize, edited, labeled, unlabeled]

permissions:
  contents: read

jobs:
  adr-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: agentic-delivery-au/adr-check@vX.Y.Z
```

Pin the action to a release tag, `@vX.Y.Z`. Move it together with the hook's version (its `rev:`, or
`adr-check==` in a local hook), so the hook and CI apply the same rules. Four details matter:

- **`fetch-depth: 0`.** A shallow checkout has no base branch to compare with, and the action fails
  with a message that says so.
- **`labeled` and `unlabeled`.** Without them, adding `adr-correction` does not re-run the check,
  and the pull request stays red until the next push.
- **No `paths:` filter.** A filtered workflow does not report on a pull request that touches no ADR,
  so a required check never arrives.
- **Avoid triggering on `push`.** A push carries no pull request labels, so a history comparison
  would fail every merged `adr-correction`. If a push does trigger the action, it runs only the
  checks on the files and the `proposed` check.

The action installs the tool from its own checkout (the files the runner fetched for `uses:`), so
the code that runs is the commit the tag points at. Rulesets in this repository stop anyone moving
or deleting a release tag (`vX.Y.Z`), and stop anyone but the release App creating one.
[Repository settings](#repository-settings) gives their limits. The action uses
[astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) to provide uv.

#### Action inputs

Every input has a default taken from the `github` context. You normally set none of them.

| Input             | Default                                                                       | Purpose                                                 |
| ----------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------- |
| `adr-dir`         | `docs/adr`                                                                    | Directory that holds the ADRs                           |
| `base-ref`        | `origin/<base branch>` on a pull request, empty on a push                     | Ref to compare with. A push ignores it                  |
| `merging-to-main` | `true` for a pull request into the default branch or a push to it, else false | Whether `status: proposed` fails the run                |
| `labels`          | The pull request's label names, as JSON                                       | Labels on the PR. `adr-correction` allows a body change |

Set `merging-to-main` yourself only to override the default, for example in a repository whose
release branch is not the default branch.

### Command line

```bash
adr-check [--mode {local,ci}] [--adr-dir DIR] [--base-ref REF] [--labels LABELS] [--merging-to-main]
```

| Flag                | Default       | Purpose                                                               |
| ------------------- | ------------- | --------------------------------------------------------------------- |
| `--mode`            | `local`       | `local` checks the working tree. `ci` also compares with the base ref |
| `--adr-dir`         | `docs/adr`    | ADR directory                                                         |
| `--base-ref`        | `origin/main` | `ci` only. Ref to compare with. It needs full history                 |
| `--labels`          | none          | `ci` only. PR labels as a JSON array or a comma-separated list        |
| `--merging-to-main` | off           | Fail any ADR with `status: proposed`                                  |

The command prints one line per problem to stderr. It exits 0 when every rule holds, 1 when a rule
is broken and 2 when the base ref is missing or the directory is not in a git repository.

In `ci` mode, the no-reused-numbers check compares with the tip of the base ref. The other history
checks compare with the merge base of the base ref and `HEAD`. Git finds renames with
`git diff --name-status -M`, which detects a rename only when the file is mostly unchanged. A
renumbering repair always is.

## Development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync             # create .venv and install the package with its dev dependencies
pre-commit install  # one-time, sets up the pre-commit and commit-msg hooks
```

`uv sync` also installs an interpreter if no suitable one is present. `requires-python` is a lower
bound rather than a pin, so 3.14 is the floor and uv may select something newer. A project that
needs an exact interpreter pins it in a `.python-version` file, which uv reads.

| Task                       | Command                      |
| -------------------------- | ---------------------------- |
| Run the tests              | `uv run pytest`              |
| Lint                       | `uv run ruff check .`        |
| Format                     | `uv run ruff format .`       |
| Type check                 | `uv run pyrefly check src`   |
| Run the tool               | `uv run adr-check --help`    |
| Everything the hooks check | `pre-commit run --all-files` |

### Tests and coverage

`uv run pytest` runs the suite with coverage already on, so the command above and the one
`tests.yml` runs in CI are the same run. Coverage is measured over `src/` and reported to
[Codecov](https://about.codecov.io). `pytest` never fails on a coverage number. The targets live in
`codecov.yml`: the project must not regress by more than 1%, and a pull request's changed lines need
80% coverage.

Type checking names the path, `pyrefly check src`, so it skips `tests/` (deliberately unannotated)
and `scripts/` (repository tooling that the template owns and Ruff also skips).

### Repository settings

`scripts/bootstrap_repo.py` applies the branch protection, merge settings and Actions permissions
that release-please needs. It prints a plan and changes nothing until you pass `--apply`. Read the
plan first, because it replaces an existing ruleset wholesale.

```bash
python3 scripts/bootstrap_repo.py            # what it would change
python3 scripts/bootstrap_repo.py --apply    # change it
```

Two more rulesets protect release tags (`v*.*.*`). "protect release tags" blocks moving or deleting
one, with no bypass. "release tags come from the release bot" blocks creating one, except by the
release App. The App's key is a secret of the `release` environment, which deploys only from `main`,
so only the release-please job on `main` can mint the token here. That holds only while no other
secret holding the same key reaches a workflow: an organisation secret shared with this or another
repository would let that workflow mint the token too. A repository admin can also change or disable
either ruleset. Pin the action to a commit SHA if you need a guarantee that rests on neither. The
script does not manage these rulesets. Floating tags such as `v0` stay movable.

`release-please.yml` authenticates as a GitHub App, because a pull request opened with
`GITHUB_TOKEN` triggers no workflows and the required checks would never report on the release PR.
Create an App with Contents, Issues and Pull requests write permissions, install it on the
repository, then store its client ID as the variable `RELEASE_BOT_CLIENT_ID` and its private key as
the secret `RELEASE_BOT_PRIVATE_KEY` of a `release` environment whose deployment branches are
limited to `main`. There is deliberately no fallback to `GITHUB_TOKEN`.

## Releases

[release-please](https://github.com/googleapis/release-please) reads the Conventional Commits landed
on `main` and keeps an open release PR that bumps the version and updates `CHANGELOG.md`. Merging
that PR tags the version and publishes the GitHub release. The `publish` job in `release-please.yml`
then builds the package and uploads it to PyPI.

The release type is `python`, so release-please bumps the version in `pyproject.toml`, and an
`extra-files` entry keeps the project's own version in `uv.lock` in step. Without it the release PR
would fail `uv sync --locked`. The filter matches the package by name (`adr-check`), so rename the
package and it has to change in the same commit.

Tags have no component prefix (`v0.2.0`, not `adr-check-v0.2.0`), because `include-component-in-tag`
is `false`.

### Publishing

The `publish` job uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no PyPI
token is stored. Register a trusted publisher on PyPI for this repository with the workflow name
`release-please.yml` and the environment `pypi`, and create a `pypi` environment on GitHub. Renaming
either side breaks the match.

## Licence

[MIT](LICENSE).
