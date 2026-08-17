# Cookie Banner Audits That Hold Up

## A technical and legal field guide for counsel

**Current through August 3, 2026**

This guide explains how lawyers can supervise a defensible audit of a website's cookie banner, tracking stack, denial flow, and Global Privacy Control response. It is designed for internal audits, pre-litigation investigations, remediation projects, vendor oversight, and recurring compliance testing.

The central operational premise is simple: do not ask only whether a banner is present. Determine what the browser actually sends and stores before a choice, after the most privacy-protective choice, after refresh and navigation, and while a recognized universal opt-out signal is active.

The project article supplied with this skill correctly emphasizes clean-session capture, pre- and post-choice network evidence, end-to-end signal propagation, GPC, symmetry, persistence, and repeat testing. The article is a project brief, not an authority for every statistic or legal conclusion it contains. This guide therefore grounds the audit method in technical evidence and official regulator materials rather than promotional claims or unverified prevalence estimates.

## 1. What the audit is—and is not

A cookie-banner audit is a controlled observation of a browser-facing system. It answers questions such as:

- What banner and controls were rendered to this visitor at this time and location?
- What requests left the browser before any interaction?
- What cookies and other browser storage appeared?
- What changed when the visitor selected the most privacy-protective choice?
- Did the preference survive refresh and ordinary navigation?
- What happened when GPC was active from the first request?
- Were accept and decline presented symmetrically?
- Which endpoints or storage objects remain unexplained?

A browser audit does not, standing alone, prove:

- that a statute covers the operator or visitor;
- that a recipient is or is not a statutory service provider, contractor, or processor;
- how a recipient uses, combines, retains, or sells data downstream;
- whether a server-side or offline transfer occurred outside the browser's view;
- whether a particular transmission satisfies every element of a wiretap, pen-register, consumer-fraud, or privacy-law claim;
- that the site behaves identically in every geography, browser, device, account state, or experiment cohort;
- that a clean result is a legal certification.

Counsel should treat the scan as evidence and issue spotting. The final legal conclusion requires the operator's coverage facts, data map, contracts, notices, audience, purposes, and applicable-law analysis.

> **Required reporting discipline:** Separate observed fact, strict engineering baseline, potential legal relevance, missing applicability facts, and remediation. Do not collapse those categories into a single label such as “illegal cookie.”

## 2. Why banners fail technically

A banner is only the visible layer of a distributed control system. A typical implementation contains at least five components:

1. **Consent management platform (CMP).** Renders the interface, stores the choice, and may expose a consent API or framework string.
2. **Tag manager.** Decides which scripts, pixels, and endpoints load based on rules, events, page conditions, and consent state.
3. **Website and application code.** Can load vendors directly, set first-party cookies, write browser storage, or call first-party collection endpoints outside the tag manager.
4. **Server-side tagging, customer-data platforms, and reverse proxies.** Can receive data at a first-party-looking endpoint and forward it to other recipients.
5. **Vendors.** Interpret consent signals according to their own configuration, contracts, and product behavior.

The banner can display a successful rejection while another layer continues transmitting. Common failure modes include:

- optional tags load before the CMP initializes;
- the CMP records the choice but never updates the tag manager;
- tags are triggered by page-load events before a consent event arrives;
- direct hard-coded scripts bypass the tag manager;
- server-side containers ignore or strip the consent state;
- a vendor receives a signal but continues a product mode the operator assumed would stop;
- a first-party endpoint collects data and forwards it server-side;
- one page template honors denial while another does not;
- a deployment or A/B test restores an old configuration;
- the preference cookie expires, is scoped to the wrong subdomain, or is not read on later pages;
- GPC is detected only after affected requests have already fired;
- the banner controls collection categories but not the separate legal right to opt out of sale, sharing, or targeted advertising.

The legal team should therefore ask a systems question: **Does the user's preference control the entire data path?** A consent string is evidence of a recorded choice, not proof of enforcement.

## 3. Cookies are only one part of the evidence

