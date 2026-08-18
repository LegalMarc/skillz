#!/usr/bin/env python3
"""Offline regression tests for the cookie-banner auditor.

Every test here runs without visiting an external site. A live site is still
needed to validate real CMP behaviour and network conditions, but the checks
below cover the logic that has silently produced wrong answers before.
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from playwright.sync_api import sync_playwright

from lib import checks
from lib.analysis import analyze_and_write, build_cookie_inventory, partition_findings, scenario_validity_map
from lib.capture import (
    SCORE_THRESHOLD,
    ScenarioConfig,
    execute_denial,
    exercise_forms,
    find_control,
    fingerprint_cmp,
    inspect_banner,
    load_cmp_table,
    load_transmission_patterns,
    verify_choice_registered,
)
from lib.util import (
    build_zip_bundle,
    discover_browser_executable,
    markdown_to_html,
    read_json,
    run_fingerprint,
    sanitize_har_data,
    utc_now,
)

PASSED: list[str] = []


def ok(name: str) -> None:
    PASSED.append(name)
    print(f"  ok  {name}")


def assert_no_secret(value: object, secrets: list[str]) -> None:
    text = json.dumps(value, ensure_ascii=False, default=str)
    for secret in secrets:
        assert secret not in text, f"secret was not redacted: {secret}"


# ---------------------------------------------------------------------------
# Evidence handling
# ---------------------------------------------------------------------------

def test_har_sanitization() -> None:
    raw = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": "https://example.test/collect?email=person%40example.test&campaign=spring",
                        "headers": [
                            {"name": "Cookie", "value": "sid=super-secret; pref=yes"},
                            {"name": "Authorization", "value": "Bearer top-secret"},
                        ],
                        "cookies": [{"name": "sid", "value": "super-secret"}],
                        "queryString": [{"name": "email", "value": "person@example.test"}],
                        "postData": {"mimeType": "application/json", "text": '{"user":"private"}'},
                    },
                    "response": {
                        "headers": [{"name": "Set-Cookie", "value": "visitor=identifier-123; Secure; SameSite=Lax"}],
                        "cookies": [{"name": "visitor", "value": "identifier-123"}],
                        "content": {"text": "private response body"},
                    },
                }
            ]
        }
    }
    clean = sanitize_har_data(raw)
    assert_no_secret(clean, [
        "super-secret", "top-secret", "person@example.test",
        "identifier-123", "private response body", '\"user\":\"private\"',
    ])
    text = json.dumps(clean)
    assert "sid=" in text and "visitor=" in text, "cookie names should remain available for analysis"
    assert "[REDACTED" in text
    ok("HAR sanitization redacts values and keeps names")


# ---------------------------------------------------------------------------
# A - control detection
# ---------------------------------------------------------------------------

HUBSPOT_BANNER = """
<!doctype html><html><body><div style="height:1500px">content</div>
<div id="hs-eu-cookie-confirmation" style="position:fixed;bottom:0;left:0;width:900px;background:#fff;padding:20px">
  <div id="hs-eu-policy-wording"><p>We use cookies to enhance your browsing experience, serve
  personalized ads or content, and analyze our traffic. By browsing our site, you consent to our use
  of cookies. If you do not consent, click "Decline" below.</p></div>
  <div id="hs-eu-cookie-confirmation-buttons-area">
    <button id="hs-eu-confirmation-button" aria-label="Accept" tabindex="0"
      style="width:154px;height:46px;background:rgb(66,91,118);color:rgb(255,255,255);font-size:14px;font-weight:400">Accept</button>
    <button id="hs-eu-decline-button" aria-label="Decline" tabindex="0"
      style="width:154px;height:46px;background:rgb(66,91,118);color:rgb(255,255,255);font-size:14px;font-weight:400">Decline</button>
  </div></div>
<script>
  document.querySelector('#hs-eu-decline-button').addEventListener('click', () => {
    document.querySelector('#hs-eu-cookie-confirmation').remove();
    try { document.cookie = '__hs_cookie_cat_pref=1:false_2:false_3:false; path=/'; } catch (e) {}
  });
</script></body></html>
"""

UNRELATED_ACCEPT = """
<!doctype html><html><body><h1>Checkout</h1>
<form><label>Terms</label><button id="accept">Accept</button></form></body></html>
"""

SHADOW_BANNER = """
<!doctype html><html><body><div id="host"></div><script>
  const root = document.getElementById('host').attachShadow({mode: 'open'});
  root.innerHTML = `<div style="position:fixed;bottom:0;padding:20px">
    <p>We use cookies for analytics and advertising on this site.</p>
    <button id="sd-accept" style="width:120px;height:40px">Accept All</button>
    <button id="sd-reject" style="width:120px;height:40px">Reject All</button></div>`;
