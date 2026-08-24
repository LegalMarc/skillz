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

## Harness vocabulary

This skill is written in generic terms so any agentic coding harness can run the pattern. The **Concept** column is the contract; the harness columns are translations. On a harness not listed here, satisfy the Concept column and the rest of this document applies unchanged.

| Generic term | Concept — what any harness must provide | Claude Code | OpenAI (Codex CLI / Agents SDK) | DeepSeek-based harness (e.g. OpenHands, Aider + DeepSeek API) |
|---|---|---|---|---|
| **orchestrator** | A deterministic runner that executes the loop script, spawns one sub-agent per prompt, and enforces each reply's JSON schema | the `Workflow` tool runs `assets/workflow-loop.js` natively (`scriptPath` + `args`) | no native equivalent — port the loop skeleton to the Agents SDK, or drive `codex exec` once per role from your own script | no native equivalent — script the loop yourself; each role is one API call with a JSON-schema response format |
| **sub-agent (fresh context)** | One clean-context model run that sees ONLY its prompt — no memory of other tickets or other roles | `agent(prompt, {schema, effort, model})` inside the Workflow script | one fresh agent run / one `codex exec` invocation per role | one fresh conversation per role — never reuse a session across tickets |
| **capability tier** | "Strongest available" vs "cheaper capable" model, resolved at invoke time, never hardcoded | leave the model arg empty to inherit the session model; set a cheaper tier for the coder if one exists | strongest reasoning model for review; a mini tier for mechanical steps | `deepseek-reasoner` for review; `deepseek-chat` for coder and mechanical steps |
| **reasoning effort** | How hard a role thinks: reviewer > coder > mechanical | `effort: "low"` … `"xhigh"` | the `reasoning_effort` parameter | no effort dial — approximate by tier: reasoner ≈ high, chat ≈ low |
| **token budget** | A ceiling for the run; the loop stops cleanly BETWEEN tickets as it nears | a "+500k"-style directive, exposed to the script as `budget` | track usage from API responses in your skeleton; stop between tickets | same — count tokens from the API's usage fields |
| **run monitor** | A live view of loop progress | `/workflows` | your skeleton's own logs | your skeleton's own logs |
| **resume** | Re-running after a stop must not redo landed work | re-invoke (discovery recomputes from GitHub), or `resumeFromRunId` to replay cached agent results | re-invoke — GitHub state (closed issues, labels, stashes) IS the resume state | same — GitHub state is the resume state |
| **scheduled task** | Something that can fire after the session is gone (see Overnight resilience) | in-session scheduled tasks (fire only while the session lives) or an external scheduler | system cron / hosted scheduler | system cron / hosted scheduler |

Only the **orchestrator** row is harness-native code: `assets/workflow-loop.js` is written in Claude Code's Workflow DSL. Everything else — the issue template, the AFK ladder, the role prompts inside the script, the hygiene rules, the journal/marker protocol — is plain text and plain process, portable as-is. Porting to a new harness means re-implementing only the loop skeleton (discover → code → review×N → land | park → re-discover) around the same prompts.

## When to use

- "Break this into tickets and solve them automatically." / "Run an AFK build loop overnight."
- "Advance the queue, fresh context per ticket."
- You have a plan/PRD and want it turned into agent-grabbable issues *and* executed unattended.

For decomposition only (no execution), prefer `to-issues`. This skill adds the autonomous solver loop.

## Model policy (model-agnostic by design)

