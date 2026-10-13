"""Checks that compare the working tree with the base branch."""

import re
import subprocess
from collections import defaultdict
from collections.abc import Collection
from pathlib import Path

from adr_check.adr import (
    AdrFile,
    is_candidate,
    number_of,
    parse_text,
    slug_of,
)

CORRECTION_LABEL = "adr-correction"


class BaseRefError(Exception):
    """The base ref cannot be used, so the history checks cannot run."""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603  # fixed git binary, arguments are not shell-parsed
        ["git", "-C", str(repo), *args],  # noqa: S607  # git is resolved from PATH on purpose
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise BaseRefError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def repo_root() -> Path:
    """Return the top of the git repository containing the current directory."""
    try:
        return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    except BaseRefError as error:
        raise BaseRefError("not inside a git repository, which ci mode needs") from error


def _numbers_at(repo: Path, rev: str, rel_dir: str) -> dict[int, list[str]]:
    out = _git(repo, "ls-tree", "--name-only", "-z", rev, f"{rel_dir}/")
    numbers: dict[int, list[str]] = defaultdict(list)
    for path in out.split("\0"):
        name = path.rsplit("/", 1)[-1]
        number = number_of(name)
        if number is not None:
            numbers[number].append(name)
    return numbers


def _is_top_level(path: str, rel_dir: str) -> bool:
    """Return whether `path` is directly in the ADR directory, as `load_tree` reads it."""
    return Path(path).parent == Path(rel_dir)


def _changes(repo: Path, base_ref: str, rel_dir: str) -> list[tuple[str, str, str]]:
    """Return (status letter, old path, new path) for each changed ADR candidate."""
    out = _git(repo, "diff", "--name-status", "-M", "-z", f"{base_ref}...HEAD", "--", f"{rel_dir}/")
    tokens = out.split("\0")
    changes: list[tuple[str, str, str]] = []
    index = 0
    while index < len(tokens) and tokens[index]:
        letter = tokens[index][0]
        width = 2 if letter in "RC" else 1
        paths = tokens[index + 1 : index + 1 + width]
        index += 1 + width
        old, new = paths[0], paths[-1]
        in_old, in_new = _is_top_level(old, rel_dir), _is_top_level(new, rel_dir)
        if in_old and not in_new:
            letter, new = "D", old  # moved into a subdirectory: the ADR is gone from the list
        elif in_new and not in_old:
            letter, old = "A", new  # moved out of a subdirectory: it is a new ADR
        elif not in_old:
            continue
        if is_candidate(old.rsplit("/", 1)[-1]) or is_candidate(new.rsplit("/", 1)[-1]):
            changes.append((letter, old, new))
    return changes


def _show(repo: Path, rev: str, path: str) -> AdrFile:
    adr, _ = parse_text(path, _git(repo, "show", f"{rev}:{path}"))
    return adr


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _is_retarget(old: object, new: object, renumbered: dict[int, int]) -> bool:
    """Return whether `new` only repoints renumbered ADRs in `old` at their new numbers."""
    before, after = _as_list(old), _as_list(new)
    if len(before) != len(after):
        return False
    return all(
        b == a or (isinstance(b, int) and renumbered.get(b) == a)
        for b, a in zip(before, after, strict=True)
    )


def _frontmatter_change_allowed(
    old: dict[str, object], new: dict[str, object], renumbered: dict[int, int]
) -> bool:
    keys = old.keys() | new.keys()
    flip_keys = {"status", "superseded_by"}
    rest_same = all(old.get(k) == new.get(k) for k in keys - flip_keys)
    if (
        rest_same
        and old.get("status") == "accepted"
        and new.get("status") == "superseded"
        and old.get("superseded_by") is None
        and isinstance(new.get("superseded_by"), int)
    ):
        return True
    pointer_keys = {"supersedes", "superseded_by"}
    return (
        bool(renumbered)
        and all(old.get(k) == new.get(k) for k in keys - pointer_keys)
        and all(_is_retarget(old.get(k), new.get(k), renumbered) for k in pointer_keys)
    )


