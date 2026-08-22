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

import audit_site
from lib import checks
from lib.analysis import (
    analyze_and_write,
    build_cookie_inventory,
    generate_findings,
    partition_findings,
    preconsent_tracking_assertion_hits,
    render_markdown_report,
    scenario_validity_map,
)
from lib.capture import (
    ANNOTATION_LAYER_ID,
    COMPLETED_DENIAL_STATUSES,
    SCORE_THRESHOLD,
    UNSAVED_PREFERENCE_STATUS,
    VIEWPORT_PROFILES,
    ScenarioConfig,
    _scenario_validity,
    annotate_controls,
    annotation_layer_present,
    build_context_options,
    consent_snapshot,
    execute_denial,
    exercise_forms,
    find_control,
    fingerprint_cmp,
    inspect_banner,
    load_cmp_table,
    load_transmission_patterns,
    measure_focus_visibility,
    measure_tab_order,
    verify_choice_registered,
    viewport_profile,
)
from lib.util import (
    build_zip_bundle,
    endpoint_key,
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
# Test infrastructure
# ---------------------------------------------------------------------------

def serve_fixture(page, holder: dict, url: str = "https://fixture.test/") -> dict:
    """Register a route handler that serves `holder["html"]` at a real https
    origin, with no network, server or socket involved.

    `page.set_content(...)` cannot express a reload test: reloading a
    set_content page navigates to about:blank and the fixture vanishes, and
    cookies/localStorage are unavailable or useless there. This intercepts
    every request for `page` before the network layer and fulfils it from
    `holder["html"]`, so `page.goto(url)` and `page.reload()` land on a real
    origin where cookies and localStorage behave normally. Mutating
    `holder["html"]` between loads changes what the next load serves.
    `holder["loads"]` is incremented on every intercepted request.
    """
    holder.setdefault("loads", 0)

    def handler(route) -> None:
        holder["loads"] += 1
        route.fulfill(status=200, content_type="text/html", body=holder["html"])

    page.route("**/*", handler)
    return holder


def test_serve_fixture_seam(page) -> None:
    holder = {"html": "<!doctype html><html><body>fixture-v1</body></html>"}
    serve_fixture(page, holder)

    page.goto("https://fixture.test/")
    assert "https://fixture.test/" in page.url, page.url
    page.evaluate("() => { document.cookie = 'seen=1; path=/'; localStorage.setItem('k', 'v'); }")
    assert page.evaluate("() => document.cookie") == "seen=1", "cookies must work on a real https origin"
    assert page.evaluate("() => localStorage.getItem('k')") == "v", "localStorage must work on a real https origin"
    ok("serve_fixture serves a real https:// origin where cookies and localStorage work")

    # Swap the content and prove a reload re-fetches rather than restoring a
    # cached DOM: assert on a marker present only in the new HTML, read back
    # from the live document rather than from holder["html"] itself.
    holder["html"] = "<!doctype html><html><body>fixture-v2-marker</body></html>"
    page.reload()
    body_text = page.evaluate("() => document.body.innerText")
    assert "fixture-v2-marker" in body_text, body_text
    assert "fixture-v1" not in body_text, body_text
    ok("page.reload() re-serves the swapped holder['html'], proving a real re-fetch")

    # Positive control: a handler that silently stopped intercepting would
    # fall through to the real network (and fail, since fixture.test does not
    # resolve) rather than quietly passing.
    assert holder["loads"] >= 2, holder["loads"]
    ok(f"holder['loads'] reached {holder['loads']} across goto + reload with no real network")

    # Unroute so later tests sharing this `page` (e.g. the real local-HTTP-server
    # test) are not silently intercepted by this fixture's handler.
    page.unroute("**/*")


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


def test_cmp_observational_noise_ignored() -> None:
    """dataLayer byte-count growth alone must never verify a choice, but a
    genuine cmp_api change (e.g. oneTrustActiveGroups) still must."""
    base_cmp = {"hasTCF": True, "hasUSP": False, "hasGPP": False, "oneTrustActiveGroups": None, "consentSignature": "sig1"}
    before = {
        "cookies": {}, "local_storage": {}, "cmp_api": dict(base_cmp),
        "cmp_api_observational": {"consentStateLength": 10, "dataLayerEntryCount": 1},
        "banner_visible": True,
    }

    noisy_after = {
        "cookies": {}, "local_storage": {}, "cmp_api": dict(base_cmp),
        "cmp_api_observational": {"consentStateLength": 987654, "dataLayerEntryCount": 500},
        "banner_visible": True,
    }
    noisy_result = verify_choice_registered(before, noisy_after)
    assert noisy_result["verified"] is False, noisy_result
    assert noisy_result["cmp_api_changed"] is False, noisy_result

    real_after = {
        "cookies": {}, "local_storage": {},
        "cmp_api": {**base_cmp, "oneTrustActiveGroups": "C0001,C0002,C0003"},
        "cmp_api_observational": {"consentStateLength": 10, "dataLayerEntryCount": 1},
        "banner_visible": True,
    }
    real_result = verify_choice_registered(before, real_after)
    assert real_result["verified"] is True, real_result
    assert real_result["cmp_api_changed"] is True, real_result

    expected_keys = {
        "new_cookies", "changed_cookies", "new_storage_keys", "changed_storage_keys",
        "cmp_api_changed", "banner_dismissed", "consent_state_changed", "verified", "note",
    }
    assert set(noisy_result.keys()) == expected_keys, noisy_result.keys()
    assert set(real_result.keys()) == expected_keys, real_result.keys()
    ok("cmp_api_observational growth never verifies; a real cmp_api change still does; keys unchanged")


def test_local_storage_same_length_rewrite_detected(page) -> None:
    """Positive control: a localStorage value rewritten to a different value of
    the *identical length* must still be detected as a change. `consent_snapshot`
    previously recorded only `len(value)`, so this rewrite was invisible; it now
    records `short_hash(value)` instead."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silence request logging
            pass

        def do_GET(self) -> None:
            body = b"<!doctype html><html><body>fixture</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(("127.0.0.1", 0), _Handler) as server:
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            page.goto(f"http://127.0.0.1:{port}/")
            page.evaluate("() => localStorage.setItem('consent_pref', 'AAAA')")
            before = consent_snapshot(page, page.context)
            page.evaluate("() => localStorage.setItem('consent_pref', 'ZZZZ')")
            after = consent_snapshot(page, page.context)
            result = verify_choice_registered(before, after)
            assert result["changed_storage_keys"] == ["consent_pref"], result
            assert result["verified"] is True, result
        finally:
            server.shutdown()
    ok("a same-length localStorage value rewrite is detected via content hash")


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


def test_settings_path_denial_without_save_control(page) -> None:
    """A preferences layer whose toggles can be switched off but which offers no
    resolvable save control must not report "No denial control was operated" -
    the toggles *were* operated and page state was mutated.

    Reachable in the real world whenever a CMP's `save` selector list is
    intentionally empty (HubSpot, TrustArc, Quantcast Choice), so the fixture
    reproduces that shape: an open panel with optional toggles and no save
    button at all."""
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
        </div>
        <script>
          settings.addEventListener('click', () => { document.querySelector('#cookie-consent').hidden=true; panel.hidden=false; });
        </script></body></html>
    """)
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))

    assert result["status"] == UNSAVED_PREFERENCE_STATUS, result
    disabled = result.get("toggle_result", {}).get("disabled", [])
    assert len(disabled) >= 2, result

    note = (result.get("verification") or {}).get("note", "")
    assert "No denial control was operated" not in note, (
        f"the toggles were operated, so this note is false: {note!r}"
    )
    assert "never committed" in note, note

    # The decision this status encodes: an unsaved preference panel is not a
    # recorded choice, so the scenario stays invalid and cannot support
    # findings about post-denial behaviour.
    assert UNSAVED_PREFERENCE_STATUS not in COMPLETED_DENIAL_STATUSES
    validity = _scenario_validity("deny", result, [])
    assert validity["interaction_completed"] is False, validity
    assert validity["valid"] is False, validity
    ok("toggles disabled with no save control is reported accurately and stays invalid")


def test_settings_path_no_toggles_still_reports_manual_required(page) -> None:
    """The accurate-note fix must not swallow the genuine case. When the
    preferences layer opens but nothing is actually operated - no optional
    toggle was on to begin with - "No denial control was operated" is true and
    must still be what the run reports."""
    page.set_content("""
        <!doctype html><html><body>
        <div id="cookie-consent" role="dialog" style="position:fixed;bottom:0;left:0;right:0;padding:24px;background:white">
          <p>Choose cookie preferences for analytics and advertising.</p>
          <button id="accept">Accept All</button>
          <button id="settings">Cookie Preferences</button>
        </div>
        <div id="panel" role="dialog" hidden>
          <label><input id="necessary" type="checkbox" checked disabled> Strictly necessary</label>
          <label><input id="analytics" type="checkbox"> Analytics</label>
          <label><input id="ads" type="checkbox"> Advertising</label>
        </div>
        <script>
          settings.addEventListener('click', () => { document.querySelector('#cookie-consent').hidden=true; panel.hidden=false; });
        </script></body></html>
    """)
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    assert result["status"] == "manual_required", result
    assert not (result.get("toggle_result", {}).get("disabled") or []), result
    assert "No denial control was operated" in (result.get("verification") or {}).get("note", "")
    ok("a preferences layer where nothing was operated still reports manual_required")


