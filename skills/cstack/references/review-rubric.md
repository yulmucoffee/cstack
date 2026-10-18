# Review rubric and finding contract

## Lenses

Use the lenses that apply. A one-line bug fix does not need an architecture essay.

**Correctness.** Does the code do what the intent says? Empty, null and boundary inputs. Errors caught, propagated or silently swallowed. Off-by-one, coercion, overflow, encoding. Stale closures, dangling references, partial transactions. Idempotency: what happens if this runs twice, or after a crash halfway? Concurrency: is shared mutable state serialized by structure (locks, phases, single owner) or by a convention that will not hold? When you suspect a bug, show the call chain that triggers it, not "this could be null".

**Root cause.** Is the change fixing the problem or hiding a symptom? Read callers, callees and types beyond the diff. Watch for guards that mask an invariant violation, retries that hide a broken contract, casts that silence a modeling error, and a fix in module A that belongs in module B's contract. If the fix is a comment saying "don't do X", ask whether a type, lint rule or runtime check could make X impossible.

**Structure.** Validation at system boundaries, trusted types inside. Data structures that match access patterns. Would the code look like this if the requirement had existed from day one? A new API with the old one kept alive and no external consumers is a dual path to delete now. Do not penalize simple code for lacking abstraction.

**Verification.** Are there tests, and do they assert behavior rather than implementation? Does a bug fix ship with a test for the bug? Is an integration boundary tested end to end? Does the code check the real value, or a proxy such as a file mtime or a self-report?

**Complexity.** Abstractions with one caller. Parameters for cases that do not exist. Dead code, vestigial flags, finished migrations whose scaffolding is still there. Every option and control should earn its place. Simpler is better unless simpler is wrong.

**Security.** Trace each input to its sink: SQL, shell, eval, HTML, file paths, deserialization. New endpoints without authn or authz. Secrets in code, logs or errors. Time-of-check to time-of-use gaps. Permission boundaries in CI and tooling.

**Repo conventions.** Code that breaks a rule in `CLAUDE.md`, `AGENTS.md` or `REVIEW.md`. Changes that make a line in those files out of date.

## Reviewer prompt

Give every reviewer the same prompt. Change only the model.

```
You are an adversarial code reviewer. Find real problems: bugs, design flaws,
security issues and maintainability risks that will cause pain. Do not praise.
Do not restate what the code does. An empty review is a valid outcome.

Intent (assume the goal is right; challenge the execution):
> {INTENT}

Code under review:
{DIFF_AND_CONTEXT}

Rubric:
{THIS FILE'S LENSES}

For each finding give: severity (critical | warning | nit), location (file:line),
trigger (exact input, state or ordering), failure (what breaks, who notices),
evidence (the call chain or a runnable repro), and a fix only if you have a
concrete one. Separate "this is broken" from "I would have done it differently".
Mark bugs that exist outside the diff as pre-existing.
```

## Finding contract

```
[ACT ON | CONSIDER | NOTED | DISMISSED | PRE-EXISTING] [critical | high | medium | low]
Location: path/to/file.ext:L123
Trigger: exact input, execution order or state
Failure: what breaks and who notices
Proof: executed repro or test output, or UNPROVEN plus the exact next check
Raised by: reviewer and model labels that found it independently
```

- `ACT ON`: an introduced correctness, security or costly maintenance defect. Blocks ship.
- `CONSIDER`: a real tradeoff worth the owner's attention now.
- `NOTED`: valid but not actionable at this scope.
- `DISMISSED`: disproven, unreachable or preference. Say why in one line.
- `PRE-EXISTING`: outside the diff. Report it without blaming the author.

Reviewers report `critical | warning | nit`. The lead assigns the contract severity after verifying: `critical` stays critical or becomes high, `warning` becomes medium or low, and `nit` is dropped unless `REVIEW.md` asks for nits.

When posting to a forge that uses Important / Nit / Pre-existing tags, map `ACT ON` to Important, keep nits out unless the repo's `REVIEW.md` asks for them, and map `PRE-EXISTING` directly.

No invented locations or test runs. Findings from shared or copied reasoning are not independent votes. "Consider adding tests" without a failing scenario is not a finding.

## Lead judgment

You are the lead reviewer, not a neutral aggregator.

- **Nitpick gravity.** Reviewers fill space. If every finding is a nit, the code is probably fine. Say so.
- **Hypothetical vs actual.** "What if this is null?" counts only if a caller can pass null. Trace it.
- **Premature abstraction.** "Extract an interface" is noise unless the code must vary a second way.
- **Different, not wrong.** A preference without a concrete failure is dismissed.
- **Missing context.** Findings on untouched code, or against a pattern the codebase uses everywhere, usually come from a narrow view. Dismiss them gracefully.
- **When they are right.** Independent agreement across models, a concrete execution path, or a finding that breaks your mental model all deserve attention. Correctness and security findings get extra scrutiny even from a single reviewer.

## Result template

```
VERDICT: PASS | PASS+NOTES | BLOCKED | FAIL
N actionable findings
Intent: ...
Safety fact: ... PROVED via ... | UNPROVEN
Act on: ...
Consider: ...
Dismissed / pre-existing: ...
Checks run: command -> observed result
Checks not run: ... and why
Independence: <models and agents> | limited
Agreement map: where reviewers agreed and diverged
Residual risk: ...
```
