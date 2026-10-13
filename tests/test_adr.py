from pathlib import Path

import pytest
from adrs import adr, name

from adr_check.adr import (
    AdrFile,
    check_no_proposed,
    check_tree,
    is_candidate,
    load_tree,
    parse_text,
    split_document,
)


def parse(number: int, text: str, slug: str = "a-decision") -> tuple[AdrFile, list[str]]:
    return parse_text(f"docs/adr/{name(number, slug)}", text)


def tree(*adrs: tuple[int, str]) -> list[AdrFile]:
    return [parse(number, text)[0] for number, text in adrs]


def test_valid_adr_has_no_problems():
    parsed, problems = parse(7, adr(7))

    assert problems == []
    assert parsed.number == 7
    assert parsed.meta is not None
    assert parsed.meta.status == "accepted"


def test_quoted_string_date_is_accepted():
    text = adr(7).replace("date: 2026-03-12", 'date: "2026-03-12"')

    assert parse(7, text)[1] == []


def test_adr_with_comments_and_y_statement_is_accepted():
    text = adr(7).replace(
        "## Context",
        "> In the context of X, we decided Y.\n\n<!-- ## Not a heading -->\n\n## Context",
    )

    assert parse(7, text)[1] == []


@pytest.mark.parametrize("bad_name", ["adr-7.md", "007-short.md", "0007-Upper.md", "0007_x.md"])
def test_bad_filename_fails(bad_name: str):
    _, problems = parse_text(f"docs/adr/{bad_name}", adr(7))

    assert any("filename must look like" in p for p in problems)


def test_missing_frontmatter_fails():
    _, problems = parse(7, "# 0007. Title\n")

    assert any("frontmatter block" in p for p in problems)


def test_unterminated_frontmatter_fails():
    assert split_document("---\nstatus: x\n")[0] is None


def test_invalid_yaml_fails():
    text = adr(7).replace("status: accepted", "status: [unclosed")

    assert any("not valid YAML" in p for p in parse(7, text)[1])


def test_non_mapping_frontmatter_fails():
    text = "---\n- a\n- b\n---\n" + adr(7).split("---\n", 2)[2]

    assert any("must be a mapping" in p for p in parse(7, text)[1])


@pytest.mark.parametrize("key", ["status", "date", "supersedes", "superseded_by"])
def test_missing_key_fails(key: str):
    text = "\n".join(line for line in adr(7).split("\n") if not line.startswith(f"{key}:"))

    assert any(f"missing the key `{key}`" in p for p in parse(7, text)[1])


def test_ticket_key_is_not_required():
    assert "ticket" not in adr(7)
    assert parse(7, adr(7))[1] == []


def test_unknown_status_fails():
    problems = parse(7, adr(7, status="deprecated"))[1]

    assert any("`status` must be one of" in p for p in problems)


@pytest.mark.parametrize("value", ["12/03/2026", "2026-13-45", "tomorrow", "2026-03-12T10:00:00"])
def test_non_iso_date_fails(value: str):
    text = adr(7).replace("date: 2026-03-12", f'date: "{value}"')

    assert any("`date` must be an ISO date" in p for p in parse(7, text)[1])


def test_datetime_date_fails():
    text = adr(7).replace("date: 2026-03-12", "date: 2026-03-12 10:00:00")

    assert any("`date` must be an ISO date" in p for p in parse(7, text)[1])


@pytest.mark.parametrize("value", ["7", '["7"]', "[true]", "{a: 1}"])
def test_bad_supersedes_fails(value: str):
    text = adr(7).replace("supersedes: []", f"supersedes: {value}")

    assert any("`supersedes` must be a list" in p for p in parse(7, text)[1])


def test_null_supersedes_is_empty():
    text = adr(7).replace("supersedes: []", "supersedes:")

    assert parse(7, text)[1] == []


def test_bad_superseded_by_fails():
    text = adr(7).replace("superseded_by: ", "superseded_by: seven")

    assert any("`superseded_by` must be one ADR number" in p for p in parse(7, text)[1])


def test_h1_number_must_match_filename():
    problems = parse(7, adr(7, h1_number=8))[1]

    assert any("H1 number 0008 does not match filename number 0007" in p for p in problems)


def test_missing_h1_fails():
    text = adr(7).replace("# 0007. A decision\n", "")

    assert any("missing the H1" in p for p in parse(7, text)[1])


def test_h1_without_number_fails():
    text = adr(7).replace("# 0007. A decision", "# A decision")

    assert any("H1 must look like" in p for p in parse(7, text)[1])


def test_heading_inside_code_fence_does_not_count():
    text = adr(7).replace("## Decision\n", "```\n## Decision\n```\n\n~~~\n~~~\n")

    assert any("missing the `## Decision` section" in p for p in parse(7, text)[1])


