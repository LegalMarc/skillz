# skillz

Skills for legal work and building — public offerings for the legal tech community.

## Skills

### [ai-tos-review](ai-tos-review/)

Rapid, IP-focused triage of an AI tool's Terms of Service before corporate adoption. Built for standard, non-negotiable click-through terms where the decision is up-or-down: it zeroes in on the two questions that can be existential — can the provider train on your data, and do you own the outputs — and deliberately ignores the general terms (liability caps, indemnities) that create risks you can insure against or live with.

Returns a one-line verdict, an employee-facing findings list, and a section-cited, quote-backed addendum for the reviewing attorney. Model-neutral: runs as an agent skill (Claude Code, etc.) or pastes directly into a Claude Project / ChatGPT custom GPT. Ships with a runnable eval set.

**Intended workflow:** require requesters to run this on the terms *before* submitting a legal-review ticket and to include the output in the ticket. Bad terms get caught before legal ever sees them; good ones arrive pre-digested with the key clauses located and quoted. Triage, not clearance — every verdict still routes to a human attorney.

### [cookie-banner-auditor](cookie-banner-auditor/)

Answers the question nobody can actually answer from DevTools: **does the Reject button do anything?** Runs isolated browser contexts for a clean baseline, a verified denial, a Global Privacy Control signal, and an accept control; exercises the page with dwell, scrolling, form-field entry, and site search so tags that fire on engagement rather than load are observed; and produces a 14-section report in Markdown, HTML, and PDF over a hashed evidence bundle of HAR, cookies, storage, and screenshots. Ships a comparison tool so a retest is a diff, not a re-litigation.

Two rules make it usable as evidence. It **never reports a scenario it did not complete** — every finding declares the scenarios it depends on, each scenario records whether its interaction completed *and* whether consent state actually changed, and a finding resting on an incomplete scenario is withheld into `suppressed-findings.json` and listed in the report while the run exits non-zero. (This exists because an earlier version scored a plain `Decline` button below its click threshold, never clicked anything, and then reported "tracking continued after the denial action.") And it **never reports a script load as confirmed tracking** — every request is graded `script_loaded_only` / `beacon_observed` / `identifier_transmitted`, because a correct implementation can deliberately load a tag and gate its transmission. Google Consent Mode does exactly that, and the skill reports it as a favourable informational finding rather than a failure.

Unlike the other skills here it ships executable capture code (Python + Playwright + an installed Chrome, which also renders the PDF). Includes a 19-entry CMP fingerprint table, automated scans for hardcoded analytics identifiers in served markup and for a sale/share mechanism separate from the banner, measured symmetry and WCAG contrast rather than inference from click counts, and 99 test functions (110 checks) — not purely offline, since the browser-backed ones launch a local headless Chromium, but none contacts an external site.

**Intended workflow:** run `--detect-only` on any new property first (seconds, tells you whether the denial control is even reachable), then the full audit; route the PDF to counsel and the remediation table to whoever owns the tag manager. Technical evidence and issue spotting — never a compliance certification.

### [tm-clearance](tm-clearance/)

A US-only trademark clearance workflow: structured seven-question intake (hard gate — no analysis until answered), live USPTO federal search covering registrations *and* pending applications with dead-mark follow-up, common-law digital-footprint sweep (web, app stores, domains, social), Abercrombie strength plus a full refusal-ground screen (§2(e)(1)–(4), §2(c), §2(a), ornamentation/failure to function), an explicit priority determination, 13-factor DuPont analysis, a separate dilution screen, and a source-tagged report built for attorney review.

Two rules make it safe for legal workflows: it **never fabricates registration data** — only records read from a live USPTO/TSDR source this session count as verified, everything else is tagged `[Requires Manual Verification]`, and the same doubt applies to statutory and TMEP pincites — and it **calibrates its searches**, never treating a zero-result query as a clearance until proven syntax has returned a known record. Two screens run outside the confusion analysis because DuPont is blind to them: **priority** (who was first) and **dilution** (a near-copy of a famous mark on unrelated goods scores *well* on DuPont and no examiner will ever raise it). State registries and non-US registers are deliberately excluded and the report says so. A `knockout` mode gives a fast kill/proceed screen on a reduced intake gate, and a `CANDIDATES` list mode compares several names at once. Ships with a runnable eval set including fabrication-resistance, jurisdiction-boundary, and live-dispute tests.

**Intended workflow:** run it on every candidate name *before* anyone falls in love with one; the report routes to attorney review with the key records located, quoted, and pre-verified.

### [workflow-loop](workflow-loop/)

Turn a goal into self-contained GitHub issues, then grind through them **AFK** with a deterministic multi-agent loop: fresh clean-context coder per ticket, independent adversarial reviewer who re-runs all verification, committer that lands with evidence — and blocked tickets are *parked* (work stashed, findings posted to the issue, triage label applied) so an overnight queue never dies at the first stubborn ticket. Model-agnostic: roles are capability tiers and effort levels, not model names. Requires a runtime with a Workflow-style orchestration tool (built for Claude Code).

## Provenance

`ai-tos-review` and `tm-clearance` each ship an `original-prompt.md` — the verbatim chat prompt the skill was distilled from, kept as a historical artifact. If you're converting your own working prompts into skills, the before/after pairs show exactly what conversion adds: the domain expertise carries over nearly untouched, while verification gates, deterministic rubrics, self-checks, and eval sets grow around it.

## License

MIT — see [LICENSE](LICENSE).
