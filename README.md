# cstack

[![ci](https://github.com/yulmucoffee/cstack/actions/workflows/ci.yml/badge.svg)](https://github.com/yulmucoffee/cstack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**English** · [한국어](README.ko.md)

**Evidence before merge.** cstack is one agent skill for **Claude Code, Codex and Cursor**, a rules file for **Cursor BugBot**, and a small **GitHub merge gate**. Together they bring the Claude Code team's layered code-review process and poteto's [pstack](https://github.com/cursor/plugins/tree/main/pstack) engineering discipline into your own repositories.

The goal is not more code or more review comments. It is the smallest correct change, proven on the real surface, reviewed from a fresh context, with human attention spent only where the risk is.

## Why

Agents write PRs faster than people can read them. The Claude Code team [describes](https://claude.dev/blog/solving-code-review-at-anthropic/) how they handled this. Merged PRs more than doubled while the share that had to be reverted fell by more than 40 percent. They did not drop review. They moved most of the reading to machines, layered the checks, scaled human approval to risk, and made sure review converges instead of looping.

pstack covers the other half: how an agent should work so that its output deserves trust. Sharpen the task, name the data shape, fix root causes, prove the one fact a change is safe because of, and use adversarial review across models.

cstack packages both as files you can install and read, with no service to run.

## What you get

| Layer | Files | Who reads it | Enforces? |
| --- | --- | --- | --- |
| Skill | `skills/cstack/SKILL.md` + `references/` | Claude Code, Codex, Cursor agents | No. It shapes how the agent works. |
| BugBot rules | `.cursor/BUGBOT.md`, `.cursor/config/bugbot.yaml` | Cursor BugBot on every PR | No. It shapes what BugBot reports. |
| Review rules | `REVIEW.md` (starter) | Any AI reviewer, and your team | No. Owners tune it. |
| Merge gate | `.cstack/gate.py`, `.cstack/policy.json`, `.github/workflows/cstack-gate.yml` | GitHub Actions | **Yes**, once a ruleset requires `cstack-risk-gate`. |

How a change moves through the layers:

```
author verifies → fresh-context review → security review → required CI
→ risk-tiered human approval (cstack-risk-gate) → merge queue → flag / staged release → rollback
```

Each layer catches some problems and misses others. Few problems get through all of them, and rollback handles the rest.

## Install

You need Python 3.10 or later and nothing else. The installer makes no network calls.

### Personal: the skill only

Use cstack in every repository you open, without touching the repository.

```bash
git clone https://github.com/yulmucoffee/cstack.git
```

```bash
python3 cstack/scripts/install.py --global
```

This writes `~/.claude/skills/cstack/` (Claude Code) and `~/.agents/skills/cstack/` (Codex), plus `~/.cstack/manifest.json` to track upgrades. Cursor reads both skill folders. Run it again after `git pull` to upgrade.

**Claude Code plugin.** Alternatively, install it as a plugin inside Claude Code:

```text
/plugin marketplace add yulmucoffee/cstack
/plugin install cstack@cstack
```

On Claude Code 2.1.275 or later, `/plugin install cstack --marketplace yulmucoffee/cstack` does both in one step. Plugin skills are namespaced, so you invoke it as `/cstack:cstack`.

### Project: skill, BugBot and gate

Run from the cstack checkout and point it at your repository. Look at the dry run first.

```bash
python3 scripts/install.py --target /path/to/your-repo --dry-run
```

```bash
python3 scripts/install.py --target /path/to/your-repo
```

| Path in your repo | Kind | On reinstall |
| --- | --- | --- |
| `.claude/skills/cstack/`, `.agents/skills/cstack/` | managed | upgraded if you have not edited it |
| `.cursor/BUGBOT.md` | marked block | only the `<!-- cstack:begin -->` block is replaced |
| `.cstack/gate.py`, `.github/workflows/cstack-gate.yml` | managed | upgraded if you have not edited it |
| `.cstack/policy.json`, `.cursor/config/bugbot.yaml`, `REVIEW.md`, `.github/pull_request_template.md` | seed | created once, never overwritten |
| `.cstack/manifest.json` | bookkeeping | hashes of managed files |

Options: `--no-gate` skips the gate workflow, `gate.py` and `policy.json`, and still installs the skill, BugBot files, `REVIEW.md` and the PR template. `--hosts claude`, `--hosts codex` or `--hosts claude,codex,cursor` picks skill locations. `--force` overwrites managed files you edited locally. Seed files are never overwritten, even with `--force`. An existing PR template anywhere GitHub looks for one is left alone.

Commit the result. Restart the agent or open a new session so it picks up the skill. To upgrade later, `git pull` in the cstack checkout and run the same command. Seed files stay yours, so compare `configs/policy.json` with your copy for new keys. The gate prints a warning when a required check is not bound to an App.

### Before first production use

The gate does nothing until GitHub requires it. Do these in order.

1. **Set trusted authors.** Put the GitHub logins of trusted human maintainers in `.cstack/policy.json` under `trusted_authors`. With the empty default, every PR needs two human approvals. Review the sensitive path list and add your own with `additional_high_risk_patterns`.
2. **Enable BugBot** for the repository in the Cursor dashboard. The YAML file configures BugBot. It does not turn it on. Without BugBot, the required `Cursor Bugbot` check never appears and the gate stays blocked, on purpose. If you use a different AI reviewer, change `required_check_names` and `required_check_apps`.
3. **Require the checks.** In a GitHub ruleset for the default branch, require `cstack-risk-gate`, your build and tests, your security scans and `Cursor Bugbot`. Bind each check to the GitHub App that publishes it. Turn on required review, dismiss stale approvals, require conversation resolution and restrict who can bypass.
4. **Protect the gate itself.** On `pull_request`, GitHub runs the workflow file from the PR, so a PR could edit `cstack-gate.yml`. If your plan offers it, use the ruleset rule *Require workflows to pass before merging* with the default-branch copy. Otherwise add CODEOWNERS for `.github/workflows/`, `.cstack/`, `.cursor/` and `CODEOWNERS`, and require code-owner review. The gate already treats those paths as high risk.
5. **Dry-run on a throwaway PR.** Try a docs change, a code change and a workflow change before anyone relies on zero-human merges.

cstack never merges on its own. A passing gate means "allowed", not "go".

## Use it

| Host | Invoke |
| --- | --- |
| Claude Code | `/cstack` (project or personal install) or `/cstack:cstack` (plugin). Claude may also load it when the task matches. |
| Codex | `$cstack`, or pick it from `/skills`. Codex may also load it when the task matches. |
| Cursor | Type `/cstack` in Agent chat, or let the agent pick it up. |
| BugBot | Nothing to do. It reads `.cursor/BUGBOT.md` on every PR. |

The skill picks a mode from your request and says which one it chose.

| Mode | Ask for | Writes code | Stops at |
| --- | --- | --- | --- |
| `build` | a feature or change | yes | PR open with proof |
| `fix` | a bug fixed | yes | failing then passing proof, PR open |
| `review` | a review, "are we sure" | no | a verdict with findings |
| `investigate` | how or why something works | no | a cited answer |
| `babysit` | "get PR 42 green", "address the BugBot comments", "check on PR 42" | fixes on the PR branch | `MERGE-READY` or `BLOCKED` |
| `ship` | "ship", "merge" or "land" in so many words | merges | the top of the verified run |

### Example prompts

```text
/cstack review this branch against its PR description. prove the riskiest assumption with a script that runs the real code. don't edit anything.
```

```text
/cstack the export button double-submits on slow networks. repro first on the real page, then fix and show me the before and after.
```

```text
/cstack babysit PR 42 to merge-ready. triage the BugBot threads and tell me what's blocking. don't merge.
```

```text
/cstack ship PRs 41 to 43 bottom-up. stop at the first one without an independent verdict.
```

```text
$cstack inspect my current branch, check the failure paths, and give me a merge-readiness verdict. do not merge.
```

### Writing a good prompt

This follows pstack's prompting advice. State the goal and how you will know it is done. Let the skill supply the steps.

- **Put in:** the goal, a done check that can pass or fail, the proof you want to see (command output, a screenshot, a before and after number), what you already know (a repro step, a log), and real constraints ("repro first", "no behavior change", "don't merge").
- **Leave out:** how to do it, a list of steps, and your theory of the cause. A stated guess narrows the search.
- **Steer in one line:** "I asked for a repro, not a fix yet." "Show me the real output, not the build log."

### What a report looks like

```text
MODE: review | VERDICT: PASS+NOTES | REF: 9f2c1e4
FINDINGS: 1 actionable
  [ACT ON][high] src/cache/evict.ts:L88 trigger: refresh during eviction -> live entry dropped -> repro: scripts/evict-race.ts (fails on 9f2c1e4)
PROOF: npm test -- cache -> 42 passed; node scripts/evict-race.ts -> FAIL as expected
SAFETY FACT: eviction only removes entries past TTL: UNPROVEN (race above breaks it)
RISK: tier medium, approvals 0/1, Cursor Bugbot success
INDEPENDENCE: Claude Opus subagent + Sonnet subagent (different models)
NEXT: guard eviction with the entry's generation counter and rerun the race script
```

## Risk tiers

The gate computes a floor from the changed paths and the author. Humans and reviewers can always raise it.

| Change | Trusted author | Anyone else |
| --- | ---: | ---: |
| Docs only (`.md`, `.mdx`, `.rst`, `.adoc`, images under `docs/`) | 0 | 2 |
| Code, config, dependency manifests, agent or reviewer instructions (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`, skills) | 1 | 2 |
| CI workflows and other CI configs, CODEOWNERS, `.cstack/`, BugBot config, agent hooks and MCP config, auth, security, billing, payments, migrations, secrets, Terraform, lockfiles | 2 | 2 |

On every tier the gate also requires that approvals are on the current head commit and from human repository owners, members or collaborators other than the author (drive-by approvals never count), that no change request is standing and no review thread is unresolved, and that every required check concludes `success` (not `neutral`) from its expected App. A zero-human merge is allowed only when at least one automated review check is required. API errors, drafts and malformed policy block the merge.

This is stricter than the blog's tiers on purpose. You can loosen it with evidence. See [design and trust boundaries](docs/design.md) for every rule and its limits.

### `policy.json`

| Key | Default | Meaning |
| --- | --- | --- |
| `trusted_authors` | `[]` | GitHub logins that get the lighter tiers. Case-insensitive. |
| `additional_high_risk_patterns` | `infra/**`, `**/deploy/**`, `**/production/**` | Extra paths that always need two humans. |
| `required_check_names` | `["Cursor Bugbot"]` | Checks that must conclude `success` on the head. |
| `required_check_apps` | `{"Cursor Bugbot": "cursor"}` | Only count a check if this GitHub App published it. |
| `approver_associations` | `OWNER`, `MEMBER`, `COLLABORATOR` | Whose approvals count. Narrow it if not every org member should approve. |
| `require_resolved_review_threads` | `true` | Block on unresolved review threads. |
| `check_wait_seconds` | `600` | How long to wait for required checks that are still running. Keep it below the workflow's `timeout-minutes`. |

## What the skill does differently

- **Proof, not claims.** Every claim carries its evidence or says `measured`, `inferred` or `guess`. It never reports a test it did not run.
- **Fresh, independent review.** At least two read-only reviewers in parallel, ideally on different models, with only the intent, diff and rubric. It names the independence it actually had.
- **Verify before posting.** Each finding is checked in a separate pass. Style-only findings are dropped. Pre-existing bugs are labeled so they do not read as the author's fault.
- **One safety fact.** It finds the single fact the change is safe because of and pushes it down an evidence ladder, from "asserted" to "reproduced in the running app". If it cannot prove it, it says `UNPROVEN`.
- **Convergence.** Three rounds on one problem, then rethink. Diff-only re-review after the first pass. Flag the bug class. Never repeat a finding.
- **Skeptical BugBot triage.** Each thread is `fix`, `dismiss` with a disproof, or `ask`. Security, data and migration findings are never auto-dismissed.
- **Babysit is not ship.** Babysitting stops at merge-ready. Shipping needs an explicit request, an independent verdict per PR, and lands only the contiguous verified run from the bottom of the stack.
- **Lessons become structure.** A repeated finding becomes a lint rule, test or `REVIEW.md` line. An incident becomes an eval case.

## Repository layout

```text
skills/cstack/SKILL.md                     the workflow, for every agent host
skills/cstack/agents/openai.yaml           Codex display metadata
skills/cstack/references/                  review rubric, merge playbook, BugBot triage, principles, evals
.claude-plugin/                            Claude Code plugin and marketplace manifests
.cursor/BUGBOT.md                          BugBot review rules (also used by this repo)
.cursor/config/bugbot.yaml                 BugBot repository config
templates/workflows/cstack-gate.yml        gate workflow, installed into your repo
templates/REVIEW.md                        starter REVIEW.md
.github/PULL_REQUEST_TEMPLATE.md           PR template: Why, Scope, Testing, Risk, How to revert
configs/policy.json                        default gate policy
scripts/gate.py                            the gate (stdlib only)
scripts/install.py                         the installer (stdlib only)
tests/                                     gate and installer tests
docs/design.md                             trust boundaries and known limits
```

## Development

```bash
python3 -m unittest discover -s tests -v
```

To try the gate against a real PR without writing anything:

```bash
GH_TOKEN="$(gh auth token)" GITHUB_REPOSITORY=owner/repo PR_NUMBER=123 CSTACK_CONFIG=configs/policy.json python3 scripts/gate.py
```

Issues and PRs are welcome. Changes to the skill should come with a reason it changes agent behavior, ideally a before and after on a real task.

## Credits

- Addy Osmani, Morgan Westlee Lunt and Qing Wang, [How the Claude Code team does code review](https://claude.dev/blog/solving-code-review-at-anthropic/) (October 15, 2026).
- Lauren Tan ([poteto](https://github.com/poteto)), [pstack](https://github.com/cursor/plugins/tree/main/pstack), MIT. Principles, review rubric, BugBot triage and shipping discipline are adapted from it. See [NOTICE.md](NOTICE.md).

cstack is independent and not affiliated with or endorsed by Anthropic, Cursor or OpenAI.

## License

[MIT](LICENSE)