def decision_problems(opening: str, closing: str) -> list[str]:
    """Return the problems when `## Decision` follows a fence opened and then `closed`."""
    text = adr(7).replace("## Decision\n", f"{opening}\nx\n{closing}\n\n## Decision\n")
    return parse(7, text)[1]


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("````", "```"),
        ("````", "~~~~"),
        ("~~~~", "~~~"),
        ("```", "~~~"),
        ("```", "``` text"),
        ("````", "````` text"),
        ("```", "    ```"),
    ],
)
def test_a_fence_is_not_closed_by_a_shorter_other_or_info_line(opening: str, closing: str):
    problems = decision_problems(opening, closing)

    assert any("missing the `## Decision` section" in p for p in problems)


@pytest.mark.parametrize(
    ("opening", "closing"),
    [("```", "```"), ("````", "````"), ("````", "``````"), ("~~~", "~~~~"), ("   ```", "   ```")],
)
def test_a_fence_is_closed_by_the_same_char_at_least_as_long(opening: str, closing: str):
    assert decision_problems(opening, closing) == []


def test_a_backtick_fence_with_a_backtick_in_its_info_string_does_not_open():
    text = adr(7).replace("## Decision\n", "```a`b\n\n## Decision\n")

    assert parse(7, text)[1] == []


def test_an_unclosed_fence_runs_to_the_end_of_the_document():
    text = adr(7).replace("## Consequences\n", "```\n## Consequences\n")

    assert any("missing the `## Consequences` section" in p for p in parse(7, text)[1])


def test_an_unclosed_comment_hides_the_sections_after_it():
    text = adr(7).replace("## Context\n", "<!--\n## Context\n")

    problems = parse(7, text)[1]

    for section in ("Context", "Considered options", "Decision", "Consequences"):
        assert any(f"missing the `## {section}` section" in p for p in problems)


def test_a_comment_opener_inside_a_fence_is_literal():
    text = adr(7).replace("## Context\n", "```\n<!--\n```\n## Context\n")

    assert parse(7, text)[1] == []


@pytest.mark.parametrize("opener", ["<!-->", "<!--->"])
def test_a_comment_that_closes_on_its_opening_line_hides_nothing(opener: str):
    text = adr(7).replace("## Context\n", f"{opener}\n## Context\n")

    assert parse(7, text)[1] == []


def test_a_comment_closes_on_a_later_line_and_the_sections_after_it_count():
    text = adr(7).replace("## Context\n", "<!-- guidance\n## Not a section\n-->\n## Context\n")

    assert parse(7, text)[1] == []


@pytest.mark.parametrize("section", ["Context", "Considered options", "Decision", "Consequences"])
def test_missing_section_fails(section: str):
    text = adr(7).replace(f"## {section}", "## Something else")

    assert any(f"missing the `## {section}` section" in p for p in parse(7, text)[1])


def test_crlf_line_endings_parse():
    assert parse(7, adr(7).replace("\n", "\r\n"))[1] == []


def test_readme_and_other_files_are_not_candidates():
    assert not is_candidate("README.md")
    assert not is_candidate("readme.md")
    assert not is_candidate("diagram.png")
    assert is_candidate("0001-x.md")
    assert is_candidate("notes.md")


def test_load_tree_ignores_readme_and_non_adr_files(tmp_path: Path):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "README.md").write_text("# ADRs\n\nNo frontmatter here.\n")
    (adr_dir / "diagram.png").write_bytes(b"\x89PNG")
    (adr_dir / "sub").mkdir()
    (adr_dir / name(1)).write_text(adr(1))

    files, problems = load_tree(adr_dir, "docs/adr")

    assert [f.name for f in files] == [name(1)]
    assert problems == []


def test_load_tree_checks_a_badly_named_markdown_file(tmp_path: Path):
    (tmp_path / "notes.md").write_text(adr(1))

    _, problems = load_tree(tmp_path, "docs/adr")

    assert any("filename must look like" in p for p in problems)


def test_load_tree_reports_non_utf8(tmp_path: Path):
    (tmp_path / name(1)).write_bytes(b"\xff\xfe")

    _, problems = load_tree(tmp_path, "docs/adr")

    assert problems == [f"docs/adr/{name(1)}: file is not valid UTF-8"]


def test_load_tree_rejects_a_symlinked_adr(tmp_path: Path):
    target = tmp_path / "elsewhere.md"
    target.write_text(adr(1))
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / name(1)).symlink_to(target)

    files, problems = load_tree(adr_dir, "docs/adr")

    assert files == []
    assert problems == [f"docs/adr/{name(1)}: is a symlink. An ADR must be a regular file"]


def test_load_tree_rejects_a_dangling_symlinked_adr(tmp_path: Path):
    (tmp_path / name(1)).symlink_to(tmp_path / "missing.md")

    _, problems = load_tree(tmp_path, "docs/adr")

    assert problems == [f"docs/adr/{name(1)}: is a symlink. An ADR must be a regular file"]


def test_load_tree_ignores_a_symlink_that_is_not_a_candidate(tmp_path: Path):
    (tmp_path / "README.md").write_text("# ADRs\n")
    (tmp_path / "diagram.png").symlink_to(tmp_path / "README.md")

    assert load_tree(tmp_path, "docs/adr") == ([], [])


