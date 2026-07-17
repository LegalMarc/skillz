---
name: workflow-loop
description: >
  Turn a goal into self-contained GitHub issues, then autonomously grind through
  them AFK with a multi-agent loop that gives every ticket clean context: a coder
  implements and stages, an independent reviewer adversarially verifies, a
  committer lands — and blocked tickets are parked with findings posted to the
  issue so the loop keeps going without human intervention. Use when the user
  wants to break work into tickets and solve them automatically, run an
  AFK/autonomous/overnight/unattended build loop, grind a ticket queue with
  fresh context per ticket, or says "create issues and solve them". Model-
  agnostic: roles are defined by capability tier and effort, not model names.
---

# Workflow Loop

A two-phase pattern for shipping a body of work autonomously:

1. **Decompose** the goal into GitHub issues that are *self-contained* — each carries its own acceptance criteria AND the exact commands that prove it's done.
2. **Loop** over eligible issues with a deterministic multi-agent workflow. Every ticket gets a **fresh agent (clean context)**: a coder implements and stages, an **independent reviewer** adversarially checks the staged diff, a committer lands it. Blocked tickets are **parked** — work stashed, findings posted to the issue, triage label applied — and the loop grinds on. After each landing the loop **re-discovers** — tickets unblocked by the landing join the queue in the same run.

The load-bearing idea: **the solver agent has zero prior context.** It only knows what the issue body says. The loop's quality is decided in Phase 1 — an issue without its own verification commands cannot self-verify, and the loop will drift. Spend the effort making issues self-contained.

## When to use

- "Break this into tickets and solve them automatically." / "Run an AFK build loop overnight."
- "Advance the queue, fresh context per ticket."
- You have a plan/PRD and want it turned into agent-grabbable issues *and* executed unattended.

For decomposition only (no execution), prefer `to-issues`. This skill adds the autonomous solver loop.

## Model policy (model-agnostic by design)

Roles are capability tiers, not model names. Resolve them **at invoke time** from whatever models the runtime offers:

| Role | Intelligence tier | Effort | How to configure |
|---|---|---|---|
| Reviewer (supervisor) | **Highest available** | high (`reviewerEffort: "xhigh"` default) | Leave `reviewerModel` empty to inherit the session model — correct when the session runs a frontier model; set it explicitly only if the session model is NOT the strongest available |
| Coder | **Mid tier** | high (`coderEffort: "high"` default) | Set `coderModel` to the runtime's cheaper capable tier if one exists; otherwise leave empty to inherit |
| Discovery / land / park | inherits coder model | medium (fixed) | Mechanical git/gh work — no configuration needed |

Never write model names into issues, and never hardcode them in the script — the asymmetry that matters is *reviewer thinks harder than coder*, and that survives every model generation.

## Prerequisites

- `gh` CLI authenticated for the target repo.
- A green baseline: the repo's check command passes on a clean tree. The loop keeps a green tree green; it can't fix a red one.
- Clean working tree, on the branch you'll commit to.
- The `Workflow` tool. The loop is `assets/workflow-loop.js`.

---

## Phase 1 — Decompose into self-contained issues

Work from the conversation context (plan, PRD, prose). Then:

**1a. Slice vertically.** Tracer-bullet issues — thin slices cutting end-to-end (schema → logic → API → tests), not horizontal layers. Many thin slices beat few thick ones. Size each slice for one clean-context sitting: if it plausibly touches more than ~10 files, split it.

**1b. Order by dependency.** Record dependencies explicitly in each issue body (`## Dependencies` / "needs #N") so the loop computes eligibility from GitHub state alone. An issue is *eligible* only when all its deps are CLOSED.

**1c. Use the self-contained template.** Every issue MUST include a **Required verification** section with copy-pasteable commands — runnable from the repo root, deterministic (no live network, no manual steps). Non-negotiable: it is how a cold solver and reviewer prove the work. If a change constrains a layer the unit suite bypasses (migrations, infra, external seams), the verification must include the integration command that exercises that layer.

```markdown
## Goal
One paragraph: the end-to-end behavior this slice delivers.

## Dependencies
- needs #N   (or "None — immediately eligible")

## Scope
- Exactly what changes.

## Out of scope
- What this slice deliberately does NOT touch.

## Acceptance criteria
- Observable, testable statements; each maps to a verification command below.

## Required verification
- `<exact test command for this slice>`
- `<full repo check command, e.g. bash scripts/check.sh>`

## Notes
- Everything a cold solver must know: security invariants, conventions,
  "read file X §Y", prior decisions. The solver will not infer these.
```

