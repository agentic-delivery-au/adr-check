"""Parse ADR files and run the checks that need only the files in front of you."""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

STATUSES = ("proposed", "accepted", "rejected", "superseded")
KEYS = ("status", "date", "supersedes", "superseded_by")
SECTIONS = ("Context", "Considered options", "Decision", "Consequences")

_FILENAME = re.compile(r"^(\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
_H1 = re.compile(r"^(\d{4})\. \S")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True)
class Meta:
    """Validated frontmatter of one ADR."""

    status: str
    date: date
    supersedes: tuple[int, ...]
    superseded_by: int | None


@dataclass(frozen=True)
class AdrFile:
    """One ADR file, parsed as far as it parses.

    `number` comes from the filename and is None when the name is not `NNNN-kebab-title.md`.
    `raw` is the frontmatter as written, and `meta` is None when it failed validation.
    """

    path: str
    name: str
    number: int | None
    raw: dict[str, object] | None
    meta: Meta | None
    body: str


Resolver = Callable[[AdrFile, int, str], AdrFile | None]


def is_candidate(name: str) -> bool:
    """Return whether a file in the ADR directory is meant to be an ADR.

    The directory may also hold a README or other non-Markdown files. Every other Markdown file is
    checked, so a badly named ADR fails rather than being ignored.
    """
    return name.endswith(".md") and name.lower() != "readme.md"


def number_of(name: str) -> int | None:
    """Return the number in an ADR filename, or None if the name is not well formed."""
    match = _FILENAME.match(name)
    return int(match.group(1)) if match else None


def slug_of(name: str) -> str | None:
    """Return the kebab-case title in an ADR filename, or None if the name is not well formed."""
    match = _FILENAME.match(name)
    return match.group(2) if match else None


