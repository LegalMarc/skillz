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
//     dryRun: false,
//     priority: [],                   // issue numbers to prefer first (tie-break only)
//
//     // ── Parallel mode (opt-in; 1 = the sequential loop, unchanged) ──
//     workers: 1,                     // tickets coded+reviewed CONCURRENTLY
//     workerSetupCommand: "",         // provision each worktree ($WL_MAIN, $WL_WORKSPACE)
//     worktreeRoot: "",               // default: ../.wl-worktrees
//     branchPrefix: "wl",             // per-ticket branches: wl/<issue>
//     shadowFootprints: false         // sequential run that MEASURES write-set prediction
//   }
//
// Design invariants (do not weaken):
// - ONE writer to `branch`, always. Sequentially that is the single tree; in parallel
//   mode it is the serialized Integrate phase. Concurrent pushes to `branch` are never
//   allowed.
// - Push must succeed before an issue is closed. Never merge/rebase on push rejection.
// - The reviewer never edits; findings go back to a coder agent.
// - Parked work is preserved, never discarded — stashed (sequential) or committed to the
//   ticket's own branch (parallel); every park leaves findings on the issue.
// - In parallel mode the gate is re-run on `branch` after EVERY merge. Per-branch green is
//   not evidence the combination is green — that is the whole risk parallelism introduces,
//   and re-verifying at integration is the only thing that pays for it.
//
// WHEN PARALLEL IS WORTH IT
// The bottleneck in this loop is model latency, not local CPU: coders and reviewers spend
// most of their wall-clock thinking, while the test gate is often ~1 core. Overlapping
// those waits is a real win. But it costs a worktree per worker (each needs its build deps
// provisioned), and the reviewer re-runs the gate, so W workers means up to 2W concurrent
// gate runs — measure the gate's core usage before going wide. 2-3 is usually the knee.
// Below ~8-10 queued tickets the setup cost and conflict risk generally exceed the saving;
// keep workers: 1. Run shadowFootprints over one queue first — prediction accuracy IS the
// parallelism, and one confidently-wrong footprint costs a full coder+reviewer pass.

export const meta = {
  name: 'workflow-loop',
  description: 'Decompose-then-solve loop: per-ticket clean-context coder → independent reviewer → land; parks blocked tickets and grinds on',
  phases: [
    { title: 'Discover', detail: 'sync gate + eligible issues (deps closed); re-checked after lands' },
    { title: 'Coder', detail: 'fresh agent per ticket: implement + verify + stage' },
    { title: 'Review', detail: 'independent adversarial review of the staged diff' },
    { title: 'Land', detail: 'commit + push + close issue with evidence' },
    { title: 'Park', detail: 'stash blocked work, post findings to the issue, label for triage' },
    // Parallel mode only (workers > 1); unused phases simply never appear.
    { title: 'Partition', detail: 'predict each ticket write-set, pack conflict-free dispatch' },
    { title: 'Prep', detail: 'one git worktree per worker slot, gate-capable' },
    { title: 'Build', detail: 'code + review W tickets concurrently, each sandboxed' },
    { title: 'Integrate', detail: 'serialized merge into the branch, full gate after EACH' },
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
  // Shell snippet that PRINTS a GitHub token for the account this run must act as
  // (e.g. "gh auth token --user SOMEUSER"). Needed whenever the ambient `gh` account
  // differs from the repo's account: env vars set by setupCommand do NOT survive to
  // the next tool call (each Bash invocation is a fresh shell), so every `gh` command
  // this script emits is prefixed inline with GH_TOKEN=$(...) instead of relying on
  // a prior export. Leave empty to use the ambient gh account unchanged.
  ghAuthCmd: A.ghAuthCmd || '',
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

  // Issue numbers to prefer at the FRONT of the eligible queue, in this order.
  // A tie-break within the topological order only — never overrides dependencies.
  priority: Array.isArray(A.priority) ? A.priority : [],

  // ── Parallel mode ─────────────────────────────────────────────────────────
  // How many tickets to code+review CONCURRENTLY. 1 (default) is the sequential
  // loop, unchanged: one tree, one branch, land in place. >1 gives each ticket
  // its OWN git worktree and branch; nothing touches `branch` until a SERIALIZED
  // integration phase merges the approved branches, re-running the gate per merge.
  workers: Math.max(1, typeof A.workers === 'number' ? A.workers : 1),
  // Run inside each fresh worktree before any verification (symlink node_modules,
  // .venv, etc.). Worktrees are checkouts, NOT copies — they have no build deps.
  // Receives $WL_MAIN (the primary checkout) and $WL_WORKSPACE (this worktree).
  workerSetupCommand: A.workerSetupCommand || '',
  // Where worktrees live. Default: a sibling of the primary checkout, so the
  // repo's own ignore rules and file-watchers never see them.
  worktreeRoot: A.worktreeRoot || '',
  // Branch-name prefix for per-ticket branches in parallel mode.
  branchPrefix: A.branchPrefix || 'wl',
  // SHADOW MODE. Runs the ordinary SEQUENTIAL loop, but predicts each ticket's
  // write-set first and scores the prediction against what the coder actually
  // staged. Changes nothing about execution — it answers "is footprint prediction
  // accurate enough to schedule on?" BEFORE you bet wall-clock on it.
  shadowFootprints: !!A.shadowFootprints,
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

// Inline GH_TOKEN prefix for every `gh` invocation this script emits — see cfg.ghAuthCmd
// comment above for why this can't be a one-time export instead.
const ghPrefix = cfg.ghAuthCmd ? `GH_TOKEN=$(${cfg.ghAuthCmd}) ` : ''
const gh = (cmd) => `${ghPrefix}${cmd}`
const ghAuthNote = cfg.ghAuthCmd
  ? `\nGH AUTH: every "gh ..." command below already shows the required "GH_TOKEN=$(...) gh ..."
   prefix — always include it verbatim; a plain "gh ..." call runs as the WRONG GitHub account
   (env vars from setup do not carry over between your shell calls, so there is no other way
   this stays authenticated). Same rule for any "gh" command not shown explicitly above.\n`
  : ''

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

// Exception boundary around every agent call (LegalMarc/skillz#22 finding 2).
// agent() returns null on user-skip and terminal API errors, and every call site
// below already routes null into park/halt/log — but agent() can also THROW
// (budget-target exhaustion mid-ticket is the known case), and an uncaught throw
// kills the whole run instead of failing one ticket. Converting a throw into the
// same null every call site already handles gives per-ticket fault isolation with
// one uniform mechanism. The park/report agents this triggers may throw for the
// same underlying reason — they pass through here too, becoming a logged, graceful
// halt rather than a crash.
const tryAgent = async (prompt, opts) => {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    log(`agent "${(opts && opts.label) || '?'}" threw (${e && e.message ? String(e.message).slice(0, 160) : 'unknown error'}) — treating as terminated`)
    return null
  }
}

// ─── Schemas ─────────────────────────────────────────────────────────────────

const QUEUE_SCHEMA = {
  type: 'object',
  required: ['ok', 'reason', 'tickets', 'malformed', 'pendingCount', 'blocked'],
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
    blocked: {
      type: 'array',
      description:
        'one entry per pending (not-yet-eligible) issue naming what still blocks it — this is what lets a "queue drained" report say WHY, instead of reading identically to "nothing left to do." Empty array when pendingCount is 0.',
      items: {
        type: 'object',
        required: ['number', 'title', 'blockedBy'],
        properties: {
          number: { type: 'number' },
          title: { type: 'string' },
          blockedBy: {
            type: 'array',
            items: { type: 'string' },
            description: 'still-open dependency refs, e.g. "#12" or "#7 (parked)"',
          },
        },
      },
    },
  },
}

