import importlib.util
import json
import os
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


def run(*args, env=None):
    return subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env)


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
        self.assertEqual(f.read_text(encoding="utf-8"), "MY CUSTOM WORK")
        forced = self.install("--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(f.read_bytes(), (ROOT / "skills/cstack/SKILL.md").read_bytes())

    def test_unmodified_older_copy_upgrades_without_force(self):
        self.install()
        f = self.target / ".claude/skills/cstack/SKILL.md"
        f.write_text("cstack v0 as shipped")
        manifest = self.target / ".cstack/manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
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
        data = json.loads(manifest.read_text(encoding="utf-8"))
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
        self.assertEqual(policy.read_text(encoding="utf-8"), '{"trusted_authors": ["me"]}')
        self.assertEqual(review.read_text(encoding="utf-8"), "# ours\n")

    def test_existing_bugbot_config_is_kept(self):
        (self.target / ".cursor/config").mkdir(parents=True)
        cfg = self.target / ".cursor/config/bugbot.yaml"
        cfg.write_text("version: 1\ntriggers:\n  drafts: true\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cfg.read_text(encoding="utf-8"), "version: 1\ntriggers:\n  drafts: true\n")

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
        text = bugbot.read_text(encoding="utf-8")
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


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def routed(self, path):
        return path.is_file() and "use the `cstack` skill in `review` mode" in path.read_text(encoding="utf-8")

    def test_project_install_routes_reviews_in_claude_and_agents_md(self):
        (self.target / "CLAUDE.md").write_text("# House rules\n\nUse tabs.\n")
        self.assertEqual(run("--target", str(self.target), "--no-gate").returncode, 0)
        self.assertTrue(self.routed(self.target / "CLAUDE.md"))
        self.assertTrue(self.routed(self.target / "AGENTS.md"))
        self.assertIn("Use tabs.", (self.target / "CLAUDE.md").read_text(encoding="utf-8"))
        again = run("--target", str(self.target), "--no-gate")
        self.assertIn("0 changes", again.stdout)
        self.assertEqual((self.target / "CLAUDE.md").read_text(encoding="utf-8").count("cstack:begin"), 1)

    def test_claude_md_that_imports_agents_md_is_left_alone(self):
        (self.target / "CLAUDE.md").write_text("@AGENTS.md\n")
        run("--target", str(self.target), "--no-gate")
        self.assertEqual((self.target / "CLAUDE.md").read_text(encoding="utf-8"), "@AGENTS.md\n")
        self.assertTrue(self.routed(self.target / "AGENTS.md"))

    def test_symlinked_claude_md_gets_one_block(self):
        (self.target / "AGENTS.md").write_text("# Shared\n")
        try:
            (self.target / "CLAUDE.md").symlink_to("AGENTS.md")
        except OSError as e:  # Windows without symlink privilege or developer mode
            self.skipTest(f"symlinks unavailable: {e}")
        run("--target", str(self.target), "--no-gate")
        self.assertEqual((self.target / "AGENTS.md").read_text(encoding="utf-8").count("cstack:begin"), 1)

    def test_merged_routing_block_keeps_the_rest_of_the_file_byte_for_byte(self):
        cases = {
            "lf": (b"# Shared\n\nUse tabs.\n", b"\n"),
            "crlf": (b"# Shared\r\n\r\nUse tabs.\r\n", b"\r\n"),
            "mostly lf, one crlf line": (b"# A\n\nx\ny\nz\r\n", b"\n"),
            "mostly crlf, one lf line": (b"# A\r\n\r\nx\r\ny\nz\r\n", b"\r\n"),
        }
        for name, (original, eol) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as d:
                target = Path(d)
                (target / "AGENTS.md").write_bytes(original)
                result = run("--target", str(target), "--no-gate", "--hosts", "codex")
                self.assertEqual(result.returncode, 0, result.stderr)
                data = (target / "AGENTS.md").read_bytes()
                self.assertTrue(data.startswith(original.rstrip()), data[:60])
                block = data[data.index(b"<!-- cstack:begin -->"):]
                if eol == b"\n":
                    self.assertNotIn(b"\r", block)
                else:
                    self.assertEqual(block.count(b"\n"), block.count(b"\r\n"))
                self.assertIn("0 changes", run("--target", str(target), "--no-gate", "--hosts", "codex").stdout)

    def test_output_is_utf8_even_on_a_legacy_code_page_pipe(self):
        target = self.target / "한글 프로젝트 😀"
        target.mkdir()
        result = run("--target", str(target), "--no-gate", env=dict(os.environ, PYTHONIOENCODING="cp1252"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("한글 프로젝트 😀", result.stdout)

    def test_windows_checkout_of_installed_files_is_not_a_conflict(self):
        run("--target", str(self.target), "--no-gate")
        for f in (self.target / ".claude/skills/cstack").rglob("*"):
            if f.is_file():
                f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        again = run("--target", str(self.target), "--no-gate")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("0 changes", again.stdout)

    def test_hosts_pick_routing_files(self):
        run("--target", str(self.target), "--no-gate", "--hosts", "claude")
        self.assertTrue(self.routed(self.target / "CLAUDE.md"))
        self.assertFalse((self.target / "AGENTS.md").exists())

    def test_no_routing(self):
        run("--target", str(self.target), "--no-gate", "--no-routing")
        self.assertFalse((self.target / "CLAUDE.md").exists())
        self.assertFalse((self.target / "AGENTS.md").exists())

    def test_global_install_routes_only_for_tools_that_exist(self):
        (self.target / ".claude").mkdir()
        old = os.environ.pop("CODEX_HOME", None)
        try:
            installer.install(self.target, hosts=["claude", "codex"], skill_only=True)
            self.assertTrue(self.routed(self.target / ".claude/CLAUDE.md"))
            self.assertFalse((self.target / ".codex").exists())
            (self.target / ".codex").mkdir()
            (self.target / ".codex/AGENTS.override.md").write_text("# override\n")
            installer.install(self.target, hosts=["claude", "codex"], skill_only=True)
            self.assertTrue(self.routed(self.target / ".codex/AGENTS.override.md"))
            self.assertFalse((self.target / ".codex/AGENTS.md").exists())
            home = self.target / "elsewhere"
            home.mkdir()
            os.environ["CODEX_HOME"] = str(home)
            installer.install(self.target, hosts=["codex"], skill_only=True)
            self.assertTrue(self.routed(home / "AGENTS.md"))
        finally:
            os.environ.pop("CODEX_HOME", None)
            if old is not None:
                os.environ["CODEX_HOME"] = old

    def test_skill_description_claims_review_requests(self):
        text = (ROOT / "skills/cstack/SKILL.md").read_text(encoding="utf-8")
        description = text.split("description: ", 1)[1].split("\n", 1)[0]
        for phrase in ["review this PR", "code review", "코드 리뷰", "even when another review skill"]:
            self.assertIn(phrase, description)


class PackageTests(unittest.TestCase):
    def test_skill_frontmatter(self):
        text = (ROOT / "skills/cstack/SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match)
        fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
        self.assertEqual(fields["name"], "cstack")
        self.assertLessEqual(len(fields["description"]), 1024)
        self.assertLess(len(text.splitlines()), 500)

    def test_solo_review_only_for_docs_only_changes(self):
        text = (ROOT / "skills/cstack/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("A short diff is not an exception.", text)
        self.assertIn("independence: limited (docs-only)", text)

    def test_skill_references_exist(self):
        text = (ROOT / "skills/cstack/SKILL.md").read_text(encoding="utf-8")
        for ref in set(re.findall(r"`(references/[\w-]+\.md)`", text)):
            self.assertTrue((ROOT / "skills/cstack" / ref).is_file(), ref)

    def test_plugin_manifests(self):
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], "cstack")
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])

    def test_gate_workflow_runs_base_branch_gate_only(self):
        wf = (ROOT / "templates/workflows/cstack-gate.yml").read_text(encoding="utf-8")
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", wf)
        self.assertIn("python3 .cstack/gate.py", wf)
        self.assertNotIn("pull_request_target", wf)
        self.assertNotIn("write", wf.split("jobs:")[0])
        self.assertFalse((ROOT / ".github/workflows/cstack-gate.yml").exists(),
                         "the template must not run on cstack's own PRs")


if __name__ == "__main__":
    unittest.main()
