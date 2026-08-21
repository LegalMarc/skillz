# workflow-loop — known issues

Defects observed across real multi-day autonomous runs. Each was diagnosed from run evidence, not
theorised — except where a bullet says otherwise (e.g. a code-review pass that demonstrated an
injection on a real shell before it ever bit a live run). Recorded here because they cost real
tokens and real wall-clock, and each is easy to misdiagnose as something else.

---

## 1. A usage-limit kill often takes the park agent with the coder, leaving the ticket un-parked

**Symptom.** A relaunched loop serves the same ticket first, fails the same way, and the cycle repeats.

**Mechanism.** When a session limit terminates a coder mid-ticket, it frequently terminates the park
agent too (`park failed: park agent terminated`). The ticket is left un-parked and therefore still
eligible, so the next discovery pass ranks it first — especially if it carries a high priority label.

**Cost, measured.** On one multi-day run, a single high-priority ticket consumed roughly 11% of the
entire run's token budget this way (~3.5M tokens) across four starved legs. Zero-land legs totalled
about 15% of the run.

**Why the script cannot self-heal it.** The workflow script has no shell access; only agents can call
`gh`. So the guard has to live in the discovery step rather than in the failure handler.

**Suggested fix.** At discovery, exclude any ticket whose issue comments record a prior attempt that
consumed a window and landed nothing, until a park agent or a human clears it. A partial guard of this
shape exists and fires on some tickets, but is not reliable enough to break the repeat-serve loop.

**Status: fixed, with a dependency.** The double-death case leaves no trace on the ticket's own
issue by construction — the ticket's own comments and labels are exactly what the dead park agent
never got to write. So the guard was moved to the one place that keeps an independent record: the
coder now posts a "🟡 Started #N" marker to the run journal before doing anything else, and land/park
each close it out ("✅ Landed #N" / "🛑 Parked #N"). Discovery's head-blocker guard (step 3b) now reads
the journal first: a "Started" with no later "Landed"/"Parked" for that ticket number is treated as
proof a window was already spent, and the ticket is parked before it can be re-served. The older
stash/issue-comment checks stay as a fallback for the (weaker) case where the journal isn't in use.
**Caveat: this needs `reportIssue` enabled.** Without a journal there is nothing to read, and the
guard falls back to the old signals — which is exactly the case that was unreliable. If a run is
worth protecting from this failure mode, turn `reportIssue` on. A run that dies before the coder even
reaches its first action never posts a "Started" marker either, but that's fine: no window was really
spent on that ticket, so re-serving it isn't a defect.

**Update (code review pass).** Two follow-on gaps in this guard, found before either bit a live run:
(a) the primary signal matched `#N` as a bare substring, so checking `#5` could accept `#55`'s
close-out as its own — now anchored to `#N` followed by a space, colon, `@`, or end of line. (b) A
run that halts mid-ticket without landing or parking it (loop-level coder failure, halt-mode block,
halt-mode review exhaustion, landing failure) left the "Started" marker dangling exactly like a crash
would — so a later resume could park fully-approved, already-staged work as a false head-blocker.
Every halt path now posts a closing "⏹️ Halted #N" marker before the run stops, and the guard treats
it the same as "Landed"/"Parked."

---

## 2. Discovery reports "queue drained" while eligible-looking tickets remain

**Symptom.** `done: true` with open, apparently-workable tickets still in the queue.

**Mechanism.** The remaining tickets were transitively blocked by *parked* dependencies. Discovery is
right that nothing is workable, but "drained" reads as "finished" and invites a relaunch that finds the
same wall.

**Observed.** Three "drained" reports in one run. The first two were premature; the third was correct.
Distinguishing them required reading the journal's `reason` field.

**A red herring that costs time.** `journalIssue: 0` looks like a crash but only means discovery exited
before initialising the run log. It is not a malfunction.

**Suggested fix.** Surface the transitive-block reasoning in the drained message itself, so "nothing left"
and "everything left is blocked by A, B, C" are distinguishable without opening the journal.

**Status: fixed.** Discovery now returns a `blocked` array alongside `pendingCount`: one entry per
pending issue naming the still-open dependency refs holding it back. The drained log line and the
run's final `reason` now read "queue drained (nothing pending)" when `pendingCount` is 0, or "queue
drained of eligible work, but N ticket(s) remain — transitively blocked, NOT finished: #A (...), #B
(...)" when it isn't — distinguishable at a glance, no journal read required. The `journalIssue: 0`
red herring is now documented plainly in `SKILL.md`'s Failure modes table.
**Caveat:** the `blocked` array is populated by the discovery agent's own reasoning about dependency
refs, capped for brevity (8 in the log line, more in the returned data, with a "+N more" suffix when
the list runs longer than that so the cap itself is visible) — treat it as a best-effort explanation,
not a guaranteed-complete audit of every blocking edge.