const CODER_SCHEMA = {
  type: 'object',
  required: ['status', 'summary', 'files_changed', 'reason'],
  properties: {
    status: {
      type: 'string',
      enum: ['staged', 'no_change_needed', 'blocked', 'failed'],
      description:
        'no_change_needed = verified the ticket is already fully implemented on the target branch; nothing to stage.',
    },
    summary: { type: 'string', description: 'max 2 sentences' },
    files_changed: { type: 'array', items: { type: 'string' } },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

const REVIEWER_SCHEMA = {
  type: 'object',
  required: ['verdict', 'findings', 'additions', 'lesson'],
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'REQUEST_CHANGES'] },
    findings: {
      type: 'string',
      description:
        'If REQUEST_CHANGES: numbered findings, each "N. <file>:<line> — <problem> — <required change>". If APPROVE: one line of evidence.',
    },
    additions: {
      type: 'string',
      description:
        'Everything the diff adds beyond the ticket\'s stated scope that you ruled IN-SPIRIT (kept), one short line each — surfaced in the landing record so no addition lands unremarked. Empty string if the diff adds nothing beyond scope. Creep goes in findings as REQUEST_CHANGES, never here.',
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

const CLOSE_SCHEMA = {
  type: 'object',
  required: ['status', 'evidence_sha', 'reason'],
  properties: {
    status: { type: 'string', enum: ['closed', 'failed'] },
    evidence_sha: {
      type: 'string',
      description: 'short SHA of the pre-existing commit that already implements this, if identifiable; else empty',
    },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

// Parallel mode only. Predicted write-set per ticket, used to avoid dispatching
// two colliding tickets at once.
const FOOTPRINT_SCHEMA = {
  type: 'object',
  required: ['number', 'files', 'confidence'],
  properties: {
    number: { type: 'number' },
    files: {
      type: 'array',
      items: { type: 'string' },
      description: 'repo-relative paths this ticket will likely MODIFY (not merely read)',
    },
    confidence: {
      type: 'string',
      enum: ['high', 'low'],
      description: 'low = the ticket does not name its files; treat as conflicting with everything',
    },
  },
}

// Parallel mode only. Worktree provisioning result.
const PREP_SCHEMA = {
  type: 'object',
  required: ['ok', 'reason', 'ready'],
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    ready: {
      type: 'array',
      items: {
        type: 'object',
        required: ['number', 'branch', 'workspace'],
        properties: {
          number: { type: 'number' },
          branch: { type: 'string' },
          workspace: { type: 'string' },
        },
      },
    },
  },
}

// Parallel mode only. Result of committing one approved ticket to its own branch.
const BRANCH_SCHEMA = {
  type: 'object',
  required: ['status', 'branch', 'reason'],
  properties: {
    status: { type: 'string', enum: ['ready', 'failed'] },
    branch: { type: 'string', description: 'branch holding the commit, or empty' },
    reason: { type: 'string', description: 'max 1 sentence' },
  },
}

// Parallel mode only. ONE attempt to merge ALL approved branches, gated once.
// The cheap path: N merges cost one gate run instead of N serialized ones.
// On red or conflict it backs out entirely and the loop falls back to
// one-at-a-time integration to find the culprit.
const BATCH_INTEGRATE_SCHEMA = {
  type: 'object',
  required: ['status', 'landed', 'reason'],
  properties: {
    status: {
      type: 'string',
      enum: ['landed', 'red', 'conflict', 'failed'],
      description: 'red/conflict = fully backed out, all branches preserved, nothing closed',
    },
    landed: {
      type: 'array',
      items: {
        type: 'object',
        required: ['number', 'commit_sha'],
        properties: { number: { type: 'number' }, commit_sha: { type: 'string' } },
      },
      description: 'only populated when status is "landed"; empty otherwise',
    },
    reason: { type: 'string', description: 'max 1 sentence; on red, name the failing check' },
  },
}

// Parallel mode only. One serialized merge of an approved branch into `branch`.
const INTEGRATE_SCHEMA = {
  type: 'object',
  required: ['status', 'commit_sha', 'reason'],
  properties: {
    status: {
      type: 'string',
      enum: ['landed', 'conflict', 'gate_red', 'failed'],
      description: 'conflict/gate_red = backed out cleanly, branch preserved for a retry',
    },
    commit_sha: { type: 'string' },
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

// Every step below that posts model-authored text (a park/halt reason, review findings,
// verification evidence) to GitHub writes it to a scratch file with the acting agent's OWN
// file-write tool first, then passes only that file's PATH to `gh ... --body-file`. Content
// that never touches a shell string or heredoc cannot be reinterpreted by the shell no
// matter what it contains — this text is reviewer/coder/discovery output, and backticked
// `identifiers` or $(...)-shaped substrings inside it are the ordinary case, not the
// adversarial one. This deliberately does NOT use `--body-file - <<'EOF'`: the heredoc
// delimiter is fixed text in this published script, and a bare line matching it inside
// model-authored content ends the heredoc early — the remainder is then read as ordinary
// shell input and executes (demonstrated in the review that required this fix).
const scratchFile = (label) => `/tmp/workflow-loop-${label}.md`
// `gh issue close` has no --body-file/-F equivalent (only --comment <string>), so evidence
// text is always posted as a separate file-based comment, then the issue is closed bare.
const GH_CLOSE_NO_BODY_FILE_NOTE =
  '`gh issue close` has no --body-file option (only --comment <string>) — post the evidence as a normal file-based comment first (step a/b), then close separately (step c) rather than interpolating it into --comment.'

// ─── Prompts ─────────────────────────────────────────────────────────────────

// dryRun must be strictly read-only: no stashing, no comments, no labels.
const dirtyTreePolicy = cfg.autoRecover && !cfg.dryRun
  ? `   - If the tree is dirty (has non-"??" lines): this is an UNATTENDED RESTART (autoRecover on).
     Preserve the crashed run's leftovers, then proceed:
     git stash push -u -m "afk-crash-recovery"
     Confirm the tree is clean afterwards (git status --short: no non-"??" lines). If the stash
     fails or the tree stays dirty →
     {ok:false, reason:"autoRecover stash failed — human inspection needed", tickets:[], malformed:[], pendingCount:0, blocked:[]}`
  : `   - If the tree is dirty (has non-"??" lines) →
     {ok:false, reason:"working tree dirty (possibly a crashed prior run) — inspect git status, then commit/stash/reset by hand", tickets:[], malformed:[], pendingCount:0, blocked:[]}`

const DISCOVER_PROMPT = `Sync gate and eligibility discovery for an autonomous build loop.
Repo: ${cfg.repo}   Loop label: ${cfg.label}   Branch: ${cfg.branch}
${setupPrefix}${ghAuthNote}
1. SYNC GATE:
   git remote get-url origin
   - The origin URL must point at ${cfg.repo} (match the OWNER/REPO pair case-insensitively;
     any host, protocol, or trailing ".git" is fine). args.repo only feeds the gh commands —
     every git command in this loop acts on the CURRENT working directory, so a mismatch
     means issues would be read from one repository and commits pushed to a different one,
     and nothing downstream would notice. Do not proceed:
     {ok:false, reason:"cwd origin <url> does not match args.repo ${cfg.repo} — launch the loop from the target repo's checkout", tickets:[], malformed:[], pendingCount:0, blocked:[]}
   git fetch origin
   git status --short
   git rev-list --left-right --count origin/${cfg.branch}...HEAD
   - If local is BEHIND origin/${cfg.branch} (left count > 0) →
     {ok:false, reason:"local behind origin/${cfg.branch} — fast-forward first", tickets:[], malformed:[], pendingCount:0, blocked:[]}
   - If local is AHEAD of origin/${cfg.branch} (right count > 0) → a commit exists locally
     that never reached the remote. The likely cause is a prior run whose land step
     committed but whose push then failed (rejected, network, auth) — the loop halts a
     failed push before the issue is closed, so that ticket's issue is still open and its
     commit still unpushed. Left unchecked, THIS discovery pass would re-serve that same
     ticket (issue open, not blockedLabel'd), the coder would find the work already done
     and stage nothing, the ticket would eventually park as if blocked — and a LATER
     ticket's successful \`git push\` would then silently ship the earlier commit too, with
     its issue never closed. Do not proceed; surface it instead:
     {ok:false, reason:"local ahead of origin/${cfg.branch} by <right count> commit(s) — a previous land likely committed but failed to push; inspect (git log origin/${cfg.branch}..HEAD), then push by hand, or reset the commit if it was abandoned, before resuming", tickets:[], malformed:[], pendingCount:0, blocked:[]}
   - Tree is DIRTY if git status --short contains any lines NOT starting with "??" (i.e., staged
     changes, modified tracked files, deletions, renames). Untracked-only lines ("?? ...") are safe
     to ignore and do NOT make the tree dirty.
${dirtyTreePolicy}

2. LIST OPEN ISSUES:
   ${gh(`gh issue list --repo ${cfg.repo} --label ${cfg.label} --state open --json number,title,body,labels --limit 100`)}
   EXCLUDE any issue carrying the label "${cfg.blockedLabel}" — those are parked for human triage.
   Parse each body's "## Dependencies" / "Blocked by" / "needs #N" references.
   An issue is ELIGIBLE only when EVERY referenced dependency is CLOSED — verify with:
   ${gh(`gh issue view <dep> --repo ${cfg.repo} --json state`)}
   (Dependencies on issues in the open set are by definition not closed — no API call needed.)
   NON-#N DEPENDENCY TOKENS: a dependency may be written as a project backlog ID rather than
   a GitHub ref (e.g. "M4", "H7", "C6, D1, D5"). These are NOT malformed. Resolve each by
   finding the issue whose title contains that id (e.g. token "M4" -> an issue titled like
   "... M4: ..."): ${gh(`gh issue list --repo ${cfg.repo} --search "<token>" --state all --json number,title,state --limit 20`)}
   Use the matched issue's state. If no issue matches the token, treat that dependency as
   NON-BLOCKING (it refers to backlog work outside this repo's issue set) and proceed —
   do NOT mark the issue malformed and do NOT park it for an unresolvable token.

3. LINT each eligible issue before admitting it to the queue — an issue that cannot
   self-verify wastes a full coder+reviewer cycle, so it must not enter the loop:
   - the body has a non-empty verification section — accept EITHER a "## Required
     verification" heading OR a "## Acceptance criteria" heading (they are equivalent;
     the runnable commands are the bash/command blocks under whichever heading is present)
     — whose entries look like runnable commands (reject prose placeholders like
     "add tests later");
   - its dependency section is present and interpretable. Accept "None", "#N" refs, AND
     project backlog-ID tokens (e.g. "M4", "H7", "C6, D1, D5") resolved per step 2 above.
     A backlog-ID token is NEVER grounds to mark an issue malformed. Only mark malformed
     if the dependency section is unintelligible prose that names no resolvable work item.
${cfg.dryRun
    ? `   DRY RUN — read-only: EXCLUDE each malformed issue from the queue and report it in
   malformed, but do NOT comment, do NOT label, do NOT change anything on GitHub.`
    : `   For each malformed issue: post a comment naming exactly what is missing
   (${gh(`gh issue comment <n> --repo ${cfg.repo} --body "..."`)}), apply the "${cfg.blockedLabel}"
   label (create it first if needed; ignore an already-exists error), and EXCLUDE it
   from the queue. Report it in malformed.`}

3b. HEAD-BLOCKER GUARD — park any ticket that already consumed a whole window without
   landing or being parked.
   The queue is served in order, so a ticket whose attempt died mid-run (usage limit,
   crash, operator stop) gets re-served first on EVERY restart and starves the rest of the
   queue. The dangerous case is the one that looks clean: the death also killed the park
   agent, so there is NO park comment and NO ${cfg.blockedLabel} label on the ticket's own
   issue — it looks untouched. The only reliable trace of that case is a RUN JOURNAL entry
   recording that the ticket was started, with nothing recording that it finished.

   PRIMARY SIGNAL${cfg.reportIssue ? '' : ' — NOT AVAILABLE this run (see caveat below)'}:
${cfg.reportIssue
    ? `   Read the run journal's comments: ${gh(`gh issue view <journal issue> --repo ${cfg.repo} --comments`)}
   The journal issue is ${journalLocatorHint()}.
   For each candidate ticket #N, find its LAST "🟡 Started #N" comment (if any) — match
   "#N" only when followed by a space, colon, "@", or end of line, so checking #5 does
   NOT match "#55" (a "🛑 Parked #N" body appends free-form text that can itself contain
   other "#N" refs — only the first "#N" occurrence, right after the marker word, is the
   marker's own ticket number). If no "✅ Landed #N", "🛑 Parked #N", or "⏹️ Halted #N"
   comment for that SAME ticket number, matched with the same word-boundary rule, appears
   AFTER it, the attempt never finished — a window was spent and nothing was landed,
   parked, or explicitly closed out. That is a head-blocker regardless of what the
   ticket's own issue looks like. ("⏹️ Halted #N" is a clean loop-level/halt-mode stop the
   run reported on itself — not a crash — so treat it exactly like a Landed/Parked close.)`
    : `   reportIssue is OFF for this run, so no journal exists — there is no reliable way to
   see a coder-and-park-agent double death. Skip straight to the fallback signals below,
   and treat them as weaker evidence, not proof.`}

   FALLBACK SIGNALS (weaker — they only catch a death that left SOME trace on the ticket's
   own issue or a local stash; they CANNOT see a death that killed the park agent before it
   wrote anything, which is why the journal above is the primary signal when it exists):
   - a stash for it: git stash list | grep -E '#<n>( |$)'
   - prior loop comments on the issue reporting a failed/interrupted/non-approved attempt:
     ${gh(`gh issue view <n> --repo ${cfg.repo} --comments`)}

   A ticket with PRIMARY or FALLBACK evidence that is STILL unlanded has already had its
   window.${cfg.dryRun
    ? ` DRY RUN: report it in malformed with why="head-blocker: already consumed a window"; change nothing on GitHub.`
    : ` Post a comment stating it is being parked as a head-blocker (with the evidence and
   the note that it should be retried on its own dedicated window, ideally attended),
   apply the "${cfg.blockedLabel}" label, EXCLUDE it from the queue, and report it in
   malformed with why="head-blocker: already consumed a window".`}
   Do NOT apply this to a ticket whose only prior failure was the loop's own tooling
   (e.g. a lint-gate misparse that has since been corrected) — that is not a wasted window.

4. ORDER the remaining eligible issues topologically (dependencies first). If you detect
   a dependency cycle, exclude the cycle members and mention it in reason.${cfg.priority.length ? `
   PRIORITY TIE-BREAK: among issues whose dependencies are equally satisfied, place these
   FIRST, in exactly this order: ${cfg.priority.map((n) => `#${n}`).join(', ')}.
   This only breaks ties — it must NEVER place an issue ahead of one of its own dependencies.` : ''}

5. Return {ok:true, reason:"<N> eligible", tickets:[{number,title}...],
   malformed:[{number, why}...] (empty array if none),
   pendingCount:<open label-matching issues that are NOT eligible>,
   blocked:[{number,title,blockedBy:["#12","#7 (parked)"]}...] — one entry per pending
   issue, naming its still-open dependency refs (GitHub #N, or the resolved issue for a
   backlog-ID token; append " (parked)" if that dependency itself carries "${cfg.blockedLabel}").
   This is the difference between a drained report that says "nothing left" and one that
   says "everything left is blocked by #12, #7" — do not return an empty array here when
   pendingCount > 0. Empty array only when pendingCount is 0.}`

// Where the run journal issue can be found, in prose the discovery/coder/land/park prompts can
// paste inline. Used both to resolve it fresh (discovery, a new process each restart) and to
// describe it when a marker should be posted. Empty string when reportIssue is off — every call
// site below must treat that as "no journal, skip the journal step" rather than guessing.
function journalLocatorHint() {
  if (!cfg.reportIssue) return ''
  return typeof cfg.reportIssue === 'number' && cfg.reportIssue > 0
    ? `issue #${cfg.reportIssue}`
    : `the OPEN issue titled exactly "AFK run log" (${gh(`gh issue list --repo ${cfg.repo} --search "AFK run log in:title" --state open --json number,title`)} — if none exists, there is no journal yet)`
}

// When referenceMode is on, derive the ticket's bracketed id (e.g. "[ABC-004]" → "abc-004")
// and tell the coder to mine the matching reference branch's tip commit as a guide to adapt.
function referenceSection(ticket, ws) {
  if (!cfg.referenceMode) return ''
  const m = ticket.title.match(/\[([A-Za-z]+-\d+)\]/)
  if (!m) return ''
  const g = gitC(ws)
  const id = m[1].toLowerCase()
  const glob = `*${id}-*`
  return `
2b. REFERENCE IMPLEMENTATION — use this; it is the main accelerator for this loop:
   A prior implementation of THIS EXACT ticket may exist on a reference branch.
   - Find it:  ${g} branch -a --list "${glob}"
   - Its per-ticket diff is that branch's TIP commit: ${g} show <branch> — read the WHOLE commit.
   - ADAPT, never blind-copy: the reference predates later work on ${cfg.branch}, so modernize
     its wiring to CURRENT branch conventions (current helper names, current dependency seams),
     and re-derive anything that collides with state that already landed (migration numbers,
     schema already present, files earlier tickets already handled).
   - COMPLETENESS — the #1 failure mode: list the reference's full changed-file set
     (${g} show --name-only <branch>) and account for EVERY file — skip what earlier tickets
     already landed, port what remains. If the reference tightens a constraint (e.g. makes a
     column NOT NULL), you MUST port every WRITER it updated too — a partial copy that adds
     constraints without updating writers passes unit tests and breaks in production.
   - The independent reviewer WILL reject stale pre-refactor patterns and unjustified test-
     assertion changes. Integrate cleanly; the reference is a guide, not a paste source.
${cfg.referenceNote ? `   PROJECT REFERENCE NOTES:\n${cfg.referenceNote}\n` : ''}`
}

// ─── Parallel mode: workspace scoping ────────────────────────────────────────
//
// In parallel mode every ticket gets its own git worktree — a full checkout
// sharing one .git, so N tickets can be edited and tested at once without
// seeing each other. `ws` is that worktree's absolute path; undefined means the
// primary checkout, i.e. the original sequential behavior, unchanged.
//
// The staged INDEX is what carries state between the coder, the reviewer and
// the fix rounds. A worktree has its own index on disk, so `git add` in the
// coder agent is still visible to the reviewer agent that follows it — the
// same handoff the sequential loop relies on, just scoped to this worktree.
const gitC = (ws) => (ws ? `git -C ${ws}` : 'git')
function workspaceBlock(ws) {
  if (!ws) return ''
  return `
WORKSPACE — read this before running anything:
  Your workspace is a dedicated git worktree: ${ws}
  Other tickets are being worked CONCURRENTLY in sibling worktrees. Staying
  inside yours is what keeps them from corrupting each other.
  - Run every git command as: git -C ${ws} <cmd>   (never bare \`git\`)
  - Run verification/test commands from INSIDE the worktree (cd ${ws} first in each shell)
  - Edit, read and test ONLY files under ${ws}
  - Do NOT run \`git pull\`, \`git push\`, \`git merge\`, \`git rebase\`, or \`git fetch\`.
    Integration onto ${cfg.branch} is a separate, serialized phase — not yours.
    (Workspaces share one .git; a concurrent fetch races the others.)
  - Do NOT commit. Stage only; the loop commits for you.
  - Your changes will be verified again after merge. Do not compensate for
    other tickets' work — it is not in your tree and must not be.
`
}

function coderPrompt(ticket, journalIssue, ws, branch) {
  const g = gitC(ws)
  const syncGate = ws
    ? `1. CLAIM YOUR WORKSPACE. It is a reusable worker slot that may still hold a
   previous ticket's work — start from a clean base cut from ${cfg.branch}:
     git -C ${ws} reset --hard && git -C ${ws} clean -fd
     git -C ${ws} checkout -B ${branch} origin/${cfg.branch}
     git -C ${ws} status --short          (MUST be empty before you edit anything)
   This \`checkout -B\` is the ONE checkout you may run. Do not switch branches again.`
    : `1. SYNC GATE: git fetch origin && git status --short
   - If behind origin/${cfg.branch} → return blocked, reason "behind origin".`
  return `You are the CODER in an autonomous build loop. Work ONLY issue #${ticket.number}.
Repo: ${cfg.repo}   Branch: ${cfg.branch}
${setupPrefix}${ghAuthNote}${workspaceBlock(ws)}
${syncGate}

${journalIssue
  ? `1b. RUN JOURNAL MARKER — before any other work, post one line so a mid-ticket crash (this
   process dying before landing OR parking) is visible to the next discovery pass. Keep the
   body to the ticket number only — do not interpolate the issue title verbatim into the
   quoted string below, it may contain characters that break the quoting:
   ${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body "🟡 Started #${ticket.number}"`)}

`
  : ''}2. LOAD TICKET (read the FULL body AND all comments; "## Correction"/"## Notes" sections and
   any "Implementation guidance" comments are authoritative):
   ${gh(`gh issue view ${ticket.number} --repo ${cfg.repo} --comments`)}
   You have NO context beyond this issue — read whatever code you need from the repo.
${referenceSection(ticket, ws)}
2c. PRE-FLIGHT STALENESS CHECK — before changing anything, run the ticket's own verification
   commands (its "## Required verification" section if present, otherwise "## Acceptance
   criteria") against the UNTOUCHED tree. The healthy result is that at least one
   ticket-specific command FAILS — that failure is the gap your change exists to close (the
   red half of red–green). The repo-wide gate (${cfg.checkCommand || 'the full check command'})
   passing is expected — the loop only runs on a green baseline — so it does not count.
   If EVERY ticket-specific verification command already passes on the untouched tree, the
   ticket may be STALE — what it asks for has likely already shipped (landed by earlier
   work the ticket predates). Do NOT rebuild it and do NOT fabricate a no-op diff. Instead
   check every acceptance criterion DIRECTLY against the current code, not just the
   commands: if all are genuinely met, return status "no_change_needed" (files_changed: [],
   your verification evidence in summary) — a valid, complete outcome that an independent
   reviewer will re-verify before anything is closed. If a criterion is NOT actually met
   even though the commands pass, the verification block is too weak to gate this ticket —
   implement the gap AND make the verification actually exercise it.
   (No flaky retries here — a pre-flight failure is the expected result, not a problem.)

2d. CHECK FOR RECOVERABLE PRIOR WORK before writing anything new:
   ${g} stash list | grep -E '#${ticket.number}( |$)'
   If a stash for THIS ticket exists, it is a previous attempt that was interrupted
   (crash, usage limit, operator stop) — often already complete and verified. Prefer
   RECOVERING it over re-implementing from scratch:
   - Inspect it first: ${g} stash show -p 'stash@{N}'
   - If it applies cleanly to current ${cfg.branch} and matches the ticket's intent, apply it
     (${g} stash apply 'stash@{N}' — apply, do NOT drop), then continue at step 4 and
     re-verify it yourself. Re-verification is mandatory; inheriting a prior "it passed"
     claim is not.
   - Re-derive from scratch ONLY if the stash conflicts against current main, is clearly
     stale (the code moved underneath it), or does not actually address the ticket.
   State in your summary which path you took and why. Re-deriving already-green work is
   pure waste — but so is applying a stale patch, so judge it, don't default either way.

3. PLAN, then IMPLEMENT. Before editing, decide the change set; if it spans more than ~3
   files, write the plan out first, then execute it. Follow existing repo conventions,
   reuse helpers, honor every constraint in the issue Notes (security invariants, refs).
   If the ticket is ambiguous on a load-bearing decision (security, privilege,
   data integrity) → return blocked with the ambiguity. Do NOT guess.
${lessonsBlock()}
4. VERIFY: run EVERY command in the issue's verification section — the "## Required
   verification" section if present, otherwise the "## Acceptance criteria" section —
   AND PASTE its real exit status. Do NOT claim "checks pass" for a command you did not actually run.
   ${checkLine}
   If the ticket lists BOTH unit and integration verification, run BOTH — unit suites often
   bypass the layer your change constrains (migrations, infra, external seams), so passing
   units alone proves nothing about that layer.
   ${FLAKY_RULE}
   ${g} diff --check (must be clean).

5. If the ticket needed a real change: STAGE the complete change set: ${g} add <files>;
   confirm ${g} diff --cached --stat matches the working tree exactly (no stray or missing
   files). If instead your work in steps 2c-4 proved the ticket's functionality is ALREADY
   fully present — ${g} diff and ${g} diff --cached are BOTH empty once you're done checking —
   return status "no_change_needed" per step 2c instead of "staged".

Return status "staged" (summary ≤2 sentences, files_changed, reason "checks green"),
or "no_change_needed" per step 2c, or "blocked"/"failed" with a 1-sentence reason. Do not commit.
${cfg.coderNote ? `\nPROJECT NOTE (mandatory — read before staging):\n${cfg.coderNote}` : ''}`
}

function reviewerPrompt(ticket, iter, noChangeNeeded, ws) {
  const g = gitC(ws)
  const step1 = noChangeNeeded
    ? `1. The coder claims issue #${ticket.number} is ALREADY FULLY IMPLEMENTED on ${cfg.branch}
   and needs NO code change. Do not accept this on faith — independently verify it:
   - ${g} status --short && ${g} diff && ${g} diff --cached — ALL must be empty. If anything is
     staged or unstaged, REQUEST_CHANGES: the coder mis-reported its status.
   - Try to identify the pre-existing commit that already implements this (${g} log -S"<distinctive
     string>", ${g} blame, ${g} log --oneline -- <file>) — strengthens the evidence if found, not
     required.
   - Actively hunt for a real gap: check EVERY acceptance criterion against the current code
     yourself, not just the commands the coder ran. A missed criterion here is exactly the
     failure mode to catch — if you find one, REQUEST_CHANGES with the specific gap and treat
     it like any other missing implementation.`
    : `1. Read the staged diff: ${g} diff --cached`
  return `You are an INDEPENDENT, adversarial reviewer. Issue #${ticket.number}, iteration ${iter}/${cfg.maxReviewIterations}.
Repo: ${cfg.repo}
${setupPrefix}${ghAuthNote}${workspaceBlock(ws)}
The coder claims its checks pass. Do not trust the claim — verify everything yourself.

${step1}
2. Re-read the ticket's acceptance criteria AND comments: ${gh(`gh issue view ${ticket.number} --repo ${cfg.repo} --comments`)}
3. Re-run the ticket's verification commands yourself — from its "## Required verification"
   section if present, otherwise its "## Acceptance criteria" section.
   ${FLAKY_RULE}
   If the coder disclosed a "passed on retry" flake, re-run that command yourself with
   extra attention — two independent retry-passes may be a flake; a failure is real.
4. ${checkLine}
5. ${g} diff --check (clean).
6. Judge against acceptance criteria and the issue Notes' invariants. For security or
   correctness tickets, the diff must include the attack/regression test, not just the
   happy path. Check the staged set is complete (nothing left unstaged that belongs).
7. PROHIBITIONS PASS — run this SEPARATELY from the acceptance criteria, and never skip it:
   enumerate EVERY negative constraint in the issue body and its comments — each "do not",
   "never", "must not", "only", "exactly" statement, the entire "## Out of scope" section,
   and constraints buried in "## Notes" prose. QUOTE each one verbatim, then rule on it
   explicitly: does the staged diff honour it — yes or no, with the evidence. This pass
   exists because acceptance criteria are positive and executable, so they get checked by
   default, while prohibitions are prose that reads as background — a diff can pass every
   AC and still break the sentence that mattered most. Asked "does this violate the
   ticket?" a reviewer says no; forced to enumerate and rule, a reviewer has to look. Any
   violated prohibition is a REQUEST_CHANGES finding, no matter how green the checks are.
8. SCOPE-ADDITIONS PASS: enumerate everything the staged diff ADDS beyond the ticket's
   stated scope — new behaviors, new flags, new files, extra checks or types the ticket
   never asked for. Additive creep is invisible to every other gate (old tests pass, new
   tests pass, ACs are met), so it must be caught by enumeration here. Rule on each item:
   - CREEP (unjustified, or it deserves its own ticket) → a REQUEST_CHANGES finding.
   - IN-SPIRIT (small, and clearly serving THIS ticket's goal) → it may land, but list it
     in "additions" so it is surfaced in the landing record for human review — an addition
     may be kept or rejected later, but it must never land unremarked.
9. You may NOT edit anything. Findings only.

APPROVE only if you personally ran the verification and it passed (retry-passes disclosed
in your evidence line) AND the prohibitions pass found no violations. Otherwise
REQUEST_CHANGES with numbered findings:
"N. <file>:<line> — <problem> — <required change>". When you REQUEST_CHANGES, also fill
"lesson": one factual sentence a future coder in this repo should know to avoid this CLASS
of mistake — empty string if the finding is purely ticket-specific.`
}

function fixPrompt(ticket, iter, findings, ws) {
  const g = gitC(ws)
  return `You are the CODER addressing review findings for issue #${ticket.number} (fix round ${iter}).
Repo: ${cfg.repo}
${setupPrefix}${ghAuthNote}${workspaceBlock(ws)}
Findings (fix each exactly; change nothing else):
${findings}
${cfg.referenceMode ? 'If useful, the reference branch for this ticket (see git branch -a) shows how the original handled this — adapt, do not blind-copy.\n' : ''}${lessonsBlock()}
Then re-run the ticket's verification commands — its "## Required verification" section if present, otherwise its "## Acceptance criteria" section (${gh(`gh issue view ${ticket.number} --repo ${cfg.repo}`)} if needed). ${checkLine}
${FLAKY_RULE}
${g} diff --check (clean). Re-stage the COMPLETE set: ${g} add <files>; confirm ${g} diff --cached --stat.

Return status "staged" with a ≤2-sentence summary of what changed, or "failed" with a 1-sentence reason. Do not commit.
${cfg.coderNote ? `\nPROJECT NOTE (mandatory — read before staging):\n${cfg.coderNote}` : ''}`
}

function landPrompt(ticket, journalIssue, additions) {
  const evidenceFile = scratchFile(`land-${ticket.number}`)
  // Reviewer-ruled in-spirit additions must land SURFACED, never silently — additive scope
  // creep passes every green check, so this close-comment line is the only record of it.
  const additionsLine = (additions || '').trim()
    ? `\n      Beyond-scope additions (reviewer ruled in-spirit — kept, flagged for human review): ${additions.trim().slice(0, 400)}`
    : ''
  const prefixHint = cfg.commitPrefix
    ? `Use the commit-subject prefix convention "${cfg.commitPrefix}".`
    : 'Match the subject PREFIX convention of recent commits (git log --oneline -5), e.g. "fix(scope): ...".'
  return `You are the COMMITTER landing APPROVED issue #${ticket.number}: "${ticket.title}".
Repo: ${cfg.repo}   Branch: ${cfg.branch}
${setupPrefix}${ghAuthNote}
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
6. Close with evidence (if gh says it is already closed, treat that as success). The
   one-line evidence comes from verification output you just read and MAY contain
   backticks or $(...) — a passing test name or a shell-shaped assertion is the ordinary
   case, not an attack. ${GH_CLOSE_NO_BODY_FILE_NOTE}
   Never build the comment as a double-quoted --comment string — do it in two safe steps
   instead:
   a. Use your file-write tool (not a shell command) to write the exact text below,
      verbatim, to ${evidenceFile}:
      Implemented in <sha>. Review approved (independent reviewer). Acceptance criteria: all passed — <one-line evidence>.${additionsLine}
   b. ${gh(`gh issue comment ${ticket.number} --repo ${cfg.repo} --body-file ${evidenceFile}`)}
   c. ${gh(`gh issue close ${ticket.number} --repo ${cfg.repo}`)}
${journalIssue
    ? `7. RUN JOURNAL MARKER — close out the "Started" marker so this ticket reads as finished:
   ${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body "✅ Landed #${ticket.number} @ <sha>."`)}
`
    : ''}
Return {status:"landed", commit_sha:"<sha>"} or {status:"failed", commit_sha:"", reason:"..."}.`
}

function parkPrompt(ticket, why, journalIssue) {
  const issueBodyFile = scratchFile(`park-${ticket.number}`)
  const journalBodyFile = scratchFile(`park-journal-${ticket.number}`)
  return `You are PARKING blocked issue #${ticket.number} so an autonomous loop can continue past it.
Repo: ${cfg.repo}
${setupPrefix}${ghAuthNote}
Why it is blocked:
${why}

1. PRESERVE any in-progress work — never discard it:
   git status --short
   If there are ANY staged or unstaged changes (including new files):
   git stash push -u -m "${cfg.blockedLabel} #${ticket.number}"
   Then confirm the tree is clean: git status --short must show no non-"??" lines.
   If stashing fails or the tree is still dirty, return status "failed" — the loop must halt
   rather than contaminate the next ticket.
2. POST the block reason to the issue so a human can triage asynchronously. That reason
   (above) is reviewer/coder text, not operator text: numbered findings are markdown and
   routinely contain backticked \`identifiers\` or $(...)-shaped substrings — that is the
   ordinary case, not the adversarial one. NEVER paste it into a plain double-quoted
   --body string, and do NOT use a shell heredoc either, even a quoted one — a heredoc's
   own delimiter is fixed text in this published script, and a bare line matching it
   inside the reason would end the heredoc early and let the remainder run as ordinary
   shell input. Instead:
   a. Use your file-write tool (not a shell command) to write the following, verbatim and
      unmodified, to ${issueBodyFile}:
      Autonomous loop parked this ticket.
      <the block reason above, verbatim>
      <if work was stashed above, append: Stash to recover it: git stash list | grep '#${ticket.number}'>
   b. ${gh(`gh issue comment ${ticket.number} --repo ${cfg.repo} --body-file ${issueBodyFile}`)}
3. LABEL it (create the label first; ignore an 'already exists' error):
   ${gh(`gh label create ${cfg.blockedLabel} --repo ${cfg.repo} --color D93F0B --description "parked by autonomous loop" 2>/dev/null; true`)}
   ${gh(`gh issue edit ${ticket.number} --repo ${cfg.repo} --add-label ${cfg.blockedLabel}`)}
${journalIssue
    ? `4. RUN JOURNAL MARKER — close out the "Started" marker so this ticket reads as finished,
   not as a dangling in-flight attempt. Same rule as step 2 (this is the same reason text,
   just truncated) — write it with your file-write tool, never a shell string or heredoc:
   a. Write the single line below, verbatim, to ${journalBodyFile}:
      🛑 Parked #${ticket.number}: ${why.slice(0, 200)}
   b. ${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body-file ${journalBodyFile}`)}
`
    : ''}
Return {status:"parked", reason:"<1 sentence>"} or {status:"failed", reason:"<why parking failed>"}.`
}

// Both modes: close a ticket the coder AND an independent reviewer confirmed is already
// fully implemented — nothing to commit or push, but the close still carries evidence.
function closeOnlyPrompt(ticket, journalIssue, ws) {
  const g = gitC(ws)
  const evidenceFile = scratchFile(`close-${ticket.number}`)
  return `You are the COMMITTER closing ALREADY-IMPLEMENTED issue #${ticket.number} — the coder
and an independent reviewer both confirmed this is already fully done on ${cfg.branch}, so there
is nothing to commit or push.
Repo: ${cfg.repo}
${setupPrefix}${ghAuthNote}
1. Confirm there is truly nothing to land: ${g} status --short
   Only "??" untracked-and-unrelated lines are acceptable. If ANYTHING else is present (staged
   or modified tracked files), do not close — return failed, reason "unexpected dirty tree".
2. Try to identify the existing commit on ${cfg.branch} that already implements this, for
   citation: ${g} log -S"<distinctive string from the ticket>" -- <relevant file>, or
   ${g} log --oneline -- <relevant file>. If you can identify it confidently, note its short
   SHA. If not, leave evidence_sha blank — that's fine, it does not block closing.
3. Close with the verification evidence (if gh says it is already closed, treat that as
   success). ${GH_CLOSE_NO_BODY_FILE_NOTE}
   a. Use your file-write tool (not a shell command) to write the exact text below,
      verbatim, to ${evidenceFile}:
      Verified already implemented on ${cfg.branch}<if evidence_sha found, append: " (landed in <sha>)">. No code change needed — independent reviewer confirmed every acceptance criterion. Evidence: <one-line verification summary>.
   b. ${gh(`gh issue comment ${ticket.number} --repo ${cfg.repo} --body-file ${evidenceFile}`)}
   c. ${gh(`gh issue close ${ticket.number} --repo ${cfg.repo}`)}
${journalIssue
    ? `4. RUN JOURNAL MARKER — close out the "Started" marker so this ticket reads as finished:
   ${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body "✅ Landed #${ticket.number} (no change needed — verified already implemented)"`)}
`
    : ''}
Return {status:"closed", evidence_sha:"<short sha or empty>", reason:"..."} or
{status:"failed", evidence_sha:"", reason:"..."}.`
}

// ─── Parallel mode: footprint → worker slots → pool → serialized integration ─

function footprintPrompt(ticket) {
  return `Predict the WRITE-SET of issue #${ticket.number} in ${cfg.repo}. Do not implement anything.
${setupPrefix}${ghAuthNote}
${gh(`gh issue view ${ticket.number} --repo ${cfg.repo} --comments`)}

List the repo-relative paths this ticket will MODIFY. Files it merely reads do not count —
two tickets reading the same file is harmless; two tickets writing it is a merge conflict.

Be GENEROUS on the write side. A missed file causes a real conflict later; a spurious one
only costs a little parallelism. Include the test files the ticket will add or change, and
any shared registry/index/barrel file a new module must be registered in — those are the
classic surprise conflicts.

Ground it in the repo, don't guess from the title: if the issue names paths, resolve them;
if it names a symbol, grep for where that symbol lives.

confidence "high" only if the issue names its files or you located them in the repo.
"low" if the ticket is vague or exploratory — the loop then treats it as conflicting with
everything and runs it alone, which is the safe reading.`
}

function prepPrompt(slots) {
  const lines = slots
    .map((s) => `   - slot ${s.number} → worktree ${s.workspace} (idle branch ${s.branch})`)
    .join('\n')
  return `Prepare reusable WORKER WORKTREES so several tickets can be built CONCURRENTLY.
Repo: ${cfg.repo}   Primary checkout: $(git rev-parse --show-toplevel)   Base: origin/${cfg.branch}
${setupPrefix}${ghAuthNote}
These are SLOTS, not per-ticket checkouts: each is provisioned once and reused for ticket
after ticket, so the expensive setup in step 3 is paid once rather than per ticket. Each
coder resets its slot to a fresh branch off origin/${cfg.branch} before it starts.

1. From the PRIMARY checkout: git fetch origin && git status --short
   - Tree must be clean (only "??" lines are acceptable) and NOT behind origin/${cfg.branch}.
     If it is dirty or behind → return ok:false with the reason; create nothing.
   - This is the ONLY fetch: the coders are forbidden from fetching, because they share
     one .git and concurrent fetches race. Tickets branch from origin/${cfg.branch} as of now.

2. Create ${slots.length} worktree(s), each on its own idle branch cut from origin/${cfg.branch}:
${lines}

   For each: git worktree add -B <idle-branch> <worktree-path> origin/${cfg.branch}
   If a path already exists from a previous run, remove it first:
     git worktree remove --force <path> 2>/dev/null; git worktree prune
   Create them ONE AT A TIME, not in parallel — concurrent \`git worktree add\` races on
   the shared .git directory.

3. A worktree is a CHECKOUT, not a copy: it has no node_modules, no virtualenv, no build
   cache. Anything the verification gate needs must be provisioned now, or every gate run
   in that worktree fails for reasons that have nothing to do with the ticket.
${cfg.workerSetupCommand
      ? `   Run this in EACH worktree, with WL_MAIN=<primary checkout> and WL_WORKSPACE=<that worktree>:
     ${cfg.workerSetupCommand}`
      : `   No workerSetupCommand was configured. Inspect what the gate needs (node_modules,
     .venv, .env) and symlink it from the primary checkout into each worktree — symlink,
     do not copy. If you cannot make a worktree able to run the gate, return ok:false
     rather than letting every ticket fail its verification.`}

4. PROVE a worktree can actually run the gate before returning — a worktree that cannot is
   worse than no parallelism, because it fails every ticket instead of zero, and each
   failure costs a full coder pass. In ONE worktree run:
     ${cfg.checkCommand || "the repo's gate"}
   If it does not pass in a freshly-prepared worktree, return ok:false with what was missing.
   Do NOT skip this because it is slow — it is the cheapest failure in the whole run.

Return {ok, reason, ready:[{number, branch, workspace}...]} — one entry per SLOT, where
number is the slot number from the list above.`
}

function sealPrompt(ticket, ws, branch) {
  const prefixHint = cfg.commitPrefix
    ? `Use the commit-subject prefix convention "${cfg.commitPrefix}".`
    : `Match the subject PREFIX convention of recent commits (git -C ${ws} log --oneline -5), e.g. "fix(scope): ...".`
  return `Commit the APPROVED work for issue #${ticket.number}: "${ticket.title}" to its own branch. Do NOT push.
Repo: ${cfg.repo}   Workspace: ${ws}   Branch: ${branch}
${setupPrefix}
1. Confirm staged work exists: git -C ${ws} diff --cached --stat (non-empty).
2. Read the real change: git -C ${ws} diff --cached. Derive the subject from what THIS diff
   does plus the ticket title above — never copy or lightly reword a recent commit's
   subject. ${prefixHint} Match prior commits' FORMAT only, never their wording: back-to-back
   tickets can touch identical files with unrelated fixes, and reusing a prior subject
   has silently mislabeled commits before.
3. git -C ${ws} commit -m "<imperative subject>" -m "Refs #${ticket.number}"
   No "closes/fixes" keywords — the explicit close happens after integration.
4. Confirm the worktree is now clean: git -C ${ws} status --short
5. git -C ${ws} rev-parse --abbrev-ref HEAD  (must equal ${branch})

Do NOT push, merge, rebase, or touch ${cfg.branch}. Integration is a separate phase.
Return {status:"ready", branch:"${branch}", reason:"committed <short sha>"} or
{status:"failed", branch:"", reason:"..."}.`
}

// One close-comment body per issue, written via the acting agent's file-write tool —
// the same shell-safety rule as every other gh body in this script.
function integrationCloseSteps(n, additions, journalIssue, extraEvidence) {
  const evidenceFile = scratchFile(`integrate-${n}`)
  const additionsLine = (additions || '').trim()
    ? `\n      Beyond-scope additions (reviewer ruled in-spirit — kept, flagged for human review): ${additions.trim().slice(0, 400)}`
    : ''
  return `   a. Use your file-write tool (not a shell command) to write the exact text below,
      verbatim, to ${evidenceFile}:
      Implemented in <merge sha>. Reviewed independently on its own branch; full gate re-run green after merging into ${cfg.branch}${extraEvidence}. <one-line evidence>.${additionsLine}
   b. ${gh(`gh issue comment ${n} --repo ${cfg.repo} --body-file ${evidenceFile}`)}
   c. ${gh(`gh issue close ${n} --repo ${cfg.repo}`)}${journalIssue
    ? `
   d. RUN JOURNAL MARKER: ${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body "✅ Landed #${n} @ <merge sha>."`)}`
    : ''}`
}

function batchIntegratePrompt(ready, journalIssue) {
  const list = ready.map((r) => `   - ${r.branch}  (issue #${r.ticket.number})`).join('\n')
  const closes = ready
    .map((r) => `For issue #${r.ticket.number}:\n${integrationCloseSteps(r.ticket.number, r.additions, journalIssue, ' alongside <the other branch names, or "no other branches">')}`)
    .join('\n')
  return `You are the INTEGRATOR. Merge ALL of these approved branches into ${cfg.branch} as ONE batch.
Repo: ${cfg.repo}   Target: ${cfg.branch}
${setupPrefix}${ghAuthNote}
Branches (each already built and independently reviewed, each green ON ITS OWN):
${list}

WHY A BATCH: the gate is the expensive serial step. Merging one-at-a-time and gating after
each costs N gate runs; merging all N and gating ONCE costs one. Most batches are green, so
this is the cheap path. When it is NOT green you back the whole thing out and the loop
re-integrates one at a time to find the culprit — you do NOT hunt for it here.

WHAT THE GATE IS ACTUALLY TESTING: each branch was built against ${cfg.branch} as it stood
BEFORE its siblings landed. Individually green is not evidence the COMBINATION is green —
two tickets can each pass alone and break together (a renamed helper, a changed fixture, a
tightened assertion). This gate run is the only place that combination is ever tested.

Work in the PRIMARY checkout (not a worktree). You are the only writer to ${cfg.branch}.

1. git checkout ${cfg.branch} && git pull --ff-only
2. Record the pre-merge SHA — you will need it to back out EXACTLY: git rev-parse HEAD
3. Merge each branch in the order listed:
     git merge --no-ff <branch> -m "Merge <branch> (Refs #<n>)"
   - On ANY conflict: git merge --abort, then git reset --hard <pre-merge SHA>, confirm
     git status is clean, and return {status:"conflict", landed:[]} naming the conflicting
     paths and branch. Do NOT resolve it — a hand-resolved merge has been reviewed by nobody.
4. RUN THE FULL GATE once on the combined result: ${cfg.checkCommand || "the repo's gate"}
   - If RED: git reset --hard <pre-merge SHA>, confirm git status is clean and that
     git log -1 matches the pre-merge SHA, then return {status:"red", landed:[]} with the
     failing check named. Close NOTHING. Every branch is preserved — nothing is lost.
     A red ${cfg.branch} is far more expensive than a re-integration: never leave it merged.
5. Only if GREEN: git push
   If rejected: git pull --ff-only && re-run the gate && git push (once). If it still fails,
   do NOT force — return {status:"failed", landed:[]} with the rejection message.
6. For EACH merged issue, capture its merge commit SHA, then close it with evidence
   (if gh says already closed, treat as success). ${GH_CLOSE_NO_BODY_FILE_NOTE}
${closes}
7. Delete the merged branches: git branch -d <branch> (each).

Return {status, landed:[{number, commit_sha}...], reason}. "landed" is non-empty ONLY when
status is "landed", and must then contain EVERY issue in the list above.`
}

function integratePrompt(r, position, total, journalIssue) {
  const ticket = r.ticket
  return `You are the INTEGRATOR, merging ONE approved branch into ${cfg.branch}. Merge ${position} of ${total}.
Repo: ${cfg.repo}   Branch to merge: ${r.branch}   Issue: #${ticket.number}
${setupPrefix}${ghAuthNote}
Work in the PRIMARY checkout (not a worktree). You are the only writer to ${cfg.branch} —
merges are deliberately serialized, so take your time and do this carefully.

WHY THIS PHASE RE-VERIFIES: ${r.branch} was built and reviewed in ISOLATION, against
origin/${cfg.branch} as it stood before the other tickets in this round landed. Each branch
is individually green. That is NOT evidence the COMBINATION is green — two tickets can each
pass alone and break together (a renamed helper, a changed fixture, a tightened assertion).
This phase is the only place that combination is ever tested. Do not skip the gate because
"the reviewer already ran it" — the reviewer ran it on a tree that no longer exists.

1. git checkout ${cfg.branch} && git pull --ff-only
2. Record the pre-merge SHA so you can back out exactly: git rev-parse HEAD
3. git merge --no-ff ${r.branch} -m "Merge ${r.branch} (Refs #${ticket.number})"
   - On CONFLICT: git merge --abort, then return {status:"conflict"} naming the conflicting
     paths. Do NOT resolve it yourself — the ticket needs re-running against the new base,
     and a hand-resolved merge has never been reviewed by anyone.
4. RUN THE FULL GATE on the merged result: ${cfg.checkCommand || "the repo's gate"}
   - If RED: reset hard back to the SHA from step 2 (git reset --hard <sha>), confirm
     git status is clean, and return {status:"gate_red"} with the failing output. The branch
     is preserved, so nothing is lost — the ticket is simply re-run against the new base.
     A red ${cfg.branch} is far more expensive than a re-run: never leave the merge in place.
5. Only if GREEN: git push
   If rejected: git pull --ff-only && re-run the gate && git push (once). If it still fails,
   do NOT force — return failed with the rejection message.
6. SHA: git rev-parse --short HEAD
7. Close with evidence (if gh says already closed, treat as success). ${GH_CLOSE_NO_BODY_FILE_NOTE}
${integrationCloseSteps(ticket.number, r.additions, journalIssue, '')}
8. Clean up the merged branch: git branch -d ${r.branch}

Return {status:"landed"|"conflict"|"gate_red"|"failed", commit_sha, reason}.`
}

// Parallel-mode park: same contract as parkPrompt (preserve work, findings on the issue,
// triage label, journal close-out) but the work lives in a worktree, not the primary tree —
// so it is PRESERVED BY COMMITTING to the ticket's own branch (a ref in the shared .git
// that survives the slot being reset for the next ticket), never by stashing.
function parallelParkPrompt(ticket, why, ws, branch, journalIssue) {
  const issueBodyFile = scratchFile(`park-${ticket.number}`)
  const journalBodyFile = scratchFile(`park-journal-${ticket.number}`)
  return `You are PARKING blocked issue #${ticket.number} so an autonomous loop can continue past it.
Repo: ${cfg.repo}   Workspace: ${ws}   Ticket branch: ${branch}
${setupPrefix}${ghAuthNote}
Why it is blocked:
${why}

1. PRESERVE any in-progress work — never discard it. This worktree is a reusable slot that
   the next ticket will reset, so anything left uncommitted here is destroyed:
   git -C ${ws} status --short
   If there are ANY staged or unstaged changes (including new files):
   git -C ${ws} add -A && git -C ${ws} commit -m "WIP (parked): #${ticket.number}" -m "Refs #${ticket.number} — parked by autonomous loop; NOT reviewed, NOT approved. Recover via: git log ${branch}"
   (Committing to ${branch} is the preservation mechanism — the branch survives slot reuse.
   This WIP commit is never merged by the loop; integration only merges APPROVED branches.)
   Then confirm the worktree is clean: git -C ${ws} status --short must show no non-"??" lines.
2. POST the block reason to the issue so a human can triage asynchronously. That reason
   (above) is reviewer/coder text, not operator text — NEVER paste it into a plain
   double-quoted --body string, and do NOT use a shell heredoc either, even a quoted one.
   Instead:
   a. Use your file-write tool (not a shell command) to write the following, verbatim and
      unmodified, to ${issueBodyFile}:
      Autonomous loop parked this ticket.
      <the block reason above, verbatim>
      <if work was committed in step 1, append: Work preserved on branch ${branch} (WIP commit, unreviewed).>
   b. ${gh(`gh issue comment ${ticket.number} --repo ${cfg.repo} --body-file ${issueBodyFile}`)}
3. LABEL it (create the label first; ignore an 'already exists' error):
   ${gh(`gh label create ${cfg.blockedLabel} --repo ${cfg.repo} --color D93F0B --description "parked by autonomous loop" 2>/dev/null; true`)}
   ${gh(`gh issue edit ${ticket.number} --repo ${cfg.repo} --add-label ${cfg.blockedLabel}`)}
${journalIssue
    ? `4. RUN JOURNAL MARKER — close out the "Started" marker so this ticket reads as finished,
   not as a dangling in-flight attempt. Same rule as step 2 — write it with your file-write
   tool, never a shell string or heredoc:
   a. Write the single line below, verbatim, to ${journalBodyFile}:
      🛑 Parked #${ticket.number}: ${why.slice(0, 200)}
   b. ${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body-file ${journalBodyFile}`)}
`
    : ''}
Return {status:"parked", reason:"<1 sentence>"} or {status:"failed", reason:"<why parking failed>"}.`
}

// The predicted write-set, or null when we don't trust it.
function filesOf(footprints, number) {
  const fp = footprints.find((f) => f && f.number === number)
  return fp && fp.confidence === 'high' && Array.isArray(fp.files) ? fp.files : null
}

// A null write-set means "could touch anything", so it runs ALONE. Guessing
// optimistically is paid for later with a merge conflict that wastes a whole
// coder+reviewer pass; erring toward less parallelism is the cheaper mistake.
function collides(files, inflightFileSets) {
  if (inflightFileSets.length === 0) return false // idle pool: always dispatchable
  if (!files) return true // unknown write-set: must run alone
  return inflightFileSets.some((other) => !other || other.some((f) => files.includes(f)))
}

// Conflict-aware work-stealing pool. NOT waves: a wave is a barrier that ends when its
// slowest member does, idling workers. Here, the moment a slot frees it takes the next
// queued ticket whose predicted write-set collides with nothing currently IN FLIGHT.
// Queue order is preserved; a ticket is skipped over only on a genuine conflict.
async function runPool(specs, slots, footprints, journalIssue) {
  const pending = [...specs]
  const freeSlots = [...slots]
  const inflight = new Map() // id -> {files, promise}
  const results = []
  let nextId = 0

  while (pending.length || inflight.size) {
    let dispatched = true
    while (dispatched && freeSlots.length && pending.length) {
      dispatched = false
      const active = [...inflight.values()].map((e) => e.files)
      for (let i = 0; i < pending.length; i++) {
        const files = filesOf(footprints, pending[i].number)
        if (collides(files, active)) continue
        const ticket = pending.splice(i, 1)[0]
        const slot = freeSlots.pop()
        const id = ++nextId
        const branch = `${cfg.branchPrefix}/${ticket.number}`
        log(`  → #${ticket.number} dispatched to ${slot.workspace}`)
        const promise = (async () => ({
          id,
          slot,
          result: await runTicketInWorkspace(ticket, slot.workspace, branch, journalIssue),
        }))()
        inflight.set(id, { files, promise })
        dispatched = true
        break
      }
    }
    // Nothing running and nothing dispatchable cannot happen: with an empty
    // pool `collides` always returns false. Guard anyway rather than spin.
    if (!inflight.size) break
    const { id, slot, result } = await Promise.race([...inflight.values()].map((e) => e.promise))
    inflight.delete(id)
    freeSlots.push(slot)
    results.push(result)
    log(`  ← #${result.ticket.number} ${result.status}`)
  }
  return results
}

// Shadow mode scoring. `missed` is the dangerous half — a file the ticket really
// wrote but the prediction did not list would have let a colliding ticket run
// beside it. `extra` only costs a little parallelism.
function scoreFootprint(predicted, actual) {
  const p = new Set(predicted || [])
  const a = new Set(actual || [])
  return {
    missed: [...a].filter((f) => !p.has(f)),
    extra: [...p].filter((f) => !a.has(f)),
    exact: p.size === a.size && [...a].every((f) => p.has(f)),
  }
}

// One ticket's full code→review→fix cycle inside its own worktree. Returns a sealed
// branch ready for integration, a verified no_change_needed, or a terminal status.
// Never touches `branch` — landing is the serialized integration phase's job alone.
// Parking (skip mode) happens IN HERE, while the slot is still claimed: the work is
// preserved by committing to the ticket branch, which must occur before the next
// ticket's claim step resets the slot.
async function runTicketInWorkspace(ticket, ws, branch, journalIssue) {
  const coded = await tryAgent(coderPrompt(ticket, journalIssue, ws, branch), {
    ...coderOpts({ label: `coder-${ticket.number}`, phase: 'Build' }),
    schema: CODER_SCHEMA,
  })
  if (!coded || !['staged', 'no_change_needed'].includes(coded.status)) {
    const status = coded ? coded.status : 'failed'
    const reason = coded ? coded.reason : 'coder agent terminated (skipped or API error)'
    return await maybeParkParallel(ticket, `Coder ${status}: ${reason}`, ws, branch, journalIssue, status === 'blocked' ? 'blocked' : 'failed')
  }
  let noChangeNeeded = coded.status === 'no_change_needed'

  let approved = false
  let approvedAdditions = ''
  let lastFindings = ''
  let reviewRounds = 0
  for (let iter = 1; iter <= cfg.maxReviewIterations; iter++) {
    reviewRounds = iter
    const reviewed = await tryAgent(reviewerPrompt(ticket, iter, noChangeNeeded, ws), {
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
      approvedAdditions = (reviewed.additions || '').trim()
      break
    }
    recordLesson(reviewed.lesson)
    if (iter === cfg.maxReviewIterations) break

    const isFinalFixRound = iter === cfg.maxReviewIterations - 1
    const fixAgentOpts = isFinalFixRound ? escalatedOpts : coderOpts
    const fixed = await tryAgent(fixPrompt(ticket, iter, reviewed.findings, ws), {
      ...fixAgentOpts({ label: `fix-${ticket.number}-i${iter}${isFinalFixRound ? '-esc' : ''}`, phase: 'Build' }),
      schema: CODER_SCHEMA,
    })
    if (!fixed || fixed.status !== 'staged') {
      lastFindings = `fix round ${iter} ${fixed ? 'failed: ' + fixed.reason : 'terminated'}; outstanding: ${lastFindings}`
      break
    }
    noChangeNeeded = false
  }

  if (!approved) {
    const why = `Review not approved after ${reviewRounds} round(s). Outstanding findings:\n${lastFindings}`
    return await maybeParkParallel(ticket, why, ws, branch, journalIssue, 'blocked', reviewRounds)
  }
  if (noChangeNeeded) {
    return { ticket, status: 'no_change_needed', branch: '', ws, reviewRounds, reason: coded.reason, additions: '' }
  }

  const sealed = await tryAgent(sealPrompt(ticket, ws, branch), {
    ...mechanicalOpts({ label: `seal-${ticket.number}`, phase: 'Build' }),
    schema: BRANCH_SCHEMA,
  })
  if (!sealed || sealed.status !== 'ready') {
    const reason = sealed ? sealed.reason : 'seal agent terminated (skipped or API error)'
    return await maybeParkParallel(ticket, `Seal failed: ${reason}`, ws, branch, journalIssue, 'failed', reviewRounds)
  }
  return { ticket, status: 'ready', branch, ws, reviewRounds, reason: sealed.reason, additions: approvedAdditions }
}

// Skip mode parks inside the worker (see runTicketInWorkspace). Halt mode returns the
// raw status: work stays in the worktree/branch for inspection, and the loop halts after
// the pool drains. A park failure here does NOT halt the run — the worktree is isolated,
// so unlike the sequential tree there is nothing a failed park can contaminate.
async function maybeParkParallel(ticket, why, ws, branch, journalIssue, rawStatus, reviewRounds) {
  if (cfg.onBlocked !== 'skip') {
    return { ticket, status: rawStatus, branch: '', ws, reviewRounds, reason: why.slice(0, 240), additions: '' }
  }
  const parked = await tryAgent(parallelParkPrompt(ticket, why, ws, branch, journalIssue), {
    ...mechanicalOpts({ label: `park-${ticket.number}`, phase: 'Park' }),
    schema: PARK_SCHEMA,
  })
  if (!parked || parked.status !== 'parked') {
    const reason = parked ? parked.reason : 'park agent terminated (skipped or API error)'
    return { ticket, status: 'failed', branch: '', ws, reviewRounds, reason: `park failed: ${reason} (original: ${why.slice(0, 160)})`, additions: '' }
  }
  log(`#${ticket.number} PARKED (${cfg.blockedLabel}) — findings posted; work preserved on ${branch}; loop continues`)
  return { ticket, status: 'parked', branch, ws, reviewRounds, reason: why.slice(0, 240), additions: '' }
}

function journalStartPrompt() {
  return `You are opening the RUN JOURNAL for an autonomous build loop that is starting now.
Repo: ${cfg.repo}   Journal setting: ${cfg.reportIssue}
${setupPrefix}${ghAuthNote}
1. Resolve the journal issue:
   ${typeof cfg.reportIssue === 'number' && cfg.reportIssue > 0
     ? `Use issue #${cfg.reportIssue}.`
     : `Find an OPEN issue titled exactly "AFK run log":
   ${gh(`gh issue list --repo ${cfg.repo} --search "AFK run log in:title" --state open --json number,title`)}
   If none exists, create it:
   ${gh(`gh issue create --repo ${cfg.repo} --title "AFK run log" --body "Journal for autonomous workflow-loop runs. Each run posts a start comment and an end-of-run report here."`)}`}
2. Post the start comment (get the timestamp from: date -u):
   ${gh(`gh issue comment <issue> --repo ${cfg.repo} --body "🟢 Run started <UTC timestamp>. Label: ${cfg.label} · branch: ${cfg.branch} · onBlocked: ${cfg.onBlocked}."`)}

Return {status:"ok", issue:<number>, reason:""} or {status:"failed", issue:0, reason:"<1 sentence>"}.`
}

function reportPrompt(journalIssue, resultLines, haltReason, pendingCount, drainedReason) {
  // This comment IS the durable external marker overnight resilience depends on (see
  // SKILL.md "Overnight resilience"). A session death or sleep can kill everything else —
  // agents, cron firings — but a comment already posted to GitHub survives. The first
  // line must therefore say, unambiguously, whether this run finished or was cut off:
  // a relauncher (or a human) reading only that line must be able to tell the two apart.
  // It must ALSO not claim "finished cleanly" when the queue only drained of ELIGIBLE
  // work while other tickets remain transitively blocked — that used to be the one case
  // this marker got wrong, silently, every time it happened.
  const haltLine = haltReason
    ? `⏸ HALTED <UTC timestamp>. Did NOT finish — stopped mid-run: ${haltReason}. Safe to resume with the same args (add autoRecover: true).`
    : pendingCount > 0
      ? `🔴 Run ended <UTC timestamp>. ${drainedReason} — resuming will not find new work until a blocker lands or is parked.`
      : `🔴 Run ended <UTC timestamp>. Finished cleanly — queue drained, nothing left to resume.`
  const bodyFile = scratchFile('run-report')
  return `You are posting the END-OF-RUN marker for an autonomous build loop.
Repo: ${cfg.repo}   Journal issue: #${journalIssue}
${setupPrefix}${ghAuthNote}
Compose the comment body described below, then use your file-write tool (NOT a shell
heredoc, and NOT a double-quoted --body string) to write it verbatim to ${bodyFile}. The
haltReason/drainedReason/result details are reviewer/coder/discovery text, and backticks
or $(...)-shaped substrings inside them are the ordinary case, not the adversarial one — a
heredoc is unsafe here even with a quoted delimiter, because the delimiter itself is fixed
text in this published script and a bare line matching it inside that text would end the
heredoc early. Writing the file directly and passing only its PATH to gh sidesteps shell
interpolation entirely.

The comment body, as GitHub markdown (get the timestamp from: date -u, substitute it for
<UTC timestamp> below):
- First line, EXACTLY (substitute the real timestamp): ${haltLine}
- Then, only if there is at least one result below, a results table with columns:
  Ticket | Outcome | Detail. One row per line below. For landed rows the detail is the
  short SHA (verify against git log if useful); for parked rows, the one-line reason plus
  "findings on the ticket".

Results (may be empty — this run may have stopped before landing or parking anything):
${resultLines || '(none — halted before any ticket completed)'}

Once ${bodyFile} is written, post it:
${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body-file ${bodyFile}`)}

This comment must land even when nothing was completed — it is the only durable proof,
outside a live session, that this run stopped here and did not vanish silently.

Return {status:"ok", issue:${journalIssue}, reason:""} or {status:"failed", issue:0, reason:"<1 sentence>"}.`
}

function haltMarkerPrompt(ticket, reason, journalIssue) {
  const bodyFile = scratchFile(`halt-${ticket.number}`)
  return `You are closing out the run journal's "Started" marker for issue #${ticket.number}
because this run is halting on it WITHOUT landing or parking it (a loop-level or
halt-mode stop, not a crash) — the next discovery pass must not read a dangling
"Started #${ticket.number}" as evidence a window died mid-ticket and park approved,
staged, or in-review work as a head-blocker.
Repo: ${cfg.repo}
${setupPrefix}${ghAuthNote}
The halt reason is loop/coder/reviewer text and may contain backticks or $(...)-shaped
substrings — that is the ordinary case. Use your file-write tool (never a shell heredoc or
a double-quoted --body string — a heredoc delimiter is fixed text in this published
script, and a bare line matching it inside the reason would end the heredoc early and let
the remainder run as shell input) to write the exact text below to ${bodyFile}, then post
it by PATH only:
   ⏹️ Halted #${ticket.number}: ${reason.slice(0, 200)}. Not landed, not parked — a clean
   loop-level/halt-mode stop reported by the run itself, not a crash. Safe to resume
   directly once the underlying cause is fixed.
${gh(`gh issue comment ${journalIssue} --repo ${cfg.repo} --body-file ${bodyFile}`)}
Return {status:"ok", issue:${journalIssue}, reason:""} or {status:"failed", issue:0, reason:"<1 sentence>"}.`
}

// Closes a dangling "Started #N" journal entry on every halt path that stops on a
// ticket without landing or parking it: loop-level coder failure, halt-mode coder
// block, halt-mode review exhaustion, and landing failure. Without this, the ticket's
// only journal trace is an unclosed "Started", which the discovery head-blocker guard
// (DISCOVER_PROMPT step 3b) cannot distinguish from a crash — so a resume would park
// fully-approved, already-staged work as if it were blocked. Posting failure here is
// never fatal to the halt itself (the run is stopping regardless); it only logs, same
// as journalStartPrompt's own failure handling.
async function closeJournalOnHalt(ticket, reason, journalIssue) {
  if (!journalIssue) return
  const closed = await tryAgent(haltMarkerPrompt(ticket, reason, journalIssue), {
    ...mechanicalOpts({ label: `halt-marker-${ticket.number}`, phase: 'Land' }),
    schema: JOURNAL_SCHEMA,
  })
  if (!closed || closed.status !== 'ok') {
    log(`Could not post the Halted journal marker for #${ticket.number} (${closed ? closed.reason : 'agent terminated'}) — a later resume's head-blocker guard may misread this ticket; check manually if so.`)
  }
}

// ─── Park helper: preserve work, annotate issue, keep the loop grinding ──────

async function park(ticket, why, completed, journalIssue) {
  const parked = await tryAgent(parkPrompt(ticket, why, journalIssue), {
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
// Shadow mode: one entry per ticket, predicted write-set vs what was staged.
const footprintScores = []
let landedTotal = 0
let parkedTotal = 0
let halted = false
let haltReason = ''
let journalIssue = 0
// Last discovery's blocked-ticket detail, kept outside the round loop so the final
// summary and the drained-queue log can both name WHY things stopped, not just THAT
// they stopped — "queue drained" and "queue drained but #12, #7 are stuck" must not
// read the same.
let lastPendingCount = 0
let lastBlocked = []
const describeBlocked = (blocked) => {
  const list = blocked || []
  const parts = list
    .slice(0, 8)
    .map((b) => `#${b.number} (${(b.blockedBy && b.blockedBy.length ? b.blockedBy.join(', ') : 'unresolved deps')})`)
  // A 20-ticket block list truncated to 8 with no marker reads as a complete
  // enumeration — it isn't. Name the gap.
  if (list.length > 8) parts.push(`+${list.length - 8} more`)
  return parts.join('; ')
}

for (let round = 1; round <= MAX_ROUNDS && !halted; round++) {
  phase('Discover')

  // Open the run journal as early as possible in the run — before discovery can fail
  // and before we know whether the queue turns out empty. Two cases need a marker more
  // than any other, and both used to get none: a discovery agent death (a usage-limit
  // kill is exactly this) on round 1, and a round whose entire remaining queue is
  // transitively blocked (queue.length === 0 further down) — that second case can also
  // recur on later restarts, leaving the journal's last comment stale and misread by a
  // relauncher as "still alive." Guarded by !cfg.dryRun: dryRun must never touch GitHub.
  if (cfg.reportIssue && !cfg.dryRun && !journalIssue) {
    const opened = await tryAgent(journalStartPrompt(), {
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

  const discovery = await tryAgent(DISCOVER_PROMPT, {
    ...mechanicalOpts({ label: round === 1 ? 'discover' : `discover-r${round}`, phase: 'Discover' }),
    schema: QUEUE_SCHEMA,
  })

  if (!discovery) {
    halted = true
    haltReason = 'discovery agent terminated (skipped or API error)'
    break
  }
  if (!discovery.ok) {
    // An early `return` here would skip the end-of-run journal block below entirely —
    // fine on round 1 (nothing started yet), but reachable on round 2+ of any multi-round
    // run: a mid-run sync-gate abort (dirty tree, behind origin) after earlier rounds
    // already landed tickets and posted markers. Without this, the journal's last comment
    // stays a stale "Landed #N" that a relauncher reads as "still alive" — forever. Halt
    // and fall through instead, so a HALTED marker posts whenever journalIssue is set.
    halted = true
    haltReason = `discovery blocked: ${discovery.reason}`
    log(`BLOCKED at discovery: ${discovery.reason}`)
    break
  }

  lastPendingCount = discovery.pendingCount || 0
  lastBlocked = discovery.blocked || []

  // QUEUE_SCHEMA declares number:'number', but that's enforced only by discovery-agent
  // compliance, not the runtime — coerce here, once, before `${ticket.number}` gets
  // interpolated into every gh/git command the coder, reviewer, land, and park prompts
  // emit for this ticket.
  const queue = discovery.tickets
    .map((t) => ({ ...t, number: Number(t.number) }))
    .filter((t) => !attempted.has(t.number))
  if (queue.length === 0) {
    if (lastPendingCount > 0) {
      log(`Queue drained of ELIGIBLE work, but ${lastPendingCount} ticket(s) remain — transitively blocked, not finished: ${describeBlocked(lastBlocked) || '(discovery did not name them)'}`)
    } else {
      log(round === 1 ? 'No eligible tickets.' : 'No newly eligible tickets — queue fully drained (nothing pending).')
    }
    break
  }
  log(`Round ${round} eligible: ${queue.map((t) => '#' + t.number).join(', ')} (${discovery.pendingCount} still blocked on deps${lastBlocked.length ? ': ' + describeBlocked(lastBlocked) : ''})`)
  if (discovery.malformed && discovery.malformed.length) {
    log(`Lint gate excluded ${discovery.malformed.length} issue(s): ${discovery.malformed.map((m) => `#${m.number} (${m.why})`).join('; ')}${cfg.dryRun ? ' (dryRun — reported only, nothing touched)' : ` — commented + labeled ${cfg.blockedLabel}`}`)
  }

  if (cfg.dryRun) {
    log('dryRun — reporting queue without changing anything.')
    return { done: true, dryRun: true, eligible: queue, malformed: discovery.malformed || [], pendingCount: discovery.pendingCount, blocked: discovery.blocked || [], completed: [] }
  }

  for (const m of discovery.malformed || []) {
    if (!attempted.has(m.number)) {
      attempted.add(m.number)
      completed.push({ ticket: m.number, status: 'parked', commit_sha: '', reason: `lint gate: ${m.why}` })
      parkedTotal++
    }
  }

  let landedThisRound = 0

  // ── Parallel path (workers > 1) ──────────────────────────────────────────
  // Same roles as the sequential loop below, but code+review run W-wide in
  // isolated worktrees via a conflict-aware work-stealing pool, and NOTHING
  // reaches `branch` until the serialized Integrate phase — ONE writer, always.
  if (cfg.workers > 1) {
    if (budget.total && budget.remaining() < BUDGET_FLOOR) {
      halted = true
      haltReason = `token budget nearly exhausted (${Math.round(budget.remaining() / 1000)}k left) — stopped cleanly between rounds`
      break
    }
    let batch = queue
    if (cfg.maxTickets > 0) batch = batch.slice(0, Math.max(0, cfg.maxTickets - landedTotal))
    if (batch.length === 0) {
      halted = true
      haltReason = `maxTickets (${cfg.maxTickets}) reached`
      break
    }

    phase('Partition')
    const footprints = await parallel(
      batch.map((t) => () =>
        tryAgent(footprintPrompt(t), {
          ...mechanicalOpts({ label: `footprint-${t.number}`, phase: 'Partition' }),
          schema: FOOTPRINT_SCHEMA,
        }),
      ),
    )
    const loners = batch.filter((t) => !filesOf(footprints, t.number))
    if (loners.length) {
      log(`Write-set unknown for ${loners.map((t) => '#' + t.number).join(', ')} — each runs ALONE (safe reading).`)
    }

    // Worker SLOTS: provisioned once, reused ticket after ticket.
    const width = Math.min(cfg.workers, batch.length)
    const slots = Array.from({ length: width }, (_, i) => ({
      number: i + 1,
      workspace: `${cfg.worktreeRoot || '../.wl-worktrees'}/slot-${i + 1}`,
      branch: `${cfg.branchPrefix}/idle-${i + 1}`,
    }))

    phase('Prep')
    const prep = await tryAgent(prepPrompt(slots), {
      ...mechanicalOpts({ label: `prep-${width}-slots`, phase: 'Prep' }),
      schema: PREP_SCHEMA,
    })
    if (!prep || !prep.ok || !prep.ready || prep.ready.length === 0) {
      // Halt-and-fall-through (not an early return) so the end-of-run marker posts.
      halted = true
      haltReason = `worktree prep failed: ${prep && prep.reason ? prep.reason : 'prep agent terminated'}`
      log(`BLOCKED at worktree prep: ${haltReason}`)
      break
    }
    const readySlots = prep.ready.map((r) => ({ workspace: r.workspace, branch: r.branch }))
    log(`${readySlots.length} worker slot(s) ready; dispatching ${batch.length} ticket(s).`)

    batch.forEach((t) => attempted.add(t.number))
    phase('Build')
    const results = await runPool(batch, readySlots, footprints, journalIssue)

    const ready = results.filter((r) => r && r.status === 'ready')
    const notReady = results.filter((r) => r && r.status !== 'ready')
    const died = batch.length - results.filter(Boolean).length

    // ── Integration: batch-merge first, fall back to one-at-a-time on red ──
    phase('Integrate')
    const integratedNumbers = new Set()
    if (ready.length > 1) {
      const bulk = await tryAgent(batchIntegratePrompt(ready, journalIssue), {
        ...mechanicalOpts({ label: `integrate-batch-${ready.map((r) => r.ticket.number).join('-')}`, phase: 'Integrate' }),
        schema: BATCH_INTEGRATE_SCHEMA,
      })
      if (bulk && bulk.status === 'landed' && Array.isArray(bulk.landed)) {
        for (const l of bulk.landed) {
          const r = ready.find((x) => x.ticket.number === l.number)
          completed.push({
            ticket: l.number,
            status: 'landed',
            commit_sha: l.commit_sha,
            reviewRounds: r ? r.reviewRounds : undefined,
            reason: bulk.reason,
          })
          integratedNumbers.add(l.number)
          landedTotal++
          landedThisRound++
        }
        log(`Batch-merged ${bulk.landed.length} branch(es) with ONE gate run: ${bulk.landed.map((l) => '#' + l.number).join(', ')}`)
      } else {
        const why = bulk ? `${bulk.status}: ${bulk.reason}` : 'batch integrator terminated'
        log(`Batch merge backed out (${why}) — falling back to one-at-a-time to find the culprit.`)
      }
    }

    // Anything the batch did not land (or a single ready branch) goes through
    // the serialized path, which is also how the culprit gets identified.
    const remaining = ready.filter((r) => !integratedNumbers.has(r.ticket.number))
    let pos = 0
    for (const r of remaining) {
      pos++
      const integrated = await tryAgent(integratePrompt(r, pos, remaining.length, journalIssue), {
        ...mechanicalOpts({ label: `integrate-${r.ticket.number}`, phase: 'Integrate' }),
        schema: INTEGRATE_SCHEMA,
      })
      if (!integrated || integrated.status !== 'landed') {
        const status = integrated ? integrated.status : 'failed'
        const reason = integrated ? integrated.reason : 'integrator agent terminated'
        completed.push({ ticket: r.ticket.number, status, commit_sha: '', branch: r.branch, reason })
        if (status === 'conflict' || status === 'gate_red') {
          // Expected, recoverable: branch preserved; the ticket re-runs against the
          // new base via the next discovery round. Close its journal marker so the
          // head-blocker guard doesn't misread the deliberate re-serve as a crash.
          log(`Integration ${status} for #${r.ticket.number}: ${reason} (branch ${r.branch} preserved; re-queued against the new base)`)
          await closeJournalOnHalt(r.ticket, `integration ${status}: ${reason} — branch ${r.branch} preserved, ticket re-queued against the new base`, journalIssue)
          attempted.delete(r.ticket.number)
          continue
        }
        // Push/infra failure: loop-level, same as a sequential landing failure.
        halted = true
        haltReason = `integration failed for #${r.ticket.number}: ${reason}`
        log(`Integration FAILED for #${r.ticket.number}: ${reason}`)
        await closeJournalOnHalt(r.ticket, haltReason, journalIssue)
        break
      }
      completed.push({
        ticket: r.ticket.number,
        status: 'landed',
        commit_sha: integrated.commit_sha,
        reviewRounds: r.reviewRounds,
        reason: integrated.reason,
      })
      landedTotal++
      landedThisRound++
      log(`#${r.ticket.number} landed @ ${integrated.commit_sha}`)
    }

    // Tickets that never produced a ready branch: verified-no-change closes,
    // in-worker parks (already commented/labeled), and halt-mode blocks.
    for (const r of notReady) {
      if (halted) break
      if (r.status === 'no_change_needed') {
        const closed = await tryAgent(closeOnlyPrompt(r.ticket, journalIssue), {
          ...mechanicalOpts({ label: `close-${r.ticket.number}`, phase: 'Integrate' }),
          schema: CLOSE_SCHEMA,
        })
        if (closed && closed.status === 'closed') {
          completed.push({
            ticket: r.ticket.number,
            status: 'closed_no_change',
            commit_sha: closed.evidence_sha || '',
            reviewRounds: r.reviewRounds,
            reason: closed.reason,
          })
          landedTotal++
          landedThisRound++
          log(`#${r.ticket.number} closed, no change needed`)
        } else {
          const reason = closed ? closed.reason : 'close agent terminated (skipped or API error)'
          completed.push({ ticket: r.ticket.number, status: 'failed', commit_sha: '', reason: `close failed: ${reason}` })
          await closeJournalOnHalt(r.ticket, `close (no change needed) failed: ${reason}`, journalIssue)
        }
        continue
      }
      if (r.status === 'parked') {
        // Parked in-worker: findings, label, and journal marker already posted.
        completed.push({ ticket: r.ticket.number, status: 'parked', commit_sha: '', reason: r.reason })
        parkedTotal++
        continue
      }
      // blocked/failed: halt mode, or a park that itself failed.
      completed.push({ ticket: r.ticket.number, status: r.status, commit_sha: '', reason: r.reason })
      if (cfg.onBlocked === 'halt') {
        halted = true
        haltReason = `#${r.ticket.number} ${r.status}: ${r.reason} (work left in its worktree for inspection)`
      }
      await closeJournalOnHalt(r.ticket, `#${r.ticket.number} ${r.status}: ${r.reason}`, journalIssue)
      if (halted) break
    }
    if (died) log(`${died} ticket agent(s) terminated with no result — their journal "Started" markers (if any) will be caught by the next run's head-blocker guard`)

    if (halted || landedThisRound === 0) break
    continue
  }

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

    // ── Shadow footprint (measurement only; changes nothing) ─────────────────
    // Predict BEFORE the coder runs, so the prediction cannot be contaminated
    // by seeing the answer. Scored against what the coder actually staged.
    let predictedFiles = null
    if (cfg.shadowFootprints) {
      const fp = await tryAgent(footprintPrompt(ticket), {
        ...mechanicalOpts({ label: `footprint-${ticket.number}`, phase: 'Coder' }),
        schema: FOOTPRINT_SCHEMA,
      })
      predictedFiles = fp && fp.confidence === 'high' && Array.isArray(fp.files) ? fp.files : null
      log(`shadow: predicted ${predictedFiles ? predictedFiles.length + ' file(s)' : 'UNKNOWN (would run alone)'}`)
    }

    // ── Coder ────────────────────────────────────────────────────────────────
    const coded = await tryAgent(coderPrompt(ticket, journalIssue), {
      ...coderOpts({ label: `coder-${ticket.number}`, phase: 'Coder' }),
      schema: CODER_SCHEMA,
    })

    if (!coded || !['staged', 'no_change_needed'].includes(coded.status)) {
      const status = coded ? coded.status : 'failed'
      const reason = coded ? coded.reason : 'coder agent terminated (skipped or API error)'
      log(`Coder ${status} on #${ticket.number}: ${reason}`)
      // Sync problems are loop-level: every subsequent ticket hits the same wall.
      const loopLevel = /behind origin|dirty tree/i.test(reason)
      if (cfg.onBlocked === 'skip' && !loopLevel) {
        const res = await park(ticket, `Coder ${status}: ${reason}`, completed, journalIssue)
        if (!res.ok) { halted = true; haltReason = res.reason; break }
        parkedTotal++
        continue
      }
      completed.push({ ticket: ticket.number, status, commit_sha: '', reason })
      halted = true
      haltReason = `#${ticket.number} ${status}: ${reason}`
      await closeJournalOnHalt(ticket, haltReason, journalIssue)
      break
    }
    let noChangeNeeded = coded.status === 'no_change_needed'
    log(`${noChangeNeeded ? 'Verified, no change needed' : 'Staged'}: ${coded.summary} (${coded.files_changed.length} file(s))`)

    if (cfg.shadowFootprints && !noChangeNeeded) {
      const score = scoreFootprint(predictedFiles, coded.files_changed)
      footprintScores.push({
        ticket: ticket.number,
        predicted: predictedFiles,
        actual: coded.files_changed,
        ...score,
      })
      if (predictedFiles === null) {
        log('shadow: no usable prediction — would have run alone (no parallelism, but safe)')
      } else if (score.missed.length) {
        log(`shadow: UNSAFE — missed ${score.missed.join(', ')} (a colliding ticket could have run beside this one)`)
      } else {
        log(`shadow: safe${score.extra.length ? ` (over-predicted ${score.extra.length}: costs parallelism only)` : ' (exact)'}`)
      }
    }

    // ── Review loop ──────────────────────────────────────────────────────────
    let approved = false
    let approvedAdditions = ''
    let lastFindings = ''
    let reviewRounds = 0

    for (let iter = 1; iter <= cfg.maxReviewIterations; iter++) {
      reviewRounds = iter
      const reviewed = await tryAgent(reviewerPrompt(ticket, iter, noChangeNeeded), {
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
        approvedAdditions = (reviewed.additions || '').trim()
        log(`APPROVED (iter ${iter})${approvedAdditions ? ` — beyond-scope additions ruled in-spirit, will be surfaced on the issue: ${approvedAdditions.slice(0, 160)}` : ''}`)
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
      const fixed = await tryAgent(fixPrompt(ticket, iter, reviewed.findings), {
        ...fixAgentOpts({ label: `fix-${ticket.number}-i${iter}${isFinalFixRound ? '-esc' : ''}`, phase: 'Coder' }),
        schema: CODER_SCHEMA,
      })

      if (!fixed || fixed.status !== 'staged') {
        lastFindings = `fix round ${iter} ${fixed ? 'failed: ' + fixed.reason : 'terminated'}; outstanding findings: ${lastFindings}`
        break
      }
      noChangeNeeded = false
      log(`Re-staged: ${fixed.summary}`)
    }

    if (!approved) {
      const why = `Review not approved after ${reviewRounds} round(s). Outstanding findings:\n${lastFindings}`
      if (cfg.onBlocked === 'skip') {
        const res = await park(ticket, why, completed, journalIssue)
        if (!res.ok) { halted = true; haltReason = res.reason; break }
        parkedTotal++
        continue
      }
      const reason = `review not approved after ${reviewRounds} round(s): ${lastFindings.slice(0, 240)}`
      log(`STOP — ${reason} (work left STAGED, not committed)`)
      completed.push({ ticket: ticket.number, status: 'blocked', commit_sha: '', reason })
      halted = true
      haltReason = reason
      await closeJournalOnHalt(ticket, haltReason, journalIssue)
      break
    }

    // ── Land ─────────────────────────────────────────────────────────────────
    if (noChangeNeeded) {
      // Coder found it already implemented; the reviewer independently confirmed
      // every acceptance criterion. Close with evidence — nothing to commit.
      const closed = await tryAgent(closeOnlyPrompt(ticket, journalIssue), {
        ...mechanicalOpts({ label: `close-${ticket.number}`, phase: 'Land' }),
        schema: CLOSE_SCHEMA,
      })
      if (!closed || closed.status !== 'closed') {
        const reason = closed ? closed.reason : 'close agent terminated (skipped or API error)'
        log(`Closing FAILED for #${ticket.number}: ${reason}`)
        completed.push({ ticket: ticket.number, status: 'failed', commit_sha: '', reason })
        halted = true
        haltReason = `closing failed: ${reason}`
        await closeJournalOnHalt(ticket, haltReason, journalIssue)
        break
      }
      completed.push({
        ticket: ticket.number,
        status: 'closed_no_change',
        commit_sha: closed.evidence_sha || '',
        reviewRounds,
        reason: closed.reason,
      })
      landedTotal++
      landedThisRound++
      log(`#${ticket.number} closed, no change needed${closed.evidence_sha ? ' (evidence: ' + closed.evidence_sha + ')' : ''}`)
      continue
    }

    const landed = await tryAgent(landPrompt(ticket, journalIssue, approvedAdditions), {
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
      await closeJournalOnHalt(ticket, haltReason, journalIssue)
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

  // Re-discover whenever this round landed something. Do NOT also require
  // pendingCount > 0: that assumed the only source of newly-eligible work is a
  // dependency unblocking, which is false — issues get FILED mid-run (by a human
  // watching, or by this loop's own coders reporting out-of-scope defects they
  // tripped over), and parallel-mode integration conflicts re-queue their tickets
  // deliberately. Neither exists at discovery time, so pendingCount is 0 and the
  // old rule exited announcing "queue drained" while labelled work sat open
  // (observed 2026-08-02: three coder-filed tickets stranded exactly this way).
  // An extra discovery costs one cheap agent; a false "drained" ends the run.
  // Termination is unaffected — an empty queue breaks out above, and MAX_ROUNDS
  // is the backstop.
  if (halted || landedThisRound === 0) break
}

// A ticket can legitimately appear in `completed` more than once — a parallel-mode
// integration conflict records the failed attempt, then the re-run against the new
// base records the landing. Judge the run by each ticket's FINAL state, keep the
// full history in the returned `completed` array.
const finalStates = [...new Map(completed.map((r) => [r.ticket, r])).values()]
const SUCCESS_STATES = ['landed', 'closed_no_change', 'parked']
const failed = finalStates.filter((r) => !SUCCESS_STATES.includes(r.status)).length
log(`\nDone. ${landedTotal} landed/closed, ${parkedTotal} parked (${cfg.blockedLabel}), ${failed} failed, of ${finalStates.length} ticket(s) attempted.${haltReason ? ' Halt: ' + haltReason : ''}`)

// Shadow report: the number that decides whether `workers` > 1 is safe here.
let shadow = null
if (cfg.shadowFootprints && footprintScores.length) {
  const n = footprintScores.length
  const unusable = footprintScores.filter((s) => s.predicted === null).length
  const unsafe = footprintScores.filter((s) => s.predicted !== null && s.missed.length > 0)
  const exact = footprintScores.filter((s) => s.exact).length
  const usable = n - unusable
  shadow = {
    tickets: n,
    exact,
    unusablePredictions: unusable,
    unsafePredictions: unsafe.length,
    // The only number that matters for scheduling: of the predictions we WOULD
    // have scheduled on, how many were safe (no missed file)?
    safeRate: usable ? Number(((usable - unsafe.length) / usable).toFixed(2)) : 0,
    worstOffenders: unsafe.slice(0, 5).map((s) => ({ ticket: s.ticket, missed: s.missed })),
  }
  log(`\nSHADOW FOOTPRINT REPORT (${n} ticket(s))`)
  log(`  exact predictions:      ${exact}/${n}`)
  log(`  no usable prediction:   ${unusable}/${n}  (these would run alone — safe, just slower)`)
  log(`  UNSAFE (missed a file): ${unsafe.length}/${usable} of schedulable predictions`)
  log(`  safe rate:              ${usable ? Math.round(((usable - unsafe.length) / usable) * 100) : 0}%`)
  for (const s of unsafe) log(`    #${s.ticket} missed: ${s.missed.join(', ')}`)
  log(unsafe.length === 0
    ? '  → Prediction never missed a file. Parallel scheduling is safe on this queue.'
    : "  → Each miss is a ticket that could have run beside a colliding one. Tighten the issues' file lists (or keep workers: 1) before going parallel.")
}

// "Drained" must not read as "finished" when work is only transitively stuck — name it.
// Computed before the end-of-run marker below so that marker can say WHY, not just THAT,
// nothing more landed — this is the one thing the marker text used to hardcode wrong.
const drainedReason = lastPendingCount > 0
  ? `Queue drained of eligible work, but ${lastPendingCount} ticket(s) remain — transitively blocked, NOT finished: ${describeBlocked(lastBlocked) || 'discovery did not name them'}`
  : 'Queue drained (nothing pending)'

// End-of-run marker — pure reporting, after all state changes; failure is logged, never
// fatal. Posted even when nothing landed or parked (completed.length === 0): a run that
// died at discovery, or hit the budget floor before finishing a single ticket, still needs
// a durable "I stopped here" record — that record, not the cron, is what makes an overnight
// resume across a multi-day gap possible (see SKILL.md "Overnight resilience").
if (journalIssue) {
  const resultLines = finalStates
    .map((r) => `#${r.ticket} | ${r.status} | ${r.status === 'landed' || r.status === 'closed_no_change' ? (r.commit_sha || 'no change needed') : (r.reason || '').slice(0, 160)}`)
    .join('\n')
  const reported = await tryAgent(reportPrompt(journalIssue, resultLines, haltReason, lastPendingCount, drainedReason), {
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
  done: finalStates.length > 0 && failed === 0 && !halted,
  landed: landedTotal,
  parked: parkedTotal,
  failed,
  journalIssue,
  pendingCount: lastPendingCount,
  blocked: lastBlocked,
  reason: haltReason || (parkedTotal > 0 ? `${drainedReason}; ${parkedTotal} ticket(s) parked for triage under label "${cfg.blockedLabel}"` : drainedReason),
  completed,
  ...(shadow ? { shadow } : {}),
}
