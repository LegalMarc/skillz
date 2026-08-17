# Technical audit protocol

## Objective

Determine what the site actually does before a choice, during denial, after denial, on refresh, across subsequent pages, and when Global Privacy Control is present. Preserve enough evidence to reproduce the observations and distinguish cookies from other tracking mechanisms.

## Scope defaults

Use these defaults unless the user specifies otherwise:

- Public, logged-out pages only.
- Homepage or supplied landing page plus up to two safe same-origin links.
- No purchase, account creation, deletion, subscription, download, or login.
- **Form fields are filled but not submitted.** See "Interaction exercises" below.
- Separate browser contexts for baseline, denial, GPC, optional accept control, baseline repeats, and the persistence check.
- Thorough profile by default: 15-second dwell with staged scrolling per page. The quick profile (5-second wait, no exercises, no repeats) systematically under-observes engagement-triggered tags and must be disclosed in the report when used.
- Desktop viewport 1440x1000, English locale, and the actual test machine's timezone unless a specific configuration is requested.
- Raw evidence remains local; use sanitized evidence for research and reporting.

## Interaction exercises

A page view alone does not exercise the tags that matter most. The thorough profile adds:

**Dwell and scroll.** Staged scrolling to 25/50/75/100% with mouse movement and an idle settle, because many advertising and analytics tags fire on scroll depth or a timer rather than on load.

**Form-field entry, without submission.** Visible text, email, and telephone fields are filled with obviously synthetic values and then blurred. Fill-and-blur is what fires form-capture and engagement tags such as HubSpot's `collectedforms.js`, so it exercises the tracking without side effects. Values are chosen to be unmistakable if they ever reach a real system:

| Field | Value | Why |
|---|---|---|
| email | `privacy-audit-test@example.com` | `example.com` is IANA-reserved and undeliverable |
| phone | `+1-555-0100` | reserved fictional US range |
| name / company | `Privacy Audit Test` | self-identifying |
| free text | `AUTOMATED PRIVACY AUDIT - DISREGARD` | self-identifying |

Forms matching login, signup, register, password, payment, billing, checkout, donate, unsubscribe, delete, cancel, account, profile, or address are skipped entirely.

**Submission is opt-in only.** `--submit-forms` actually submits. On a CRM-backed site that creates a real contact record and can trigger sales-notification workflows, so it is off by default, prints a warning, and is recorded in the report's scope table. Confirm with the site owner before enabling it, even on a site they own.

**On-site search.** A benign query is submitted through the site's own search. This is a read-only GET that creates nothing, and site-search terms are frequently forwarded to analytics and advertising platforms, so it is enabled by default.

**Baseline repeats.** The baseline runs more than once. Endpoints present in some runs but not others are reported as unstable — evidence of an A/B test, a geo or cohort experiment, or a flaky tag — and must not be stated as settled fact.

## Scenario matrix

### A. Baseline: no interaction

1. Create a pristine context.
2. Begin HAR and event capture before navigation.
3. Navigate to the supplied URL.
4. Wait for delayed scripts.
5. Capture viewport and full-page screenshots.
6. Capture banner text, controls, dimensions, computed styles, cookie state, local/session-storage key metadata, IndexedDB names, Cache Storage names, service-worker registrations, and available CMP APIs.
7. Close the context to flush the HAR.

Purpose: establish what was transmitted or stored before the user made any choice. Do not treat all first-party or analytics traffic as legally prohibited. Treat known nonessential activity as a failure of the conservative composite baseline and then analyze the applicable law and the banner's promises.

### B. Denial

1. Start a second pristine context and repeat the pre-interaction capture.
2. Search for a direct control such as `Decline All`, `Reject All`, `Only Necessary`, or equivalent.
3. Do not mistake `Do Not Sell or Share` for a complete cookie denial. It may address sale/sharing without disabling analytics, session replay, or other collection.
4. When no direct rejection exists, open settings, disable visible optional categories, and save.
5. If automation cannot reliably identify the control, pause in headed mode for a human choice. Do not guess or click ambiguous controls.
6. Capture immediately after denial.
7. Refresh in the same context and capture again.
8. Visit up to two safe same-origin links and capture each page.
9. Close the context.

Record the control labels, click count, hierarchy, dimensions, styles, and whether accept was available in one step. A successful UI click is not proof that the tag layer honored the preference.

### C. Global Privacy Control

1. Start a third pristine context.
2. Before any page script executes, send `Sec-GPC: 1` and expose `navigator.globalPrivacyControl = true`.
3. Navigate without interacting with the banner.
4. Capture initial state, refresh, and visit the same safe links.
5. Compare advertising, social, targeted-advertising, and sale/share-related flows with baseline and denial.

GPC is not a generic command to stop every analytics request. The report should identify advertising/social endpoints as potentially relevant to sale, sharing, or targeted advertising and separately apply the conservative baseline to other nonessential activity.

### D. Optional accept control

Run a fourth pristine context, click Accept All, and repeat the same capture. This is useful when:

