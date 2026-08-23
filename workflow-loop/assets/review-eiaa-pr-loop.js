// review-eiaa-pr-loop — autonomous ticket solver that lands via PR + CI + auto-merge.
//
// Adapted from workflow-loop.js for the review-eiaa repo, where merges go through a PR
// (so the path-filtered CI gate-workflows run) instead of committing straight to main.
// Sequential by design: one issue at a time, branch -> PR -> review -> wait CI -> merge ->
// re-discover. Closing an issue (via "Closes #N" on merge) unblocks its dependents, so a
// single run can cross all phase boundaries until only human-gated work remains.
//
//   Workflow({
//     scriptPath: ".../workflow-loop/assets/review-eiaa-pr-loop.js",
//     args: {
//       repo: "exos-legal/review-eiaa",
//       label: "afk",                 // curated safe-set (excludes legal/spike/gate/tracker)
//       branch: "main",
//       checkCommand: "...",          // full local governance gate (see CHECK_CMD default)
//       setupCommand: "",             // prepended to each agent shell (or "")
//       planIssue: 101,               // master build plan, read for stage/wave ordering
//       coderModel: "sonnet",
//       reviewerAgentType: "general-purpose",
//       reviewerModel: "opus",
//       mergeMethod: "squash",        // squash | merge | rebase
//       ciTimeoutMins: 20,            // how long the land step waits for PR checks
//       maxTickets: 0,                // 0 = all eligible
//       maxReviewIterations: 3,
//       dryRun: false                 // true = report the eligible queue, change nothing
//     }
//   })
//
// MUST be invoked from a Claude session rooted in the review-eiaa checkout — the agents'
// git/python commands run in the session's working directory.
//
// Invariants (do not weaken):
// - Sequential: one branch in flight at a time; the next coder branches from a freshly
//   synced main AFTER the prior PR merges. No parallel lands -> no merge races.
// - The PR must MERGE (and the issue close) before a dependent ticket is eligible.
// - The reviewer never edits; findings go back to a coder agent.
// - Protected paths are off-limits to the coder (legal-owned content).

export const meta = {
  name: 'review-eiaa-pr-loop',
  description: 'review-eiaa afk loop: per-ticket clean-context coder -> Opus review -> PR -> CI -> auto-merge',
  phases: [
    { title: 'Discover', detail: 'sync gate + eligible afk issues (deps closed), #101-ordered' },
    { title: 'Coder', detail: 'fresh agent per ticket: TDD branch + push + open PR', model: 'sonnet' },
    { title: 'Review', detail: 'independent adversarial review of the PR branch', model: 'opus' },
    { title: 'Land', detail: 'wait for PR CI, squash-merge (closes issue), sync main' },
  ],
}

// ─── Config ──────────────────────────────────────────────────────────────────

const A = (typeof args === 'string' ? JSON.parse(args) : args) || {}
const cfg = {
  repo: A.repo || 'exos-legal/review-eiaa',
  repoPath: A.repoPath || '/Users/marcmandel/Documents/dev/review-eiaa',
  label: A.label || 'afk',
  branch: A.branch || 'main',
  setupCommand: A.setupCommand || '',
  planIssue: typeof A.planIssue === 'number' ? A.planIssue : 101,
  coderModel: A.coderModel || 'sonnet',
  reviewerAgentType: A.reviewerAgentType || 'general-purpose',
  reviewerModel: A.reviewerModel || 'opus',
  mergeMethod: A.mergeMethod || 'squash',
  ciTimeoutMins: typeof A.ciTimeoutMins === 'number' ? A.ciTimeoutMins : 20,
  maxTickets: typeof A.maxTickets === 'number' ? A.maxTickets : 0,
  maxReviewIterations: typeof A.maxReviewIterations === 'number' ? A.maxReviewIterations : 3,
  dryRun: !!A.dryRun,
}

