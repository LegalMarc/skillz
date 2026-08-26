# cookie-banner-auditor

An evidence-preserving audit of a website's cookie banner: does the Reject button actually do anything? Runs isolated browser contexts for a clean baseline, a denial, a Global Privacy Control signal, and an accept control; exercises the page hard enough to trigger tags that fire on engagement rather than load; grades every request by whether a tag merely *loaded* or actually *transmitted*; and produces a 14-section report in Markdown, HTML, and PDF with a hashed evidence bundle behind it.

> ⚖️ This produces **technical evidence and legal issue spotting**, not a compliance opinion. A clean result is reported as *no material issue observed in this limited test* — never as compliance.

## Why this exists

Most cookie-banner review is someone opening DevTools, clicking Decline, squinting at the Network tab, and forming an impression. That impression is usually directionally right and evidentially worthless: it doesn't survive a challenge, it can't be reproduced in six months, and it can't tell the difference between a tag that was blocked and a tag that just didn't happen to fire in the ten seconds someone watched.

This skill makes the *methodology* cheap enough to run on every property: separate pristine contexts per scenario, HAR and state capture at every checkpoint, screenshots, SHA-256 manifest, and a comparison tool so a retest six months later is a diff instead of a re-litigation.

## The two rules that make it trustworthy

**It never reports a scenario it did not complete.** Every scenario records the interaction it required, whether that interaction completed, and whether the resulting state actually changed — verified by diffing cookies, storage, CMP API state, and banner visibility across the click. Every finding declares which scenarios it depends on. A finding resting on a scenario that did not complete is **withheld** into `suppressed-findings.json`, listed in the report so its absence is visible rather than silent, and the run exits non-zero as `INCOMPLETE`.

This exists because an earlier version shipped a false critical finding. Its control detection scored a plain `Decline` button below the auto-click threshold, so it never clicked anything — and then reported "tracking continued after the denial action," describing post-denial behaviour it had never captured. A tool that reaches the right answer by accident is not yet a tool.

**It never reports a script load as confirmed tracking.** Every request is graded:

| Evidence strength | What it establishes |
|---|---|
| `script_loaded_only` | The tag was fetched. The vendor received IP, user agent, and referring URL. **No measurement event is shown to have been sent.** |
| `beacon_observed` | A request reached a known collection endpoint. |
| `identifier_transmitted` | Such a request also carried a value matching a durable identifier. |

The distinction decides whether an implementation is broken or correct. Google Consent Mode *deliberately* loads `gtag.js` and then suppresses or redacts the outbound event, signalling denial in a `gcs=G100` parameter. Reporting that as "tracking after denial" is simply wrong — so when tags load, no beacon fires, and the consent signals are all denied, the skill emits `consent-enforced-at-transmission` as an **informational, favourable** finding rather than a failure. It also refuses to let that become a free pass: a script load is still a third-party disclosure, and *not observing* a beacon is weaker evidence than observing suppression.

## What it does

**Scenarios**, each in a fresh context on a throwaway browser profile, with an assertion recorded in the bundle that the context held no cookies or storage before navigation:

1. **Baseline** — no interaction. What happens before any choice.
2. **Denial** — the most privacy-protective option, verified as having registered, then refresh and same-origin navigation.
3. **GPC** — `Sec-GPC: 1` and `navigator.globalPrivacyControl = true` before page scripts run. Needs no click, so it stays valid even when control detection fails.
4. **Accept control** — for differential comparison. Not a compliance requirement.
5. **Baseline repeats** — identical reruns. Endpoints seen in only some runs are reported as **unstable**, not as fact, which is how A/B tests and flaky tags stop becoming findings.
6. **Persistence** — the post-denial state replayed into a brand-new context, testing whether the choice survives a session boundary.

**Control detection** resolves from a 19-entry CMP fingerprint table (`references/cmp-selectors.json` — HubSpot, OneTrust, Cookiebot, Usercentrics, Sourcepoint, Didomi, TrustArc, Osano, Termly, CookieYes, Iubenda, Quantcast, Complianz, Borlabs, CookieLawInfo, Klaro, Axeptio, Civic, Secure Privacy) before falling back to text scoring. Vendors ship stable element ids; button labels vary by site, language, and configuration. Open shadow roots and cross-origin CMP iframes are both reachable.

One structural safety rule, enforced by a test rather than by review: **a CMP's `save` selector may never be its `accept` control.** The denial fallback is settings → toggles → save, so that mistake silently converts a denial into an acceptance while reporting a completed denial. Four entries had it.

**Exercising the page**, because a page view alone doesn't fire the tags that matter: staged scrolling with dwell, form fields filled with obviously synthetic values (`privacy-audit-test@example.com` on IANA-reserved `example.com`, `+1-555-0100` from the reserved fictional range) and blurred to trigger form-capture tags, and on-site search submitted. **Forms are filled but never submitted by default** — submission creates real CRM records and can trigger sales workflows, so it requires `--submit-forms` and prints a warning. Login, signup, payment, and account forms are skipped entirely.

