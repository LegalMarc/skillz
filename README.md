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

## License

MIT — see [LICENSE](LICENSE).