**1d. Confirm before publishing.** Present the breakdown (title · blocked-by) and iterate with the user. Publish in dependency order via `gh issue create`, applying the loop label (default `afk`).

> Existing issues? Skip to Phase 2 — but first confirm they carry **Required verification** sections; add them if missing.

---

## Phase 2 — Run the autonomous loop

`assets/workflow-loop.js` is a parameterized `Workflow` script. Repo-agnostic and model-agnostic: configure via `args`, never edit per project.

### Invoke

```
Workflow({
  scriptPath: "<absolute path to this skill>/assets/workflow-loop.js",
  args: {
    repo: "OWNER/REPO",              // required
    label: "afk",                    // loop label
    branch: "main",
    checkCommand: "bash scripts/check.sh",
    setupCommand: "source .venv/bin/activate",  // or ""
    coderModel: "",                  // "" = inherit session model; or the runtime's mid tier
    coderEffort: "high",
    reviewerAgentType: "general-purpose",  // or a project reviewer, e.g. "skull-reviewer"
    reviewerModel: "",               // "" = inherit session model (use the strongest available)
    reviewerEffort: "xhigh",
    onBlocked: "skip",               // "skip" = park & grind on (AFK default); "halt" = stop at first block
    blockedLabel: "afk-blocked",     // triage label for parked tickets
    reportIssue: "auto",             // run journal + end report: "auto" = create/reuse "AFK run log" issue; N = issue number; 0 = off
    autoRecover: false,              // restart flows ONLY — stash a crashed run's dirty tree and proceed (see Overnight resilience)
    commitPrefix: "",                // optional subject convention
    maxTickets: 0,                   // 0 = all eligible
    maxReviewIterations: 3,
    coderNote: "",                   // project invariants for every coder prompt (see Adapting)
    referenceMode: false,            // mine per-ticket reference branches (adapt, don't copy)
    referenceNote: "",               // project specifics for referenceMode
    dryRun: false                    // true = preview the eligible queue, change nothing
  }
})
```

Runs in the background; watch with `/workflows`. Tip: run once with `dryRun: true` to sanity-check the queue, dependency parsing, and lint findings before spending tokens — dryRun is strictly read-only (no comments, no labels, no stashes, no journal). If the user set a token target ("+500k"), the loop honors it — it stops cleanly *between* tickets when the budget nears exhaustion.

### Shape of a run

```
Round:
  Discover →  sync gate (fetch; abort if behind or dirty — autoRecover stashes
              instead) + eligible open `label` issues (all deps CLOSED, not
              parked) + LINT GATE: issues without runnable Required-verification
              commands are commented, labeled, excluded. Topological order.
              First live round also opens the run journal (reportIssue).
  For each eligible issue (FRESH AGENT, no shared memory):
    Coder    →  read issue, plan, implement, run the issue's Required
                verification + checkCommand (one bounded retry per flaky
                command, disclosed), git diff --check, stage. Sees the RUN
                LEDGER: ≤5 factual lessons from this run's earlier rejections.
    Review   →  independent agent re-runs verification on the staged diff
                → APPROVE | REQUEST_CHANGES (numbered file:line findings,
                  plus a one-line lesson for the ledger)
                  ↳ coder fixes, re-stages, re-review (max N rounds);
                    the FINAL fix round escalates to reviewer-tier model/effort
                  ↳ exhausted: PARK (skip mode) or stop (halt mode)
    Land     →  commit ("Refs #N" — no auto-close keywords), PUSH
                (ff-only retry once, NEVER merge/rebase), then
                gh issue close with SHA + evidence
    Park     →  (blocked tickets, skip mode) stash work, post findings as an
                issue comment, apply `blockedLabel`, continue to next ticket
  Re-discover if this round landed work and issues remain dep-blocked
  (a landing may have unblocked them). Else done.
End of run → one report comment on the journal issue: landed (SHAs), parked
             (reasons), failed. Reporting never affects outcomes.
```

**AFK grinding (`onBlocked: "skip"`, the default):** a blocked ticket never stops the queue. Its work is stashed (recoverable via `git stash list`), the reviewer's findings land on the issue as a comment, and the `blockedLabel` marks it for morning triage. Dependents of a parked ticket stay ineligible automatically (the issue stays open). Loop-level problems still halt — behind-origin, dirty tree, push rejection, or a failed park — because continuing would contaminate every subsequent ticket.

**Attended runs (`onBlocked: "halt"`):** stops at the first blocked ticket with work left staged for inspection — same discipline as a human running one ticket per `/clear`.

