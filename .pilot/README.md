# Single- vs multi-agent pilot

A reproducible comparison of ALCHEMY on one agent and on several, for a
server-side audit-and-refactor task: correctness bugs, security defects, dead
code, architectural simplification, and independent review.

**Status: real runs recorded.** Each run's result, with acceptance facts taken
from the runtime's own event stream or saved sessions, is in
[`results/`](./results/); the summary table and what it does and does not show
are in the [root README, section 2](../README.md#single-agent-or-several-measured).
The fixture is a representative stand-in: the production backend the pilot is
meant to represent was not available in this repository.

## Layout

| Path | Holds |
|:--|:--|
| `server-audit/project/` | The fixture: a Node.js (CommonJS, no dependencies) orders/users/payments/reports API, 17 source files in routes → services → store layers, a spec in its `README.md`, and a visible `node --test` suite that passes |
| `server-audit/defects.json` | Ground truth: 10 seeded defects with category, file, and scoring method |
| `server-audit/hidden-tests/` | One scoring test per behavioral defect, named by defect id; never copied into a run project |
| `score.py` | Scores a result project; never modifies it |
| `run_pilot.py` | Builds a throwaway run project, runs one arm headless, analyses the stream, scores, writes the result |
| `pilot_analysis.py` | Acceptance facts from a Claude Code or Codex event stream |
| `test/` | Parser unit tests over hand-written **synthetic** streams; they prove the parser, not the methodology |
| `codex_threads.py` | Recovers a Codex run's agent tree (parent thread, spawn depth, skills read) from `~/.codex/sessions`, because `codex exec --json` does not always stream sub-agent activity |
| `objectives/` | Objective files for runs other than the built-in audit and trivial objectives |
| `results/` | Recorded runs: result JSON plus the redacted, time-stamped event stream |

## Arms

Both arms send the same objective through the normal entrypoint, `/alchemy
<objective>` for Claude Code and `$alchemy <objective>` for Codex, and never
mention agents. Both run
`.agents/skills/alchemy-orchestrate/scripts/init_workspace.py --runtime
claude-code|codex`. The arms differ only in `alchemy-workspace.json`:

| Arm | `execution.multi_agent` |
|:--|:--|
| `single` (baseline) | `off`, written by the harness after init |
| `multi` | `auto`, as init writes it; the harness refuses to run otherwise |

Built-in objectives: `audit` (the measured task) and `trivial` (a one-function
rename, an acceptance test that `auto` still stays single-agent on small work).
`--objective-file` supplies any other text; a leading `/alchemy` or `$alchemy`
is replaced by the runtime's entrypoint.

The run project is a temporary git repository: commit 1 is the fixture, commit
2 (the base) adds `.claude/skills`, `.agents/skills`, the root `CLAUDE.md` as
`CLAUDE.md` and `AGENTS.md`, and the init output. Before the agent starts, the
harness checks that no `.pilot` path, hidden test, `defects.json`, or answer
marker is in it, and aborts if one is.

## Reproduce

Prerequisites: Python 3.12+, Node.js 20+, git, and a signed-in `claude` or
`codex` CLI. Pin the model so both arms use the same one.

```sh
python .pilot/run_pilot.py --arm single --dry-run          # build, check isolation, print the command
python .pilot/run_pilot.py --arm single --model <id> --out .pilot/results/single-claude-audit-1.json
python .pilot/run_pilot.py --arm multi  --model <id> --out .pilot/results/multi-claude-audit-1.json
python .pilot/run_pilot.py --arm multi  --model <id> --objective trivial
python .pilot/run_pilot.py --arm multi  --model <id> --inject-agent-failure
python .pilot/run_pilot.py --arm multi  --runtime codex --model <id>
python .pilot/score.py <project dir> [--json out.json]     # score any project directory
python -m unittest discover -s .pilot/test -v              # parser tests
```

`--keep DIR` copies the finished run project out before the temp copy is
deleted. `--timeout` defaults to 3600 s; on timeout the process tree is killed
and the partial result is still scored. `--max-budget-usd` caps a Claude run.
`--cli PATH` runs another executable instead of the one on `PATH`.
`--analyze-stream FILE` re-derives acceptance facts from a saved stream.

Claude Code runs as `claude -p <prompt> --output-format stream-json --verbose
--setting-sources project --strict-mcp-config --no-session-persistence
--permission-mode bypassPermissions --forward-subagent-text` with `CLAUDECODE`
removed from the environment. Codex runs as `codex exec --json
--dangerously-bypass-approvals-and-sandbox --ephemeral -C <project>
--ignore-user-config` (`--codex-user-config` drops the last flag).

## What is measured

Each run writes `<out>.json` and `<out>.stream.jsonl` (every event stamped with
`_t`, seconds since launch). Both are redacted: machine paths, the home
directory, the git identity, and token-shaped strings are replaced.

| Field | Source |
|:--|:--|
| `score` | `score.py`: per-defect `fixed`, counts by category, `defects_fixed` of 10, `visible_tests_pass` (the fixture's original tests against the result's `src/`), `project_tests_pass` (the result's own `node --test`), `result_unmodified` |
| `metrics` | Claude: the `result` event's `total_cost_usd`, `usage`, `modelUsage`, `duration_ms`, `num_turns`. Codex: summed `turn.completed` usage (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`); Codex reports no cost |
| `wall_clock_seconds`, `exit_code`, `timed_out` | The harness |
| `acceptance` | `pilot_analysis.py`, below |
| `git` | `git diff --numstat` against the base plus untracked files; `fixture_files_changed` excludes skill trees, `.alchemy/`, and `PR.md` |
| `pr_md` | Whether `PR.md` exists, names a test command, reports results, and lists what was not verified; its redacted text |
| `orchestration_artifacts` | Files the run wrote under `.alchemy/` (plans, ledgers, hand-offs) |
| `objective_checks` | Objective-specific static checks; `trivial` checks the rename |

Scoring: five defects are behavioral and scored by a hidden test that fails on
the seeded code and passes once fixed; five are structural and scored by a
deterministic check over `src/` (`defects.json` holds each check). Each hidden
test runs as its own `node --test` process, so one exit code scores one defect.

### Acceptance facts

| Fact | Derivation |
|:--|:--|
| `agent_launches` | Each `Agent`/`Task` tool use: id, `subagent_type`, description, order, `launched_at`, `finished_at` (tool result for foreground agents; task notification for background agents; the latest sub-agent event when later) |
| `parallel_overlap` | A later launch arrives before an earlier agent finished (stream order) |
| `skills_loaded_by_lead`, `skills_loaded_by_subagents` | `Skill` tool uses and reads of `*/skills/*/SKILL.md`, grouped by `parent_tool_use_id`; `null` when no sub-agent event was observable |
| `execution_line`, `execution_mode`, `dispatch` | The lead's printed `Execution:` and `Dispatch:` records |
| `orchestration_checks` | Shell commands running `check_orchestration.py`, with subcommand, exit status, and verdict |
| `review_after_implementation` | An analyst launch that starts after every earlier implementer finished |
| `correction_after_review` | An implementer launch after such a review finished |
| `injection` | With `--inject-agent-failure`: a `PreToolUse` hook (`.alchemy/fail_first_agent.py`, merged into `.claude/settings.json`) blocks the first `Agent` call with exit 2 and `simulated agent crash: retry from the base commit`; records hook invocations, whether the lead launched again, and whether it relaunched the same agent type |

For Codex, launches are `collab_tool_call` items with `tool: spawn_agent`; an
agent finishes at the first later `wait` or `close_agent` item naming its
thread. `stream.collab_item_keys` lists the field names a real run produced.

## Proof of the harness

Executed while building it, with no model call:

- `node --test` on the fixture: 20 of 20 pass.
- `score.py` on the untouched fixture: 0 of 10 fixed, visible tests pass,
  result unmodified.
- Hand fixes applied one at a time in a copy outside the repository: each
  flipped exactly its own defect and kept the visible tests passing; all ten
  together: 10 of 10 fixed. The fixed copy is not stored.
- Dry runs for both arms on both runtimes: isolation clean, profile `off` or
  `auto` as intended, hook merged without dropping init's settings.
- A stand-in agent passed with `--cli` exercised the live path: line stamping,
  scoring, git and `PR.md` facts, redaction, stream file, and the timeout kill.
- 12 parser tests over the synthetic streams pass.

## Threats to validity

- **Single fixture, seeded defects.** A small synthetic service with known
  answers is not a production backend; defect density, size, and realism
  differ, and results may not transfer.
- **Small n, nondeterminism.** One run per arm says little; model output varies
  run to run. Run each arm several times, alternate the order, pin `--model`,
  and compare distributions, not single values.
- **Scoring blind spots.** Only seeded defects are scored: extra findings,
  false positives, and churn are not penalized except through the regression
  suites. Static checks are regex rules that a renamed or relocated equivalent
  can evade (`defects.json` states each rule). Hidden tests use only
  `createApp` and the documented HTTP API; an agent that changes that surface
  fails them for reasons other than the defect.
- **Visible harness.** The failure hook's script and settings are visible to
  the agent and may change its behavior.
- **Cost accounting.** Claude's `total_cost_usd` is taken as reported; whether
  it includes every sub-agent was not verified. Codex usage covers the parent
  thread's `turn.completed` events only.

## Not verified

- No real Claude Code or Codex run was executed, so these are unverified: that
  `--permission-mode bypassPermissions` allows edits and shell commands in this
  CLI version; that sub-agent events carry `parent_tool_use_id` in the stream
  (the result warns when none do); that the hook command
  `python .alchemy/fail_first_agent.py` resolves from the hook's working
  directory on Windows; the real shape of Codex `collab_tool_call` items; and
  whether Codex loads the project `.codex/config.toml` and `.codex/agents/`,
  which it reads only for a trusted project and the harness does not mark the
  temporary project trusted.
