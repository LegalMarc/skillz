# tm-clearance

A **US-only** trademark clearance workflow in a single, model-neutral skill: structured intake → federal (USPTO) search → common-law digital-footprint sweep → Abercrombie strength and refusal-ground screening → priority determination → 13-factor DuPont analysis → dilution screen → a source-tagged, attorney-review-ready report with strategic recommendations.

> ⚖️ This produces a **preliminary screen**, not a clearance opinion. Every report routes to attorney review, and everything not verified against a live USPTO record is tagged for manual verification.

## Provenance

Distilled from a working chat prompt, preserved verbatim in [`original-prompt.md`](original-prompt.md). The before/after is instructive: the trademark methodology (Abercrombie, DuPont, dead-mark and crowded-field doctrine) carried over nearly intact, while the conversion added the verification machinery — structural definition of "verified," search calibration, prosecution-history mining, and the eval set.

## Scope — what it searches and what it doesn't

| Searched | How |
|---|---|
| USPTO federal register — registrations **and pending applications**, live + dead | Live queries against the USPTO Trademark Search system, records verified via TSDR |
| Owner enforcement history | TTABVUE oppositions and cancellations, where reachable |
| Common law — web commercial use | Mandatory live web search when the session has web access |
| Common law — app stores (Apple, Google Play) | Mandatory live step — direct or via targeted web queries against the store domains |
| Domains (.com/.net/.org/.io/.co) | WHOIS where reachable |
| Social handles (commercial use) | Where reachable; otherwise flagged for manual check |

**Deliberately excluded:** state trademark and business-name registries (Secretary of State databases) — the report says so explicitly, so the reviewing attorney can order a full commercial search when the matter warrants it. Also out of scope: all non-US registers — no WIPO international register, no foreign national offices. A non-US or "global" request gets a stated scope boundary, never a US result dressed up as an answer.

One nuance: **§66(a) Madrid extensions of protection are in scope.** They are US rights sitting in the USPTO database and are searched and cited like any other US application. "No Madrid" means the WIPO international register, not §66(a) records.

What actually runs live depends on the session's tools: with web access the common-law sweep is performed, not just described; without it, the skill still produces the full analysis with every unsearched item honestly tagged `[Requires Manual Verification]` — never a silent skip.

## Why this exists, and how I use it

*From the author — a corporate legal perspective:*

Formal clearance searches are expensive and slow, so in practice most naming decisions get made with either no search at all or a two-minute look at Google. This skill fills that gap: it makes the *methodology* of a proper clearance — the phonetic variants an examiner would test, the coordinated classes, the dead-mark follow-up, the common-law sweep, the DuPont balancing — cheap enough to run on every candidate name, before anyone falls in love with one.

The two rules that make it usable in a legal workflow: it **never fabricates registration data** (anything not read from a live USPTO record this session is tagged `[Requires Manual Verification]`), and it **tags every finding with its source**, so the reviewing attorney spends their time verifying the few facts that matter instead of reconstructing the search. The same doubt now applies to **authorities**: a TMEP section number recalled from training is treated exactly like a registration number recalled from training — verified this session, or stated without a pincite.

For triage there are two lighter modes: `REPORT_DEPTH = knockout` for a fast kill/proceed screen on one mark, and `CANDIDATES` as a list for a comparison matrix across several names at once, which is the mode that actually matches "check it before anyone falls in love with it."

## What makes it portable

The whole skill is one self-contained [`SKILL.md`](SKILL.md) — no bundled scripts, no runtime assumptions. It runs as an auto-triggering agent skill (Claude Code etc.) or pastes directly into a Claude Project / ChatGPT custom GPT. It is **tool-adaptive**: with live web search it performs the digital-footprint sweep itself; without, it still produces the full analytical structure with every unverifiable slot honestly tagged — it degrades to "here is exactly what to verify manually," never to guessing.

## Configure before first use

| Setting | Default | What it does |
|---|---|---|
| `CLIENT_NAME` | `[Client]` | Report header |
| `REPORT_DEPTH` | `full` | `full` = complete 9-section report (full seven-item intake gate); `knockout` = Sections I–IV kill/proceed screen (reduced gate: mark, goods/services, use status) |
| `CANDIDATES` | one mark | Give it a list instead and it runs a comparison matrix across candidates, then routes survivors to full clearance |

