---
name: cookie-banner-auditor
description: Audit website cookie banners and privacy-preference flows with ChatGPT Desktop browser control and an instrumented Playwright capture. Use when a user says “scan my website,” supplies a URL for a cookie or tracker audit, asks whether Reject or Decline actually works, requests pre-consent and post-denial cookies or HAR evidence, wants Global Privacy Control tested, needs unknown cookies researched, or wants a lawyer-ready U.S. privacy report. Supports clean isolated sessions, screenshots, raw and sanitized HAR files, cookies and browser storage, safe same-origin navigation, evidence hashing, and conservative federal and state legal issue spotting.
---

# Cookie Banner Auditor

Run an interview-style, evidence-preserving audit of a public website's cookie banner, network traffic, browser storage, denial flow, preference persistence, and Global Privacy Control behavior. Produce technical findings and legal issue spotting without overstating what a browser scan proves.

## Start the interview

1. If the user has not supplied a URL, ask only: **“What website should I scan?”**
2. If the user supplied a URL, do not ask routine setup questions. State the default scope in one sentence and proceed:
   - public, logged-out pages;
   - landing page plus up to two safe same-origin links;
   - fresh isolated contexts for baseline, denial, and GPC;
   - no form submission, purchase, login, logout, download, account change, or destructive action;
   - strict U.S. composite baseline plus law-specific issue spotting.
3. Ask one additional question only when an authenticated page, private environment, regional proxy, test credentials, or unusual authorization boundary is necessary. Never place credentials in chat, a command line, a URL, a HAR, or a report.
4. Confirm that the requester owns, operates, or is authorized to test the site. A simple representation is enough for a public, non-destructive scan. Stop before accessing private systems without authorization.

## Explain the clean-session method

Tell the user that the audit does not delete or alter their ordinary browser profile. Use separate, pristine browser contexts instead. This is safer and more reliable than clearing the user's normal cookies.

Use ChatGPT Desktop's built-in browser for the visible review and permission prompts. Use the instrumented runner for the evidentiary capture because it creates separate contexts and writes HAR, state snapshots, screenshots, inventories, and hashes. Read `references/browser-setup.md` before the first run on a device.

## Run the audit

Resolve script paths relative to this file. Install dependencies only when needed:

```bash
python -m pip install -r scripts/requirements.txt
```

**Always run the pre-flight first.** It loads the page, reports the detected consent platform and every candidate control with its score, and exits without auditing. It takes seconds and answers the one question that determines whether the audit will be meaningful — whether the denial control is reachable:

```bash
python scripts/audit_site.py --url "<TARGET_URL>" --detect-only
```

If the reject control resolves, run the audit. Defaults, unless the user asks otherwise:

```bash
python scripts/audit_site.py \
  --url "<TARGET_URL>" \
  --out "<OUTPUT_DIRECTORY>" \
  --accept-control
```

That runs the **thorough** profile (roughly 15 minutes): 15-second dwell with staged scrolling on every page, form-field entry, on-site search, two baseline repeats, and a fresh-context persistence check. Use `--quick` (about 4 minutes) only for a smoke check, and say so in the report — the quick profile systematically under-observes tags that fire on engagement rather than load.

**Audit mobile, not just desktop.** The default profile is desktop (1440x1000). `--viewport mobile` emulates a Pixel-7-class Android phone — 412x915, touch, and a mobile user agent together, because CMPs branch on all three and a merely narrow desktop context is often still served the desktop banner. `--viewport both` runs the whole set twice, writing a complete bundle per profile under `desktop/` and `mobile/`, and roughly doubles runtime.

Treat the two as independent observations rather than one result with a footnote. Small screens frequently get a different banner: more often a full-screen interstitial, and frequently with decline moved behind a settings layer that is one tap further away than accept. Symmetry, click count, and which controls exist at all can legitimately differ, so a finding present in one profile and absent in the other is evidence about the site, not an inconsistency in the audit. Most traffic is mobile; a desktop-only audit should say so in its scope.

One quirk worth knowing before reading a mobile bundle: a page that declares no `<meta name="viewport">` is laid out near the legacy 980px width even under mobile emulation. That is genuinely what a phone does with such a page, not a measurement artefact.

