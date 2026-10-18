#!/usr/bin/env python3
"""Install cstack into a repository for Claude Code, Codex, Cursor and BugBot.

Also adds a short routing block to CLAUDE.md and AGENTS.md so that any request
to review code or a PR goes through the cstack skill, not a competing one.

No network access or third-party dependencies. Safe by default:
- cstack-managed files are tracked by hash in .cstack/manifest.json, so an
  unmodified older copy upgrades cleanly and a locally edited copy is a conflict;
- seed files you are meant to own (policy, BugBot config, REVIEW.md, PR template) are created
  once and never overwritten, not even with --force.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "cstack"
MARKER_START = "<!-- cstack:begin -->"
MARKER_END = "<!-- cstack:end -->"
MANIFEST = ".cstack/manifest.json"
# Claude Code reads .claude/skills. Codex reads .agents/skills. Cursor reads both,
# plus .cursor/skills, so it never needs a third copy.
HOST_DIRS = {
    "claude": ".claude/skills/cstack",
    "codex": ".agents/skills/cstack",
    "cursor": ".cursor/skills/cstack",
}
GATE_FILES = {
    ".cstack/gate.py": ROOT / "scripts/gate.py",
    ".github/workflows/cstack-gate.yml": ROOT / "templates/workflows/cstack-gate.yml",
}
SEED_FILES = {
    ".cstack/policy.json": ROOT / "templates/policy.json",
    ".cursor/config/bugbot.yaml": ROOT / ".cursor/config/bugbot.yaml",
    "REVIEW.md": ROOT / "templates/REVIEW.md",
    ".github/pull_request_template.md": ROOT / ".github/PULL_REQUEST_TEMPLATE.md",
}
PR_TEMPLATE_LOCATIONS = [
    "pull_request_template.md", "PULL_REQUEST_TEMPLATE.md", "docs/pull_request_template.md",
    "docs/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md",
    ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE",
]


def content(path: Path) -> bytes:
    """File bytes with CRLF folded to LF, so a Windows checkout (core.autocrlf) of an
    unmodified file still counts as unmodified."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(content(path)).hexdigest()


def unmodified(path: Path, recorded_digest: str | None) -> bool:
    """True if the file still matches what cstack wrote. Manifests from before CRLF
    folding hold raw-byte hashes, so accept those too."""
    return recorded_digest in (sha256(path), hashlib.sha256(path.read_bytes()).hexdigest())


