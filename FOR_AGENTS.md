# Setting up cstack: instructions for AI agents

You are an AI coding agent (Claude Code, Codex, Cursor or similar). A user gave you this repository and asked you to set up cstack. Follow these steps in order. Each step says what to run, what to check, and when to stop and ask. Speak to the user in their language.

cstack has three parts:
- **The skill.** Any request to review code or a PR, in any wording, runs cstack's review process.
- **BugBot rules.** They tell Cursor BugBot what to report.
- **The merge gate.** A GitHub check that requires 0, 1 or 2 human approvals depending on risk.

The skill works on its own. The gate only enforces anything after GitHub settings that a repository admin must approve.

## Rules for you

- Do not invent values the user owns. That includes trusted maintainers, which repository to install into, and whether to enforce merges.
- Before you change repository settings (rulesets, branch protection), or push to or merge into a shared branch, show the exact change and get an explicit yes. Asking to "set up cstack" does not cover these.
- Never put tokens or secrets in files or commands.
- Run `scripts/doctor.py` at the end and report what it prints. Do not report a step as done unless the doctor shows `[ok]` for it.

## Step 1. Decide the scope

Pick one. Ask only if the user's request does not already say.

| Scope | When | What it touches |
| --- | --- | --- |
| **Personal** | "for me", "everywhere", no specific repository | `~/.claude/skills`, `~/.agents/skills`, routing lines in `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` |
| **Project** | "this repo", "our team", a repository path or URL | the repository: skill, routing in `CLAUDE.md` and `AGENTS.md`, BugBot files, `REVIEW.md`, PR template, gate |
| **Project without gate** | the user wants review behavior but no merge enforcement | the same as Project, but with `--no-gate` |

If you are inside a git repository and the user said "set this up" without more, ask: "Just for you in every repo, or for this repository and its team?"

## Step 2. Get cstack

Use a stable location so later upgrades are a `git pull`:

```bash
git clone --depth 1 https://github.com/yulmucoffee/cstack.git "$HOME/.cstack/src"
```

If it already exists, update it instead:

```bash
git -C "$HOME/.cstack/src" pull --ff-only
```

Needs Python 3.10 or later. The commands use `$HOME`, which works in bash, zsh and PowerShell. On Windows, use PowerShell or Git Bash, and run `py -3` (or `python`) wherever a step says `python3`, because `python3` there is often only the Microsoft Store stub. The scripts use only the standard library and make no network calls, except that `doctor.py` uses `gh` when it is available.

## Step 3. Install

Always do a dry run first and show the user the list of files.

**Personal:**

```bash
python3 "$HOME/.cstack/src/scripts/install.py" --global --dry-run
python3 "$HOME/.cstack/src/scripts/install.py" --global
```

**Project** (replace the path with the repository root):

```bash
python3 "$HOME/.cstack/src/scripts/install.py" --target /path/to/repo --dry-run
python3 "$HOME/.cstack/src/scripts/install.py" --target /path/to/repo
```

Add `--no-gate` for project-without-gate. Add `--hosts claude`, `--hosts codex` or `--hosts claude,codex,cursor` if the user uses only some tools. The default, `claude,codex`, also covers Cursor.

If the installer reports conflicts, stop. Show the listed files and ask whether to keep their versions or overwrite with `--force`. It never overwrites `policy.json`, `bugbot.yaml`, `REVIEW.md` or an existing PR template.

For the Claude Code plugin route, no files are written. The user runs `/plugin marketplace add yulmucoffee/cstack` and `/plugin install cstack@cstack`. A plugin cannot edit `CLAUDE.md`, so append the text of `templates/routing.md` to `~/.claude/CLAUDE.md` with the user's OK.

**Personal scope is done here.** Go to step 7.

## Step 4. Configure the gate (project scope only)

1. **Trusted authors.** Ask the user for the GitHub logins of trusted human maintainers. You may show candidates from `gh api repos/OWNER/REPO/collaborators --jq '.[].login'`, but the user picks. Write them to `.cstack/policy.json` under `trusted_authors`. Leaving it empty is allowed. It means every PR needs two approvals.
2. **High-risk paths.** Show the defaults in `docs/design.md` (CI, auth, billing, migrations, lockfiles and more). Ask whether the repository has other sensitive directories, and add them to `additional_high_risk_patterns`.
3. **AI reviewer.** The default requires the `Cursor Bugbot` check. If the user does not use BugBot, ask which automated reviewer check to require, and set `required_check_names` and `required_check_apps` to match. Or remove both, and accept that zero-human merges become impossible.
4. **REVIEW.md.** Offer to fill in the "What failure looks like here" and "Skip" sections from what you learn about the repository. Keep it short.

## Step 5. Land the install

1. Commit the changes on a new branch and open a PR. The PR's `cstack-risk-gate` check **will fail**. That is expected, because the base branch does not have `.cstack/gate.py` yet. Tell the user this before they see it.
2. A maintainer merges this one PR with their normal review. Do not merge it yourself unless the user explicitly asks.

## Step 6. Turn on enforcement (project scope with gate, admin only)

These steps need the user or an admin. Present them as a checklist, and do each one only after an explicit yes.

1. **BugBot.** The user enables it for the repository in the Cursor dashboard. You cannot do this.
2. **Ruleset.** `templates/ruleset.json` requires `cstack-risk-gate` and `Cursor Bugbot` from their real GitHub Apps. It also blocks force-pushes and deletion, dismisses stale approvals and requires conversation resolution. First add the repository's own CI check names to `required_status_checks`. With the user's yes and admin rights:

   ```bash
   gh api -X POST repos/OWNER/REPO/rulesets --input "$HOME/.cstack/src/templates/ruleset.json"
   ```

   Show the user the API response. If it fails, report the error and give the manual path: Settings > Rules > Rulesets.
3. **CODEOWNERS.** Suggest a `CODEOWNERS` entry for `.github/workflows/`, `.cstack/`, `.cursor/` and `CODEOWNERS` with human owners, and turn on code-owner review. This stops a PR from editing the gate unnoticed.

## Step 7. Verify and report

```bash
python3 "$HOME/.cstack/src/scripts/doctor.py" --target /path/to/repo
python3 "$HOME/.cstack/src/scripts/doctor.py" --global
```

It exits 1 while any `[todo]` remains. Report to the user:
- what was installed, and where;
- each remaining `[todo]` and `[warn]`, with who must do it (you, the user or an admin);
- how to use it: "Just ask me to review a PR or your changes, in any words."

Then tell the user to start a new agent session, so the skill and routing load.

## Upgrading later

```bash
git -C "$HOME/.cstack/src" pull --ff-only
python3 "$HOME/.cstack/src/scripts/install.py" --target /path/to/repo
```

Unmodified files upgrade automatically. Edited ones are reported as conflicts. Compare `$HOME/.cstack/src/templates/policy.json` with the repository's copy for new keys.