`--time-budget-min N` caps wall-clock time per device profile. It never drops the baseline or denial scenarios — those are what the findings rest on — only the corroborating work: GPC, the accept control, baseline repeats, policy capture, and the persistence check. Everything dropped is printed to stderr and recorded in the bundle, so a budgeted run can never be mistaken for a thorough one.

Add `--headed` to watch it work. `--manual` requires an interactive terminal and now fails immediately if stdin is not a TTY, instead of silently skipping the pause. Use `--location-label` or `--proxy` when geography matters; the runner also resolves and records the actual egress region unless `--no-geo` is passed.

### Scenarios

1. **Baseline:** fresh context, no interaction.
2. **Denial:** fresh context, capture before interaction, choose the most privacy-protective option, verify the choice registered, capture after, refresh, visit up to two safe same-origin pages, then exercise forms and search.
3. **GPC:** fresh context with `Sec-GPC: 1` and `navigator.globalPrivacyControl=true`. This scenario needs no click, so it stays valid even when control detection fails.
4. **Accept control:** fresh context, accept all, compare against denial. Reveals differential behaviour; not itself a compliance requirement.
5. **Baseline repeats:** identical reruns. Endpoints seen in only some runs are reported as unstable, not as fact.
6. **Persistence:** the post-denial state replayed into a brand-new context, to test whether the choice survives a session boundary.

Each context is created fresh from a throwaway browser profile, and the bundle records an assertion that it held no cookies or storage before navigation. Never reuse a scenario context or the user's ordinary profile.

## Never report a scenario you did not complete

This is the rule that matters most, and the tool now enforces it.

A scenario declares the interaction it required, whether that interaction completed, and whether the resulting state change was verified. Every finding declares which scenarios it depends on. A finding whose scenario did not complete and verify is **withheld**, written to `suppressed-findings.json`, listed in section 12 of the report, and the run is marked `INCOMPLETE` with a non-zero exit code.

Do not work around this. If a denial control exists but was not resolved, add its selectors to `references/cmp-selectors.json` and re-run. Never describe post-denial behaviour from a run where no denial occurred, and never let a scenario's silence read as a pass.

The corollary is that a status must describe what actually happened. Where the settings path switches the optional-category toggles off but no save control resolves — which is the expected shape on CMPs whose `save` list is intentionally empty — the run reports `toggles_disabled_no_save_control` and the `denial-not-committed` finding, not "no denial control was operated." It is still **not** a completed denial: an unsaved preference panel is not a recorded choice, so the scenario stays invalid and dependent findings stay suppressed. If a CMP writes provisional state when a toggle flips, that change is recorded but labelled provisional; do not read it as consent having been registered.

A scenario that fails on a navigation or timeout error is retried once, and both attempts are recorded. A *failed consent interaction* is never retried — that is a real finding, not a flake.

## Distinguish a tag loading from a tag transmitting

Every request observation carries an `evidence_strength`:

| Value | Meaning |
|---|---|
| `script_loaded_only` | The tag was fetched. The vendor received IP, user agent, and referring URL. **No measurement event is shown to have been sent.** |
| `beacon_observed` | A request reached a known collection endpoint. |
| `identifier_transmitted` | Such a request also carried a value matching a durable identifier. |

Tags that load without transmitting can mean the implementation is **correct**: Google Consent Mode deliberately loads `gtag.js` and then suppresses or redacts the outbound event. When tags load, no beacon fires, and the observed Consent Mode signals are all denied, the tool emits `consent-enforced-at-transmission` as an *informational* finding rather than a failure.

State the distinction every time. A script load is not proof consent was ignored — but it is still a third-party disclosure, and absence of an observed beacon within the capture window is weaker evidence than a positive observation. Say which one you have.

## Operate the banner conservatively

Prefer a direct `Reject All`, `Decline All`, `Deny All`, or `Necessary Only` control. If none exists, open settings, disable clearly optional categories, and save. Do not disable a control labeled strictly necessary, essential, security, authentication, fraud prevention, or similar unless the user specifically requests a separate functional test.

