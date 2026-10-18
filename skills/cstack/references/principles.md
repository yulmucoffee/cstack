# Engineering principles

Adapted from the principles in poteto's [pstack](https://github.com/cursor/plugins/tree/main/pstack) (MIT), rewritten for a review-and-merge workflow. In the report's `PRINCIPLES` line, name each principle that changed a decision and say which choice it changed. A principle you did not apply does not get cited.

| Principle | Apply when | What it changes | Evidence |
| --- | --- | --- | --- |
| Laziness protocol | Sizing a diff, tempted to add a layer | Bias to deletion and the smallest change that solves it | Smaller diff, unchanged behavior check |
| Subtract before you add | Sequencing a feature, refactor or rewrite | Remove dead weight first, build on the simpler base | Deletion commit lands before the addition |
| Foundational thinking | Before writing logic | Name core types, data shapes and what concurrent actors share | The type or schema, plus one illegal state it rules out |
| Model the domain | Stateful or branch-heavy code | Encode it in a structure (state machine, table, typed model) instead of scattered conditionals | One place to read the rules |
| Type system discipline | Designing a signature | Make illegal states unrepresentable, parse external data at boundaries | Compiler rejects the bad case |
| Boundary discipline | Validation, errors, adapters | Guard at system edges, trust internal types | No duplicate checks deep inside |
| Make operations idempotent | Commands, lifecycle steps, retries | Converge to the same end state after a crash or rerun | Run it twice, same result |
| Separate before serializing | Concurrent writers to one file, branch, key | Remove the sharing first, lock only if one writer is a real invariant | Ownership map |
| Migrate callers, then delete | New internal API with old callers | Move every caller and delete the old path in one wave | Zero references to the old API |
| Redesign from first principles | New requirement in an old design | Shape it as if it had existed from day one | The change does not read as bolted on |
| Minimize reader load | Code that is hard to trace | Collapse one-caller wrappers, shrink mutable scope, count hidden state | Fewer hops to follow a call |
| Exhaust the design space | Novel interaction or architecture | Prototype two or three options and compare | Measured tradeoff, not rhetoric |
| Experience first | Scope or UX tradeoff | Choose the user's outcome over implementation convenience | What the user notices |
| Attack the premise | Two fixes failed on one assumption | Test the assumption directly before a third fix | The premise check and its result |
| Fix root causes | Debugging | Fix the first place the system went wrong; guard only legitimate states | Repro red before, green after |
| Prove it works | Before saying done | Check the real artifact, not "it compiles" or a self-report | Command and observed output |
| Test behavior, not implementation | Writing or keeping a test | Assert what users of the code observe | Test survives a refactor, fails on regression |
| Explain the number | Reporting a measurement | Find the limiter, rule out measuring the wrong thing | Baseline, method and noise |
| Sequence verifiable units | Multi-step work and PR stacks | Small units that each end in a check, ordered to prove themselves | Each commit or PR has its own proof |
| Build the lever | Repetitive or sweeping work | Write the script or codemod instead of hand edits | The rerunnable tool |
| Guard the context window | Large outputs, many files | Push bulk reading to subagents, keep summaries in the main thread | Main thread holds conclusions, not dumps |
| Never block on the human | Reversible "should I?" questions | Proceed, report, let the human correct course | Decision log; pause only for irreversible steps |
| Encode lessons in structure | Same instruction written twice | Turn it into a lint, type, test or script | The new guard and a fixture it catches |

Do not claim multi-model review unless different models actually ran. Do not hand approvals or accountability to an agent.