def split_document(text: str) -> tuple[str | None, str]:
    """Split a document into its frontmatter text and body.

    The frontmatter is None when the file does not open with a closed `---` block.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != "---":
        return None, "\n".join(lines)
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None, "\n".join(lines)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_meta(raw: dict[str, object]) -> tuple[Meta | None, list[str]]:
    problems: list[str] = []
    for key in KEYS:
        if key not in raw:
            problems.append(f"frontmatter is missing the key `{key}`")
    problems.extend(
        f"frontmatter has the key `{key}`, which is not one of {', '.join(KEYS)}"
        for key in raw
        if key not in KEYS
    )
    if problems:
        return None, problems

    status = raw["status"]
    if status not in STATUSES:
        problems.append(f"`status` must be one of {', '.join(STATUSES)}, not {status!r}")

    raw_date = raw["date"]
    parsed: date | None = None
    if type(raw_date) is date:
        parsed = raw_date
    elif isinstance(raw_date, str) and _ISO_DATE.match(raw_date):
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            parsed = None
    if parsed is None:
        problems.append(f"`date` must be an ISO date such as 2026-03-12, not {raw_date!r}")

    raw_supersedes = raw["supersedes"]
    supersedes: tuple[int, ...] = ()
    if raw_supersedes is None:
        pass
    elif isinstance(raw_supersedes, list) and all(_is_int(item) for item in raw_supersedes):
        supersedes = tuple(item for item in raw_supersedes if isinstance(item, int))
    else:
        problems.append("`supersedes` must be a list of ADR numbers such as [7], or empty")

    superseded_by = raw["superseded_by"]
    if superseded_by is not None and not _is_int(superseded_by):
        problems.append("`superseded_by` must be one ADR number such as 15, or empty")

    if problems or parsed is None or not isinstance(status, str):
        return None, problems
    by = superseded_by if isinstance(superseded_by, int) else None
    return Meta(status, parsed, supersedes, by), []


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_COMMENT_START = re.compile(r"^ {0,3}<!--")


def _headings(body: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    in_comment = False
    for line in body.split("\n"):
        if in_comment:
            # CommonMark: an HTML comment block runs to the first line holding `-->`, or to EOF.
            in_comment = "-->" not in line
            continue
        if fence is None and _COMMENT_START.match(line):
            in_comment = "-->" not in line[line.index("<!--") :]
            continue
        line = _COMMENT.sub("", line)
        match = _FENCE.match(line)
        if match:
            run, rest = match.groups()
            if fence is None:
                # CommonMark: a backtick fence's info string cannot hold a backtick.
                if run[0] != "`" or "`" not in rest:
                    fence = (run[0], len(run))
                continue
            if run[0] == fence[0] and len(run) >= fence[1] and not rest.strip():
                fence = None
                continue
        if fence:
            continue
        heading = re.match(r"^(#{1,6}) +(.*?) *#*$", line)
        if heading:
            headings.append((len(heading.group(1)), heading.group(2)))
    return headings


def parse_text(path: str, text: str) -> tuple[AdrFile, list[str]]:
    """Parse one ADR and return it with the problems found in that file alone."""
    name = path.rsplit("/", 1)[-1]
    number = number_of(name)
    problems: list[str] = []
    if number is None:
        problems.append("filename must look like NNNN-kebab-title.md, for example 0007-use-x.md")

    front, body = split_document(text)
    raw: dict[str, object] | None = None
    meta: Meta | None = None
    if front is None:
        problems.append("file must open with a frontmatter block between `---` lines")
    else:
        try:
            loaded: object = yaml.safe_load(front)
        except (yaml.YAMLError, ValueError, OverflowError) as error:
            # PyYAML raises ValueError for an unquoted impossible date such as 2026-02-30.
            loaded = None
            problems.append(f"frontmatter is not valid YAML: {str(error).partition('\n')[0]}")
        else:
            if isinstance(loaded, dict) and all(isinstance(key, str) for key in loaded):
                raw = {str(key): value for key, value in loaded.items()}
                meta, meta_problems = _validate_meta(raw)
                problems.extend(meta_problems)
            else:
                problems.append("frontmatter must be a mapping of the four keys")

    problems.extend(_check_body(number, body))
    return AdrFile(path, name, number, raw, meta, body), [f"{path}: {p}" for p in problems]


def _check_body(number: int | None, body: str) -> list[str]:
    problems: list[str] = []
    headings = _headings(body)
    h1s = [text for level, text in headings if level == 1]
    if not h1s:
        problems.append("missing the H1 title, for example `# 0007. Use managed identities`")
    else:
        match = _H1.match(h1s[0])
        if not match:
            problems.append(f"H1 must look like `# 0007. Title`, not `# {h1s[0]}`")
        elif number is not None and int(match.group(1)) != number:
            problems.append(
                f"H1 number {match.group(1)} does not match filename number {number:04d}"
            )
    present = {text for level, text in headings if level == 2}
    problems.extend(f"missing the `## {s}` section" for s in SECTIONS if s not in present)
    return problems


def load_tree(adr_dir: Path, display_dir: str) -> tuple[list[AdrFile], list[str]]:
    """Read every ADR in `adr_dir` and return them with the per-file problems."""
    files: list[AdrFile] = []
    problems: list[str] = []
    if not adr_dir.is_dir():
        return files, problems
    for entry in sorted(adr_dir.iterdir()):
        path = f"{display_dir}/{entry.name}"
        if entry.is_symlink() and is_candidate(entry.name):
            problems.append(f"{path}: is a symlink. An ADR must be a regular file")
            continue
        if not entry.is_file() or not is_candidate(entry.name):
            continue
        try:
            text = entry.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"{path}: file is not valid UTF-8")
            continue
        adr, found = parse_text(path, text)
        files.append(adr)
        problems.extend(found)
    return files, problems


def check_tree(files: list[AdrFile]) -> list[str]:
    """Check numbering and supersession across every ADR in the working tree."""
    problems: list[str] = []
    by_number: dict[int, list[AdrFile]] = defaultdict(list)
    for adr in files:
        if adr.number is not None:
            by_number[adr.number].append(adr)
    duplicated = {n for n, group in by_number.items() if len(group) > 1}
    for number in sorted(duplicated):
        names = ", ".join(adr.name for adr in by_number[number])
        problems.append(f"{number:04d} is used by more than one ADR: {names}")

    def resolve(adr: AdrFile, target: int, field: str) -> AdrFile | None:
        if target in duplicated:
            problems.append(
                f"{adr.path}: `{field}` names {target:04d}, which is a duplicated number, "
                "so it is ambiguous"
            )
            return None
        if target not in by_number:
            problems.append(f"{adr.path}: `{field}` names {target:04d}, which does not exist")
            return None
        return by_number[target][0]

    for adr in files:
        meta = adr.meta
        if meta is None or adr.number is None:
            continue
        for target in meta.supersedes:
            _check_predecessor(adr, adr.number, target, resolve, problems)
        _check_successor(adr, adr.number, meta, resolve, problems)
    return problems


def _check_predecessor(
    adr: AdrFile, number: int, target: int, resolve: Resolver, problems: list[str]
) -> None:
    if target == number:
        problems.append(f"{adr.path}: `supersedes` names the ADR itself")
        return
    old = resolve(adr, target, "supersedes")
    if old is None or old.meta is None:
        return
    if old.meta.status != "superseded" or old.meta.superseded_by != number:
        problems.append(
            f"{adr.path}: supersedes {target:04d}, but {old.name} must have `status: superseded` "
            f"and `superseded_by: {number}`"
        )


def _check_successor(
    adr: AdrFile, number: int, meta: Meta, resolve: Resolver, problems: list[str]
) -> None:
    if meta.status == "superseded" and meta.superseded_by is None:
        problems.append(f"{adr.path}: `status: superseded` needs `superseded_by`")
    if meta.superseded_by is None:
        return
    if meta.status != "superseded":
        problems.append(
            f"{adr.path}: `superseded_by` is set, so `status` must be `superseded`, "
            f"not `{meta.status}`"
        )
    if meta.superseded_by == number:
        problems.append(f"{adr.path}: `superseded_by` names the ADR itself")
        return
    successor = resolve(adr, meta.superseded_by, "superseded_by")
    if successor is None or successor.meta is None:
        return
    if successor.meta.status == "rejected":
        problems.append(
            f"{adr.path}: superseded by {successor.name}, which is rejected. A rejected ADR "
            "leaves the ADR it proposed to replace untouched"
        )
    if number not in successor.meta.supersedes:
        problems.append(
            f"{adr.path}: superseded by {successor.name}, whose `supersedes` must include {number}"
        )


def check_no_proposed(files: list[AdrFile]) -> list[str]:
    """Fail every ADR still `proposed`, for a run that merges to main."""
    return [
        f"{adr.path}: `status: proposed` cannot reach main. Set accepted, rejected or superseded"
        for adr in files
        if adr.meta is not None and adr.meta.status == "proposed"
    ]
