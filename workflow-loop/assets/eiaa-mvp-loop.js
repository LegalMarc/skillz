// eiaa-mvp-loop — mock-first MVP walking skeleton for exos-legal/review-eiaa.
//
// Differences from the standard workflow-loop.js:
//   - PR-based landing: coder stages on main, land agent creates feature branch,
//     commits, pushes, opens PR ("Closes #N"), merges it, returns to main.
//   - Dedup: discovery excludes issues that already have an open PR referencing them.
//   - Excludes epic #123 and trackers #48/#101 from the eligible set.
//   - Injects mock-boundary and security invariants into every coder prompt.
//   - "pending_gc" outcome: if gh pr merge is blocked (legal-review-required or
//     branch-protection), PR is left open, ticket is marked pending_gc, loop stops.
//   - Coder-note injected from args.coderNote (or default below).

export const meta = {
  name: 'eiaa-mvp-loop',
  description: 'Mock-first MVP skeleton: TDD coder → Opus review → PR-based land',
  phases: [
    { title: 'Discover', detail: 'sync gate + eligible mvp-skeleton issues (deps closed, no open PR)' },
    { title: 'Coder', detail: 'fresh Sonnet per ticket: TDD implement + stage', model: 'sonnet' },
    { title: 'Review', detail: 'independent Opus adversarial review of staged diff', model: 'opus' },
    { title: 'Land', detail: 'feature branch + commit + PR + merge' },
  ],
}

// ─── Config ──────────────────────────────────────────────────────────────────

const A = (typeof args === 'string' ? JSON.parse(args) : args) || {}
const cfg = {
  repo: A.repo || 'exos-legal/review-eiaa',
  label: A.label || 'mvp-skeleton',
  branch: A.branch || 'main',
  checkCommand: A.checkCommand || '',
  setupCommand: A.setupCommand || '',
  coderModel: A.coderModel || 'sonnet',
  reviewerModel: A.reviewerModel || 'opus',
  maxTickets: typeof A.maxTickets === 'number' ? A.maxTickets : 0,
  maxReviewIterations: typeof A.maxReviewIterations === 'number' ? A.maxReviewIterations : 3,
  dryRun: !!A.dryRun,
  // Issues never to treat as workable (epic + trackers)
  excluded: A.excluded || [123, 48, 101],
}

const BUDGET_FLOOR = 80_000
const MAX_ROUNDS = 10

const setupPrefix = cfg.setupCommand ? `First run: ${cfg.setupCommand}\n` : ''
const checkLine = cfg.checkCommand
  ? `Run the full green-gate: ${cfg.checkCommand} — must pass.`
  : "Run whatever gate exists so far (docs-lint if nothing else: python3 scripts/docs-lint.py). If this ticket IS the first gate, verify the gate itself passes on the repo root."

const DEFAULT_CODER_NOTE = `
MOCK BOUNDARY (from epic #123 — mandatory):
The LLM brain is mocked in this slice.
- Issue #59 builds a mock review Lambda: "eiaa" playbook_id → canned REQUEST_CHANGE + pre-baked
  redline; "nda" → MANUAL_REVIEW_REQUIRED "coming soon". Do NOT implement real Bedrock/LLM calls.
- For issue #84: treat the pipeline stages (#80–#83) as satisfied by #59's mock. Do not block on them.
- Read the "MVP scope (epic #123)" comment on each issue for per-issue boundary notes.

SECURITY INVARIANTS (enforce in every ticket):
- Fail-closed auth: any auth failure must DENY, never grant.
- Per-data-class KMS: S3 uploads, redlines, corpus, and audit use separate KMS CMKs.
- Split API role + scoped download auth: separate IAM roles; pre-signed download URLs, short-lived.
- XSS/CSP: frontend sets Content-Security-Policy; no innerHTML with user content.
- Hostile-file AV: uploads scanned before processing.
- Pointer-only payloads: Step Functions inputs hold S3/DDB references — no document content.
- No doc substance in logs: CloudWatch must never log document content, rationales, or PII.
- Watermark: every reviewer output carries a traceability watermark (playbook hash + review_id).

Before implementing: read epic #123 (gh issue view 123 --repo ${cfg.repo} --comments) for the
authoritative build order and any per-issue scope corrections.
`.trim()