Roles are capability tiers, not model names. Resolve them **at invoke time** from whatever models the runtime offers. (Effort names below use Claude Code's scale — translate per the Harness vocabulary table.)

| Role | Intelligence tier | Effort | How to configure |
|---|---|---|---|
| Reviewer (supervisor) | **Highest available** | high (`reviewerEffort: "xhigh"` default) | Leave `reviewerModel` empty to inherit the session model — correct when the session runs a frontier model; set it explicitly only if the session model is NOT the strongest available |
| Coder | **Mid tier** | high (`coderEffort: "high"` default) | Set `coderModel` to the runtime's cheaper capable tier if one exists; otherwise leave empty to inherit |
| Discovery / land / park / integrate | inherits coder model | medium (fixed) | Mechanical git/gh work — no configuration needed |

Never write model names into issues, and never hardcode them in the script — the asymmetry that matters is *reviewer thinks harder than coder*, and that survives every model generation.

## Prerequisites

- `gh` CLI authenticated for the target repo.
- A green baseline: the repo's check command passes on a clean tree. The loop keeps a green tree green; it can't fix a red one.
- Clean working tree, on the branch you'll commit to.
- An orchestrator (see Harness vocabulary). On Claude Code that is the `Workflow` tool, which runs `assets/workflow-loop.js` natively; elsewhere, the loop skeleton is ported around the same prompts.

---

## Phase 1 — Decompose into self-contained issues

Work from the conversation context (plan, PRD, prose). Then:

**1a. Slice vertically.** Tracer-bullet issues — thin slices cutting end-to-end (schema → logic → API → tests), not horizontal layers. Many thin slices beat few thick ones. Size each slice for one clean-context sitting: if it plausibly touches more than ~10 files, split it.

**1b. Order by dependency.** Record dependencies explicitly in each issue body (`## Dependencies` / "needs #N") so the loop computes eligibility from GitHub state alone. An issue is *eligible* only when all its deps are CLOSED.

**1c. Use the self-contained template.** Every issue MUST include a **Required verification** section with copy-pasteable commands — runnable from the repo root, deterministic (no live network, no manual steps). Non-negotiable: it is how a cold solver and reviewer prove the work. If a change constrains a layer the unit suite bypasses (migrations, infra, external seams), the verification must include the integration command that exercises that layer. Write verification that **fails on the untouched tree** — a block that already passes before the diff exists gates nothing; the loop's coder pre-flights exactly this and parks any ticket whose verification is already fully green as stale.

```markdown
## Goal
One paragraph: the end-to-end behavior this slice delivers.

## Dependencies
- needs #N   (or "None — immediately eligible")

## Scope
- Exactly what changes.

## Out of scope
- What this slice deliberately does NOT touch.

## Automation
- `afk` — one line on what makes it runnable unattended.
  (or) ATTENDED, rung 3 — why no CLI/API/browser/computer-control path exists,
  and the single click or paste the human performs.

## Acceptance criteria
- Observable, testable statements; each maps to a verification command below.

## Required verification
- `<exact test command for this slice>`
- `<full repo check command, e.g. bash scripts/check.sh>`

## Notes
- Everything a cold solver must know: security invariants, conventions,
  "read file X §Y", prior decisions. The solver will not infer these.
```

**1d. Run the AFK ladder over every ticket. This is what decides the label.**

A ticket the loop cannot grind is a place the queue stalls waiting on a human. **Attended is a last resort you argue for, not a default you fall back to.** For each ticket, climb until it stops:

| Rung | Question | If yes |
|---|---|---|
| **0** | Does it already run unattended from a clean checkout? | Label `afk`. Done. |
| **1** | Is it blocked only by a **missing input** — a credential, an ID, an endpoint, a choice between two designs? | Not a real blocker. Collect the question for 1e, inline the answer into `## Notes`, then `afk`. |
| **2** | Is it blocked only because nobody looked for a **programmatic path**? | Escalate in order: **CLI** (install it if that is what it takes) → **HTTP API** → **browser automation** → **computer control**. It only leaves this rung after all four have actually been tried. |
| **3** | Is the human act itself the irreducible content — a consent screen that detects automation, a physical action, a signature, a legally-personal click? | Attended. Go to 1f. |

Record the rung in the issue's `## Automation` field. A rung-3 ticket must say *why*, so a later pass can re-attack it when a CLI ships or a policy changes.

⚠ **Rung 2 is where attended tickets get created by mistake.** "There is no CLI for that" is a claim to verify, not an assumption to make. Check the vendor's own CLI, the `gh`/`aws`/`gcloud`-class tool, the HTTP API sitting behind the web UI, and a headless browser driver — in that order — before conceding. Installing a tool is cheaper than a permanent hole in the queue.

**1e. Ask every unblocking question at once, as multiple choice.**

Rung-1 tickets are blocked only until the user answers. Collect every such question across the **whole batch** and ask them in **one** interaction — multiple choice, recommended option first, each naming the ticket it unblocks and what changes based on the answer. Never drip-feed one question per ticket, and never ask open prose the user has to compose an answer to.

After the answers land, inline them into the relevant `## Notes` and relabel those tickets `afk`.

> The measure of success for this step: **afterwards, no ticket in the queue is waiting on information.**

**1f. For genuine rung-3 tickets, reduce the human's part to a single action.**

Never hand over a procedure. Hand over exactly one of:

- **One approval click** — the URL, already scoped, naming the exact control to click.
- **One copy-paste block** — a single fenced command with every value already substituted. No placeholders, no "replace `<X>` with your…", no multi-step sequence.

Everything around that one action is yours: pre-create what can be pre-created, prepare the payload, and write the verification that will confirm the human's action landed. Their job is to click or paste, nothing else.

Create these **without** the loop label so the queue never blocks on them — but keep their `## Required verification` section, because an attended session still has to prove it did the right thing.

**1g. Confirm before publishing.** Present the breakdown (title · rung · blocked-by) and iterate with the user. Publish in dependency order via `gh issue create`, applying the loop label (default `afk`) to everything that cleared rungs 0-2.

> Existing issues? Skip to Phase 2 — but first confirm they carry **Required verification** sections, and run the ladder (1d) over any that are unlabelled or attended; a queue inherited from an earlier pass is exactly where stale rung-3 calls hide.

---

## Phase 2 — Run the autonomous loop

`assets/workflow-loop.js` is a parameterized orchestrator script. Repo-agnostic and model-agnostic: configure via `args`, never edit per project.

### Invoke (Claude Code syntax — on another harness, feed the same args to your loop skeleton)

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
    reviewerAgentType: "general-purpose",  // or a project reviewer subagent, e.g. "backend-reviewer"
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
    dryRun: false,                   // true = preview the eligible queue, change nothing
    priority: [],                    // issue numbers to prefer first (tie-break only, never over deps)

    // ── Parallel mode (opt-in; see "Parallel mode" below) ──
    workers: 1,                      // tickets coded+reviewed CONCURRENTLY; 1 = sequential
    workerSetupCommand: "",          // provision each worktree ($WL_MAIN, $WL_WORKSPACE)
    worktreeRoot: "",                // default: ../.wl-worktrees (sibling of the checkout)
    branchPrefix: "wl",              // per-ticket branches: wl/<issue>
    shadowFootprints: false          // sequential run that MEASURES write-set prediction
  }
})
```

Runs in the background; watch with your harness's run monitor (Claude Code: `/workflows`). Tip: run once with `dryRun: true` to sanity-check the queue, dependency parsing, and lint findings before spending tokens — dryRun is strictly read-only (no comments, no labels, no stashes, no journal). If the user set a token target ("+500k"), the loop honors it — it stops cleanly *between* tickets when the budget nears exhaustion.

### Shape of a run

```
Round:
  Discover →  sync gate (origin URL must match `repo` — every git command acts on
              the cwd, so a wrong checkout would read issues from one repo and
              push to another; then fetch; abort if behind, ahead, or dirty —
              ahead means a prior land likely committed but failed to push;
              autoRecover stashes a dirty tree instead) + eligible open `label` issues (all deps CLOSED, not
              parked) + LINT GATE: issues without runnable Required-verification
              commands are commented, labeled, excluded. HEAD-BLOCKER GUARD:
              reads the run journal for a ticket marked "Started" with no later
              "Landed"/"Parked"/"Halted" entry — a coder-and-park-agent double death — and
              parks it before it starves the rest of the queue (needs reportIssue;
              see Head-blocker guard below). Topological order. First live round
              also opens the run journal (reportIssue) and reports pendingCount:
              open, label-matching issues NOT yet eligible, WITH the specific
              tickets blocking them — so a later "drained" report can say why.
  For each eligible issue (FRESH AGENT, no shared memory):
    Coder    →  posts a "Started #N" journal marker first (if reportIssue is on),
                reads issue, then PRE-FLIGHTS the ticket's own verification on
                the untouched tree — if every ticket-specific command already
                passes, the ticket is stale (its feature likely already shipped):
                blocked → parked, never rebuilt. Otherwise plans, implements,
                runs the issue's Required verification + checkCommand (one
                bounded retry per flaky command, disclosed), git diff --check,
                stages. Sees the RUN LEDGER: ≤5 factual lessons from this run's
                earlier rejections.
    Review   →  independent agent re-runs verification on the staged diff,
                then runs two passes no green suite can substitute for:
                PROHIBITIONS (quote every "do not"/"never"/"out of scope"
                statement in the ticket and rule on each — a violation is
                REQUEST_CHANGES no matter how green the checks) and
                SCOPE ADDITIONS (enumerate what the diff adds beyond the
                ticket; creep → findings, in-spirit → surfaced at landing)
                → APPROVE | REQUEST_CHANGES (numbered file:line findings,
                  plus a one-line lesson for the ledger)
                  ↳ coder fixes, re-stages, re-review (max N rounds);
                    the FINAL fix round escalates to reviewer-tier model/effort
                  ↳ exhausted: PARK (skip mode) or stop (halt mode)
    Land     →  commit ("Refs #N" — no auto-close keywords), PUSH
                (ff-only retry once, NEVER merge/rebase), gh issue close with
                SHA + evidence + any reviewer-ruled in-spirit additions (so
                nothing lands unremarked), then a "Landed #N" journal marker (closes out
                the Started marker so this ticket doesn't look dangling).
    Park     →  (blocked tickets, skip mode) stash work, post findings as an
                issue comment, apply `blockedLabel`, post a "Parked #N" journal
                marker, continue to next ticket
    Halt     →  (loop-level stop on THIS ticket, without landing or parking it:
                coder failure, halt-mode block, halt-mode review exhaustion,
                landing failure) post a "⏹️ Halted #N" journal marker closing
                out its "Started" entry — a clean, reported stop, not a crash,
                so the head-blocker guard doesn't misread it on the next resume.
                Distinct from the end-of-run marker below, which reports the
                WHOLE RUN, not one ticket.
  Re-discover if this round landed work and issues remain dep-blocked
  (a landing may have unblocked them). Else done — logged as either "nothing
  pending" or "drained but #A, #B still blocked", never the same message.
End of run → one marker comment on the journal issue, posted even if nothing
             landed or parked: "🔴 Run ended" (finished cleanly) or "⏸ HALTED"
             (stopped mid-run — budget floor, maxTickets, a loop-level failure)
             naming the reason. This comment is the durable external record an
             overnight resume depends on — see Overnight resilience. Reporting
             never affects outcomes.
```

**AFK grinding (`onBlocked: "skip"`, the default):** a blocked ticket never stops the queue. Its work is stashed (recoverable via `git stash list`), the reviewer's findings land on the issue as a comment, and the `blockedLabel` marks it for morning triage. Dependents of a parked ticket stay ineligible automatically (the issue stays open). Loop-level problems still halt — behind-origin, ahead-of-origin, dirty tree, push rejection, or a failed park — because continuing would contaminate every subsequent ticket.

**Head-blocker guard (needs `reportIssue`):** the dangerous failure mode isn't a ticket that parks cleanly — it's one where the session dies mid-ticket and takes the park agent down with it, so the ticket's own issue shows no comment and no `blockedLabel`; it looks untouched and gets served first on every restart, starving the queue. The script has no shell access — only agents call `gh` — so this has to be caught at discovery, and it can only be caught reliably if there is a run journal to read: the coder posts a "Started #N" marker before doing anything else, and land/park/halt each close it out with "Landed #N" / "Parked #N" / "⏹️ Halted #N" (the last one for a clean loop-level stop that neither lands nor parks the ticket — see the Halt row in "Shape of a run"). Discovery treats a "Started" with no matching close as proof a window was already spent on that ticket and parks it as a head-blocker. **Without `reportIssue` enabled, this guard has no journal to read and cannot detect this case** — it falls back to weaker signals (a stash, or a comment on the ticket's own issue) that miss exactly the scenario that matters most, the one where nothing was ever written.

**Attended runs (`onBlocked: "halt"`):** stops at the first blocked ticket with work left staged for inspection — same discipline as a human running one ticket per `/clear`.

**Already-implemented tickets close themselves, with evidence.** When the coder's pre-flight finds the ticket's verification fully green on the untouched tree (or its work proves the feature already present), it returns `no_change_needed` instead of fabricating a no-op diff. The reviewer then independently re-verifies **every acceptance criterion against the current code** — a missed criterion is exactly the gap this hunt exists to catch — and only a confirmed no-change closes the issue, citing the pre-existing commit where identifiable. Stale tickets stop costing rebuild passes without anything closing unverified.

**One writer to `branch`, always.** At `workers: 1` (the default) that is the single tree — the sequential loop above, unchanged. Parallel mode keeps the same invariant by a different route: the serialized Integrate phase is the only writer, and concurrent pushes to `branch` are never allowed.

### Parallel mode (`workers: N`)

The bottleneck in this loop is **model latency, not local CPU** — coders and reviewers spend most of their wall-clock thinking while the test gate is often ~1 core. `workers: N` overlaps those waits. `workers: 1` (default) is the sequential loop above, byte-for-byte.

```
Round:
  Discover  →  as above (same sync gate, lint gate, head-blocker guard)
  Partition →  one cheap agent per ticket predicts its WRITE-SET
  Prep      →  N reusable WORKER SLOTS (git worktrees), each provisioned via
               workerSetupCommand and PROVEN able to run the gate. Once, not per ticket.
  Build     →  WORK-STEALING POOL, not waves. The moment a slot frees it takes the next
               queued ticket whose write-set collides with nothing IN FLIGHT. Queue order
               is preserved; a ticket is skipped only on a real conflict. Unknown
               write-set ⇒ runs ALONE. Nobody fetches, pushes, merges, or touches <branch>.
               Each ticket: coder → reviewer×N (same prohibitions/additions passes) → the
               approved work is COMMITTED to its own wl/<n> branch. Blocked tickets are
               parked in-worker: findings on the issue, label, journal marker — and the
               work PRESERVED as a WIP commit on the ticket branch (worktree slots get
               reset for the next ticket; a branch ref survives that).
  Integrate →  BATCH FIRST: merge every approved branch, run the gate ONCE, push, close
               each issue with evidence (+ any in-spirit additions). On red or conflict ⇒
               back the whole thing out and re-integrate ONE AT A TIME to find the culprit.
               Each fallback merge re-runs the gate; red ⇒ reset --hard, branch preserved,
               journal marker closed out, ticket re-queued against the new base.
```

**Why a pool and not waves.** A wave is a barrier: it ends when its slowest member does, so pairing a 10-minute ticket with a 35-minute one idles a worker for 25 minutes. The pool has no barrier.

**Why the batch merge.** The gate is the expensive *serial* step. Gating after every merge costs N gate runs — Amdahl's law eating the win. Merging all N and gating once costs one, and most batches are green. The one-at-a-time path still exists; it is now the *fallback*, and doubles as the bisect that identifies the culprit.

**Why integration re-verifies at all.** Each branch was built and reviewed against `origin/<branch>` as it stood *before* its siblings landed. Per-branch green is not evidence the *combination* is green — two tickets can each pass alone and break together (a renamed helper, a changed fixture, a tightened assertion). That gate run is the only place the combination is ever tested, and it is what pays for the parallelism. Do not remove it.

### Measure before you parallelise

**Prediction accuracy *is* the parallelism.** One confidently-wrong write-set lets two colliding tickets run together, costing a full coder+reviewer pass — which at width 3 can exceed everything the parallelism saved. Do not guess at it: run once with `shadowFootprints: true`. That runs the ordinary **sequential** loop, predicts each ticket's write-set *before* the coder starts (so the prediction cannot be contaminated by seeing the answer), and scores it against what was actually staged — changing nothing about execution. Read the report:

- **`missed`** — files the ticket really wrote that the prediction omitted. The dangerous half; each one is a collision that would have happened.
- **`extra`** — over-prediction. Costs a little parallelism, nothing else.
- **`safeRate`** — of the predictions you'd actually have scheduled on, the fraction with no miss.

If `safeRate` is not near 1.0, tighten the file lists in the issue bodies (Partition grounds itself in what the issue names) before setting `workers > 1`.

**Sizing.** The reviewer re-runs the gate too, so N workers means up to 2N concurrent gate runs — measure the gate's core usage before going wide. 2–3 is usually the knee. Below ~8–10 queued tickets the setup cost and conflict risk generally exceed the saving: stay at `workers: 1`.

**`workerSetupCommand` is not optional in practice.** A worktree is a checkout, not a copy — no `node_modules`, no virtualenv, no build cache. Symlink them from `$WL_MAIN` into `$WL_WORKSPACE` (e.g. `ln -sfn $WL_MAIN/.venv $WL_WORKSPACE/.venv`). Prep proves a slot can run the gate before any ticket starts; if it can't, the run halts rather than failing every ticket for reasons unrelated to their code.

### Hygiene rules (encoded in the template — do not weaken)

- **Sync before picking**; refuse to act if behind or ahead of the remote, or if the tree is dirty — ahead means a prior land committed without a successful push, and re-serving that ticket would let a later push ship it silently, unreviewed and with its issue never closed.
- **ONE writer to `branch`, always.** Sequentially that's the single tree; in parallel mode it's the serialized Integrate phase. Concurrent pushes to `branch` are never allowed.
- **Push after every commit**; a closed issue must cite a SHA reachable from the remote.
- **Never merge/rebase on push rejection** — ff-only retry once, else stop. Never hand-resolve an integration conflict — a hand-resolved merge has been reviewed by nobody; back it out and re-run the ticket against the new base.
- **In parallel mode, re-run the full gate after every merge.** Per-branch green is never evidence the combination is green.
- **One loop per repo.** Never start a second concurrently. (Parallel mode is *within* one loop — it is not a licence to run two.)
- **Independent review, always**; the reviewer re-runs verification itself and never edits.
- **Prohibitions are enumerated, never assumed** — the reviewer quotes every "do not / never / must not / out of scope" statement in the ticket and rules on each one. Acceptance criteria are executable and get checked by default; prohibitions are prose, and a diff can pass every AC while breaking the sentence that mattered most. A green suite is not a defense.
- **Nothing lands unremarked** — the reviewer enumerates everything the diff adds beyond the ticket's scope. Creep is a finding; an in-spirit addition may land, but it is named in the issue-close comment for human review. Additive scope creep is invisible to every green check; enumeration is the only gate that sees it.
- **Every ticket starts red** — the coder pre-flights the ticket's own verification on the untouched tree. All-green means stale: the ticket is never rebuilt — it routes to `no_change_needed`, where the reviewer independently confirms every acceptance criterion before a verified close (or finds the real gap and sends it back to be implemented). A verification block that passes before the diff exists gates nothing.
- **Parked work is stashed, never discarded**; every park leaves findings on the issue.
- **Flaky retries are bounded and disclosed** — one re-run per failing command, ever; a retry-pass must say "passed on retry — possible flake" so nothing is silently masked (the reviewer re-runs it anyway).
- **Attended is a last resort with a stated reason** — every ticket created without the loop label names the rung it stopped at and what would unblock it. "No CLI exists" is a verified claim, not an assumption; a ticket parked as attended without that reasoning is a defect in the decomposition, not a property of the work.
- **The run ledger stays factual and bounded** — max 5 one-line lessons distilled from actual reviewer findings; never speculation, never project lore (that belongs in `coderNote`).

## Adapting

Keep the four-role spine and the hygiene rules; layer project specifics through args, never by editing the script:

- **`coderNote`** — invariants every coder must know. Example: *"The unit suite builds the schema directly, NOT via migrations — always run the ticket's integration verification too; a NOT NULL column whose writers aren't updated passes unit tests and breaks in prod."*
- **`reviewerAgentType`** — point at a project reviewer subagent that encodes repo rules.
- **`referenceMode` + `referenceNote`** — when per-ticket reference branches exist (e.g. from a prior implementation pass), the coder mines each ticket's branch as a guide; `referenceNote` carries what changed since (refactors, migration renumbering, already-landed schema).
- Front-load invariants into each issue's `## Notes` — the solver reads nothing else.

## Overnight resilience (resuming after usage-limit exhaustion)

A usage window (e.g., an hours-long session limit, or a longer weekly reset) can kill the
session mid-run: agents die, the loop halts, and — because the harness kills the whole
process — the script gets no chance to react. All loop *state* lives in GitHub (labels,
closed issues, stashes), so **any fresh session can resume with the same args**. The open
question is only ever "how does anything find out the run stopped and needs resuming."

**The primary mechanism is the durable marker, not the cron.** Invoke the loop with
`reportIssue: "auto"` so it keeps a journal on the "AFK run log" issue: a start comment
when the run begins, a "Started #N" / "Landed #N" / "Parked #N" / "⏹️ Halted #N" marker around each ticket,
and — critically — an end-of-run comment that fires even when nothing landed: "🔴 Run
ended" if it finished cleanly, or "⏸ HALTED — <reason>" if it stopped mid-run (budget
floor, a loop-level failure, `maxTickets`). That comment is a plain GitHub comment: it
exists whether the session that posted it is still running, asleep, or long gone. Whoever
or whatever checks in next — a human glancing at the issue, a scheduled job, the next
morning's standup — reads one line and knows whether to resume, and with what.

