# Source note: attached article

The user-provided article is the project brief, not an independently verified legal authority. It supports the following design requirements:

- A banner can be ornamental when it is not wired to gate the tag manager or downstream vendors.
- An audit should preserve network traffic before and after consent interactions.
- A denial choice should suppress nonessential tracking and persist across pages and sessions.
- Consent signals must propagate from the CMP to client-side tags, server-side tags, and vendors.
- Global Privacy Control should be tested separately.
- Acceptance and rejection should be assessed for asymmetry and friction.
- Monitoring must be repeatable because site changes can break consent tooling.
- Consent and test records should be retained as evidence.

Do not adopt the article's unsubstantiated percentage claims, litigation generalizations, or vendor marketing statements as fact. Do not repeat its claim that a broken banner is always worse than no banner or that every malfunction creates statutory damages. The audit must separate observed behavior, a conservative engineering baseline, possible legal relevance, and facts still needed for a legal conclusion.

The article's practical audit direction is sound: use a clean session, compare traffic before and after denial, test GPC, inspect persistence, and preserve evidence. The skill expands that approach to non-cookie storage, server-set cookies, request endpoints, UI symmetry, research of unknown items, evidence sanitation, and legal-applicability analysis.
