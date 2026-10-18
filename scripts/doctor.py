#!/usr/bin/env python3
"""Check a cstack installation and say exactly what is left to do.

Read-only. Uses the GitHub CLI (`gh`) for the GitHub checks when it is
installed and signed in, and skips them otherwise. Exits 1 while any TODO
remains, so an agent can loop until it is clean.

  python3 scripts/doctor.py --target /path/to/repo
  python3 scripts/doctor.py --global
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402
import install  # noqa: E402

ROUTING_SIGNATURE = "use the `cstack` skill in `review` mode"
CURSOR_APP = "cursor"


class Report:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, status: str, what: str, next_step: str = ""):
        self.items.append({"status": status, "check": what, "next": next_step})

    def ok(self, what):
        self.add("ok", what)

    def todo(self, what, next_step):
        self.add("todo", what, next_step)

    def warn(self, what, next_step=""):
        self.add("warn", what, next_step)

    def skip(self, what, why):
        self.add("skip", what, why)


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, p.stdout.strip() or p.stderr.strip()


def check_skill(report: Report, base: Path, label: str):
    source = install.SKILL / "SKILL.md"
    found = False
    for host, rel in install.HOST_DIRS.items():
        skill = base / rel / "SKILL.md"
        if not skill.is_file():
            continue
        found = True
        if skill.read_bytes() == source.read_bytes():
            report.ok(f"{host} skill installed and current ({label}{rel})")
        else:
            report.warn(f"{host} skill differs from this cstack checkout ({label}{rel})",
                        "Rerun install.py to upgrade, or keep it if you edited it on purpose.")
    if not found:
        report.todo("cstack skill not installed", "Run scripts/install.py (see FOR_AGENTS.md step 3).")


def has_routing(path: Path) -> bool:
    return path.is_file() and ROUTING_SIGNATURE in path.read_text(encoding="utf-8")


def check_project(report: Report, target: Path, use_github: bool):
    check_skill(report, target, "")

    routed = [name for name in ("CLAUDE.md", "AGENTS.md") if has_routing(target / name)]
    if routed:
        report.ok("review requests route to cstack via " + " and ".join(routed))
        if not has_routing(target / "CLAUDE.md") and (target / ".claude/skills/cstack").is_dir() \
                and not install.imports_agents_md(target / "CLAUDE.md"):
            report.warn("Claude Code does not read AGENTS.md, and CLAUDE.md has no routing block",
                        "Rerun install.py with --hosts including claude.")
    else:
        report.todo("no review-routing block in CLAUDE.md or AGENTS.md", "Rerun install.py without --no-routing.")

    bugbot = target / ".cursor/BUGBOT.md"
    if bugbot.is_file() and install.MARKER_START in bugbot.read_text(encoding="utf-8"):
        report.ok("BugBot rules present (.cursor/BUGBOT.md)")
    else:
        report.warn("BugBot rules missing", "Rerun install.py, unless this repo does not use BugBot.")

    gate_file = target / ".cstack/gate.py"
    if not gate_file.is_file():
        report.skip("merge gate", "not installed (--no-gate); nothing is enforced on GitHub")
        return
    policy_ok = check_policy(report, target)
    if not (target / ".github/workflows/cstack-gate.yml").is_file():
        report.todo("gate workflow missing", "Rerun install.py to restore .github/workflows/cstack-gate.yml.")

    default = default_branch(target)
    if default:
        code, _ = run(["git", "cat-file", "-e", f"origin/{default}:.cstack/gate.py"], target)
        if code == 0:
            report.ok(f"gate is on the default branch (origin/{default})")
        else:
            report.todo(f"gate is not on origin/{default} yet",
                        "Commit the install, open a PR and merge it before requiring cstack-risk-gate. "
                        "The gate fails on the PR that adds it, because its base has no gate.py yet; "
                        "a maintainer merges that one PR with normal review.")
    else:
        report.skip("default branch", "no origin remote found")

    if not use_github:
        report.skip("GitHub settings", "skipped (--no-github, or gh is missing or not signed in)")
        return
    check_github(report, target, policy_ok)


def check_policy(report: Report, target: Path) -> dict | None:
    try:
        policy = gate.load_config(target / ".cstack/policy.json")
    except gate.GateError as e:
        report.todo("policy.json is invalid", str(e))
        return None
    if policy.get("trusted_authors"):
        report.ok(f"trusted_authors set ({len(policy['trusted_authors'])} login(s))")
    else:
        report.todo("trusted_authors is empty, so every PR needs two human approvals",
                    "Ask the user which GitHub logins are trusted maintainers and add them to .cstack/policy.json.")
    apps = policy.get("required_check_apps", {})
    unbound = [n for n in policy.get("required_check_names", []) if n not in apps]
    if unbound:
        report.warn(f"required checks not bound to a GitHub App: {unbound}",
                    "Add them to required_check_apps so a workflow cannot fake them.")
    return policy


def default_branch(target: Path) -> str | None:
    code, out = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], target)
    if code == 0 and out.startswith("origin/"):
        return out.split("/", 1)[1]
    code, out = run(["git", "remote", "show", "origin"], target)
    for line in out.splitlines() if code == 0 else []:
        if "HEAD branch:" in line:
            return line.split(":", 1)[1].strip()
    return None


def gh_json(args: list[str], cwd: Path):
    code, out = run(["gh", *args], cwd)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def check_github(report: Report, target: Path, policy: dict | None):
    repo = gh_json(["repo", "view", "--json", "nameWithOwner,defaultBranchRef"], target)
    if not repo:
        report.skip("GitHub settings", "gh cannot resolve this repository")
        return
    name, branch = repo["nameWithOwner"], repo["defaultBranchRef"]["name"]
    rules = gh_json(["api", f"repos/{name}/rules/branches/{branch}"], target)
    if rules is None:
        report.skip("branch rules", "cannot read them (needs read access to repository settings)")
    else:
        required = {c.get("context") for r in rules if r.get("type") == "required_status_checks"
                    for c in r.get("parameters", {}).get("required_status_checks", [])}
        wanted = ["cstack-risk-gate"] + (policy or {}).get("required_check_names", [])
        missing = [c for c in wanted if c not in required]
        if missing:
            report.todo(f"{branch} does not require {missing}",
                        "With the user's OK and admin rights: gh api -X POST repos/"
                        f"{name}/rulesets --input {install.ROOT / 'templates/ruleset.json'} (add the repo's own CI checks first). "
                        "Or set it in Settings > Rules > Rulesets.")
        else:
            report.ok(f"{branch} requires " + ", ".join(wanted))
        pr_rules = [r.get("parameters", {}) for r in rules if r.get("type") == "pull_request"]
        if not pr_rules:
            report.warn(f"{branch} has no pull request rule", "Apply the cstack ruleset (see the TODO above) or add one in Settings.")
        elif not any(p.get("dismiss_stale_reviews_on_push") and p.get("required_review_thread_resolution") for p in pr_rules):
            report.warn("stale-approval dismissal or conversation resolution is off",
                        "Turn both on in the ruleset's pull request rule.")

    if policy and "Cursor Bugbot" in policy.get("required_check_names", []):
        prs = gh_json(["pr", "list", "--state", "all", "--limit", "5", "--json", "headRefOid"], target) or []
        seen = False
        for pr in prs:
            runs = gh_json(["api", f"repos/{name}/commits/{pr['headRefOid']}/check-runs?check_name=Cursor%20Bugbot"], target)
            if runs and any((r.get("app") or {}).get("slug") == CURSOR_APP for r in runs.get("check_runs", [])):
                seen = True
                break
        if seen:
            report.ok("BugBot has reviewed a recent PR")
        elif prs:
            report.todo("no BugBot check on the last 5 PRs",
                        "The user enables BugBot for this repo in the Cursor dashboard (cursor.com > Bugbot).")
        else:
            report.skip("BugBot", "no PRs yet to tell whether it is enabled")

    owners = [p for p in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS") if (target / p).is_file()]
    if owners:
        report.ok(f"CODEOWNERS present ({owners[0]})")
    else:
        report.warn("no CODEOWNERS file",
                    "Add owners for .github/workflows/, .cstack/ and .cursor/ and require code-owner review, "
                    "so a PR cannot edit the gate unnoticed.")


def check_global(report: Report, home: Path):
    check_skill(report, home, "~/")
    if (home / ".claude").is_dir():
        if has_routing(home / ".claude/CLAUDE.md"):
            report.ok("Claude Code routes reviews to cstack (~/.claude/CLAUDE.md)")
        else:
            report.todo("no routing block in ~/.claude/CLAUDE.md", "Rerun install.py --global.")
    codex = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else home / ".codex"
    if codex.is_dir():
        target = codex / "AGENTS.override.md" if (codex / "AGENTS.override.md").is_file() else codex / "AGENTS.md"
        if has_routing(target):
            report.ok(f"Codex routes reviews to cstack ({target.name})")
        else:
            report.todo(f"no routing block in {target}", "Rerun install.py --global.")
    report.skip("Cursor user rules", "stored in Cursor settings; paste the routing text from templates/routing.md")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--target", type=Path, help="Repository to check (default: current directory)")
    where.add_argument("--global", dest="global_", action="store_true", help="Check the personal install")
    parser.add_argument("--no-github", action="store_true", help="Skip checks that call the GitHub API")
    parser.add_argument("--json", action="store_true", help="Print machine-readable results")
    args = parser.parse_args()

    report = Report()
    if args.global_:
        place = Path.home()
        check_global(report, place)
    else:
        place = (args.target or Path.cwd()).resolve()
        use_github = not args.no_github and shutil.which("gh") is not None and run(["gh", "auth", "status"], place)[0] == 0
        check_project(report, place, use_github)

    todo = [i for i in report.items if i["status"] == "todo"]
    if args.json:
        print(json.dumps({"place": str(place), "items": report.items, "todo": len(todo)}, indent=2, ensure_ascii=False))
    else:
        print(f"cstack doctor: {place}")
        for i in report.items:
            print(f"  [{i['status']:<4}] {i['check']}")
            if i["next"]:
                print(f"         -> {i['next']}")
        counts = {s: sum(1 for i in report.items if i["status"] == s) for s in ("ok", "todo", "warn", "skip")}
        print("  " + ", ".join(f"{n} {s}" for s, n in counts.items()))
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main())