The loop is sequential by design: one shared tree, one branch; parallel landings invite merge races.

### Hygiene rules (encoded in the template — do not weaken)

- **Sync before picking**; refuse to act if behind the remote or the tree is dirty.
- **Push after every commit**; a closed issue must cite a SHA reachable from the remote.
- **Never merge/rebase on push rejection** — ff-only retry once, else stop.
- **One loop per repo.** Never start a second concurrently.
- **Independent review, always**; the reviewer re-runs verification itself and never edits.
- **Parked work is stashed, never discarded**; every park leaves findings on the issue.
- **Flaky retries are bounded and disclosed** — one re-run per failing command, ever; a retry-pass must say "passed on retry — possible flake" so nothing is silently masked (the reviewer re-runs it anyway).
- **The run ledger stays factual and bounded** — max 5 one-line lessons distilled from actual reviewer findings; never speculation, never project lore (that belongs in `coderNote`).

## Adapting

Keep the four-role spine and the hygiene rules; layer project specifics through args, never by editing the script:

- **`coderNote`** — invariants every coder must know. Example: *"The unit suite builds the schema directly, NOT via migrations — always run the ticket's integration verification too; a NOT NULL column whose writers aren't updated passes unit tests and breaks in prod."*
- **`reviewerAgentType`** — point at a project reviewer subagent that encodes repo rules.
- **`referenceMode` + `referenceNote`** — when per-ticket reference branches exist (e.g. from a prior implementation pass), the coder mines each ticket's branch as a guide; `referenceNote` carries what changed since (refactors, migration renumbering, already-landed schema).
- Front-load invariants into each issue's `## Notes` — the solver reads nothing else.

## Overnight resilience (auto-restart after usage-limit exhaustion)

A usage window (e.g., a 5-hour limit) can kill the session mid-run: agents die, the loop halts. All loop state lives in GitHub — labels, closed issues, parked labels, stashes — so **any fresh session can resume with the same args**. To make that happen without a human:

1. Invoke the loop with `reportIssue: "auto"` so the run keeps a journal (start comment, end report) on the "AFK run log" issue.
2. Create an **hourly, self-canceling cron job** (Claude Code: `CronCreate`; or the schedule skill) whose prompt is self-contained:

```text
You are the overnight relauncher for a workflow-loop run on OWNER/REPO.
1. LIVENESS: read the newest comments on the open "AFK run log" issue and run
   git log --oneline --since="45 minutes ago" in <repo path>. If the latest
   journal comment is "Run started" less than 45 minutes old OR commits are
   still landing, exit — the run is alive.
2. WORK CHECK: gh issue list --repo OWNER/REPO --label <label> --state open,
   excluding issues labeled <blockedLabel>. If none remain, verify the journal
   has an end-of-run report, then DELETE this cron job. Done.
3. RESUME: invoke the Workflow tool with <skill path>/assets/workflow-loop.js
   and the ORIGINAL args verbatim, plus autoRecover: true and
   reportIssue: "auto". Do not change any other arg.
```

3. While the account is rate-limited, a cron firing simply fails or does nothing — harmless. The first firing after the window resets resumes the run, so "ASAP" means within the cron interval of the reset.

**Honest caveat:** the liveness check is a heuristic (journal freshness + commit recency). Its worst cases are benign by construction — a delayed restart, or a concurrent-start attempt that the sync gate and the `autoRecover` stash absorb. `autoRecover: true` belongs **only** in these restart flows: it stashes a crashed run's leftovers (`afk-crash-recovery` stash, recoverable) instead of refusing on a dirty tree. Attended runs keep the strict gate so a human inspects crashed state.

## Failure modes & recovery

- **"behind origin" / "dirty tree"** → aborts at the sync gate. Fix by hand, re-run (or see *Overnight resilience* for unattended flows).
- **Parked tickets** (skip mode) → triage by label: `gh issue list --label afk-blocked`. Findings are in the issue comments; stashed work via `git stash list`; the run journal issue has the full landed/parked/failed report. Fix or refine the issue, remove the label, re-run.
- **Lint-gate exclusions** → same label and triage path as parks; the comment says exactly which section is missing. Add the verification commands, remove the label, re-run.
- **Coder blocked / review exhausted** (halt mode) → loop stops with the reason; work is **staged, not committed**. Inspect, fix or refine, re-run; closed issues drop out automatically.
- **Landing failed** → always halts (loop-level). Resolve the push problem by hand.
- **Resume** → invoke again (discovery recomputes from GitHub), or `Workflow({scriptPath, resumeFromRunId})` to reuse the prior run's cached agent results.
