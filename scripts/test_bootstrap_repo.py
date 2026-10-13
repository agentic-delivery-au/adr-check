#!/usr/bin/env python3
"""Tests for bootstrap_repo.

Run with: python3 -m unittest discover -s scripts -t scripts

The --apply path writes real repository settings, so it is exercised against a
fake gh rather than GitHub: every test asserts on the requests that would be
sent. That is the only way this path gets covered at all.
"""

from __future__ import annotations

import copy
import io
import sys
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bootstrap_repo as br  # noqa: E402


def matching_ruleset(ruleset_id: int = 1) -> dict:
    """What the API returns for a ruleset that matches the template.

    The extra parameters are defaults the API adds and the payload never sets;
    they belong here so the tests prove those do not read as differences.
    """
    live = copy.deepcopy(br.ruleset_payload())
    live["id"] = ruleset_id
    live["source_type"] = "Repository"
    for rule in live["rules"]:
        if rule["type"] == "pull_request":
            rule["parameters"].update(
                {
                    "dismissal_restriction": {"allowed_actors": [], "enabled": False},
                    "require_extra_approval_for_unattributed_changes": True,
                    "required_reviewers": [],
                }
            )
    return live


class FakeGh:
    """Stands in for the gh CLI, recording writes instead of making them."""

    def __init__(self, ruleset=None, repo=None, workflow=None, rulesets_index=None):
        self.repo = "owner/repo"
        self._ruleset = ruleset
        self._repo_settings = repo if repo is not None else dict(br.MERGE_SETTINGS)
        self._workflow = (
            workflow if workflow is not None else dict(br.WORKFLOW_PERMISSIONS)
        )
        self._index = rulesets_index
        self.writes: list[tuple[str, str, dict | None]] = []

    def get(self, path, paginate=False):
        if path.endswith("/rulesets"):
            if self._index is not None:
                return self._index
            return [{"id": self._ruleset["id"], "name": self._ruleset["name"]}] if self._ruleset else []
        if "/rulesets/" in path:
            return self._ruleset
        if path.endswith("/actions/permissions/workflow"):
            return self._workflow
        return self._repo_settings

    def request(self, method, path, payload=None):
        self.writes.append((method, path, payload))


def execute(gh, apply=False) -> tuple[str, int]:
    out = io.StringIO()
    with redirect_stdout(out):
        changes = br.run(gh, apply)
    return out.getvalue(), changes


class RulesetPayloadTests(unittest.TestCase):
    def test_required_checks_are_the_contexts_the_workflows_report(self):
        """A context no workflow reports never resolves and blocks every PR.

        The names are job ids (or a job's `name:`) in .github/workflows, not
        workflow names: `pytest` is the job in tests.yml.
        """
        checks = br._params(br.ruleset_payload(), "required_status_checks")
        self.assertEqual(
            sorted(c["context"] for c in checks["required_status_checks"]),
            ["Validate PR title", "pre-commit", "pytest"],
        )

    def test_copilot_reviews_on_open_not_on_every_push(self):
        """review_on_push turns a pull request into a fix-after-review loop."""
        copilot = br._params(br.ruleset_payload(), "copilot_code_review")
        self.assertFalse(copilot["review_on_push"])


class RulesetSummaryTests(unittest.TestCase):
    def test_api_defaults_are_not_differences(self):
        self.assertEqual(
            br.ruleset_summary(matching_ruleset()),
            br.ruleset_summary(br.ruleset_payload()),
        )

    def test_integration_id_change_is_detected(self):
        live = matching_ruleset()
        checks = br._params(live, "required_status_checks")["required_status_checks"]
        checks[0]["integration_id"] = 99999
        self.assertNotEqual(br.ruleset_summary(live), br.ruleset_summary(br.ruleset_payload()))

    def test_bypass_actor_is_detected(self):
        live = matching_ruleset()
        live["bypass_actors"] = [{"actor_id": 1, "actor_type": "OrganizationAdmin"}]
        summary = br.ruleset_summary(live)
        self.assertTrue(any(line.startswith("bypass actor:") for line in summary))
        self.assertNotEqual(summary, br.ruleset_summary(br.ruleset_payload()))

    def test_extra_required_check_is_detected(self):
        live = matching_ruleset()
        br._params(live, "required_status_checks")["required_status_checks"].append(
            {"context": "tests", "integration_id": br.ACTIONS_APP_ID}
        )
        self.assertIn(
            "required check: tests (integration 15368)", br.ruleset_summary(live)
        )


class GhTests(unittest.TestCase):
    """The one class that is not replaced by a fake, so it needs its own cover."""

    def test_slurped_pages_are_flattened(self):
        with mock.patch.object(br.Gh, "_run", return_value='[[{"id": 1}], [{"id": 2}]]'):
            self.assertEqual(
                br.Gh("owner/repo").get("path", paginate=True), [{"id": 1}, {"id": 2}]
            )

    def test_empty_pages_flatten_to_nothing(self):
        with mock.patch.object(br.Gh, "_run", return_value="[[]]"):
            self.assertEqual(br.Gh("owner/repo").get("path", paginate=True), [])

    def test_a_single_document_is_not_flattened(self):
        with mock.patch.object(br.Gh, "_run", return_value='{"allow_squash_merge": true}'):
            self.assertEqual(br.Gh("owner/repo").get("path"), {"allow_squash_merge": True})

    def test_paginated_get_asks_for_slurp(self):
        with mock.patch.object(br.Gh, "_run", return_value="[[]]") as run:
            br.Gh("owner/repo").get("path", paginate=True)
        self.assertIn("--slurp", run.call_args.args[0])