Count every interaction required to reach denial, including opening settings, changing toggles, and saving. Capture the rendered text and visual characteristics of accept, reject, settings, toggles, and save controls. Do not infer symmetry solely from labels; compare click count, layer, size, contrast, placement, preselection, and wording.

Treat a `Do Not Sell or Share` mechanism as a separate statutory-rights control unless the banner expressly uses it as the general denial choice. Test GPC separately even when the banner appears to work.

When automation cannot identify a reliable denial control, use manual mode, let the user make the visible denial choice, record that manual intervention, and continue. Never guess-click an ambiguous control.

## Operate the banner conservatively, and prove the click worked

Controls resolve in this order: the known-CMP selector table (`references/cmp-selectors.json`), then text scoring, then — in headed mode with a real terminal — a human. A CMP fingerprint match is preferred because vendors ship stable element ids while button labels vary by site, language, and configuration.

After any consent click, the runner diffs cookies, local storage, CMP API state, and banner visibility. A click Playwright reports as successful but which changes nothing is not a completed denial: it invalidates the scenario and raises `denial-not-registered`.

When adding a CMP to the selector table, never map `save` to the same element as `accept`. The denial fallback is settings → toggles → save, so that mistake converts a denial into an acceptance while reporting a completed denial. The smoke test enforces this structurally. Leaving a CMP's `save` list empty is the correct move when no safe selector exists; the run will report `toggles_disabled_no_save_control` rather than silently clicking accept.

### Symmetry is measured, not inferred

Before either control is clicked, the runner walks the page's **real** keyboard focus order — pressing Tab and reading `document.activeElement` back out across every frame, descending into iframe-hosted CMPs — and records where accept and reject actually land. This is not the DOM `tabIndex` attribute: a control that comes first in markup can be reached last, or never. It also compares each control's computed outline, box-shadow, and border focused versus unfocused, so a suppressed focus ring is caught regardless of what the CSS declares.

Read the reachability fields as three-state. `None` means not measured or not knowable — the traversal hit its Tab-press budget before completing a lap — and must not be reported as "unreachable." Only a completed lap that never saw the control proves it is absent from the focus order. Never state that decline is keyboard-unreachable unless `tab_order_cap_hit` is false.

## Preserve and protect evidence

The output directory contains:

- `audit-report.pdf`, `.html`, and `.md` — the same 14-section report in three formats, all rendered from one source;
- `audit-data.json` (schema 2.0) and `findings.json`;
- `suppressed-findings.json` — findings withheld as unsupported. **Read this before concluding anything is clean.**
- `cookie-inventory.csv` and `request-inventory.csv`, the latter graded by evidence strength;
- `research-queue.md` and `legal-applicability-questionnaire.md`;
- `evidence-private/` with raw HAR and raw browser state;
- `evidence-shareable/` with sanitized HAR, redacted state, screenshots, and event logs;
- `manifest.sha256` covering the bundle;
- `<host>-<timestamp>-CONTAINS-RAW-EVIDENCE.zip` — the complete bundle including raw HAR, with a `READ-ME-FIRST.txt` warning inside.

The archive deliberately includes raw evidence, because a bundle without the HAR is not much use as evidence. The filename and embedded README carry the warning. Raw HAR can contain identifiers, cookie values, authorization material, request bodies, and personal information: do not upload it to chat, send it by ordinary email, or quote its raw values. For routine collaboration build the redacted archive with `--zip-shareable-only`.

Do not fabricate a HAR, screenshot, timestamp, cookie, request, or browser action. When capture fails, preserve the error and label the affected scenario incomplete.

## Exercising the page

The thorough profile fills visible form fields with obviously synthetic values (`privacy-audit-test@example.com` on the IANA-reserved `example.com`; `+1-555-0100` from the reserved fictional range) and blurs each field, which is what fires form-capture and engagement tags. Login, signup, payment, unsubscribe, and account forms are skipped entirely.

**Forms are filled but not submitted by default.** Submission is a side-effecting act: on a CRM-backed site it creates a real contact record and can trigger sales-notification workflows. It requires `--submit-forms`, prints a warning, and is recorded in the report's scope table. Ask the user before enabling it, even on a site they own.

On-site search is submitted by default — it is a read-only GET, and search terms are frequently forwarded to analytics and advertising platforms.

