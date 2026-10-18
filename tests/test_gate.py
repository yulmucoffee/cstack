import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cstack_gate", ROOT / "scripts/gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.config = {"trusted_authors": ["maintainer"], "required_check_names": ["Cursor Bugbot"], "additional_high_risk_patterns": []}

    def tier(self, *paths):
        return gate.classify(list(paths), self.config)[0]

    def test_docs_only_low(self):
        self.assertEqual(self.tier("README.md", "docs/setup.mdx", "docs/img/flow.png"), "low")

    def test_normal_code_medium(self):
        self.assertEqual(self.tier("src/index.ts"), "medium")

    def test_dependency_and_build_text_files_are_not_docs(self):
        for p in ["requirements.txt", "requirements-dev.txt", "CMakeLists.txt", "docs/conf.py"]:
            with self.subTest(path=p):
                self.assertEqual(self.tier(p), "medium")

    def test_agent_and_reviewer_instructions_are_not_docs(self):
        for p in ["CLAUDE.md", "AGENTS.md", "REVIEW.md", "pkg/api/REVIEW.md", ".claude/skills/x/SKILL.md",
                  ".agents/skills/cstack/references/review-rubric.md", ".cursor/rules/style.mdc",
                  ".github/pull_request_template.md"]:
            with self.subTest(path=p):
                self.assertEqual(self.tier(p), "medium")

    def test_sensitive_paths_high(self):
        for p in [".github/workflows/ci.yml", ".cursor/config/bugbot.yaml", ".cursor/BUGBOT.md",
                  "api/.cursor/BUGBOT.md", "server/auth/login.py", "auth/session.py", ".cstack/policy.json",
                  "db/migrations/001.sql", "CODEOWNERS", ".github/CODEOWNERS", "package-lock.json",
                  "web/pnpm-lock.yaml", "go.sum", ".claude/settings.json", ".mcp.json", ".codex/config.toml",
                  "infra/main.tf"]:
            with self.subTest(path=p):
                self.assertEqual(self.tier(p), "high")

    def test_other_ci_systems_high(self):
        for p in [".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", "ci/Jenkinsfile", ".github/scripts/release.sh"]:
            with self.subTest(path=p):
                self.assertEqual(self.tier(p), "high")

    def test_other_agent_instruction_dirs_not_docs(self):
        for p in [".windsurf/rules/a.md", ".clinerules/x.md", ".junie/guidelines.md", ".roo/rules/a.md"]:
            with self.subTest(path=p):
                self.assertEqual(self.tier(p), "medium")

    def test_lock_substring_is_not_a_lockfile(self):
        for p in ["src/clock.ts", "ui/Block.tsx", "lib/blocking_queue.py"]:
            with self.subTest(path=p):
                self.assertEqual(self.tier(p), "medium")

    def test_oauth_is_not_auth_directory(self):
        self.assertEqual(self.tier("src/oauth/client.ts"), "medium")

    def test_additional_high_risk_patterns(self):
        self.config["additional_high_risk_patterns"] = ["infra/**"]
        self.assertEqual(self.tier("infra/k8s/app.yaml"), "high")

    def test_sensitive_rename_old_path_high(self):
        self.assertEqual(self.tier("docs/clean.md", ".github/workflows/deleted.yml"), "high")

    def test_fail_closed_on_empty(self):
        self.assertEqual(self.tier(), "high")

    def test_approvals_by_tier_and_trust(self):
        self.assertEqual(gate.approvals_needed("low", "outsider", self.config), 2)
        self.assertEqual(gate.approvals_needed("low", "maintainer", self.config), 0)
        self.assertEqual(gate.approvals_needed("medium", "maintainer", self.config), 1)
        self.assertEqual(gate.approvals_needed("high", "maintainer", self.config), 2)

    def test_trusted_author_match_ignores_case(self):
        self.assertEqual(gate.approvals_needed("low", "Maintainer", self.config), 0)

    def test_review_approval_exact_commit(self):
        reviews = [
            {"user": {"login": "alice", "type": "User"}, "state": "APPROVED", "commit_id": "old", "author_association": "MEMBER"},
            {"user": {"login": "bob", "type": "Bot"}, "state": "APPROVED", "commit_id": "new", "author_association": "MEMBER"},
            {"user": {"login": "writer", "type": "User"}, "state": "APPROVED", "commit_id": "new", "author_association": "OWNER"},
            {"user": {"login": "carol", "type": "User"}, "state": "APPROVED", "commit_id": "new", "author_association": "COLLABORATOR"},
            {"user": {"login": "dave", "type": "User"}, "state": "CHANGES_REQUESTED", "commit_id": "new"},
        ]
        approved, blocked = gate.effective_reviews(reviews, "new", "Writer")
        self.assertEqual(approved, {"carol"})
        self.assertEqual(blocked, {"dave"})

    def test_approvals_without_a_repository_role_do_not_count(self):
        reviews = [{"user": {"login": u, "type": "User"}, "state": "APPROVED", "commit_id": "H", "author_association": a}
                   for u, a in [("sock1", "NONE"), ("sock2", "CONTRIBUTOR"), ("sock3", None), ("real", "MEMBER")]]
        self.assertEqual(gate.effective_reviews(reviews, "H", "attacker"), ({"real"}, set()))
        self.assertEqual(gate.effective_reviews(reviews, "H", "attacker", ["OWNER"]), (set(), set()))

    def test_subsequent_changes_requested_supersedes_approval(self):
        reviews = [
            {"user": {"login": "alice", "type": "User"}, "state": "APPROVED", "commit_id": "sha"},
            {"user": {"login": "alice", "type": "User"}, "state": "CHANGES_REQUESTED", "commit_id": "sha"},
        ]
        self.assertEqual(gate.effective_reviews(reviews, "sha", "writer"), (set(), {"alice"}))

    def test_dismissed_change_request_no_longer_blocks(self):
        reviews = [{"user": {"login": "alice", "type": "User"}, "state": "DISMISSED", "commit_id": "sha"}]
        self.assertEqual(gate.effective_reviews(reviews, "sha", "writer"), (set(), set()))

    def test_load_config_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            for bad in ['{"trusted_authors": 1}', '{"required_check_apps": ["cursor"]}',
                        '{"required_check_names": ["Cursor Bugbot"], "required_check_apps": {"Cursor BugBot": "cursor"}}',
                        '{"approver_associations": ["CONTRIBUTOR"]}', '{"check_wait_seconds": -1}', '{"check_wait_seconds": true}', "[]"]:
                with self.subTest(policy=bad):
                    path.write_text(bad)
                    with self.assertRaises(gate.GateError):
                        gate.load_config(path)

    def test_shipped_policy_is_valid(self):
        config = gate.load_config(ROOT / "configs/policy.json")
        self.assertEqual(config["trusted_authors"], [])


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeGithub:
    def __init__(self, *, check_runs=None, unresolved=None, reviews=None, files=None, author="maintainer"):
        self.check_runs = check_runs if check_runs is not None else [[success()]]
        self.unresolved = unresolved if unresolved is not None else []
        self.reviews = reviews or []
        self.files = files or [{"filename": "docs/README.md"}]
        self.author = author
        self.check_calls = 0

    def rest(self, endpoint):
        if endpoint.startswith("pulls/"):
            return {"draft": False, "head": {"sha": "head"}, "user": {"login": self.author}}
        raise AssertionError(endpoint)

    def pages(self, endpoint):
        if endpoint.endswith("/files"):
            return self.files
        if endpoint.endswith("/reviews"):
            return self.reviews
        raise AssertionError(endpoint)

    def unresolved_threads(self, number):
        return self.unresolved() if callable(self.unresolved) else self.unresolved

    def checks(self, sha, name):
        assert sha == "head" and name == "Cursor Bugbot"
        runs = self.check_runs[min(self.check_calls, len(self.check_runs) - 1)]
        self.check_calls += 1
        return runs


