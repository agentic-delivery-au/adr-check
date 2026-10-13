#!/usr/bin/env python3
"""One-time setup for a repository created from base-template.

GitHub's "Use this template" copies files and nothing else, so branch
protection, merge behaviour and Actions permissions all start at GitHub's
defaults. Prints a plan and changes nothing unless --apply is passed.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys

RULESET_NAME = "protect main"
# The GitHub Actions app. Scoping a required check to it stops a same-named
# check from another integration from satisfying the rule.
ACTIONS_APP_ID = 15368


class GhError(RuntimeError):
    """gh is missing, unauthenticated, or returned a failure."""


class Gh:
    """The only thing that talks to GitHub, so a test can replace it."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def get(self, path: str, paginate: bool = False) -> object:
        args = ["gh", "api"]
        if paginate:
            # Without --slurp each page is its own JSON document, which is not
            # parseable as one. --slurp wraps the pages in an outer array, so
            # the pages are flattened back into the single list callers want.
            args += ["--paginate", "--slurp"]
        args.append(path)
        data = json.loads(self._run(args))
        if paginate:
            return [item for page in data for item in page]
        return data

    def request(self, method: str, path: str, payload: dict | None = None) -> None:
        args = ["gh", "api", "--method", method, path, "--silent"]
        if payload is None:
            self._run(args)
            return
        args += ["--input", "-"]
        self._run(args, stdin=json.dumps(payload))

    @staticmethod
    def _run(args: list[str], stdin: str | None = None) -> str:
        done = subprocess.run(args, input=stdin, capture_output=True, text=True)
        if done.returncode != 0:
            raise GhError(f"{' '.join(args)}: {done.stderr.strip()}")
        return done.stdout


class Plan:
    """Collects what would change, and prints it as it goes."""

    def __init__(self, apply: bool) -> None:
        self.apply = apply
        self.changes = 0

    def section(self, name: str) -> None:
        print(name)

    def change(self, text: str) -> None:
        self.changes += 1
        print(f"  {'+' if self.apply else '~'} {text}")

    def unchanged(self, text: str) -> None:
        print(f"  = {text}")

    def detail(self, lines: list[str]) -> None:
        for line in lines:
            print(f"      {line}")


def ruleset_payload() -> dict:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "copilot_code_review",
                "parameters": {"review_on_push": False, "review_draft_pull_requests": False},
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": False,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": "Validate PR title", "integration_id": ACTIONS_APP_ID},
                        {"context": "pre-commit", "integration_id": ACTIONS_APP_ID},
                        {"context": "pytest", "integration_id": ACTIONS_APP_ID},
                    ],
                },
            },
        ],
    }


def _params(ruleset: dict, rule_type: str) -> dict:
    for rule in ruleset.get("rules", []):
        if rule.get("type") == rule_type:
            return rule.get("parameters", {})
    return {}


def ruleset_summary(ruleset: dict) -> list[str]:
    """Every field ruleset_payload states, and nothing else.

    The API fills in defaults of its own that the payload never sets, which
    would otherwise read as differences on a ruleset that already matches.
    Set-like fields are listed per entry, so policy only one side has shows up
    as its own line rather than vanishing.
    """
    ref = ruleset.get("conditions", {}).get("ref_name", {})
    pr = _params(ruleset, "pull_request")
    copilot = _params(ruleset, "copilot_code_review")
    checks = _params(ruleset, "required_status_checks")

    lines = [
        f"enforcement: {ruleset.get('enforcement')}",
        f"target: {ruleset.get('target')}",
        f"condition include: {', '.join(sorted(ref.get('include', [])))}",
        f"condition exclude: {', '.join(sorted(ref.get('exclude', [])))}",
    ]
    lines += sorted(
        f"bypass actor: {json.dumps(a, sort_keys=True)}" for a in ruleset.get("bypass_actors", [])
    )
    lines.append(
        "rules: " + ", ".join(sorted(r.get("type", "") for r in ruleset.get("rules", [])))
    )
    lines += [
        f"pr merge methods: {', '.join(sorted(pr.get('allowed_merge_methods', [])))}",
        f"pr approvals required: {pr.get('required_approving_review_count')}",
        f"pr code owner review: {pr.get('require_code_owner_review')}",
        f"pr dismiss stale reviews: {pr.get('dismiss_stale_reviews_on_push')}",
        f"pr last push approval: {pr.get('require_last_push_approval')}",
        f"pr thread resolution: {pr.get('required_review_thread_resolution')}",
        f"copilot review on push: {copilot.get('review_on_push')}",
        f"copilot review drafts: {copilot.get('review_draft_pull_requests')}",
        f"checks strict policy: {checks.get('strict_required_status_checks_policy')}",
        f"checks enforce on create: {checks.get('do_not_enforce_on_create')}",
    ]
    lines += sorted(
        f"required check: {c.get('context')} (integration {c.get('integration_id', 'any')})"
        for c in checks.get("required_status_checks", [])
    )
    return lines


