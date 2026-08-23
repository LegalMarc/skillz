# Prospector — a proposed phase for workflow-loop

**Status:** design, not implemented. Written 2026-08-02 from evidence in a real run.

## The problem it solves

In a nine-ticket run of workflow-loop, every ticket landed with an independent adversarial reviewer that re-ran the full gate. All nine were green. During that same run three serious defects sat untouched in the same codebase:

- `GET /api/users` returned a 500 whenever two users had never signed in
- `GET /api/users` returned every password-mode user's `password_hash`
- the retention purge sweep deleted **no** input documents and recorded success anyway

None were found by the loop. All three were found by a human driving the *real* code path — moto-backed DynamoDB, real seed functions, real client — and noticing the fakes had diverged from reality.

The reason is structural, not a quality failure:

> **The loop verifies tickets. It cannot find what no ticket asked about.**

A coder reads one issue and satisfies its acceptance criteria. A reviewer re-reads the same issue and checks the same criteria harder. Neither is ever asked "what else is wrong here?" — so a defect nobody has written an issue for is invisible to both, forever, no matter how many rounds run.

The loop already *stumbles* onto such defects. In this run, ticket #449 discovered the retention bug while doing unrelated work, correctly judged it out of scope, and documented it at four code sites plus ARCHITECTURE.md. That was exemplary — and it still sat inert as code comments until a human happened to read them. The finding never entered the queue.

## What a prospector is

A phase that runs agents whose job is **not** to close a ticket, but to **open** one. Each hunts for a class of defect by driving real code paths, and files what it finds as a properly-formed issue carrying the loop's own label — so the next Discover round picks it up and the existing coder→review→land machinery fixes it.

It closes the loop: the loop starts finding its own work.

## Why it fits parallelism specifically

Prospecting is **embarrassingly parallel** — every prospector is read-only, touches no shared tree, and cannot conflict with any other. It needs no worktree, no branch, no integration. It is the ideal thing to run at width when the ticket queue is thin, which is exactly when the worker pool would otherwise idle.

It also inverts the economics. Parallelism on a 6-ticket queue saves maybe an hour. Parallelism on prospecting is unbounded: more workers means more of the codebase examined per unit time.

## Prospector lenses

Each lens is a distinct hunt. Diversity matters more than depth — redundant prospectors find the same bug.

| Lens | Hunts for | Grounded in |
|---|---|---|
| **fake-divergence** | Places where test doubles disagree with the real client. Drive the real path (moto, real SDK, real serializer) and compare. | All three bugs above; the Decimal 500; the model-output contract |
| **success-without-effect** | Operations that report success without checking they had any. `deleted.append(x)` after a delete that matched nothing. | The retention sweep |
| **boundary-leak** | Fields crossing an API boundary that shouldn't — credentials, internal ids, PII. Enumerate response shapes, not code. | The `password_hash` leak |
| **empty/null/one** | Behaviour at zero, null, and exactly-one — where sorts, joins and aggregates break. | The `None < None` 500 |
| **doc-code drift** | Comments and docs asserting invariants the code no longer holds. Especially `KNOWN DEFECT` / `TODO` / `FIXME`. | #449's inert comments |
| **dead-guard** | Tests and assertions that cannot fail. Mutate the code under them; if still green, the guard is vacuous. | Issue #451 in the same repo |

## Hard rules

1. **Read-only.** A prospector never edits, stages, commits, or pushes. It files issues. Nothing it does can turn the branch red.
2. **Reproduce before filing.** Every issue must carry a reproduction that was actually executed, against the real path, with its output pasted. An unreproduced suspicion is noise, and noise in the queue is worse than silence — it spends a full coder+reviewer pass on nothing.
3. **Watch it fail.** The reproduction must demonstrate the defect on current `main`. If it can't be made to fail, it isn't a defect and must not be filed.
4. **Self-contained issues.** Same template the loop already requires: Goal, Dependencies, Scope, Out of scope, Acceptance criteria, **Required verification**, Notes. A prospector-filed issue is indistinguishable from a human-filed one.
5. **Dedupe before filing.** Search open *and recently closed* issues first. A prospector that re-files a known defect every run is a denial-of-service on the queue.
6. **Cap the fan-out.** A hard per-run limit on issues filed. A lens that finds forty things has almost certainly found one thing forty times — file the pattern, not each instance.
7. **Never auto-fix.** Filing and fixing must stay separate. The value is that a *fresh* coder, with clean context and an independent reviewer, does the fix.

## Sketch

```
prospect:  N lenses in parallel (read-only, no worktree)
             → each: pick a target area, drive the REAL path, reproduce, dedupe
             → file issues with the loop label
Discover:  next round picks them up like any other ticket
```

Config shape:

```js
prospect: {
  lenses: ['fake-divergence', 'success-without-effect', 'boundary-leak'],
  maxIssuesPerRun: 3,
  when: 'queue-thin',   // 'queue-thin' | 'always' | 'never'
  areas: ['backend/src/'],
}
```

`when: 'queue-thin'` is the interesting default: prospect when there is idle capacity, so it costs wall-clock only when there was nothing better to do.

## Open questions

- **Precision is everything and is unmeasured.** A prospector with low precision poisons the queue faster than it improves the code. It needs a shadow mode of its own — file to a scratch label first, have a human rate them, and only promote to the live label once the hit rate justifies it. Do not skip this.
- **Does a prospector-filed issue need human triage before entering the queue?** Probably yes at first, via a `needs-triage` label the loop ignores.
- **Cost.** A thorough lens is not cheap — it drives real infrastructure and reproduces failures. Worth measuring against the alternative: three production defects that shipped.
- **Reviewer overlap.** Some of this could instead be a broadened reviewer mandate ("also look for X"). Rejected here: it dilutes the reviewer's job, which is to judge *this* diff against *this* ticket, and a diluted reviewer is a worse reviewer.