def _fresh_content(page, html: str) -> None:
    """Load `html` on a genuinely fresh document.

    A `set_content()` immediately after a prior `set_content()` on the same
    `page` can leave Chromium's tabindex-ordered focus chain reflecting the
    previous document's structure rather than the new one - reproducible even
    though the DOM itself is fully replaced. An explicit navigation to
    about:blank in between forces a real frame reset, which the tab-order
    tests below depend on for a trustworthy reading."""
    page.goto("about:blank")
    page.set_content(html)


def _cookie_banner_html(accept_tabindex: int, reject_tag: str, reject_tabindex: int | str) -> str:
    return f"""
        <!doctype html><html><body>
        <div style="position:fixed;bottom:0;padding:20px">
          <p>We use cookies for analytics and advertising on this site.</p>
          <button id="accept" tabindex="{accept_tabindex}">Accept All</button>
          <{reject_tag} id="reject" href="#" tabindex="{reject_tabindex}">Reject All</{reject_tag}>
        </div>
        </body></html>
    """


def test_tab_order_direction(page) -> None:
    """A fixture where Decline is reachable before Accept and one where it is
    reachable after must produce different `accept_precedes_reject` results -
    a single-direction test would pass against an implementation that always
    returned the same answer."""
    _fresh_content(page, _cookie_banner_html(accept_tabindex=1, reject_tag="button", reject_tabindex=2))
    forward = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    forward_symmetry = checks.measure_symmetry(forward["accept_candidates"][0], forward["reject_candidates"][0])
    assert forward_symmetry["accept_tab_position"] == 1, forward_symmetry
    assert forward_symmetry["reject_tab_position"] == 2, forward_symmetry
    assert forward_symmetry["accept_precedes_reject"] is True, forward_symmetry

    _fresh_content(page, _cookie_banner_html(accept_tabindex=2, reject_tag="button", reject_tabindex=1))
    reversed_result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    reversed_symmetry = checks.measure_symmetry(reversed_result["accept_candidates"][0], reversed_result["reject_candidates"][0])
    assert reversed_symmetry["accept_tab_position"] == 2, reversed_symmetry
    assert reversed_symmetry["reject_tab_position"] == 1, reversed_symmetry
    assert reversed_symmetry["accept_precedes_reject"] is False, reversed_symmetry
    ok("real tab order distinguishes Decline-before-Accept from Accept-before-Decline")


def test_tab_order_unreachable_control(page) -> None:
    """A control that is not keyboard reachable at all (tabindex=-1, skipped
    by sequential Tab navigation) must not crash the traversal and must be
    recorded as unreachable - not silently as tab position 0 or as preceding
    the other control."""
    _fresh_content(page, _cookie_banner_html(accept_tabindex=1, reject_tag="a", reject_tabindex=-1))
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    symmetry = checks.measure_symmetry(result["accept_candidates"][0], result["reject_candidates"][0])
    assert symmetry["comparable"] is True, symmetry
    assert symmetry["accept_tab_reachable"] is True, symmetry
    assert symmetry["accept_tab_position"] == 1, symmetry
    assert symmetry["reject_tab_reachable"] is False, symmetry
    assert symmetry["reject_tab_position"] is None, symmetry
    # The traversal completed a full lap of the page's real focus order (it
    # cycled back to Accept, the only reachable control) without exhausting
    # its press budget, so the cap was never the limiting factor here - the
    # unreachability is proven, not merely unmeasured. Contrast with
    # test_measure_tab_order_bounded, where the budget genuinely runs out.
    assert symmetry["tab_order_cap_hit"] is False, symmetry
    assert symmetry["accept_precedes_reject"] is None, "must not guess precedence when one control is unreachable"
    ok("a tab-unreachable control is recorded as unreachable, not as position 0 or as preceding")


def test_tab_order_reaches_iframe_hosted_controls(page) -> None:
    """Iframe-hosted CMPs (Sourcepoint, TrustArc, and similar) render the
    accept/reject controls inside a child frame, not the main document. When
    focus is inside that child frame, the *main* frame's own
    `document.activeElement` is the `<iframe>` element itself - not null, not
    body - so a traversal that accepts the first frame reporting a non-body
    `activeElement` would stop there and never see the real control. This
    must instead descend into the frame that actually holds focus and report
    both controls as genuinely reachable, in the right relative order."""
    inner_html = _cookie_banner_html(accept_tabindex=1, reject_tag="button", reject_tabindex=2)
    escaped_srcdoc = inner_html.replace('"', "&quot;")
    _fresh_content(page, f"""
        <!doctype html><html><body>
        <iframe id="cmp" srcdoc="{escaped_srcdoc}" style="width:400px;height:200px;border:0"></iframe>
        </body></html>
    """)
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    symmetry = checks.measure_symmetry(result["accept_candidates"][0], result["reject_candidates"][0])
    assert symmetry["comparable"] is True, symmetry
    assert isinstance(symmetry["accept_tab_position"], int), symmetry
    assert isinstance(symmetry["reject_tab_position"], int), symmetry
    assert symmetry["accept_tab_position"] < symmetry["reject_tab_position"], symmetry
    assert symmetry["accept_precedes_reject"] is True, symmetry
    assert symmetry["accept_tab_reachable"] is True, symmetry
    assert symmetry["reject_tab_reachable"] is True, symmetry
    ok("tab-order traversal descends into an iframe-hosted CMP and reaches both controls")


def test_symmetry_early_exit_survives_new_fields(page) -> None:
    """measure_symmetry's early-exit contract (comparable: False when either
    control is missing) must still hold once tab-order and focus-visibility
    fields are folded in."""
    _fresh_content(page, _cookie_banner_html(accept_tabindex=1, reject_tag="button", reject_tabindex=2))
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    accept_only = checks.measure_symmetry(result["accept_candidates"][0], None)
    assert accept_only == {"comparable": False, "reason": "reject control not found"}, accept_only
    reject_only = checks.measure_symmetry(None, result["reject_candidates"][0])
    assert reject_only == {"comparable": False, "reason": "accept control not found"}, reject_only
    ok("measure_symmetry's comparable:False early exit is unaffected by the new measured fields")


def test_focus_visibility_detection(page) -> None:
    """Positive control required: the detector must be shown able to report
    both a visible focus indicator and the absence of one."""
    _fresh_content(page, """
        <!doctype html><html><head><style>
          #ring:focus { outline: 3px solid blue; }
          #noring:focus { outline: none; box-shadow: none; }
        </style></head><body>
          <button id="ring" style="border:1px solid #ccc">Has Ring</button>
          <button id="noring" style="border:1px solid #ccc">No Ring</button>
        </body></html>
    """)
    visible = measure_focus_visibility(page.locator("#ring"))
    assert visible["measured"] is True, visible
    assert visible["visible"] is True, visible
    assert "outlineStyle" in visible["changed_properties"], visible

    hidden = measure_focus_visibility(page.locator("#noring"))
    assert hidden["measured"] is True, hidden
    assert hidden["visible"] is False, hidden
    assert hidden["changed_properties"] == [], hidden
    ok("focus-visibility detector reports both a visible ring and a suppressed one")


def test_measure_tab_order_distinguishes_cap_from_unreachable(page) -> None:
    """A control missing from `positions` can mean two different things: it
    does not appear anywhere in the page's real focus order, or it merely
    sits past the Tab-press budget. A `cap_hit` derived only from `position
    is None` cannot tell these apart - this asserts they resolve to
    different, correct values."""
    _fresh_content(page, """
        <!doctype html><html><body>
          <button id="a">A</button>
          <button id="b">B</button>
          <button id="unreachable" tabindex="-1">Unreachable</button>
        </body></html>
    """)
    unreachable_result = measure_tab_order(
        page, {"unreachable": page.locator("#unreachable")}, max_presses=10
    )
    assert unreachable_result["positions"]["unreachable"] is None, unreachable_result
    assert unreachable_result["cap_hit"] is False, (
        "a control excluded from the focus order entirely must be provable "
        f"within budget, not reported as a cap hit: {unreachable_result}"
    )

    many_buttons = "".join(f'<button id="btn{i}">{i}</button>' for i in range(120))
    _fresh_content(page, f"<!doctype html><html><body>{many_buttons}</body></html>")
    capped_result = measure_tab_order(page, {"far": page.locator("#btn119")}, max_presses=20)
    assert capped_result["positions"]["far"] is None, capped_result
    assert capped_result["cap_hit"] is True, (
        f"a reachable control sitting past the budget must report cap_hit: {capped_result}"
    )

    assert unreachable_result["cap_hit"] != capped_result["cap_hit"], (
        "a genuinely unreachable control and a reachable-but-past-budget "
        f"control must not be indistinguishable: {unreachable_result} vs {capped_result}"
    )
    ok("cap_hit distinguishes a genuinely unreachable control from one merely past the Tab-press budget")


