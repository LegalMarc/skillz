// workflow-loop — autonomous ticket solver with clean context per ticket.
//
// Repo-agnostic AND model-agnostic. Drive it entirely through `args`; do not edit
// this file per project. Full arg documentation lives in ../SKILL.md (single source
// of truth) — the summary below is a reminder, not the spec.
//
//   args: {
//     repo: "OWNER/REPO",             // required
//     label: "afk",                   // issue label marking loop work
//     branch: "main",
//     checkCommand: "bash scripts/check.sh",
//     setupCommand: "",               // prepended to each agent shell
//     coderModel: "",                 // "" = inherit session model (recommended)
//     coderEffort: "high",
//     reviewerAgentType: "general-purpose",
//     reviewerModel: "",              // "" = inherit session model (recommended)
//     reviewerEffort: "xhigh",
//     onBlocked: "skip",              // "skip" = park & continue (AFK); "halt" = stop at first block
//     blockedLabel: "afk-blocked",    // label applied to parked tickets
//     reportIssue: 0,                 // 0 = off; "auto" = create/reuse "AFK run log" issue; or an issue number
//     autoRecover: false,             // restart flows ONLY: stash a crashed run's dirty tree and proceed
//     commitPrefix: "",
//     maxTickets: 0,                  // 0 = all eligible
//     maxReviewIterations: 3,
//     coderNote: "",                  // project invariants injected into every coder prompt
//     referenceMode: false,           // mine per-ticket reference branches (adapt, don't copy)
//     referenceNote: "",              // project-specific guidance for referenceMode
//     dryRun: false
//   }
//
// Design invariants (do not weaken):
// - Sequential by design: one shared tree, one branch. Parallel lands invite merge races.
// - Push must succeed before an issue is closed. Never merge/rebase on push rejection.
// - The reviewer never edits; findings go back to a coder agent.
// - Parked work is stashed, never discarded; every park leaves findings on the issue.

export const meta = {
  name: 'workflow-loop',
  description: 'Decompose-then-solve loop: per-ticket clean-context coder → independent reviewer → land; parks blocked tickets and grinds on',
  phases: [
    { title: 'Discover', detail: 'sync gate + eligible issues (deps closed); re-checked after lands' },
    { title: 'Coder', detail: 'fresh agent per ticket: implement + verify + stage' },
    { title: 'Review', detail: 'independent adversarial review of the staged diff' },
    { title: 'Land', detail: 'commit + push + close issue with evidence' },
    { title: 'Park', detail: 'stash blocked work, post findings to the issue, label for triage' },
  ],
}

// ─── Config ──────────────────────────────────────────────────────────────────

// args may arrive as a JSON string when invoked via XML parameter format
const A = (typeof args === 'string' ? JSON.parse(args) : args) || {}
const cfg = {
  repo: A.repo || '',
  label: A.label || 'afk',
  branch: A.branch || 'main',
  checkCommand: A.checkCommand || '',
  setupCommand: A.setupCommand || '',
  // Model-agnostic defaults: empty model = inherit the session model. Differentiate the
  // roles by EFFORT (reviewer thinks harder than the coder). Set explicit models only
  // when the runtime offers a genuinely cheaper tier for the coder.
  coderModel: A.coderModel || '',
  coderEffort: A.coderEffort || 'high',
  reviewerAgentType: A.reviewerAgentType || 'general-purpose',
  reviewerModel: A.reviewerModel || '',
  reviewerEffort: A.reviewerEffort || 'xhigh',
  onBlocked: A.onBlocked === 'halt' ? 'halt' : 'skip',
  blockedLabel: A.blockedLabel || 'afk-blocked',
  // Run journal + end-of-run report target: 0 = off, "auto" = create/reuse an issue
  // titled "AFK run log", or an explicit issue number.
  reportIssue: A.reportIssue === 'auto' ? 'auto' : typeof A.reportIssue === 'number' ? A.reportIssue : 0,
  // Unattended-restart mode: a dirty tree at discovery is stashed (afk-crash-recovery)
  // and the run proceeds, instead of refusing. Set ONLY by auto-restart flows; attended
  // runs keep the strict gate so a human inspects crashed state.
  autoRecover: !!A.autoRecover,
  commitPrefix: A.commitPrefix || '',
  maxTickets: typeof A.maxTickets === 'number' ? A.maxTickets : 0,
  maxReviewIterations: typeof A.maxReviewIterations === 'number' ? A.maxReviewIterations : 3,
  dryRun: !!A.dryRun,
  // Free-text note injected verbatim into every coder and fix-round prompt.
  // Use for project-specific invariants the coder must know (framework blind spots,
  // registration steps, migration numbering rules — see SKILL.md for examples).
  coderNote: A.coderNote || '',
  // When true, the coder mines a per-ticket reference branch (matched by the ticket's
  // bracketed id, e.g. [ABC-004] → glob *abc-004-*) to adapt rather than re-derive.
  referenceMode: !!A.referenceMode,
  // Project-specific guidance appended to the reference instructions (what refactors
  // postdate the reference branches, what to modernize, known collisions).
  referenceNote: A.referenceNote || '',
}

