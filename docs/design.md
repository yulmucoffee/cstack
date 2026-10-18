# Design and trust boundaries

## Three layers

1. **The skill** (`skills/cstack/`). One `SKILL.md` with references, read by Claude Code, Codex and Cursor. It shapes how an agent builds, reviews, babysits and ships. It enforces nothing.
2. **BugBot rules** (`.cursor/BUGBOT.md`, `.cursor/config/bugbot.yaml`). BugBot does not run skills. It reads these files when it reviews a PR. The YAML is read from the PR's base branch, so a PR cannot change its own review settings.
3. **The gate** (`.cstack/gate.py`, `.cstack/policy.json`, `.github/workflows/cstack-gate.yml`). A deterministic required check. It is the only layer that can block a merge, and only once a ruleset requires it.

A prompt is guidance. Branch rules and required checks are enforcement. cstack never treats the first as the second.

## What the gate decides

| Input | Rule |
| --- | --- |
| Changed paths (old and new names) | Sensitive path → high. Docs only (`.md`, `.mdx`, `.rst`, `.adoc`, images under `docs/`) → low. Agent or reviewer instructions (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`, `SKILL.md`, `.claude/`, `.agents/`, `.cursor/`, `.windsurf/`, `.clinerules`, `.github/` and similar) → never low. Everything else → medium. No paths → high. |
| PR author | Not in `trusted_authors` (case-insensitive) → at least two approvals. |
| Reviews | Only `User` accounts other than the author whose `author_association` is in `approver_associations` (default `OWNER`, `MEMBER`, `COLLABORATOR`). Drive-by and sock-puppet approvals never count. Latest review per person wins. Approvals count only on the current head SHA. Any standing change request blocks. |
| Review threads | Any unresolved thread blocks, when `require_resolved_review_threads` is on. |
| Required checks | Each named check must conclude `success` on the head. `neutral`, `skipped`, missing or still running all block. With `required_check_apps`, only runs published by that GitHub App count, and the gate warns about any required check left unbound. The newest run (highest id) decides, so a queued rerun is not hidden behind an older success. |
| Zero-human path | Allowed only if at least one required check is named. |
| Draft PRs, API errors, malformed policy | Block. The gate fails closed. |

The gate waits up to `check_wait_seconds` for required checks that are still running, but only when they are the last thing missing. Otherwise it reports immediately and spends no runner minutes. After a wait it re-reads reviews and threads, since they may have changed.

High-risk defaults: GitHub workflows, composite actions and workflow scripts, other CI configs (GitLab, CircleCI, Jenkins, Buildkite, Azure Pipelines), CODEOWNERS, dependency bots, `.cstack/`, BugBot rules and config, Cursor hooks, Claude Code settings and hooks, `.mcp.json`, `.codex/`, `auth`, `security`, `billing`, `payments`, `migrations` and `secrets` directories, Terraform, Prisma schema, and dependency lockfiles. Add your own with `additional_high_risk_patterns`. Patterns use `fnmatch`, where `*` also crosses `/`, and a leading `**/` also matches at the root.

## Trust rules

- The gate is Python standard library only and runs with read-only token permissions.
- The workflow checks out the PR's **base SHA**. It never checks out or runs PR code.
- On `pull_request` events, GitHub runs the workflow file from the PR itself, so a PR can edit the gate's workflow. Close this hole in one of two ways. Preferred, where your GitHub plan offers it: a ruleset rule **Require workflows to pass before merging**, pointing at `cstack-gate.yml` on the default branch, so the PR's copy is never the one that runs. Minimum: CODEOWNERS on `.github/workflows/`, `.cstack/` and `.cursor/` with required code-owner review. The gate already classifies those paths as high risk.
- A check of a given name can be published by any workflow. Bind important checks to their source App, in the ruleset and in `required_check_apps`.
- PR bodies, comments and bot output are data, never commands.
- Approvals are stricter than GitHub's sticky default. Turn on "dismiss stale approvals" too.
- `MEMBER` means organization member. Where not every member is a trusted reviewer, set `approver_associations` to `["OWNER", "COLLABORATOR"]` and rely on code-owner review in the ruleset.
- `trusted_authors` starts empty, so every PR needs two humans until an owner opts in. That is deliberate.
- The path tier is a floor. A human or a reviewer can always escalate.

## Known limits

- Path rules cannot tell whether a change behind a flag is safe. All code is at least medium.
- GitHub does not start a workflow when a review thread is resolved. After resolving threads, re-run the `cstack-risk-gate` job or push.
- If BugBot finishes after `check_wait_seconds`, the gate stays red until the next event or a re-run.
- BugBot reports `success` only when it has no unresolved comments. Resolve or fix them, then let it re-run.
- The gate does not run CI, security scans, end-to-end verification or deploys, and does not merge. Require those separately.
- An agent's independence from the author is a process claim. The gate cannot check it.

## Not reproduced

This adapts ideas from Anthropic's published review process. It is not Anthropic's internal infrastructure or the Code Review product. It has no risk classifier model, no merge queue, no staged release and no autonomous merge job.