def test_execute_denial_measures_focus_visibility_per_control(page) -> None:
    """Acceptance criterion: measure_symmetry must carry a focus-visibility
    result for each control. This exercises the real execute_denial ->
    accept_candidates[0]/reject_candidates[0] -> measure_symmetry wiring,
    not measure_focus_visibility in isolation, so a regression that drops
    the `focus_visible=` fields at the execute_denial call site is caught."""
    _fresh_content(page, """
        <!doctype html><html><head><style>
          #accept:focus { outline: 3px solid blue; }
          #reject:focus { outline: none; box-shadow: none; }
        </style></head><body>
        <div style="position:fixed;bottom:0;padding:20px">
          <p>We use cookies for analytics and advertising on this site.</p>
          <button id="accept" style="border:1px solid #ccc" tabindex="1">Accept All</button>
          <button id="reject" style="border:1px solid #ccc" tabindex="2">Reject All</button>
        </div>
        </body></html>
    """)
    result = execute_denial(page, page.context, wait_ms=20, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    symmetry = checks.measure_symmetry(result["accept_candidates"][0], result["reject_candidates"][0])
    assert symmetry["accept_focus_visible"] is True, symmetry
    assert symmetry["reject_focus_visible"] is False, symmetry
    ok("execute_denial wires a per-control focus-visibility result through to measure_symmetry")


def test_measure_tab_order_bounded(page) -> None:
    """A control past the traversal's Tab budget must be reported as capped,
    not falsely reachable - and the traversal itself must not hang."""
    _fresh_content(page, """
        <!doctype html><html><body>
          <button id="a">A</button>
          <button id="b">B</button>
          <button id="c">C</button>
        </body></html>
    """)
    result = measure_tab_order(page, {"c": page.locator("#c")}, max_presses=1)
    assert result["positions"]["c"] is None, result
    assert result["cap_hit"] is True, result
    assert result["max_presses"] == 1
    ok("measure_tab_order bounds its Tab-press budget and reports the cap being hit")


def test_annotate_controls_marks_resolved_controls(page) -> None:
    """The pre-flight image must outline what would be clicked, and must skip a
    control with no measurable box rather than drawing it at the origin, where
    it would read as a control sitting in the top-left corner."""
    page.set_content("""
        <!doctype html><html><body>
        <div style="position:fixed;bottom:0;padding:20px">
          <p>We use cookies for analytics and advertising on this site.</p>
          <button id="accept">Accept All</button>
          <button id="reject">Reject All</button>
        </div>
        </body></html>
    """)
    reject_box = page.locator("#reject").bounding_box()
    drawn = annotate_controls(page, [
        {"box": reject_box, "color": "#1a7f37", "label": "reject: Reject All"},
        {"box": None, "color": "#cf222e", "label": "accept: unmeasurable"},
        {"box": {"x": 0, "y": 0, "width": 0, "height": 0}, "color": "#0969da", "label": "save: zero-size"},
    ])
    assert drawn == 1, "only the one control with a real box may be outlined"

    layer = page.evaluate(
        "(id) => { const el = document.getElementById(id);"
        " return el ? {children: el.children.length, pointer: getComputedStyle(el).pointerEvents} : null; }",
        ANNOTATION_LAYER_ID,
    )
    assert layer is not None, "the annotation layer must be attached"
    assert layer["children"] == 2, f"one outline plus one text label expected: {layer}"
    # It sits over a live page during pre-flight; it must never intercept a click.
    assert layer["pointer"] == "none", layer

    # Re-annotating replaces rather than stacking, so a second call cannot leave
    # stale outlines from the first pointing at the wrong elements.
    annotate_controls(page, [{"box": reject_box, "color": "#1a7f37", "label": "reject"}])
    count = page.evaluate(
        "(id) => document.querySelectorAll('#' + CSS.escape(id)).length", ANNOTATION_LAYER_ID
    )
    assert count == 1, f"a second annotation pass must replace the layer, not stack: {count}"

    # Observed on a real React site: the page's own framework can remove an
    # element appended to <html> after hydration. The caller must be able to
    # detect that, or it captions an unannotated image as annotated.
    assert annotation_layer_present(page) is True
    page.evaluate("(id) => document.getElementById(id).remove()", ANNOTATION_LAYER_ID)
    assert annotation_layer_present(page) is False, (
        "a removed overlay must be detectable, not assumed still present"
    )
    assert annotate_controls(page, [{"box": reject_box, "color": "#1a7f37", "label": "reject"}]) == 1
    assert annotation_layer_present(page) is True, "re-drawing must restore the overlay"
    ok("the pre-flight overlay marks resolved controls, skips unmeasurable ones, and replaces itself")


def test_annotation_labels_are_painted_above_every_outline(page) -> None:
    """With stacked controls, a later outline must not paint over an earlier
    label — on an accept/decline pair that struck through the very text saying
    which button is which."""
    page.set_content("""
        <!doctype html><html><body>
        <div style="position:fixed;bottom:0;padding:20px">
          <button id="accept" style="display:block;width:200px">Accept All</button>
          <button id="reject" style="display:block;width:200px">Reject All</button>
        </div>
        </body></html>
    """)
    marks = [
        {"box": page.locator("#accept").bounding_box(), "color": "#cf222e", "label": "accept: Accept All"},
        {"box": page.locator("#reject").bounding_box(), "color": "#1a7f37", "label": "reject: Reject All"},
    ]
    assert annotate_controls(page, marks) == 2
    kinds = page.evaluate(
        "(id) => Array.from(document.getElementById(id).children)"
        ".map(el => el.textContent ? 'label' : 'outline')",
        ANNOTATION_LAYER_ID,
    )
    assert kinds == ["outline", "outline", "label", "label"], (
        f"all outlines must be appended before any label so labels stay legible: {kinds}"
    )
    ok("annotation labels are painted above every outline, not interleaved")


def test_mobile_emulation_reaches_the_page(page) -> None:
    """End-to-end proof that the mobile profile changes what the page observes.

    The unit test above asserts the options dict is built correctly; this
    asserts Chromium actually applies it. Without this, the options could stop
    being passed to new_context and every run would still pass while capturing
    the desktop banner under a mobile label."""
    profile = viewport_profile("mobile")
    config = ScenarioConfig(
        url="https://example.test",
        viewport=dict(profile["viewport"]),
        viewport_label="mobile",
        is_mobile=profile["is_mobile"],
        has_touch=profile["has_touch"],
        device_scale_factor=profile["device_scale_factor"],
        device_user_agent=profile["user_agent"],
    )
    probe = (
        "() => ({ua: navigator.userAgent, width: window.innerWidth,"
        " touch: navigator.maxTouchPoints > 0, dpr: window.devicePixelRatio})"
    )
    responsive_page = """
        <!doctype html><html><head>
          <meta name="viewport" content="width=device-width, initial-scale=1">
        </head><body>viewport probe</body></html>
    """
    context = page.context.browser.new_context(**build_context_options(config))
    try:
        mobile_page = context.new_page()
        mobile_page.set_content(responsive_page)
        observed = mobile_page.evaluate(probe)
        assert "Mobile" in observed["ua"], observed
        assert observed["width"] == profile["viewport"]["width"], observed
        assert observed["touch"] is True, observed
        assert observed["dpr"] > 1, observed

        # Documenting a real emulation quirk rather than asserting a wish: with
        # is_mobile set, Chromium lays out a page that declares no viewport meta
        # tag at the legacy 980px default, NOT at the device width. Every modern
        # responsive site ships the meta tag, so audits see the device width -
        # but a target that omits it is genuinely laid out wide on a phone, and
        # that is the site's behaviour, not a bug in this runner. Do not "fix"
        # this by forcing the viewport.
        legacy_page = context.new_page()
        legacy_page.set_content("<!doctype html><html><body>no meta</body></html>")
        legacy = legacy_page.evaluate(probe)
        # Asserted as a range: Chromium reports 981 rather than exactly 980 at
        # this device scale, and pinning the rounding would break on a browser
        # update without anything meaningful having changed.
        assert legacy["width"] >= 900, (
            "a page with no viewport meta tag is expected to lay out near the 980px "
            f"legacy default under mobile emulation: {legacy}"
        )
        assert legacy["width"] > observed["width"], (
            f"the no-meta page must lay out wider than the responsive one: {legacy} vs {observed}"
        )
        assert "Mobile" in legacy["ua"], legacy
    finally:
        context.close()

    # The desktop profile must not leak any of that into its own contexts.
    desktop_profile = viewport_profile("desktop")
    desktop_config = ScenarioConfig(
        url="https://example.test",
        viewport=dict(desktop_profile["viewport"]),
        viewport_label="desktop",
    )
    desktop_context = page.context.browser.new_context(**build_context_options(desktop_config))
    try:
        desktop_page = desktop_context.new_page()
        desktop_page.set_content("<!doctype html><html><body>viewport probe</body></html>")
        observed = desktop_page.evaluate(
            "() => ({ua: navigator.userAgent, width: window.innerWidth, touch: navigator.maxTouchPoints > 0})"
        )
        assert "Mobile" not in observed["ua"], observed
        assert observed["width"] == 1440, observed
        assert observed["touch"] is False, observed
    finally:
        desktop_context.close()
    ok("the mobile profile changes the page's real user agent, width, touch, and pixel ratio")


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
    # Neither control dict carries any tab-order fields here (measure_tab_order
    # never ran, e.g. because a resolved control still fell below the score
    # threshold). That must read as "not measured", not as the false
    # affirmative "measured, and the cap was not hit".
    assert symmetric["tab_order_cap_hit"] is None, symmetric

    smaller = {**button, "box": {"width": 60, "height": 20},
               "style": {**button["style"], "backgroundColor": "rgb(240, 240, 240)"}}
    asymmetric = checks.measure_symmetry(button, smaller)
    assert asymmetric["symmetric"] is False
    assert asymmetric["area_equivalent"] is False
    assert asymmetric["same_background_color"] is False

    assert checks.measure_symmetry(button, None)["comparable"] is False
    assert checks.contrast_ratio("rgb(0,0,0)", "rgb(255,255,255)") == 21.0
    ok("symmetry and WCAG contrast measured from rendered styles")


def test_issue_matrix_generation() -> None:
    """`build_issue_matrix` must build Section 9 from the findings actually
    emitted, not a static block. This is the whole defect from issue #9, so
    both directions are asserted against two different synthetic finding sets:
    a run with a GPC finding must produce a GPC-implicating row citing its id,
    and a run with no GPC finding must produce no such row.
    """
    with_gpc = checks.build_issue_matrix([
        {"id": "F-GPC-NOT-HONORED", "check_type": "gpc-not-honored"},
        {"id": "F-EMBEDDED-IDENTIFIER", "check_type": "embedded-identifier"},
    ])
    assert with_gpc, "a GPC finding must produce at least one row"
    gpc_rows = [r for r in with_gpc if "F-GPC-NOT-HONORED" in r["evidence"]]
    assert gpc_rows, with_gpc
    assert any("Global Privacy Control" in r["requirement"] for r in gpc_rows), with_gpc
    assert any("F-EMBEDDED-IDENTIFIER" in r["evidence"] for r in with_gpc), with_gpc

    without_gpc = checks.build_issue_matrix([
        {"id": "F-EMBEDDED-IDENTIFIER", "check_type": "embedded-identifier"},
    ])
    assert without_gpc, "a non-GPC finding can still produce a row (California disclosure theory)"
    assert not any("Global Privacy" in str(r) or "opt-out preference" in str(r).lower() for r in without_gpc), without_gpc
    assert all("F-EMBEDDED-IDENTIFIER" in r["evidence"] for r in without_gpc), without_gpc

    assert checks.build_issue_matrix([]) == []

    # Findings that explicitly disclaim any legal inference must not produce a
    # row even though they are known, mapped check_type values.
    no_inference = checks.build_issue_matrix([
        {"id": "F-CAPTURE-ERRORS-BASELINE", "check_type": "capture-errors"},
        {"id": "F-DENIAL-CONTROL-UNRESOLVED", "check_type": "denial-control-unresolved"},
        {"id": "F-UNSTABLE-TAG-BEHAVIOUR", "check_type": "unstable-tag-behaviour"},
        {"id": "F-INSECURE-AUTH-COOKIE", "check_type": "insecure-auth-cookie"},
        {"id": "F-UNRESOLVED-PURPOSES", "check_type": "unresolved-purposes"},
    ])
    assert no_inference == [], no_inference

    # An unrecognised check_type - including a not-yet-landed one - must not raise.
    unmapped = checks.build_issue_matrix([
        {"id": "F-DENIAL-AUTOSAVE-UNCONFIRMED", "check_type": "denial-autosave-unconfirmed"},
        {"id": "F-SOME-FUTURE-CHECK", "check_type": "not-a-real-check-type"},
    ])
    assert unmapped == [], unmapped
    ok("build_issue_matrix generates Section 9 rows from evidence in both directions and tolerates unmapped check_types")


def test_issue_matrix_renders_in_report() -> None:
    """The rendered report must reflect `build_issue_matrix`, not the old static
    block: no finding must ever produce a row without a real finding id, the
    literal fallback text must be gone, and a zero-finding run still renders a
    well-formed section rather than a broken or truncated table.
    """
    root = Path(tempfile.gettempdir())
    metadata = _metadata()

    gpc_finding = {"id": "F-GPC-NOT-HONORED", "check_type": "gpc-not-honored", "severity": "critical", "certainty": "high"}
    with_findings = render_markdown_report(root, "https://example.test/", metadata, [gpc_finding], [], [], {})
    assert "## 9. Legal issue-spotting matrix" in with_findings
    assert "See findings above" not in with_findings
    section = with_findings.split("## 9. Legal issue-spotting matrix", 1)[1].split("## 10.", 1)[0]
    assert "F-GPC-NOT-HONORED" in section, section
    assert "Authority | Requirement or theory | Observed evidence | Missing applicability facts" in section

    empty = render_markdown_report(root, "https://example.test/", metadata, [], [], [], {})
    assert "## 9. Legal issue-spotting matrix" in empty
    assert "See findings above" not in empty
    empty_section = empty.split("## 9. Legal issue-spotting matrix", 1)[1].split("## 10.", 1)[0]
    assert "_None observed._" in empty_section, empty_section
    assert "prompt for counsel, not a conclusion" in empty_section
    ok("Section 9 renders real evidence when present and the None-observed convention when it is not")


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

def test_time_budget_skips_only_corroborating_work() -> None:
    """The wall-clock ceiling must never drop baseline or denial - the findings
    rest on them - and must record every drop rather than truncating silently."""
    from lib import capture

    calls: list[str] = []

    def fake_run_scenario_with_retry(browser, scenario, config, private_dir, share_dir, action, **kwargs):
        calls.append(scenario)
        return {"scenario": scenario, "checkpoints": [], "events": {"requests": []},
                "page_scan": {"links": []}, "validity": {"valid": True}}

    originals = (capture.run_scenario_with_retry, capture.run_persistence_check, capture.capture_policy_texts)
    capture.run_scenario_with_retry = fake_run_scenario_with_retry
    capture.run_persistence_check = lambda *a, **k: calls.append("persistence") or {}
    capture.capture_policy_texts = lambda *a, **k: calls.append("policies") or {}
    try:
        # A budget of zero is already spent when the first check runs, so every
        # droppable step is dropped and only the mandatory pair survives.
        results = capture.run_all_scenarios(
            browser=None, config=ScenarioConfig(url="https://example.test"),
            private_dir=Path(tempfile.mkdtemp()), share_dir=Path(tempfile.mkdtemp()),
            include_gpc=True, include_accept=True, baseline_repeats=2,
            include_persistence=True, include_policies=True, time_budget_s=0,
        )
        assert calls == ["baseline", "denial"], f"only the mandatory scenarios may survive: {calls}"
        budget = results["time_budget"]
        assert budget["exceeded"] is True, budget
        dropped = {step["step"] for step in budget["skipped_steps"]}
        assert dropped == {
            "gpc scenario", "accept-control scenario", "baseline repeat 1",
            "policy text capture", "persistence check",
        }, f"every drop must be recorded, not silently truncated: {dropped}"

        # No budget: nothing is dropped, and behaviour is exactly as before.
        calls.clear()
        results = capture.run_all_scenarios(
            browser=None, config=ScenarioConfig(url="https://example.test"),
            private_dir=Path(tempfile.mkdtemp()), share_dir=Path(tempfile.mkdtemp()),
            include_gpc=True, include_accept=True, baseline_repeats=1,
            include_persistence=True, include_policies=True, time_budget_s=None,
        )
        assert calls == ["baseline", "denial", "gpc", "accept", "baseline-repeat-1", "policies", "persistence"], calls
        assert results["time_budget"]["exceeded"] is False, results["time_budget"]
        assert results["time_budget"]["skipped_steps"] == []
    finally:
        capture.run_scenario_with_retry, capture.run_persistence_check, capture.capture_policy_texts = originals
    ok("the time budget drops only corroborating work, never baseline or denial, and records every drop")


def test_policy_link_selection() -> None:
    """E6 selects which policy documents to archive. It must file each link
    under its most specific kind, treat a fragment as the same document, and
    refuse application surfaces that merely look like policy links."""
    links = [
        {"text": "Cookie Policy", "href": "https://a.test/legal/cookies"},
        {"text": "Privacy Policy", "href": "https://a.test/legal/privacy#top"},
        {"text": "Privacy", "href": "https://a.test/legal/privacy"},
        {"text": "Do Not Sell or Share My Personal Information", "href": "https://a.test/dns"},
        {"text": "Log in", "href": "https://a.test/account/login?next=/privacy"},
        {"text": "Privacy settings", "href": "https://a.test/settings/privacy"},
        {"text": "Home", "href": "https://a.test/"},
        {"text": "", "href": "https://cdn.other.test/privacy-policy.pdf"},
        {"text": "Email us", "href": "mailto:privacy@a.test"},
        {"text": "Privacy", "href": "/relative/privacy"},
    ]
    selected = checks.select_policy_links(links)
    by_url = {s["url"]: s for s in selected}

    assert by_url["https://a.test/legal/cookies"]["kind"] == "cookie_policy"
    assert by_url["https://a.test/legal/privacy"]["kind"] == "privacy_policy"
    # Most specific wins: this is an opt-out mechanism, not a generic privacy page.
    assert by_url["https://a.test/dns"]["kind"] == "sale_share_optout"
    # A bare URL with no link text is still matched, on the path.
    assert by_url["https://cdn.other.test/privacy-policy.pdf"]["kind"] == "privacy_policy"

    # /privacy and /privacy#top are one document; archiving both would store it
    # twice under two names.
    assert sum(1 for s in selected if s["url"].endswith("/legal/privacy")) == 1

    for rejected in (
        "https://a.test/account/login?next=/privacy",   # login page, not a policy
        "https://a.test/settings/privacy",              # a settings widget, not a document
        "https://a.test/",
        "mailto:privacy@a.test",
        "/relative/privacy",                            # not absolute; cannot be fetched as-is
    ):
        assert rejected not in by_url, f"must not be selected for archiving: {rejected}"

    # Regression, found on a live site: Google's cross-domain linker decorates
    # every outbound link with a distinct `_gl` value, so one policy appeared
    # under four URLs and was archived four times, burning the cap. Worse, `_gl`
    # and `_ga` carry the visitor's GA client id - fetching the decorated URL
    # would have the audit transmit that identifier to the policy host as a side
    # effect of auditing.
    assert checks.strip_tracking_params("https://a.test/p?_gl=1*x&lang=es&utm_source=n&id=7") == (
        "https://a.test/p?lang=es&id=7"
    )
    decorated = [
        {"text": "Cookie Policy", "href": "https://l.test/cookie-policy?_gl=1*abc*_gcl_au*A"},
        {"text": "Privacy Policy", "href": "https://l.test/privacy-policy?_gl=1*def*_gcl_au*B"},
        {"text": "Privacy", "href": "https://l.test/privacy-policy"},
        {"text": "Privacy", "href": "https://l.test/privacy-policy?_gl=1*ghi*_ga*C"},
        {"text": "Cookies", "href": "https://l.test/cookie-policy?_gl=1*jkl*_ga*D"},
    ]
    deduped = checks.select_policy_links(decorated)
    assert len(deduped) == 2, f"linker-decorated duplicates must collapse to two documents: {deduped}"
    for entry in deduped:
        assert "_gl" not in entry["url"] and "_ga" not in entry["url"], (
            f"the archived URL must not carry a GA identifier: {entry['url']}"
        )
    # A meaningful parameter is not a tracking parameter and must survive, since
    # it can select a different document.
    localised = checks.select_policy_links([{"text": "Privacy", "href": "https://l.test/privacy?lang=es"}])
    assert localised[0]["url"].endswith("?lang=es"), localised

    # The cap is honoured, so a link farm cannot turn a pre-flight into a crawl.
    many = [{"text": f"Privacy {i}", "href": f"https://a.test/p{i}"} for i in range(40)]
    assert len(checks.select_policy_links(many, limit=3)) == 3
    ok("policy-link selection files each document by kind, dedupes fragments, and skips app surfaces")


def test_meta_ldu_signal_parsing() -> None:
    """Meta LDU is a transmission-layer restriction like a denied Consent Mode
    signal, and must be recognised without contaminating the Google-derived
    fields that drive the consent-enforced-at-transmission finding."""
    ldu = checks.parse_meta_ldu_signal(
        "https://www.facebook.com/tr/?id=123&ev=PageView&dpo=LDU&dpoco=1&dpost=1000"
    )
    assert ldu is not None and ldu["vendor"] == "meta", ldu
    assert ldu["ldu_active"] is True, ldu
    assert ldu["country_raw"] == "1" and ldu["state_raw"] == "1000", ldu
    assert ldu["pixel_id"] == "123", ldu

    # A pixel request with no dpo parameter carries no LDU signal at all.
    assert checks.parse_meta_ldu_signal("https://www.facebook.com/tr/?id=1&ev=PageView") is None
    # dpo present but not LDU: recognised, and explicitly not active.
    off = checks.parse_meta_ldu_signal("https://www.facebook.com/tr/?id=1&dpo=0")
    assert off is not None and off["ldu_active"] is False, off
    # Right parameter, wrong vendor: must not be claimed as a Meta signal.
    assert checks.parse_meta_ldu_signal("https://evil.test/tr/?dpo=LDU") is None

    # Dispatch picks the right vendor for each.
    google = checks.parse_consent_signal("https://www.google-analytics.com/g/collect?gcs=G100&tid=G-1")
    assert google["vendor"] == "google" and google["all_denied"] is True, google
    meta = checks.parse_consent_signal("https://www.facebook.com/tr/?id=1&dpo=LDU")
    assert meta["vendor"] == "meta", meta
    assert checks.parse_consent_signal("https://example.test/page") is None

    # A Meta signal must not dilute or satisfy the Google-only test that drives
    # the consent-enforced-at-transmission finding.
    google_only = checks.summarize_consent_mode([google])
    assert google_only["all_signals_denied"] is True, google_only
    assert google_only["signal_count"] == 1, google_only

    mixed = checks.summarize_consent_mode([google, meta])
    assert mixed["all_signals_denied"] is True, "the Meta row must not dilute the Google verdict"
    assert mixed["signal_count"] == 1, f"signal_count stays Google-only: {mixed}"
    assert mixed["total_signal_count"] == 2, mixed
    assert mixed["vendors"] == ["google", "meta"], mixed
    assert mixed["meta_ldu_active"] is True, mixed

    meta_only = checks.summarize_consent_mode([meta])
    assert meta_only["present"] is False, (
        "a Meta LDU signal alone must not read as Consent Mode being present, "
        f"which would let it satisfy a Google-specific finding: {meta_only}"
    )
    assert meta_only["all_signals_denied"] is False, meta_only
    ok("Meta LDU is parsed and summarised without contaminating the Google consent-mode verdict")


def test_endpoint_key_is_shared_and_strict() -> None:
    """One definition of endpoint identity, used by both the stability check and
    the run diff. They previously disagreed at the edges, so a URL could count
    as an endpoint in one answer and not the other."""
    assert endpoint_key("https://cdn.example.com/tag.js?cb=123") == "cdn.example.com/tag.js"
    assert endpoint_key("https://example.com") == "example.com"
    assert endpoint_key("https://example.com/") == "example.com/"

    # The query string is excluded on purpose: cache busters and per-request
    # identifiers would make every run look entirely different from every other.
    assert endpoint_key("https://a.test/p?x=1") == endpoint_key("https://a.test/p?x=2")

    # Not network endpoints, and must not appear in either answer.
    for url in ("data:text/html,<p>hi", "about:blank", "blob:https://a.test/abc", ""):
        assert endpoint_key(url) is None, url

    # The capture-side helper must go through it.
    scenario = {"events": {"requests": [
        {"url": "https://a.test/one"},
        {"url": "https://a.test/one?cb=9"},
        {"url": "data:text/html,x"},
        {"url": "https://b.test/two"},
    ]}}
    from lib import capture
    assert capture._endpoint_set(scenario) == {"a.test/one", "b.test/two"}
    ok("endpoint identity has one definition, shared by the stability check and the run diff")


def test_viewport_profiles() -> None:
    """The mobile profile must carry touch and a mobile user agent, not just a
    narrow viewport — a 412px context with a desktop UA is routinely served the
    desktop banner, which would be captured and labelled as mobile evidence."""
    desktop = viewport_profile("desktop")
    assert desktop["viewport"] == {"width": 1440, "height": 1000}, desktop
    assert desktop["is_mobile"] is False and desktop["user_agent"] is None, desktop

    mobile = viewport_profile("mobile")
    assert mobile["viewport"]["width"] < 500, mobile
    assert mobile["is_mobile"] is True and mobile["has_touch"] is True, mobile
    assert "Mobile" in (mobile["user_agent"] or ""), mobile
    assert "Android" in (mobile["user_agent"] or ""), mobile

    # An unknown label must fail loudly. Falling back to desktop would produce a
    # bundle labelled with a profile it was not captured under.
    try:
        viewport_profile("tablet")
    except ValueError as error:
        assert "tablet" in str(error) and "desktop" in str(error), error
    else:
        raise AssertionError("an unknown viewport profile must raise, not fall back to desktop")
    ok("viewport profiles carry touch and a mobile UA, and an unknown label fails loudly")


def test_context_options_device_emulation() -> None:
    """The emulation options must actually be built for mobile and absent for
    desktop, and an explicit --user-agent must beat the profile's UA."""
    def config_for(label: str, **overrides) -> ScenarioConfig:
        profile = viewport_profile(label)
        return ScenarioConfig(
            url="https://example.test",
            viewport=dict(profile["viewport"]),
            viewport_label=label,
            is_mobile=profile["is_mobile"],
            has_touch=profile["has_touch"],
            device_scale_factor=profile["device_scale_factor"],
            device_user_agent=profile["user_agent"],
            **overrides,
        )

    desktop = build_context_options(config_for("desktop"))
    assert "is_mobile" not in desktop, desktop
    assert "has_touch" not in desktop, desktop
    assert "user_agent" not in desktop, desktop
    assert desktop["viewport"] == {"width": 1440, "height": 1000}, desktop

    mobile = build_context_options(config_for("mobile"))
    assert mobile["is_mobile"] is True, mobile
    assert mobile["has_touch"] is True, mobile
    assert mobile["device_scale_factor"] > 1, mobile
    assert "Mobile" in mobile["user_agent"], mobile
    assert mobile["viewport"]["width"] < 500, mobile

    # An explicit override is a deliberate act and must win over the profile UA.
    overridden = build_context_options(config_for("mobile", user_agent="my-custom-agent/1.0"))
    assert overridden["user_agent"] == "my-custom-agent/1.0", overridden
    assert overridden["is_mobile"] is True, "an override of the UA must not disable emulation"

    # GPC and storage_state must still thread through after the extraction.
    gpc = build_context_options(config_for("desktop"), gpc=True)
    assert gpc["extra_http_headers"] == {"Sec-GPC": "1"}, gpc
    assert "storage_state" not in gpc, gpc
    seeded = build_context_options(config_for("desktop"), storage_state={"cookies": []})
    assert seeded["storage_state"] == {"cookies": []}, seeded
    ok("mobile context options carry touch, scale, and a mobile UA; an explicit override wins")


def test_merge_invalid_scenarios() -> None:
    """Across profiles the invalid maps must union, not overwrite: both bundles
    have a scenario called `denial`, so an unqualified merge would report one
    incomplete scenario where there were two."""
    desktop_only = audit_site.merge_invalid_scenarios(
        {"desktop": {"invalid_scenarios": {"denial": {"invalid_reason": "no control"}}}}
    )
    assert desktop_only == {"denial": {"invalid_reason": "no control"}}, desktop_only

    both = audit_site.merge_invalid_scenarios({
        "desktop": {"invalid_scenarios": {"denial": {"invalid_reason": "desktop reason"}}},
        "mobile": {"invalid_scenarios": {"denial": {"invalid_reason": "mobile reason"}}},
    })
    assert set(both) == {"desktop/denial", "mobile/denial"}, both
    assert both["mobile/denial"]["invalid_reason"] == "mobile reason", both

    # A clean profile alongside a broken one must still report the breakage.
    mixed = audit_site.merge_invalid_scenarios({
        "desktop": {"invalid_scenarios": {}},
        "mobile": {"invalid_scenarios": {"denial": {"invalid_reason": "mobile reason"}}},
    })
    assert set(mixed) == {"mobile/denial"}, mixed
    assert audit_site.exit_code([], mixed) == 4, "a clean desktop run must not mask an incomplete mobile one"
    ok("invalid scenarios union across profiles instead of overwriting by scenario name")


def test_denial_not_committed_finding() -> None:
    """The unsaved-preference status must produce its own finding rather than
    the `manual_required` one, and must describe the resolution accurately in
    both shapes: no save candidate found at all, versus candidates visible but
    below the confidence threshold."""
    def findings_for(action_result):
        results = {"denial": {"action_result": action_result}}
        return generate_findings(results, [], [])

    no_candidates = findings_for({
        "status": UNSAVED_PREFERENCE_STATUS,
        "toggle_result": {"disabled": [{"label": "Analytics"}, {"label": "Advertising"}]},
        "resolution": {"save": {}},
        "save_candidates": [],
    })
    matched = [f for f in no_candidates if f["check_type"] == "denial-not-committed"]
    assert len(matched) == 1, [f["check_type"] for f in no_candidates]
    assert "no candidate save control was found" in matched[0]["observation"], matched[0]
    assert "switched 2 optional-category toggle(s) off" in matched[0]["observation"], matched[0]
    # It must not also emit the "could not operate a denial choice" finding,
    # whose observation asserts that nothing was operated.
    assert not [f for f in no_candidates if f["check_type"] == "denial-control-unresolved"], no_candidates

    below_threshold = findings_for({
        "status": UNSAVED_PREFERENCE_STATUS,
        "toggle_result": {"disabled": [{"label": "Analytics"}]},
        "resolution": {"save": {"best_score": 45, "threshold": 70}},
        "save_candidates": [{"ownText": "Accept All", "score": 45}],
    })
    matched = [f for f in below_threshold if f["check_type"] == "denial-not-committed"]
    assert len(matched) == 1, [f["check_type"] for f in below_threshold]
    assert "best score 45 against a threshold of 70" in matched[0]["observation"], matched[0]
    # The remediation must warn about the accept-as-save trap that caused these
    # CMPs' save lists to be emptied in the first place.
    assert "not the accept control" in matched[0]["recommendation"], matched[0]
    ok("an unsaved preference panel produces its own accurate finding, not the unresolved-control one")


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


def test_unknown_scenario_dependency_fails_closed() -> None:
    """A dependency naming a scenario absent from the validity map must block, not pass through.

    This is the fail-open gap: today, `name in validity` is False for an unknown
    name, so the "not validity[name].get('valid', True)" check is never reached
    and the finding slips out as if its dependency were satisfied. "I couldn't
    find that scenario" is not evidence the interaction succeeded.
    """
    findings = [
        {"id": "F-GHOST", "title": "Depends on a scenario that never ran", "depends_on_scenarios": ["denial@nonexistent"]},
        {"id": "F-VALID", "title": "Depends on a scenario that ran and passed", "depends_on_scenarios": ["denial"]},
        {"id": "F-NODEP", "title": "No dependency, reports its own capture failure", "depends_on_scenarios": []},
    ]
    validity = {"denial": {"valid": True}}

    emitted, suppressed = partition_findings(findings, validity)
    emitted_ids = {f["id"] for f in emitted}

    assert "F-GHOST" not in emitted_ids, (
        "a finding depending on an unknown scenario name must be withheld, not emitted"
    )
    assert emitted, "findings whose dependencies are all present and valid must still be emitted"
    assert {"F-VALID", "F-NODEP"} == emitted_ids, emitted_ids

    ghost = next(s for s in suppressed if s["id"] == "F-GHOST")
    blocker = ghost["blocking_scenarios"][0]
    assert blocker["scenario"] == "denial@nonexistent"
    assert "not present" in blocker["reason"], (
        f"reason must distinguish 'missing' from 'invalid': {blocker['reason']!r}"
    )
    ok("a finding depending on an unknown scenario name is suppressed, not silently emitted")


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


def test_preconsent_tracking_assertion_positive_control() -> None:
    """--assert-no-preconsent-tracking's detector must be shown able to fire.

    A "no tracking found" pass proves nothing unless the same detector can also
    go red on a dirty baseline (see acceptance criteria). The synthetic baseline
    here already POSTs to a Google Analytics collect endpoint with a `cid`
    param, which `checks.classify_request` scores as identifier_transmitted -
    confirmed transmission, not a bare script load.
    """
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-assert-dirty-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        analysis = analyze_and_write(root, "https://example.test/", synthetic_results(True), _metadata(), patterns)

        ids = {f["id"] for f in analysis["findings"]}
        assert "F-PRE-CONSENT-TRACKING" in ids, ids

        hits = preconsent_tracking_assertion_hits(analysis["findings"])
        assert hits, "a baseline that produces the pre-consent-tracking finding must also trip the CI assertion"
        assert all(h.get("evidence_strength") in {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER} for h in hits), hits
        ok("--assert-no-preconsent-tracking detector fires on a dirty baseline (positive control)")


def test_preconsent_tracking_assertion_clean_baseline() -> None:
    """The same detector must clear when the baseline has no tracking requests."""
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-assert-clean-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        results = synthetic_results(True)
        results["baseline"]["events"] = {"requests": [], "responses": [], "request_failures": [], "console": []}
        analysis = analyze_and_write(root, "https://example.test/", results, _metadata(), patterns)

        ids = {f["id"] for f in analysis["findings"]}
        assert "F-PRE-CONSENT-TRACKING" not in ids, ids
        assert preconsent_tracking_assertion_hits(analysis["findings"]) == []
        ok("--assert-no-preconsent-tracking clears on a clean baseline")


def test_preconsent_tracking_assertion_ignores_script_load_only() -> None:
    """Invariant: script_loaded_only evidence alone must never trip the gate.

    A tag load without a beacon is what a correct Google-Consent-Mode-style
    implementation looks like; the report treats it as informational, and a
    CI gate that failed on it would fail correct implementations and get
    disabled within a week.
    """
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-assert-scriptonly-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        results = synthetic_results(True)
        now = utc_now()
        results["baseline"]["events"] = {
            "requests": [{
                "time": now, "phase": "initial_navigation",
                "url": "https://connect.facebook.net/en_US/fbevents.js",
                "method": "GET", "resource_type": "script", "is_navigation_request": False,
            }],
            "responses": [], "request_failures": [], "console": [],
        }
        analysis = analyze_and_write(root, "https://example.test/", results, _metadata(), patterns)

        ids = {f["id"] for f in analysis["findings"]}
        assert "F-PRE-CONSENT-TRACKING" in ids, "a script load in a tracking category still produces the report finding"

        hits = preconsent_tracking_assertion_hits(analysis["findings"])
        assert hits == [], "script_loaded_only evidence alone must not trip the CI assertion"
        ok("--assert-no-preconsent-tracking ignores script_loaded_only evidence alone")


def test_preconsent_tracking_assertion_beyond_truncation_cutoff() -> None:
    """Regression: a confirmed row past the report's evidence[:20] display cutoff
    must still trip --assert-no-preconsent-tracking.

    `generate_findings` truncates the pre-consent-tracking finding's `evidence`
    list to the first 20 rows for display (analysis.py). 21+ distinct tracking
    endpoint patterns with loaders ahead of beacons is the normal shape of a
    commercial site, so a confirmed beacon/identifier-transmission row easily
    lands past that cutoff. If the CI gate read the truncated `evidence` list
    instead of the full row set, this case would silently pass with exit 0.

    Builds a baseline with 20 distinct script-only tracking loads (distinct
    fbevents-N.js paths) followed by one confirmed-transmission POST, and
    asserts the gate still fires.
    """
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-assert-truncation-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        results = synthetic_results(True)
        now = utc_now()
        script_only_requests = [
            {
                "time": now, "phase": "initial_navigation",
                "url": f"https://connect.facebook.net/en_US/fbevents-{i}.js",
                "method": "GET", "resource_type": "script", "is_navigation_request": False,
            }
            for i in range(20)
        ]
        confirmed_request = {
            "time": now, "phase": "initial_navigation",
            "url": "https://www.google-analytics.com/g/collect?v=2&cid=secret",
            "method": "POST", "resource_type": "fetch", "is_navigation_request": False,
        }
        results["baseline"]["events"] = {
            "requests": script_only_requests + [confirmed_request],
            "responses": [], "request_failures": [], "console": [],
        }
        analysis = analyze_and_write(root, "https://example.test/", results, _metadata(), patterns)

        finding = next(f for f in analysis["findings"] if f["id"] == "F-PRE-CONSENT-TRACKING")
        assert len(finding["evidence"]) == 20, "sanity check: the display evidence list is still truncated to 20"
        assert not any(
            row.get("evidence_strength") in {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER}
            for row in finding["evidence"]
        ), "the confirmed-transmission row must land past the display truncation for this to be a real regression test"

        hits = preconsent_tracking_assertion_hits(analysis["findings"])
        assert hits, "a confirmed-transmission row beyond the 20-row display cutoff must still trip the CI assertion"
        assert any(
            h.get("host") == "www.google-analytics.com" and h.get("path") == "/g/collect" for h in hits
        ), hits
        ok("--assert-no-preconsent-tracking catches a confirmed row past the evidence display cutoff")


def test_assertion_hits_for_is_opt_in_and_defaults_off() -> None:
    """Acceptance criterion: without the flag, a dirty baseline still exits 0.

    Exercises the actual flag-to-hits wiring (audit_site.assertion_hits_for),
    not just the pure exit_code() function, using the SAME dirty synthetic
    baseline as test_preconsent_tracking_assertion_positive_control. Proves
    both polarities: disabled always yields [] (and exit 0) no matter how
    dirty the findings are, while enabled surfaces the hits (and exit 5).
    Also confirms parse_args() defaults the flag to False, so a bare
    invocation never opts in by accident.
    """
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-assert-optin-") as temp:
        root = Path(temp)
        patterns = SCRIPT_DIR.parent / "references" / "vendor-patterns.json"
        analysis = analyze_and_write(root, "https://example.test/", synthetic_results(True), _metadata(), patterns)
        findings = analysis["findings"]

        disabled_hits = audit_site.assertion_hits_for(False, findings)
        assert disabled_hits == [], "the flag must be opt-in: disabled must yield no hits even on a dirty baseline"
        assert audit_site.exit_code(disabled_hits, {}) == 0, "without the flag, a dirty baseline must still exit 0"

        enabled_hits = audit_site.assertion_hits_for(True, findings)
        assert enabled_hits, "enabled must surface hits on the same dirty baseline"
        assert audit_site.exit_code(enabled_hits, {}) == 5, "enabled must exit 5 on the same dirty baseline"

        old_argv = sys.argv
        try:
            sys.argv = ["audit_site.py", "--url", "https://example.test/"]
            args = audit_site.parse_args()
        finally:
            sys.argv = old_argv
        assert args.assert_no_preconsent_tracking is False, "the flag must default to False (opt-in)"

        ok("assertion_hits_for is opt-in and defaults to off, matching default exit behaviour")


def test_exit_code_precedence_and_values() -> None:
    """Pure exit-code decision (audit_site.exit_code), wired into main().

    Covers the acceptance values (assertion-hit-only -> 5; invalid-only -> 4;
    neither -> 0) and the precedence rule: an invalid/incomplete run must
    never report the definitive "confirmed pre-consent tracking" verdict (5),
    even when the assertion also finds a hit, because findings depending on
    the incomplete scenario may have been withheld and the audit itself is
    bannered INCOMPLETE.
    """
    hit = {
        "host": "www.google-analytics.com", "path": "/g/collect",
        "vendor": "Google Analytics", "evidence_strength": checks.STRENGTH_IDENTIFIER,
    }
    invalid = {"denial": {"invalid_reason": "The required denial click did not complete."}}

    assert audit_site.exit_code([], {}) == 0, "no assertion hits and a complete run must exit 0"
    assert audit_site.exit_code([hit], {}) == 5, "an assertion hit on a complete run must exit 5"
    assert audit_site.exit_code([], invalid) == 4, "an incomplete run with no assertion hits must exit 4"
    assert audit_site.exit_code([hit], invalid) == 4, "incompleteness must win over an assertion hit"
    ok("exit_code returns 5 / 4 / 0 correctly, and incompleteness takes precedence over an assertion hit")


def test_format_assertion_hit_lines_names_offending_endpoints() -> None:
    """Acceptance criterion: the offending endpoints must be named on stderr."""
    hits = [
        {
            "host": "www.google-analytics.com", "path": "/g/collect",
            "vendor": "Google Analytics", "evidence_strength": checks.STRENGTH_IDENTIFIER,
        },
        {
            "host": "connect.facebook.net", "path": "/en_US/fbevents.js",
            "vendor": "Meta", "evidence_strength": checks.STRENGTH_BEACON,
        },
    ]
    lines = audit_site.format_assertion_hit_lines(hits)
    assert len(lines) == 2
    assert "www.google-analytics.com/g/collect" in lines[0]
    assert "vendor=Google Analytics" in lines[0]
    assert f"evidence={checks.STRENGTH_IDENTIFIER}" in lines[0]
    assert "connect.facebook.net/en_US/fbevents.js" in lines[1]
    assert "vendor=Meta" in lines[1]
    ok("format_assertion_hit_lines names host+path, vendor, and evidence strength for each offending endpoint")


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


# ---------------------------------------------------------------------------
# Retry classification - transient transport failures vs. consent findings (#12)
# ---------------------------------------------------------------------------

def test_scenario_failure_classification() -> None:
    timeout = checks.classify_scenario_failure(fatal_error="Timeout 30000ms exceeded.", fatal_error_type="TimeoutError")
    assert timeout == checks.FAILURE_TIMEOUT and checks.should_retry_scenario(timeout)

    navigation = checks.classify_scenario_failure(
        fatal_error="Page.goto: net::ERR_NAME_NOT_RESOLVED at https://example.test/", fatal_error_type="Error",
    )
    assert navigation == checks.FAILURE_NAVIGATION and checks.should_retry_scenario(navigation)

    incomplete = checks.classify_scenario_failure(interaction_required=True, interaction_completed=False)
    assert incomplete == checks.FAILURE_CONSENT_INTERACTION and not checks.should_retry_scenario(incomplete)

    unverified = checks.classify_scenario_failure(
        interaction_required=True, interaction_completed=True, interaction_verified=False,
    )
    assert unverified == checks.FAILURE_CONSENT_INTERACTION and not checks.should_retry_scenario(unverified)

    unknown = checks.classify_scenario_failure(fatal_error="Something exploded", fatal_error_type="RuntimeError")
    assert unknown == checks.FAILURE_UNKNOWN and not checks.should_retry_scenario(unknown), (
        "an unrecognized fatal error must fail closed and never retry"
    )

    success = checks.classify_scenario_failure()
    assert success == checks.FAILURE_NONE and not checks.should_retry_scenario(success)
    ok("scenario failures classify into timeout/navigation/consent/unknown, unknown failing closed")


def test_retry_recovers_from_transient_navigation_failure() -> None:
    """A navigation flake on attempt 1 that succeeds on attempt 2 ends valid."""
    from lib import capture

    calls: list[int] = []

    def fake_run_scenario(browser, scenario, config, private_dir, share_dir, action, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {
                "scenario": scenario,
                "errors": [{"stage": "scenario", "error": "net::ERR_CONNECTION_RESET at https://example.test/", "type": "Error"}],
                "validity": {"valid": False, "invalid_reason": "aborted", "required_interaction": None},
            }
        return {
            "scenario": scenario,
            "errors": [],
            "validity": {"valid": True, "invalid_reason": None, "required_interaction": None},
        }

    original = capture.run_scenario
    capture.run_scenario = fake_run_scenario
    try:
        with tempfile.TemporaryDirectory(prefix="cookie-auditor-retry-") as temp:
            tmp_path = Path(temp)
            result = capture.run_scenario_with_retry(
                browser=None, scenario="baseline", config=None,
                private_dir=tmp_path / "private", share_dir=tmp_path / "share", action="none",
            )
    finally:
        capture.run_scenario = original

    assert len(calls) == 2, "a navigation flake must be retried exactly once"
    assert result["validity"]["valid"] is True
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["failure_class"] == "navigation"
    assert "ERR_CONNECTION_RESET" in result["attempts"][0]["error"], "the first attempt's error must be preserved"
    assert result["attempts"][1]["failure_class"] == "none"
    ok("a navigation flake on attempt 1 that succeeds on attempt 2 ends valid with both attempts recorded")


def test_retry_gives_up_after_second_transient_failure() -> None:
    """Two transport failures in a row stay invalid and are never retried a third time."""
    from lib import capture

    calls: list[int] = []

    def fake_run_scenario(browser, scenario, config, private_dir, share_dir, action, **kwargs):
        calls.append(1)
        return {
            "scenario": scenario,
            "errors": [{"stage": "scenario", "error": "Timeout 30000ms exceeded.", "type": "TimeoutError"}],
            "validity": {"valid": False, "invalid_reason": "aborted", "required_interaction": None},
        }

    original = capture.run_scenario
    capture.run_scenario = fake_run_scenario
    try:
        with tempfile.TemporaryDirectory(prefix="cookie-auditor-retry-") as temp:
            tmp_path = Path(temp)
            result = capture.run_scenario_with_retry(
                browser=None, scenario="baseline", config=None,
                private_dir=tmp_path / "private", share_dir=tmp_path / "share", action="none",
            )
    finally:
        capture.run_scenario = original

    assert len(calls) == 2, "a scenario is retried at most once, never chased a third time"
    assert result["validity"]["valid"] is False
    assert len(result["attempts"]) == 2
    assert all(a["failure_class"] == "timeout" for a in result["attempts"])
    ok("a scenario that fails twice on a transport error stays invalid, with both attempts recorded")


def test_retry_never_fires_for_a_failed_consent_interaction() -> None:
    """A denial click that never resolved is a finding, not a flake - exactly one attempt."""
    from lib import capture

    calls: list[int] = []

    def fake_run_scenario(browser, scenario, config, private_dir, share_dir, action, **kwargs):
        calls.append(1)
        return {
            "scenario": scenario,
            "action_result": {"status": "manual_required"},
            "errors": [],
            "validity": {
                "valid": False,
                "invalid_reason": "The required denial click did not complete (status: manual_required).",
                "required_interaction": "denial click",
                "interaction_completed": False,
                "verification_passed": False,
            },
        }

    original = capture.run_scenario
    capture.run_scenario = fake_run_scenario
    try:
        with tempfile.TemporaryDirectory(prefix="cookie-auditor-retry-") as temp:
            tmp_path = Path(temp)
            result = capture.run_scenario_with_retry(
                browser=None, scenario="denial", config=None,
                private_dir=tmp_path / "private", share_dir=tmp_path / "share", action="deny",
            )
    finally:
        capture.run_scenario = original

    assert len(calls) == 1, "a failed consent interaction is a finding, not a flake, and must not be retried"
    assert result["validity"]["valid"] is False
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["failure_class"] == "consent_interaction_failure"
    ok("a scenario whose consent interaction failed to verify is never retried")


def main() -> int:
    print("\nOffline checks")
    test_har_sanitization()
    test_verify_choice_registered_unit()
    test_cmp_observational_noise_ignored()
    test_transmission_classification()
    test_consent_mode_parsing()
    test_embedded_identifier_scan()
    test_rights_mechanism_scan()
    test_symmetry_measurement()
    test_issue_matrix_generation()
    test_issue_matrix_renders_in_report()
    test_cmp_table_integrity()
    test_repeat_stability()
    test_time_budget_skips_only_corroborating_work()
    test_policy_link_selection()
    test_meta_ldu_signal_parsing()
    test_endpoint_key_is_shared_and_strict()
    test_viewport_profiles()
    test_context_options_device_emulation()
    test_merge_invalid_scenarios()
    test_denial_not_committed_finding()
    test_validity_gating()
    test_unknown_scenario_dependency_fails_closed()
    test_scenario_validity_map()
    test_cookie_inventory_handles_non_scenario_entries()
    test_markdown_to_html()
    test_run_fingerprint()
    test_scenario_failure_classification()
    test_retry_recovers_from_transient_navigation_failure()
    test_retry_gives_up_after_second_transient_failure()
    test_retry_never_fires_for_a_failed_consent_interaction()

    print("\nBrowser-backed checks")
    executable = discover_browser_executable(None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True,
                                             chromium_sandbox=False, args=["--no-sandbox"])
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            test_serve_fixture_seam(page)
            test_control_detection(page)
            test_denial_flow_and_verification(page)
            test_local_storage_same_length_rewrite_detected(page)
            test_settings_path_denial(page)
            test_settings_path_denial_without_save_control(page)
            test_settings_path_no_toggles_still_reports_manual_required(page)
            test_tab_order_direction(page)
            test_tab_order_unreachable_control(page)
            test_tab_order_reaches_iframe_hosted_controls(page)
            test_symmetry_early_exit_survives_new_fields(page)
            test_focus_visibility_detection(page)
            test_measure_tab_order_distinguishes_cap_from_unreachable(page)
            test_execute_denial_measures_focus_visibility_per_control(page)
            test_measure_tab_order_bounded(page)
            test_annotate_controls_marks_resolved_controls(page)
            test_annotation_labels_are_painted_above_every_outline(page)
            test_mobile_emulation_reaches_the_page(page)
            test_form_exercise_does_not_submit(page)
        finally:
            browser.close()

    print("\nReporting and packaging")
    test_analysis_outputs()
    test_incomplete_run_suppresses_and_flags()
    test_preconsent_tracking_assertion_positive_control()
    test_preconsent_tracking_assertion_clean_baseline()
    test_preconsent_tracking_assertion_ignores_script_load_only()
    test_preconsent_tracking_assertion_beyond_truncation_cutoff()
    test_assertion_hits_for_is_opt_in_and_defaults_off()
    test_exit_code_precedence_and_values()
    test_format_assertion_hit_lines_names_offending_endpoints()
    test_zip_bundle()
    test_compare_runs()

    print(f"\nAll {len(PASSED)} cookie-banner-auditor smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