if (!cfg.repo) {
  log('ERROR: args.repo is required (e.g. "OWNER/REPO"). Aborting.')
  return { done: false, reason: 'missing args.repo', completed: [] }
}

// Stop cleanly between tickets when a token target is set and nearly spent.
// A full ticket (code+review+land) rarely fits in less than this.
const BUDGET_FLOOR = 80_000
// Runaway backstop for re-discovery rounds.
const MAX_ROUNDS = 10

const setupPrefix = cfg.setupCommand ? `First run: ${cfg.setupCommand}\n` : ''
const checkLine = cfg.checkCommand
  ? `Run the full green-gate: ${cfg.checkCommand} — must pass.`
  : "Run the repo's full test+lint gate — must pass."

// Per-role agent options. Model is included only when explicitly configured —
// omitted means the agent inherits the session model (the model-agnostic default).
const coderOpts = (extra) => ({
  ...(cfg.coderModel ? { model: cfg.coderModel } : {}),
  effort: cfg.coderEffort,
  ...extra,
})
const reviewerOpts = (extra) => ({
  agentType: cfg.reviewerAgentType,
  ...(cfg.reviewerModel ? { model: cfg.reviewerModel } : {}),
  effort: cfg.reviewerEffort,
  ...extra,
})
// Discovery, landing, and parking are mechanical git/gh work — medium effort suffices.
const mechanicalOpts = (extra) => ({
  ...(cfg.coderModel ? { model: cfg.coderModel } : {}),
  effort: 'medium',
  ...extra,
})
// FINAL fix round only: the strongest configuration the run knows — one max-strength
// attempt at the cliff edge before parking is where extra tokens pay best. If no
// reviewerModel is set, omit the model entirely (inherit the session model, presumed
// strongest) rather than keeping a deliberately cheaper coderModel.
const escalatedOpts = (extra) => ({
  ...(cfg.reviewerModel ? { model: cfg.reviewerModel } : {}),
  effort: cfg.reviewerEffort,
  ...extra,
})

// ─── Schemas ─────────────────────────────────────────────────────────────────

const QUEUE_SCHEMA = {
  type: 'object',
  required: ['ok', 'reason', 'tickets', 'malformed', 'pendingCount'],
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
    malformed: {
      type: 'array',
      description: 'eligible issues excluded by the lint gate (already commented + labeled); empty array if none',
      items: {
        type: 'object',
        required: ['number', 'why'],
        properties: {
          number: { type: 'number' },
          why: { type: 'string' },
        },
      },
    },
    pendingCount: {
      type: 'number',
      description: 'open label-matching issues NOT yet eligible (deps still open)',
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
  required: ['verdict', 'findings', 'lesson'],
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'REQUEST_CHANGES'] },
    findings: {
      type: 'string',
      description:
        'If REQUEST_CHANGES: numbered findings, each "N. <file>:<line> — <problem> — <required change>". If APPROVE: one line of evidence.',
    },
    lesson: {
      type: 'string',
      description:
        'REQUEST_CHANGES only: ONE factual sentence a future coder in THIS repo should know to avoid this class of finding (e.g. "when a migration tightens a constraint, update every writer of that table"). Empty string on APPROVE or when the finding is purely ticket-specific.',
    },
  },
}