**A cron/scheduled-task relauncher is a convenience layered on top, not a substitute.**
Scheduled tasks inside a session fire only while that session is idle-but-alive; a session
that has ended, or that the runtime has put to sleep, never fires them — **a cron alone is
not a resume mechanism across a multi-day gap.** In one observed run, a loop halted by a
weekly limit reset sat idle roughly nine hours past the reset with no cron ever firing;
what actually resumed it was a person reading the "⏸ HALTED" marker already sitting on the
run-log issue and relaunching by hand. If the runtime offers a scheduled task that keeps
firing regardless of session lifecycle (a real system cron, a hosted scheduler, anything
external to this session), point it at the recipe below; if it doesn't, the marker is still
there for a human (or the next session) to act on — treat that as the expected path, not a
fallback.

If you do have an always-on scheduler available, an hourly, self-canceling task with a
self-contained prompt like this is a reasonable relauncher:

```text
You are the overnight relauncher for a workflow-loop run on OWNER/REPO.
1. LIVENESS: read the newest comments on the open "AFK run log" issue. If the latest
   comment is a "🔴 Run ended" or "⏸ HALTED" marker, the run has already stopped — go to
   step 2. If neither marker is present yet and commits are still landing, exit — the run
   is still alive.
2. DRAINED-BUT-BLOCKED CHECK: read that SAME latest marker's first line, not just its
   presence. If it is a "🔴 Run ended" line containing "resuming will not find new work"
   (the pendingCount > 0 case — every remaining ticket is transitively blocked, not
   finished), do NOT resume: relaunching would re-discover nothing new and repost an
   identical marker, hourly, forever. Instead post a comment on the journal issue —
   "⚠️ Relauncher: queue is transitively blocked (see marker above) — needs human triage,
   not another run." — then DELETE this scheduled task. A human (or a fresh trigger, once
   the blocker is fixed or parked) must re-enable it; go no further.
3. WORK CHECK: gh issue list --repo OWNER/REPO --label <label> --state open,
   excluding issues labeled <blockedLabel>. If none remain, confirm the journal shows a
   "🔴 Run ended" (not "⏸ HALTED") and does NOT match step 2's phrase, then DELETE this
   scheduled task. Done.
4. RESUME: invoke the Workflow tool with <skill path>/assets/workflow-loop.js
   and the ORIGINAL args verbatim, plus autoRecover: true and
   reportIssue: "auto". Do not change any other arg.
```