## Classify cookies and requests

Read `references/classification-guidance.md` and `references/vendor-patterns.json`.

Apply these rules:

1. A cookie name or vendor-domain match is a heuristic, not proof of purpose.
2. A first-party domain can still perform tracking or forward data server-side.
3. A third-party domain is not automatically unlawful or nonessential.
4. Network requests matter even when no cookie is written; pixels, local storage, IndexedDB, fingerprinting, and server-side tagging can operate without conventional cookies.
5. `Unknown` means research is required. It does not mean necessary, unlawful, or harmless.
6. Preserve the distinction between observed category, inferred purpose, claimed purpose, and legally relevant use.

## Research unknown items

For every unresolved cookie, storage key, script, or endpoint that could affect a material finding:

1. Inspect the request path, resource type, initiator context, parameter names, response cookie names, and page source or tag-manager configuration when available.
2. Search current primary sources in this order:
   - the site's own source/configuration and privacy disclosures;
   - official vendor cookie or product documentation;
   - official developer documentation or source repository;
   - written confirmation from the site owner or vendor;
   - reputable secondary cookie databases only as corroboration.
3. Record source, access date, vendor, purpose, data fields, recipient role, retention, cross-site use, consent or opt-out behavior, and confidence.
4. Never assign `essential` merely because the site or vendor says so. Explain the function and why it is necessary to the user's requested service.
5. Keep inconclusive items in the research queue and explain the missing evidence.

## Apply the legal framework

Read `references/legal-baseline.md` before writing legal conclusions. At audit time, verify current law and official regulator materials because effective dates, recognized universal opt-out mechanisms, regulations, and enforcement positions change.

There is no single nationwide U.S. rule requiring affirmative consent for every nonessential cookie. Use two separate layers:

1. **Strict U.S. composite baseline:** a deliberately conservative engineering standard that blocks optional analytics, advertising, session replay, personalization, social pixels, fingerprinting, and similar processing until affirmative choice; honors denial and GPC; uses symmetric choices; persists preferences; and applies opt-in treatment to sensitive, health, and children's data where appropriate.
2. **Law-specific issue spotting:** determine whether the observed conduct may implicate an applicable state privacy law, FTC deception or unfairness, COPPA, consumer-health law, sector rule, contractual promise, or other theory.

Never convert a baseline failure into an automatic legal violation. Never call a site `compliant` based only on a browser scan. Do not state that a HAR proves sale, sharing, targeted advertising, wiretapping, a pen register, statutory coverage, recipient status, or downstream use.

Every material finding must contain five separate fields:

- **Observed fact** supported by evidence;
- **Strict U.S. composite baseline result**;
- **Potential legal relevance** with the theory and assumptions;
- **Applicability facts needed** before a legal conclusion;
- **Recommended remediation and retest**.

Use `references/report-template.md` for the final report.

## Finalize the report

The runner creates a draft. Review screenshots and inventories, research material unknowns, complete the legal applicability questionnaire with the user or counsel, and then issue a final report that includes:

1. scope, authorization, date/time, egress region, browser, locale, pages, and exclusions;
2. executive summary and overall risk statement;
3. banner text and interaction analysis;
4. scenario-by-scenario results;
5. cookie, storage, and request inventory with purpose and confidence;
6. GPC and separate statutory-rights analysis;
7. findings with evidence citations to bundle paths and timestamps;
8. unresolved research items;
9. prioritized remediation plan and retest criteria;
10. limitations and an explicit statement that the report is technical evidence and legal issue spotting, not a certification.

A clean scan must be described as `No material issue observed in this limited test`, not `compliant`.

## Compare remediation runs

When the user asks for a retest, run the same URL, region, locale, browser, waits, and page paths into a **new** output directory, preserve both bundles, then:

```bash
python scripts/compare_runs.py --before ./audit-2026-08 --after ./audit-2026-09
```

This emits `comparison-report.md`, `.html`, and `.pdf` covering findings resolved, new, and persisting; severity and evidence-strength changes; endpoints added and removed; and a comparability table. Neither input bundle is modified.

Findings carry stable ids derived from what they are about, not emission order, so the same issue keeps its id across runs.

