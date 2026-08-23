"""Pure analysis helpers.

Everything in this module is a plain function over captured data with no browser
or filesystem dependency, so each check can be exercised by the offline smoke
test without visiting a site. Browser-side collection lives in `capture.py`;
this module only interprets what was collected.
"""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


#: Link kinds worth archiving for E6, most specific first. A link matching more
#: than one is filed under the first match, so "Cookie Policy" is a cookie
#: policy rather than being swallowed by the broader privacy pattern.
POLICY_LINK_KINDS: tuple[tuple[str, Any], ...] = (
    ("sale_share_optout", re.compile(r"do[-_\s]?not[-_\s]?sell|your[-_\s]privacy[-_\s]choices|limit[-_\s]the[-_\s]use", re.I)),
    ("cookie_policy", re.compile(r"cookie", re.I)),
    ("privacy_policy", re.compile(r"privacy|datenschutz|privacidad", re.I)),
)

#: Paths that look like a policy link but are an application surface, not a
#: document. Fetching these produces a login page or a settings widget archived
#: under a name claiming it is the site's privacy policy.
_POLICY_URL_EXCLUSIONS = re.compile(
    r"/(login|signin|sign-in|account|preferences|settings|dashboard|admin)(/|$|\?)", re.I
)


#: Query parameters that identify a visitor or a campaign rather than a
#: document. Google's cross-domain linker decorates outbound links with `_gl`,
#: so the same policy page appears under several URLs in one page's markup.
_TRACKING_PARAM = re.compile(
    r"^(?:_gl|_ga|_gac_.*|_gcl_au|gclid|gbraid|wbraid|dclid|gclsrc|"
    r"fbclid|msclkid|ttclid|twclid|li_fat_id|igshid|epik|mc_cid|mc_eid|"
    r"utm_[a-z_]+|ref|referrer)$",
    re.I,
)