The term “cookie audit” is convenient but incomplete. A competent review examines at least the following.

### 3.1 HTTP cookies

A server can send `Set-Cookie` in an HTTP response. JavaScript can write a non-HttpOnly cookie through `document.cookie`. Each cookie should be recorded by name, domain, path, expiration, Secure, HttpOnly, SameSite, partition status, scenario, and first-seen checkpoint.

The value can be highly sensitive. Shareable evidence should retain the name and attributes while replacing the value with a redacted length and hash. The raw value belongs only in restricted evidence when it is genuinely needed.

### 3.2 Local storage and session storage

JavaScript can store identifiers, consent state, experiment assignments, and application data outside cookies. Local storage persists; session storage normally lasts for the tab session. A shareable audit should record key names, origin, length, and a one-way hash—not raw values.

### 3.3 IndexedDB, Cache Storage, and service workers

Modern applications can maintain substantial persistent state in IndexedDB, cache scripts and responses, and register service workers that intercept requests or operate after page load. Record database names, cache names, service-worker scope, and script URL. These artifacts can explain persistence that a cookie-only review misses.

### 3.4 Network requests

The most important evidence is often the request itself. A pixel, `fetch`, script load, image beacon, or form-associated request can transmit IP address, user agent, page URL, identifiers, event data, or form context before a cookie is stored. The audit should record request time, phase, URL with query values redacted, host, path, method, resource type, response status, and same-site status.

### 3.5 Browser and CMP state

The audit should capture:

- `navigator.globalPrivacyControl`;
- the `Sec-GPC` request header;
- cookie names visible to JavaScript;
- CMP API presence, including TCF, USP, GPP, or vendor-specific APIs;
- consent categories or counts exposed by those APIs without unnecessarily preserving full identifiers;
- banner text, controls, click count, toggle state, and screenshots.

## 4. The four-scenario protocol

Do not perform the entire test in one browser session. Use separate, pristine contexts so the scenarios do not inherit cookies, cache, local storage, service workers, or consent state from each other.

### Scenario A: Baseline before any choice

Open a fresh context and start capture before navigation. Load the landing page and wait long enough for delayed tags. Do not click the banner. Capture:

- initial banner and page screenshots;
- cookies and browser storage;
- network requests and responses;
- CMP state;
- delayed requests after the page appears idle.

This scenario answers what happens before any purported consent or denial.

### Scenario B: Denial

Open another fresh context. Capture the same pre-interaction evidence. Then choose the most privacy-protective available option:

1. direct `Decline All`, `Reject All`, `Deny All`, or `Necessary Only`; or
2. settings, all clearly optional toggles off, and save.

Count every interaction. Capture immediately after the action, then refresh and capture again. Visit up to two safe same-origin pages and capture each. Avoid forms, downloads, login, logout, purchases, account changes, or other actions that could alter data or create legal risk.

This scenario tests enforcement and persistence.

### Scenario C: Global Privacy Control

Open a third fresh context with both:

- `Sec-GPC: 1` on outbound requests; and
- `navigator.globalPrivacyControl = true` exposed to page scripts.

Capture the landing page, refresh, and safe internal pages without waiting for the user to click a banner. GPC is a separate signal and should not depend on a consent-banner interaction.

This scenario tests universal opt-out handling. Endpoint presence alone does not prove sale, sharing, or targeted advertising, but advertising or social-tracking traffic under GPC is a high-priority fact requiring investigation.

### Scenario D: Accept control

Open a fourth fresh context, accept all, and repeat the capture. This is a diagnostic control, not a requirement that the business offer an accept-all choice. It helps identify which requests, cookies, and storage are optional because they appear only or primarily after acceptance.

## 5. What a HAR file proves—and what it does not

A HAR is a structured record of browser network activity. It can preserve request and response timing, URLs, methods, status, headers, cookie metadata, and other details depending on capture settings.

A HAR is valuable because it can show that a request occurred before any interaction or after denial. It can also show request headers such as GPC and response headers such as `Set-Cookie`. But it has limits:

