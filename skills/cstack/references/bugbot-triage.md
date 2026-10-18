# BugBot and review-bot triage

Bots catch real bugs and also file non-issues. The goal is to stop treating every comment as a required code change, not to ignore the bot. This page is for bots and automated reviewers. For a human reviewer's thread, or a bot thread a human has replied in, reply with the fix commit or your reasoning, and leave resolving it to them. If a human's request is unclear or conflicts with what the user decided, stop and ask the user before changing anything.

## Decide per thread

- `fix`: you reproduced or traced the issue, and the fix is local and keeps the PR's intended behavior. This includes security, privacy, auth, billing and data issues when both hold; say so in the reply so the owner sees it. Fix it in the lowest PR that owns the code, reply with the commit SHA, resolve the thread.
- `dismiss`: the current code disproves it, or it matches a pattern below at `recurring` or `strong` confidence. Never dismiss anything on the ask-by-default list. Reply with the concrete disproof and resolve.
- `ask`: unconfirmed and high severity or on the list below, or the fix would change intended behavior. Ask the owner instead of guessing. A confirmed issue with a local fix that keeps intent is `fix`, whatever its severity.

When unsure, ask. Skipping a noisy style comment is cheap. Skipping a real data or security bug is not.

## Always verify cheaply first

- If the claim can be checked with one command (a contract test, a type check, a grep on the tip), run it before classifying. A red run confirms the claim. A green run is the disproof for the reply.
- A finding about a missing check may be stale. Confirm against the current head, not the commit the bot reviewed.
- Findings against hand-rolled replacements of native platform behavior (scrolling, sticky positioning, focus, event forwarding) are usually real. Default to verifying and fixing them.

## Ask by default

Never dismiss these, even if a similar comment was dismissed before. Fix them under `fix`, or ask:

- Security, privacy, auth, billing, data retention and permission boundaries.
- Anything the bot marks high severity.
- Migrations, schemas, idempotency, concurrency and cross-system behavior.

## Pass count

From the third bot pass on the same PR, close a repeat of an already-disproven finding by linking the earlier disproof. Triage anything new normally. The third round on the same root cause means the approach needs rethinking, not another patch (SKILL.md section 6).

## Pattern format

Record a recurring dismissal here, or in the repo's `REVIEW.md`, in this shape:

```markdown
### <short pattern name>

- Confidence: candidate | recurring | strong
- Skip when: <conditions that must all be true>
- Do not skip when: <risk boundaries>
- Example signal: <phrases or code shape that identify it>
- Source: <PR or comment URL>
```

`candidate` after one or two examples. `recurring` after several verified dismissals. `strong` only for narrow, repeatedly verified, low-risk patterns.

## Starter patterns

These start at `candidate` confidence. Use them to look closer, not to dismiss. Promote one only after several verified dismissals in your repository.

### Unused export used later in the stack

- Confidence: candidate
- Skip when: the symbol is used by a later PR in the same stack and you verified that diff.
- Do not skip when: the PR is not part of a stack, the symbol is public API, or the later use cannot be verified.
- Example signal: "Exported function is never used."

### Intentional visual change

- Confidence: candidate
- Skip when: the change is visibly intentional in screenshots or a linked design, not only because the PR description says so, and the comment only restates it.
- Do not skip when: the comment touches accessibility, focus, keyboard navigation, contrast or a component API contract.
- Example signal: comments about spacing, sizes or shared visual defaults.

### Invariant already enforced elsewhere

- Confidence: candidate
- Skip when: a shared component, framework contract, type or single source of truth visibly guarantees the concern.
- Do not skip when: the invariant is assumed rather than enforced, depends on timing, or crosses async or state boundaries.
- Example signal: "value may be null" where the type and the only producer rule it out.

### Narrow error condition on purpose

- Confidence: candidate
- Skip when: the bot asks to widen a specific error check (an errno, status class or error code) into a catch-all, and the narrow check encodes a real distinction, such as "binary missing" versus "command failed".
- Do not skip when: the narrow check misses a case in the same category, or the unhandled path loses data or leaves partial state.
- Example signal: "only falls back on ENOENT".