def test_load_tree_of_a_missing_directory_is_empty(tmp_path: Path):
    assert load_tree(tmp_path / "nope", "docs/adr") == ([], [])


def test_unrelated_tree_passes():
    assert check_tree(tree((1, adr(1)), (2, adr(2)))) == []


def test_duplicate_number_fails():
    files = [
        parse_text("docs/adr/0003-a.md", adr(3))[0],
        parse_text("docs/adr/0003-b.md", adr(3))[0],
    ]

    problems = check_tree(files)

    assert problems == ["0003 is used by more than one ADR: 0003-a.md, 0003-b.md"]


def test_supersession_in_both_directions_passes():
    old = adr(1, status="superseded", superseded_by=2)
    new = adr(2, supersedes=[1])

    assert check_tree(tree((1, old), (2, new))) == []


def test_supersedes_needs_the_old_adr_to_name_it_back():
    problems = check_tree(tree((1, adr(1)), (2, adr(2, supersedes=[1]))))

    assert any("0002-a-decision.md: supersedes 0001" in p for p in problems)


def test_supersedes_needs_the_old_adr_to_be_superseded():
    old = adr(1, status="accepted", superseded_by=2)
    problems = check_tree(tree((1, old), (2, adr(2, supersedes=[1]))))

    assert any("must have `status: superseded`" in p for p in problems)
    assert any("`superseded_by` is set, so `status` must be `superseded`" in p for p in problems)


def test_superseded_adr_must_be_named_by_its_successor():
    old = adr(1, status="superseded", superseded_by=2)
    problems = check_tree(tree((1, old), (2, adr(2))))

    assert any("whose `supersedes` must include 1" in p for p in problems)


def test_superseded_needs_a_successor_number():
    problems = check_tree(tree((1, adr(1, status="superseded"))))

    assert any("`status: superseded` needs `superseded_by`" in p for p in problems)


def test_rejected_successor_fails():
    old = adr(1, status="superseded", superseded_by=2)
    new = adr(2, status="rejected", supersedes=[1])

    problems = check_tree(tree((1, old), (2, new)))

    assert any("which is rejected" in p for p in problems)


def test_proposed_successor_passes_on_a_branch():
    old = adr(1, status="superseded", superseded_by=2)
    new = adr(2, status="proposed", supersedes=[1])

    assert check_tree(tree((1, old), (2, new))) == []


def test_superseding_a_missing_adr_fails():
    problems = check_tree(tree((2, adr(2, supersedes=[1]))))

    assert any("names 0001, which does not exist" in p for p in problems)


def test_superseded_by_a_missing_adr_fails():
    problems = check_tree(tree((1, adr(1, status="superseded", superseded_by=9))))

    assert any("names 0009, which does not exist" in p for p in problems)


def test_reference_to_a_duplicated_number_fails_both_ways():
    files = [
        parse_text("docs/adr/0001-a.md", adr(1))[0],
        parse_text("docs/adr/0001-b.md", adr(1))[0],
        parse_text("docs/adr/0002-new.md", adr(2, supersedes=[1]))[0],
        parse_text("docs/adr/0003-old.md", adr(3, status="superseded", superseded_by=1))[0],
    ]

    problems = check_tree(files)

    ambiguous = [p for p in problems if "duplicated number" in p]
    assert len(ambiguous) == 2
    assert "0002-new.md: `supersedes` names 0001" in ambiguous[0]
    assert "0003-old.md: `superseded_by` names 0001" in ambiguous[1]


def test_self_references_fail():
    problems = check_tree(
        tree((1, adr(1, supersedes=[1])), (2, adr(2, status="superseded", superseded_by=2)))
    )

    assert any("`supersedes` names the ADR itself" in p for p in problems)
    assert any("`superseded_by` names the ADR itself" in p for p in problems)


def test_malformed_adr_is_skipped_by_the_tree_checks():
    broken = parse(1, "no frontmatter")[0]

    assert check_tree([broken]) == []


def test_proposed_fails_when_merging_to_main():
    problems = check_no_proposed(tree((1, adr(1, status="proposed")), (2, adr(2))))

    assert problems == [
        "docs/adr/0001-a-decision.md: `status: proposed` cannot reach main. "
        "Set accepted, rejected or superseded"
    ]


def test_proposed_passes_when_not_merging_to_main():
    assert check_no_proposed(tree((2, adr(2)))) == []


def test_badly_named_file_does_not_join_the_number_checks():
    files = [parse_text("docs/adr/notes.md", adr(1))[0], parse(1, adr(1))[0]]

    assert check_tree(files) == []


def test_unquoted_impossible_date_is_a_problem_naming_the_file():
    text = adr(7).replace("date: 2026-03-12", "date: 2026-02-30")

    _, problems = parse(7, text)

    assert any(
        p.startswith("docs/adr/0007-a-decision.md: frontmatter is not valid YAML") for p in problems
    )


def test_key_beyond_the_four_fails():
    text = adr(7).replace("supersedes: []", "supersedes: []\nticket: ABC-1")

    assert any("`ticket`" in p and "status, date, supersedes" in p for p in parse(7, text)[1])