- it may omit WebSocket frames, browser-internal traffic, extension traffic, service-worker detail, or content depending on the tool;
- it may not identify the JavaScript initiator without a separate event log or DevTools trace;
- it records browser-visible traffic, not all server-to-server transfers;
- a request to a vendor does not establish the recipient's legal role or downstream use;
- timing close to the denial click may require rerun or initiator analysis to determine whether the request was queued before the click;
- raw HAR files can contain credentials, identifiers, cookie values, URLs, request bodies, and personal information.

The evidence bundle should therefore contain two versions:

- **restricted raw evidence** for counsel and authorized technical personnel; and
- **sanitized shareable evidence** with sensitive values removed while retaining names, structure, timing, hosts, paths, and attributes needed for analysis.

Hash the complete bundle with SHA-256. Preserve the tool version, date, egress location, browser, locale, target pages, waits, and manual interventions. Those details make the capture reproducible and explain variations.

## 6. How to decide whether a cookie or endpoint is “necessary”

“Strictly necessary” is not a vendor label that counsel should accept at face value. It is a functional conclusion tied to the user's requested service and the legal framework.

A useful necessity analysis asks:

1. What exact function does the item perform?
2. What data does it store or transmit?
3. Is the function requested by the user at that moment?
4. Can the requested service reasonably operate without it?
5. Is the same item also used for analytics, advertising, profiling, or secondary purposes?
6. Is the retention period limited to the function?
7. Is the recipient contractually and technically restricted?
8. Does the item operate across sites, accounts, or devices?
9. Does it appear before choice, after denial, under GPC, or only after accept?
10. Does the banner or privacy notice describe it accurately?

Likely candidates for necessary treatment can include security, fraud prevention, CSRF protection, load balancing, authentication for a requested session, shopping-cart state, transaction completion, and storage of the user's privacy preference. Even these require configuration-specific confirmation.

Advertising, behavioral targeting, social pixels, session replay, personalization, experimentation, and ordinary product or audience analytics are usually treated as optional under the strict composite baseline. That baseline is intentionally more conservative than the minimum rule in many U.S. jurisdictions.

## 7. There is no single “strictest U.S. cookie law”

The United States does not have one generally applicable federal cookie-consent rule equivalent to the European ePrivacy framework. Legal requirements arise from a mixture of state privacy statutes, regulations, universal opt-out rules, sensitive-data and consumer-health statutes, child-privacy law, sector rules, regulator deception and unfairness theories, contractual commitments, and the operator's own representations.

For that reason, a useful audit produces two results.

### 7.1 Strict U.S. composite baseline

The skill applies a voluntary conservative baseline intended to create a nationally defensible configuration:

- only narrowly necessary processing before affirmative choice;
- no advertising, targeted advertising, session replay, social pixels, fingerprinting, personalization, experimentation, or nonessential analytics before affirmative choice;
- denial stops all processing represented as optional;
- GPC is honored as an immediate opt-out of sale, sharing, and targeted advertising;
- accept and decline are offered symmetrically;
- optional categories are not preselected;
- silence, closing the banner, or continued browsing is not treated as affirmative consent;
- preference state persists and propagates;
- sensitive, health, and children's data receive opt-in or heightened treatment as applicable;
- the banner does not substitute for a separate statutory rights mechanism where the law requires one.

A failure of this baseline is a control failure. It is not automatically a statutory violation.

### 7.2 Law-specific issue spotting

Counsel then asks which laws and theories apply to the observed fact. The final report should state assumptions and missing facts rather than pretending the browser has answered them.

## 8. California: symmetry, GPC, and separate rights

California's current regulations require relevant methods for requests and consent to be easy to understand and symmetrical. The regulations use a direct example: an interface with `Accept All` and `Preferences` is not symmetrical when acceptance takes one step and the privacy-protective choice requires additional steps; `Accept All` and `Decline All` can provide a symmetrical choice. Visual prominence that favors yes over no is also problematic.

