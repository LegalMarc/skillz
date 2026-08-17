# Strict U.S. composite baseline and legal issue-spotting rules

## Use of this baseline

There is no single nationwide U.S. rule requiring affirmative consent for every nonessential cookie. The skill therefore applies two separate layers:

1. A **strict U.S. composite baseline** chosen for engineering simplicity, consumer protection, and defensibility. It is intentionally more conservative than the minimum generally required for ordinary analytics under many U.S. laws.
2. A **law-specific issue-spotting analysis** that asks whether the observed flow implicates an applicable statute, regulation, enforcement theory, notice, representation, contract, or sector rule.

Never merge those layers. A failure of the composite baseline is not automatically a legal violation. A clean result under the baseline is not a legal certification.

This reference is current through August 3, 2026. Recheck current official sources at the time of every legal audit.

## Composite baseline

### 1. Before affirmative choice

Permit only processing that is narrowly necessary to deliver a page or service the user requested, maintain security, authenticate a requested session, balance load, complete a transaction, or store the user's privacy choice.

Under this voluntary baseline, block advertising, targeted advertising, cross-context behavioral advertising, session replay, fingerprinting, social pixels, personalization, A/B testing, and nonessential analytics until affirmative consent. This rule is stricter than generally applicable U.S. law and is used to create a clean, nationally deployable default.

### 2. After denial

The most privacy-protective choice must stop all processing that the interface represents as optional. The decision must propagate to the CMP, tag manager, server-side tag container, CDP, SDKs, first-party collection endpoints, and downstream vendors. A denial recorded only in a CMP cookie is not enough.

#### Consent enforced at the transmission layer

Some implementations gate transmission rather than loading. Google Consent Mode is the common case: `gtag.js` loads regardless, and consent state is carried in a `gcs` parameter, with the tag suppressing or redacting what it sends when consent is denied.

Assess this on its own terms rather than collapsing it into "tags loaded, therefore denial ignored":

- **It is not a baseline failure of limb 2.** If no measurement event is transmitted, the denial has been given effect at the point that matters for the data.
- **It is still a failure of limb 1**, before any choice. Loading a third-party script discloses the visitor's IP address, user agent, and referring URL to that vendor. The conservative baseline prefers not loading nonessential tags at all.
- **The evidence is weaker than it looks.** Not observing a beacon is not the same as observing suppression. Confirm against the tag configuration and a payload review before relying on it.
- **Record the signal.** A `gcs=G100` on a request that still fired is affirmative evidence of denied-state transmission. Absence of any Consent Mode signal means the mechanism is not in use, and the load-without-beacon observation is then unexplained rather than reassuring.

Report this as a favourable, informational observation. Never upgrade it to a pass, and never downgrade it to a violation.

### 3. Global Privacy Control

Treat GPC as an immediate opt-out of sale, sharing, and targeted advertising for the browser/device and associated known profile. Do not wait for a banner click. As a conservative operational choice, honor GPC for all U.S. visitors even when geolocation is unavailable or a specific state-law threshold has not been adjudicated.

GPC does not, by itself, necessarily prohibit every first-party analytics flow. Analyze purpose, recipient, contract status, and applicable law.

### 4. Symmetry

Provide Accept All and Decline All in the same layer, with equivalent click count and comparable size, contrast, color, placement, and wording. Do not preselect optional processing. Do not treat silence, closing, or continued browsing as affirmative consent.

### 5. Persistence

Persist the choice across refreshes, ordinary page navigation, and reasonable session boundaries. Do not repeatedly prompt after denial unless a documented expiration, material purpose change, legal change, or user-initiated preference reset justifies a new choice.

### 6. Separate rights

Do not assume that a cookie banner alone implements a statutory sale/share or targeted-advertising opt-out. Test the actual rights mechanism, GPC handling, account/profile propagation, and downstream disclosures.

### 7. Sensitive, health, and children's data

Use opt-in consent for sensitive-data processing unless a narrow applicable exception is documented. Apply sector-specific and state health-data rules. For child-directed services or actual knowledge of a child under 13, apply COPPA and its persistent-identifier rules; targeted advertising and third-party disclosures require heightened treatment and, under the amended rule, separate verifiable parental consent where applicable.

### 8. Evidence and governance

Retain versioned banner text, policy version, timestamp, signal source, choice, browser/device context, CMP record, tag-layer propagation evidence, and test results. Re-run after site, tag-manager, CMP, SDK, or vendor changes.

## Law-specific anchors

### California

California's current regulations require methods for CCPA requests and consent to be easy to understand and symmetrical. They give the example that an `Accept All` plus `Preferences` banner is not symmetrical when acceptance takes one step and the more protective option takes additional steps; an equal choice could be `Accept All` and `Decline All`. The rules also reject visual prominence favoring yes over no.

A business that sells or shares personal information must process a recognized opt-out preference signal. The signal can be delivered through an HTTP header or JavaScript object and applies to the browser/device and associated pseudonymous profiles; if the consumer is known, the rule extends further.

California also states that a cookie banner or cookie controls, by themselves, are not an acceptable sale/share opt-out method because cookie controls address collection rather than necessarily addressing sale or sharing.

Primary sources:

- Current regulations and effective date: https://cppa.ca.gov/regulations/ccpa_updates.html
- Approved regulations PDF: https://cppa.ca.gov/regulations/pdf/ccpa_updates_cyber_risk_admt_appr_text.pdf
- CPPA Todd Snyder enforcement: https://www.cppa.ca.gov/announcements/2025/20250506.html
- CPPA Honda enforcement: https://cppa.ca.gov/announcements/2025/20250312.html
- California DOJ Healthline settlement: https://oag.ca.gov/node/604800

