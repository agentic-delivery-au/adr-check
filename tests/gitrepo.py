"""A throwaway git repository with an ADR directory, for CI-mode tests."""

import subprocess
from collections.abc import Collection
from pathlib import Path

from adr_check.adr import check_tree, load_tree
from adr_check.ci import check_against_base


class Repo:
    def __init__(self, path: Path) -> None:
        """Create the repository, with an empty `docs/adr`, at `path`."""
        self.path = path
        self.adr_dir = path / "docs" / "adr"
        self.adr_dir.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> None:
        subprocess.run(  # noqa: S603  # fixed git binary and test-controlled arguments
            [  # noqa: S607  # git is resolved from PATH on purpose
                "git",
                "-C",
                str(self.path),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            check=True,
            capture_output=True,
        )

    def write(self, name: str, text: str) -> None:
        (self.adr_dir / name).write_text(text)

    def read(self, name: str) -> str:
        return (self.adr_dir / name).read_text()

    def remove(self, name: str) -> None:
        (self.adr_dir / name).unlink()

    def rename(self, old: str, new: str) -> None:
        (self.adr_dir / old).rename(self.adr_dir / new)

    def commit(self, message: str = "change") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def branch(self, name: str = "feature") -> None:
        self.git("checkout", "-q", "-b", name)

    def checkout(self, name: str) -> None:
        self.git("checkout", "-q", name)

    def check(self, labels: Collection[str] = ()) -> list[str]:
        """Return the CI-mode problems for the current branch against main."""
        return check_against_base(self.path, "docs/adr", "main", labels)

    def check_all(self, labels: Collection[str] = ()) -> list[str]:
        """Return the in-tree problems plus the CI-mode ones."""
        files, problems = load_tree(self.adr_dir, "docs/adr")
        return [*problems, *check_tree(files), *self.check(labels)]
