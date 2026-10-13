"""Command line entry point for hello-world."""

import argparse
import sys
from collections.abc import Sequence

from hello_world.greeting import greet


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the hello-world command."""
    parser = argparse.ArgumentParser(prog="hello-world", description="Greet someone.")
    parser.add_argument("name", help="who to greet")
    parser.add_argument("--greeting", default="Hello", help="greeting to use")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write a greeting to stdout and return the process exit code."""
    args = build_parser().parse_args(argv)
    name: str = args.name
    greeting: str = args.greeting
    try:
        print(greet(name, greeting=greeting))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