if (!cfg.repo) {
  log('ERROR: args.repo is required. Aborting.')
  return { done: false, reason: 'missing args.repo', completed: [] }
}

// review-eiaa has no single green-gate command; the gate is the set of standalone CI scripts.
const CHECK_CMD =
  A.checkCommand ||
  'python3 scripts/docs-lint.py && for t in tests/test_*.py tests/*/test_*.py tests/lint-*.py; do echo ">> $t"; python3 "$t" || exit 1; done'

const BUDGET_FLOOR = 90_000
const MAX_ROUNDS = 12
const setupPrefix = cfg.setupCommand ? `First run: ${cfg.setupCommand}\n` : ''
// Bare `git` commands (unlike `gh ... --repo`) depend on the shell's cwd already being the
// clone — the ambient cwd is NOT guaranteed to be this repo. Every prompt below MUST start
// with this cd, on its own line, before any git command. Do not drop this on adaptation.
const CD_CMD = `cd ${cfg.repoPath}`

// Repo-specific invariants the cold solver must honor (from the established build-loop prompt).
const PROTECTED = `PROTECTED PATHS — never modify under an afk (non-legal) ticket: playbooks/, prompts/,
standard-forms/, model-policy/, and any gold-set expected values (tests/gold-fixtures/**).
These are legal-owned. If a ticket seems to require touching them, return blocked.`

const GATE_NOTE = `GREEN-GATE for this repo = the governance/lint scripts, run as standalone programs
(there is no single "make test"). Authoritative command:
  ${CHECK_CMD}
Every script must exit 0. If one fails with ModuleNotFoundError, pip install the dep
(e.g. \`pip install jsonschema\`) and re-run — do NOT skip it. The issue's own "## TDD plan" /
acceptance tests are the PRIMARY gate; this full gate is the regression backstop.`

// ─── Schemas ─────────────────────────────────────────────────────────────────

const QUEUE_SCHEMA = {
  type: 'object',
  required: ['ok', 'reason', 'tickets', 'pendingCount'],
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    tickets: {
      type: 'array',
      items: {
        type: 'object',
        required: ['number', 'title'],
        properties: { number: { type: 'number' }, title: { type: 'string' } },
      },
    },
    pendingCount: { type: 'number', description: 'open afk issues NOT yet eligible (deps still open)' },
  },
}

const CODER_SCHEMA = {
  type: 'object',
  required: ['status', 'summary', 'pr_number', 'branch', 'reason'],
  properties: {
    status: { type: 'string', enum: ['pr_open', 'blocked', 'failed'] },
    summary: { type: 'string', description: 'max 2 sentences' },
    pr_number: { type: 'number', description: '0 if none opened' },
    branch: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

const REVIEWER_SCHEMA = {
  type: 'object',
  required: ['verdict', 'findings'],
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'REQUEST_CHANGES'] },
    findings: {
      type: 'string',
      description:
        'If REQUEST_CHANGES: numbered findings "N. <file>:<line> — <problem> — <required change>". If APPROVE: one line of evidence.',
    },
  },
}