Issue spotting:

- Is the operator covered and is the tested visitor a California consumer?
- Does the observed flow constitute sale or sharing, or is the recipient a compliant service provider/contractor?
- Does the UI seek CCPA consent or process a CCPA request?
- Is GPC received and honored before an affected transmission?
- Does the site have a separate, effective sale/share mechanism where required?
- Does the privacy notice accurately describe the observed flows?

### Colorado

Covered controllers must honor recognized universal opt-out mechanisms for sale and targeted advertising. Colorado currently recognizes GPC and required covered businesses to accept it beginning July 1, 2024. Colorado also requires affirmative consent in specified circumstances, including sensitive data and certain secondary uses; deceptive design does not constitute consent.

Primary sources:

- GPC/UOOM page: https://coag.gov/opt-out/
- Colorado Privacy Act guidance: https://coag.gov/resources/colorado-privacy-act/

### Connecticut

As of January 1, 2025, covered controllers must honor opt-out preference signals for sale and targeted advertising. Connecticut guidance also describes enhanced protections for children and teens.

Primary source: https://portal.ct.gov/ag/sections/privacy/the-connecticut-data-privacy-act

### Oregon

As of January 1, 2026, Oregon residents can use a universal opt-out to stop covered businesses from selling or sharing personal data or using it for targeted advertising.

Primary source: https://www.doj.state.or.us/media-home/news-media-releases/oregon-doj-highlights-new-universal-opt-out-tool-on-data-privacy-day/

### Maryland

Maryland's comprehensive privacy law took effect October 1, 2025 and provides heightened treatment for sensitive data, including health data, precise geolocation, children's data, and other enumerated categories. The Maryland Attorney General states that businesses cannot sell sensitive data.

Primary source: https://oag.maryland.gov/resources-info/Pages/data-privacy.aspx

### Federal Trade Commission

There is no general federal cookie-consent statute equivalent to the EU ePrivacy model. Federal risk often arises from Section 5 deception or unfairness when a business represents that tracking is disabled or a choice is honored but the technical behavior contradicts that representation. The FTC's dark-pattern work also addresses interfaces that steer users into giving up privacy.

Primary sources:

- FTC dark-pattern report announcement: https://www.ftc.gov/news-events/news/press-releases/2022/09/ftc-report-shows-rise-sophisticated-dark-patterns-designed-trick-trap-consumers
- FTC Turn tracking opt-out case: https://www.ftc.gov/news-events/news/press-releases/2017/04/ftc-approves-final-consent-order-online-company-charged-deceptively-tracking-consumers-online

Issue spotting:

- What does the banner or privacy notice expressly and impliedly promise?
- Does clicking denial actually change transmissions and storage?
- Is an opt-out temporary, incomplete, or defeated by another mechanism?
- Is the interface likely to mislead a reasonable consumer about the consequences of the choice?

### COPPA

COPPA can treat persistent identifiers as personal information when they recognize a user over time and across sites or services. Passive tracking can constitute collection. The internal-operations exception is limited: it may cover necessary functions and certain analytics when the identifier is used solely for the permitted internal purpose, but it does not cover behavioral advertising. The amended rule requires separate verifiable parental consent for targeted advertising and other third-party disclosures where applicable.

Primary sources:

- FTC COPPA FAQ: https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions
- FTC final-rule announcement: https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-finalizes-changes-childrens-privacy-rule-limiting-companies-ability-monetize-kids-data

### Consumer health data and health-sector rules

Washington's My Health My Data framework requires consent before collecting or sharing covered consumer health data, subject to statutory exceptions, and requires separate consent for sharing. Health-related browsing and pixels may also implicate other state health-data laws, the FTC Health Breach Notification Rule, HIPAA when the operator and data are within HIPAA's scope, and deceptive-practices theories.

Primary sources:

- Washington legislative summary: https://lawfilesext.leg.wa.gov/biennium/2023-24/Htm/Bill%20Reports/House/1155-S.E%20HBR%20FBR%2023.htm
- HHS HIPAA guidance index: https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/index.html
- FTC Health Breach Notification Rule resources: https://www.ftc.gov/legal-library/browse/rules/health-breach-notification-rule

Do not assume that visiting a health article automatically creates regulated health data under every law. Examine page context, data fields, inferences, recipient, operator status, and statutory definitions.

## Classification language required in reports

Use these formulations:

- `Observed`: a request, cookie, storage key, UI control, or behavior is evidenced.
- `Fails strict U.S. composite baseline`: the flow violates the project's conservative default.
- `Potential California/Colorado/etc. issue`: identify the theory and assumptions.
- `Likely noncompliant, subject to stated applicability facts`: reserve for strong evidence and known coverage.
- `Inconclusive`: evidence or purpose is not established.
- `No issue observed in this limited test`: never write `compliant` based solely on the scan.

## Facts a browser scan cannot establish by itself

- Whether the business meets statutory thresholds or an exemption.
- Whether the visitor is legally protected by a particular state law.
- Whether a recipient is a service provider/processor/contractor under a valid contract.
- The recipient's downstream use, combination, retention, or sale of data.
- Server-side or offline transfers not observable in the browser.
- Consent records stored in back-end systems.
- Whether a wiretap or pen-register cause of action is legally viable.
- Whether a privacy-policy statement is materially misleading in context.
- Whether the same behavior occurs in every region, browser, device, account state, or experiment cohort.