While the account is rate-limited, a firing simply fails or does nothing — harmless. But
its silence is not informative either way: absence of a resume attempt tells you nothing
about whether the scheduler is still alive to try. The journal marker is what tells you
that. Treat the cron as best-effort automation for the case where the session happens to
stay alive across a short reset, and the marker as the thing that actually has to work.

**Honest caveat:** `autoRecover: true` belongs **only** in restart flows — it stashes a
crashed run's leftovers (`afk-crash-recovery` stash, recoverable) instead of refusing on a
dirty tree. Attended runs keep the strict gate so a human inspects crashed state.

## Failure modes & recovery

- **"cwd origin does not match args.repo"** → the session's working directory is a different checkout than the repo the issues live in — `repo` only feeds `gh`; git acts on the cwd. Launch again from the target repo's checkout.
- **Closed as "no change needed"** → the coder's pre-flight found the ticket's verification already green (or its work proved the feature present), and an independent reviewer confirmed every acceptance criterion against the current code before closing with evidence. Legitimate outcome for stale tickets — but if it happens often, tickets are going stale in the queue: decompose closer to execution.
- **Parked with pre-flight findings** → the ticket's verification was already green but the reviewer could NOT confirm all acceptance criteria (or review was otherwise exhausted). The findings on the issue say which criterion is unmet or why the verification block is too weak to gate the ticket — rewrite it around the real gap, then remove the label.
- **"behind origin" / "ahead of origin" / "dirty tree"** → aborts at the sync gate. "Ahead" usually means a prior land committed but its push failed — inspect with `git log origin/<branch>..HEAD`, then push by hand or reset if abandoned. Fix by hand, re-run (or see *Overnight resilience* for unattended flows).
- **Parked tickets** (skip mode) → triage by label: `gh issue list --label afk-blocked`. Findings are in the issue comments; stashed work via `git stash list`; the run journal issue has the full landed/parked/failed report. Fix or refine the issue, remove the label, re-run.
- **Lint-gate exclusions** → same label and triage path as parks; the comment says exactly which section is missing. Add the verification commands, remove the label, re-run.
- **Head-blocker exclusions** → same label and triage path; the comment says "head-blocker: already consumed a window" plus the evidence (a dangling journal "Started" marker, or the fallback signals). Retry it on its own dedicated window, ideally attended, then remove the label.
- **Coder blocked / review exhausted** (halt mode) → loop stops with the reason; work is **staged, not committed**. Inspect, fix or refine, re-run; closed issues drop out automatically.
- **Landing failed** → always halts (loop-level). Resolve the push problem by hand.
- **"Queue drained" reads as "finished" but isn't** → check `pendingCount`/`blocked` in the result (or the log line right above it). `pendingCount: 0` means genuinely nothing left. `pendingCount > 0` means the remaining tickets are transitively blocked — the result's `blocked` array (and the log line) names which tickets and by what; that is not the same as done, and relaunching won't find new work until the blocker itself lands or is parked.
- **`journalIssue: 0` in the result** → looks like a crash but usually isn't. It only means `reportIssue` was off, or discovery exited before ever reaching the "open the journal" step (e.g. it blocked at the sync gate, or the queue was empty on round 1). Check `reason` for the actual cause; don't treat `journalIssue: 0` alone as a malfunction.
- **Resume** → invoke again (discovery recomputes from GitHub), or `Workflow({scriptPath, resumeFromRunId})` to reuse the prior run's cached agent results (Claude Code; same-session only — on any harness, GitHub state is the durable resume state).