For a covered business that sells or shares personal information, a recognized opt-out preference signal must be processed. California describes signals sent through an HTTP header or JavaScript object and applies the preference to the browser or device and associated profiles as specified in the regulations.

California also makes an important distinction: a cookie banner or cookie controls, by themselves, are not necessarily an acceptable method for opting out of sale or sharing, because cookie controls address collection and do not necessarily stop later sale or sharing. Counsel should test the separate legal-rights implementation, including GPC, account/profile propagation, and downstream vendor handling.

Enforcement actions reinforce the operational point. California authorities have treated CMP and opt-out failures as the business's responsibility, not a defense based on vendor malfunction. They have also scrutinized asymmetric choice architecture. The practical response is continuous verification, not reliance on a CMP deployment ticket.

Questions for counsel:

- Is the operator a covered business and is the tested visitor a California consumer?
- Does the interface seek consent or process a CCPA request to which the symmetry rule applies?
- Is any observed flow a sale or sharing, or is the recipient a compliant service provider or contractor?
- Was GPC present before the first affected transmission?
- Does the site provide an effective separate sale/share mechanism where required?
- Do the banner and privacy notice accurately describe the observed behavior?

## 9. Universal opt-out mechanisms beyond California

Colorado, Connecticut, Oregon, and other states require covered entities to honor recognized universal opt-out mechanisms for specified activities such as sale and targeted advertising. Effective dates, recognized mechanisms, definitions, thresholds, and exemptions differ.

The engineering recommendation is simpler than the legal patchwork: honor GPC nationwide for sale, sharing, and targeted-advertising flows unless counsel documents a reason not to. This reduces geolocation and rule-mapping error and produces a cleaner control environment.

That operational rule still requires legal precision. GPC does not necessarily prohibit every first-party analytics request. Counsel must determine purpose, data fields, recipient, contract status, profiling or advertising use, and applicable statutory definitions.

## 10. FTC deception, unfairness, and dark patterns

Federal risk often arises not from a general cookie-consent statute but from what the business tells the consumer and whether the system behaves consistently with that representation.

Potential FTC and state consumer-protection issues include:

- the interface says optional tracking is off, but it continues;
- denial is temporary or defeated by another identifier;
- the site creates unreasonable friction for the privacy-protective choice;
- optional categories are preselected or confusingly described;
- the banner repeatedly prompts until the user accepts;
- the notice states that the company honors an opt-out signal when the technical stack does not;
- the site uses an interface that steers or misleads a reasonable consumer about the effect of a choice.

The audit should quote or accurately transcribe the relevant representation and pair it with the observed technical behavior. Do not describe every usability defect as a dark pattern. Explain the actual asymmetry, manipulation, misrepresentation, or impairment of choice.

## 11. COPPA and persistent identifiers

COPPA can treat persistent identifiers as personal information when used to recognize a user over time and across sites or online services. Passive tracking can be collection. A limited internal-operations exception can cover specified functions and certain analytics when the identifier is used solely for the permitted internal purpose; it does not provide a general exception for behavioral advertising.

The amended COPPA rule heightens treatment of targeted advertising and third-party disclosures, including separate verifiable parental consent where applicable.

For a child-directed service or a service with actual knowledge of a child under 13, counsel should not rely on the general adult-site cookie analysis. The audit should identify:

- audience and age-screening facts;
- persistent identifiers and cross-site recognition;
- advertising and third-party disclosures;
- internal-operations rationale;
- data retention;
- parental-consent implementation;
- teen protections under applicable state laws.

## 12. Consumer health data and sensitive pages

Health-related browsing creates elevated risk even when HIPAA does not apply. Washington's My Health My Data framework and similar state laws can require consent before collecting or sharing covered consumer health data, subject to statutory exceptions, and separate consent for sharing. Other state comprehensive privacy laws provide opt-in or heightened treatment for sensitive data. The FTC Health Breach Notification Rule and deception theories can also matter.

A visit to a general health article is not automatically regulated health data under every statute. Analyze:

- page and feature context;
- search terms, form fields, appointment or symptom data;
- identifiers and inferences;
- recipient and use;
- operator status;
- precise statutory definitions and exceptions;
- whether the data is within HIPAA scope;
- notice and consent language.

The strict composite baseline should block optional advertising, session replay, and behavioral analytics on sensitive pages until affirmative authorization. Counsel should consider a more restrictive architecture rather than trying to classify every health-related event after collection.

## 13. Wiretap and pen-register theories

A HAR can be important evidence in pixel, session-replay, chat, wiretap, or pen-register disputes. It can show a transmission, timing, host, path, and certain data fields. It does not itself establish all elements of a claim.

Counsel must separately analyze, among other issues:

- the governing statute and current case law;
- interception or acquisition mechanics;
- party status and consent;
- contents versus routing or signaling information;
- device or software characterization;
- purpose, recipient, and use;
- standing, injury, and remedies;
- federal preemption or other defenses;
- arbitration, forum, and limitations issues.

The report should say `potential litigation relevance` and identify the missing elements. It should not declare that an analytics script is a wiretap or pen register merely because it collected an IP address or identifier.

## 14. How counsel should run the engagement

### 14.1 Define the objective

Choose among:

- privileged internal diagnosis;
- routine compliance monitoring;
- pre-launch review;
- vendor validation;
- litigation response;
- remediation retest;
- diligence or acquisition review.

The objective affects privilege, evidence retention, distribution, scope, and report language.

### 14.2 Establish authorization and boundaries

Document the target domains, public or authenticated state, permitted regions, test accounts, pages, actions, and prohibited conduct. Use non-destructive browsing. Do not submit forms, create transactions, bypass access controls, or test unrelated third parties without authorization.

### 14.3 Decide privilege and work-product treatment

Privilege is fact- and jurisdiction-specific. Counsel should decide at the outset:

- who directs the work;
- the legal purpose;
- which personnel and vendors need access;
- whether raw evidence will be held by counsel or a technical team;
- how ordinary-course monitoring is separated from legal advice;
- whether a dual-purpose report should have separate technical and legal sections;
- preservation obligations if a claim or demand is anticipated.

Do not place talismanic privilege labels on a routine business report and assume that resolves the issue. Structure the engagement consistently with the actual legal purpose.

### 14.4 Preserve evidence proportionately

For a point-in-time audit, retain:

- run metadata;
- raw and sanitized HAR;
- screenshots;
- raw and redacted state snapshots;
- event logs;
- cookie and request inventories;
- banner text and action log;
- research sources;
- tool and pattern-library version;
- SHA-256 manifest;
- analyst notes and manual interventions.

Restrict raw evidence. Sanitize before ordinary circulation. Establish retention based on legal, security, and operational needs.

### 14.5 Pair browser evidence with internal evidence

The most useful technical interviews are with the people who own:

- CMP configuration;
- client-side tag manager;
- server-side tag manager;
- analytics and advertising products;
- content-management templates;
- customer-data platform;
- consent and preference database;
- privacy notice and data map;
- vendor contracts;
- deployment and change management.

Ask them to trace each material endpoint from page code through downstream use.

## 15. Questions for engineering and vendors

Use this list during remediation:

1. Which code renders the banner and stores the choice?
2. Which event or API carries the choice to the tag manager?
3. Which tags are blocked by default, and which can fire before CMP initialization?
4. Are any scripts hard-coded outside the tag manager?
5. Are there first-party collection endpoints, CNAMEs, reverse proxies, or server-side tags?
6. How is GPC detected at the edge, page, CMP, tag manager, account, and vendor layers?
7. Does the preference apply to known profiles and other devices where required?
8. Which cookies or storage objects are classified as necessary, and what function supports that classification?
9. Which vendors receive data after denial or under GPC, and why?
10. What contractual restrictions apply to each recipient?
11. How are banner text, category descriptions, and privacy notices kept synchronized with configuration?
12. What happens when the CMP fails to load?
13. What monitoring detects a tag firing without the required state?
14. What deployment gates and regression tests run after a site, tag, CMP, or vendor change?
15. Who owns remediation and who can stop a release?