## Deploy it

### Claude Code / agent runtimes
Drop (or symlink) the `tm-clearance/` directory into your skills location. The frontmatter auto-triggers on clearance requests — "can we use this name," "is this name taken," "run a knockout search."

### Claude Project / ChatGPT custom GPT
Copy everything in `SKILL.md` below the frontmatter into the project's instructions. Start a chat with the mark and as many of the seven intake answers as you have — the skill extracts what you provided and asks only for the gaps.

## Usage tips

- **Answer intake in one shot.** Paste a brief covering the seven intake items and the skill goes straight to analysis. Partial answers are fine — it asks only for what's missing.
- **Best on a surface with live web search.** The federal and common-law sweeps are real searches; on browsing-disabled surfaces you get the full analysis framework with a manual-verification worklist instead.
- **The appendix is not decorative.** Section IX (search log + set-asides) is the record of thoroughness if the clearance is ever second-guessed. Don't trim it.

## Testing

Runnable evals in [`evals/`](evals/) target the skill's highest-stakes behaviors:

| Eval | Exercises |
|---|---|
| `intake-gate-holds` | No analysis before intake; asks all seven areas; doesn't re-ask what was given |
| `batch-intake-descriptive-threshold` | Extracts a full brief; flags §2(e)(1) as a threshold issue; Supplemental/§2(f) fallback; ITU recommendation |
| `fabrication-resistance-no-tools` | With no live search: zero invented registration data, honest not-searched statements, confidence capped |
| `knockout-mode-respects-depth` | `REPORT_DEPTH=knockout` produces only Sections I–IV on the *reduced* gate, without inventing the ungathered items |
| `priority-inverts-posture` | Determines who is senior before analyzing similarity; no constructive-use priority without a filing; won't resolve priority on an unverified date |
| `dilution-screen-runs-when-dupont-is-clean` | A famous mark on unrelated goods: clean §2(d), CRITICAL overall; states dilution is not an ex parte ground |
| `jurisdiction-boundary-us-only` | An EU/UK request gets a scope boundary, not a US result presented as the answer |
| `live-dispute-stops-and-routes` | A disclosed cease-and-desist stops the workflow and routes to counsel instead of producing a memo |
| `related-party-conflict-is-a-transaction-item` | A JV partner's registration is analyzed *and* escalated as an ownership/consent deal point |
| `does-not-trigger-out-of-scope` | A copyright question does not summon the clearance workflow |

Run each `query` against its `files` with the skill loaded and check against `expected_behavior`. Extend the evals before extending the instructions.

## How it decides (risk rubric)

Overall risk = the **highest** tier triggered, never averaged down:

| Tier | Trigger |
|---|---|
| **CRITICAL** | Identical/near-identical **senior** live mark on identical or closely related goods; substantial dilution risk; generic term; §2(c) with no obtainable consent |
| **HIGH** | Confusingly similar senior live mark or pending application in primary/coordinated class with overlapping channels; likely §2(e) refusal with no credible fallback; likely failure-to-function or ornamentation refusal |
| **MODERATE** | Similar marks but distinguishable goods/channels; descriptiveness with viable §2(f)/Supplemental path; unresolved dead marks or common-law users; indeterminate priority on a serious conflict |
| **LOW** | No similar live marks or pending applications in primary/coordinated classes; inherently distinctive; no non-§2(d) ground in play; clear digital footprint |

Un-run searches cap confidence, not risk: the skill will not rate a mark clear on the strength of searches that never happened. Priority can move a conflict down one tier — but only on verified dates, and never below MODERATE while an examiner would still cite it.

**Two things the confusion analysis alone would miss**, so they run as separate screens: **priority** (a senior client faces a different problem from a junior one, and DuPont does not ask who was first) and **dilution** (a near-copy of a famous mark on unrelated goods scores *well* on DuPont factors 2–4 — §43(c) is where that risk actually lives, and no examiner will ever raise it).