const LAND_SCHEMA = {
  type: 'object',
  required: ['status', 'merge_sha', 'reason'],
  properties: {
    status: { type: 'string', enum: ['merged', 'failed'] },
    merge_sha: { type: 'string' },
    ci: { type: 'string', description: 'short note on what CI checks ran (or "none triggered")' },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

// ─── Prompts ─────────────────────────────────────────────────────────────────

const DISCOVER_PROMPT = `Sync gate + eligibility discovery for an autonomous PR-based build loop.
Repo: ${cfg.repo}   Loop label: ${cfg.label}   Branch: ${cfg.branch}

0. FIRST COMMAND, before anything else: ${CD_CMD}
   All git commands below assume this cwd. If it fails (no such directory), STOP and return
   {ok:false, reason:"repoPath ${cfg.repoPath} not found — resolve by hand", tickets:[], pendingCount:0}.

1. SYNC GATE:
   git fetch origin
   git checkout ${cfg.branch} && git pull --ff-only
   git status --short
   git rev-list --left-right --count origin/${cfg.branch}...HEAD
   - If still BEHIND origin/${cfg.branch} after the pull (left count > 0) →
     {ok:false, reason:"behind origin/${cfg.branch}; resolve by hand", tickets:[], pendingCount:0}
   - Tree is DIRTY only if git status --short has lines NOT starting with "??" (untracked-only is fine).
     If dirty → {ok:false, reason:"working tree dirty — inspect/commit/stash by hand", tickets:[], pendingCount:0}

2. LIST CANDIDATES:
   gh issue list --repo ${cfg.repo} --label ${cfg.label} --state open --json number,title,body --limit 200
   These are the curated safe-set (legal-review-required / spikes / trackers are already excluded).

3. PARSE DEPENDENCIES for each issue. This repo records deps on a "**Depends on:** #A, #B; <prose>" line
   (also honor "## Dependencies", "Blocked by", "needs #N"). For PROSE deps like "the pipeline stages
   (extraction/primary/critic/redline)", resolve them to issue numbers using the master build plan:
   gh issue view ${cfg.planIssue} --repo ${cfg.repo}   (stage A→G + within-stage wave ordering).
   An issue is ELIGIBLE only when EVERY resolved numbered dependency is CLOSED:
   gh issue view <dep> --repo ${cfg.repo} --json state   (deps still in the open afk set are NOT closed).
   If a dep is an issue OUTSIDE the afk set that is still OPEN (e.g. a legal-review-required or gate issue),
   the ticket is NOT eligible — it is blocked on human-gated work; count it in pendingCount.
   If a prose dep cannot be confidently resolved, treat the ticket as NOT eligible (conservative).

4. ORDER eligible issues by ${cfg.planIssue}'s stage/wave order, dependencies first. Exclude any dependency
   cycle and mention it in reason.

5. Return {ok:true, reason:"<N> eligible", tickets:[{number,title}...], pendingCount:<open afk issues not eligible>}`

function coderPrompt(ticket) {
  return `You are the CODER in an autonomous PR-based build loop. Work ONLY issue #${ticket.number}.
Repo: ${cfg.repo}   Base branch: ${cfg.branch}
${setupPrefix}
0. FIRST COMMAND, before anything else: ${CD_CMD}
   Every git command below assumes this cwd — do not run git from anywhere else.

1. START CLEAN: git checkout ${cfg.branch} && git pull --ff-only
   git checkout -b issue-${ticket.number}-<short-slug>

2. LOAD TICKET — read the FULL body AND all comments; the "## TDD plan", "## Acceptance criteria",
   "Read first:" list, and any "Reconciliation with the 2026-06-11 architecture review" section are
   authoritative (a reconciliation section SUPERSEDES conflicting acceptance criteria above it):
   gh issue view ${ticket.number} --repo ${cfg.repo} --comments
   Read every file in the issue's "Read first" / "Docs touched" list before writing anything.
   You have NO context beyond this issue — read whatever code/docs you need.

3. IMPLEMENT with strict TDD in commit order:
   (1) RED: commit the failing test/artifact first; run it; capture its FAILING output.
   (2) GREEN: implement until it passes.
   (3) GUARD: wire the test into CI where the issue says so.
   Follow existing repo conventions, reuse helpers, honor every constraint in the issue.
   If the ticket is ambiguous on a load-bearing decision (security, privilege, data integrity, an
   authority/approval gate) → return blocked with the ambiguity. Do NOT guess.
   ${PROTECTED}

4. VERIFY — paste real exit statuses, do not claim a check you did not run:
   - Run EVERY command in the issue's TDD plan / acceptance section.
   - Run the full repo gate: ${CHECK_CMD}
   - git diff --check (must be clean).
   ${GATE_NOTE}

5. OPEN THE PR (do NOT merge):
   git push -u origin HEAD
   gh pr create --repo ${cfg.repo} --base ${cfg.branch} --head issue-${ticket.number}-<slug> \\
     --title "<imperative subject>" \\
     --body "Closes #${ticket.number}.<newline>Red→Green→Guard: <red test name + its failing output>, <green summary>, <guard wired where>.<newline>Local gate: green."
   The body MUST contain "Closes #${ticket.number}" so the merge closes the issue.

Return status "pr_open" with pr_number, branch, files_changed, summary (≤2 sentences), reason "checks green".
Return "blocked"/"failed" (pr_number 0) with a 1-sentence reason otherwise. Do NOT merge.`
}

function reviewerPrompt(ticket, pr, iter) {
  return `You are an INDEPENDENT, adversarial reviewer. Issue #${ticket.number}, PR #${pr}, iteration ${iter}/${cfg.maxReviewIterations}.
Repo: ${cfg.repo}
${setupPrefix}
0. FIRST COMMAND, before anything else: ${CD_CMD}
   Every git command below assumes this cwd — do not run git from anywhere else.

The coder claims its checks pass and opened PR #${pr}. Do not trust the claim — verify yourself.

1. Check out the PR branch fresh: git fetch origin && gh pr checkout ${pr} --repo ${cfg.repo}
2. Read the diff vs ${cfg.branch}: git diff ${cfg.branch}...HEAD
3. Re-read acceptance criteria AND comments: gh issue view ${ticket.number} --repo ${cfg.repo} --comments
4. TDD integrity: check out the RED commit, confirm the test FAILS there; confirm it PASSES at branch HEAD.
   A red artifact that never failed, or a test weakened to pass, is an automatic REQUEST_CHANGES.
5. Re-run the issue's verification commands AND the full repo gate: ${CHECK_CMD}
6. git diff --check (clean). Confirm no PROTECTED path was touched (playbooks/, prompts/, standard-forms/,
   model-policy/, gold-set values) unless the issue explicitly authorized it.
7. Judge against acceptance criteria + the cited docs (ARCHITECTURE.md, playbook-governance.md,
   output-contract.md, data-handling.md as applicable) + security invariants (no document substance in
   logs or Step Functions payloads; fail-closed paths intact; no new authority paths around
   activation/approval gates). For security/correctness tickets the diff MUST include the attack/regression
   test, not just the happy path.
8. You may NOT edit anything. Findings only.

APPROVE only if you personally ran the verification and it passed. Otherwise REQUEST_CHANGES with numbered,
file:line findings.`
}

function fixPrompt(ticket, pr, iter, findings) {
  return `You are the CODER addressing review findings for issue #${ticket.number}, PR #${pr} (fix round ${iter}).
Repo: ${cfg.repo}
${setupPrefix}
0. FIRST COMMAND, before anything else: ${CD_CMD}
   Every git command below assumes this cwd — do not run git from anywhere else.

Make sure you are on the PR branch: git fetch origin && gh pr checkout ${pr} --repo ${cfg.repo}
Findings (fix each exactly; change nothing else):
${findings}

Then re-run the issue's verification commands AND the full repo gate: ${CHECK_CMD}
git diff --check (clean). ${PROTECTED}
Commit the fixes and push to the SAME branch so the PR updates: git push
Return status "pr_open" (same pr_number ${pr}, branch) with a ≤2-sentence summary of what changed,
or "failed" with a 1-sentence reason. Do NOT merge.`
}

function landPrompt(ticket, pr, branch) {
  return `You are the LANDER for APPROVED issue #${ticket.number}, PR #${pr} (branch ${branch}).
Repo: ${cfg.repo}   Base: ${cfg.branch}
${setupPrefix}
0. FIRST COMMAND, before anything else: ${CD_CMD}
   Every git command below assumes this cwd — do not run git from anywhere else.

1. WAIT FOR CI. This repo's CI is path-filtered, so a PR may trigger few or zero checks:
   gh pr checks ${pr} --repo ${cfg.repo} --watch --interval 30
   (it polls until checks finish). Allow up to ${cfg.ciTimeoutMins} minutes.
   - If any check FAILS → return {status:"failed", merge_sha:"", ci:"<which failed>", reason:"CI red"}.
   - If it reports "no checks reported" / none are triggered → that is EXPECTED for changes outside the
     watched paths; proceed on the strength of the independent Opus approval + the green local gate.
2. MERGE (this closes the issue via the PR's "Closes #${ticket.number}"):
   gh pr merge ${pr} --repo ${cfg.repo} --${cfg.mergeMethod} --delete-branch
   If merge is rejected because the base moved, the loop is sequential so this is unexpected:
   do NOT force; return failed with the message.
3. SYNC local main for the next ticket: git checkout ${cfg.branch} && git pull --ff-only
4. CONFIRM the issue closed: gh issue view ${ticket.number} --repo ${cfg.repo} --json state,closedAt
   (if still open, run: gh issue close ${ticket.number} --repo ${cfg.repo} --reason completed).
5. SHA: git rev-parse --short HEAD

Return {status:"merged", merge_sha:"<sha>", ci:"<note>"} or {status:"failed", merge_sha:"", reason:"..."}.`
}

// ─── Main loop ─────────────────────────────────────────────────────────────

const completed = []
const attempted = new Set()
let landedTotal = 0
let halted = false
let haltReason = ''

for (let round = 1; round <= MAX_ROUNDS && !halted; round++) {
  phase('Discover')
  const discovery = await agent(DISCOVER_PROMPT, {
    schema: QUEUE_SCHEMA,
    model: cfg.coderModel,
    label: round === 1 ? 'discover' : `discover-r${round}`,
    phase: 'Discover',
  })

  if (!discovery) {
    haltReason = 'discovery agent terminated (skipped or API error)'
    break
  }
  if (!discovery.ok) {
    log(`BLOCKED at discovery: ${discovery.reason}`)
    return { done: false, reason: discovery.reason, completed }
  }

  const queue = discovery.tickets.filter((t) => !attempted.has(t.number))
  if (queue.length === 0) {
    log(round === 1 ? 'No eligible afk tickets.' : 'No newly eligible tickets — queue drained.')
    break
  }
  log(`Round ${round} eligible: ${queue.map((t) => '#' + t.number).join(', ')} (${discovery.pendingCount} still blocked — incl. human-gated deps)`)

  if (cfg.dryRun) {
    log('dryRun — reporting queue without changing anything.')
    return { done: true, dryRun: true, eligible: queue, pendingCount: discovery.pendingCount, completed: [] }
  }

  let landedThisRound = 0

  for (const ticket of queue) {
    if (cfg.maxTickets > 0 && landedTotal >= cfg.maxTickets) {
      halted = true
      haltReason = `maxTickets (${cfg.maxTickets}) reached`
      break
    }
    if (budget.total && budget.remaining() < BUDGET_FLOOR) {
      halted = true
      haltReason = `token budget nearly exhausted (${Math.round(budget.remaining() / 1000)}k left) — stopped cleanly between tickets`
      break
    }

    attempted.add(ticket.number)
    log(`\n=== #${ticket.number}: ${ticket.title} ===`)

    // ── Coder: branch + implement + push + open PR ───────────────────────────
    const coded = await agent(coderPrompt(ticket), {
      schema: CODER_SCHEMA,
      model: cfg.coderModel,
      label: `coder-${ticket.number}`,
      phase: 'Coder',
    })

    if (!coded || coded.status !== 'pr_open' || !coded.pr_number) {
      const status = coded ? coded.status : 'failed'
      const reason = coded ? coded.reason : 'coder agent terminated (skipped or API error)'
      log(`Coder ${status} on #${ticket.number}: ${reason}`)
      completed.push({ ticket: ticket.number, status, pr: 0, reason })
      halted = true
      haltReason = `#${ticket.number} ${status}: ${reason}`
      break
    }
    const pr = coded.pr_number
    const branch = coded.branch
    log(`PR #${pr} opened: ${coded.summary}`)

    // ── Review loop ──────────────────────────────────────────────────────────
    let approved = false
    let lastFindings = ''
    let reviewRounds = 0

    for (let iter = 1; iter <= cfg.maxReviewIterations; iter++) {
      reviewRounds = iter
      const reviewed = await agent(reviewerPrompt(ticket, pr, iter), {
        agentType: cfg.reviewerAgentType,
        model: cfg.reviewerModel,
        schema: REVIEWER_SCHEMA,
        label: `review-${ticket.number}-i${iter}`,
        phase: 'Review',
      })

      if (!reviewed) {
        lastFindings = 'reviewer agent terminated (skipped or API error)'
        break
      }
      lastFindings = reviewed.findings

      if (reviewed.verdict === 'APPROVE') {
        approved = true
        log(`APPROVED (iter ${iter})`)
        break
      }
      log(`REQUEST_CHANGES (iter ${iter}): ${reviewed.findings.slice(0, 160)}`)
      if (iter === cfg.maxReviewIterations) break

      const fixed = await agent(fixPrompt(ticket, pr, iter, reviewed.findings), {
        schema: CODER_SCHEMA,
        model: cfg.coderModel,
        label: `fix-${ticket.number}-i${iter}`,
        phase: 'Coder',
      })

      if (!fixed || fixed.status !== 'pr_open') {
        lastFindings = `fix round ${iter} ${fixed ? 'failed: ' + fixed.reason : 'terminated'}; outstanding: ${lastFindings}`
        break
      }
      log(`Re-pushed fixes: ${fixed.summary}`)
    }

    if (!approved) {
      const reason = `review not approved after ${reviewRounds} round(s): ${lastFindings.slice(0, 240)}`
      log(`STOP — ${reason} (PR #${pr} left OPEN for inspection)`)
      completed.push({ ticket: ticket.number, status: 'blocked', pr, reason })
      halted = true
      haltReason = reason
      break
    }

    // ── Land: wait CI + merge + sync ───────────────────────────────────────────
    const landed = await agent(landPrompt(ticket, pr, branch), {
      schema: LAND_SCHEMA,
      model: cfg.coderModel,
      label: `land-${ticket.number}`,
      phase: 'Land',
    })

    if (!landed || landed.status !== 'merged') {
      const reason = landed ? landed.reason : 'land agent terminated (skipped or API error)'
      log(`Landing FAILED for #${ticket.number} (PR #${pr}): ${reason}`)
      completed.push({ ticket: ticket.number, status: 'failed', pr, reason })
      halted = true
      haltReason = `landing failed on #${ticket.number}: ${reason}`
      break
    }

    completed.push({
      ticket: ticket.number,
      status: 'merged',
      pr,
      merge_sha: landed.merge_sha,
      reviewRounds,
      ci: landed.ci || '',
    })
    landedTotal++
    landedThisRound++
    log(`#${ticket.number} merged @ ${landed.merge_sha} (PR #${pr}; CI: ${landed.ci || 'n/a'})`)
  }

  // Re-discover only if this round merged something AND issues remain blocked on deps.
  if (!halted && !(landedThisRound > 0 && discovery.pendingCount > 0)) break
}

const allMerged = completed.length > 0 && completed.every((r) => r.status === 'merged')
log(`\nDone. ${landedTotal}/${completed.length} ticket(s) merged.${haltReason ? ' Halt: ' + haltReason : ''}`)
return { done: allMerged, merged: landedTotal, reason: haltReason || 'queue drained', completed }
