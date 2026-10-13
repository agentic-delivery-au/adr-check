import os
from pathlib import Path

import pytest
from adrs import adr, name
from gitrepo import Repo

from adr_check.ci import BaseRefError, check_against_base, repo_root

OLD = name(1, "old")
NEW = name(2, "new")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.write(OLD, adr(1))
    r.write("README.md", "# ADRs\n")
    r.commit("base")
    r.branch()
    return r


def test_unchanged_branch_passes(repo: Repo):
    assert repo.check() == []


def test_new_adr_passes(repo: Repo):
    repo.write(NEW, adr(2, status="proposed"))
    repo.commit()

    assert repo.check_all() == []


def test_readme_changes_are_ignored(repo: Repo):
    repo.write("README.md", "# Changed\n")
    repo.write("notes.txt", "x")
    repo.commit()
    repo.remove("README.md")
    repo.commit()

    assert repo.check() == []


def test_number_already_on_main_fails(repo: Repo):
    repo.write(name(1, "other"), adr(1, title="Other"))
    repo.commit()

    problems = repo.check()

    assert len(problems) == 1
    assert "number 0001 is already used on main by 0001-old.md" in problems[0]


def test_number_taken_by_main_after_branching_fails(repo: Repo):
    repo.checkout("main")
    repo.write(name(2, "main-one"), adr(2))
    repo.commit()
    repo.checkout("feature")
    repo.write(name(2, "branch-one"), adr(2))
    repo.commit()

    problems = repo.check()

    assert any("number 0002 is already used on main by 0002-main-one.md" in p for p in problems)


def test_changes_main_made_since_branching_are_not_blamed_on_the_branch(repo: Repo):
    repo.checkout("main")
    repo.write(OLD, adr(1, title="Fixed on main"))
    repo.commit()
    repo.checkout("feature")
    repo.write(NEW, adr(2))
    repo.commit()

    assert repo.check() == []


def test_body_change_fails(repo: Repo):
    repo.write(OLD, adr(1).replace("We will do it.", "We will not do it."))
    repo.commit()

    problems = repo.check()

    assert len(problems) == 1
    assert "body of an ADR on main never changes" in problems[0]


def test_body_change_passes_with_the_correction_label(repo: Repo):
    repo.write(OLD, adr(1).replace("The situation.", "The situation, fixed."))
    repo.commit()

    assert repo.check(["adr-correction"]) == []
    assert repo.check(["other"]) != []


def test_correction_label_does_not_allow_a_frontmatter_change(repo: Repo):
    repo.write(OLD, adr(1).replace("2026-03-12", "2026-04-01").replace("The situation.", "Typo."))
    repo.commit()

    problems = repo.check(["adr-correction"])

    assert len(problems) == 1
    assert "frontmatter of an ADR on main may change only" in problems[0]
    assert "label does not allow it" in problems[0]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("accepted", "rejected"),
        ("rejected", "accepted"),
        ("superseded", "accepted"),
    ],
)
def test_status_change_other_than_the_flip_fails(tmp_path: Path, before: str, after: str):
    r = Repo(tmp_path)
    by = 9 if before == "superseded" else None
    r.write(OLD, adr(1, status=before, superseded_by=by))
    r.commit("base")
    r.branch()
    r.write(OLD, adr(1, status=after, superseded_by=by))
    r.commit()

    assert any("frontmatter of an ADR on main may change only" in p for p in r.check())


def test_supersession_flip_passes(repo: Repo):
    repo.write(OLD, adr(1, status="superseded", superseded_by=2))
    repo.write(NEW, adr(2, supersedes=[1]))
    repo.commit()

    assert repo.check_all() == []


def test_flip_with_a_body_change_fails(repo: Repo):
    repo.write(
        OLD, adr(1, status="superseded", superseded_by=2).replace("The situation.", "Rewritten.")
    )
    repo.commit()

    assert any("body of an ADR on main never changes" in p for p in repo.check())


def test_flip_that_also_changes_the_date_fails(repo: Repo):
    repo.write(
        OLD, adr(1, status="superseded", superseded_by=2).replace("2026-03-12", "2026-05-05")
    )
    repo.commit()

    assert any("frontmatter of an ADR on main may change only" in p for p in repo.check())


def test_proposed_adr_on_main_may_still_change(tmp_path: Path):
    r = Repo(tmp_path)
    r.write(OLD, adr(1, status="proposed"))
    r.commit("base")
    r.branch()
    r.write(OLD, adr(1, status="accepted").replace("The situation.", "Settled."))
    r.commit()

    assert r.check() == []


def test_delete_fails(repo: Repo):
    repo.remove(OLD)
    repo.commit()

    assert repo.check() == [f"docs/adr/{OLD}: ADRs are never deleted"]