const LAND_SCHEMA = {
  type: 'object',
  required: ['status', 'commit_sha', 'reason'],
  properties: {
    status: { type: 'string', enum: ['landed', 'failed'] },
    commit_sha: { type: 'string' },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

const PARK_SCHEMA = {
  type: 'object',
  required: ['status', 'reason'],
  properties: {
    status: { type: 'string', enum: ['parked', 'failed'] },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

const JOURNAL_SCHEMA = {
  type: 'object',
  required: ['status', 'issue', 'reason'],
  properties: {
    status: { type: 'string', enum: ['ok', 'failed'] },
    issue: { type: 'number', description: 'the journal issue number (0 if failed)' },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

// ─── Run ledger ──────────────────────────────────────────────────────────────
// Cross-ticket lessons distilled from reviewer findings. Bounded and factual:
// the run learns repo-specific failure classes while each ticket stays
// otherwise clean-context. FIFO, max 5 one-liners.

const lessons = []
const LEDGER_MAX = 5
const recordLesson = (lesson) => {
  const l = (lesson || '').trim()
  if (!l) return
  if (lessons.includes(l)) return
  lessons.push(l)
  while (lessons.length > LEDGER_MAX) lessons.shift()
}
const lessonsBlock = () =>
  lessons.length
    ? `\nRUN LEDGER — independent reviewers in THIS run rejected earlier tickets for the following; do not repeat these mistakes:\n${lessons.map((l, i) => `${i + 1}. ${l}`).join('\n')}\n`
    : ''

// One bounded re-run per failing verification command; a retry-pass must be disclosed.
const FLAKY_RULE = `FLAKY-RETRY RULE: if a verification command fails, re-run THAT command exactly once.
   If it passes on the retry, continue — but you MUST disclose "passed on retry — possible
   flake" for that command in your summary. Never retry twice: two failures = a real failure.`

// ─── Prompts ─────────────────────────────────────────────────────────────────

// dryRun must be strictly read-only: no stashing, no comments, no labels.
const dirtyTreePolicy = cfg.autoRecover && !cfg.dryRun
  ? `   - If the tree is dirty (has non-"??" lines): this is an UNATTENDED RESTART (autoRecover on).
     Preserve the crashed run's leftovers, then proceed:
     git stash push -u -m "afk-crash-recovery"
     Confirm the tree is clean afterwards (git status --short: no non-"??" lines). If the stash
     fails or the tree stays dirty →
     {ok:false, reason:"autoRecover stash failed — human inspection needed", tickets:[], malformed:[], pendingCount:0}`
  : `   - If the tree is dirty (has non-"??" lines) →
     {ok:false, reason:"working tree dirty (possibly a crashed prior run) — inspect git status, then commit/stash/reset by hand", tickets:[], malformed:[], pendingCount:0}`

const DISCOVER_PROMPT = `Sync gate and eligibility discovery for an autonomous build loop.
Repo: ${cfg.repo}   Loop label: ${cfg.label}   Branch: ${cfg.branch}

1. SYNC GATE:
   git fetch origin
   git status --short
   git rev-list --left-right --count origin/${cfg.branch}...HEAD
   - If local is BEHIND origin/${cfg.branch} (left count > 0) →
     {ok:false, reason:"local behind origin/${cfg.branch} — fast-forward first", tickets:[], malformed:[], pendingCount:0}
   - Tree is DIRTY if git status --short contains any lines NOT starting with "??" (i.e., staged
     changes, modified tracked files, deletions, renames). Untracked-only lines ("?? ...") are safe
     to ignore and do NOT make the tree dirty.
${dirtyTreePolicy}

2. LIST OPEN ISSUES:
   gh issue list --repo ${cfg.repo} --label ${cfg.label} --state open --json number,title,body,labels --limit 100
   EXCLUDE any issue carrying the label "${cfg.blockedLabel}" — those are parked for human triage.
   Parse each body's "## Dependencies" / "Blocked by" / "needs #N" references.
   An issue is ELIGIBLE only when EVERY referenced dependency is CLOSED — verify with:
   gh issue view <dep> --repo ${cfg.repo} --json state
   (Dependencies on issues in the open set are by definition not closed — no API call needed.)

3. LINT each eligible issue before admitting it to the queue — an issue that cannot
   self-verify wastes a full coder+reviewer cycle, so it must not enter the loop:
   - the body has a non-empty "## Required verification" section whose entries look like
     runnable commands (reject prose placeholders like "add tests later");
   - its dependency references parse ("None" or "#N" forms).
${cfg.dryRun
    ? `   DRY RUN — read-only: EXCLUDE each malformed issue from the queue and report it in
   malformed, but do NOT comment, do NOT label, do NOT change anything on GitHub.`
    : `   For each malformed issue: post a comment naming exactly what is missing
   (gh issue comment <n> --repo ${cfg.repo} --body "..."), apply the "${cfg.blockedLabel}"
   label (create it first if needed; ignore an already-exists error), and EXCLUDE it
   from the queue. Report it in malformed.`}

4. ORDER the remaining eligible issues topologically (dependencies first). If you detect
   a dependency cycle, exclude the cycle members and mention it in reason.

5. Return {ok:true, reason:"<N> eligible", tickets:[{number,title}...],
   malformed:[{number, why}...] (empty array if none),
   pendingCount:<open label-matching issues that are NOT eligible>}`

// When referenceMode is on, derive the ticket's bracketed id (e.g. "[ABC-004]" → "abc-004")
// and tell the coder to mine the matching reference branch's tip commit as a guide to adapt.
function referenceSection(ticket) {
  if (!cfg.referenceMode) return ''
  const m = ticket.title.match(/\[([A-Za-z]+-\d+)\]/)
  if (!m) return ''
  const id = m[1].toLowerCase()
  const glob = `*${id}-*`
  return `
2b. REFERENCE IMPLEMENTATION — use this; it is the main accelerator for this loop:
   A prior implementation of THIS EXACT ticket may exist on a reference branch.
   - Find it:  git branch -a --list "${glob}"
   - Its per-ticket diff is that branch's TIP commit: git show <branch> — read the WHOLE commit.
   - ADAPT, never blind-copy: the reference predates later work on ${cfg.branch}, so modernize
     its wiring to CURRENT branch conventions (current helper names, current dependency seams),
     and re-derive anything that collides with state that already landed (migration numbers,
     schema already present, files earlier tickets already handled).
   - COMPLETENESS — the #1 failure mode: list the reference's full changed-file set
     (git show --name-only <branch>) and account for EVERY file — skip what earlier tickets
     already landed, port what remains. If the reference tightens a constraint (e.g. makes a
     column NOT NULL), you MUST port every WRITER it updated too — a partial copy that adds
     constraints without updating writers passes unit tests and breaks in production.
   - The independent reviewer WILL reject stale pre-refactor patterns and unjustified test-
     assertion changes. Integrate cleanly; the reference is a guide, not a paste source.
${cfg.referenceNote ? `   PROJECT REFERENCE NOTES:\n${cfg.referenceNote}\n` : ''}`
}

function coderPrompt(ticket) {
  return `You are the CODER in an autonomous build loop. Work ONLY issue #${ticket.number}.
Repo: ${cfg.repo}   Branch: ${cfg.branch}
${setupPrefix}
1. SYNC GATE: git fetch origin && git status --short
   - If behind origin/${cfg.branch} → return blocked, reason "behind origin".

2. LOAD TICKET (read the FULL body AND all comments; "## Correction"/"## Notes" sections and
   any "Implementation guidance" comments are authoritative):
   gh issue view ${ticket.number} --repo ${cfg.repo} --comments
   You have NO context beyond this issue — read whatever code you need from the repo.
${referenceSection(ticket)}
3. PLAN, then IMPLEMENT. Before editing, decide the change set; if it spans more than ~3
   files, write the plan out first, then execute it. Follow existing repo conventions,
   reuse helpers, honor every constraint in the issue Notes (security invariants, refs).
   If the ticket is ambiguous on a load-bearing decision (security, privilege,
   data integrity) → return blocked with the ambiguity. Do NOT guess.
${lessonsBlock()}
4. VERIFY: run EVERY command in the issue's "Required verification" section AND PASTE its
   real exit status. Do NOT claim "checks pass" for a command you did not actually run.
   ${checkLine}
   If the ticket lists BOTH unit and integration verification, run BOTH — unit suites often
   bypass the layer your change constrains (migrations, infra, external seams), so passing
   units alone proves nothing about that layer.
   ${FLAKY_RULE}
   git diff --check (must be clean).

5. STAGE the complete change set: git add <files>; confirm git diff --cached --stat
   matches the working tree exactly (no stray or missing files).

Return status "staged" (summary ≤2 sentences, files_changed, reason "checks green"),
or "blocked"/"failed" with a 1-sentence reason. Do not commit.
${cfg.coderNote ? `\nPROJECT NOTE (mandatory — read before staging):\n${cfg.coderNote}` : ''}`
}

function reviewerPrompt(ticket, iter) {
  return `You are an INDEPENDENT, adversarial reviewer. Issue #${ticket.number}, iteration ${iter}/${cfg.maxReviewIterations}.
Repo: ${cfg.repo}
${setupPrefix}
The coder claims its checks pass. Do not trust the claim — verify everything yourself.

1. Read the staged diff: git diff --cached
2. Re-read the ticket's acceptance criteria AND comments: gh issue view ${ticket.number} --repo ${cfg.repo} --comments
3. Re-run the ticket's "Required verification" commands yourself.
   ${FLAKY_RULE}
   If the coder disclosed a "passed on retry" flake, re-run that command yourself with
   extra attention — two independent retry-passes may be a flake; a failure is real.
4. ${checkLine}
5. git diff --check (clean).
6. Judge against acceptance criteria and the issue Notes' invariants. For security or
   correctness tickets, the diff must include the attack/regression test, not just the
   happy path. Check the staged set is complete (nothing left unstaged that belongs).
7. You may NOT edit anything. Findings only.

APPROVE only if you personally ran the verification and it passed (retry-passes disclosed
in your evidence line). Otherwise REQUEST_CHANGES with numbered findings:
"N. <file>:<line> — <problem> — <required change>". When you REQUEST_CHANGES, also fill
"lesson": one factual sentence a future coder in this repo should know to avoid this CLASS
of mistake — empty string if the finding is purely ticket-specific.`
}

function fixPrompt(ticket, iter, findings) {
  return `You are the CODER addressing review findings for issue #${ticket.number} (fix round ${iter}).
Repo: ${cfg.repo}
${setupPrefix}
Findings (fix each exactly; change nothing else):
${findings}
${cfg.referenceMode ? 'If useful, the reference branch for this ticket (see git branch -a) shows how the original handled this — adapt, do not blind-copy.\n' : ''}${lessonsBlock()}
Then re-run the ticket's "Required verification" commands (gh issue view ${ticket.number} --repo ${cfg.repo} if needed). ${checkLine}
${FLAKY_RULE}
git diff --check (clean). Re-stage the COMPLETE set: git add <files>; confirm git diff --cached --stat.

Return status "staged" with a ≤2-sentence summary of what changed, or "failed" with a 1-sentence reason. Do not commit.
${cfg.coderNote ? `\nPROJECT NOTE (mandatory — read before staging):\n${cfg.coderNote}` : ''}`
}

function landPrompt(ticket) {
  const prefixHint = cfg.commitPrefix
    ? `Use the commit-subject prefix convention "${cfg.commitPrefix}".`
    : 'Match the subject PREFIX convention of recent commits (git log --oneline -5), e.g. "fix(scope): ...".'
  return `You are the COMMITTER landing APPROVED issue #${ticket.number}: "${ticket.title}".
Repo: ${cfg.repo}   Branch: ${cfg.branch}
${setupPrefix}
1. Confirm staged work exists: git diff --cached --stat (non-empty).
2. Read the real change: git diff --cached. Derive the subject from what THIS diff does
   plus the ticket title above — never copy or lightly reword a recent commit's subject.
   ${prefixHint} Match prior commits' FORMAT only, never their wording: back-to-back
   tickets can touch identical files with unrelated fixes, and reusing a prior subject
   has silently mislabeled commits before (code + "Refs #N" stay correct; only the
   human-readable subject goes stale and misdescribes the diff).
3. Commit with a trailer that references WITHOUT auto-closing (no "closes/fixes" keywords —
   the explicit close below carries the evidence):
   git commit -m "<imperative subject>" -m "Refs #${ticket.number}"
4. PUSH — must succeed BEFORE the issue is closed:
   git push
   If rejected: git pull --ff-only && git push (once). If it still fails, do NOT merge or
   rebase — return failed with the rejection message.
5. SHA: git rev-parse --short HEAD
6. Close with evidence (if gh says it is already closed, treat that as success):
   gh issue close ${ticket.number} --repo ${cfg.repo} \\
     --comment "Implemented in <sha>. Review approved (independent reviewer). Acceptance criteria: all passed — <one-line evidence>."

Return {status:"landed", commit_sha:"<sha>"} or {status:"failed", commit_sha:"", reason:"..."}.`
}

function parkPrompt(ticket, why) {
  return `You are PARKING blocked issue #${ticket.number} so an autonomous loop can continue past it.
Repo: ${cfg.repo}
${setupPrefix}
Why it is blocked:
${why}

1. PRESERVE any in-progress work — never discard it:
   git status --short
   If there are ANY staged or unstaged changes (including new files):
   git stash push -u -m "${cfg.blockedLabel} #${ticket.number}"
   Then confirm the tree is clean: git status --short must show no non-"??" lines.
   If stashing fails or the tree is still dirty, return status "failed" — the loop must halt
   rather than contaminate the next ticket.
2. POST the block reason to the issue so a human can triage asynchronously:
   gh issue comment ${ticket.number} --repo ${cfg.repo} --body "<the block reason above, verbatim,
   prefixed with: 'Autonomous loop parked this ticket.' and — if work was stashed — the stash
   message to recover it: git stash list | grep '#${ticket.number}'>"
3. LABEL it (create the label first; ignore an 'already exists' error):
   gh label create ${cfg.blockedLabel} --repo ${cfg.repo} --color D93F0B --description "parked by autonomous loop" 2>/dev/null; true
   gh issue edit ${ticket.number} --repo ${cfg.repo} --add-label ${cfg.blockedLabel}

Return {status:"parked", reason:"<1 sentence>"} or {status:"failed", reason:"<why parking failed>"}.`
}

function journalStartPrompt() {
  return `You are opening the RUN JOURNAL for an autonomous build loop that is starting now.
Repo: ${cfg.repo}   Journal setting: ${cfg.reportIssue}
${setupPrefix}
1. Resolve the journal issue:
   ${typeof cfg.reportIssue === 'number' && cfg.reportIssue > 0
     ? `Use issue #${cfg.reportIssue}.`
     : `Find an OPEN issue titled exactly "AFK run log":
   gh issue list --repo ${cfg.repo} --search "AFK run log in:title" --state open --json number,title
   If none exists, create it:
   gh issue create --repo ${cfg.repo} --title "AFK run log" --body "Journal for autonomous workflow-loop runs. Each run posts a start comment and an end-of-run report here."`}
2. Post the start comment (get the timestamp from: date -u):
   gh issue comment <issue> --repo ${cfg.repo} --body "🟢 Run started <UTC timestamp>. Label: ${cfg.label} · branch: ${cfg.branch} · onBlocked: ${cfg.onBlocked}."

Return {status:"ok", issue:<number>, reason:""} or {status:"failed", issue:0, reason:"<1 sentence>"}.`
}

function reportPrompt(journalIssue, resultLines) {
  return `You are posting the END-OF-RUN report for an autonomous build loop.
Repo: ${cfg.repo}   Journal issue: #${journalIssue}
${setupPrefix}
Post ONE comment on issue #${journalIssue} (get the timestamp from: date -u) containing,
as GitHub markdown:
- First line: "🔴 Run ended <UTC timestamp>."
- Then a results table with columns: Ticket | Outcome | Detail. One row per line below.
  For landed rows the detail is the short SHA (verify against git log if useful);
  for parked rows, the one-line reason plus "findings on the ticket".

Results:
${resultLines}

Return {status:"ok", issue:${journalIssue}, reason:""} or {status:"failed", issue:0, reason:"<1 sentence>"}.`
}

// ─── Park helper: preserve work, annotate issue, keep the loop grinding ──────

async function park(ticket, why, completed) {
  const parked = await agent(parkPrompt(ticket, why), {
    ...mechanicalOpts({ label: `park-${ticket.number}`, phase: 'Park' }),
    schema: PARK_SCHEMA,
  })
  if (!parked || parked.status !== 'parked') {
    const reason = parked ? parked.reason : 'park agent terminated (skipped or API error)'
    completed.push({ ticket: ticket.number, status: 'failed', commit_sha: '', reason: `park failed: ${reason}` })
    return { ok: false, reason: `parking #${ticket.number} failed (${reason}) — halting to avoid contaminating the next ticket` }
  }
  completed.push({ ticket: ticket.number, status: 'parked', commit_sha: '', reason: why.slice(0, 240) })
  log(`#${ticket.number} PARKED (${cfg.blockedLabel}) — findings posted to the issue; loop continues`)
  return { ok: true }
}

// ─── Main loop: discover → (code → review×N → land | park)* → re-discover ───

const completed = []
const attempted = new Set()
let landedTotal = 0
let parkedTotal = 0
let halted = false
let haltReason = ''
let journalIssue = 0

for (let round = 1; round <= MAX_ROUNDS && !halted; round++) {
  phase('Discover')
  const discovery = await agent(DISCOVER_PROMPT, {
    ...mechanicalOpts({ label: round === 1 ? 'discover' : `discover-r${round}`, phase: 'Discover' }),
    schema: QUEUE_SCHEMA,
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
    log(round === 1 ? 'No eligible tickets.' : 'No newly eligible tickets — queue drained.')
    break
  }
  log(`Round ${round} eligible: ${queue.map((t) => '#' + t.number).join(', ')} (${discovery.pendingCount} still blocked on deps)`)
  if (discovery.malformed && discovery.malformed.length) {
    log(`Lint gate excluded ${discovery.malformed.length} issue(s): ${discovery.malformed.map((m) => `#${m.number} (${m.why})`).join('; ')}${cfg.dryRun ? ' (dryRun — reported only, nothing touched)' : ` — commented + labeled ${cfg.blockedLabel}`}`)
  }

  if (cfg.dryRun) {
    log('dryRun — reporting queue without changing anything.')
    return { done: true, dryRun: true, eligible: queue, malformed: discovery.malformed || [], pendingCount: discovery.pendingCount, completed: [] }
  }

  for (const m of discovery.malformed || []) {
    if (!attempted.has(m.number)) {
      attempted.add(m.number)
      completed.push({ ticket: m.number, status: 'parked', commit_sha: '', reason: `lint gate: ${m.why}` })
      parkedTotal++
    }
  }

  // Open the run journal once, on the first live round with work to do.
  if (cfg.reportIssue && !journalIssue) {
    const opened = await agent(journalStartPrompt(), {
      ...mechanicalOpts({ label: 'journal-start', phase: 'Discover' }),
      schema: JOURNAL_SCHEMA,
    })
    if (opened && opened.status === 'ok' && opened.issue > 0) {
      journalIssue = opened.issue
      log(`Run journal: issue #${journalIssue}`)
    } else {
      // Reporting must never affect outcomes — note it and grind on.
      log(`Journal unavailable (${opened ? opened.reason : 'agent terminated'}) — continuing without it.`)
    }
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

    // ── Coder ────────────────────────────────────────────────────────────────
    const coded = await agent(coderPrompt(ticket), {
      ...coderOpts({ label: `coder-${ticket.number}`, phase: 'Coder' }),
      schema: CODER_SCHEMA,
    })

    if (!coded || coded.status !== 'staged') {
      const status = coded ? coded.status : 'failed'
      const reason = coded ? coded.reason : 'coder agent terminated (skipped or API error)'
      log(`Coder ${status} on #${ticket.number}: ${reason}`)
      // Sync problems are loop-level: every subsequent ticket hits the same wall.
      const loopLevel = /behind origin|dirty tree/i.test(reason)
      if (cfg.onBlocked === 'skip' && !loopLevel) {
        const res = await park(ticket, `Coder ${status}: ${reason}`, completed)
        if (!res.ok) { halted = true; haltReason = res.reason; break }
        parkedTotal++
        continue
      }
      completed.push({ ticket: ticket.number, status, commit_sha: '', reason })
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
        ...reviewerOpts({ label: `review-${ticket.number}-i${iter}`, phase: 'Review' }),
        schema: REVIEWER_SCHEMA,
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
      recordLesson(reviewed.lesson)
      log(`REQUEST_CHANGES (iter ${iter}): ${reviewed.findings.slice(0, 160)}`)
      if (iter === cfg.maxReviewIterations) break

      // The FINAL fix round escalates to the strongest configuration the run knows —
      // one max-strength attempt before parking.
      const isFinalFixRound = iter === cfg.maxReviewIterations - 1
      if (isFinalFixRound) log(`Final fix round for #${ticket.number} — escalating to reviewer-tier model/effort`)
      const fixAgentOpts = isFinalFixRound ? escalatedOpts : coderOpts
      const fixed = await agent(fixPrompt(ticket, iter, reviewed.findings), {
        ...fixAgentOpts({ label: `fix-${ticket.number}-i${iter}${isFinalFixRound ? '-esc' : ''}`, phase: 'Coder' }),
        schema: CODER_SCHEMA,
      })

      if (!fixed || fixed.status !== 'staged') {
        lastFindings = `fix round ${iter} ${fixed ? 'failed: ' + fixed.reason : 'terminated'}; outstanding findings: ${lastFindings}`
        break
      }
      log(`Re-staged: ${fixed.summary}`)
    }

    if (!approved) {
      const why = `Review not approved after ${reviewRounds} round(s). Outstanding findings:\n${lastFindings}`
      if (cfg.onBlocked === 'skip') {
        const res = await park(ticket, why, completed)
        if (!res.ok) { halted = true; haltReason = res.reason; break }
        parkedTotal++
        continue
      }
      const reason = `review not approved after ${reviewRounds} round(s): ${lastFindings.slice(0, 240)}`
      log(`STOP — ${reason} (work left STAGED, not committed)`)
      completed.push({ ticket: ticket.number, status: 'blocked', commit_sha: '', reason })
      halted = true
      haltReason = reason
      break
    }

    // ── Land ─────────────────────────────────────────────────────────────────
    const landed = await agent(landPrompt(ticket), {
      ...mechanicalOpts({ label: `land-${ticket.number}`, phase: 'Land' }),
      schema: LAND_SCHEMA,
    })

    if (!landed || landed.status !== 'landed') {
      // Landing failures are loop-level (push rejection, remote drift) — always halt.
      const reason = landed ? landed.reason : 'land agent terminated (skipped or API error)'
      log(`Landing FAILED for #${ticket.number}: ${reason}`)
      completed.push({ ticket: ticket.number, status: 'failed', commit_sha: '', reason })
      halted = true
      haltReason = `landing failed: ${reason}`
      break
    }

    completed.push({
      ticket: ticket.number,
      status: 'landed',
      commit_sha: landed.commit_sha,
      reviewRounds,
      reason: landed.reason,
    })
    landedTotal++
    landedThisRound++
    log(`#${ticket.number} landed @ ${landed.commit_sha}`)
  }

  // Re-discover only when this round landed something AND issues remain blocked
  // on deps — a land may have unblocked them. Otherwise we're done.
  if (!halted && !(landedThisRound > 0 && discovery.pendingCount > 0)) break
}

const failed = completed.filter((r) => r.status !== 'landed' && r.status !== 'parked').length
log(`\nDone. ${landedTotal} landed, ${parkedTotal} parked (${cfg.blockedLabel}), ${failed} failed, of ${completed.length} attempted.${haltReason ? ' Halt: ' + haltReason : ''}`)

// End-of-run report — pure reporting, after all state changes; failure is logged, never fatal.
if (journalIssue && completed.length > 0) {
  const resultLines = completed
    .map((r) => `#${r.ticket} | ${r.status} | ${r.status === 'landed' ? r.commit_sha : (r.reason || '').slice(0, 160)}`)
    .join('\n')
  const reported = await agent(reportPrompt(journalIssue, resultLines), {
    ...mechanicalOpts({ label: 'run-report', phase: 'Land' }),
    schema: JOURNAL_SCHEMA,
  })
  if (!reported || reported.status !== 'ok') {
    log(`Run report could not be posted (${reported ? reported.reason : 'agent terminated'}) — results above are still authoritative.`)
  } else {
    log(`Run report posted to issue #${journalIssue}.`)
  }
}

return {
  done: completed.length > 0 && failed === 0 && !halted,
  landed: landedTotal,
  parked: parkedTotal,
  failed,
  journalIssue,
  reason: haltReason || (parkedTotal > 0 ? `queue drained; ${parkedTotal} ticket(s) parked for triage under label "${cfg.blockedLabel}"` : 'queue drained'),
  completed,
}