Parallel mode only:

- **Worktree prep failed** → the run halts before any ticket starts (and still posts its end-of-run marker). Usually `workerSetupCommand` didn't provision what the gate needs; fix it and re-run. Nothing was landed; nothing to clean up but the worktrees.
- **Batch merge red** → two individually-green tickets broke in combination. The whole batch was backed out and re-integrated one at a time to find the culprit; the innocent ones land, the culprit's branch is **preserved** and its ticket re-queued. If the same pair keeps colliding, their write-sets were mispredicted — name the shared file in one issue's body so Partition separates them.
- **`conflict` at integration** → merge aborted, branch preserved, journal marker closed out, ticket re-runs against the new base on the next round. Never hand-resolve: a resolved merge has been reviewed by nobody.
- **Leftover worktrees** → `git worktree list`, then `git worktree remove --force <path> && git worktree prune`. Prep also clears stale slot paths before recreating them.
- **Parked parallel tickets** → same triage as sequential parks (findings comment + label + journal marker), but the preserved work is a **WIP commit on the ticket's `wl/<n>` branch**, not a stash — recover with `git log wl/<n>`. The WIP commit is never merged by the loop; integration only merges approved branches.

### What the tree means after a kill — check before you land anything

A killed run leaves a dirty tree, and the same tree state means opposite things depending on which stage died. Pair the run journal (or your harness's agent transcripts) with the table before deciding.

| Which agent died | What the tree holds | Safe action |
|---|---|---|
| **Coder**, mid-work | partial, unstaged, **never reviewed** | Park it (branch or stash, pushed if a branch), relaunch clean. **Do not land it**, however green its own tests are. |
| **Fix round**, after a REQUEST_CHANGES | **staged** = the *rejected* attempt; **unstaged** = a half-written fix on top | Park **both layers as two commits** so the boundary survives. Landing the staged half ships code a review explicitly failed. |
| **Reviewer** | staged, complete, **unreviewed** | Resume so the review actually runs. Do not hand-land. |
| **Land/Integrate**, after an APPROVE | staged or committed, complete, **already approved** | The **only** safe hand-land: re-run the gate yourself, then commit/push/close. No review was skipped — only the mechanical step. |

The trap is pattern-matching "loop died → salvage the staged diff → land it." That is right only in the last row. A gate passing is not evidence the diff is good; that is what the independent review is for.

### `checkCommand` is global, but tickets are not

One `checkCommand` runs for every ticket, so a fast variant chosen for throughput (e.g. skipping slow infra/integration tests) is **blind to whole classes of regression** on the tickets that touch those layers. The loop will not notice; the coder will report green. Either pass the full gate and accept the wall-clock, or state the stronger gate in the affected issue's own `## Required verification` so the coder and reviewer run it for that ticket.

Related: a repo's "authoritative gate" may not cover its own CI. Check for test files the gate's discovery pattern misses and job steps that live outside the test directory entirely. Those gates are invisible locally and red `main` after the merge.

### Watching a live run (Claude Code specifics)

`~/.claude/projects/<project>/<session>/workflows/<runId>.json` **only exists once the run has ended** — a missing file is not a missing run. For a run in progress use `<session>/subagents/workflows/<runId>/journal.jsonl` (one line per agent completion — the milestone stream) and the `agent-*.jsonl` transcripts beside it (newest mtime vs now is the real alive-or-stalled check), plus new commits on `<branch>`. The state file truncates each agent's result to ~400 chars, but `journal.jsonl` stores the complete return value under `result` — mine it before paying for a re-review; a recovered multi-finding verdict can be posted onto the ticket so the next attempt inherits it. On other harnesses, your loop skeleton's own logs play this role.

### Related

`references/prospector.md` — a proposed phase that makes the loop find its own work. The loop verifies tickets, so it cannot find defects no ticket asked about; the prospector files them. Design only, not implemented.