</script></body></html>
"""


def test_control_detection(page) -> None:
    table = load_cmp_table()
    assert table, "CMP selector table should load"

    # Regression for the defect that produced a false critical finding: the
    # ancestor-text walk froze on the button's own label, so a bare "Decline"
    # scored 60 against a threshold of 70 and was never clicked.
    page.set_content(HUBSPOT_BANNER)
    match = fingerprint_cmp(page, table)
    assert match and match["id"] == "hubspot", match
    ok(f"HubSpot banner fingerprinted via {match['matched_by']}")

    control, candidates, resolution = find_control(page, "reject", match["entry"])
    assert control is not None, resolution
    assert resolution["path"] == "cmp_selector_table"
    assert resolution["matched_selector"] == "#hs-eu-decline-button"
    ok("CMP selector table resolves the HubSpot decline control")

    control, candidates, resolution = find_control(page, "reject", None)
    assert control is not None, f"bare 'Decline' must now resolve by text scoring: {resolution}"
    assert candidates[0]["score"] >= SCORE_THRESHOLD, candidates[0]["score"]
    assert candidates[0]["score"] > 100, f"expected a decisive score, got {candidates[0]['score']}"
    ok(f"text scoring resolves bare 'Decline' at score {candidates[0]['score']} (was 60, threshold {SCORE_THRESHOLD})")

    ancestor = candidates[0].get("ancestorText", "")
    assert "cookies" in ancestor.lower(), f"ancestorText must reach banner copy, got {ancestor!r}"
    assert candidates[0].get("ownText") == "Decline"
    ok("ancestorText reaches the banner container rather than the button label")

    # The guard against clicking unrelated buttons must still hold.
    page.set_content(UNRELATED_ACCEPT)
    control, _, resolution = find_control(page, "accept", None)
    assert control is None, "an unrelated 'Accept' button must not be treated as a consent control"
    assert (resolution.get("best_score") or 0) < SCORE_THRESHOLD
    ok(f"unrelated 'Accept' button correctly rejected at score {resolution.get('best_score')}")

    # Shadow DOM: Playwright's engine pierces open roots.
    page.set_content(SHADOW_BANNER)
    control, _, resolution = find_control(page, "reject", None)
    assert control is not None, f"shadow-DOM control should be reachable: {resolution}"
    ok("controls inside an open shadow root are reachable")


def test_denial_flow_and_verification(page) -> None:
    context = page.context
    page.set_content(HUBSPOT_BANNER)
    result = execute_denial(page, context, wait_ms=20, manual=False,
                            share_scenario_dir=Path(tempfile.mkdtemp()),
                            cmp_entry=(fingerprint_cmp(page, load_cmp_table()) or {}).get("entry"))
    assert result["status"] == "direct_reject_clicked", result
    assert result["click_count"] == 1
    assert result["verification"]["verified"] is True, result["verification"]
    assert result["verification"]["banner_dismissed"] is True
    ok("denial click completes and is verified as registering a state change")

    # A banner whose button does nothing must not be reported as a completed denial.
    page.set_content(HUBSPOT_BANNER.replace(
        "document.querySelector('#hs-eu-cookie-confirmation').remove();", ""
    ).replace(
        "try { document.cookie = '__hs_cookie_cat_pref=1:false_2:false_3:false; path=/'; } catch (e) {}", ""
    ))
    result = execute_denial(page, context, wait_ms=20, manual=False,
                            share_scenario_dir=Path(tempfile.mkdtemp()),
                            cmp_entry=(fingerprint_cmp(page, load_cmp_table()) or {}).get("entry"))
    assert result["status"] == "direct_reject_clicked", result
    assert result["verification"]["verified"] is False, result["verification"]
    ok("a click that changes nothing is flagged as unverified")


def test_verify_choice_registered_unit() -> None:
    before = {"cookies": {"a|x": "h1"}, "local_storage": {}, "cmp_api": {}, "banner_visible": True}
    same = {"cookies": {"a|x": "h1"}, "local_storage": {}, "cmp_api": {}, "banner_visible": True}
    assert verify_choice_registered(before, same)["verified"] is False

    changed = {"cookies": {"a|x": "h1", "b|pref": "h2"}, "local_storage": {}, "cmp_api": {}, "banner_visible": True}
    result = verify_choice_registered(before, changed)
    assert result["verified"] is True and result["new_cookies"] == ["b|pref"]

    dismissed = {"cookies": {"a|x": "h1"}, "local_storage": {}, "cmp_api": {}, "banner_visible": False}
    assert verify_choice_registered(before, dismissed)["banner_dismissed"] is True
    ok("verify_choice_registered distinguishes real changes from no-ops")


def test_settings_path_denial(page) -> None:
    page.set_content("""
        <!doctype html><html><body>
        <div id="cookie-consent" role="dialog" style="position:fixed;bottom:0;left:0;right:0;padding:24px;background:white">
          <p>Choose cookie preferences for analytics and advertising.</p>
          <button id="accept">Accept All</button>
          <button id="settings">Cookie Preferences</button>
        </div>
        <div id="panel" role="dialog" hidden>
          <label><input id="necessary" type="checkbox" checked disabled> Strictly necessary</label>
          <label><input id="analytics" type="checkbox" checked> Analytics</label>
          <label><input id="ads" type="checkbox" checked> Advertising</label>
          <button id="save">Save Preferences</button>
        </div>
        <script>
          settings.addEventListener('click', () => { document.querySelector('#cookie-consent').hidden=true; panel.hidden=false; });
          save.addEventListener('click', () => { panel.remove(); try { document.cookie='consent=custom; path=/'; } catch (e) {} });
        </script></body></html>
    """)
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    assert result["status"] == "preferences_disabled_and_saved", result
    disabled = result.get("toggle_result", {}).get("disabled", [])
    assert len(disabled) >= 2, result
    assert all(item.get("state_after") in {False, None} for item in disabled)
    ok("settings-layer denial disables optional toggles and saves")


def test_form_exercise_does_not_submit(page) -> None:
    page.set_content("""
        <!doctype html><html><body>
        <form id="contact" action="/submit">
          <input name="firstname" type="text">
          <input name="email" type="email">
          <input name="phone" type="tel">
          <button type="submit" id="go">Submit</button>
        </form>
        <form id="login" action="/login"><input name="password" type="password"></form>
        <script>window.__submitted = false;
          document.getElementById('contact').addEventListener('submit', e => { e.preventDefault(); window.__submitted = true; });
        </script></body></html>
    """)
    config = ScenarioConfig(url="https://example.test", wait_ms=10, submit_forms=False)
    record = exercise_forms(page, config)
    filled = {item["type"] for item in record["fields_filled"]}
    assert {"text", "email", "tel"}.issubset(filled), record
    assert record["submitted"] is False
    assert page.evaluate("window.__submitted") is False, "form must not be submitted by default"
    values = page.evaluate("() => [document.querySelector('[name=email]').value, document.querySelector('[name=phone]').value]")
    assert values[0] == "privacy-audit-test@example.com"
    assert "555-0100" in values[1]
    ok("form fields are filled with synthetic data and NOT submitted by default")


# ---------------------------------------------------------------------------
# C - transmission classification and consent mode
# ---------------------------------------------------------------------------

def test_transmission_classification() -> None:
    patterns = load_transmission_patterns()
    assert patterns, "transmission patterns should load"

    loader = checks.classify_request("https://connect.facebook.net/en_US/fbevents.js", "script", transmission_patterns=patterns)
    assert loader["evidence_strength"] == checks.STRENGTH_SCRIPT_ONLY, loader
    assert loader["request_role"] == checks.ROLE_LOADER

    beacon = checks.classify_request("https://www.facebook.com/tr?id=123&ev=PageView", "image", transmission_patterns=patterns)
    assert beacon["evidence_strength"] in {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER}, beacon

    identified = checks.classify_request(
        "https://www.google-analytics.com/g/collect?v=2&tid=G-X&cid=1234567890.1729326454",
        "fetch", transmission_patterns=patterns,
    )
    assert identified["evidence_strength"] == checks.STRENGTH_IDENTIFIER, identified
    assert "cid" in identified["identifier_params"]

    passive = checks.classify_request("https://cdn.example.test/logo.png", "image", transmission_patterns=patterns)
    assert passive["evidence_strength"] == checks.STRENGTH_NONE, passive

    assert checks.strongest([checks.STRENGTH_SCRIPT_ONLY, checks.STRENGTH_IDENTIFIER]) == checks.STRENGTH_IDENTIFIER
    ok("requests are graded loader / beacon / identifier-bearing / passive")


def test_consent_mode_parsing() -> None:
    denied = checks.parse_consent_mode_signal("https://www.google-analytics.com/g/collect?v=2&gcs=G100&tid=G-X")
    assert denied and denied["all_denied"] is True and denied["gcs_recognized"] is True

    granted = checks.parse_consent_mode_signal("https://www.google-analytics.com/g/collect?v=2&gcs=G111")
    assert granted and granted["all_denied"] is False

    unknown = checks.parse_consent_mode_signal("https://www.google-analytics.com/g/collect?gcs=GZZZ")
    assert unknown and unknown["gcs_recognized"] is False, "unrecognised values must not be guessed at"

    assert checks.parse_consent_mode_signal("https://example.test/page") is None

    summary = checks.summarize_consent_mode([denied, denied])
    assert summary["all_signals_denied"] is True and summary["present"] is True
    ok("Consent Mode gcs values parsed, unknown values marked rather than guessed")


# ---------------------------------------------------------------------------
# E - the checks that were previously manual
# ---------------------------------------------------------------------------

def test_embedded_identifier_scan() -> None:
    html = (
        '<a href="https://legal.example.test/privacy-policy?_gl=1*j3dme7*_ga*'
        'MjA3MTE2ODIzOS4xNzI5MzI2NDU0*_gcl_au*MzU5MTYzNzc3LjE3MjkzMjY0NTg.">Privacy</a>'
    )
    findings = checks.scan_embedded_identifiers(html, "https://example.test/")
    assert findings, "hardcoded GA linker should be detected"
    decoded = findings[0]["decoded"]
    values = [d["decoded"] for d in decoded]
    assert any(v.startswith("2071168239.") for v in values), values
    created = [d.get("identifier_created") for d in decoded if d.get("identifier_created")]
    assert created and created[0].startswith("2024-10"), created
    ok(f"embedded GA client id decoded, creation date recovered ({created[0]})")

    assert checks.scan_embedded_identifiers("<a href='/about'>About</a>", "") == []
    ok("clean markup produces no embedded-identifier finding")


def test_rights_mechanism_scan() -> None:
    absent = checks.scan_rights_mechanisms(
        "We use cookies. Read our Privacy Policy.",
        [{"text": "Privacy Policy", "href": "https://example.test/privacy"}],
        {"cmp": {"hasUSP": False, "hasGPP": False}},
    )
    assert absent["mechanism_observed"] is False

    present = checks.scan_rights_mechanisms(
        "Do Not Sell or Share My Personal Information",
        [{"text": "Do Not Sell or Share My Personal Information", "href": "https://example.test/dns"}],
        {"cmp": {"hasUSP": False, "hasGPP": False}},
    )
    assert present["mechanism_observed"] is True and present["matching_links"]

    via_api = checks.scan_rights_mechanisms("nothing here", [], {"cmp": {"hasGPP": True}})
    assert via_api["mechanism_observed"] is True
    ok("statutory-rights mechanism scan detects links and consent APIs")


def test_symmetry_measurement() -> None:
    button = {
        "box": {"width": 154, "height": 46}, "frame_url": "https://example.test/",
        "style": {"backgroundColor": "rgb(66, 91, 118)", "color": "rgb(255, 255, 255)",
                  "fontSize": "14px", "fontWeight": "400"},
    }
    symmetric = checks.measure_symmetry(button, dict(button))
    assert symmetric["symmetric"] is True
    assert symmetric["accept_contrast_ratio"] and symmetric["accept_contrast_ratio"] > 4.5

    smaller = {**button, "box": {"width": 60, "height": 20},
               "style": {**button["style"], "backgroundColor": "rgb(240, 240, 240)"}}
    asymmetric = checks.measure_symmetry(button, smaller)
    assert asymmetric["symmetric"] is False
    assert asymmetric["area_equivalent"] is False
    assert asymmetric["same_background_color"] is False

    assert checks.measure_symmetry(button, None)["comparable"] is False
    assert checks.contrast_ratio("rgb(0,0,0)", "rgb(255,255,255)") == 21.0
    ok("symmetry and WCAG contrast measured from rendered styles")


def test_cmp_table_integrity() -> None:
    """A 'save' selector that also accepts would turn a denial into an acceptance.

    execute_denial falls back to settings -> toggles -> save. If a CMP's save
    control is the same element as its accept control, that fallback silently
    grants consent while the run reports a completed denial. Guard against it
    structurally rather than by review.
    """
    table = load_cmp_table()
    assert table, "CMP table must load"

    required = {"id", "name", "fingerprint", "accept", "reject"}
    for entry in table:
        missing = required - set(entry)
        assert not missing, f"{entry.get('id')} missing keys: {missing}"

        overlap = set(entry.get("save") or []) & set(entry.get("accept") or [])
        assert not overlap, (
            f"{entry['id']}: 'save' reuses the accept selector(s) {sorted(overlap)}. "
            "A settings-path denial would click accept."
        )
        reject_overlap = set(entry.get("reject") or []) & set(entry.get("accept") or [])
        assert not reject_overlap, f"{entry['id']}: reject and accept share selector(s) {sorted(reject_overlap)}"

        fingerprint = entry.get("fingerprint") or {}
        assert fingerprint.get("selectors") or fingerprint.get("script_hosts"), \
            f"{entry['id']} has no fingerprint and can never be matched"

    ids = [e["id"] for e in table]
    assert len(ids) == len(set(ids)), "CMP ids must be unique"
    ok(f"CMP table integrity: {len(table)} entries, no save/accept or reject/accept collisions")


def test_repeat_stability() -> None:
    result = checks.compare_repeat_runs([{"a", "b", "c"}, {"a", "b"}, {"a", "b", "d"}])
    assert result["stable"] == ["a", "b"]
    assert result["unstable"] == ["c", "d"]
    assert result["run_count"] == 3
    ok("endpoints seen in only some repeats are marked unstable")


# ---------------------------------------------------------------------------
# B - validity gating
# ---------------------------------------------------------------------------

def test_validity_gating() -> None:
    findings = [
        {"id": "F-POST-DENIAL-TRACKING", "title": "Tracking continued after denial", "depends_on_scenarios": ["denial"]},
        {"id": "F-GPC-NOT-HONORED", "title": "GPC ignored", "depends_on_scenarios": ["gpc"]},
        {"id": "F-EMBEDDED-IDENTIFIER", "title": "Hardcoded id", "depends_on_scenarios": []},
    ]
    validity = {
        "denial": {"valid": False, "invalid_reason": "The required denial click did not complete (status: manual_required)."},
        "gpc": {"valid": True},
    }
    emitted, suppressed = partition_findings(findings, validity)
    emitted_ids = {f["id"] for f in emitted}

    assert "F-POST-DENIAL-TRACKING" not in emitted_ids, "a finding from an invalid scenario must be withheld"
    assert {"F-GPC-NOT-HONORED", "F-EMBEDDED-IDENTIFIER"} == emitted_ids
    assert len(suppressed) == 1
    assert suppressed[0]["blocking_scenarios"][0]["scenario"] == "denial"
    assert "manual_required" in suppressed[0]["blocking_scenarios"][0]["reason"]
    ok("findings depending on an incomplete scenario are suppressed, not reported")


def test_scenario_validity_map() -> None:
    results = {
        "denial": {"validity": {"valid": False, "invalid_reason": "click never happened"}},
        "baseline": {"validity": {"valid": True}},
        "legacy": {"checkpoints": [], "action_result": {}},          # captured, no verdict recorded
        "baseline_stability": {"stable": [], "unstable": ["x"]},      # a summary, not a scenario
        "baseline_repeats": [{"scenario": "baseline-repeat-1"}],      # a list, not a scenario
        "persistence": {"ran": True, "banner_reprompted": False},     # wrapper, not a scenario
    }
    mapping = scenario_validity_map(results)
    assert mapping["denial"]["valid"] is False
    assert mapping["legacy"]["valid"] is True, "a captured scenario without a verdict defaults to valid"
    for non_scenario in ("baseline_stability", "baseline_repeats", "persistence"):
        assert non_scenario not in mapping, f"{non_scenario} is not a scenario and must not appear as one"
    ok("scenario validity map covers scenarios only, not summaries or wrappers")


# ---------------------------------------------------------------------------
# F/G - reporting, packaging, comparison
# ---------------------------------------------------------------------------

def test_markdown_to_html() -> None:
    md = "\n".join([
        "# Title", "", "Some **bold** and *italic* and `code`.", "",
        "| A | B |", "|---|---|", "| 1 | 2 |", "",
        "- one", "- two", "", "> a quote", "", "```", "raw <tag>", "```",
    ])
    html = markdown_to_html(md)
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html and "<code>code</code>" in html
    assert "<em>italic</em>" in html, "single-asterisk italics must render"
    assert "<strong>bold</strong>" in html and "**" not in html, "bold must not be eaten by the italic rule"
    assert "<table>" in html and "<th>A</th>" in html and "<td>1</td>" in html
    assert "<li>one</li>" in html
    assert "<blockquote>" in html
    assert "&lt;tag&gt;" in html, "code blocks must be escaped"
    ok("markdown renders to HTML for the shared report/PDF pipeline")


def test_run_fingerprint() -> None:
    base = {"target_url": "https://example.test", "pages": 2, "locale": "en-US", "profile": "thorough", "tool_version": "2.0.0"}
    assert run_fingerprint(base) == run_fingerprint({**base, "started_at": "later", "out": "/tmp/x"}), \
        "timestamps and paths must not affect the fingerprint"
    assert run_fingerprint(base) != run_fingerprint({**base, "profile": "quick"}), \
        "a changed profile must change the fingerprint"
    ok("run fingerprint is stable across timestamps and sensitive to conditions")


def synthetic_results(denial_completed: bool = True) -> dict:
    now = utc_now()
    cookie = {"name": "_ga", "value": "raw-cookie-value", "domain": ".example.test", "path": "/",
              "expires": -1, "httpOnly": False, "secure": True, "sameSite": "Lax"}
    base_checkpoint = {
        "scenario": "baseline", "checkpoint": "01-pre-interaction", "time": now,
        "url": "https://example.test/", "title": "Example", "cookies": [cookie],
        "storage_state": {"cookies": [cookie], "origins": []},
        "banner": {"containers": [{"text": "Cookies", "score": 100}],
                   "controls": [{"text": "Accept All"}, {"text": "Decline All"}], "best_text": "We use cookies"},
        "browser_state": {"gpc": False, "cmp": {"hasUSP": False, "hasGPP": False}},
        "screenshots": [],
    }
    denial_status = "direct_reject_clicked" if denial_completed else "manual_required"
    return {
        "baseline": {
            "started": now, "finished": now, "gpc": False, "action": "none",
            "action_result": {"status": "no_interaction"},
            "checkpoints": [base_checkpoint],
            "events": {"requests": [{"time": now, "phase": "initial_navigation",
                                     "url": "https://www.google-analytics.com/g/collect?v=2&cid=secret",
                                     "method": "POST", "resource_type": "fetch", "is_navigation_request": False}],
                       "responses": [], "request_failures": [], "console": []},
            "errors": [], "raw_har": None, "sanitized_har": None,
            "validity": {"valid": True, "required_interaction": None, "invalid_reason": None},
            "isolation_assertion": {"checked": True, "cookie_count": 0, "local_storage_keys": 0,
                                    "session_storage_keys": 0, "clean": True},
            "page_scan": {"links": [{"text": "Privacy", "href": "https://example.test/privacy"}],
                          "page_text": "We use cookies.", "embedded_identifiers": []},
            "consent_mode": {"signals": [], "summary": checks.summarize_consent_mode([])},
        },
        "denial": {
            "started": now, "finished": now, "gpc": False, "action": "deny",
            "action_result": {
                "status": denial_status, "click_count": 1 if denial_completed else 0,
                "direct_accept_available": True, "accept_candidates": [], "reject_candidates": [],
                "verification": {"verified": denial_completed, "note": "test"},
                "resolution": {"reject": {"path": "cmp_selector_table" if denial_completed else "none",
                                          "best_score": None if denial_completed else 60, "threshold": 70}},
            },
            "checkpoints": [
                {**base_checkpoint, "scenario": "denial"},
                {**base_checkpoint, "scenario": "denial", "checkpoint": "02-post-denial", "cookies": [],
                 "storage_state": {"cookies": [], "origins": []},
                 "banner": {"containers": [], "controls": [], "best_text": ""}},
            ],
            "events": {"requests": [{"time": now, "phase": "post_denial",
                                     "url": "https://connect.facebook.net/en_US/fbevents.js",
                                     "method": "GET", "resource_type": "script", "is_navigation_request": False}],
                       "responses": [], "request_failures": [], "console": []},
            "errors": [], "raw_har": None, "sanitized_har": None,
            "validity": {"valid": denial_completed, "required_interaction": "denial click",
                         "interaction_completed": denial_completed, "verification_passed": denial_completed,
                         "invalid_reason": None if denial_completed else "The required denial click did not complete (status: manual_required)."},
            "isolation_assertion": {"checked": True, "cookie_count": 0, "local_storage_keys": 0,
                                    "session_storage_keys": 0, "clean": True},
            "page_scan": {"links": [], "page_text": "", "embedded_identifiers": []},
            "consent_mode": {"signals": [], "summary": checks.summarize_consent_mode([])},
        },
        "gpc": {
            "started": now, "finished": now, "gpc": True, "action": "none",
            "action_result": {"status": "no_interaction"},
            "checkpoints": [{**base_checkpoint, "scenario": "gpc", "cookies": [],
                             "storage_state": {"cookies": [], "origins": []}, "browser_state": {"gpc": True}}],
            "events": {"requests": [{"time": now, "phase": "initial_navigation",
                                     "url": "https://bat.bing.com/action/0?ti=secret",
                                     "method": "GET", "resource_type": "image", "is_navigation_request": False}],
                       "responses": [], "request_failures": [], "console": []},
            "errors": [], "raw_har": None, "sanitized_har": None,
            "validity": {"valid": True, "required_interaction": None, "invalid_reason": None},
            "isolation_assertion": {"checked": True, "cookie_count": 0, "local_storage_keys": 0,
                                    "session_storage_keys": 0, "clean": True},
            "page_scan": {"links": [], "page_text": "", "embedded_identifiers": []},
            "consent_mode": {"signals": [], "summary": checks.summarize_consent_mode([])},
        },
        # run_all_scenarios also puts these non-scenario entries into `results`.
        # Every loop over results.items() that calls result.get(...) must tolerate them.
        "baseline_repeats": [
            {
                "started": now, "finished": now, "gpc": False, "action": "none",
                "action_result": {"status": "no_interaction"},
                "checkpoints": [{**base_checkpoint, "scenario": "baseline-repeat-1"}],
                "events": {"requests": [], "responses": [], "request_failures": [], "console": []},
                "errors": [], "raw_har": None, "sanitized_har": None,
                "page_scan": {"links": [], "page_text": "", "embedded_identifiers": []},
                "consent_mode": {"signals": [], "summary": checks.summarize_consent_mode([])},
            },
        ],
        "baseline_stability": {"stable": [], "unstable": [], "run_count": 1, "total_distinct": 0},
        "persistence": {
            "ran": True, "banner_reprompted": False, "banner_text": "",
            "scenario_result": {
                "started": now, "finished": now, "gpc": False, "action": "none",
                "action_result": {"status": "no_interaction"},
                "checkpoints": [{**base_checkpoint, "scenario": "persistence"}],
                "events": {"requests": [], "responses": [], "request_failures": [], "console": []},
                "errors": [], "raw_har": None, "sanitized_har": None,
                "page_scan": {"links": [], "page_text": "", "embedded_identifiers": []},
                "consent_mode": {"signals": [], "summary": checks.summarize_consent_mode([])},
            },
            "note": "The saved preference survived into a fresh context and no re-prompt was observed.",
        },
    }


def test_cookie_inventory_handles_non_scenario_entries() -> None:
    """build_cookie_inventory must tolerate the non-scenario entries that
    run_all_scenarios legitimately puts into `results`: `baseline_repeats` (a list of
    scenario dicts), `baseline_stability` (a dict with no `checkpoints` key), and
    `persistence` (a wrapper dict whose scenario is nested under `scenario_result`).
    A guard that skips every entry would also pass a no-raise check, so this asserts
    the real scenario cookies still come through.
    """
    patterns = read_json(SCRIPT_DIR.parent / "references" / "vendor-patterns.json")
    rows = build_cookie_inventory(synthetic_results(), "example.test", patterns)
    assert rows, "build_cookie_inventory must still return rows for the real scenarios"
    assert any(row.get("scenario") == "baseline" for row in rows), "baseline scenario cookies must be present"
    ok("build_cookie_inventory tolerates list/dict/wrapper non-scenario results entries")


def _metadata() -> dict:
    meta = {"completed_at": utc_now(), "started_at": utc_now(), "location_label": "Offline test",
            "tool": "cookie-banner-auditor", "tool_version": "2.0.0", "profile": "thorough",
            "pages": 2, "locale": "en-US", "viewport": "1440x1000", "target_url": "https://example.test/"}
    meta["run_fingerprint"] = run_fingerprint(meta)
    return meta


def test_analysis_outputs() -> None:
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-test-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        analysis = analyze_and_write(root, "https://example.test/", synthetic_results(True), _metadata(), patterns)

        ids = {f["id"] for f in analysis["findings"]}
        assert "F-PRE-CONSENT-TRACKING" in ids, ids
        assert "F-POST-DENIAL-TRACKING" in ids, ids
        assert "F-GPC-NOT-HONORED" in ids, ids
        assert not any(i.startswith("F-00") for i in ids), f"ids must be stable, not ordinal: {ids}"

        for name in ("audit-data.json", "findings.json", "suppressed-findings.json",
                     "cookie-inventory.csv", "request-inventory.csv",
                     "audit-report.md", "audit-report.html",
                     "research-queue.md", "legal-applicability-questionnaire.md"):
            assert (root / name).is_file(), name

        share_text = (root / "audit-data.json").read_text(encoding="utf-8")
        assert "raw-cookie-value" not in share_text
        assert "secret" not in share_text

        report = (root / "audit-report.md").read_text(encoding="utf-8")
        for section in ("## 1. Executive summary", "## 5. Findings", "## 12. Withheld findings",
                        "## 14. Conclusion", "## Appendix A", "## Appendix B"):
            assert section in report, f"missing report section: {section}"
        assert "Script loaded only" in report or "script_loaded_only" in report
        assert "Context isolation assertions" in report

        inventory = (root / "request-inventory.csv").read_text(encoding="utf-8")
        assert "evidence_strength" in inventory.splitlines()[0]
        ok("analysis writes the 14-section report, appendices, and stable finding ids")


def test_incomplete_run_suppresses_and_flags() -> None:
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-invalid-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        analysis = analyze_and_write(root, "https://example.test/", synthetic_results(False), _metadata(), patterns)

        ids = {f["id"] for f in analysis["findings"]}
        assert "F-POST-DENIAL-TRACKING" not in ids, "must not report post-denial tracking when no denial occurred"
        suppressed_ids = {f["id"] for f in analysis["suppressed_findings"]}
        assert "F-POST-DENIAL-TRACKING" in suppressed_ids, suppressed_ids
        assert "F-GPC-NOT-HONORED" in ids, "the GPC scenario is unaffected and must still report"

        assert analysis["overall_status"].startswith("INCOMPLETE"), analysis["overall_status"]
        assert "denial" in analysis["invalid_scenarios"]

        report = (root / "audit-report.md").read_text(encoding="utf-8")
        assert "RUN INCOMPLETE" in report
        assert "F-POST-DENIAL-TRACKING" in report, "withheld findings must be listed, not silently dropped"

        data = json.loads((root / "audit-data.json").read_text(encoding="utf-8"))
        assert data["run_complete"] is False
        assert data["schema_version"] == "2.0"
        ok("an incomplete run is flagged INCOMPLETE and withholds dependent findings")


def test_zip_bundle() -> None:
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-zip-") as temp:
        root = Path(temp)
        (root / "evidence-private").mkdir()
        (root / "evidence-shareable").mkdir()
        (root / "evidence-private" / "raw.har").write_text('{"log":{}}')
        (root / "evidence-shareable" / "clean.har").write_text('{"log":{}}')
        (root / "audit-report.md").write_text("# Report")

        full = build_zip_bundle(root, root / "full.zip", include_raw=True)
        with zipfile.ZipFile(root / "full.zip") as archive:
            names = set(archive.namelist())
            assert "READ-ME-FIRST.txt" in names
            assert "evidence-private/raw.har" in names
            readme = archive.read("READ-ME-FIRST.txt").decode()
            assert "CONTAINS RAW EVIDENCE" in readme and "Do not email" in readme
        assert full["raw_included"] is True

        shareable = build_zip_bundle(root, root / "share.zip", include_raw=False)
        with zipfile.ZipFile(root / "share.zip") as archive:
            names = set(archive.namelist())
            assert "evidence-private/raw.har" not in names
            assert "evidence-shareable/clean.har" in names
        assert shareable["skipped"] >= 1
        ok("zip bundles raw evidence with a warning README; shareable variant excludes it")


def test_compare_runs() -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    from compare_runs import compare, render_comparison_markdown

    before = {
        "run_fingerprint": "abc123", "overall_status": "Critical issues observed", "run_complete": True,
        "metadata": {"target_url": "https://example.test", "profile": "thorough", "tool_version": "2.0.0"},
        "findings": [{"id": "F-GPC-NOT-HONORED", "title": "GPC ignored", "severity": "critical", "evidence_strength": "beacon_observed"},
                     {"id": "F-PRE-CONSENT-TRACKING", "title": "Pre-consent", "severity": "high"}],
        "scenario_results": {"baseline": {"events": {"requests": [
            {"url": "https://connect.facebook.net/en_US/fbevents.js"},
            {"url": "https://snap.licdn.com/li.lms-analytics/insight.min.js"}]}}},
    }
    after = {
        "run_fingerprint": "abc123", "overall_status": "Review required", "run_complete": True,
        "metadata": {"target_url": "https://example.test", "profile": "thorough", "tool_version": "2.0.0"},
        "findings": [{"id": "F-PRE-CONSENT-TRACKING", "title": "Pre-consent", "severity": "medium"}],
        "scenario_results": {"baseline": {"events": {"requests": [
            {"url": "https://connect.facebook.net/en_US/fbevents.js"}]}}},
    }
    delta = compare(before, after)
    assert delta["fingerprints_match"] is True
    assert [f["id"] for f in delta["findings"]["resolved"]] == ["F-GPC-NOT-HONORED"]
    assert delta["findings"]["new"] == []
    assert delta["endpoints"]["removed_count"] == 1
    assert delta["findings"]["severity_changes"][0]["severity_after"] == "medium"

    markdown = render_comparison_markdown(delta, Path("/before"), Path("/after"))
    assert "F-GPC-NOT-HONORED" in markdown and "## Comparability" in markdown

    mismatched = compare(before, {**after, "metadata": {**after["metadata"], "profile": "quick"}, "run_fingerprint": "zzz"})
    assert mismatched["fingerprints_match"] is False
    assert mismatched["comparability_mismatches"]
    warn = render_comparison_markdown(mismatched, Path("/b"), Path("/a"))
    assert "Run conditions differ" in warn
    ok("compare_runs diffs findings and endpoints and warns on mismatched conditions")


def main() -> int:
    print("\nOffline checks")
    test_har_sanitization()
    test_verify_choice_registered_unit()
    test_transmission_classification()
    test_consent_mode_parsing()
    test_embedded_identifier_scan()
    test_rights_mechanism_scan()
    test_symmetry_measurement()
    test_cmp_table_integrity()
    test_repeat_stability()
    test_validity_gating()
    test_scenario_validity_map()
    test_cookie_inventory_handles_non_scenario_entries()
    test_markdown_to_html()
    test_run_fingerprint()

    print("\nBrowser-backed checks")
    executable = discover_browser_executable(None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True,
                                             chromium_sandbox=False, args=["--no-sandbox"])
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            test_control_detection(page)
            test_denial_flow_and_verification(page)
            test_settings_path_denial(page)
            test_form_exercise_does_not_submit(page)
        finally:
            browser.close()

    print("\nReporting and packaging")
    test_analysis_outputs()
    test_incomplete_run_suppresses_and_flags()
    test_zip_bundle()
    test_compare_runs()

    print(f"\nAll {len(PASSED)} cookie-banner-auditor smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