const CODER_NOTE = A.coderNote || DEFAULT_CODER_NOTE

// ─── Schemas ─────────────────────────────────────────────────────────────────

const QUEUE_SCHEMA = {
  type: 'object',
  required: ['ok', 'reason', 'tickets', 'pendingCount', 'inFlightCount'],
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    tickets: {
      type: 'array',
      items: {
        type: 'object',
        required: ['number', 'title'],
        properties: {
          number: { type: 'number' },
          title: { type: 'string' },
        },
      },
    },
    pendingCount: {
      type: 'number',
      description: 'open label-matching issues NOT yet eligible (deps still open)',
    },
    inFlightCount: {
      type: 'number',
      description: 'issues skipped because an open PR already references them',
    },
  },
}

const CODER_SCHEMA = {
  type: 'object',
  required: ['status', 'summary', 'files_changed', 'reason'],
  properties: {
    status: { type: 'string', enum: ['staged', 'blocked', 'failed'] },
    summary: { type: 'string', description: 'max 2 sentences' },
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
        'If REQUEST_CHANGES: numbered findings "N. file:line — problem — required change". If APPROVE: one line of evidence.',
    },
  },
}

const LAND_SCHEMA = {
  type: 'object',
  required: ['status', 'commit_sha', 'pr_url', 'reason'],
  properties: {
    status: { type: 'string', enum: ['landed', 'pending_gc', 'failed'] },
    commit_sha: { type: 'string' },
    pr_url: { type: 'string' },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

// ─── Prompts ─────────────────────────────────────────────────────────────────

const DISCOVER_PROMPT = `Sync gate + eligible-issue discovery for the mvp-skeleton build loop.
Repo: ${cfg.repo}   Label: ${cfg.label}   Branch: ${cfg.branch}
Excluded issue numbers (epic + trackers — never workable): ${cfg.excluded.join(', ')}

1. SYNC GATE:
   git fetch origin
   git status --short
   git rev-list --left-right --count origin/${cfg.branch}...HEAD
   - If local is BEHIND (left count > 0) → {ok:false, reason:"behind origin/${cfg.branch}", tickets:[], pendingCount:0, inFlightCount:0}
   - If tree is DIRTY (any non-"??" lines in git status) → {ok:false, reason:"working tree dirty", tickets:[], pendingCount:0, inFlightCount:0}

2. LIST OPEN ISSUES with label ${cfg.label}:
   gh issue list --repo ${cfg.repo} --label ${cfg.label} --state open --json number,title,body,labels --limit 100
   Remove excluded numbers: ${cfg.excluded.join(', ')}
   Also remove any issue labeled "needs-discussion".

3. DEDUP — find issues already referenced by an open PR:
   gh pr list --repo ${cfg.repo} --state open --json number,body --limit 100
   Parse each body for patterns: "Closes #N", "Fixes #N", "Resolves #N" (case-insensitive).
   Collect those issue numbers as the IN_FLIGHT set. Remove them from the candidate list.
   Report count as inFlightCount.

4. CHECK DEPS — for each remaining candidate, parse "## Dependencies", "Blocked by", "needs #N"
   in the issue body. An issue is ELIGIBLE only when ALL referenced deps are CLOSED:
   gh issue view <dep> --repo ${cfg.repo} --json state --jq '.state'
   (Deps in the open candidate set are by definition not closed — no API call needed for those.)
   Count ineligible-due-to-deps as pendingCount.

5. TOPOLOGICAL SORT — order eligible issues by dependency graph (shallowest first). If a cycle
   is detected, exclude the cycle members and mention them in reason.

6. Return:
   {ok:true, reason:"<N> eligible", tickets:[{number,title}...], pendingCount:<N>, inFlightCount:<N>}`

function coderPrompt(ticket) {
  return `You are the CODER in an autonomous build loop. Work ONLY issue #${ticket.number}.
Repo: ${cfg.repo}   Branch: ${cfg.branch}
${setupPrefix}
1. SYNC GATE: git fetch origin && git status --short
   If behind origin/${cfg.branch} → return blocked, reason "behind origin".

2. LOAD TICKET — read the FULL body AND all comments (they carry scope corrections):
   gh issue view ${ticket.number} --repo ${cfg.repo} --comments
   Pay special attention to any comment titled "MVP scope (epic #123)" — it overrides the body.
   You have NO prior context — read whatever repo files you need.

3. PLAN then IMPLEMENT with strict TDD (Red → Green → Guard):
   a. Write the failing test first (Red). Run it — confirm it fails for the right reason.
   b. Implement the minimum to make it pass (Green). Run it again.
   c. Add the guard (regression) test if one is specified in ACs (Guard).
   If the ticket touches more than ~3 files, write a brief plan before editing.
   Follow existing repo conventions; reuse helpers; honor every Note in the issue.
   If ambiguous on a security, privilege, or data-integrity decision → return blocked.

4. VERIFY: run EVERY command in the issue's "Required verification" section and paste its
   real exit status. Do NOT claim "checks pass" without actually running them.
   ${checkLine}
   git diff --check (must be clean).

5. STAGE the complete change set:
   git add <files>
   Confirm: git diff --cached --stat (must match your working tree — no stray/missing files).
   Do NOT commit.

Return status "staged" (summary ≤2 sentences, files_changed list, reason "checks green"),
or "blocked"/"failed" with a 1-sentence reason.

PROJECT NOTE (mandatory — read before staging):
${CODER_NOTE}`
}

function reviewerPrompt(ticket, iter) {
  return `You are an INDEPENDENT, adversarial reviewer. Issue #${ticket.number}, round ${iter}/${cfg.maxReviewIterations}.
Repo: ${cfg.repo}
${setupPrefix}
The coder claims checks pass. Verify everything yourself — do not trust the claim.

1. Read the staged diff:  git diff --cached
2. Read the ticket ACs and all comments: gh issue view ${ticket.number} --repo ${cfg.repo} --comments
3. Re-run EVERY "Required verification" command from the issue yourself.
4. ${checkLine}
5. git diff --check (must be clean).
6. Assess against every AC and the Notes. For security or correctness tickets, the diff MUST
   include the attack/regression test, not only the happy path. Verify the staged set is
   complete (nothing left unstaged that belongs).
7. Check the security invariants from epic #123 that apply to this ticket:
   - Fail-closed auth (any failure → deny)
   - Per-data-class KMS keys where applicable
   - XSS/CSP on frontend changes
   - Pointer-only payloads in Step Functions inputs
   - No doc substance in CloudWatch logs
   - Watermark on reviewer outputs
8. You may NOT edit anything. Findings only.

APPROVE only if you personally ran the verification and it passed. Otherwise REQUEST_CHANGES
with numbered findings: "N. <file>:<line> — <problem> — <required change>".`
}

function fixPrompt(ticket, iter, findings) {
  return `You are the CODER addressing reviewer findings for issue #${ticket.number} (fix round ${iter}).
Repo: ${cfg.repo}
${setupPrefix}
Findings to fix (each exactly; change nothing else):
${findings}

Re-read the ticket if needed: gh issue view ${ticket.number} --repo ${cfg.repo} --comments
Then re-run EVERY "Required verification" command from the issue. ${checkLine}
git diff --check (clean). Re-stage the COMPLETE set: git add <files>; confirm git diff --cached --stat.

Return status "staged" (≤2-sentence summary of what changed) or "failed" (1-sentence reason).

PROJECT NOTE (mandatory):
${CODER_NOTE}`
}

function landPrompt(ticket) {
  return `You are the COMMITTER landing APPROVED issue #${ticket.number}.
Repo: ${cfg.repo}   Target branch: ${cfg.branch}

1. Confirm staged work exists: git diff --cached --stat (must be non-empty).

2. Derive a short slug from the issue title (lowercase, hyphens, ≤40 chars).
   Create a feature branch: git checkout -b issue-${ticket.number}-<slug>

3. Commit — match the subject style of recent commits (git log --oneline -5):
   git commit -m "<imperative subject line>"
   The commit body should reference: Refs #${ticket.number}
   (Use "Refs" not "Closes" — the PR body carries the closing keyword.)

4. Push the feature branch:
   git push -u origin issue-${ticket.number}-<slug>

5. Get the commit SHA: git rev-parse --short HEAD

6. Open a PR:
   gh pr create --repo ${cfg.repo} \\
     --title "<same subject line>" \\
     --body "<summary bullets>\\n\\nCloses #${ticket.number}\\n\\n**Red→Green→Guard evidence:** <paste real verification output, max 20 lines>\\n\\n**Reviewer verdict:** APPROVED by independent Opus reviewer."
   Capture the PR URL and number from gh output.

7. Attempt to merge the PR:
   gh pr merge <pr_number> --repo ${cfg.repo} --merge
   - If merge succeeds: return status "landed".
   - If merge is BLOCKED (required review, legal-review-required label, or branch protection):
     Leave the PR open. Return status "pending_gc" with the pr_url and the blocking reason.
   - If merge fails for other reasons: return status "failed" with the reason.

8. After a successful merge, return to the base branch:
   git checkout ${cfg.branch}
   git pull

Return {status:"landed"|"pending_gc"|"failed", commit_sha:"<sha>", pr_url:"<url>", reason:"<1 sentence>"}.`
}

// ─── Main loop ────────────────────────────────────────────────────────────────

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
    haltReason = 'discovery agent terminated'
    break
  }
  if (!discovery.ok) {
    log(`BLOCKED at discovery: ${discovery.reason}`)
    return { done: false, reason: discovery.reason, completed }
  }

  const queue = discovery.tickets.filter((t) => !attempted.has(t.number))
  if (queue.length === 0) {
    log(round === 1
      ? `No eligible tickets. Pending: ${discovery.pendingCount}, In-flight: ${discovery.inFlightCount}.`
      : `No newly eligible tickets — queue drained.`)
    break
  }
  log(`Round ${round}: ${queue.map((t) => '#' + t.number).join(', ')} eligible (${discovery.pendingCount} pending deps, ${discovery.inFlightCount} in-flight PRs)`)

  if (cfg.dryRun) {
    log('dryRun — reporting queue without changes.')
    return { done: true, dryRun: true, eligible: queue, pendingCount: discovery.pendingCount, inFlightCount: discovery.inFlightCount, completed: [] }
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
      haltReason = `token budget nearly exhausted (${Math.round(budget.remaining() / 1000)}k left)`
      break
    }

    attempted.add(ticket.number)
    log(`\n=== #${ticket.number}: ${ticket.title} ===`)

    // ── Coder ────────────────────────────────────────────────────────────────
    const coded = await agent(coderPrompt(ticket), {
      schema: CODER_SCHEMA,
      model: cfg.coderModel,
      label: `coder-${ticket.number}`,
      phase: 'Coder',
    })

    if (!coded || coded.status !== 'staged') {
      const status = coded ? coded.status : 'failed'
      const reason = coded ? coded.reason : 'coder agent terminated'
      log(`Coder ${status} on #${ticket.number}: ${reason}`)
      completed.push({ ticket: ticket.number, status, commit_sha: '', pr_url: '', reason })
      halted = true
      haltReason = `#${ticket.number} ${status}: ${reason}`
      break
    }
    log(`Staged: ${coded.summary} (${coded.files_changed.length} file(s))`)

    // ── Review loop ──────────────────────────────────────────────────────────
    let approved = false
    let lastFindings = ''
    let reviewRounds = 0

    for (let iter = 1; iter <= cfg.maxReviewIterations; iter++) {
      reviewRounds = iter
      const reviewed = await agent(reviewerPrompt(ticket, iter), {
        model: cfg.reviewerModel,
        schema: REVIEWER_SCHEMA,
        label: `review-${ticket.number}-i${iter}`,
        phase: 'Review',
      })

      if (!reviewed) {
        lastFindings = 'reviewer agent terminated'
        break
      }
      lastFindings = reviewed.findings

      if (reviewed.verdict === 'APPROVE') {
        approved = true
        log(`APPROVED (iter ${iter}): ${reviewed.findings.slice(0, 120)}`)
        break
      }
      log(`REQUEST_CHANGES (iter ${iter}): ${reviewed.findings.slice(0, 160)}`)
      if (iter === cfg.maxReviewIterations) break

      const fixed = await agent(fixPrompt(ticket, iter, reviewed.findings), {
        schema: CODER_SCHEMA,
        model: cfg.coderModel,
        label: `fix-${ticket.number}-i${iter}`,
        phase: 'Coder',
      })

      if (!fixed || fixed.status !== 'staged') {
        lastFindings = `fix round ${iter} ${fixed ? 'failed: ' + fixed.reason : 'terminated'}; findings: ${lastFindings}`
        break
      }
      log(`Re-staged (fix ${iter}): ${fixed.summary}`)
    }

    if (!approved) {
      const reason = `not approved after ${reviewRounds} round(s): ${lastFindings.slice(0, 240)}`
      log(`STOP — ${reason} (work left STAGED, not committed)`)
      // Label the issue needs-discussion so it's skipped on re-run
      await agent(
        `Add the label "needs-discussion" to issue #${ticket.number} on repo ${cfg.repo} using: gh issue edit ${ticket.number} --repo ${cfg.repo} --add-label needs-discussion`,
        { model: cfg.coderModel, label: `label-needs-discussion-${ticket.number}`, phase: 'Land' }
      )
      completed.push({ ticket: ticket.number, status: 'blocked', commit_sha: '', pr_url: '', reason })
      halted = true
      haltReason = reason
      break
    }

    // ── Land ─────────────────────────────────────────────────────────────────
    const landed = await agent(landPrompt(ticket), {
      schema: LAND_SCHEMA,
      model: cfg.coderModel,
      label: `land-${ticket.number}`,
      phase: 'Land',
    })

    if (!landed || landed.status === 'failed') {
      const reason = landed ? landed.reason : 'land agent terminated'
      log(`Landing FAILED for #${ticket.number}: ${reason}`)
      completed.push({ ticket: ticket.number, status: 'failed', commit_sha: landed?.commit_sha || '', pr_url: landed?.pr_url || '', reason })
      halted = true
      haltReason = `landing failed: ${reason}`
      break
    }

    if (landed.status === 'pending_gc') {
      log(`#${ticket.number} → PR open, pending GC sign-off: ${landed.pr_url} — ${landed.reason}`)
      completed.push({ ticket: ticket.number, status: 'pending_gc', commit_sha: landed.commit_sha, pr_url: landed.pr_url, reason: landed.reason })
      halted = true
      haltReason = `#${ticket.number} pending GC sign-off — subsequent deps blocked until PR is merged`
      break
    }

    // landed
    completed.push({ ticket: ticket.number, status: 'landed', commit_sha: landed.commit_sha, pr_url: landed.pr_url, reviewRounds, reason: 'merged' })
    landedTotal++
    landedThisRound++
    log(`#${ticket.number} landed @ ${landed.commit_sha} — ${landed.pr_url}`)
  }

  // Re-discover only if we landed something and deps might now be unblocked
  if (!halted && !(landedThisRound > 0 && discovery.pendingCount > 0)) break
}

const allLanded = completed.length > 0 && completed.every((r) => r.status === 'landed')
log(`\nDone. ${landedTotal}/${completed.length} ticket(s) landed.${haltReason ? ' Halt: ' + haltReason : ''}`)
return { done: allLanded, landed: landedTotal, reason: haltReason || 'queue drained', completed }