def success(app="cursor", id=1):
    return {"id": id, "name": "Cursor Bugbot", "status": "completed", "conclusion": "success",
            "started_at": "2026-01-01T00:00:00Z", "app": {"slug": app}}


def neutral():
    return {"id": 1, "name": "Cursor Bugbot", "status": "completed", "conclusion": "neutral",
            "started_at": "2026-01-01T00:00:00Z", "app": {"slug": "other"}}


def running(id=2):
    return {"id": id, "name": "Cursor Bugbot", "status": "in_progress", "conclusion": None,
            "started_at": "2026-01-01T00:05:00Z", "app": {"slug": "cursor"}}


def queued(id=3):
    return {"id": id, "name": "Cursor Bugbot", "status": "queued", "conclusion": None, "started_at": None,
            "app": {"slug": "cursor"}}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.config = {"trusted_authors": ["maintainer"], "required_check_names": ["Cursor Bugbot"],
                       "require_resolved_review_threads": True, "check_wait_seconds": 120}
        self.clock = FakeClock()

    def run_gate(self, gh):
        return gate.evaluate(gh, 42, self.config, sleep=self.clock.sleep, clock=self.clock.clock)

    def test_low_trusted_can_pass_if_bot_success(self):
        self.assertEqual(self.run_gate(FakeGithub())["failures"], [])

    def test_neutral_bot_blocks(self):
        failures = self.run_gate(FakeGithub(check_runs=[[neutral()]]))["failures"]
        self.assertTrue(any("neutral" in f for f in failures))

    def test_latest_run_wins(self):
        self.assertTrue(self.run_gate(FakeGithub(check_runs=[[success(), running()]]))["failures"])

    def test_queued_rerun_beats_older_success(self):
        self.config["check_wait_seconds"] = 0
        self.assertTrue(self.run_gate(FakeGithub(check_runs=[[success(id=1), queued(id=9)]]))["failures"])

    def test_threads_rechecked_after_waiting(self):
        gh = FakeGithub(check_runs=[[running()], [success(id=5)]])
        gh.unresolved = lambda: ["t1"] if self.clock.now > 0 else []
        self.assertEqual(self.run_gate(gh)["failures"], ["1 unresolved review threads"])

    def test_waits_for_check_to_finish(self):
        gh = FakeGithub(check_runs=[[], [running()], [success()]])
        self.assertEqual(self.run_gate(gh)["failures"], [])
        self.assertEqual(gh.check_calls, 3)

    def test_wait_times_out(self):
        failures = self.run_gate(FakeGithub(check_runs=[[running()]]))["failures"]
        self.assertTrue(any("has not completed" in f for f in failures))
        self.assertLessEqual(self.clock.now, 120)

    def test_no_waiting_when_already_blocked(self):
        gh = FakeGithub(check_runs=[[running()]], unresolved=["t1"])
        self.assertTrue(self.run_gate(gh)["failures"])
        self.assertEqual(self.clock.sleeps, [])

    def test_unresolved_thread_blocks(self):
        self.assertTrue(self.run_gate(FakeGithub(unresolved=["t1"]))["failures"])

    def test_untrusted_author_needs_two_humans_even_for_docs(self):
        result = self.run_gate(FakeGithub(author="drive-by"))
        self.assertEqual(result["approvals_needed"], 2)
        self.assertTrue(result["failures"])

    def test_two_current_head_approvals_pass_high_risk(self):
        reviews = [{"user": {"login": u, "type": "User"}, "state": "APPROVED", "commit_id": "head",
                    "author_association": "MEMBER"} for u in ("a", "b")]
        gh = FakeGithub(files=[{"filename": ".github/workflows/ci.yml"}], reviews=reviews)
        self.assertEqual(self.run_gate(gh)["failures"], [])

    def test_check_from_unexpected_app_is_ignored(self):
        self.config["required_check_apps"] = {"Cursor Bugbot": "cursor"}
        spoofed = success(app="github-actions", id=7)
        self.assertEqual(self.run_gate(FakeGithub(check_runs=[[neutral(), spoofed]]))["failures"],
                         ["Required check 'Cursor Bugbot' has not completed on current head"])
        self.assertEqual(self.run_gate(FakeGithub(check_runs=[[success(), spoofed]]))["failures"], [])

    def test_unbound_check_warns(self):
        self.assertTrue(self.run_gate(FakeGithub())["warnings"])
        self.config["required_check_apps"] = {"Cursor Bugbot": "cursor"}
        self.assertEqual(self.run_gate(FakeGithub())["warnings"], [])

    def test_zero_human_requires_named_check(self):
        self.config["required_check_names"] = []
        self.assertTrue(self.run_gate(FakeGithub())["failures"])


if __name__ == "__main__":
    unittest.main()
