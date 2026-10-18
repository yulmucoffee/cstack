# REVIEW.md

Read by AI reviewers (Claude Code review, Codex `/review`, BugBot via `.cursor/BUGBOT.md`, the cstack skill). Code owners keep it short. Every line should change what a reviewer does.

## What failure looks like here

<!-- One line per area. Examples: -->
- Docs: the doc lies about current behavior.
- Config: a value misroutes traffic or silently falls back to a default.
- API: a response shape changes without a version bump.
- Data: a write is not idempotent under retry.

## Always check

<!-- Repo-specific invariants a newcomer would miss. -->
- 

## Skip

<!-- Generated, vendored or snapshot paths reviewers should ignore. -->
- 

## Rules for findings

- Cite `file:line` as evidence. Do not infer behavior from a name.
- At most three nits per review. Correctness and security first.
- Mark bugs that existed before the PR as pre-existing.
- Start the summary with the count of actionable findings, and say plainly when there is nothing to fix.

## Recurring dismissals

<!-- Patterns reviewers keep flagging that are safe here. Use the format in
     the cstack bugbot-triage reference: skip when / do not skip when / signal / source. -->
