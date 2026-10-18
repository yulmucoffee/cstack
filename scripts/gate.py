#!/usr/bin/env python3
"""Conservative cstack risk and approval gate. Python stdlib only.

Run as a read-only GitHub Actions job against the BASE branch's checked-out
.cstack/ files. Never check out or execute the pull request head.
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import sys
import time
from urllib import error, parse, request

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"

# Always two humans: CI, review policy, agent tool config that can run commands,
# dependency locks, infrastructure and the usual sensitive domains.
HIGH_RISK = [
    ".github/workflows/**", ".github/actions/**", ".github/scripts/**", "**/CODEOWNERS",
    ".gitlab-ci.yml", ".gitlab/**", ".circleci/**", "**/Jenkinsfile", ".buildkite/**", "azure-pipelines.yml",
    ".github/dependabot.yml", ".github/renovate.json", "renovate.json",
    ".cstack/**", "**/.cursor/BUGBOT.md", ".cursor/config/**", ".cursor/hooks.json",
    ".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/**",
    ".mcp.json", ".codex/**",
    "**/auth/**", "**/security/**", "**/billing/**", "**/payments/**",
    "**/migrations/**", "**/secrets/**", "**/*.tf", "**/schema.prisma",
    "**/package-lock.json", "**/npm-shrinkwrap.json", "**/yarn.lock",
    "**/pnpm-lock.yaml", "**/bun.lock", "**/bun.lockb", "**/poetry.lock",
    "**/uv.lock", "**/Pipfile.lock", "**/Cargo.lock", "**/Gemfile.lock",
    "**/composer.lock", "**/go.sum", "**/flake.lock",
]
# Prose that steers agents or reviewers is not "just docs".
AGENT_INSTRUCTIONS = [
    "**/CLAUDE.md", "**/AGENTS.md", "**/REVIEW.md", "**/GEMINI.md", "**/SKILL.md",
    "**/*.mdc", "**/.claude/**", "**/.agents/**", "**/.cursor/**", "**/skills/**",
    "**/.clinerules", "**/.clinerules/**", "**/.windsurf/**", "**/.junie/**", "**/.roo/**", "**/.gemini/**",
    ".github/**",
]
LOW_RISK = [
    "**/*.md", "**/*.mdx", "**/*.rst", "**/*.adoc",
    "docs/*.png", "docs/*.jpg", "docs/*.jpeg", "docs/*.gif", "docs/*.webp", "docs/*.svg",
]
TIER_APPROVALS = {"low": 0, "medium": 1, "high": 2}
# Reviews from accounts without a role on the repository never count.
DEFAULT_APPROVER_ASSOCIATIONS = ["OWNER", "MEMBER", "COLLABORATOR"]
POLL_SECONDS = 30


class GateError(RuntimeError):
    pass


def matches(path: str, pattern: str) -> bool:
    """fnmatch, where a leading **/ also matches at the repository root."""
    return fnmatch.fnmatchcase(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])
    )


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches(path, p) for p in patterns)


def classify(paths: list[str], config: dict) -> tuple[str, list[str]]:
    if not paths:
        return "high", ["No changed paths returned; fail closed"]
    high = HIGH_RISK + config.get("additional_high_risk_patterns", [])
    risky = [p for p in paths if matches_any(p, high)]
    if risky:
        return "high", ["Sensitive path(s): " + ", ".join(risky[:10])]
    if all(matches_any(p, LOW_RISK) and not matches_any(p, AGENT_INSTRUCTIONS) for p in paths):
        return "low", ["Documentation-only change"]
    steering = [p for p in paths if matches_any(p, AGENT_INSTRUCTIONS)]
    if steering:
        return "medium", ["Agent or reviewer instructions changed: " + ", ".join(steering[:10])]
    return "medium", ["Code or config change; default medium risk"]


def is_trusted(author: str, config: dict) -> bool:
    return author.casefold() in {a.casefold() for a in config.get("trusted_authors", [])}


def approvals_needed(tier: str, author: str, config: dict) -> int:
    needed = TIER_APPROVALS[tier]
    return needed if is_trusted(author, config) else max(2, needed)


def effective_reviews(reviews: list[dict], head_sha: str, author: str,
                      associations: list[str] | None = None) -> tuple[set[str], set[str]]:
    """Only CURRENT-head approvals from humans with a repository role count.

    A later review supersedes an earlier one. Any account may still block with a
    change request, since GitHub shows it and a human should look.
    """
    allowed = set(associations or DEFAULT_APPROVER_ASSOCIATIONS)
    latest: dict[str, dict] = {}
    for r in reviews:
        user = r.get("user") or {}
        login = user.get("login")
        if not login or user.get("type") != "User" or login.casefold() == author.casefold():
            continue
        if r.get("state") in ("PENDING", "COMMENTED", None):
            continue
        latest[login.casefold()] = r
    approved, blocked = set(), set()
    for r in latest.values():
        login = r["user"]["login"]
        if r.get("state") == "CHANGES_REQUESTED":
            blocked.add(login)
        if r.get("state") == "APPROVED" and r.get("commit_id") == head_sha and r.get("author_association") in allowed:
            approved.add(login)
    return approved, blocked


def load_config(path: Path) -> dict:
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise GateError(f"Cannot read policy config: {e}") from e
    if not isinstance(c, dict):
        raise GateError("Policy must be a JSON object")
    for key in ("trusted_authors", "additional_high_risk_patterns", "required_check_names", "approver_associations"):
        value = c.get(key, [])
        if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
            raise GateError(f"{key} must be an array of nonempty strings")
    apps = c.get("required_check_apps", {})
    if not isinstance(apps, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in apps.items()):
        raise GateError("required_check_apps must map check names to GitHub App slugs")
    unknown = sorted(set(apps) - set(c.get("required_check_names", [])))
    if unknown:
        raise GateError(f"required_check_apps names checks not in required_check_names: {unknown}")
    bad = sorted(set(c.get("approver_associations", [])) - {"OWNER", "MEMBER", "COLLABORATOR"})
    if bad:
        raise GateError(f"approver_associations may contain only OWNER, MEMBER, COLLABORATOR; got {bad}")
    if not isinstance(c.get("require_resolved_review_threads", True), bool):
        raise GateError("require_resolved_review_threads must be boolean")
    wait = c.get("check_wait_seconds", 600)
    if isinstance(wait, bool) or not isinstance(wait, int) or not 0 <= wait <= 3600:
        raise GateError("check_wait_seconds must be an integer from 0 to 3600")
    return c


class Github:
    def __init__(self, token: str, repo: str):
        if not token or "/" not in repo:
            raise GateError("GH_TOKEN and GITHUB_REPOSITORY required")
        self.token, self.repo = token, repo

    def call(self, url: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cstack-gate/2",
        }
        try:
            with request.urlopen(request.Request(url, headers=headers, data=data), timeout=20) as resp:
                return json.load(resp)
        except (error.URLError, ValueError, TimeoutError) as e:
            raise GateError(f"GitHub API unavailable: {e}") from e

    def rest(self, endpoint: str):
        return self.call(f"{API}/repos/{self.repo}/{endpoint}")

    def pages(self, endpoint: str, max_pages: int = 30):
        out = []
        for p in range(1, max_pages + 1):
            delimiter = "&" if "?" in endpoint else "?"
            part = self.rest(f"{endpoint}{delimiter}per_page=100&page={p}")
            if not isinstance(part, list):
                raise GateError(f"Invalid paginated API response: {endpoint}")
            out.extend(part)
            if len(part) < 100:
                return out
        raise GateError(f"API pagination exceeds {max_pages * 100} items; fail closed")

    def unresolved_threads(self, number: int) -> list[str]:
        owner, repo = self.repo.split("/", 1)
        nodes, after = [], None
        for _ in range(30):
            q = '''query($owner:String!, $repo:String!, $number:Int!, $after:String) {
              repository(owner:$owner, name:$repo) {
                pullRequest(number:$number) {
                  reviewThreads(first:100, after:$after) {
                    nodes { id isResolved }
                    pageInfo { hasNextPage endCursor }
                  }
                }
              }
            }'''
            data = self.call(GRAPHQL, {"query": q, "variables": {"owner": owner, "repo": repo, "number": number, "after": after}})
            if data.get("errors"):
                raise GateError("GraphQL review thread query failed: " + str(data["errors"])[:300])
            try:
                threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]
            except (KeyError, TypeError) as e:
                raise GateError("Cannot retrieve PR review threads") from e
            nodes.extend(n["id"] for n in threads["nodes"] if not n["isResolved"])
            if not threads["pageInfo"]["hasNextPage"]:
                return nodes
            after = threads["pageInfo"]["endCursor"]
        raise GateError("More than 3000 review threads; fail closed")

    def checks(self, sha: str, name: str) -> list[dict]:
        result = self.rest(f"commits/{parse.quote(sha)}/check-runs?check_name={parse.quote(name)}&per_page=100")
        runs = result.get("check_runs")
        if not isinstance(runs, list):
            raise GateError(f"Invalid check-runs response for {name!r}")
        return runs


def check_failures(gh, head: str, names: list[str], wait_seconds: int, apps: dict | None = None,
                   sleep=time.sleep, clock=time.monotonic) -> list[str]:
    """Wait up to wait_seconds for required checks to finish, then demand success.

    When apps names the GitHub App expected to publish a check, runs of the same
    name from any other source (a workflow in the PR, say) are ignored.
    """
    apps = apps or {}
    deadline = clock() + wait_seconds
    while True:
        pending, failed = [], []
        for name in names:
            runs = gh.checks(head, name)
            if name in apps:
                runs = [r for r in runs if (r.get("app") or {}).get("slug") == apps[name]]
            # Check-run ids increase monotonically; a queued rerun has no started_at yet.
            latest = max(runs, key=lambda c: c.get("id") or 0, default=None)
            if latest is None or latest.get("status") != "completed":
                pending.append(name)
            elif latest.get("conclusion") != "success":
                failed.append(f"Required check {name!r} concluded {latest.get('conclusion')!r} on current head; need 'success'")
        remaining = deadline - clock()
        if failed or not pending or remaining <= 0:
            return failed + [f"Required check {name!r} has not completed on current head" for name in pending]
        sleep(min(POLL_SECONDS, remaining))


def human_failures(gh, number: int, head: str, author: str, needed: int, config: dict) -> tuple[list[str], set[str]]:
    reviews = gh.pages(f"pulls/{number}/reviews")
    approved, blocked = effective_reviews(reviews, head, author, config.get("approver_associations"))
    failures = []
    if blocked:
        failures.append("Active change requests by: " + ", ".join(sorted(blocked)))
    if len(approved) < needed:
        failures.append(f"Need {needed} current-head approvals from repository owners, members or collaborators; have {len(approved)}")
    if config.get("require_resolved_review_threads", True):
        open_threads = gh.unresolved_threads(number)
        if open_threads:
            failures.append(f"{len(open_threads)} unresolved review threads")
    return failures, approved


def evaluate(gh, number: int, config: dict, sleep=time.sleep, clock=time.monotonic) -> dict:
    pr = gh.rest(f"pulls/{number}")
    if pr.get("draft"):
        raise GateError("Draft pull request cannot merge")
    head = pr["head"]["sha"]
    author = pr["user"]["login"]
    paths = []
    for f in gh.pages(f"pulls/{number}/files"):
        paths.append(f["filename"])
        if f.get("previous_filename"):
            paths.append(f["previous_filename"])
    tier, reasons = classify(paths, config)
    needed = approvals_needed(tier, author, config)
    failures, approved = human_failures(gh, number, head, author, needed, config)
    names = config.get("required_check_names", [])
    apps = config.get("required_check_apps", {})
    warnings = [f"Required check {n!r} is not bound to a GitHub App in required_check_apps; any workflow can publish it"
                for n in names if n not in apps]
    if not names and needed == 0:
        failures.append("Zero-human merging requires at least one named automated review check")
    if names:
        # Only spend runner minutes waiting when the checks are the last thing missing.
        wait = 0 if failures else config.get("check_wait_seconds", 600)
        started = clock()
        failures += check_failures(gh, head, names, wait, apps, sleep, clock)
        if not failures and clock() > started:
            # Reviews and threads may have changed while we waited.
            failures, approved = human_failures(gh, number, head, author, needed, config)
    return {"risk_tier": tier, "reasons": reasons, "author": author, "trusted_author": is_trusted(author, config),
            "head": head, "approvals_needed": needed, "valid_human_approvers": sorted(approved),
            "warnings": warnings, "failures": failures}


def main() -> int:
    try:
        config = load_config(Path(os.getenv("CSTACK_CONFIG", ".cstack/policy.json")))
        repo = os.getenv("GITHUB_REPOSITORY", "")
        number = os.getenv("PR_NUMBER", "")
        if not number.isdigit():
            raise GateError("PR_NUMBER must be an integer")
        result = evaluate(Github(os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN", ""), repo), int(number), config)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        for warning in result["warnings"]:
            print(f"::warning::cstack gate: {warning}")
        if result["failures"]:
            print("cstack gate: BLOCKED", file=sys.stderr)
            for reason in result["failures"]:
                print(" - " + reason, file=sys.stderr)
            return 1
        print("cstack gate: PASS")
        return 0
    except (GateError, KeyError, TypeError) as e:
        print(f"cstack gate: BLOCKED ({e})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