class PlanTests(unittest.TestCase):
    def test_everything_matching_reports_no_changes(self):
        gh = FakeGh(ruleset=matching_ruleset())
        output, changes = execute(gh)
        self.assertEqual(changes, 0)
        self.assertIn("nothing to change", output)
        self.assertEqual(gh.writes, [])

    def test_dry_run_never_writes(self):
        gh = FakeGh(ruleset=None, repo={}, workflow={})
        output, changes = execute(gh, apply=False)
        self.assertGreater(changes, 0)
        self.assertEqual(gh.writes, [])
        self.assertIn("re-run with --apply", output)

    def test_dry_run_never_overwrites_an_existing_ruleset(self):
        # The other dry-run test has no ruleset to overwrite, so it exercises
        # the create path only and would miss a write on this branch.
        live = matching_ruleset(ruleset_id=5)
        br._params(live, "pull_request")["required_approving_review_count"] = 2
        gh = FakeGh(ruleset=live, repo={}, workflow={})
        _, changes = execute(gh, apply=False)
        self.assertGreater(changes, 0)
        self.assertEqual(gh.writes, [])

    def test_loss_is_shown_before_it_happens(self):
        live = matching_ruleset()
        br._params(live, "required_status_checks")["required_status_checks"].append(
            {"context": "tests", "integration_id": br.ACTIONS_APP_ID}
        )
        output, _ = execute(FakeGh(ruleset=live))
        self.assertIn("-required check: tests (integration 15368)", output)

    def test_first_matching_ruleset_wins(self):
        index = [
            {"id": 7, "name": br.RULESET_NAME},
            {"id": 8, "name": br.RULESET_NAME},
            {"id": 9, "name": "something else"},
        ]
        gh = FakeGh(ruleset=matching_ruleset(ruleset_id=7), rulesets_index=index)
        _, changes = execute(gh)
        self.assertEqual(changes, 0)


class ApplyTests(unittest.TestCase):
    def test_apply_creates_a_missing_ruleset(self):
        gh = FakeGh(ruleset=None)
        execute(gh, apply=True)
        methods = [(m, p) for m, p, _ in gh.writes]
        self.assertIn(("POST", "repos/owner/repo/rulesets"), methods)
        payload = next(pl for m, _, pl in gh.writes if m == "POST")
        self.assertEqual(payload["name"], br.RULESET_NAME)
        self.assertEqual(payload["enforcement"], "active")

    def test_apply_overwrites_a_diverged_ruleset(self):
        live = matching_ruleset(ruleset_id=42)
        br._params(live, "pull_request")["required_approving_review_count"] = 3
        gh = FakeGh(ruleset=live)
        execute(gh, apply=True)
        put = [(p, pl) for m, p, pl in gh.writes if m == "PUT" and "rulesets" in p]
        self.assertEqual(len(put), 1)
        self.assertEqual(put[0][0], "repos/owner/repo/rulesets/42")
        self.assertEqual(put[0][1], br.ruleset_payload())

    def test_apply_leaves_a_matching_ruleset_alone(self):
        gh = FakeGh(ruleset=matching_ruleset(), repo={}, workflow={})
        execute(gh, apply=True)
        self.assertFalse([p for _, p, _ in gh.writes if "rulesets" in p])

    def test_apply_patches_only_the_merge_settings_that_differ(self):
        current = dict(br.MERGE_SETTINGS)
        current["delete_branch_on_merge"] = False
        current["squash_merge_commit_title"] = "COMMIT_OR_PR_TITLE"
        gh = FakeGh(ruleset=matching_ruleset(), repo=current)
        execute(gh, apply=True)
        patch = next(pl for m, p, pl in gh.writes if m == "PATCH" and p == "repos/owner/repo")
        self.assertEqual(
            patch, {"delete_branch_on_merge": True, "squash_merge_commit_title": "PR_TITLE"}
        )

    def test_apply_sends_both_permission_fields_together(self):
        gh = FakeGh(
            ruleset=matching_ruleset(),
            workflow={"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True},
        )
        execute(gh, apply=True)
        put = next(
            pl for m, p, pl in gh.writes if p.endswith("/actions/permissions/workflow")
        )
        # The endpoint replaces the whole object, so a partial body would reset
        # the field that was already correct.
        self.assertEqual(put, br.WORKFLOW_PERMISSIONS)

    def test_apply_writes_nothing_when_nothing_differs(self):
        gh = FakeGh(ruleset=matching_ruleset())
        _, changes = execute(gh, apply=True)
        self.assertEqual(changes, 0)
        self.assertEqual(gh.writes, [])

    def test_apply_reports_what_it_did(self):
        gh = FakeGh(ruleset=None, repo={}, workflow={})
        output, changes = execute(gh, apply=True)
        self.assertIn(f"{changes} change(s) applied", output)
        self.assertIn("applying settings to owner/repo", output)


if __name__ == "__main__":
    unittest.main()