## 16. Interpreting common findings

### Known advertising pixel before choice

**Observed fact:** A recognized advertising endpoint loaded in the baseline context.

**Baseline result:** Fails the strict composite baseline.

**Legal analysis:** Determine whether the operator is covered, whether the flow is sale, sharing, targeted advertising, or another regulated use, whether a consent representation applies, whether GPC was present, and whether the recipient has a qualifying contract and restricted role.

**Remediation:** Block the tag before initialization or affected transmission, not merely after a cookie is set.

### Analytics after denial

**Observed fact:** Analytics traffic continued during or after denial, refresh, or navigation.

**Baseline result:** Fails the strict composite baseline and may contradict the banner's category promise.

**Legal analysis:** U.S. law does not universally require opt-in for all analytics, but a represented choice that does not control the behavior can create deception risk. Sensitive pages, children, sale/share, and contract facts can alter the analysis.

**Remediation:** Trace CMP-to-tag propagation, hard-coded scripts, consent-mode configuration, and server-side forwarding. Retest with request timing and initiator analysis.

### Banner has Accept All but only a preferences link

**Observed fact:** Acceptance is available in one step; denial requires settings, toggles, and save.

**Baseline result:** Fails the symmetry rule.

**Legal analysis:** California's regulations contain directly relevant symmetry examples when their scope and applicability are satisfied. Other dark-pattern and consumer-protection theories may also matter.

**Remediation:** Add same-layer `Decline All` with comparable visual treatment.

### GPC present but ad endpoints load

**Observed fact:** The browser sent GPC from the first request, but advertising or social-tracking endpoints appeared.

**Baseline result:** Critical failure under the strict composite baseline.

**Legal analysis:** Determine whether the endpoint participates in sale, sharing, or targeted advertising under an applicable universal-opt-out law. Endpoint presence is strong technical evidence but not the complete legal conclusion.

**Remediation:** Enforce GPC at the earliest layer, including edge, CMP, tag manager, server-side container, account profile, and vendor.

### Unknown first-party collection endpoint

**Observed fact:** A path such as `/collect`, `/events`, or `/telemetry` received data on the site's own domain.

**Baseline result:** Inconclusive until purpose is established; unknown is not presumed necessary.

**Legal analysis:** First-party appearance does not resolve recipient, purpose, or downstream forwarding.

**Remediation:** Review source, payload schema, server routing, data warehouse, vendor forwarding, retention, and contract role.

## 17. Remediation architecture

A durable solution is more than editing banner copy.

### 17.1 Default-deny at the earliest practical layer

Optional tags should not load until the relevant state exists. Avoid a race in which tags load and are then told to stop. Use tag-manager consent requirements, script blocking, conditional loading, and edge or server-side enforcement as appropriate.

### 17.2 One authoritative preference model

Define a versioned model mapping:

- user choices;
- CMP categories;
- GPC and other universal signals;
- state rights;
- tag-manager permissions;
- server-side routing;
- vendor modes;
- profile and account propagation.

Avoid independent, inconsistent interpretations in each product.

### 17.3 Fail closed

Decide what happens when the CMP, API, tag manager, or preference service fails. For optional processing, a missing or unreadable state should not become permission.

### 17.4 Separate consent from opt-out rights

A user can decline optional cookies and still need a legally effective sale/share or targeted-advertising opt-out. Conversely, GPC can require suppression even before or without a banner interaction. Implement both paths and reconcile them to the most privacy-protective applicable state.

### 17.5 Verify downstream behavior

Do not stop at a CMP screenshot. Use browser capture, server logs, vendor dashboards, configuration review, test identifiers, and contract confirmation to determine whether downstream systems honor the state.

### 17.6 Maintain a necessary-processing register

For each item allowed before choice or after denial, record:

