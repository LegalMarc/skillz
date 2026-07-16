# skillz

Skills for legal work and building — public offerings for the legal tech community.

## Skills

### [ai-tos-review](ai-tos-review/)

Rapid, IP-focused triage of an AI tool's Terms of Service before corporate adoption. Built for standard, non-negotiable click-through terms where the decision is up-or-down: it zeroes in on the two questions that can be existential — can the provider train on your data, and do you own the outputs — and deliberately ignores the general terms (liability caps, indemnities) that create risks you can insure against or live with.

Returns a one-line verdict, an employee-facing findings list, and a section-cited, quote-backed addendum for the reviewing attorney. Model-neutral: runs as an agent skill (Claude Code, etc.) or pastes directly into a Claude Project / ChatGPT custom GPT. Ships with a runnable eval set.

**Intended workflow:** require requesters to run this on the terms *before* submitting a legal-review ticket and to include the output in the ticket. Bad terms get caught before legal ever sees them; good ones arrive pre-digested with the key clauses located and quoted. Triage, not clearance — every verdict still routes to a human attorney.

## License

MIT — see [LICENSE](LICENSE).