def _renumber_problems(old: AdrFile, new: AdrFile, mb_numbers: dict[int, list[str]]) -> list[str]:
    """Return why a rename is not the renumbering repair, or nothing when it is."""
    if old.number is None or new.number is None:
        return [f"{new.path}: renamed from {old.path}, which is not an ADR rename the check allows"]
    where = f"{new.path}: renamed from {old.name}"
    if old.number == new.number or slug_of(old.name) != slug_of(new.name):
        return [f"{where}. Only the number in the filename may change, and ADRs are never renamed"]
    if len(mb_numbers.get(old.number, [])) < 2:
        return [f"{where}, but {old.number:04d} is not a duplicated number on main"]
    if old.raw is None or new.raw is None or old.raw != new.raw:
        return [f"{where}. A renumbering repair changes no frontmatter"]
    renumbered = re.sub(
        rf"^# {old.number:04d}\.", f"# {new.number:04d}.", old.body, count=1, flags=re.MULTILINE
    )
    if renumbered != new.body:
        return [f"{where}. A renumbering repair changes only the H1 number"]
    return []


def check_against_base(
    repo: Path,
    rel_dir: str,
    base_ref: str,
    labels: Collection[str],
) -> list[str]:
    """Compare the ADRs in HEAD with `base_ref` and return every rule they break.

    Raises:
        BaseRefError: `base_ref` is missing or shares no history with HEAD.
    """
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}")
    except BaseRefError as error:
        raise BaseRefError(
            f"base ref {base_ref!r} not found. Check out the caller repo with `fetch-depth: 0` "
            "so the base branch is available"
        ) from error
    try:
        merge_base = _git(repo, "merge-base", base_ref, "HEAD").strip()
    except BaseRefError as error:
        raise BaseRefError(
            f"HEAD and {base_ref!r} share no history. Check out with `fetch-depth: 0`"
        ) from error

    tip_numbers = _numbers_at(repo, base_ref, rel_dir)
    mb_numbers = _numbers_at(repo, merge_base, rel_dir)
    changes = _changes(repo, base_ref, rel_dir)
    problems: list[str] = []

    renumbered: dict[int, int] = {}
    for letter, old_path, new_path in changes:
        if letter != "R":
            continue
        if (repo / new_path).is_symlink():
            continue  # load_tree reports it, and reading it would follow the link
        old, new = _show(repo, merge_base, old_path), _read(repo, new_path)
        found = _renumber_problems(old, new, mb_numbers)
        problems.extend(found)
        if not found and old.number is not None and new.number is not None:
            renumbered[old.number] = new.number

    for letter, old_path, new_path in changes:
        name = new_path.rsplit("/", 1)[-1]
        if letter == "D":
            problems.append(f"{old_path}: ADRs are never deleted")
        elif letter in "AR":
            number = number_of(name)
            if number in tip_numbers:
                problems.append(
                    f"{new_path}: number {number:04d} is already used on {base_ref} by "
                    f"{', '.join(tip_numbers[number])}. Renumber this ADR"
                )
        elif letter == "M" and not (repo / new_path).is_symlink():
            problems.extend(_modified_problems(repo, merge_base, new_path, labels, renumbered))
        if letter not in "ADRM":
            problems.append(f"{new_path}: unexpected change type {letter!r}")
    return problems


def _read(repo: Path, path: str) -> AdrFile:
    adr, _ = parse_text(path, (repo / path).read_text(encoding="utf-8"))
    return adr


def _modified_problems(
    repo: Path, merge_base: str, path: str, labels: Collection[str], renumbered: dict[int, int]
) -> list[str]:
    old, new = _show(repo, merge_base, path), _read(repo, path)
    if old.raw is not None and old.raw.get("status") == "proposed":
        return []
    if old.raw is None:
        return [f"{path}: the version on main has unreadable frontmatter, so it cannot be compared"]
    problems: list[str] = []
    if old.body != new.body and CORRECTION_LABEL not in labels:
        problems.append(
            f"{path}: the body of an ADR on main never changes. Write a superseding ADR, or for "
            f"a typo or link fix label the PR `{CORRECTION_LABEL}`"
        )
    if new.raw is not None and old.raw != new.raw:
        if not _frontmatter_change_allowed(old.raw, new.raw, renumbered):
            problems.append(
                f"{path}: frontmatter of an ADR on main may change only from `accepted` to "
                "`superseded` with `superseded_by`, or to retarget a renumbered ADR. The "
                f"`{CORRECTION_LABEL}` label does not allow it"
            )
    return problems