def sync_ruleset(gh: Gh, plan: Plan) -> None:
    plan.section("branch ruleset")
    # Paginated at 30, so a repo past that looks ruleset-less and gets a
    # duplicate created on every run. First match wins: names are not unique.
    existing = [
        r for r in gh.get(f"repos/{gh.repo}/rulesets", paginate=True) if r.get("name") == RULESET_NAME
    ]
    payload = ruleset_payload()

    if not existing:
        plan.change(f'create ruleset "{RULESET_NAME}"')
        if plan.apply:
            gh.request("POST", f"repos/{gh.repo}/rulesets", payload)
        return

    ruleset_id = existing[0]["id"]
    live = ruleset_summary(gh.get(f"repos/{gh.repo}/rulesets/{ruleset_id}"))
    want = ruleset_summary(payload)
    if live == want:
        plan.unchanged(f'ruleset "{RULESET_NAME}" (#{ruleset_id}) already matches')
        return

    plan.change(f'ruleset "{RULESET_NAME}" (#{ruleset_id}) would be overwritten')
    # A "-" line is policy this repo has and the template does not, so an
    # apply loses it. That is the whole reason this prints before writing.
    plan.detail(
        [
            line
            for line in difflib.unified_diff(live, want, lineterm="", n=0)
            if line[:1] in "+-" and not line.startswith(("+++", "---"))
        ]
    )
    if plan.apply:
        gh.request("PUT", f"repos/{gh.repo}/rulesets/{ruleset_id}", payload)


MERGE_SETTINGS = {
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": False,
    "delete_branch_on_merge": True,
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "PR_BODY",
}


def sync_merge_settings(gh: Gh, plan: Plan) -> None:
    plan.section("merge settings")
    current = gh.get(f"repos/{gh.repo}")
    patch = {}
    for field, desired in MERGE_SETTINGS.items():
        if current.get(field) == desired:
            plan.unchanged(f"{field} = {_fmt(desired)}")
        else:
            plan.change(f"{field}: {_fmt(current.get(field))} -> {_fmt(desired)}")
            patch[field] = desired
    if plan.apply and patch:
        gh.request("PATCH", f"repos/{gh.repo}", patch)


# Every workflow in the template declares its own permissions block, so the
# repository default stays read-only.
WORKFLOW_PERMISSIONS = {
    "default_workflow_permissions": "read",
    "can_approve_pull_request_reviews": True,
}


def sync_actions_permissions(gh: Gh, plan: Plan) -> None:
    plan.section("actions permissions")
    current = gh.get(f"repos/{gh.repo}/actions/permissions/workflow")
    dirty = False
    for field, desired in WORKFLOW_PERMISSIONS.items():
        if current.get(field) == desired:
            plan.unchanged(f"{field} = {_fmt(desired)}")
        else:
            plan.change(f"{field}: {_fmt(current.get(field))} -> {_fmt(desired)}")
            dirty = True
    # The endpoint replaces the whole object, so both fields go in either way.
    if plan.apply and dirty:
        gh.request(
            "PUT", f"repos/{gh.repo}/actions/permissions/workflow", dict(WORKFLOW_PERMISSIONS)
        )


def _fmt(value: object) -> str:
    return json.dumps(value) if isinstance(value, bool) else str(value)


def current_repo() -> str:
    done = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0 or not done.stdout.strip():
        raise GhError("no repository given and the current directory has no GitHub remote")
    return done.stdout.strip()


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise GhError("gh is not installed: https://cli.github.com")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        raise GhError("gh is not authenticated: run gh auth login")


def run(gh: Gh, apply: bool) -> int:
    if apply:
        print(f"applying settings to {gh.repo}\n")
    else:
        print(f"plan for {gh.repo} (nothing will change; re-run with --apply)\n")

    plan = Plan(apply)
    sync_ruleset(gh, plan)
    sync_merge_settings(gh, plan)
    sync_actions_permissions(gh, plan)

    if plan.changes == 0:
        print("\nnothing to change")
    elif apply:
        print(f"\n{plan.changes} change(s) applied")
    else:
        print(f"\n{plan.changes} change(s) to make; re-run with --apply")
    return plan.changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Apply the repository settings that "Use this template" does not copy: '
        'the "protect main" ruleset, squash-only merges with the PR title and description '
        "as the commit subject and body, delete branch on merge, and the Actions "
        "pull request permission.",
        epilog="Without --apply it prints what it would change and exits.",
    )
    parser.add_argument("--apply", action="store_true", help="make the changes")
    parser.add_argument("repo", nargs="?", help="owner/repo (defaults to the origin remote)")
    args = parser.parse_args(argv)

    try:
        require_gh()
        run(Gh(args.repo or current_repo()), args.apply)
    except GhError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
