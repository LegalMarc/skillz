"""Pure analysis helpers.

Everything in this module is a plain function over captured data with no browser
or filesystem dependency, so each check can be exercised by the offline smoke
test without visiting a site. Browser-side collection lives in `capture.py`;
this module only interprets what was collected.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

# --------------------------------------------------------------------------
# C1 / C5 - request role and evidence strength
# --------------------------------------------------------------------------

#: Resource types that can only ever be a fetch of code or presentation assets.
LOADER_RESOURCE_TYPES = {"script", "stylesheet", "font"}
PASSIVE_RESOURCE_TYPES = {"image", "media", "manifest", "texttrack", "other"}

#: Query/body parameter names that carry a durable identifier for a person or
#: device. Presence of one of these upgrades a beacon to `identifier_transmitted`.
IDENTIFIER_PARAM = re.compile(
    r"^(?:"
    r"cid|_ga|ga_cid|client_id|clientid|uid|user_id|userid|visitor_id|"
    r"gclid|gbraid|wbraid|_gcl_au|dclid|"
    r"fbclid|fbp|_fbp|fbc|_fbc|external_id|"
    r"msclkid|li_fat_id|li_giant|ttclid|twclid|epik|sc_click_id|"
    r"em|ph|hashed_email|sha256_email|ud\[.*\]|"
    r"anonymous_id|anonymousid|distinct_id|device_id|deviceid|idfa|aaid|"
    r"session_id|sessionid|_hsq|hutk|hubspotutk|vid"
    r")$",
    re.I,
)

#: Values that look like a durable identifier even when the parameter name is
#: uninformative: GA client ids, UUIDs, and long opaque tokens.
IDENTIFIER_VALUE = re.compile(
    r"^(?:"
    r"\d{6,12}\.\d{9,11}|"                                  # GA client id
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"  # UUID
    r"fb\.\d\.\d{10,}\.\d{6,}|"                             # _fbp
    r"[A-Za-z0-9_-]{32,}"                                   # long opaque token
    r")$"
)

ROLE_LOADER = "loader"
ROLE_BEACON = "beacon"
ROLE_IDENTIFIER = "identifier_bearing"
ROLE_PASSIVE = "passive"

STRENGTH_SCRIPT_ONLY = "script_loaded_only"
STRENGTH_BEACON = "beacon_observed"
STRENGTH_IDENTIFIER = "identifier_transmitted"
STRENGTH_NONE = "no_transmission_evidence"

#: Ordered weakest -> strongest, used when summarising a group of requests.
STRENGTH_ORDER = [STRENGTH_NONE, STRENGTH_SCRIPT_ONLY, STRENGTH_BEACON, STRENGTH_IDENTIFIER]

STRENGTH_LABEL = {
    STRENGTH_NONE: "No transmission evidence",
    STRENGTH_SCRIPT_ONLY: "Script loaded only - no beacon observed",
    STRENGTH_BEACON: "Collection endpoint contacted",
    STRENGTH_IDENTIFIER: "Identifier transmitted to collection endpoint",
}

STRENGTH_CAVEAT = {
    STRENGTH_SCRIPT_ONLY: (
        "A script fetch proves the tag was loaded and that the vendor received the visitor's IP "
        "address, user agent, and referring URL. It does not prove any measurement event was sent. "
        "Consent may still be enforced inside the tag at transmission time."
    ),
    STRENGTH_BEACON: (
        "A request reached a known collection endpoint. The payload was not inspected, so the "
        "content and any identifiers it carried remain unconfirmed."
    ),
    STRENGTH_IDENTIFIER: (
        "A request to a known collection endpoint carried a value matching a durable identifier "
        "pattern. Confirm against the decoded payload and the vendor contract before characterising "
        "the recipient's role or the downstream use."
    ),
}


def strongest(strengths: Iterable[str]) -> str:
    """Return the strongest evidence level present, or STRENGTH_NONE."""
    best = STRENGTH_NONE
    for value in strengths:
        if value in STRENGTH_ORDER and STRENGTH_ORDER.index(value) > STRENGTH_ORDER.index(best):
            best = value
    return best


def _matches_transmission_pattern(host: str, path: str, patterns: list[dict[str, Any]]) -> dict[str, Any] | None:
    for pattern in patterns or []:
        host_match = pattern.get("host_match")
        path_regex = pattern.get("path_regex")
        if host_match and host_match not in host:
            continue
        if path_regex and not re.search(path_regex, path, re.I):
            continue
        if host_match or path_regex:
            return pattern
    return None


def _identifier_params(url: str) -> list[str]:
    """Parameter names in `url` whose name or value looks like a durable identifier."""
    try:
        query = urlsplit(url).query
    except Exception:
        return []
    found: list[str] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if IDENTIFIER_PARAM.match(key) or (value and IDENTIFIER_VALUE.match(value)):
            if key not in found:
                found.append(key)
    return found


def classify_request(
    url: str,
    resource_type: str | None,
    method: str = "GET",
    has_post_body: bool = False,
    transmission_patterns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify one request into a role and an evidence strength.

    The distinction this draws is the one that separates a broken consent
    implementation from a correct one: a tag that *loads* is not a tag that
    *transmits*. Google Consent Mode, for example, deliberately loads gtag.js
    and then suppresses or redacts the outbound event.
    """
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or "/"
    except Exception:
        host, path = "", "/"

    resource_type = (resource_type or "").lower()
    pattern = _matches_transmission_pattern(host, path, transmission_patterns or [])
    identifiers = _identifier_params(url)

    if pattern:
        if identifiers or has_post_body or method.upper() == "POST":
            role, strength = ROLE_IDENTIFIER, STRENGTH_IDENTIFIER
        else:
            role, strength = ROLE_BEACON, STRENGTH_BEACON
    elif resource_type in LOADER_RESOURCE_TYPES:
        role, strength = ROLE_LOADER, STRENGTH_SCRIPT_ONLY
    elif identifiers and resource_type not in PASSIVE_RESOURCE_TYPES:
        role, strength = ROLE_IDENTIFIER, STRENGTH_IDENTIFIER
    elif identifiers:
        # An image or beacon carrying an identifier is a classic tracking pixel.
        role, strength = ROLE_IDENTIFIER, STRENGTH_IDENTIFIER
    elif resource_type in {"xhr", "fetch", "ping", "websocket", "eventsource"}:
        role, strength = ROLE_BEACON, STRENGTH_BEACON
    else:
        role, strength = ROLE_PASSIVE, STRENGTH_NONE

    return {
        "request_role": role,
        "evidence_strength": strength,
        "identifier_params": identifiers,
        "transmission_pattern": (pattern or {}).get("id"),
        "transmission_vendor": (pattern or {}).get("vendor"),
    }