def strip_tracking_params(url: str) -> str:
    """Remove visitor- and campaign-identifying query parameters from `url`.

    Two reasons, and the second matters more.

    Deduplication: a page commonly links the same policy several times, and
    Google's linker gives each link a different `_gl` value, so the identical
    document looks like several distinct URLs and gets archived once per link.

    Hygiene: `_gl` and `_ga` *carry the visitor's Google Analytics client id*.
    Fetching a policy at the decorated URL would have this tool transmit that
    identifier to the policy host as a side effect of auditing - the audit
    creating exactly the kind of disclosure it exists to detect. Always fetch
    the stripped URL.
    """
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    kept = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not _TRACKING_PARAM.match(key)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def select_policy_links(links: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Pick the policy documents worth archiving from a page's links (E6).

    Counsel's first question about any observed behaviour is what the site
    *said* it would do. Answering it by hand means finding the policy, reading
    it, and hoping it has not changed since the capture - so the bundle archives
    the text alongside the behaviour, with a retrieval timestamp.

    Matching is on both label and href, since plenty of sites link a policy from
    an icon or a bare URL with no useful text. Selection only: this decides what
    is worth fetching and says nothing about what any of it means.
    """
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links or []:
        href = str(link.get("href", "") or "").strip()
        label = str(link.get("text", "") or "").strip()
        if not href.lower().startswith(("http://", "https://")):
            continue
        try:
            parts = urlsplit(href)
        except Exception:
            continue
        if not parts.hostname:
            continue
        # Drop the fragment and any tracking parameters: /privacy,
        # /privacy#cookies, and /privacy?_gl=1*abc are one document. Without the
        # strip, a linker-decorated page archives the same policy once per link
        # and fetches it at a URL carrying the visitor's GA client id.
        canonical = strip_tracking_params(
            urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
        )
        if canonical in seen:
            continue
        if _POLICY_URL_EXCLUSIONS.search(parts.path or ""):
            continue
        haystack = f"{label} {parts.path} {parts.query}"
        for kind, pattern in POLICY_LINK_KINDS:
            if pattern.search(haystack):
                seen.add(canonical)
                selected.append({"kind": kind, "url": canonical, "label": label[:160], "host": parts.hostname.lower()})
                break
        if len(selected) >= limit:
            break
    return selected


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
# D4 - endpoint identity and stability across repeated baseline runs
# --------------------------------------------------------------------------

def endpoint_key(url: str) -> str | None:
    """The `host+path` identity of one request, or None if there is no endpoint.

    Single definition shared by the capture-side stability check
    (`capture._endpoint_set`) and the run comparison (`compare_runs._endpoints`).
    Those two previously extracted this independently and disagreed at the
    edges - one required a hostname, the other only a non-empty key - so a URL
    could count as an endpoint when deciding whether a tag was unstable but not
    when diffing two runs, or the reverse. Both questions are "which network
    endpoints were contacted", so they must count the same things. Lives here
    because `checks.py` holds the pure decision logic with no browser or
    filesystem dependency, matching SKILL.md's split: put the decision in
    `checks.py` and the driving in `capture.py`.

    A hostname is required: a `data:`, `blob:`, or `file:` URL is not a network
    endpoint and must not appear in either answer. The query string is
    deliberately excluded, since cache busters and per-request identifiers
    would otherwise make every run look entirely different from every other.
    """
    try:
        parts = urlsplit(str(url))
    except Exception:
        return None
    if not parts.hostname:
        return None
    key = f"{parts.hostname}{parts.path or ''}"
    return key if key.strip("/") else None


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
# Autosave-denial classification - settings-panel denial with no save control (#6)
# --------------------------------------------------------------------------
# Three CMPs in references/cmp-selectors.json (hubspot, trustarc, quantcast)
# deliberately have an empty `save` list: their settings panel has no separate
# save control, so a denial there is either autosaved as each toggle is
# flipped or never persisted at all. Reporting "no denial control was
# operated" for that path is false - a toggle *was* operated. What is missing
# is proof the CMP kept it. The functions below decide that from already
# -gathered facts; none of them drive a browser.
#
# `reload_probe` is the caller's already-gathered read-back after a reload:
#   {
#     "toggle_states": [{"label": str, "state": bool | None}, ...],  # the
#         same optional toggles disable_optional_toggles operated (or found),
#         re-read after a reload; state is None when re-location failed.
#     "banner_visible": bool | None,  # observational only - see the note
#         below on why banner absence can never verify anything by itself.
#   }
# A future ticket wires the actual reload; this one only defines the shape
# the pure classifier consumes.

def consent_namespace(cmp_entry: dict[str, Any] | None) -> list[str]:
    """The CMP's known consent-storage key namespace, or [] when unknown.

    This is `references/cmp-selectors.json`'s `consent_storage` field, read
    via `load_cmp_table()`. Every entry in the table carries a non-empty list
    (see `test_cmp_table_integrity`); an unfingerprinted CMP or a malformed
    entry yields the empty list, and every caller here treats that as "no
    namespaced verification is possible" rather than guessing.
    """
    if not cmp_entry:
        return []
    namespace = cmp_entry.get("consent_storage")
    return [str(item) for item in namespace] if isinstance(namespace, list) else []


def consent_key_matches(observed_key: str, namespace: list[str], *, cookie_key: bool = False) -> str | None:
    """The namespace entry `observed_key` matches, or None.

    Cookie snapshot keys are `"{domain}|{name}"` (see `consent_snapshot`), so
    with `cookie_key=True` this splits on the *last* `|` and matches only the
    name half - a domain that happens to contain `|` must not corrupt the
    match. localStorage keys carry no such prefix and match whole.

    A namespace entry ending in `-` or `_` is a prefix rule (iubenda's
    `_iub_cs-<id>` cookies carry a random suffix per visitor); everything else
    must match exactly. Both forms are case-insensitive.
    """
    if not namespace or not observed_key:
        return None
    name = observed_key.rsplit("|", 1)[-1] if cookie_key else observed_key
    name_lower = name.lower()
    for rule in namespace:
        rule_lower = str(rule).lower()
        if rule_lower.endswith("-") or rule_lower.endswith("_"):
            if name_lower.startswith(rule_lower):
                return rule
        elif name_lower == rule_lower:
            return rule
    return None


def narrow_consent_diff(before: dict[str, Any], after: dict[str, Any], namespace: list[str]) -> dict[str, Any]:
    """Diff only the CMP's own consent-storage keys between two snapshots.

    The broad diff (`verify_choice_registered`) rests on *any* cookie or
    storage change, which is exactly wrong on the no-save-control path: the
    banner usually stays open, so there is no `banner_dismissed` signal, and
    ordinary analytics activity (`_ga`, a session cookie) would otherwise be
    enough to certify a denial that was never actually recorded. This looks
    only at keys matching the CMP's declared namespace, in `cookies` and
    `local_storage` only.
    """
    namespace = namespace or []
    namespace_available = bool(namespace)
    new_keys: list[dict[str, Any]] = []
    changed_keys: list[dict[str, Any]] = []
    removed_keys: list[dict[str, Any]] = []

    for store, is_cookie_store in (("cookies", True), ("local_storage", False)):
        before_store = (before or {}).get(store) or {}
        after_store = (after or {}).get(store) or {}
        before_keys = set(before_store)
        after_keys = set(after_store)

        for key in sorted(after_keys - before_keys):
            rule = consent_key_matches(key, namespace, cookie_key=is_cookie_store)
            if rule:
                new_keys.append({"store": store, "key": key, "matched_rule": rule})

        for key in sorted(before_keys & after_keys):
            if before_store[key] == after_store[key]:
                continue
            rule = consent_key_matches(key, namespace, cookie_key=is_cookie_store)
            if rule:
                changed_keys.append({"store": store, "key": key, "matched_rule": rule})

        for key in sorted(before_keys - after_keys):
            rule = consent_key_matches(key, namespace, cookie_key=is_cookie_store)
            if rule:
                removed_keys.append({"store": store, "key": key, "matched_rule": rule})

    namespaced_state_changed = bool(new_keys or changed_keys or removed_keys)
    if not namespace_available:
        note = "No consent_storage namespace is known for this CMP; namespaced verification is unavailable."
    elif namespaced_state_changed:
        note = "A key in the CMP's declared consent-storage namespace changed."
    else:
        note = "No key in the CMP's declared consent-storage namespace changed."

    return {
        "namespace": list(namespace),
        "namespace_available": namespace_available,
        "new_keys": new_keys,
        "changed_keys": changed_keys,
        "removed_keys": removed_keys,
        "namespaced_state_changed": namespaced_state_changed,
        "note": note,
    }


AUTOSAVE_VERIFIED_RELOAD = "toggles_disabled_autosave_verified_reload"
AUTOSAVE_VERIFIED_STORAGE = "toggles_disabled_autosave_verified_storage"
AUTOSAVE_NO_SAVE_CONTROL = "toggles_disabled_no_save_control"


def classify_autosave_denial(
    toggle_result: dict[str, Any],
    narrow_diff: dict[str, Any],
    reload_probe: dict[str, Any],
) -> dict[str, Any]:
    """Decide whether a settings-panel denial with no save control was kept.

    Implements the truth table from issue #6 exactly. Two things are
    load-bearing and deliberately checked first, ahead of everything else:

    - a toggle reading back ON after a reload is affirmative evidence the CMP
      *discarded* the choice, and beats even a namespaced storage write - a
      CMP can write a namespaced key and still not honour it on reload;
    - banner absence is never consulted here at all, so a probe reporting
      only "banner not visible" can never verify anything by itself.
    """
    toggle_result = toggle_result or {}
    narrow_diff = narrow_diff or {}
    reload_probe = reload_probe or {}

    examined = [e for e in (toggle_result.get("examined") or []) if isinstance(e, dict)]
    disabled = [e for e in (toggle_result.get("disabled") or []) if isinstance(e, dict)]
    some_disabled = bool(disabled)
    already_off = (not some_disabled) and any(e.get("state_before") is False for e in examined)

    states = [t.get("state") for t in (reload_probe.get("toggle_states") or []) if isinstance(t, dict)]
    any_read_back_on = any(state is True for state in states)
    all_read_back_off = bool(states) and all(state is False for state in states)

    namespaced_write = bool(narrow_diff.get("namespace_available")) and bool(narrow_diff.get("namespaced_state_changed"))

    if not examined:
        return {
            "status": AUTOSAVE_NO_SAVE_CONTROL,
            "verified": False,
            "note": "No optional denial toggle was found, so no choice was operated and there is nothing to verify.",
            "basis": "no_controls_examined",
        }

    if some_disabled:
        if any_read_back_on:
            return {
                "status": AUTOSAVE_NO_SAVE_CONTROL,
                "verified": False,
                "note": (
                    "Optional denial toggles were operated and page state was mutated, but a reload read "
                    "at least one back ON: this CMP has no save control on this path and discarded the choice."
                ),
                "basis": "reload_reverted",
            }
        if all_read_back_off:
            return {
                "status": AUTOSAVE_VERIFIED_RELOAD,
                "verified": True,
                "note": (
                    "Optional denial toggles were disabled and a reload confirmed every one read back OFF: "
                    "the CMP persisted the choice without a separate save control."
                ),
                "basis": "reload_confirmed_off",
            }
        if namespaced_write:
            return {
                "status": AUTOSAVE_VERIFIED_STORAGE,
                "verified": True,
                "note": (
                    "Optional denial toggles were operated and a namespaced consent-storage write was "
                    "observed for this CMP, though the reload read-back was inconclusive."
                ),
                "basis": "namespaced_storage_write",
            }
        return {
            "status": AUTOSAVE_NO_SAVE_CONTROL,
            "verified": False,
            "note": (
                "Optional denial toggles were operated and page state was mutated, but neither a reload "
                "read-back nor a namespaced consent-storage write confirmed the choice persisted."
            ),
            "basis": "unconfirmed",
        }

    if already_off:
        if namespaced_write:
            return {
                "status": AUTOSAVE_VERIFIED_STORAGE,
                "verified": True,
                "note": (
                    "Optional denial toggles were already off, and a namespaced consent-storage write was "
                    "observed for this CMP."
                ),
                "basis": "already_off_namespaced_storage_write",
            }
        return {
            "status": AUTOSAVE_NO_SAVE_CONTROL,
            "verified": False,
            "note": (
                "Optional denial toggles were already off, but no namespaced consent-storage write "
                "confirmed the state as this CMP's own recorded choice."
            ),
            "basis": "already_off_unconfirmed",
        }

    return {
        "status": AUTOSAVE_NO_SAVE_CONTROL,
        "verified": False,
        "note": (
            "Optional denial toggles were examined but neither confirmed disabled nor confirmed already off, "
            "so there is nothing to verify."
        ),
        "basis": "no_confirmed_denial_state",
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


# --------------------------------------------------------------------------
# Viewport scenario keys, planning, and finding collapse (#10)
# --------------------------------------------------------------------------

#: The implicit viewport when none is given, and the one label that never
#: appears in a scenario key. Centralising this (instead of an inline
#: `"desktop"` wherever a key is built or parsed) is what keeps a
#: desktop-only run's keys byte-identical to today's.
DESKTOP_VIEWPORT = "desktop"

#: Separator between a scenario's base name and its viewport label.
#: Deliberately not `-`: base names already contain `-` (`baseline-repeat-1`),
#: so a `-` separator could not be parsed back unambiguously. `@` never
#: appears in a base name.
VIEWPORT_KEY_SEPARATOR = "@"


def scenario_key(base: str, viewport_label: str | None = None) -> str:
    """Encode a scenario's `results` dict key.

    Desktop (`None` or `"desktop"`) is always the bare base name - that
    single rule is the entire backward-compatibility story for every
    existing consumer of `results`. Any other viewport is suffixed
    `@<label>`. The format must only ever be produced here, never as an
    inline f-string elsewhere, so a stray `== "denial"` comparison cannot
    silently degrade a check to desktop-only.
    """
    if viewport_label is None or viewport_label == DESKTOP_VIEWPORT:
        return base
    return f"{base}{VIEWPORT_KEY_SEPARATOR}{viewport_label}"


def parse_scenario_key(key: str) -> tuple[str, str]:
    """Inverse of `scenario_key`: `(base, viewport_label)`.

    A key with no `@` is desktop - this is what lets `baseline-repeat-1`
    (which contains a `-` but never a `@`) round-trip correctly instead of
    colliding with the separator.
    """
    if VIEWPORT_KEY_SEPARATOR in key:
        base, viewport_label = key.split(VIEWPORT_KEY_SEPARATOR, 1)
        return base, viewport_label
    return key, DESKTOP_VIEWPORT


def scenario_dir_name(key: str) -> str:
    """Filesystem/HAR-safe form of a scenario key: `@` becomes `-`.

    Directory and HAR filenames are built from this, not from the key
    itself, so a viewport-suffixed scenario never puts `@` on disk.
    """
    return key.replace(VIEWPORT_KEY_SEPARATOR, "-")


def plan_scenarios(
    *,
    include_gpc: bool = True,
    include_accept: bool = True,
    baseline_repeats: int = 2,
    include_persistence: bool = True,
    viewport_labels: Iterable[str] = (DESKTOP_VIEWPORT,),
) -> list[dict[str, Any]]:
    """Build the ordered scenario plan `run_all_scenarios` will eventually execute.

    Desktop always runs first and in full - baseline, denial, gpc, accept,
    baseline repeats, persistence - which reproduces today's exact sequence
    and names when `viewport_labels` is desktop-only. That reproduction is
    the regression guard for the whole viewport effort. Additional viewports
    repeat the single-run scenarios (baseline, denial, gpc, accept,
    persistence) under their own `@<label>` keys; `baseline-repeat-*` stays
    desktop-only because its entire purpose is measuring desktop A/B and
    flake noise, which a second viewport adds nothing to.

    Each entry carries enough to drive `run_scenario_with_retry` later:
    `key`, `base`, `action`, `gpc`, `viewport_label`, `pages`, `run_exercises`,
    `storage_state_from` (the scenario key whose saved storage state this
    entry must be replayed with, or `None` for entries that start fresh).
    Nothing calls this yet - it is pure planning.
    """
    plan: list[dict[str, Any]] = []

    seen: list[str] = []
    for viewport_label in viewport_labels:
        if viewport_label not in seen:
            seen.append(viewport_label)
    if DESKTOP_VIEWPORT in seen:
        seen.remove(DESKTOP_VIEWPORT)
        seen.insert(0, DESKTOP_VIEWPORT)

    def add(
        base: str,
        action: str,
        viewport_label: str,
        *,
        gpc: bool = False,
        pages: int | None = None,
        run_exercises: bool = True,
        storage_state_from: str | None = None,
    ) -> None:
        plan.append({
            "key": scenario_key(base, viewport_label),
            "base": base,
            "action": action,
            "gpc": gpc,
            "viewport_label": viewport_label,
            "pages": pages,
            "run_exercises": run_exercises,
            "storage_state_from": storage_state_from,
        })

    for viewport_label in seen:
        add("baseline", "none", viewport_label, pages=0, run_exercises=False)
        add("denial", "deny", viewport_label)
        if include_gpc:
            add("gpc", "none", viewport_label, gpc=True)
        if include_accept:
            add("accept", "accept", viewport_label)
        if viewport_label == DESKTOP_VIEWPORT:
            for index in range(1, max(0, baseline_repeats) + 1):
                add(f"baseline-repeat-{index}", "none", viewport_label, pages=0, run_exercises=False)
        if include_persistence:
            add(
                "persistence", "none", viewport_label, pages=0, run_exercises=False,
                storage_state_from=scenario_key("denial", viewport_label),
            )

    return plan


#: Fields (beyond the normalised `depends_on_scenarios` bases) that must
#: match for two findings to be the same finding seen from different
#: viewports. `severity` and `evidence_strength` are included deliberately -
#: a finding that reads differently on mobile is exactly the divergence
#: testing mobile exists to surface, and must never be silently merged away.
_VIEWPORT_COLLAPSE_MATCH_FIELDS = (
    "check_type", "title", "severity", "certainty", "observation",
    "strict_us_composite_baseline", "potential_legal_relevance",
    "applicability_needed", "recommendation", "evidence_strength",
)


def _finding_viewport(finding: dict[str, Any]) -> str:
    deps = finding.get("depends_on_scenarios") or []
    if not deps:
        return DESKTOP_VIEWPORT
    return parse_scenario_key(deps[0])[1]


def _finding_match_key(finding: dict[str, Any]) -> tuple[Any, ...]:
    bases = tuple(sorted(parse_scenario_key(s)[0] for s in (finding.get("depends_on_scenarios") or [])))
    return (bases,) + tuple(finding.get(field) for field in _VIEWPORT_COLLAPSE_MATCH_FIELDS)


def collapse_viewport_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge findings that are identical across viewports into one.

    A non-desktop finding collapses into its desktop counterpart when every
    field in `_VIEWPORT_COLLAPSE_MATCH_FIELDS` matches and their
    `depends_on_scenarios` share the same base scenario names. The merged
    result keeps the desktop finding untouched - including its id and its
    desktop-only `depends_on_scenarios`, so re-running `partition_findings`
    over a written bundle cannot let a mobile-only failure suppress a valid
    desktop finding - and gains `observed_viewports` (desktop plus every
    viewport it also matched) and `also_observed_in_scenarios` (the matched
    findings' own scenario keys).

    A finding with no desktop counterpart (mobile-only) passes through
    unchanged, `@`-suffixed dependency intact. Findings differing in
    `severity` or `evidence_strength` are never collapsed.

    Designed to run after `partition_findings`, over already-valid findings.
    Nothing calls this yet.
    """
    desktop: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for finding in findings:
        (desktop if _finding_viewport(finding) == DESKTOP_VIEWPORT else others).append(finding)

    unmatched_others = list(others)
    merged_by_id: dict[int, dict[str, Any]] = {}
    consumed_ids: set[int] = set()
    for finding in desktop:
        key = _finding_match_key(finding)
        matches = [other for other in unmatched_others if _finding_match_key(other) == key]
        if matches:
            for match in matches:
                unmatched_others.remove(match)
                consumed_ids.add(id(match))
            merged = dict(finding)
            merged["observed_viewports"] = [DESKTOP_VIEWPORT] + sorted({_finding_viewport(m) for m in matches})
            merged["also_observed_in_scenarios"] = [
                scenario
                for match in matches
                for scenario in (match.get("depends_on_scenarios") or [])
            ]
            merged_by_id[id(finding)] = merged

    # Single pass over the input in its original order: emit each finding at
    # its original position (merged, if it absorbed matches), skipping only
    # the non-desktop findings that were consumed by a merge above. This
    # preserves the severity-then-id ordering `generate_findings` relies on -
    # findings are never reshuffled to the back just for being non-desktop.
    output: list[dict[str, Any]] = []
    for finding in findings:
        fid = id(finding)
        if fid in consumed_ids:
            continue
        output.append(merged_by_id.get(fid, finding))
    return output