def test_rename_fails(repo: Repo):
    repo.rename(OLD, name(5, "old"))
    repo.write(name(5, "old"), adr(1, h1_number=5))
    repo.commit()

    problems = repo.check()

    assert any("is not a duplicated number on main" in p for p in problems)


def test_rename_to_a_non_adr_name_fails(repo: Repo):
    repo.rename(OLD, "renamed.md")
    repo.commit()

    assert any("not an ADR rename the check allows" in p for p in repo.check())


def test_symlink_replacing_an_adr_fails(repo: Repo):
    repo.remove(OLD)
    os.symlink("README.md", repo.adr_dir / OLD)
    repo.commit()

    assert any("unexpected change type 'T'" in p for p in repo.check())


def test_a_symlinked_adr_added_on_the_branch_is_reported_once(repo: Repo):
    os.symlink(OLD, repo.adr_dir / NEW)
    repo.commit()

    problems = repo.check_all()

    assert problems == [f"docs/adr/{NEW}: is a symlink. An ADR must be a regular file"]


def test_a_dangling_symlink_on_main_edited_on_the_branch_does_not_crash(tmp_path: Path):
    r = Repo(tmp_path)
    os.symlink("gone-1.md", r.adr_dir / OLD)
    r.commit("base")
    r.branch()
    (r.adr_dir / OLD).unlink()
    os.symlink("gone-2.md", r.adr_dir / OLD)
    r.commit()

    assert r.check_all() == [f"docs/adr/{OLD}: is a symlink. An ADR must be a regular file"]


def test_a_symlinked_adr_renamed_on_the_branch_does_not_crash(tmp_path: Path):
    r = Repo(tmp_path)
    r.write(name(3, "first"), adr(3, title="First"))
    os.symlink("gone.md", r.adr_dir / name(3, "second"))
    r.commit("base")
    r.branch()
    r.rename(name(3, "second"), name(5, "second"))
    r.commit()

    problems = r.check_all()

    assert f"docs/adr/{name(5, 'second')}: is a symlink. An ADR must be a regular file" in problems


@pytest.fixture
def duplicated(tmp_path: Path) -> Repo:
    """Main holds two ADRs numbered 0003, and 0004 supersedes the second of them."""
    r = Repo(tmp_path)
    r.write(name(3, "first"), adr(3, title="First"))
    r.write(name(3, "second"), adr(3, status="superseded", superseded_by=4, title="Second"))
    r.write(name(4, "newer"), adr(4, supersedes=[3], title="Newer"))
    r.commit("base")
    r.branch()
    return r


def repair(r: Repo) -> None:
    r.rename(name(3, "second"), name(5, "second"))
    r.write(
        name(5, "second"), adr(3, status="superseded", superseded_by=4, title="Second", h1_number=5)
    )
    r.write(name(4, "newer"), adr(4, supersedes=[5], title="Newer"))


def test_renumbering_repair_passes(duplicated: Repo):
    repair(duplicated)
    duplicated.commit()

    assert duplicated.check_all() == []


def test_the_duplicate_fails_in_tree_before_the_repair(duplicated: Repo):
    files_problems = duplicated.check_all()

    assert any("0003 is used by more than one ADR" in p for p in files_problems)


def test_repair_with_a_body_change_fails(duplicated: Repo):
    repair(duplicated)
    duplicated.write(
        name(5, "second"),
        duplicated.read(name(5, "second")).replace("The situation.", "Changed."),
    )
    duplicated.commit()

    assert any("changes only the H1 number" in p for p in duplicated.check(["adr-correction"]))


def test_repair_with_a_frontmatter_change_fails(duplicated: Repo):
    repair(duplicated)
    duplicated.write(
        name(5, "second"),
        duplicated.read(name(5, "second")).replace("2026-03-12", "2026-06-01"),
    )
    duplicated.commit()

    assert any("changes no frontmatter" in p for p in duplicated.check())


def test_repair_that_changes_the_title_slug_fails(duplicated: Repo):
    duplicated.rename(name(3, "second"), name(5, "renamed"))
    duplicated.write(
        name(5, "renamed"), duplicated.read(name(5, "renamed")).replace("# 0003.", "# 0005.")
    )
    duplicated.commit()

    assert any("Only the number in the filename may change" in p for p in duplicated.check())


def test_repair_onto_a_number_main_already_uses_fails(duplicated: Repo):
    duplicated.rename(name(3, "second"), name(4, "second"))
    duplicated.write(
        name(4, "second"), duplicated.read(name(4, "second")).replace("# 0003.", "# 0004.")
    )
    duplicated.commit()

    assert any("number 0004 is already used on main" in p for p in duplicated.check())


def test_repair_may_only_retarget_the_renumbered_adr(duplicated: Repo):
    repair(duplicated)
    duplicated.write(name(4, "newer"), adr(4, supersedes=[9], title="Newer"))
    duplicated.commit()

    assert any("frontmatter of an ADR on main may change only" in p for p in duplicated.check())


