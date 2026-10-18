import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cstack_install", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), *args], capture_output=True, text=True)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args):
        result = run("--target", str(self.target), *args)
        return result

    def test_install_layout_and_idempotence(self):
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        for rel in [".claude/skills/cstack/SKILL.md", ".agents/skills/cstack/SKILL.md",
                    ".agents/skills/cstack/agents/openai.yaml", ".cursor/config/bugbot.yaml",
                    ".cursor/BUGBOT.md", ".cstack/gate.py", ".cstack/policy.json", ".cstack/manifest.json",
                    ".github/workflows/cstack-gate.yml", "REVIEW.md", ".github/pull_request_template.md"]:
            self.assertTrue((self.target / rel).is_file(), rel)
        self.assertFalse((self.target / ".cursor/skills").exists(), "Cursor already reads .claude and .agents")
        again = self.install()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("0 changes", again.stdout)

    def test_dry_run_writes_nothing(self):
        result = self.install("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WRITE", result.stdout)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_local_edit_is_a_conflict_until_force(self):
        self.install()
        f = self.target / ".agents/skills/cstack/SKILL.md"
        f.write_text("MY CUSTOM WORK")
        blocked = self.install()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(f.read_text(), "MY CUSTOM WORK")
        forced = self.install("--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(f.read_bytes(), (ROOT / "skills/cstack/SKILL.md").read_bytes())

    def test_unmodified_older_copy_upgrades_without_force(self):
        self.install()
        f = self.target / ".claude/skills/cstack/SKILL.md"
        f.write_text("cstack v0 as shipped")
        manifest = self.target / ".cstack/manifest.json"
        data = json.loads(manifest.read_text())
        data["files"][".claude/skills/cstack/SKILL.md"] = installer.sha256(f)
        manifest.write_text(json.dumps(data))
        upgraded = self.install()
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assertEqual(f.read_bytes(), (ROOT / "skills/cstack/SKILL.md").read_bytes())

    def test_obsolete_unmodified_file_is_removed_and_edited_one_kept(self):
        self.install()
        stale = self.target / ".claude/skills/cstack/references/old.md"
        edited = self.target / ".claude/skills/cstack/references/older.md"
        stale.write_text("old")
        edited.write_text("old but edited")
        manifest = self.target / ".cstack/manifest.json"
        data = json.loads(manifest.read_text())
        data["files"][".claude/skills/cstack/references/old.md"] = installer.sha256(stale)
        data["files"][".claude/skills/cstack/references/older.md"] = "0" * 64
        manifest.write_text(json.dumps(data))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(stale.exists())
        self.assertTrue(edited.exists())

    def test_seed_files_are_never_overwritten(self):
        self.install()
        policy = self.target / ".cstack/policy.json"
        policy.write_text('{"trusted_authors": ["me"]}')
        review = self.target / "REVIEW.md"
        review.write_text("# ours\n")
        result = self.install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(policy.read_text(), '{"trusted_authors": ["me"]}')
        self.assertEqual(review.read_text(), "# ours\n")

    def test_existing_bugbot_config_is_kept(self):
        (self.target / ".cursor/config").mkdir(parents=True)
        cfg = self.target / ".cursor/config/bugbot.yaml"
        cfg.write_text("version: 1\ntriggers:\n  drafts: true\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cfg.read_text(), "version: 1\ntriggers:\n  drafts: true\n")

    def test_malformed_bugbot_markers_fail_before_writing(self):
        (self.target / ".cursor").mkdir()
        for text in ["<!-- cstack:end -->\n<!-- cstack:begin -->\n", "<!-- cstack:begin -->\n"]:
            with self.subTest(text=text):
                (self.target / ".cursor/BUGBOT.md").write_text(text)
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("malformed", result.stderr)
                self.assertEqual(sorted(p.name for p in self.target.iterdir()), [".cursor"])

    def test_existing_pr_template_anywhere_is_respected(self):
        (self.target / "docs").mkdir()
        (self.target / "docs/pull_request_template.md").write_text("ours")
        self.install()
        self.assertFalse((self.target / ".github/pull_request_template.md").exists())

    def test_existing_bugbot_is_preserved_and_block_updated_in_place(self):
        (self.target / ".cursor").mkdir()
        bugbot = self.target / ".cursor/BUGBOT.md"
        bugbot.write_text("# Existing rule\n\n<!-- cstack:begin -->\nold\n<!-- cstack:end -->\n\n# Tail rule\n")
        result = self.install("--no-gate")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = bugbot.read_text()
        self.assertIn("# Existing rule", text)
        self.assertIn("# Tail rule", text)
        self.assertNotIn("\nold\n", text)
        self.assertEqual(text.count("cstack:begin"), 1)
        self.assertFalse((self.target / ".cstack/gate.py").exists())
        self.assertFalse((self.target / ".cstack/policy.json").exists())

    def test_hosts_selection(self):
        result = self.install("--hosts", "codex", "--no-gate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / ".agents/skills/cstack/SKILL.md").exists())
        self.assertFalse((self.target / ".claude").exists())
        self.assertNotEqual(self.install("--hosts", "vscode").returncode, 0)

    def test_skill_only_mode_installs_just_the_skill(self):
        installer.install(self.target, hosts=["claude", "codex"], skill_only=True)
        self.assertTrue((self.target / ".claude/skills/cstack/SKILL.md").exists())
        self.assertFalse((self.target / ".cursor").exists())
        self.assertFalse((self.target / "REVIEW.md").exists())


class PackageTests(unittest.TestCase):
    def test_skill_frontmatter(self):
        text = (ROOT / "skills/cstack/SKILL.md").read_text()
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match)
        fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
        self.assertEqual(fields["name"], "cstack")
        self.assertLessEqual(len(fields["description"]), 1024)
        self.assertLess(len(text.splitlines()), 500)

    def test_skill_references_exist(self):
        text = (ROOT / "skills/cstack/SKILL.md").read_text()
        for ref in set(re.findall(r"`(references/[\w-]+\.md)`", text)):
            self.assertTrue((ROOT / "skills/cstack" / ref).is_file(), ref)

    def test_plugin_manifests(self):
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(plugin["name"], "cstack")
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])

    def test_gate_workflow_runs_base_branch_gate_only(self):
        wf = (ROOT / "templates/workflows/cstack-gate.yml").read_text()
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", wf)
        self.assertIn("python3 .cstack/gate.py", wf)
        self.assertNotIn("pull_request_target", wf)
        self.assertNotIn("write", wf.split("jobs:")[0])
        self.assertFalse((ROOT / ".github/workflows/cstack-gate.yml").exists(),
                         "the template must not run on cstack's own PRs")


if __name__ == "__main__":
    unittest.main()
