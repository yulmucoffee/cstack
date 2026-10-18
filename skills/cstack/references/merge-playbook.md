# Merge playbook

`babysit` gets a PR to merge-ready and stops. `ship` lands verified work and starts only on an explicit request. GitHub CLI (`gh`) is assumed. Use the repo's own forge tooling if it has one.

## Babysit

1. **Declare the sub-mode.** `drive` (loop to merge-ready), `threads-only` (answer threads, fix only what a thread needs, leave CI and conflicts alone) or `check` (one read-only status pass). Small and docs-only PRs get `check`.
2. **One babysitter per stack.** Check nothing else is already driving it.
3. **Find the frontier.** The lowest unmerged PR in the dependency chain is the only one that matters until it merges. Read upstack threads and batch them. Do not fix upstack at the cost of restarting the frontier's checks.
4. **Read forge truth.** `gh pr view <n> --json state,isDraft,mergeable,mergeStateStatus,reviewDecision,headRefOid,baseRefName` and `gh pr checks <n>`. For threads, query `reviewThreads { isResolved }` through `gh api graphql`. Trust the forge's merge state over a list of green checks.
5. **Conflicts first.** Report which branch needs a rebase and stop. Do not rebase, retarget or force-push a shared stack from inside a babysit. Mention that trunk may have grown new callers of code the stack moves or deletes.
6. **Review threads next.** Triage each per `bugbot-triage.md`. Push fixes before replying so the reply can cite the commit. Write the reply body to a JSON file and send it with `gh api --method POST repos/<owner>/<repo>/pulls/<n>/comments/<id>/replies --input reply.json`. Never interpolate comment text into a command.
7. **CI last.** Read the failing job's log before anything else.
   - Flake or infrastructure: one fresh rerun (`gh run rerun <id> --failed`). Only one.
   - Identical second failure: not flake. Debug it.
   - Failure in code the diff never touched: check `git merge-base --is-ancestor origin/<base> HEAD`. A stale base needs a rebase, reported per step 5.
   - Failure in the diff's own code: fix with a commit on the owning branch.
8. **Re-verify after every push.** A new commit invalidates earlier approvals, verdicts and review coverage.
9. **Stop at the human's line.** Report `MERGE-READY` or `BLOCKED` with the blocker class. Missing human approval is a wait. A green gate is not a merge instruction.
10. **Sweep once at the end.** Offer recurring safe dismissals as candidate patterns in `bugbot-triage.md` or one line in `REVIEW.md`, in their own PR.

## Ship

1. **Verdict per PR.** One verifier per PR that did not write it runs the change the way a user would, parent against head, and records `PASS`, `PASS+NOTES` or `FAIL` on the PR with the commands and artifacts. CI and bot approvals are not verdicts.
2. **Contiguous run from the bottom.** Walk up from the lowest unmerged PR and stop at the first without a passing verdict. Everything below is the run. A verified PR above an unverified one waits.
3. **Verdicts cover patches.** Before trusting an older verdict, compare `git diff <base>...<verdict-sha> | git patch-id --stable` against the same for the current head. Different patch means a new verdict, except for differences only in tests, docs or lint config, which still need fresh checks.
4. **Gate and policy.** Every required check, current-head approval, code-owner review and ruleset passes. Never bypass. Never arm auto-merge on a head the verdict does not cover.
5. **Land bottom-up, one at a time.** Use the merge queue when configured. Otherwise `gh pr merge <n> --squash --match-head-commit <verified-head-sha>`, which refuses if the head moved. Then read back `gh pr view <n> --json state,mergedAt,baseRefName`. A PR merged into its parent branch is not on trunk. Queued and auto-merge-enabled are not merged.
6. **Move the next PR.** Retarget it to trunk (`gh pr edit <n> --base <trunk>`), rebase its patch onto the merge result, push with `--force-with-lease`, and apply step 3 before merging it.
7. **Leave the stack alone while it lands.** No other branch or base changes. If a merge stalls, find out why before touching anything.
8. **After merge.** Prefer flag, internal and canary rollout before broad release. Name the rollback step and its owner. A merge never authorizes a production deploy.

**Report:** the verified run and its ceiling, each PR's verdict and who produced it, what landed and how you confirmed it, and what the next gap needs.

GitHub settings, not prompts, enforce merges. Owners must configure rulesets, required checks, code-owner review and bypass restrictions.