def utf8_output():
    """Write UTF-8 even when stdout is a pipe on Windows (cp949, cp1252). A non-ASCII
    path can no longer crash a finished install, and agents and test harnesses read
    UTF-8. A PowerShell capture decodes with the console code page instead."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def managed_plan(hosts: list[str], skill_only: bool, gate: bool) -> dict[str, Path]:
    plan: dict[str, Path] = {}
    for host in hosts:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and f.name != ".DS_Store" and "__pycache__" not in f.parts:
                plan[f"{HOST_DIRS[host]}/{f.relative_to(SKILL).as_posix()}"] = f
    if not skill_only and gate:
        plan.update(GATE_FILES)
    return plan


def line_ending(text: str) -> str:
    crlf = text.count("\r\n")
    return "\r\n" if crlf > text.count("\n") - crlf else "\n"


def merged_block(previous: str, body: str, path: Path) -> str:
    """Insert or replace the one marked cstack block.

    Text before and after an existing block is kept byte-for-byte. An appended block
    goes after the file's content with trailing blank lines trimmed. The block is
    written in the dominant line ending of the text outside it."""
    starts, ends = previous.count(MARKER_START), previous.count(MARKER_END)
    if starts != ends or starts > 1 or (starts and previous.index(MARKER_END) < previous.index(MARKER_START)):
        raise ValueError(f"{path} has malformed cstack markers; fix or remove the cstack block and rerun")
    if starts:
        before, tail = previous.split(MARKER_START, 1)
        _, after = tail.split(MARKER_END, 1)
    else:
        before, after = previous, ""
    eol = line_ending(before + after)
    block = eol.join([MARKER_START, *body.rstrip().split("\n"), MARKER_END])
    if starts:
        return before + block + after
    return previous.rstrip() + (eol * 2 if previous.strip() else "") + block + eol


def read_untranslated(path: Path) -> str:
    """Read without newline translation, so a merged file keeps its own line endings."""
    with path.open(encoding="utf-8", newline="") as f:
        return f.read()


def imports_agents_md(claude_md: Path) -> bool:
    if not claude_md.is_file():
        return False
    return any(line.strip() == "@AGENTS.md" for line in claude_md.read_text(encoding="utf-8").splitlines())


def block_files(target: Path, hosts: list[str], skill_only: bool, routing: bool) -> dict[Path, str]:
    """Files that get a marked cstack block, mapped to the block body."""
    blocks: dict[Path, str] = {}
    if not skill_only:
        blocks[target / ".cursor/BUGBOT.md"] = (ROOT / ".cursor/BUGBOT.md").read_text(encoding="utf-8")
    if not routing:
        return blocks
    body = (ROOT / "templates/routing.md").read_text(encoding="utf-8")
    wanted: list[Path] = []
    if skill_only:
        # Personal install: only touch the instruction files of tools that are present.
        if "claude" in hosts and (target / ".claude").is_dir():
            wanted.append(target / ".claude/CLAUDE.md")
        codex_home = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else target / ".codex"
        if "codex" in hosts and codex_home.is_dir():
            override = codex_home / "AGENTS.override.md"
            wanted.append(override if override.is_file() else codex_home / "AGENTS.md")
    else:
        agents = target / "AGENTS.md"
        if {"codex", "cursor"} & set(hosts):
            wanted.append(agents)
        claude = target / "CLAUDE.md"
        if "claude" in hosts and not (agents in wanted and imports_agents_md(claude)):
            wanted.append(claude)
    seen: set[Path] = set()
    for path in wanted:
        real = path.resolve()
        if real not in seen:
            seen.add(real)
            blocks[path] = body
    return blocks


def install(target: Path, *, hosts: list[str], force: bool = False, dry_run: bool = False,
            gate: bool = True, skill_only: bool = False, routing: bool = True) -> list[str]:
    if not target.is_dir():
        raise ValueError(f"Target directory does not exist: {target}")
    unknown = [h for h in hosts if h not in HOST_DIRS]
    if unknown or not hosts:
        raise ValueError(f"--hosts must name some of {', '.join(HOST_DIRS)}; got {hosts}")
    manifest_path = target / MANIFEST
    try:
        recorded: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))["files"] if manifest_path.exists() else {}
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"Unreadable {manifest_path}: {e}") from e

    plan = managed_plan(hosts, skill_only, gate)
    every_known = managed_plan(list(HOST_DIRS), False, True)
    log: list[str] = []
    conflicts: list[str] = []
    writes: list[tuple[Path, Path]] = []
    for rel, src in plan.items():
        dst = target / rel
        if not dst.exists():
            writes.append((src, dst))
        elif content(dst) == content(src):
            continue
        elif force or unmodified(dst, recorded.get(rel)):
            writes.append((src, dst))
        else:
            conflicts.append(rel)
    block_updates: list[tuple[Path, str]] = []
    for path, body in block_files(target, hosts, skill_only, routing).items():
        previous = read_untranslated(path) if path.exists() else ""
        updated = merged_block(previous, body, path)
        if updated != previous:
            block_updates.append((path, updated))
    if conflicts:
        raise ValueError("These files differ from the cstack copy (edited locally, or installed before "
                         ".cstack/manifest.json existed). Review them, then rerun with --force:\n"
                         + "\n".join(f"  {target / rel}" for rel in conflicts))

    removals = [rel for rel, digest in recorded.items()
                if rel not in every_known and rel not in SEED_FILES
                and (target / rel).is_file() and unmodified(target / rel, digest)]
    seeds = [] if skill_only else [(rel, src) for rel, src in SEED_FILES.items()
                                   if gate or rel != ".cstack/policy.json"]

    for src, dst in writes:
        log.append(f"WRITE  {dst}")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    for rel in removals:
        log.append(f"REMOVE {target / rel} (obsolete, unmodified)")
        if not dry_run:
            (target / rel).unlink()
    for rel, src in seeds:
        dst = target / rel
        if rel.endswith("pull_request_template.md") and any((target / p).exists() for p in PR_TEMPLATE_LOCATIONS):
            continue
        if dst.exists():
            continue
        log.append(f"SEED   {dst}")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    for path, updated in block_updates:
        log.append(f"MERGE  {path}")
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(updated, encoding="utf-8", newline="")

    files = {rel: d for rel, d in recorded.items() if rel not in removals and (target / rel).exists()}
    files.update({rel: sha256(src) for rel, src in plan.items()})
    if not dry_run and (log or files != recorded):
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({"files": dict(sorted(files.items()))}, indent=2) + "\n", encoding="utf-8")
    return log


def main() -> int:
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--target", type=Path, help="Project repository to install into (default: current directory)")
    where.add_argument("--global", dest="global_", action="store_true",
                       help="Install only the skill into your home directory (~/.claude/skills, ~/.agents/skills)")
    parser.add_argument("--hosts", default="claude,codex",
                        help="Comma-separated skill hosts: claude, codex, cursor (default: claude,codex; Cursor reads both)")
    parser.add_argument("--no-gate", action="store_true", help="Skip the GitHub Actions gate and policy")
    parser.add_argument("--no-routing", action="store_true",
                        help="Do not add the review-routing block to CLAUDE.md / AGENTS.md")
    parser.add_argument("--force", action="store_true", help="Overwrite locally modified cstack-managed files")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()
    target = Path.home() if args.global_ else (args.target or Path.cwd())
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    try:
        changes = install(target.resolve(), hosts=hosts, force=args.force, dry_run=args.dry_run,
                          gate=not args.no_gate, skill_only=args.global_, routing=not args.no_routing)
    except (OSError, ValueError) as e:
        print("cstack install failed:", e, file=sys.stderr)
        return 1
    for change in changes:
        print(change)
    print(f"cstack {'dry-run complete' if args.dry_run else 'installed'}: {len(changes)} changes")
    if not args.global_ and not args.no_gate:
        print("NEXT: set trusted_authors in .cstack/policy.json, enable BugBot, and require "
              "cstack-risk-gate plus your CI in a GitHub ruleset. Run scripts/doctor.py, and see README 'Turn on enforcement'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
