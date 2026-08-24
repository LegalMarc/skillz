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
    status: { type: 'string', enum: ['staged', 'blocked', 'failed'] },
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
   a dependency cycle, exclude the cycle members and mention it in reason.

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

function coderPrompt(ticket, journalIssue) {
  return `You are the CODER in an autonomous build loop. Work ONLY issue #${ticket.number}.
Repo: ${cfg.repo}   Branch: ${cfg.branch}
${setupPrefix}${ghAuthNote}
1. SYNC GATE: git fetch origin && git status --short
   - If behind origin/${cfg.branch} → return blocked, reason "behind origin".

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
${referenceSection(ticket)}
2c. PRE-FLIGHT STALENESS CHECK — before changing anything, run the ticket's own verification
   commands (its "## Required verification" section if present, otherwise "## Acceptance
   criteria") against the UNTOUCHED tree. The healthy result is that at least one
   ticket-specific command FAILS — that failure is the gap your change exists to close (the
   red half of red–green). The repo-wide gate (${cfg.checkCommand || 'the full check command'})
   passing is expected — the loop only runs on a green baseline — so it does not count.
   If EVERY ticket-specific verification command already passes on the untouched tree, the
   ticket is stale: what it asks for has most likely already shipped (landed by earlier work
   the ticket predates). Do NOT implement a second, parallel version of an existing feature.
   Return status "blocked", reason "pre-flight: ticket's own verification already passes on
   the untouched tree — possibly already implemented; ticket needs human review, not code".
   (No flaky retries here — a pre-flight failure is the expected result, not a problem.)

2d. CHECK FOR RECOVERABLE PRIOR WORK before writing anything new:
   git stash list | grep -E '#${ticket.number}( |$)'
   If a stash for THIS ticket exists, it is a previous attempt that was interrupted
   (crash, usage limit, operator stop) — often already complete and verified. Prefer
   RECOVERING it over re-implementing from scratch:
   - Inspect it first: git stash show -p 'stash@{N}'
   - If it applies cleanly to current main and matches the ticket's intent, apply it
     (git stash apply 'stash@{N}' — apply, do NOT drop), then continue at step 4 and
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
${setupPrefix}${ghAuthNote}
The coder claims its checks pass. Do not trust the claim — verify everything yourself.

1. Read the staged diff: git diff --cached
2. Re-read the ticket's acceptance criteria AND comments: ${gh(`gh issue view ${ticket.number} --repo ${cfg.repo} --comments`)}
3. Re-run the ticket's verification commands yourself — from its "## Required verification"
   section if present, otherwise its "## Acceptance criteria" section.
   ${FLAKY_RULE}
   If the coder disclosed a "passed on retry" flake, re-run that command yourself with
   extra attention — two independent retry-passes may be a flake; a failure is real.
4. ${checkLine}
5. git diff --check (clean).
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

function fixPrompt(ticket, iter, findings) {
  return `You are the CODER addressing review findings for issue #${ticket.number} (fix round ${iter}).
Repo: ${cfg.repo}
${setupPrefix}${ghAuthNote}
Findings (fix each exactly; change nothing else):
${findings}
${cfg.referenceMode ? 'If useful, the reference branch for this ticket (see git branch -a) shows how the original handled this — adapt, do not blind-copy.\n' : ''}${lessonsBlock()}
Then re-run the ticket's verification commands — its "## Required verification" section if present, otherwise its "## Acceptance criteria" section (${gh(`gh issue view ${ticket.number} --repo ${cfg.repo}`)} if needed). ${checkLine}
${FLAKY_RULE}
git diff --check (clean). Re-stage the COMPLETE set: git add <files>; confirm git diff --cached --stat.

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
  const closed = await agent(haltMarkerPrompt(ticket, reason, journalIssue), {
    ...mechanicalOpts({ label: `halt-marker-${ticket.number}`, phase: 'Land' }),
    schema: JOURNAL_SCHEMA,
  })
  if (!closed || closed.status !== 'ok') {
    log(`Could not post the Halted journal marker for #${ticket.number} (${closed ? closed.reason : 'agent terminated'}) — a later resume's head-blocker guard may misread this ticket; check manually if so.`)
  }
}

// ─── Park helper: preserve work, annotate issue, keep the loop grinding ──────

async function park(ticket, why, completed, journalIssue) {
  const parked = await agent(parkPrompt(ticket, why, journalIssue), {
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

  const discovery = await agent(DISCOVER_PROMPT, {
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
    const coded = await agent(coderPrompt(ticket, journalIssue), {
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
    log(`Staged: ${coded.summary} (${coded.files_changed.length} file(s))`)

    // ── Review loop ──────────────────────────────────────────────────────────
    let approved = false
    let approvedAdditions = ''
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
    const landed = await agent(landPrompt(ticket, journalIssue, approvedAdditions), {
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

  // Re-discover only when this round landed something AND issues remain blocked
  // on deps — a land may have unblocked them. Otherwise we're done.
  if (!halted && !(landedThisRound > 0 && discovery.pendingCount > 0)) break
}

const failed = completed.filter((r) => r.status !== 'landed' && r.status !== 'parked').length
log(`\nDone. ${landedTotal} landed, ${parkedTotal} parked (${cfg.blockedLabel}), ${failed} failed, of ${completed.length} attempted.${haltReason ? ' Halt: ' + haltReason : ''}`)

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
  const resultLines = completed
    .map((r) => `#${r.ticket} | ${r.status} | ${r.status === 'landed' ? r.commit_sha : (r.reason || '').slice(0, 160)}`)
    .join('\n')
  const reported = await agent(reportPrompt(journalIssue, resultLines, haltReason, lastPendingCount, drainedReason), {
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
  pendingCount: lastPendingCount,
  blocked: lastBlocked,
  reason: haltReason || (parkedTotal > 0 ? `${drainedReason}; ${parkedTotal} ticket(s) parked for triage under label "${cfg.blockedLabel}"` : drainedReason),
  completed,
}
