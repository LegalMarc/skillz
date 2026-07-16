# workflow-loop

Turn a goal into self-contained GitHub issues, then **grind through them AFK** with a deterministic multi-agent loop: every ticket gets a fresh, clean-context coder; an independent reviewer adversarially re-verifies the staged diff; a committer lands it with evidence; blocked tickets are **parked** — work stashed, findings posted to the issue, triage label applied — and the loop keeps going.

> 🌙 Built for the overnight run: start it, walk away, wake up to landed commits and a labeled triage list — not to a queue that died at ticket 4.

## Why this exists, and how I use it

*From the author:*

The bottleneck in agentic coding isn't the coding — it's the babysitting. Running one ticket per fresh context works beautifully, but it turns you into a human `while` loop: clear context, paste the ticket, review, commit, repeat. This skill is that loop, made deterministic and unattended. The setup cost moves where it belongs: into writing issues so self-contained that a solver with **zero prior context** can implement and *prove* them — every issue carries its own verification commands, and nothing lands without an independent reviewer re-running them.

The AFK part is the point. A long queue will always contain a ticket that's ambiguous or stubborn; the loop doesn't die there — it stashes the work, posts the reviewer's findings on the issue, labels it `afk-blocked`, and moves on to everything that doesn't depend on it. Morning triage is a label filter, not an archaeology dig.

## How it works

```
Decompose (with you) ──▶ self-contained issues, dependency-ordered, labeled `afk`
Loop (without you):
  Discover  sync gate + eligible issues (deps closed, not parked)
  Coder     fresh context: implement, run the issue's verification, stage
  Review    independent agent re-runs everything → APPROVE / findings (×N rounds)
  Land      commit "Refs #N" → push (ff-only) → close issue with SHA + evidence
  Park      blocked? stash, comment findings, label, continue
  ↺         re-discover: landings unblock dependents mid-run
```

**Model-agnostic:** roles are capability tiers, not model names. The reviewer runs the strongest model available at extra-high effort; the coder runs a mid tier (or inherits the session model) at high effort; mechanical steps (discover/land/park) run at medium effort. Configure via args — the script never hardcodes a vendor's model names, so it survives model generations and ports across runtimes.

**Safety rails (non-negotiable):** sync gate before every pick; push must succeed before an issue closes; never merge/rebase on rejection (ff-only retry once, then halt); reviewer never edits; parked work is stashed, never discarded; sequential by design — one tree, one branch, no merge races.

## Configure

All project specifics flow through `args` — never edit the script. Key knobs:

| Arg | Default | Notes |
|---|---|---|
| `repo` | — (required) | `OWNER/REPO` |
| `label` | `afk` | Which issues the loop owns |
| `checkCommand` | — | Full green-gate command; the loop keeps a green tree green |
| `coderModel` / `coderEffort` | inherit / `high` | Set model only if the runtime has a cheaper capable tier |
| `reviewerModel` / `reviewerEffort` | inherit / `xhigh` | Leave empty when the session already runs the strongest model |
| `onBlocked` | `skip` | `skip` = park & grind on (AFK); `halt` = stop at first block (attended) |
| `blockedLabel` | `afk-blocked` | Morning-triage filter |
| `maxTickets` / `maxReviewIterations` | 0 / 3 | 0 = all eligible |
| `coderNote` | `""` | Project invariants injected into every coder prompt |
| `referenceMode` / `referenceNote` | off | Mine per-ticket reference branches; adapt, never blind-copy |
| `dryRun` | false | Preview the queue before spending tokens |

See [SKILL.md](SKILL.md) for the full invocation, the issue template, and the failure-mode table.

## Requirements

- A runtime with a `Workflow`-style orchestration tool that can run `assets/workflow-loop.js` (Claude Code's Workflow tool).
- `gh` CLI authenticated for the target repo.
- A green baseline and a clean tree on the target branch.

## The morning after

```bash
gh issue list --label afk-blocked        # what got parked, findings in comments
git stash list                            # any preserved in-progress work
git log --oneline -20                     # what landed, each "Refs #N"
```

Fix or refine parked issues, remove the label, re-run — discovery recomputes everything from GitHub state.

## Testing

Hermetic evals in [`evals/`](evals/) cover the four behaviors that decide loop quality: PRD → self-contained vertical slices (with integration-level verification where unit suites are blind), model-agnostic invocation (tiers not names, `skip` for AFK), refusal to run issues that can't self-verify, and the parked-ticket triage story. No live repo needed — see `evals/evals.json`.