def test_retargeting_without_a_repair_fails(duplicated: Repo):
    duplicated.write(name(4, "newer"), adr(4, supersedes=[5], title="Newer"))
    duplicated.commit()

    assert any("frontmatter of an ADR on main may change only" in p for p in duplicated.check())


def test_retarget_with_a_different_length_fails(duplicated: Repo):
    repair(duplicated)
    duplicated.write(name(4, "newer"), adr(4, supersedes=[5, 6], title="Newer"))
    duplicated.commit()

    assert any("frontmatter of an ADR on main may change only" in p for p in duplicated.check())


def test_superseded_by_repoint_to_the_new_number_passes(tmp_path: Path):
    r = renumber_repo(tmp_path)
    r.write(name(1, "old"), adr(1, status="superseded", superseded_by=5, title="Old"))
    r.commit()

    assert r.check_all() == []


def test_superseded_by_repoint_to_another_number_fails(tmp_path: Path):
    r = renumber_repo(tmp_path)
    r.write(name(1, "old"), adr(1, status="superseded", superseded_by=9, title="Old"))
    r.commit()

    assert any("frontmatter of an ADR on main may change only" in p for p in r.check())


def renumber_repo(tmp_path: Path) -> Repo:
    """Main holds two ADRs numbered 0003, and 0001 names the second as its successor.

    The branch has already renumbered the second one to 0005.
    """
    r = Repo(tmp_path)
    r.write(name(1, "old"), adr(1, status="superseded", superseded_by=3, title="Old"))
    r.write(name(3, "first"), adr(3, title="First"))
    r.write(name(3, "second"), adr(3, supersedes=[1], title="Second"))
    r.commit("base")
    r.branch()
    r.rename(name(3, "second"), name(5, "second"))
    r.write(name(5, "second"), adr(3, supersedes=[1], title="Second", h1_number=5))
    return r


def test_subdirectories_of_the_adr_dir_are_ignored(repo: Repo):
    sub = repo.adr_dir / "sub"
    sub.mkdir()
    (sub / "x.md").write_text("x\n")
    (sub / "0001-x.md").write_text("x\n")
    repo.commit("add")
    (sub / "x.md").write_text("y\n")
    repo.commit("modify")
    (sub / "x.md").unlink()
    repo.commit("delete")

    assert repo.check() == []


def test_changes_to_subdirectory_files_already_on_main_are_ignored(tmp_path: Path):
    r = Repo(tmp_path)
    r.write(OLD, adr(1))
    sub = r.adr_dir / "sub"
    sub.mkdir()
    (sub / "kept.md").write_text("x\n")
    (sub / "gone.md").write_text("x\n")
    r.commit("base")
    r.branch()
    (sub / "kept.md").write_text("y\n")
    (sub / "gone.md").unlink()
    r.commit()

    assert r.check() == []


def test_moving_an_adr_into_a_subdirectory_counts_as_deleting_it(repo: Repo):
    (repo.adr_dir / "sub").mkdir()
    repo.rename(OLD, f"sub/{OLD}")
    repo.commit()

    assert repo.check() == [f"docs/adr/{OLD}: ADRs are never deleted"]


def test_moving_an_adr_out_of_a_subdirectory_counts_as_adding_it(tmp_path: Path):
    r = Repo(tmp_path)
    (r.adr_dir / "sub").mkdir()
    r.write(name(3, "other"), adr(3, title="Other"))
    r.write("sub/" + name(3, "moved"), adr(3, title="Moved"))
    r.commit("base")
    r.branch()
    r.rename("sub/" + name(3, "moved"), name(3, "moved"))
    r.commit()

    problems = r.check()

    assert len(problems) == 1
    assert "number 0003 is already used on main by 0003-other.md" in problems[0]


def test_unreadable_frontmatter_on_main_cannot_be_compared(tmp_path: Path):
    r = Repo(tmp_path)
    r.write(OLD, "no frontmatter\n")
    r.commit("base")
    r.branch()
    r.write(OLD, adr(1))
    r.commit()

    assert any("unreadable frontmatter" in p for p in r.check())


def test_missing_base_ref_says_to_fetch_history(repo: Repo):
    with pytest.raises(BaseRefError, match="fetch-depth: 0"):
        check_against_base(repo.path, "docs/adr", "origin/main", [])


def test_unrelated_history_is_reported(repo: Repo):
    repo.git("checkout", "-q", "--orphan", "island")
    repo.commit("island")

    with pytest.raises(BaseRefError, match="share no history"):
        repo.check()


def test_repo_root_outside_a_repository_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    with pytest.raises(BaseRefError, match="not inside a git repository"):
        repo_root()


def test_repo_root_finds_the_top(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(repo.adr_dir)

    assert repo_root().resolve() == repo.path.resolve()
