# skillz

Skills for legal work and building — public offerings for the legal tech community.

## Skills

### [ai-tos-review](ai-tos-review/)

Rapid, IP-focused triage of an AI tool's Terms of Service before corporate adoption. Built for standard, non-negotiable click-through terms where the decision is up-or-down: it zeroes in on the two questions that can be existential — can the provider train on your data, and do you own the outputs — and deliberately ignores the general terms (liability caps, indemnities) that create risks you can insure against or live with.

Returns a one-line verdict, an employee-facing findings list, and a section-cited, quote-backed addendum for the reviewing attorney. Model-neutral: runs as an agent skill (Claude Code, etc.) or pastes directly into a Claude Project / ChatGPT custom GPT. Ships with a runnable eval set.

**Intended workflow:** require requesters to run this on the terms *before* submitting a legal-review ticket and to include the output in the ticket. Bad terms get caught before legal ever sees them; good ones arrive pre-digested with the key clauses located and quoted. Triage, not clearance — every verdict still routes to a human attorney.

### [tm-clearance](tm-clearance/)

A US-only trademark clearance workflow: structured seven-question intake (hard gate — no analysis until answered), live USPTO federal search with dead-mark follow-up, common-law digital-footprint sweep (web, app stores, domains, social), Abercrombie strength and §2(e) screening, 13-factor DuPont analysis, and a source-tagged report built for attorney review.

Two rules make it safe for legal workflows: it **never fabricates registration data** — only records read from a live USPTO/TSDR source this session count as verified, everything else is tagged `[Requires Manual Verification]` — and it **calibrates its searches**, never treating a zero-result query as a clearance until proven syntax has returned a known record. State registries and non-US registers are deliberately excluded and the report says so. A `knockout` mode gives a fast kill/proceed screen for triaging candidate-name lists. Ships with a runnable eval set including a fabrication-resistance test.

**Intended workflow:** run it on every candidate name *before* anyone falls in love with one; the report routes to attorney review with the key records located, quoted, and pre-verified.

### [workflow-loop](workflow-loop/)

Turn a goal into self-contained GitHub issues, then grind through them **AFK** with a deterministic multi-agent loop: fresh clean-context coder per ticket, independent adversarial reviewer who re-runs all verification, committer that lands with evidence — and blocked tickets are *parked* (work stashed, findings posted to the issue, triage label applied) so an overnight queue never dies at the first stubborn ticket. Model-agnostic: roles are capability tiers and effort levels, not model names. Requires a runtime with a Workflow-style orchestration tool (built for Claude Code).

## Provenance

`ai-tos-review` and `tm-clearance` each ship an `original-prompt.md` — the verbatim chat prompt the skill was distilled from, kept as a historical artifact. If you're converting your own working prompts into skills, the before/after pairs show exactly what conversion adds: the domain expertise carries over nearly untouched, while verification gates, deterministic rubrics, self-checks, and eval sets grow around it.

## License

MIT — see [LICENSE](LICENSE).
