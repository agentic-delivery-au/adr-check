"""Command line entry point for adr-check."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from adr_check.adr import check_no_proposed, check_tree, load_tree
from adr_check.ci import BaseRefError, check_against_base, repo_root

DEFAULT_BASE_REF = "origin/main"


def parse_labels(value: str) -> list[str]:
    """Read labels from a JSON array, as `toJSON` writes them, or a comma-separated list."""
    text = value.strip()
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [item.strip() for item in text.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the adr-check command."""
    parser = argparse.ArgumentParser(
        prog="adr-check",
        description="Check architecture decision records. Exits 1 if any rule is broken.",
    )
    parser.add_argument(
        "--mode",
        choices=("local", "ci"),
        default="local",
        help="local checks the working tree only; ci also compares with the base branch",
    )
    parser.add_argument("--adr-dir", default="docs/adr", help="ADR directory (default: docs/adr)")
    parser.add_argument(
        "--base-ref",
        help=f"ci only: ref to compare with (needs full history) (default: {DEFAULT_BASE_REF})",
    )
    parser.add_argument(
        "--labels",
        help="ci only: PR labels, as a JSON array or comma-separated; `adr-correction` allows a "
        "body change",
    )
    parser.add_argument(
        "--merging-to-main",
        action="store_true",
        help="this run is a PR into main or a push to main, so `proposed` fails",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checks, print each problem to stderr and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    mode: str = args.mode
    adr_dir: str = args.adr_dir.rstrip("/")
    base_ref: str | None = args.base_ref
    labels_arg: str | None = args.labels
    merging: bool = args.merging_to_main
    if mode == "local" and (base_ref or labels_arg):
        parser.error("--base-ref and --labels need --mode ci")
    try:
        labels = parse_labels(labels_arg) if labels_arg else []
    except ValueError as error:
        parser.error(f"--labels is not a JSON array or a comma-separated list: {error}")

    files, problems = load_tree(Path(adr_dir), adr_dir)
    problems.extend(check_tree(files))
    if merging:
        problems.extend(check_no_proposed(files))
    if mode == "ci":
        try:
            root = repo_root()
            rel_dir = Path(adr_dir).resolve().relative_to(root.resolve()).as_posix()
            problems.extend(check_against_base(root, rel_dir, base_ref or DEFAULT_BASE_REF, labels))
        except (BaseRefError, ValueError) as error:
            print(f"adr-check: {error}", file=sys.stderr)
            return 2

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"adr-check: {len(problems)} problem(s) found", file=sys.stderr)
        return 1
    return 0