**Update (code review pass).** Two more gaps, found before either bit a live run: the run journal used
to open only after a round found eligible work, so a discovery-agent death (a usage-limit kill, most
dangerously) or a round whose entire remaining queue was transitively blocked posted nothing at all —
on a relaunched run this can leave the journal's last comment stale from an earlier round, misread as
"still alive." The journal now opens before discovery can fail or the queue can turn out empty
(skipped, as always, in `dryRun`, which must never touch GitHub). Separately, the end-of-run marker's
first line was hardcoded to "Finished cleanly" even in the transitively-blocked case above — it was
right that the run *ended*, but wrong about *why* — so it now carries the same drained/blocked
reasoning instead of contradicting it.

---

## 3. Cron-based overnight resume does not fire across a multi-day gap

**Symptom.** A loop halted by a weekly limit sits idle long past the reset, then resumes only when a human
intervenes.

**Mechanism.** Scheduled crons run only while the session is idle-but-alive. A session that is asleep, or
that ended, never fires them. In the observed case the loop sat idle roughly nine hours past its reset.

**What actually saved it.** A halt marker posted as a comment on the run-log issue. That durable, external
record is what let a later session pick the run back up.

**Suggested fix.** Pair every cron-based resume with an external durable marker, and say plainly in the
docs that a cron alone is not a resume mechanism across a multi-day gap. The skill's own "Overnight
resilience" section already describes the right shape — an hourly self-cancelling relauncher with a
liveness check against the journal issue — but that was never actually stood up in the runs observed.

**Status: fixed.** `SKILL.md`'s "Overnight resilience" section is rewritten around the marker as the
primary mechanism and the cron as a convenience layered on top, with the nine-hour case stated as the
concrete example of why a cron alone doesn't survive a multi-day gap. On the code side, the loop now
posts its end-of-run comment even when nothing landed or parked (previously it skipped posting
entirely when `completed.length === 0`, which is exactly the case where a halt marker matters most —
a run that died before finishing a single ticket), and the comment's first line now says plainly
whether the run finished cleanly ("🔴 Run ended") or stopped mid-run ("⏸ HALTED — <reason>"), instead
of using identical wording for both.
**Caveat, unchanged:** none of this helps against a hard kill mid-agent-call — the harness terminates
the whole process, and there is no code left running to post anything. The graceful stop this fix
covers is the one the script can see coming (the token-budget-floor check between tickets); a hard
kill still relies on the per-ticket "Started" marker from defect 1 to reveal, after the fact, which
ticket was mid-flight when it happened — there remains no run-level "a hard kill happened right now"
marker, because nothing survives to write one.

---

## Related operating notes, learned the same way

- **Never hand-edit a shared file mid-run.** A near-miss silently dropped a decisions-log paragraph from a
  commit; it was recovered only because a later coder happened to notice an unstaged file.
- **Stage only your own files.** Check `git diff --cached --name-only` before staging, never `git add -A`,
  and report a pre-populated index rather than committing over it. One incident swept ~1,015 lines of
  unreviewed implementation into an unrelated commit because the index was already populated.
- **Uninterrupted runtime is the dominant lever**, not model choice or prompt tuning. Measured throughput
  on one run was roughly 490k tokens per landed ticket on average, against a floor of about 427k on
  uninterrupted legs.
- **A reviewer/coder reason string is not operator text — never paste it into a double-quoted shell
  string, even with quote-escaping.** Reviewer findings are markdown and routinely contain backticked
  `identifiers`; that is the ordinary case, not the adversarial one. Escaping only `"` leaves backticks
  and `$(...)` live, so a routine finding like `` `hash_secret()` not used `` can mangle or misfire a
  `gh` command, and an adversarial one (e.g. steered through a public repo's issue body) can execute
  with the loop's credentials. Found in a code review pass, not a live run.
  **First fix was incomplete and itself had a gap, found by a second independent review pass — not
  asserted, demonstrated on a real shell each time:** the initial `--body-file -` + quoted heredoc
  (`<<'EOF'`, not `<<EOF`) fix landed on some call sites but not others — the park prompt's own
  issue-facing comment kept the plain double-quoted `--body` twelve lines from the fixed journal
  marker, and the same shape recurred in the land prompt's closing comment. Separately, the heredoc
  mitigation itself was unsafe: its delimiter (`PARK_EOF`/`HALT_EOF`/`REPORT_EOF`) is fixed text in
  this published script, so a bare line matching it inside model-authored text ends the heredoc
  early and the remainder runs as ordinary shell input — demonstrated by embedding a bare `PARK_EOF`
  line followed by a `touch` command and watching the file actually get created. Both are now closed
  by dropping heredocs entirely: every one of these sites writes its body to a scratch file with the
  acting agent's own file-write tool (never a shell string), then passes only that file's PATH to
  `gh ... --body-file` — content that never touches a shell string or heredoc can't be reinterpreted
  by the shell no matter what it contains.
- **`node --check` on this file is not proof it loads.** It's `.js` with top-level `return` (an ES
  module goal fails on that) and `export` (a CommonJS goal fails on that) — it only resolves inside the
  Workflow tool's own wrapper. `node --check` exiting 0 here is an artifact of Node's module-goal
  ambiguity, not evidence of validity. Verify by running it (or the evals), never by syntax-checking it
  standalone.
