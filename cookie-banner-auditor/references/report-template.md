# Final cookie banner audit report template

Use this structure for the reviewed final report. Adapt detail to the evidence, but do not omit the separation between observation, baseline, and law-specific analysis.

# Cookie Banner, Tracking, and Privacy Preference Audit

## 1. Executive summary

State the target, date, location, scenarios, overall technical result, highest-priority findings, and immediate remediation. Use `No material issue observed in this limited test` for a clean result. Never write `certified compliant`.

## 2. Scope and authorization

- target URL and operator;
- requester and authorization basis;
- audit date/time and tool version;
- egress region, browser, locale, viewport, user state, and GPC configuration;
- landing page and internal paths visited;
- included scenarios and waits;
- exclusions, including apps, authenticated areas, other regions, mobile, server-side/offline processing, and contract review.

## 3. Methodology

Explain fresh isolated contexts; baseline, denial, GPC, and accept-control runs; screenshots; state snapshots; raw and sanitized HAR; event logs; inventory generation; purpose research; and SHA-256 manifest.

## 4. Banner and interaction analysis

Quote or accurately transcribe the banner. Identify the CMP when supported. Compare accept and denial paths by layer, click count, size, contrast, placement, wording, and preselection. Describe accessibility or automation limitations.

## 5. Scenario results

### 5.1 Baseline before any choice

List known or likely optional requests, cookies, storage, CMP state, and delayed events.

### 5.2 Denial

Describe the exact interaction and click count. Compare immediate post-denial, refresh, and internal-page behavior. State whether the choice persisted.

### 5.3 Global Privacy Control

State how GPC was expressed and whether sale/share/targeted-advertising-relevant flows appeared. Do not infer legal sale or sharing from endpoint presence alone.

### 5.4 Accept control

Compare incremental cookies, requests, and storage. Explain what this difference suggests and what remains unproven.

## 6. Inventory

Provide tables or attach CSVs for:

- cookies by scenario and checkpoint;
- network requests and endpoints;
- local/session storage, IndexedDB, Cache Storage, and service workers;
- consent signals and CMP state.

For each material item include vendor, observed purpose evidence, likely category, necessity label, confidence, and source.

## 7. Findings

For each finding use exactly these subheadings:

### [ID] [Title]

**Severity:** Critical / High / Medium / Low / Informational  
**Certainty:** High / Medium / Low

**Observed fact.** [Evidence-backed statement.]

**Strict U.S. composite baseline.** [Pass/fail/inconclusive and why.]

**Potential legal relevance.** [Specific theory, not a generic citation dump.]

**Applicability facts needed.** [Coverage, location, data use, recipient role, contract, sensitive context, notice language, etc.]

**Evidence.** [Bundle-relative paths, timestamps, checkpoint, screenshot, HAR/event/inventory references.]

**Recommendation.** [Configuration change, owner, validation, and retest criterion.]

## 8. Global Privacy Control and separate statutory rights

Analyze GPC separately from cookie consent. Determine whether the site exposes and honors a separate sale/share or targeted-advertising mechanism where required. Explain profile propagation and limitations.

## 9. Legal issue-spotting matrix

Use a compact table with columns:

- jurisdiction or authority;
- potentially relevant requirement or theory;
- observed evidence;
- missing applicability facts;
- preliminary assessment;
- responsible reviewer.

Include only authorities relevant to the site, audience, data, location, and observed conduct.

## 10. Unknowns and research queue

List unresolved cookies, endpoints, storage keys, purpose statements, contracts, and server-side flows. State why each matters and the next evidence source.

## 11. Remediation plan

Prioritize:

1. stop optional transmissions before choice and after denial;
2. honor GPC before affected transmissions;
3. provide same-layer symmetric choices;
4. persist and propagate preference state;
5. reconcile banner, notice, CMP, tag manager, server-side tags, and vendors;
6. document necessary-purpose decisions;
7. implement regression testing and change controls.

Assign owner, target date, dependency, and objective retest criterion.

## 12. Limitations

State that the scan is point-in-time, location-specific, logged-out unless otherwise stated, and unable by itself to establish coverage thresholds, exemptions, contractual recipient status, downstream use, server-side/offline transfers, legal elements of wiretap or pen-register claims, or behavior in every cohort.

## 13. Evidence index and integrity

List raw restricted evidence, shareable evidence, screenshots, inventories, reports, tool version, and `manifest.sha256`. State the custody and access restrictions for raw HAR and state files.

## 14. Conclusion

Summarize the observed technical condition, immediate risk-control priorities, and required retest. Do not provide a categorical legal certification unless counsel separately completes the legal and factual analysis necessary to do so.
