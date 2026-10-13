# python-simple-template

The template every new single-package Python repository is created from (GitHub's "Use this
template"). It is created from base-template and adds the Python toolchain on top: everything in
that template — pre-commit, Markdown formatting and linting, Conventional Commits, secret scanning,
PR conventions — still applies and is not repeated here.

For a repository that holds several packages released on their own versions, use
python-monorepo-template instead. This one is deliberately the simpler shape: one package, one
version, one changelog.

What this template adds:

- **Project layout** — one [uv](https://docs.astral.sh/uv/) package at `src/hello_world/`, with
  `tests/` alongside it. See [Layout](#layout).
- **Python 3.14 or newer** — the minimum is declared once, as `requires-python` in `pyproject.toml`.
  Ruff infers its `target-version` from it, so the two cannot drift apart.
- **Ruff** — lint and format, configured in `pyproject.toml`.
- **Pyrefly** — type checking under `preset = "strict"`, configured in `pyproject.toml`.
- **pytest with coverage** — the suite runs on every pull request and has to pass before a merge;
  coverage goes to Codecov, with the target in `codecov.yml`. See
  [Tests and coverage](#tests-and-coverage).
- **Coding standard** — the Ruff and Pyrefly configuration *is* the standard: rule selection, line
  length, quote style and the strict preset all live in `pyproject.toml`. See
  [Python](AGENTS.md#python).

## Layout

```text
pyproject.toml        the package: its metadata, dependencies and all tool config
uv.lock               the resolved dependency set, committed
src/hello_world/      the package's code
tests/                the test suite, mirroring src/ by module name
scripts/              repository tooling, not part of the package
```

The repository **is** the package. There is no workspace and no nesting: `pyproject.toml` at the
root carries both the `[project]` metadata and the shared tool configuration, and `uv sync` installs
it editable into `.venv`.

The `src/` layout is deliberate. The package is importable only because it is installed, so the
tests exercise what a consumer would get rather than whatever happens to sit in the working
directory.

The example package is `hello_world`, and it exists to prove the wiring end to end. Replace it with
your own:

1. Rename `src/hello_world/` and the matching test modules.
1. Change `name` and `description` under `[project]`, and the `[project.scripts]` entry.
1. Change `known-first-party` under `[tool.ruff.lint.isort]` to the new package name.
1. Update the `uv.lock` `jsonpath` in `release-please-config.json`.
1. Run `uv lock` and commit the result.

A test module is named after the module it covers, so the mapping stays obvious without mirroring
directories:

```text
src/hello_world/greeting.py  ->  tests/test_greeting.py
src/hello_world/cli.py       ->  tests/test_cli.py
```

`tests/` needs no `__init__.py` files. A monorepo needs them, because mirroring several packages
means two of them can each have a `test_cli.py` and pytest needs distinct dotted names to tell those
apart. One flat directory of uniquely-named modules has no such collision.

## Setup

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
| Run the example app        | `uv run hello-world Ada`     |
| Everything the hooks check | `pre-commit run --all-files` |

### Tests and coverage

`uv run pytest` runs the suite with coverage already on: the flags live in `addopts`, so the command
above and the one `tests.yml` runs in CI are the same run. Coverage is measured over `src/` by
directory rather than by import name, so a module no test imports is reported at 0% instead of being
absent from the total.

`include_namespace_packages` is what makes that true below the top level. Coverage descends only
through directories holding an `__init__.py`, so a module in a namespace subpackage would otherwise
be missing from `coverage.xml` entirely — and a wholly untested one would leave the total reading
100% with nothing to notice.

Nothing in `pyproject.toml` says how much coverage is enough, and `uv run pytest` never fails on a
coverage number. The target lives in `codecov.yml` at the repository root, and that file is the only
place to change it. Two targets, because they answer different questions:

| Status            | Target      | What it asks                                                |
| ----------------- | ----------- | ----------------------------------------------------------- |
| `codecov/project` | `auto`, ±1% | Does the whole repo still cover as much as the base commit? |
| `codecov/patch`   | 80%         | Are the lines this PR adds or changes tested?               |

`auto` on the project status means "do not regress", so there is no figure to re-agree as a repo
grows; the 1% threshold absorbs the fraction of a point a refactor moves without changing what is
tested. The patch target is a fixed 80 because it asks the same thing of every pull request whatever
the repo's total — enough that new code arrives with tests, loose enough for an error path that is
awkward to reach.

CI uploads `coverage.xml` to [Codecov](https://about.codecov.io). A repository created from this
template is private, so tokenless upload does not work: the job reads a `CODECOV_TOKEN` secret, set
once for the organisation. The upload step fails the job when it cannot upload rather than passing
quietly and leaving Codecov reporting against an older commit.

**Set that secret before the first pull request.** `pytest` is a required check and the upload runs
inside it, so with the secret unset the job fails, the check never goes green, and nothing can merge
-- including the very first PR in a new repo. Settings -> Secrets and variables -> Actions.

Read the two gates apart, because they fail in different places. `pytest` is the workflow job: it
goes red when a test fails. `codecov/project` and `codecov/patch` are commit statuses the Codecov
app posts after the upload, and they go red when coverage is under target while the workflow job
stays green. Only `pytest` is a required check — the Codecov statuses have to report at least once
before they can be required, or a status that never arrives blocks every pull request.

`pytest`'s context name is the **job id** in `tests.yml`, not the workflow name, and
`scripts/bootstrap_repo.py` lists that same string. Rename one without the other and the check never
reports, which blocks every pull request instead.

### Type checking names `src` explicitly

`pyrefly check src`, not a bare `pyrefly check`. Pyrefly's project mode picks up every Python file
under the root, which here means `scripts/` and `tests/` as well as the package — 39 errors against
the package's 0, and not one of them a defect in the code being checked.

Neither directory is meant to be checked. `scripts/` belongs to base-template (see
[`scripts/` is not checked here](#scripts-is-not-checked-here)), and `tests/` is deliberately
unannotated, which the Ruff configuration already states as a per-file ignore. Naming the path is
the Pyrefly equivalent of both exclusions.

Passing a path does not weaken the check: `preset = "strict"` still applies, confirmed by an
unannotated parameter being reported under `strict` and not under `basic`.

### `scripts/` is not checked here

`scripts/bootstrap_repo.py` and its tests arrive with base-template and are linted and type-checked
there. Ruff skips them through `extend-exclude`, and Pyrefly skips them by being given `src`.

Checking them again here would only invite a local fix that then diverges from upstream, making the
next template sync a conflict rather than a fast-forward. The Ruff exclusion is written as
`scripts/**` rather than `scripts`: a bare path segment matches at any depth, which would also
un-lint a `scripts/` subpackage inside `src/`.

## Repository settings

"Use this template" copies files and nothing else, so a new repo starts with no branch protection,
merge settings at GitHub's defaults, and the Actions permission release-please needs to open its
release PR switched off. `scripts/bootstrap_repo.py` applies them. It prints a plan and changes
nothing until you pass `--apply`.

Read the plan before applying it. An existing ruleset is replaced wholesale, so the plan diffs the
repo's policy against the template's: a `-` line is policy this repo has and the template does not,
and applying loses it. A repo that has added its own required check will see it there.

The diff covers every field the template states. A ruleset field the template says nothing about
reverts to GitHub's default when the ruleset is replaced, and the plan cannot show that.

```bash
python3 scripts/bootstrap_repo.py            # what it would change
python3 scripts/bootstrap_repo.py --apply    # change it
```

### Release bot (GitHub App)

`release-please.yml` authenticates as a GitHub App rather than with `GITHUB_TOKEN`, because a pull
request opened with `GITHUB_TOKEN` triggers no workflows: the checks the ruleset requires would
never report on the release PR, and it could never merge.

**Do this before merging anything that runs the workflow.** There is deliberately no fallback to
`GITHUB_TOKEN` — a silent downgrade would reintroduce the unmergeable release PR — so until the App
exists and both credentials are set, every push to `main` fails at the token step.

1. Create the App under the organisation: Settings → Developer settings → GitHub Apps → New. It
   needs no webhook and no callback URL.
1. Grant it exactly three repository permissions: **Contents** write, **Issues** write, **Pull
   requests** write. Nothing else.
1. Install it (App settings → Install App) on the repositories that cut releases.
1. Generate a private key (App settings → Private keys) and download the `.pem`.
1. Store both credentials on the repository, under Settings → Secrets and variables → Actions:
   `RELEASE_BOT_CLIENT_ID` as a **variable**, and `RELEASE_BOT_PRIVATE_KEY` as a **secret** holding
   the whole `.pem`, `BEGIN` and `END` lines included.

The token is narrowed three times over, and the middle one is the one that gets missed:

- The App's own permissions are the ceiling. It can never mint a token holding more than the three
  granted in step 2, whatever a workflow asks for.
- `permission-contents`, `permission-issues` and `permission-pull-requests` on the token step narrow
  each run to release-please's documented minimum. Omit them and the token inherits **every**
  permission the installation holds — the ceiling becomes the grant.
- No `owner` or `repositories` input, so the token reaches only the repository running the workflow.
  The action revokes it when the job finishes, and it expires within the hour regardless.

`permissions: {}` at the top of the workflow then leaves `GITHUB_TOKEN` itself with nothing, since
the App token does all the work.

## Releases

[release-please](https://github.com/googleapis/release-please) reads the Conventional Commits landed
on `main` and keeps an open release PR that bumps the version and updates `CHANGELOG.md`. Merging
that PR tags the version and publishes the GitHub release.

The release type is `python`, so the version release-please bumps is the one in `pyproject.toml`.
There is no `version.txt`: that file belongs to base-template's language-agnostic `simple` type and
is deleted here, because a file no release type updates sits frozen at whatever version it stopped
being bumped on and quietly contradicts the real one.

One package means one version, one changelog and one release PR. `separate-pull-requests` is already
effectively on — release-please defaults it to true when the config holds a single package — so
there is nothing to set, and no per-package block to keep in step.

There is deliberately no `package-name`. Setting it would give the package a *component*, which
release-please carries into the tag (`hello-world-v0.2.0` rather than `v0.2.0`), the release name,
the pull request title and the release branch. A single-package repo wants none of that. The
`python` release type reads the project name from `pyproject.toml` regardless, so the field buys
nothing here. Add a second package and the calculation changes: components stop being noise and
start being how the two are told apart.

### Why `uv.lock` needs an `extra-files` entry

`uv.lock` records the project's own version alongside its dependencies:

```toml
[[package]]
name = "hello-world"
version = "0.1.0"
source = { editable = "." }
```

The `python` release type writes `CHANGELOG.md` and bumps `pyproject.toml` — plus `setup.py`,
`setup.cfg`, a `__version__` in `__init__.py` and any `version.py`, where those exist; it logs and
skips the ones that do not. `uv.lock` is on none of those lists, so without the `extra-files` entry
the release PR would leave the lock behind at the previous version. Both CI workflows run
`uv sync --locked`, which fails when the lock and `pyproject.toml` disagree — so the release PR
would fail its own required checks and could never merge.

The entry addresses that one field by name:

```json
{ "path": "/uv.lock", "type": "toml",
  "jsonpath": "$.package[?(@.name.value=='hello-world')].version" }
```

The leading `/` is relative to the repository root, and the `jsonpath` filter matches the package by
name rather than by position, so it keeps working when a dependency is added and the entry moves.

Rename the package and this string has to change with it, in the same commit — the filter matches on
a literal name, so a rename without it silently stops updating the lock and the first release after
that fails `uv sync --locked`.

The
[manifest releaser docs](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md)
cover the full set of options.

## Keeping up with the template

"Use this template" copies the files once and keeps no link, so nothing here reaches a repo already
created from it. Picking up a later change is a manual diff, by choice: an automatic sync would have
to decide what to do about a hook version someone bumped or a section someone added, and getting
that wrong silently is worse than not having it.

To see what a repo is missing:

```bash
git remote add template https://github.com/agentic-delivery-au/python-simple-template.git
git fetch template
git diff HEAD template/main -- .github .pre-commit-config.yaml AGENTS.md CLAUDE.md \
  .editorconfig .gitattributes .markdownlint.jsonc .markdownlintignore .mdformat.toml \
  .betterleaks.toml pyproject.toml codecov.yml ':(exclude).github/CODEOWNERS' \
  ':(exclude).github/dependabot.yml'
```

Read it as "what taking everything would do": `+` is what the template would add, and `-` is what it
would take away — your own edits, and any hook you have already bumped past the template. Take what
applies and leave the rest. Working from your own copy of the template rather than this one? Point
the remote at that copy.

`pyproject.toml` is in the pathspec because the `[tool.*]` blocks are template content, but the
`[project]` block and the dependencies are yours. Read that file's diff for the tool configuration
only.

The pathspec leaves out what is per-repo by design, so the diff stays worth reading: `README.md`,
`LICENSE`, `SECURITY.md`, the release config, `src/` and `tests/` are simply not listed, and
`.github/CODEOWNERS` and `.github/dependabot.yml` are excluded from `.github` explicitly. The
template's version of each holds a placeholder or a language choice, never something to adopt.

A hook rev that is newer downstream is not drift. `pre-commit autoupdate` is how it is meant to be
bumped; a repo that is ahead should stay ahead, and the template should catch up.
