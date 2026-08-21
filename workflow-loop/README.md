# workflow-loop

Turn a goal into self-contained GitHub issues, then **grind through them AFK** with a deterministic multi-agent loop: every ticket gets a fresh, clean-context coder; an independent reviewer adversarially re-verifies the staged diff; a committer lands it with evidence; blocked tickets are **parked** — work stashed, findings posted to the issue, triage label applied — and the loop keeps going.

> 🌙 Built for the overnight run: start it, walk away, wake up to landed commits and a labeled triage list — not to a queue that died at ticket 4.

## Why this exists, and how I use it

*From the author:*

The bottleneck in agentic coding isn't the coding — it's the babysitting. Running one ticket per fresh context works beautifully, but it turns you into a human `while` loop: clear context, paste the ticket, review, commit, repeat. This skill is that loop, made deterministic and unattended. The setup cost moves where it belongs: into writing issues so self-contained that a solver with **zero prior context** can implement and *prove* them — every issue carries its own verification commands, and nothing lands without an independent reviewer re-running them.

The AFK part is the point. A long queue will always contain a ticket that's ambiguous or stubborn; the loop doesn't die there — it stashes the work, posts the reviewer's findings on the issue, labels it `afk-blocked`, and moves on to everything that doesn't depend on it. Morning triage is a label filter, not an archaeology dig.

## How it works

```
Decompose (with you) ──▶ self-contained issues, dependency-ordered, AFK-laddered, labeled `afk`
Loop (without you):
  Discover  sync gate + eligible issues (deps closed, not parked)
  Coder     fresh context: implement, run the issue's verification, stage
  Review    independent agent re-runs everything → APPROVE / findings (×N rounds)
  Land      commit "Refs #N" → push (ff-only) → close issue with SHA + evidence
  Park      blocked? stash, comment findings, label, continue
  ↺         re-discover: landings unblock dependents mid-run
```

**The AFK ladder (decomposition):** a ticket the loop cannot grind is a place the queue stalls waiting on you, so "attended" is a last resort the decomposition has to argue for. Every ticket climbs four rungs: already unattended → blocked only on a **missing input** (asked back as one batched multiple-choice round, then it is AFK) → blocked only because nobody looked for a **programmatic path** (CLI → HTTP API → browser automation → computer control, in that order, actually tried) → genuinely irreducible human act. Only the last rung produces an attended ticket, it must state why, and the human's part is reduced to **one approval click or one fully-substituted copy-paste block** — never a procedure.

**Model-agnostic:** roles are capability tiers, not model names. The reviewer runs the strongest model available at extra-high effort; the coder runs a mid tier (or inherits the session model) at high effort; mechanical steps (discover/land/park) run at medium effort. Configure via args — the script never hardcodes a vendor's model names, so it survives model generations and ports across runtimes.

**Safety rails (non-negotiable):** sync gate before every pick; push must succeed before an issue closes; never merge/rebase on rejection (ff-only retry once, then halt); reviewer never edits; parked work is stashed, never discarded; flaky-test retries are bounded to one and always disclosed; sequential by design — one tree, one branch, no merge races.

**Built-in force multipliers:** a lint gate at discovery rejects issues that can't self-verify before they burn a coder+reviewer cycle; a bounded **run ledger** feeds each fresh coder the (≤5) lessons reviewers taught earlier in the same run; the **final fix round escalates** to reviewer-tier model/effort — one max-strength attempt before parking; and an optional **run journal** issue collects a start comment and an end-of-run report (landed SHAs, parked reasons) so triage is one permalink.

**Overnight resilience:** because all loop state lives in GitHub, a usage-limit death mid-run is recoverable by any fresh session — the question is only how anything finds out. The primary mechanism is a durable marker: the run journal posts a "Started/Landed/Parked" line per ticket plus an end-of-run "🔴 Run ended" or "⏸ HALTED" comment, even when nothing landed — a plain GitHub comment that outlives the session that wrote it. An optional hourly self-canceling scheduled-task relauncher (checks the marker, resumes with the original args + `autoRecover: true`, deletes itself when the queue drains) is a convenience on top of that, not a substitute: it only fires while its session stays alive, so a cron alone does not survive a multi-day gap — the marker on the journal issue is what a human or a longer-lived scheduler actually resumes from.

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
| `reportIssue` | `0` (off) | `"auto"` = create/reuse an "AFK run log" issue for the run journal + end report |
| `autoRecover` | `false` | Restart flows only: stash a crashed run's dirty tree and proceed |
| `maxTickets` / `maxReviewIterations` | 0 / 3 | 0 = all eligible |
| `coderNote` | `""` | Project invariants injected into every coder prompt |
| `referenceMode` / `referenceNote` | off | Mine per-ticket reference branches; adapt, never blind-copy |
| `dryRun` | false | Preview the queue before spending tokens |

See [SKILL.md](SKILL.md) for the full invocation, the issue template, and the failure-mode table.

## Requirements

- A runtime with a `Workflow`-style orchestration tool that can run a scripted multi-agent loop from a file (here, `assets/workflow-loop.js`).
- `gh` CLI authenticated for the target repo.
- A green baseline and a clean tree on the target branch.

## The morning after

```bash
gh issue list --label afk-blocked        # parked + lint-rejected, findings in comments
git stash list                            # any preserved in-progress work
git log --oneline -20                     # what landed, each "Refs #N"
```

With `reportIssue: "auto"`, skip all three: the "AFK run log" issue has the whole story in one comment — landed (SHAs), parked (reasons), failed — readable on your phone.

Fix or refine parked issues, remove the label, re-run — discovery recomputes everything from GitHub state.

## Testing

Hermetic evals in [`evals/`](evals/) cover the five behaviors that decide loop quality: PRD → self-contained vertical slices (with integration-level verification where unit suites are blind), model-agnostic invocation (tiers not names, `skip` for AFK), refusal to run issues that can't self-verify, the parked-ticket triage story, and overnight-resume setup (journal-backed liveness marker plus a self-canceling relauncher, `autoRecover` only on the restart flow). No live repo needed — see `evals/evals.json`.

If you edit `assets/workflow-loop.js`, `node --check` exiting 0 is not proof it loads: the file is plain `.js` with a top-level `return` and `export`, each invalid under one of Node's two module goals, and it only resolves inside the Workflow tool's own wrapper. Validate by running it (or the evals), not by syntax-checking it standalone.