- owner;
- function;
- data fields;
- legal and operational basis;
- recipient and contract;
- retention;
- page scope;
- security attributes;
- date approved;
- next review date.

This converts “necessary” from a label into an auditable decision.

## 18. Continuous testing and change control

Annual review is not enough for a system that changes weekly. Trigger a scan when any of the following changes:

- CMP or banner configuration;
- tag-manager container;
- server-side tagging;
- website template or content-management system;
- analytics, advertising, replay, personalization, or social vendor;
- privacy notice or category description;
- consent model or retention period;
- GPC mapping;
- regional geofencing;
- new sensitive page, form, audience, or product;
- acquisition or domain migration.

A practical monitoring program combines:

- scheduled synthetic scans;
- deployment-gate tests;
- endpoint allowlists or policy rules;
- alerts for new third-party hosts and cookies;
- periodic manual visual review;
- legal review of unknown or high-risk changes;
- evidence retention sufficient to show detection and remediation.

The control owner should have authority to stop or roll back a release when optional data flows appear without the required state.

## 19. A lawyer's review checklist

Before approving the final report, confirm:

- the tested URL, region, browser, locale, date, and user state are stated;
- each scenario used a fresh context;
- capture began before navigation;
- the initial banner and page were screenshotted;
- denial was the most privacy-protective available choice;
- every denial interaction was counted;
- refresh and at least one or two safe internal pages were tested;
- GPC was expressed by header and JavaScript property;
- accept control was used when useful;
- raw evidence is restricted and shareable evidence is sanitized;
- cookie values and credentials are not reproduced in the report;
- first-party endpoints were not automatically treated as harmless;
- unknowns were researched with primary sources;
- every finding separates observation, baseline, legal relevance, applicability, and remediation;
- no clean result is described as a legal certification;
- server-side, contract, notice, audience, and coverage questions are identified;
- remediation has an owner and objective retest criterion;
- the evidence bundle has a hash manifest.

## 20. Suggested report language

### Limited clean result

> No material issue was observed in this limited, point-in-time, logged-out browser test under the stated conditions. This result is not a certification of compliance and does not establish behavior in other regions, devices, account states, pages, experiments, server-side systems, or downstream recipients.

### Baseline failure without automatic legal conclusion

> The observed request fails the project's strict U.S. composite baseline because it was initiated before any affirmative choice and is classified with high confidence as optional analytics. U.S. law does not universally require prior opt-in for all analytics. Legal significance depends on applicable law, the site's representations, the data transmitted, recipient role and contract, sensitive-data context, and downstream use.

### Post-denial failure

> The denial interaction was completed at [time], but the identified endpoint continued to receive requests during the post-denial, refresh, or subsequent-page phase. This is evidence that the stated preference did not fully control the observed data path. Counsel should determine whether the flow implicates an applicable opt-out, consent, sensitive-data, or deception rule after confirming coverage, purpose, recipient status, and transmitted fields.

### GPC finding

> The test context sent `Sec-GPC: 1` and exposed `navigator.globalPrivacyControl=true` before navigation. The identified advertising-related endpoint nevertheless loaded. This fails the strict composite baseline. Whether it violates a particular universal-opt-out requirement depends on coverage, consumer location, statutory definitions, recipient role, and whether the endpoint is used for sale, sharing, or targeted advertising.

### Unknown purpose

> The browser evidence establishes the existence and timing of the item but not its purpose or downstream use. The item remains unclassified pending source-code or configuration review, primary vendor documentation, and confirmation of data fields, recipient, contract status, retention, and use.

## 21. Suggested internal engagement instructions

Counsel can adapt the following:

> Legal is directing a limited, non-destructive audit of the public website's cookie banner and browser-facing tracking behavior. The technical team is authorized to capture network traffic, browser storage, screenshots, consent-state information, and safe same-origin navigation in isolated test contexts. Do not submit forms, access private areas, bypass controls, alter records, or use production customer credentials. Raw HAR and state files may contain identifiers or sensitive values and must remain in the restricted matter workspace. Provide Legal with a sanitized evidence set, a technical fact report, and a separate list of unresolved purpose, contract, server-side, and applicability questions. Preserve the original evidence and hash manifest.