**Checks that were previously manual**: a scan for durable identifiers hardcoded into served markup (a GA cross-domain linker pasted into a CMS republishes one person's client id to every visitor, and the decoder recovers the creation date), a statutory-rights sweep for a sale/share mechanism separate from the banner, and measured symmetry — rendered size, colour, computed WCAG contrast, and the page's *real* keyboard focus order, walked by pressing Tab and reading focus back out across every frame (a control first in markup can still be reached last, or never) plus whether each control shows a focus ring at all — rather than an inference from click counts.

**What the site says, kept beside what it does**: the linked cookie, privacy, and do-not-sell documents are fetched and stored with source URL, retrieval timestamp, and content hash — because the policy you read six weeks later is not the one that was live during the capture. Nothing compares the text to the behaviour; that stays a reviewer's judgement, not the scanner's. Tracking parameters are stripped first, since a linker-decorated policy URL carries the visitor's GA client id and fetching it would make the audit itself leak an identifier.

## Output

`audit-report.pdf`, `.html`, and `.md` are the same 14-section report rendered from one Markdown source, so they cannot drift. Alongside them: `findings.json`, `suppressed-findings.json` (**read this before concluding anything is clean**), cookie and request inventories as CSV with evidence-strength grading, per-checkpoint screenshots and state, sanitized and raw HAR, and `manifest.sha256`.

Findings carry stable ids derived from what they are about rather than emission order, so the same issue keeps its id across runs and a retest is a real diff:

```bash
python scripts/compare_runs.py --before ./audit-2026-08 --after ./audit-2026-09
```

It warns when run conditions differ (so a change in the tool isn't read as remediation) and when either run was incomplete (so an untested finding isn't read as a fixed one).

## Use it

```bash
python -m pip install -r scripts/requirements.txt

# Pre-flight: what would it click, and why? Seconds, no audit performed.
python scripts/audit_site.py --url https://example.com --detect-only

# Full audit — thorough profile, ~15 minutes
python scripts/audit_site.py --url https://example.com --out ./audit-example --accept-control

# Desktop and mobile, separately reported (~2x runtime)
python scripts/audit_site.py --url https://example.com --out ./audit-example --viewport both
```

`--viewport mobile` emulates a Pixel-7-class phone — narrow viewport, touch, and a mobile user agent together, since CMPs branch on all three and a merely narrow desktop context is usually served the desktop banner. Small screens routinely get a different banner, often with decline one tap further away than accept, so `both` writes a complete bundle per profile rather than merging them: a finding in one and not the other is evidence about the site, not noise.

Exit `4` means the run completed but a required interaction did not — findings depending on it were withheld. That is not a crash; it is the tool declining to answer a question it couldn't test. Usually fixed by adding the CMP's selectors to `references/cmp-selectors.json`.

Add `--assert-no-preconsent-tracking` to turn an audit into a release gate: exit `5` when advertising, social, or session-replay endpoints are contacted before any consent choice. It only trips on an observed beacon or a transmitted identifier, never on a bare script load — Consent Mode legitimately produces those, and a gate that cried wolf would be switched off. Incompleteness still wins: a run that didn't finish can't certify anything.

```bash
python scripts/tests/smoke_test.py   # 141 test functions, 216 checks; launches a real Chromium locally, no external site visits
```

## What makes it different from the other skills here

This one ships executable capture code, not just a `SKILL.md`. It needs Python 3.10+, Playwright, and an installed Chrome, Edge, or Chromium — Chrome also renders the PDF, so there's no extra dependency for that. The `SKILL.md` still carries the judgment (scope, authorization, conservative operation, the legal framework and its limits); the scripts carry the evidence handling that a chat-only skill can't do.

## Handling the evidence

Raw HAR contains cookie values, `Set-Cookie` and authorization headers, query strings, and request bodies. The bundle keeps it in `evidence-private/` and the default archive is named `<host>-<timestamp>-CONTAINS-RAW-EVIDENCE.zip` with a warning README inside — a bundle without the HAR isn't much use as evidence, so the risk is made visible rather than removed. For routine collaboration, `--zip-shareable-only` produces a redacted archive where values are replaced by hashes and names are retained.

Only audit sites you own or are authorized to test. The skill asks for that representation and will not bypass a CAPTCHA or access control.

## Legal framing

Two layers, never merged. A **strict U.S. composite baseline** — a deliberately conservative engineering standard, stricter than generally applicable U.S. law — and separate **law-specific issue spotting** that names the theory and the applicability facts still required. A baseline failure is not automatically a violation, and every material finding carries observed fact / baseline result / potential legal relevance / applicability facts needed / recommendation as distinct fields. `references/legal-baseline.md` cites primary regulator sources and is dated; re-verify at audit time, because effective dates and recognized signals change.