Read two warnings carefully when they appear. **Run conditions differ** means the fingerprints diverge, so a difference may be caused by the changed conditions rather than by the site. **One or both runs are incomplete** means a scenario did not run, so a finding that "disappeared" may simply not have been tested. Neither is remediation.

An endpoint disappearing is also consistent with an A/B test, a geo difference, or a tag that did not fire this time. Check each run's baseline stability section before calling it a fix.

## Gate a release on the result

Section 9 of the report tells the user to add consent-regression testing. `--assert-no-preconsent-tracking` is that gate:

```bash
python scripts/audit_site.py --url "<TARGET_URL>" --out "<OUTPUT_DIRECTORY>" --quick --headless --assert-no-preconsent-tracking
```

It exits non-zero when advertising, social, or session-replay endpoints are contacted in the baseline scenario — before any consent choice. It is deliberately strict about evidence: only `beacon_observed` and `identifier_transmitted` rows trip it. A `script_loaded_only` row alone does not, because Consent Mode legitimately produces loads without beacons, and a gate that fired on those would be turned off within a week.

The flag is opt-in, so default runs keep their existing exit behaviour. Exit codes: **5** an assertion hit, **4** a scenario was incomplete, **0** clean. Incompleteness takes precedence — a run that did not finish cannot certify anything, and must never be read as a pass.

## Archive what the site says, separately from what it does

Each run stores the text of the site's linked cookie, privacy, and do-not-sell documents under `evidence-shareable/policies/`, each file carrying its source URL, retrieval timestamp, and a SHA-256 of the text. Counsel's first question about any observed behaviour is what the site claimed it would do, and a policy read six weeks later is not the policy that was live during the capture.

**The tool draws no conclusion from this text and does not compare it to the observed behaviour.** A policy saying one thing while the network log shows another is a question for a reviewer, not a finding the scanner is entitled to assert. Say so when you use it.

Fetches happen in a context of their own, so nothing here touches any scenario's consent state, and robots.txt is honoured per origin. Tracking parameters are stripped before fetching: Google's cross-domain linker decorates outbound policy links with `_gl`, which carries the visitor's GA client id, and retrieving the decorated URL would make the audit itself disclose an identifier to the policy host. Anything behind a login is recorded as skipped rather than archived — a login page saved under the name of a privacy policy is worse than no file. `--no-policy-capture` turns it off.

## Read supporting material only when needed

- Browser and clean-state setup: `references/browser-setup.md`
- Capture sequence and stop conditions: `references/technical-protocol.md`
- Classification methodology and evidence strength: `references/classification-guidance.md`
- Legal baseline and official sources: `references/legal-baseline.md`
- Final report structure: `references/report-template.md`
- Known CMP fingerprints and selectors: `references/cmp-selectors.json`
- Output schema for comparisons: `references/data-schema.md`
- Lawyer-facing operating guide: `references/lawyer-guide.md`
- Example user requests: `references/sample-prompts.md`
- Source article treatment: `references/source-note.md`

## Verify the tooling before trusting it

```bash
python scripts/tests/smoke_test.py
```

Covers control detection (including the bare-label regression that once caused a false critical finding), click verification, validity gating and suppression, transmission classification, Consent Mode parsing, the embedded-identifier and rights-mechanism scans, symmetry measurement including real tab order and focus visibility, the unsaved-preference status, scenario retry, the pre-consent assertion gate and its exit codes, CMP table integrity, report rendering, packaging, and run comparison.

Most checks are offline; the browser-backed ones drive a headless Chromium against in-memory fixtures and still need no network.

To see what is *not* covered:

```bash
python -m pip install coverage
python -m coverage run --branch --source=lib,. --omit="*/tests/*" tests/smoke_test.py && python -m coverage report -m --sort=cover
```

Coverage sits around 67%, concentrated where it matters: the pure logic in `checks.py` is the best-covered module and the browser-driving half of `capture.py` the least, which is the intended shape. When adding a check, put the decision in `checks.py` and the driving in `capture.py` — that is what keeps the decision testable. Treat a new uncovered branch in `checks.py` or `analysis.py` as a gap; an uncovered Playwright call path in `capture.py` usually is not. A live site is required only to validate real CMP behaviour and network conditions.