## 22. Primary authorities and technical references

Verify current versions and effective dates at the time of the audit.

### OpenAI Desktop browser

- OpenAI Help, “Using the built-in browser in the ChatGPT desktop app”: https://help.openai.com/en/articles/20001277-using-the-built-in-browser-in-the-chatgpt-desktop-app

### California

- California Privacy Protection Agency, CCPA regulation updates and effective date: https://cppa.ca.gov/regulations/ccpa_updates.html
- Approved regulations text: https://cppa.ca.gov/regulations/pdf/ccpa_updates_cyber_risk_admt_appr_text.pdf
- CPPA Todd Snyder enforcement announcement: https://www.cppa.ca.gov/announcements/2025/20250506.html
- CPPA Honda enforcement announcement: https://cppa.ca.gov/announcements/2025/20250312.html
- California Attorney General, Healthline settlement: https://oag.ca.gov/node/604800

### Universal opt-out mechanisms and state privacy

- Colorado Attorney General, universal opt-out mechanisms: https://coag.gov/opt-out/
- Colorado Privacy Act resources: https://coag.gov/resources/colorado-privacy-act/
- Connecticut Attorney General, Connecticut Data Privacy Act: https://portal.ct.gov/ag/sections/privacy/the-connecticut-data-privacy-act
- Oregon Department of Justice, universal opt-out announcement: https://www.doj.state.or.us/media-home/news-media-releases/oregon-doj-highlights-new-universal-opt-out-tool-on-data-privacy-day/
- Maryland Attorney General, data privacy: https://oag.maryland.gov/resources-info/Pages/data-privacy.aspx

### Federal Trade Commission and children

- FTC, dark-pattern report announcement: https://www.ftc.gov/news-events/news/press-releases/2022/09/ftc-report-shows-rise-sophisticated-dark-patterns-designed-trick-trap-consumers
- FTC, Turn tracking opt-out consent order: https://www.ftc.gov/news-events/news/press-releases/2017/04/ftc-approves-final-consent-order-online-company-charged-deceptively-tracking-consumers-online
- FTC, COPPA FAQ: https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions
- FTC, amended COPPA rule announcement: https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-finalizes-changes-childrens-privacy-rule-limiting-companies-ability-monetize-kids-data
- FTC, Health Breach Notification Rule resources: https://www.ftc.gov/legal-library/browse/rules/health-breach-notification-rule

### Consumer health and HIPAA

- Washington legislative summary, My Health My Data: https://lawfilesext.leg.wa.gov/biennium/2023-24/Htm/Bill%20Reports/House/1155-S.E%20HBR%20FBR%2023.htm
- HHS HIPAA guidance: https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/index.html

### Browser evidence

- Chrome DevTools, save network requests and HAR: https://developer.chrome.com/docs/devtools/network/reference/#save-all-as-har
- Playwright browser contexts: https://playwright.dev/docs/api/class-browser#browser-new-context

## Conclusion

A cookie banner should be treated as a production control, not a decorative notice. The defensible audit asks what the system did, preserves the evidence, tests the privacy-protective choice and GPC in clean contexts, researches unexplained flows, and keeps technical facts separate from legal conclusions.

The most useful result is not a blanket compliance label. It is a precise map of where preference state succeeds, where it fails, what legal questions the evidence raises, and what the organization must change and retest.

### Five non-negotiables

- Begin capture before navigation in a genuinely clean context.
- Test baseline, denial, persistence, GPC, and an accept control independently.
- Examine network traffic and all material browser storage, not cookies alone.
- Separate observed facts from the conservative baseline and from legal conclusions.
- Preserve the evidence, remediate the full data path, and retest after every material change.

> **Final operating principle:** The question is not whether a banner exists. The question is whether the user's choice controls the data path.
