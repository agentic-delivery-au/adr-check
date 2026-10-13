import json
import shutil
from pathlib import Path

import pytest
from adrs import adr, name
from gitrepo import Repo

from adr_check.cli import main, parse_labels

DATA = Path(__file__).parent / "data"


@pytest.fixture
def adr_dir(tmp_path: Path) -> Path:
    path = tmp_path / "docs" / "adr"
    path.mkdir(parents=True)
    return path


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().err


def test_adr_0001_passes(adr_dir: Path, capsys: pytest.CaptureFixture[str]):
    shutil.copy(DATA / "0001-record-architecture-decisions.md", adr_dir)
    (adr_dir / "README.md").write_text("# ADRs\n")

    assert run(capsys, "--adr-dir", str(adr_dir)) == (0, "")


def test_adr_written_to_the_template_passes(adr_dir: Path, capsys: pytest.CaptureFixture[str]):
    shutil.copy(DATA / "0002-use-the-template.md", adr_dir)

    assert run(capsys, "--adr-dir", str(adr_dir)) == (0, "")


def test_missing_adr_directory_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert run(capsys, "--adr-dir", str(tmp_path / "docs" / "adr")) == (0, "")


def test_problems_print_and_exit_one(adr_dir: Path, capsys: pytest.CaptureFixture[str]):
    (adr_dir / name(1)).write_text(adr(1, status="bogus"))

    code, err = run(capsys, "--adr-dir", str(adr_dir))

    assert code == 1
    assert "`status` must be one of" in err
    assert err.rstrip().endswith("adr-check: 1 problem(s) found")


def test_proposed_is_fine_locally_and_fails_when_merging_to_main(
    adr_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    repo = Repo(adr_dir.parent.parent)
    root = repo.path
    (adr_dir / name(1)).write_text(adr(1))
    repo.commit("base")
    repo.branch()
    (adr_dir / name(2)).write_text(adr(2, status="proposed"))
    repo.commit()
    monkeypatch.chdir(root)

    assert run(capsys, "--mode", "ci", "--base-ref", "main") == (0, "")
    code, err = run(capsys, "--mode", "ci", "--base-ref", "main", "--merging-to-main")
    assert code == 1
    assert "`status: proposed` cannot reach main" in err


def test_ci_mode_reads_labels_from_json(
    adr_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    repo = Repo(adr_dir.parent.parent)
    root = repo.path
    (adr_dir / name(1)).write_text(adr(1))
    repo.commit("base")
    repo.branch()
    (adr_dir / name(1)).write_text(adr(1).replace("The situation.", "Typo fixed."))
    repo.commit()
    monkeypatch.chdir(root)
    base = ("--mode", "ci", "--base-ref", "main")

    assert run(capsys, *base)[0] == 1
    assert run(capsys, *base, "--labels", json.dumps(["bug", "adr-correction"])) == (0, "")
    assert run(capsys, *base, "--labels", "bug, adr-correction") == (0, "")
    assert run(capsys, *base, "--labels", "[]")[0] == 1


def test_ci_mode_exits_one_naming_a_modified_adr_that_is_not_utf8(
    adr_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    repo = Repo(adr_dir.parent.parent)
    (adr_dir / name(1)).write_text(adr(1))
    repo.commit("base")
    repo.branch()
    (adr_dir / name(1)).write_bytes(adr(1).replace("It is done.", "Café").encode("latin-1"))
    repo.commit()
    monkeypatch.chdir(repo.path)

    code, err = run(capsys, "--mode", "ci", "--base-ref", "main")

    assert code == 1
    assert err.count(f"docs/adr/{name(1)}: file is not valid UTF-8") == 1


def test_ci_mode_defaults_the_base_ref_to_origin_main(
    adr_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    repo = Repo(adr_dir.parent.parent)
    root = repo.path
    (adr_dir / name(1)).write_text(adr(1))
    repo.commit("base")
    monkeypatch.chdir(root)

    code, err = run(capsys, "--mode", "ci")

    assert code == 2
    assert "base ref 'origin/main' not found" in err
    assert "fetch-depth: 0" in err


def test_ci_mode_outside_a_repository_exits_two(
    adr_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(adr_dir)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(adr_dir.parent.parent.parent))

    code, err = run(capsys, "--mode", "ci", "--adr-dir", ".")

    assert code == 2
    assert "not inside a git repository" in err


def test_adr_dir_outside_the_repository_exits_two(
    adr_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.chdir(Repo(tmp_path / "repo").path)

    code, err = run(capsys, "--mode", "ci", "--adr-dir", str(adr_dir))

    assert code == 2
    assert "adr-check:" in err


@pytest.mark.parametrize("flag", [["--base-ref", "main"], ["--labels", "x"]])
def test_ci_only_flags_are_rejected_in_local_mode(flag: list[str]):
    with pytest.raises(SystemExit) as raised:
        main(flag)

    assert raised.value.code == 2


def test_bad_labels_are_rejected():
    with pytest.raises(SystemExit) as raised:
        main(["--mode", "ci", "--labels", "[not json"])

    assert raised.value.code == 2


def test_parse_labels_accepts_json_and_commas():
    assert parse_labels('["a", "b c"]') == ["a", "b c"]
    assert parse_labels("a, b ,,c") == ["a", "b", "c"]
    assert parse_labels("") == []


def test_parse_labels_rejects_a_json_value_that_is_not_an_array():
    with pytest.raises(ValueError, match="Expecting"):
        parse_labels("[1")


def test_merging_to_main_works_without_ci_mode(adr_dir: Path, capsys: pytest.CaptureFixture[str]):
    (adr_dir / name(1)).write_text(adr(1, status="proposed"))

    code, err = run(capsys, "--adr-dir", str(adr_dir), "--merging-to-main")

    assert code == 1
    assert "`status: proposed` cannot reach main" in err


def test_unquoted_impossible_date_exits_one_naming_the_file(
    adr_dir: Path, capsys: pytest.CaptureFixture[str]
):
    (adr_dir / name(1)).write_text(adr(1).replace("date: 2026-03-12", "date: 2026-02-30"))

    code, err = run(capsys, "--adr-dir", str(adr_dir))

    assert code == 1
    assert name(1) in err


def test_push_to_main_after_an_adr_correction_passes(
    adr_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    repo = Repo(adr_dir.parent.parent)
    (adr_dir / name(1)).write_text(adr(1))
    repo.commit("base")
    (adr_dir / name(1)).write_text(adr(1).replace("We will do it.", "We will do it, fixed."))
    repo.commit("fix: correct a typo (adr-correction)")
    monkeypatch.chdir(repo.path)

    assert run(capsys, "--adr-dir", "docs/adr", "--merging-to-main") == (0, "")