- a cookie or endpoint purpose is uncertain;
- a tag appears only after acceptance and can therefore be classified with greater confidence;
- the site appears to have no meaningful behavioral difference between accept and reject;
- UI symmetry must be measured against a one-click accept path.

Do not use the accept scenario in place of vendor documentation or payload review.

## What to capture

### Network

Capture every request and response available to the browser, including method, URL, resource type, status, redirect chain, initiator where available, request/response headers, and Set-Cookie. HAR content bodies should be omitted by default to reduce data exposure, but raw headers should be retained locally.

### Cookies

For each checkpoint, record:

- name;
- value only in private evidence;
- domain and path;
- creation checkpoint and persistence;
- expiry or session status;
- Secure, HttpOnly, SameSite, and partition-key attributes;
- first-party/third-party heuristic;
- vendor/purpose classification and confidence.

A cookie's name, first-party domain, or CMP category is not conclusive evidence of purpose.

### Non-cookie storage and browser mechanisms

Inspect:

- localStorage and sessionStorage key names, value length, and a hash rather than shareable raw values;
- IndexedDB database names;
- Cache Storage names;
- service-worker scope and script URL;
- accessible consent APIs and strings, including TCF, USP, GPP, and common CMP state;
- document cookies visible to JavaScript;
- console and request failures.

Also look for URL identifiers, ETags, pixels, beacons, fingerprinting libraries, CNAME cloaking, first-party collection endpoints, and server-side tagging. A cookie-only audit is incomplete.

## UI analysis

Assess:

- whether Accept All and Decline All are in the same layer;
- number of actions from first display to completion;
- relative size, contrast, color, placement, and wording;
- whether optional toggles are preselected;
- double negatives or confusing labels;
- whether closing or navigating away is treated as consent;
- whether the banner repeatedly prompts after denial;
- keyboard and screen-reader accessibility;
- whether a separate sale/share opt-out mechanism exists where required.

Automation can identify likely asymmetry but cannot reliably measure every visual or accessibility issue. Review screenshots and, when stakes warrant, perform keyboard and screen-reader testing.

## Scenario validity

Every scenario records the interaction it required, whether that interaction completed, and whether the resulting state change was verified. A consent click is verified by diffing cookies, local storage, CMP API state, and banner visibility across the click. A click the automation reports as successful but which changes none of those has not registered a choice.

A scenario is **invalid** when its required interaction did not complete, or completed without a verifiable state change, or the scenario aborted. An invalid scenario cannot evidence what happens after that interaction. Findings depending on it are withheld into `suppressed-findings.json`, listed in the report, and the run exits non-zero as `INCOMPLETE`.

This exists because a run that never clicked Decline once reported "tracking continued after the denial action" as a critical finding. The evidence for that finding was never captured.

## Classification rules

Use four labels, not a binary legal conclusion:

1. `Observed fact`: directly shown by HAR, state snapshot, screenshot, or DOM/control record.
2. `Fails strict U.S. composite baseline`: violates the deliberately conservative engineering standard.
3. `Potential legal issue`: explain the legal theory and the applicability facts still required.
4. `Inconclusive`: evidence is missing, classification is uncertain, or the tool encountered an error.

Separately, every request carries an **evidence strength** — `script_loaded_only`, `beacon_observed`, or `identifier_transmitted`. Never let a script load stand in for a transmission. A correct implementation can load a tag and gate its transmission; that is what Google Consent Mode does, and it produces script loads with no beacons and a denied `gcs` signal.

Never call an item compliant merely because it is labeled necessary by the CMP. Never call a cookie illegal solely because it appears before consent. Never report that tracking occurred when what was observed is a script fetch.

## Unknown-item research

For every unresolved cookie or endpoint:

1. Identify the script or response that created it.
2. Search the vendor's primary documentation, SDK source, or official cookie list.
3. Inspect request parameter names, payload schema, and response headers without exposing raw values.
4. Confirm the vendor's role and purpose in the site owner's configuration and contract.
5. Use a reputable secondary cookie database only as corroboration.
6. Record the source, date, purpose, recipient, retention, cross-site use, legal role, confidence, and unresolved questions.
7. If uncertainty remains, classify it as unresolved; do not presume necessity.

## Integrity and reproducibility

- Timestamp each scenario and checkpoint in UTC.
- Record target URL, browser executable, locale, timezone, headless/headed mode, egress-region label, proxy use, wait period, and tool version.
- Keep raw and sanitized evidence separate.
- Generate SHA-256 hashes for all files.
- Preserve the original run even after remediation; produce a new run and compare.
- Do not edit raw HAR or screenshots. Make annotations on copies.

## Stop conditions

Stop and report a limitation when:

- the site requires login and no explicit authorization/test account exists;
- a CAPTCHA or access control blocks the public page;
- the flow would submit a form, make a purchase, alter an account, or exercise another person's rights;
- the site appears to be production health, financial, or children data and the proposed run may expose actual user information;
- browser control cannot distinguish a denial choice from an unrelated or destructive control;
- the raw evidence would be uploaded outside the authorized environment.
