# Sample prompts

## Minimal interview trigger

**User:** Scan my website.

**Skill:** What website should I scan?

## URL supplied

**User:** Scan https://www.example.com and tell me whether the cookie banner actually honors Decline All.

Proceed with the public logged-out default. Run baseline, denial, GPC, and accept-control scenarios; capture raw and sanitized HAR files, screenshots, cookies, storage, requests, persistence, and two safe internal pages; research material unknowns; and produce a lawyer-ready draft report.

## California and GPC focus

**User:** Audit https://www.example.com from a California perspective, including GPC and whether the banner is symmetrical.

Use a California egress point when authorized and available. Separate (1) California symmetry and opt-out-signal issue spotting, (2) the strict composite baseline, and (3) technical facts that require contract or data-use confirmation.

## Remediation retest

**User:** We fixed the banner. Rerun the audit and compare it with the prior evidence bundle.

Match prior location, browser, locale, waits, page paths, and scenarios. Preserve both bundles. Report resolved, persistent, regressed, and newly observed items.

## Authenticated area

**User:** Audit the logged-in customer portal.

Ask for authorization and a dedicated test-account method. Keep credentials in the browser only. Warn that raw evidence may contain account identifiers or tokens. Use the narrowest pages and actions necessary; never alter records or submit transactions.
