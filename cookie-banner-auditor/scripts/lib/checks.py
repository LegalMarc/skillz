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


#: Hosts on which Meta's Limited Data Use flag is meaningful.
META_LDU_HOSTS = ("facebook.com", "facebook.net", "instagram.com")


def parse_meta_ldu_signal(url: str) -> dict[str, Any] | None:
    """Extract Meta's Limited Data Use flag from a Meta pixel request.

    LDU is Meta's transmission-layer restriction: the pixel still fires, but
    `dpo=LDU` tells Meta to process the event under limited terms, with `dpoco`
    and `dpost` carrying the country and state Meta should apply. It is the
    closest Meta analogue to a denied Google Consent Mode signal, and like
    Consent Mode it means a tag firing is not by itself proof consent was
    ignored.

    Read as an observation, never as a conclusion. This parser recognises the
    documented parameter names; it does not verify that Meta honoured them, and
    a `dpoco`/`dpost` of 0 means "infer from IP" rather than a specific place.
    Confirm against a real capture before resting anything on it.
    """
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
    except Exception:
        return None
    if not any(host == known or host.endswith("." + known) for known in META_LDU_HOSTS):
        return None
    if "dpo" not in query:
        return None
    raw = query.get("dpo", "")
    return {
        "vendor": "meta",
        "host": host,
        "ldu_raw": raw or None,
        "ldu_active": raw.upper() == "LDU",
        "country_raw": query.get("dpoco") or None,
        "state_raw": query.get("dpost") or None,
        "pixel_id": query.get("id"),
    }


def parse_consent_signal(url: str) -> dict[str, Any] | None:
    """Any recognised transmission-layer consent signal on one request.

    Dispatches by vendor. Google Consent Mode and Meta LDU are implemented.

    TikTok and other vendors are deliberately absent: their wire formats have
    not been confirmed against a real capture here, and inventing a parameter
    name would manufacture evidence for a signal that was never observed. Add a
    vendor only after seeing its parameters in a HAR from a live run.
    """
    google = parse_consent_mode_signal(url)
    if google:
        return {"vendor": "google", **google}
    return parse_meta_ldu_signal(url)