# --------------------------------------------------------------------------
# C3 - Google Consent Mode v2
# --------------------------------------------------------------------------

#: Documented `gcs` values. The two digits after "G1" are ad_storage and
#: analytics_storage. Anything outside this set is recorded raw and marked
#: unrecognised rather than guessed at.
GCS_VALUES = {
    "G100": {"ad_storage": "denied", "analytics_storage": "denied"},
    "G101": {"ad_storage": "denied", "analytics_storage": "granted"},
    "G110": {"ad_storage": "granted", "analytics_storage": "denied"},
    "G111": {"ad_storage": "granted", "analytics_storage": "granted"},
    "G1--": {"ad_storage": "not_set", "analytics_storage": "not_set"},
}


def parse_consent_mode_signal(url: str) -> dict[str, Any] | None:
    """Extract Google Consent Mode state from a Google measurement request.

    Returns None when the URL carries no consent-mode parameters. A `gcs` value
    of G100 on a request that still fired is the signature of consent being
    enforced at the transmission layer rather than by blocking the tag.
    """
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
    except Exception:
        return None
    if not any(key in query for key in ("gcs", "gcd", "gcut")):
        return None

    gcs = query.get("gcs", "")
    interpreted = GCS_VALUES.get(gcs)
    return {
        "host": host,
        "gcs_raw": gcs or None,
        "gcs_interpreted": interpreted,
        "gcs_recognized": interpreted is not None,
        "gcd_raw": query.get("gcd") or None,
        "gcut_raw": query.get("gcut") or None,
        "measurement_id": query.get("tid") or query.get("id"),
        "all_denied": interpreted is not None and set(interpreted.values()) == {"denied"},
    }


