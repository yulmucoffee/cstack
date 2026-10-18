# Reviewer evals

A reviewer prompt, `REVIEW.md` rule or model change is a hypothesis. Score it against bugs that actually shipped before you keep it.

## Build the set from incidents

1. Collect PRs that were reverted or needed a fix-forward.
2. Have someone who knows that code confirm the bug and where it lived.
3. Store one case per bug. A JSON Lines file such as `evals/reviewer/cases.jsonl` works:

```json
{"id": "rev-0142", "base": "<sha>", "head": "<sha>", "bug_file": "src/cache.ts", "bug_lines": [88, 97], "summary": "eviction drops live entries under concurrent refresh", "source": "<revert PR URL>"}
```

4. Add known-clean PRs too. They measure false alarms.

## Score

For each case, run the reviewer on `base...head` with the production prompt and record its findings.

- **Recall.** The share of bug cases where a finding points at the bug's file and lines with the right failure.
- **Harmful false positives.** On clean PRs, findings that would lead someone to make a harmful change.
- **Rounds to pass.** On recent real PRs, how many review and fix cycles it took. Watch the share needing five or more.

Rerun the whole set whenever the reviewer's prompt, tools, model or `REVIEW.md` changes. Keep a change only if recall holds or improves without a jump in harmful false positives. Real bugs first, fewer rounds second.

## Measure noise in production

Sort every posted comment by what the person on the PR did with it: fixed it, said it was wrong, said the behavior was intended, or decided it did not matter. A rising "wrong" or "did not matter" share is noise. Move the fix into `REVIEW.md`, a lint rule, or the triage patterns.

## Guardrail

Track human approvals per PR, human comments and time waiting on a person. Revert and incident rates are the guardrail. If they rise, the review did not save human time. It moved it.