def summarize_consent_mode(signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse per-request consent signals into a per-scenario summary.

    The Google-derived fields are computed from Google signals alone. Meta LDU
    is reported alongside rather than folded in: `all_signals_denied` drives the
    `consent-enforced-at-transmission` finding, and letting a Meta signal that
    carries no `gcs` value dilute or satisfy that test would silently change
    what the finding asserts.
    """
    google = [s for s in signals if s.get("vendor", "google") == "google"]
    meta = [s for s in signals if s.get("vendor") == "meta"]
    recognized = [s for s in google if s.get("gcs_recognized")]
    return {
        "signal_count": len(google),
        "recognized_count": len(recognized),
        "present": bool(google),
        "all_signals_denied": bool(recognized) and all(s.get("all_denied") for s in recognized),
        "any_signal_granted": any(not s.get("all_denied") for s in recognized),
        "distinct_gcs_values": sorted({s.get("gcs_raw") for s in google if s.get("gcs_raw")}),
        "vendors": sorted({s.get("vendor", "google") for s in signals}),
        "meta_ldu_signal_count": len(meta),
        "meta_ldu_active": bool(meta) and all(s.get("ldu_active") for s in meta),
        "total_signal_count": len(signals),
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

    # Real Tab-order position (see capture.measure_tab_order), distinct from
    # the DOM `tabIndex` attribute above: a control can be first in markup and
    # still be reached last, or never, once tabindex and focusability quirks
    # are accounted for. `None` means the control was never reached within the
    # traversal's bounded budget - reported as unreachable, not as position 0.
    accept_tab_position = accept.get("tab_position")
    reject_tab_position = reject.get("tab_position")

    # Tab-order measurement only ever runs when both controls resolved (see
    # execute_denial); when either fell below the resolution threshold,
    # neither candidate dict carries these keys at all. Falling back to
    # `bool(None or None)` would silently assert "measured, cap not hit" for
    # a pair that was never measured - distinguish unmeasured from measured.
    tab_order_measured = "tab_order_cap_hit" in accept or "tab_order_cap_hit" in reject
    tab_order_cap_hit = (
        bool(accept.get("tab_order_cap_hit") or reject.get("tab_order_cap_hit"))
        if tab_order_measured
        else None
    )

    def _tab_reachable(control: dict[str, Any]) -> bool | None:
        # Interpretation of capture.measure_tab_order's raw traversal facts -
        # kept here, not in capture.py, so it stays on the pure/Playwright-free
        # side of the split and is covered by the fast checks.py tests. A
        # position was found: definitely reachable. No position and this
        # control's traversal never ran (fell below the resolution threshold,
        # so it carries no `tab_order_cap_hit` key at all): unmeasured. No
        # position and the cap was hit (budget exhausted or the traversal
        # aborted before completing a lap): the answer is unknown rather than
        # a false "not reachable". No position and the cap was *not* hit: the
        # traversal completed a full lap of the page's focus order without
        # ever seeing this control, which proves it is genuinely unreachable.
        if "tab_order_cap_hit" not in control:
            return None
        if control.get("tab_position") is not None:
            return True
        if control.get("tab_order_cap_hit"):
            return None
        return False

    accept_tab_reachable = _tab_reachable(accept)
    reject_tab_reachable = _tab_reachable(reject)
    accept_precedes_reject = None
    if accept_tab_reachable and reject_tab_reachable:
        accept_precedes_reject = accept_tab_position < reject_tab_position

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
        "accept_tab_position": accept_tab_position,
        "reject_tab_position": reject_tab_position,
        "accept_tab_reachable": accept_tab_reachable,
        "reject_tab_reachable": reject_tab_reachable,
        "tab_order_cap_hit": tab_order_cap_hit,
        "accept_precedes_reject": accept_precedes_reject,
        "accept_focus_visible": accept.get("focus_visible"),
        "reject_focus_visible": reject.get("focus_visible"),
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


# --------------------------------------------------------------------------
# Retry classification - transient transport failures vs. consent findings (#12)
# --------------------------------------------------------------------------

#: Fatal-error class names Playwright raises when a wait or navigation stalls.
TIMEOUT_ERROR_TYPES = {"TimeoutError"}

#: Substrings of a fatal error's message that indicate the browser could not
#: reach or load the page at all - DNS, connection, or an aborted navigation.
#: Lower-cased before matching.
NAVIGATION_ERROR_MARKERS = (
    "net::err_",
    "err_connection",
    "err_name_not_resolved",
    "err_internet_disconnected",
    "err_empty_response",
    "err_aborted",
    "navigation failed",
    "target page, context or browser has been closed",
    "target closed",
)

FAILURE_NONE = "none"
FAILURE_TIMEOUT = "timeout"
FAILURE_NAVIGATION = "navigation"
FAILURE_CONSENT_INTERACTION = "consent_interaction_failure"
FAILURE_UNKNOWN = "unknown"

#: Only these classes represent a flake worth a second attempt. Every other
#: class - including "unknown" - fails closed and is never retried.
RETRYABLE_FAILURE_CLASSES = {FAILURE_TIMEOUT, FAILURE_NAVIGATION}


def classify_scenario_failure(
    *,
    fatal_error: str | None = None,
    fatal_error_type: str | None = None,
    interaction_required: bool = False,
    interaction_completed: bool = True,
    interaction_verified: bool = True,
) -> str:
    """Classify why one scenario attempt did not produce a valid result.

    This is the single place that decides whether an attempt is a transport
    flake (worth a retry) or a real finding about the site (never retried).
    A denial or accept control that never resolved - or a click that changed
    nothing - is a finding, not a flake; retrying it would launder a real
    result as instability, so that case is classified as
    `FAILURE_CONSENT_INTERACTION` explicitly rather than inferred from the
    absence of a fatal error.

    An unrecognized fatal error is `FAILURE_UNKNOWN` and is never retried:
    fail closed rather than guess that an unfamiliar failure is transient.
    """
    if fatal_error or fatal_error_type:
        type_name = fatal_error_type or ""
        text = (fatal_error or "").lower()
        if type_name in TIMEOUT_ERROR_TYPES or "timeout" in text:
            return FAILURE_TIMEOUT
        if any(marker in text for marker in NAVIGATION_ERROR_MARKERS):
            return FAILURE_NAVIGATION
        return FAILURE_UNKNOWN

    if interaction_required and not (interaction_completed and interaction_verified):
        return FAILURE_CONSENT_INTERACTION

    return FAILURE_NONE


def should_retry_scenario(failure_class: str) -> bool:
    """Pure retry predicate: only a transport-class failure earns a retry."""
    return failure_class in RETRYABLE_FAILURE_CLASSES