def summarize_consent_mode(signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse per-request consent-mode signals into a per-scenario summary."""
    recognized = [s for s in signals if s.get("gcs_recognized")]
    return {
        "signal_count": len(signals),
        "recognized_count": len(recognized),
        "present": bool(signals),
        "all_signals_denied": bool(recognized) and all(s.get("all_denied") for s in recognized),
        "any_signal_granted": any(not s.get("all_denied") for s in recognized),
        "distinct_gcs_values": sorted({s.get("gcs_raw") for s in signals if s.get("gcs_raw")}),
    }


# --------------------------------------------------------------------------
# E2 - identifiers hardcoded into served markup
# --------------------------------------------------------------------------

GA_LINKER_PARAM = re.compile(r"[?&]_gl=([^&\"'\s>]+)", re.I)
DIRECT_ID_PARAM = re.compile(r"[?&](gclid|fbclid|msclkid|dclid|ttclid|twclid|_ga|_gcl_au)=([^&\"'\s>]+)", re.I)
EMAIL_IN_MARKUP = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")


def _decode_linker_part(value: str) -> str | None:
    """Decode one base64url segment of a GA cross-domain linker payload."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-+/=]", "", value)
    if len(cleaned) < 8:
        return None
    padded = cleaned + "=" * (-len(cleaned) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            text = decoder(padded).decode("utf-8", errors="strict")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if text.strip():
            return text
    return None


def _timestamp_from_client_id(decoded: str) -> str | None:
    """A GA client id is `<random>.<unix seconds>`; recover the creation date."""
    match = re.match(r"^\d{6,12}\.(\d{9,11})$", decoded.strip())
    if not match:
        return None
    try:
        seconds = int(match.group(1))
        if not 946_684_800 <= seconds <= 4_102_444_800:  # 2000-01-01 .. 2100-01-01
            return None
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def scan_embedded_identifiers(html: str, source_url: str = "") -> list[dict[str, Any]]:
    """Find durable identifiers baked into served markup.

    A cross-domain linker parameter pasted into a CMS is served to every visitor,
    so one person's analytics client id ends up propagated on every outbound
    click. This is easy to miss by eye and trivial to detect mechanically.
    """
    findings: list[dict[str, Any]] = []

    for match in GA_LINKER_PARAM.finditer(html or ""):
        raw = match.group(1)
        decoded_parts: list[dict[str, Any]] = []
        # Payload looks like: 1*hash*_ga*<b64>*_ga_XXX*<b64>*_gcl_au*<b64>
        segments = raw.split("*")
        for index, segment in enumerate(segments):
            if not segment.startswith("_g"):
                continue
            if index + 1 >= len(segments):
                continue
            decoded = _decode_linker_part(segments[index + 1])
            if not decoded:
                continue
            entry: dict[str, Any] = {"parameter": segment, "decoded": decoded}
            created = _timestamp_from_client_id(decoded)
            if created:
                entry["identifier_created"] = created
            decoded_parts.append(entry)
        if decoded_parts:
            findings.append({
                "kind": "ga_cross_domain_linker",
                "source_url": source_url,
                "raw": raw[:300],
                "decoded": decoded_parts,
                "why_it_matters": (
                    "A cross-domain linker payload is static in the served HTML, so every visitor "
                    "is served the same identifier and transmits it on click. It also stitches all "
                    "of those visitors to one analytics client id."
                ),
            })

    for match in DIRECT_ID_PARAM.finditer(html or ""):
        findings.append({
            "kind": "hardcoded_click_identifier",
            "source_url": source_url,
            "parameter": match.group(1),
            "value": match.group(2)[:120],
            "why_it_matters": (
                "An advertising click identifier hardcoded into markup is served to every visitor "
                "and corrupts attribution as well as leaking one visitor's identifier."
            ),
        })

    # Deduplicate on the (kind, parameter, value/raw) triple.
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in findings:
        key = (item["kind"], str(item.get("parameter", "")), str(item.get("value") or item.get("raw", ""))[:120])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


# --------------------------------------------------------------------------
# E1 - separate statutory-rights mechanisms
# --------------------------------------------------------------------------

RIGHTS_PHRASES = [
    ("do_not_sell", re.compile(r"do\s+not\s+sell", re.I)),
    ("do_not_share", re.compile(r"do\s+not\s+share", re.I)),
    ("privacy_choices", re.compile(r"your\s+privacy\s+choices", re.I)),
    ("limit_use", re.compile(r"limit\s+the\s+use\s+of\s+my\s+sensitive", re.I)),
    ("opt_out", re.compile(r"\bopt[-\s]?out\b", re.I)),
    ("gpc_mention", re.compile(r"global\s+privacy\s+control", re.I)),
]


def scan_rights_mechanisms(page_text: str, links: list[dict[str, Any]], cmp_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Look for a sale/share opt-out mechanism separate from the cookie banner.

    California's position is that cookie controls alone are not an acceptable
    sale/share opt-out, so the presence of a banner says nothing about this.
    Whether a mechanism is *required* depends on coverage and on whether the
    operator sells or shares - facts a scan cannot establish.
    """
    text = page_text or ""
    phrase_hits = {name: bool(pattern.search(text)) for name, pattern in RIGHTS_PHRASES}

    matching_links: list[dict[str, Any]] = []
    for link in links or []:
        label = str(link.get("text", ""))
        href = str(link.get("href", ""))
        for name, pattern in RIGHTS_PHRASES:
            if pattern.search(label) or pattern.search(href):
                matching_links.append({"mechanism": name, "text": label[:160], "href": href[:300]})
                break

    state = cmp_state or {}
    cmp_block = state.get("cmp") or {}
    return {
        "phrase_hits": phrase_hits,
        "any_phrase": any(phrase_hits.values()),
        "matching_links": matching_links,
        "has_usp_api": bool(cmp_block.get("hasUSP")),
        "has_gpp_api": bool(cmp_block.get("hasGPP")),
        "mechanism_observed": bool(matching_links) or bool(cmp_block.get("hasUSP")) or bool(cmp_block.get("hasGPP")),
    }


# --------------------------------------------------------------------------
# E3 - symmetry and accessibility measurement
# --------------------------------------------------------------------------

def _parse_css_color(value: str) -> tuple[float, float, float] | None:
    match = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)", str(value or ""), re.I)
    if not match:
        return None
    try:
        return tuple(float(match.group(i)) for i in (1, 2, 3))  # type: ignore[return-value]
    except ValueError:
        return None


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    channels = []
    for raw in rgb:
        c = raw / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float | None:
    """WCAG 2.x contrast ratio, or None when either colour cannot be parsed."""
    fg = _parse_css_color(foreground)
    bg = _parse_css_color(background)
    if not fg or not bg:
        return None
    light, dark = sorted((_relative_luminance(fg), _relative_luminance(bg)), reverse=True)
    return round((light + 0.05) / (dark + 0.05), 2)


def measure_symmetry(accept: dict[str, Any] | None, reject: dict[str, Any] | None) -> dict[str, Any]:
    """Compare the accept and reject controls on the dimensions regulators name.

    California's regulations give the example that "Accept All" plus
    "Preferences" is not symmetrical when acceptance takes one step and the more
    protective option takes more; an equal choice is "Accept All" / "Decline All".
    """
    if not accept or not reject:
        return {
            "comparable": False,
            "reason": "accept control not found" if not accept else "reject control not found",
        }

    def area(control: dict[str, Any]) -> float | None:
        box = control.get("box") or {}
        try:
            return float(box.get("width", 0)) * float(box.get("height", 0))
        except (TypeError, ValueError):
            return None

    accept_style = accept.get("style") or {}
    reject_style = reject.get("style") or {}
    accept_area, reject_area = area(accept), area(reject)
    area_ratio = round(accept_area / reject_area, 3) if accept_area and reject_area else None

    accept_contrast = contrast_ratio(accept_style.get("color", ""), accept_style.get("backgroundColor", ""))
    reject_contrast = contrast_ratio(reject_style.get("color", ""), reject_style.get("backgroundColor", ""))

    same_frame = accept.get("frame_url") == reject.get("frame_url")
    same_background = accept_style.get("backgroundColor") == reject_style.get("backgroundColor")
    same_font_size = accept_style.get("fontSize") == reject_style.get("fontSize")
    same_font_weight = accept_style.get("fontWeight") == reject_style.get("fontWeight")

    # Treat up to a 10% area difference as visually equivalent.
    area_equivalent = area_ratio is not None and 0.9 <= area_ratio <= 1.1

    return {
        "comparable": True,
        "same_layer": same_frame,
        "area_ratio_accept_over_reject": area_ratio,
        "area_equivalent": area_equivalent,
        "same_background_color": same_background,
        "same_font_size": same_font_size,
        "same_font_weight": same_font_weight,
        "accept_contrast_ratio": accept_contrast,
        "reject_contrast_ratio": reject_contrast,
        "accept_keyboard_focusable": accept.get("keyboardFocusable"),
        "reject_keyboard_focusable": reject.get("keyboardFocusable"),
        "accept_tab_index": accept.get("tabIndex"),
        "reject_tab_index": reject.get("tabIndex"),
        "symmetric": bool(
            same_frame and area_equivalent and same_background and same_font_size and same_font_weight
        ),
    }


# --------------------------------------------------------------------------
# Section 9 - legal issue-spotting matrix, generated from actual findings
# --------------------------------------------------------------------------
# Each entry maps a bundle of `check_type` values onto one authority and the
# theory/missing-facts language that applies when at least one of them fired.
# Splitting an authority into topics (rather than one fixed paragraph) means a
# row only ever mentions the theory its own evidence supports - a report with
# only an embedded-identifier finding must not claim a GPC issue just because
# California is mentioned for other reasons. Phrasing reuses the vocabulary and
# "law-specific anchors" of `references/legal-baseline.md`; that file remains
# the source of authority text and is not duplicated here beyond short labels.
#
# Deliberately unmapped: `denial-control-unresolved`, `capture-errors`,
# `unstable-tag-behaviour`, `insecure-auth-cookie`, and `unresolved-purposes`.
# Each of those findings says explicitly that no legal inference should be
# drawn from it (tooling gaps, security hygiene, or an unresolved research
# item), so they contribute no row here even when present. An unrecognised
# `check_type` - including a future `denial-autosave-unconfirmed` - behaves
# the same way: it matches no topic and is silently skipped rather than
# raising or producing a bogus authority row.
ISSUE_MATRIX_AUTHORITIES: list[dict[str, Any]] = [
    {
        "authority": "FTC Act s5 (deception)",
        "topics": [
            {
                "check_types": {
                    "denial-not-registered",
                    "post-denial-tracking",
                    "post-denial-cookies",
                    "banner-reprompt",
                    "persistence-across-session",
                },
                "requirement": (
                    "A consent interface's representation that a choice was recorded and honored "
                    "must match actual behavior; a click with no effect, tracking that continues "
                    "after denial, or a preference that resets is a classic deception fact pattern."
                ),
                "missing_facts": (
                    "The exact banner and policy language promised to the consumer; whether a "
                    "reasonable consumer would be misled; whether the discrepancy is intermittent "
                    "or systemic."
                ),
            },
            {
                "check_types": {"asymmetric-choice"},
                "requirement": (
                    "Steering a consumer toward acceptance by making the more protective choice "
                    "harder to reach can support an FTC dark-pattern theory."
                ),
                "missing_facts": (
                    "Whether the design difference is intentional; consumer-perception evidence."
                ),
            },
        ],
    },
    {
        "authority": "California CCPA/CPRA",
        "topics": [
            {
                "check_types": {"gpc-not-honored"},
                "requirement": (
                    "A business that sells or shares personal information must process a "
                    "recognized opt-out preference signal, including Global Privacy Control, "
                    "before the affected transmission."
                ),
                "missing_facts": (
                    "Coverage thresholds; sale/share determination; whether the recipient is a "
                    "service provider or contractor under a compliant contract."
                ),
            },
            {
                "check_types": {"measured-asymmetry", "measured-symmetry-satisfied"},
                "requirement": (
                    "Consent and CCPA-request interfaces must offer symmetrical choices - "
                    "comparable size, contrast, color, and click count - and must not visually "
                    "favor acceptance."
                ),
                "missing_facts": (
                    "Whether the interface is seeking CCPA consent or processing a CCPA request; "
                    "the rendered design outside the captured viewport."
                ),
            },
            {
                "check_types": {"rights-mechanism-absent"},
                "requirement": (
                    "A cookie banner alone is not an acceptable sale/share opt-out method; a "
                    "separate, effective mechanism is required where the business sells or shares."
                ),
                "missing_facts": (
                    "Whether the operator sells or shares personal information as defined, or "
                    "processes it for targeted advertising; applicable coverage thresholds."
                ),
            },
            {
                "check_types": {"embedded-identifier"},
                "requirement": (
                    "A durable identifier baked into markup and served to every visitor bears on "
                    "disclosure and profile-linkage analysis even absent a distinct opt-out signal "
                    "finding."
                ),
                "missing_facts": (
                    "Whether the identifier ties to a known consumer; the recipient's contractual "
                    "role; retention and downstream use."
                ),
            },
        ],
    },
    {
        "authority": "Colorado / Connecticut / Oregon",
        "topics": [
            {
                "check_types": {"gpc-not-honored"},
                "requirement": (
                    "Covered controllers must honor recognized universal opt-out mechanisms, "
                    "including GPC, for sale and targeted advertising."
                ),
                "missing_facts": "Coverage; targeted-advertising determination; consumer residency.",
            },
        ],
    },
    {
        "authority": "Consumer health and sensitive data",
        "topics": [
            {
                "check_types": {"pre-consent-tracking", "post-denial-tracking", "post-denial-cookies"},
                "requirement": (
                    "Sensitive and health-related processing generally requires opt-in consent "
                    "before collection or sharing, subject to narrow statutory exceptions."
                ),
                "missing_facts": (
                    "Whether the observed flows meet statutory definitions of sensitive or health "
                    "data; whether an applicable exception applies."
                ),
            },
        ],
    },
]


def build_issue_matrix(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Section 9's rows from the findings a run actually emitted.

    Returns one row per authority that has at least one supporting finding,
    each citing the finding id(s) that support it. An authority with no
    matching finding produces no row at all - this is what stops the report
    from citing "GPC and symmetry findings" on a run that has neither.
    """
    by_check_type: dict[str, list[str]] = {}
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        check_type = finding.get("check_type")
        finding_id = finding.get("id")
        if not check_type or not finding_id:
            continue
        by_check_type.setdefault(str(check_type), []).append(str(finding_id))

    rows: list[dict[str, Any]] = []
    for authority in ISSUE_MATRIX_AUTHORITIES:
        requirement_parts: list[str] = []
        missing_parts: list[str] = []
        evidence_ids: list[str] = []
        for topic in authority["topics"]:
            matched_ids = [
                finding_id
                for check_type in topic["check_types"]
                for finding_id in by_check_type.get(check_type, [])
            ]
            if not matched_ids:
                continue
            requirement_parts.append(topic["requirement"])
            missing_parts.append(topic["missing_facts"])
            for finding_id in matched_ids:
                if finding_id not in evidence_ids:
                    evidence_ids.append(finding_id)
        if not evidence_ids:
            # No topic under this authority is supported by this run's
            # findings - do not emit a row that cites nothing.
            continue
        rows.append({
            "authority": authority["authority"],
            "requirement": " ".join(dict.fromkeys(requirement_parts)),
            "evidence": ", ".join(evidence_ids),
            "missing_facts": " ".join(dict.fromkeys(missing_parts)),
        })
    return rows


# --------------------------------------------------------------------------
# D4 - stability across repeated baseline runs
# --------------------------------------------------------------------------

def compare_repeat_runs(runs: list[set[str]]) -> dict[str, Any]:
    """Split endpoints into those seen in every repeat and those seen in some.

    An endpoint present in only some runs is evidence of an A/B test, a geo
    experiment, or a flaky tag - and must not be reported as settled fact.
    """
    if not runs:
        return {"run_count": 0, "stable": [], "unstable": []}
    stable = set.intersection(*runs) if len(runs) > 1 else set(runs[0])
    union = set.union(*runs)
    return {
        "run_count": len(runs),
        "stable": sorted(stable),
        "unstable": sorted(union - stable),
        "total_distinct": len(union),
    }
