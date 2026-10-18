import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def doctor(*args, env=None):
    return subprocess.run([sys.executable, str(ROOT / "scripts/doctor.py"), *args, "--json"],
                          capture_output=True, text=True, env=env)


def install(target, *args):
    subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), "--target", str(target), *args],
                   capture_output=True, text=True, check=True)


def statuses(result):
    data = json.loads(result.stdout)
    return {item["check"]: item["status"] for item in data["items"]}


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.target, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_repo_has_todos(self):
        result = doctor("--target", str(self.target), "--no-github")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(statuses(result)["cstack skill not installed"], "todo")

    def test_fresh_install_leaves_only_owner_decisions(self):
        install(self.target)
        result = doctor("--target", str(self.target), "--no-github")
        found = statuses(result)
        self.assertEqual(found["claude skill installed and current (.claude/skills/cstack)"], "ok")
        self.assertEqual(found["review requests route to cstack via CLAUDE.md and AGENTS.md"], "ok")
        todos = [check for check, status in found.items() if status == "todo"]
        self.assertEqual(todos, ["trusted_authors is empty, so every PR needs two human approvals"])

    def test_clean_after_owner_sets_trusted_authors(self):
        install(self.target)
        policy = self.target / ".cstack/policy.json"
        data = json.loads(policy.read_text())
        data["trusted_authors"] = ["maintainer"]
        policy.write_text(json.dumps(data))
        result = doctor("--target", str(self.target), "--no-github")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_outdated_skill_is_flagged(self):
        install(self.target, "--no-gate")
        (self.target / ".claude/skills/cstack/SKILL.md").write_text("old")
        found = statuses(doctor("--target", str(self.target), "--no-github"))
        self.assertIn("warn", [s for c, s in found.items() if c.startswith("claude skill differs")])

    def test_invalid_policy_is_a_todo(self):
        install(self.target)
        (self.target / ".cstack/policy.json").write_text('{"trusted_authors": 1}')
        found = statuses(doctor("--target", str(self.target), "--no-github"))
        self.assertEqual(found["policy.json is invalid"], "todo")

    def test_global_checks_only_tools_present(self):
        home = self.target / "home"
        (home / ".claude").mkdir(parents=True)
        env = dict(os.environ, HOME=str(home))
        env.pop("CODEX_HOME", None)
        found = statuses(doctor("--global", env=env))
        self.assertEqual(found["no routing block in ~/.claude/CLAUDE.md"], "todo")
        self.assertFalse(any("Codex" in c or ".codex" in c for c in found))


if __name__ == "__main__":
    unittest.main()
