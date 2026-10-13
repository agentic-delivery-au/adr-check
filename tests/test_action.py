import os
import subprocess
from pathlib import Path

import pytest
import yaml

ACTION = Path(__file__).parent.parent / "action.yml"


def _run_step() -> dict[str, object]:
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    return next(step for step in steps if step.get("name") == "Run adr-check")


@pytest.fixture
def run_action(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uv = bin_dir / "uv"
    fake_uv.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
    fake_uv.chmod(0o755)
    step = _run_step()

    def run(event: str, **env: str) -> subprocess.CompletedProcess[str]:
        # The step maps these from inputs and contexts with expressions, so the test sets them.
        mapped = {
            "ACTION_PATH": "/action",
            "ADR_DIR": "docs/adr",
            "BASE_REF": "",
            "MERGING_TO_MAIN": "false",
            "LABELS": "[]",
            "UV_PROJECT_ENVIRONMENT": str(tmp_path / "venv"),
        }
        assert set(mapped) | {"EVENT_NAME"} == set(step["env"])
        return subprocess.run(  # noqa: S603  # fixed bash binary, test-controlled script
            ["bash", "-c", str(step["run"])],  # noqa: S607  # bash is resolved from PATH
            cwd=tmp_path,
            env={
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                **mapped,
                "EVENT_NAME": event,
                **env,
            },
            capture_output=True,
            text=True,
            check=False,
        )

    return run


def test_script_reads_only_environment_variables():
    assert "${{" not in str(_run_step()["run"])


def test_push_runs_without_ci_mode(run_action):
    result = run_action("push", BASE_REF="origin/main")

    assert result.returncode == 0
    assert "--mode" not in result.stdout.split()
    assert "--base-ref" not in result.stdout.split()


def test_non_push_event_with_an_empty_base_ref_fails(run_action):
    result = run_action("workflow_dispatch")

    assert result.returncode != 0
    assert "base-ref is empty" in result.stdout


def test_pull_request_passes_ci_mode_base_ref_and_labels(run_action):
    result = run_action("pull_request", BASE_REF="origin/main", LABELS='["adr-correction"]')

    assert result.returncode == 0
    args = result.stdout.split("\n")
    assert args[args.index("--mode") + 1] == "ci"
    assert args[args.index("--base-ref") + 1] == "origin/main"
    assert args[args.index("--labels") + 1] == '["adr-correction"]'


def test_merging_to_main_true_adds_the_flag(run_action):
    result = run_action("pull_request", BASE_REF="origin/main", MERGING_TO_MAIN="true")

    assert "--merging-to-main" in result.stdout.split()


def test_merging_to_main_false_omits_the_flag(run_action):
    result = run_action("pull_request", BASE_REF="origin/main", MERGING_TO_MAIN="false")

    assert result.returncode == 0
    assert "--merging-to-main" not in result.stdout.split()
