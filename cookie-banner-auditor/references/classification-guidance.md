# Cookie, storage, and request classification guidance

## Core rule

Classify what was observed, then separately assess likely purpose, necessity, and legal relevance. Do not use a cookie database as a substitute for understanding the actual implementation.

## Evidence objects

### Cookies

Record name, domain, path, first-seen checkpoint, expiration, Secure, HttpOnly, SameSite, partitioning, scenario, and whether the domain is same-site. Retain values only in the restricted raw evidence. A cookie can store consent, security state, session state, analytics identifiers, advertising identifiers, experiments, or unknown data.

### Local and session storage

Record key names, origin, length, and a hash rather than raw values in shareable evidence. Storage can hold identifiers and consent state even when conventional cookies are absent.

### IndexedDB, Cache Storage, and service workers

Record database names, object-store metadata when safely available, cache names, service-worker scope, and script URL. These mechanisms can preserve identifiers, code, or state across page loads.

### Network requests

Record timestamp, phase, URL with query values redacted, host, path, method, resource type, same-site status, response status, and classification. A request can transmit data before any cookie exists.

## Evidence strength: loading is not transmitting

Vendor and category answer *who* and *what for*. They do not answer *did anything actually get sent*. Grade every request on a second axis:

| Role | Evidence strength | What it establishes |
|---|---|---|
| `loader` | `script_loaded_only` | The tag was fetched. The vendor received IP, user agent, and referring URL. **No measurement event is shown to have been sent.** |
| `beacon` | `beacon_observed` | A request reached a known collection endpoint. Payload not inspected. |
| `identifier_bearing` | `identifier_transmitted` | Such a request also carried a value matching a durable identifier pattern. |
| `passive` | `no_transmission_evidence` | An asset fetch with no identifier. |

Known collection endpoints live in `transmission_patterns` in `vendor-patterns.json`. Identifiers are recognised by parameter name (`cid`, `_ga`, `gclid`, `fbp`, `li_fat_id`, ...) or by value shape (GA client id, UUID, `_fbp`, long opaque token).

**Why this matters.** A tag that loads and does not transmit may be a *correct* implementation. Google Consent Mode deliberately loads `gtag.js` and then suppresses or redacts the outbound event, signalling the state in a `gcs` parameter — `G100` is all-denied. Reporting that as "tracking after denial" is simply wrong, and it destroys the credibility of the findings that are right.

Rules:

1. Never state that tracking occurred when what was observed is a script fetch. Say the tag loaded and say what that does and does not establish.
2. Never treat absence of a beacon as proof of correct gating. It is also consistent with an observation window that was too short, a tag that fires on an interaction not exercised, or a cohort difference. Say which.
3. A script load is still a third-party disclosure of IP, user agent, and referring URL. Not transmitting a measurement event does not make it invisible to the vendor.
4. When tags load, no beacon fires, and every observed Consent Mode signal is denied, report `consent-enforced-at-transmission` as informational — a favourable observation, not a failure — and note that payload confirmation is still required.
5. Record the raw `gcs` value. Interpret only the documented set (`G100`, `G101`, `G110`, `G111`, `G1--`); mark anything else unrecognised rather than guessing.

### UI and consent state

Record exact banner text, controls, click count, optional-toggle state, screenshots, CMP API presence, GPC state, and any observable TCF, USP, GPP, or vendor-specific state.

## Purpose categories

Use one principal category and explain mixed functions when needed:

- `consent_management`: records or propagates privacy choices;
- `security`: fraud, abuse, CSRF, bot defense, or authentication protection;
- `session`: maintains a user-requested session or transaction;
- `infrastructure`: routing, load balancing, content delivery, or availability;
- `diagnostics`: error reporting, performance monitoring, or reliability;
- `analytics`: measurement of use, audience, or product behavior;
- `session_replay`: recording or reconstructing user interactions;
- `advertising`: ad measurement, retargeting, audience creation, or conversion tracking;
- `social`: social-platform widgets, pixels, or audience functions;
- `personalization`: content or experience tailoring;
- `experimentation`: A/B or multivariate testing;
- `possible_tracking`: first-party or ambiguous collection endpoint with tracking-like characteristics;
- `unknown`: insufficient evidence.

## Necessity labels

- `possibly_essential`: the observed function could be required for a user-requested service, security, or privacy choice, but confirm configuration.
- `context_dependent`: necessity depends on page, feature, data fields, user request, and implementation.
- `likely_nonessential`: the usual function is optional analytics, advertising, session replay, social tracking, personalization, or experimentation.
- `unknown`: purpose or necessity is unresolved.

Do not use `essential` as an unqualified conclusion unless the report identifies the precise user-requested function and why it cannot reasonably operate without the processing.

## Same-site and first-party limitations

Use registrable-domain comparison as a heuristic. CNAME cloaking, reverse proxies, server-side tag managers, first-party collection endpoints, and corporate domains can make third-party processing appear first-party. A request to the site's own host can still transmit data to another recipient downstream.

## Timing rules

Identify at least:

- before any interaction;
- during the denial interaction;
- immediately after denial;
- after refresh;
- on subsequent same-origin pages;
- while GPC is active;
- after accept control.

A request logged during the denial click may have been initiated by an earlier asynchronous task. Treat close-in-time findings cautiously and confirm with a rerun, initiator analysis, or request blocking when material.

## Research standard

For an unknown item, document:

1. observed name, host, path, timing, and page;
2. script or request initiator when available;
3. parameter names and payload schema without exposing values;
4. response cookies or storage effects;
5. official vendor or source documentation;
6. site-owner configuration and purpose statement;
7. recipient and contract role;
8. retention and downstream use;
9. whether the item changes among baseline, denial, GPC, and accept;
10. confidence and unresolved questions.

Use primary evidence first. Secondary cookie catalogs often contain stale, generic, or configuration-dependent descriptions.

## Materiality triage

Prioritize research when an unknown item:

- appears before choice or after denial;
- persists under GPC;
- is third-party or cross-site;
- uses an identifier-like cookie or storage key;
- appears on health, child-directed, authentication, financial, or other sensitive pages;
- transmits form-field, URL, account, or precise-location data;
- is inconsistent with banner or privacy-notice language;
- changes only after accept, suggesting optional processing.
