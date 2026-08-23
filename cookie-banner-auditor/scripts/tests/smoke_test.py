#!/usr/bin/env python3
"""Regression tests for the cookie-banner auditor.

Most checks here are pure-function tests against in-process data. The
"Browser-backed checks" and "Reporting and packaging" sections launch a real
(headless) Chromium against in-memory fixtures served from local routes, so
this suite is not purely offline — but it never contacts an external site or
the network. A live site is still needed to validate real CMP behaviour and
network conditions; the checks below cover the logic that has silently
produced wrong answers before.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from contextlib import contextmanager
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
    build_request_inventory,
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
    _robots_allows,
    _scenario_validity,
    annotate_controls,
    annotation_layer_present,
    assert_clean_context,
    banner_visible,
    build_context_options,
    capture_checkpoint,
    consent_snapshot,
    dwell_and_nudge,
    execute_denial,
    exercise_forms,
    exercise_search,
    find_control,
    fingerprint_cmp,
    inspect_banner,
    load_cmp_table,
    measure_focus_visibility,
    SYNTHETIC_VALUES,
    measure_tab_order,
    probe_autosave,
    read_optional_toggle_states,
    run_scenario,
    safe_internal_links,
    verify_choice_registered,
    viewport_profile,
)
from lib.util import (
    build_zip_bundle,
    create_hash_manifest,
    redact_storage_state,
    redacted_value,
    registrable_domain,
    same_site,
    sha256_file,
    write_json,
    discover_browser_executable,
    markdown_to_html,
    read_json,
    run_fingerprint,
    sanitize_har_data,
    short_hash,
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


def test_robots_allows_respects_disallow() -> None:
    """_robots_allows is the gate keeping E6 policy-capture from fetching a path
    a site's robots.txt asks automated clients to stay out of. Its fetch, cache,
    disallow, and fail-open branches were never exercised."""
    from lib import capture

    robots_bodies = {
        "https://blocked.test/robots.txt": "User-agent: *\nDisallow: /policies/private\n",
    }
    calls: list[str] = []

    class _FakeResponse:
        def __init__(self, body: str) -> None:
            self._body = body.encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

    def fake_urlopen(url, timeout=8.0):
        calls.append(url)
        if url not in robots_bodies:
            raise OSError("no robots.txt at this origin")
        return _FakeResponse(robots_bodies[url])

    original = capture.urlopen
    capture.urlopen = fake_urlopen
    try:
        cache: dict = {}
        disallowed, note = _robots_allows("https://blocked.test/policies/private/notice", cache)
        assert disallowed is False, note

        allowed, _ = _robots_allows("https://blocked.test/privacy", cache)
        assert allowed is True, allowed

        # Cached per origin: the second lookup against the same origin must not refetch.
        assert calls.count("https://blocked.test/robots.txt") == 1, calls

        # An origin serving no robots.txt at all fails open.
        open_allowed, open_note = _robots_allows("https://open.test/privacy", cache)
        assert open_allowed is True, open_note
        assert "no robots.txt" in open_note, open_note
    finally:
        capture.urlopen = original
    ok("_robots_allows honours a real Disallow, caches per origin, and fails open with no robots.txt")


def test_collect_consent_mode_extracts_signals_from_request_log() -> None:
    """_collect_consent_mode is the seam between the raw request log a scenario
    captures and the pure parsing/summarising logic in checks.py - the
    requests -> signals extraction and phase/time tagging were never exercised
    on their own, only the parsing functions they call."""
    from lib import capture

    events = {
        "requests": [
            {"url": "https://www.google-analytics.com/g/collect?v=2&gcs=G100&tid=G-X", "phase": "pre_interaction", "time": "t1"},
            {"url": "https://example.test/logo.png", "phase": "pre_interaction", "time": "t1"},
            {"url": "https://www.facebook.com/tr/?id=1&dpo=LDU", "phase": "post_denial", "time": "t2"},
        ],
        "responses": [],
        "request_failures": [],
        "console": [],
    }
    result = capture._collect_consent_mode(events)
    assert len(result["signals"]) == 2, result
    assert result["signals"][0]["phase"] == "pre_interaction" and result["signals"][0]["time"] == "t1", result
    assert result["signals"][1]["vendor"] == "meta", result
    assert result["summary"]["all_signals_denied"] is True, result
    assert result["summary"]["meta_ldu_active"] is True, result
    ok("_collect_consent_mode tags each parsed signal with its capture phase and time")


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


#: Shared by the #7 autosave-denial fixtures below: a settings panel with two
#: optional toggles and *no save button at all*, matching HubSpot/TrustArc/
#: Quantcast Choice's shape (`save` selector list intentionally empty). A
#: persistent `#managePrefs` control stays reachable even once the initial
#: banner is dismissed - the real-world "manage cookies" link/icon most CMPs
#: keep around - so a reload can still reopen the settings layer to read the
#: toggles back. `%PERSIST%` is substituted per-fixture with whatever (if
#: anything) the toggle's `change` handler does.
_AUTOSAVE_FIXTURE_TEMPLATE = """
    <!doctype html><html><body>
    <div id="cookie-consent" role="dialog" style="position:fixed;bottom:0;left:0;right:0;padding:24px;background:white">
      <p>Choose cookie preferences for analytics and advertising.</p>
      <button id="accept">Accept All</button>
    </div>
    <button id="managePrefs" style="position:fixed;bottom:0;right:0">Cookie Preferences</button>
    <div id="panel" role="dialog" hidden>
      <label><input id="necessary" type="checkbox" checked disabled> Strictly necessary</label>
      <label><input id="analytics" type="checkbox" checked> Analytics</label>
      <label><input id="ads" type="checkbox" checked> Advertising</label>
    </div>
    <script>
      function getCookie(name) {
        const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
        return match ? match[1] : null;
      }
      %ON_LOAD%
      managePrefs.addEventListener('click', () => { panel.hidden = false; });
      function persist() { %PERSIST% }
      analytics.addEventListener('change', persist);
      ads.addEventListener('change', persist);
    </script></body></html>
"""


def test_settings_path_autosave_verified_by_reload(page) -> None:
    """Acceptance criterion #1 (#7): unchecking a toggle writes the CMP's own
    consent cookie, there is no save button anywhere, and a reload confirms
    the choice was kept - toggles read back unchecked and the original banner
    stays gone. That is enough to verify a settings-path denial without ever
    finding a save control."""
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace(
        "%ON_LOAD%",
        # `load_seq` counts loads of this fixture: it reads back "1" for as
        # long as only the initial navigation has happened, and "2" once
        # probe_autosave has reloaded. That makes it a load-time side effect
        # a consent snapshot cannot fake - see the evidence-ordering
        # assertions at the end of this test.
        "document.cookie = 'load_seq=' + (parseInt(getCookie('load_seq') || '0', 10) + 1) "
        "+ '; path=/; max-age=31536000'; "
        "if (getCookie('consent_pref') === 'off') { "
        "document.getElementById('cookie-consent').hidden = true; analytics.checked = false; ads.checked = false; }",
    ).replace(
        "%PERSIST%",
        "document.cookie = 'consent_pref=' + ((analytics.checked || ads.checked) ? 'on' : 'off') + '; path=/; max-age=31536000';",
    )
    holder = {"html": html}
    serve_fixture(page, holder)
    # These fixtures share the "fixture.test" origin across tests within the
    # same browser context; without clearing, a consent cookie left by an
    # earlier autosave test would be read back on the very first load here,
    # before this test ever touches a toggle.
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    result = execute_denial(page, page.context, wait_ms=50, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    live_cookies = {cookie["name"]: cookie["value"] for cookie in page.context.cookies()}
    page.unroute("**/*")

    assert result["status"] == checks.AUTOSAVE_VERIFIED_RELOAD, result
    assert result["status"] in COMPLETED_DENIAL_STATUSES, result["status"]
    assert result["verification"]["verified"] is True, result["verification"]
    assert result["verification"]["basis"] == "reload_confirmed_off", result["verification"]

    validity = _scenario_validity("deny", result, [])
    assert validity["interaction_completed"] is True, validity
    assert validity["valid"] is True, validity
    ok("a reload confirming toggles read back off verifies a settings-path denial with no save control")

    # Evidence-ordering acceptance criterion (#7): consent_snapshot_before and
    # consent_snapshot_after must both be taken *before* the reload inside
    # probe_autosave - otherwise the reload the probe verifies against could
    # have influenced the very snapshots it is being checked against, making
    # the check circular. Assert the ordering at the execute_denial level,
    # not only on probe_autosave in isolation: moving `finish()` (which takes
    # both snapshots) after `probe_autosave()` in execute_denial must fail
    # here.
    #
    # Asserted structurally, via the fixture's `load_seq` cookie, and
    # deliberately NOT by comparing the snapshots' `time` fields. `utc_now()`
    # truncates to whole seconds and the probe's reload+settle finishes well
    # inside one second, so a timestamp comparison holds even when the order
    # is inverted - measured at roughly a 1-in-4 escape rate against this
    # exact mutation, which is no guard at all. `load_seq` instead names
    # *which load* a snapshot saw, and no clock resolution can blur that.
    load_seq_key = "fixture.test|load_seq"
    first_load, second_load = short_hash("1"), short_hash("2")
    assert result["consent_snapshot_before"]["cookies"].get(load_seq_key) == first_load, (
        result["consent_snapshot_before"]["cookies"]
    )
    assert result["consent_snapshot_after"]["cookies"].get(load_seq_key) == first_load, (
        "consent_snapshot_after saw a load later than the initial navigation, so it was taken after "
        f"probe_autosave's reload: {result['consent_snapshot_after']['cookies']}"
    )
    assert first_load != second_load
    # Positive control: the probe's reload really did bump `load_seq`, so the
    # equality above is a live constraint rather than a marker that never
    # moves and would pass under any ordering.
    assert live_cookies.get("load_seq") == "2", live_cookies
    ok("consent_snapshot_before/after are taken before probe_autosave's reload, not after")


def test_settings_path_autosave_reload_reverts_stays_unverified(page) -> None:
    """Acceptance criterion #2 (#7): unchecking the toggles writes nothing at
    all, and a reload re-renders them checked again - the CMP discarded the
    choice. This must stay `toggles_disabled_no_save_control`, unverified and
    invalid, with a note describing what was actually observed.

    This replaces the old fixture's assertion on "never committed", which was
    the exact defect #7 exists to fix: that note was attached unconditionally,
    even though nothing had actually confirmed the preference was discarded
    rather than merely unconfirmed."""
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace("%ON_LOAD%", "").replace("%PERSIST%", "")
    holder = {"html": html}
    serve_fixture(page, holder)
    # These fixtures share the "fixture.test" origin across tests within the
    # same browser context; without clearing, a consent cookie left by an
    # earlier autosave test would be read back on the very first load here,
    # before this test ever touches a toggle.
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    result = execute_denial(page, page.context, wait_ms=50, manual=False, share_scenario_dir=Path(tempfile.mkdtemp()))
    page.unroute("**/*")

    assert result["status"] == UNSAVED_PREFERENCE_STATUS, result
    assert UNSAVED_PREFERENCE_STATUS not in COMPLETED_DENIAL_STATUSES

    disabled = result.get("toggle_result", {}).get("disabled", [])
    assert len(disabled) >= 2, result

    verification = result.get("verification") or {}
    assert verification.get("verified") is False, verification
    note = verification.get("note", "")
    assert "No denial control was operated" not in note, (
        f"the toggles were operated, so this note is false: {note!r}"
    )
    # The entire point of #7: the old note asserted "never committed"
    # regardless of what was actually observed. This one is grounded in what
    # the reload showed - the toggles being operated, and a reload reading at
    # least one of them back on.
    assert "never committed" not in note, note
    assert "toggles were operated" in note, note
    assert "reload read" in note and "back ON" in note, note
    assert "discarded the choice" in note, note

    validity = _scenario_validity("deny", result, [])
    assert validity["interaction_completed"] is False, validity
    assert validity["valid"] is False, validity
    ok("a reload reverting the toggles keeps the denial unverified with a note grounded in what was observed")


def test_settings_path_autosave_verified_by_storage_write(page) -> None:
    """Acceptance criterion #3 (#7): after a reload there is no way back into
    the settings layer at all (a real shape - see Termly, per
    UNSAVED_PREFERENCE_STATUS's docstring), but the CMP's own namespaced
    consent-storage key was written before the reload. That alone is enough
    to verify the denial."""
    # `fixture_reload_marker` is in the declared namespace but is only ever
    # written on a load that already sees a consent cookie - i.e. never on
    # the initial navigation, only on probe_autosave's reload. It is the
    # narrow diff's half of the evidence-ordering guard below.
    cmp_entry = {
        "id": "fixture-storage-cmp",
        "consent_storage": ["fixture_consent_pref", "fixture_reload_marker"],
    }
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace(
        "%ON_LOAD%",
        "if (getCookie('fixture_consent_pref')) { document.getElementById('cookie-consent').remove(); "
        "document.getElementById('managePrefs').remove(); "
        "document.cookie = 'fixture_reload_marker=1; path=/; max-age=31536000'; }",
    ).replace(
        "%PERSIST%",
        "document.cookie = 'fixture_consent_pref=' + ((analytics.checked || ads.checked) ? 'on' : 'off') + '; path=/; max-age=31536000';",
    )
    holder = {"html": html}
    serve_fixture(page, holder)
    # These fixtures share the "fixture.test" origin across tests within the
    # same browser context; without clearing, a consent cookie left by an
    # earlier autosave test would be read back on the very first load here,
    # before this test ever touches a toggle.
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    result = execute_denial(page, page.context, wait_ms=50, manual=False,
                            share_scenario_dir=Path(tempfile.mkdtemp()), cmp_entry=cmp_entry)
    live_cookies = {cookie["name"]: cookie["value"] for cookie in page.context.cookies()}
    page.unroute("**/*")

    assert result["status"] == checks.AUTOSAVE_VERIFIED_STORAGE, result
    assert result["status"] in COMPLETED_DENIAL_STATUSES
    assert result["verification"]["verified"] is True, result["verification"]

    autosave_probe = result.get("autosave_probe") or {}
    assert autosave_probe.get("settings_reopened") is False, (
        "this fixture removes every reopen-settings control on reload; the probe must not fabricate one"
    )
    narrow = result.get("narrow_diff") or {}
    assert narrow.get("namespace_available") is True, narrow
    assert narrow.get("namespaced_state_changed") is True, narrow

    validity = _scenario_validity("deny", result, [])
    assert validity["valid"] is True, validity
    ok("a namespaced consent-storage write verifies a settings-path denial when there is no way back into settings after reload")

    # Evidence-ordering acceptance criterion (#7), narrow-diff half: the diff
    # that certifies this denial must be computed from snapshots taken before
    # probe_autosave's reload, or the reload it is verified against fed the
    # very evidence doing the verifying. `fixture_reload_marker` is written
    # only on a reload, and is inside the declared namespace, so a diff
    # computed after the reload necessarily picks it up. Structural, not
    # timing-based, for the reasons given in
    # test_settings_path_autosave_verified_by_reload.
    new_keys = {entry["key"] for entry in narrow.get("new_keys") or []}
    assert new_keys == {"fixture.test|fixture_consent_pref"}, (
        "the narrow diff saw a namespaced key that only a reload writes, so it was computed after "
        f"probe_autosave's reload rather than before it: {new_keys}"
    )
    # Positive control: the marker really was written by the probe's reload,
    # and really is in the namespace - otherwise the assertion above could
    # never fail under any ordering.
    assert live_cookies.get("fixture_reload_marker") == "1", live_cookies
    assert checks.consent_key_matches(
        "fixture.test|fixture_reload_marker", cmp_entry["consent_storage"], cookie_key=True,
    ), cmp_entry
    ok("the narrow consent diff is computed before probe_autosave's reload, not after")


def test_probe_autosave_reload_ordering_and_phase_tagging(page) -> None:
    """`probe_autosave` in isolation, covering the parts of #7's acceptance
    criteria that execute_denial's own settings-click side effects would
    confound if tested only end-to-end (opening the settings layer already
    hides the banner, which would make a before/after banner comparison
    trivially true regardless of whether the reload itself changed anything):

    - screenshot, probe_started/probe_finished, and phase restoration;
    - the reload demonstrably changing page state (banner visibility) rather
      than being a no-op the probe or narrow diff could be trivially
      "verified" against;
    - the probe's own reload traffic is stamped with phase
      `denial_verification_reload`, and that phase - and only that phase -
      is what keeps it out of the post-denial-tracking finding.
    """
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace(
        "%ON_LOAD%",
        "fetch('https://connect.facebook.net/en_US/fbevents.js', {mode: 'no-cors'}).catch(() => {}); "
        "if (getCookie('consent_pref') === 'off') { "
        "document.getElementById('cookie-consent').hidden = true; analytics.checked = false; ads.checked = false; }",
    ).replace(
        "%PERSIST%",
        "document.cookie = 'consent_pref=' + ((analytics.checked || ads.checked) ? 'on' : 'off') + '; path=/; max-age=31536000';",
    )
    holder = {"html": html}
    serve_fixture(page, holder)
    # These fixtures share the "fixture.test" origin across tests within the
    # same browser context; without clearing, a consent cookie left by an
    # earlier autosave test would be read back on the very first load here,
    # before this test ever touches a toggle.
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    # Simulate what execute_denial does before ever calling probe_autosave:
    # open the settings layer and switch the optional toggles off.
    page.click("#managePrefs")
    page.click("#analytics")
    page.click("#ads")

    banner_visible_before_probe = banner_visible(page, None)

    phase_ref = {"name": "denial_interaction"}
    captured: list[dict] = []

    def on_request(request) -> None:
        captured.append({
            "time": utc_now(), "phase": phase_ref["name"], "url": request.url,
            "method": request.method, "resource_type": request.resource_type,
            "is_navigation_request": request.is_navigation_request,
        })

    page.on("request", on_request)
    action_log: list[dict] = []
    scenario_dir = Path(tempfile.mkdtemp())
    try:
        probe = probe_autosave(page, page.context, None, 50, action_log, scenario_dir, phase_ref)
    finally:
        page.remove_listener("request", on_request)
        page.unroute("**/*")

    assert probe["probe_started"] and probe["probe_finished"], probe
    # time-assertion-ok: not an ordering guarantee standing in for structure -
    # both readings come from the same probe dict and this only checks they
    # were populated in the order the function writes them. Equality is a
    # legitimate outcome here, so whole-second truncation cannot mask a defect.
    assert probe["probe_started"] <= probe["probe_finished"], probe
    assert probe["screenshot"] and Path(probe["screenshot"]).exists(), probe
    assert (scenario_dir / "preferences-after-toggles.png").exists()
    assert phase_ref["name"] == "denial_interaction", "phase must be restored to the caller's phase after the probe"
    ok("probe_autosave screenshots, timestamps probe_started/probe_finished in order, and restores the caller's phase")

    # Evidence ordering: the reload actually changed page state, so a probe
    # or narrow diff "verifying" against it is not vacuous.
    assert banner_visible_before_probe != probe["banner_visible_after_reload"], (
        banner_visible_before_probe, probe["banner_visible_after_reload"],
    )
    ok("banner_visible_after_reload differs from the pre-reload reading, proving the reload actually ran")

    assert probe["settings_reopened"] is True, probe
    states = {t["label"]: t["state"] for t in probe["toggle_states"]}
    assert states and all(state is False for state in states.values()), states
    ok("the probe reopens settings after reload and reads the optional toggles back off")

    tracking = [r for r in captured if "connect.facebook.net" in r["url"]]
    assert tracking, "the fixture must fire its tracking request during the probe's reload"
    assert all(r["phase"] == "denial_verification_reload" for r in tracking), tracking
    ok("the probe's own reload traffic is stamped with phase denial_verification_reload")

    patterns = read_json(SCRIPT_DIR.parent / "references" / "vendor-patterns.json")
    excluded_rows = build_request_inventory({"denial": {"events": {"requests": tracking}}}, "fixture.test", patterns)
    excluded_findings = generate_findings(
        {"denial": {"action_result": {"status": UNSAVED_PREFERENCE_STATUS}, "checkpoints": []}}, [], excluded_rows,
    )
    assert "post-denial-tracking" not in {f["check_type"] for f in excluded_findings}, excluded_findings
    ok("a tracking request phased denial_verification_reload produces no post-denial-tracking finding")

    # Positive control: the identical request, tagged as ordinary denial
    # interaction traffic instead, must produce the finding - otherwise the
    # check above would only show the test request was inert.
    positive = [{**r, "phase": "denial_interaction"} for r in tracking]
    positive_rows = build_request_inventory({"denial": {"events": {"requests": positive}}}, "fixture.test", patterns)
    positive_findings = generate_findings(
        {"denial": {"action_result": {"status": UNSAVED_PREFERENCE_STATUS}, "checkpoints": []}}, [], positive_rows,
    )
    assert "post-denial-tracking" in {f["check_type"] for f in positive_findings}, positive_findings
    ok("the identical request phased denial_interaction does produce a post-denial-tracking finding (positive control)")


def test_execute_denial_wires_phase_ref_into_autosave_probe(page) -> None:
    """The prior test drives probe_autosave in isolation, handing it a
    phase_ref directly - it cannot catch execute_denial failing to forward
    its own phase_ref through to probe_autosave (capture.py's autosave-fork
    call site, and the run_scenario pass-through above it). If that wiring
    is dropped, the probe's reload traffic goes untagged as
    denial_verification_reload and is misattributed to ordinary denial
    interaction traffic - manufacturing exactly the false post-denial-
    tracking finding this tool exists to prevent. Drive the autosave path
    through execute_denial itself with a real phase_ref, the way
    run_scenario does, and assert the tagging survives that hop."""
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace(
        "%ON_LOAD%",
        "fetch('https://connect.facebook.net/en_US/fbevents.js', {mode: 'no-cors'}).catch(() => {});",
    ).replace("%PERSIST%", "")
    holder = {"html": html}
    serve_fixture(page, holder)
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    phase_ref = {"name": "denial_interaction"}
    captured: list[dict] = []

    def on_request(request) -> None:
        captured.append({"time": utc_now(), "phase": phase_ref["name"], "url": request.url})

    page.on("request", on_request)
    try:
        result = execute_denial(
            page, page.context, wait_ms=50, manual=False,
            share_scenario_dir=Path(tempfile.mkdtemp()), phase_ref=phase_ref,
        )
    finally:
        page.remove_listener("request", on_request)
        page.unroute("**/*")

    assert result["status"] == UNSAVED_PREFERENCE_STATUS, result
    assert phase_ref["name"] == "denial_interaction", "phase must be restored to the caller's phase after execute_denial"

    tracking = [r for r in captured if "connect.facebook.net" in r["url"]]
    assert tracking, "the fixture must fire its tracking request during the probe's reload"
    assert all(r["phase"] == "denial_verification_reload" for r in tracking), (
        "execute_denial must forward its phase_ref into probe_autosave so the reload's own traffic "
        f"gets stamped denial_verification_reload, not left on the caller's phase: {tracking}"
    )
    ok("execute_denial forwards its phase_ref into probe_autosave, tagging the reload's traffic denial_verification_reload")


def test_manual_precedence_over_autosave_path(page) -> None:
    """--manual must still take precedence when the autosave path IS entered -
    i.e. there are optional toggles to disable and no save control, so #7's
    classify_autosave_denial fork runs. An operator who explicitly asked to
    make the choice by hand must still be prompted, and the recorded result
    must come from that human action (`manual_denial_completed`), not from
    the automated autosave verdict (e.g. AUTOSAVE_VERIFIED_RELOAD/STORAGE or
    the unverified toggles_disabled_no_save_control)."""
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace("%ON_LOAD%", "").replace("%PERSIST%", "")
    holder = {"html": html}
    serve_fixture(page, holder)
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    original_input = builtins.input
    builtins.input = lambda: ""
    try:
        result = execute_denial(page, page.context, wait_ms=20, manual=True, share_scenario_dir=Path(tempfile.mkdtemp()))
    finally:
        builtins.input = original_input
        page.unroute("**/*")

    assert result["status"] == "manual_denial_completed", result
    assert result["manual_used"] is True, result
    ok("--manual still wins over the autosave verdict when the autosave fork is entered")


def test_manual_eof_with_operated_toggles_falls_back_to_autosave_classification(page) -> None:
    """`manual_required`'s meaning ("nothing was operated") must stay exact,
    because analysis.py keys the high-severity denial-control-unresolved
    finding off exactly that status. If --manual is requested but the
    operator's terminal is gone by the time the prompt runs (stdin closed
    mid-run, `input()` raises EOFError) *after* optional toggles were already
    switched off, those toggles are an operated denial control - reporting
    manual_required here would be a false "nothing was operated" claim. The
    run must instead fall back to the same probe-backed autosave
    classification used when --manual was never requested."""
    html = _AUTOSAVE_FIXTURE_TEMPLATE.replace("%ON_LOAD%", "").replace("%PERSIST%", "")
    holder = {"html": html}
    serve_fixture(page, holder)
    page.context.clear_cookies()
    page.goto("https://fixture.test/")

    def _raise_eof() -> str:
        raise EOFError()

    original_input = builtins.input
    builtins.input = _raise_eof
    try:
        result = execute_denial(page, page.context, wait_ms=50, manual=True, share_scenario_dir=Path(tempfile.mkdtemp()))
    finally:
        builtins.input = original_input
        page.unroute("**/*")

    assert result["manual_stdin_unavailable"] is True, result
    disabled = result.get("toggle_result", {}).get("disabled", [])
    assert len(disabled) >= 2, result

    assert result["status"] != "manual_required", result
    note = (result.get("verification") or {}).get("note", "")
    assert "No denial control was operated" not in note, (
        f"the toggles were operated, so this note is false: {note!r}"
    )
    # This fixture never persists the toggle change, so it lands in the same
    # unverified classification as test_settings_path_autosave_reload_reverts_stays_unverified.
    assert result["status"] == UNSAVED_PREFERENCE_STATUS, result
    ok("--manual with operated toggles and an EOF stdin falls back to the autosave classification instead of manual_required")


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


@contextmanager
def _serve_cmp_fixture(page, html: str, url: str = "https://cmp-fixture.test/"):
    """Serve `html` at a real https origin, navigate to it, and clean up on exit.

    `set_content` leaves the page on about:blank, where `document.cookie` is
    silently dropped - so a denial that really did record a choice still looks
    unverified, and the fixture would be testing the wrong thing. These CMP
    tests assert the *verification* result, so they need an origin where
    consent state can actually be written.

    This is a context manager, not a plain setup call, because the shared
    `page`/`context` outlive any single CMP test: a denial click here can set
    a real cookie on `url`'s origin, and the `page.route("**/*")` handler
    registered to serve `html` stays registered on the page until removed. On
    exit (even on failure) this unroutes the handler and clears the context's
    cookies, so neither the route nor the cookie survives to be seen by
    whichever test runs next on this same `page` - including a later CMP
    fixture (route matching is newest-handler-first, which used to paper over
    the leak) and, worse, a later non-CMP test that never expects to see a
    `page.route` handler or cookie at all.
    """
    serve_fixture(page, {"html": html}, url=url)
    page.goto(url)
    page.context.clear_cookies()
    try:
        yield
    finally:
        page.unroute("**/*")
        page.context.clear_cookies()


def _denial_for(page, cmp_entry: dict | None = None) -> dict:
    """Run a denial the way run_scenario does - with the fingerprinted CMP entry.

    Passing the entry is the point of these tests: without it execute_denial
    silently falls back to text scoring, and the CMP selector table it is
    supposed to be exercising is never consulted.
    """
    return execute_denial(page, page.context, wait_ms=20, manual=False,
                          share_scenario_dir=Path(tempfile.mkdtemp()), cmp_entry=cmp_entry)


def test_onetrust_shape_uses_the_second_layer_reject(page) -> None:
    """OneTrust often ships no top-level reject - its own table entry notes that
    absence is a UI observation, not a detection failure. The denial then has to
    open preferences and use the reject control inside, which is the
    `second_layer_reject_clicked` path. Nothing exercised it before this.

    Also the first non-HubSpot CMP fixture, so it is the first test that proves
    a second entry in cmp-selectors.json actually resolves against markup shaped
    like the real thing."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="onetrust-consent-sdk">
          <div id="onetrust-banner-sdk" style="position:fixed;bottom:0;padding:24px;background:#fff">
            <p>We use cookies for analytics and advertising.</p>
            <button id="onetrust-accept-btn-handler">Allow All</button>
            <button id="onetrust-pc-btn-handler">Cookie Settings</button>
          </div>
          <div id="onetrust-pc-sdk" hidden>
            <button class="ot-pc-refuse-all-handler">Reject All</button>
            <button class="save-preference-btn-handler">Confirm My Choices</button>
          </div>
        </div>
        <script>
          document.querySelector('#onetrust-pc-btn-handler').addEventListener('click', () => {
            document.querySelector('#onetrust-banner-sdk').hidden = true;
            document.querySelector('#onetrust-pc-sdk').hidden = false;
          });
          document.querySelector('.ot-pc-refuse-all-handler').addEventListener('click', () => {
            document.querySelector('#onetrust-consent-sdk').remove();
            document.cookie = 'OptanonConsent=groups=C0001:1,C0002:0; path=/';
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "onetrust", match
        assert match["matched_by"].startswith("selector:"), match

        entry = match["entry"]
        # No top-level reject exists, and that must read as absence rather than as
        # the scanner failing to look.
        top_level, _, reject_resolution = find_control(page, "reject", entry)
        assert top_level is None, "this fixture deliberately has no first-layer reject"
        assert reject_resolution["path"] == "none", reject_resolution
        assert reject_resolution.get("cmp_table_miss") is True, reject_resolution

        result = _denial_for(page, entry)
        assert result["status"] == "second_layer_reject_clicked", result
        assert result["click_count"] == 2, f"settings + reject is two interactions: {result['click_count']}"
        assert (result.get("verification") or {}).get("verified") is True, result
        assert result["resolution"]["second_layer_reject"]["path"] == "cmp_selector_table", result["resolution"]
        validity = _scenario_validity("deny", result, [])
        assert validity["valid"] is True, validity
        ok("a OneTrust-shaped banner with no first-layer reject completes via the second layer")


def test_usercentrics_shape_resolves_inside_a_shadow_root(page) -> None:
    """Usercentrics renders its controls inside a shadow root; its table entry is
    flagged shadow_dom. If control collection ever stopped piercing shadow DOM,
    every Usercentrics site would silently become 'no denial control found'."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="usercentrics-root"></div>
        <script>
          const host = document.querySelector('#usercentrics-root');
          const root = host.attachShadow({mode: 'open'});
          root.innerHTML = `
            <div style="position:fixed;bottom:0;padding:24px;background:#fff">
              <p>We use cookies for analytics and advertising.</p>
              <button data-testid="uc-accept-all-button">Accept All</button>
              <button data-testid="uc-deny-all-button">Deny All</button>
            </div>`;
          root.querySelector('[data-testid=uc-deny-all-button]').addEventListener('click', () => {
            host.remove();
            localStorage.setItem('uc_settings', '{"consent":"denied"}');
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "usercentrics", match

        control, _, resolution = find_control(page, "reject", match["entry"])
        assert control is not None, "the deny control lives in a shadow root and must still resolve"
        assert resolution["path"] == "cmp_selector_table", resolution

        result = _denial_for(page, match["entry"])
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a Usercentrics-shaped banner resolves and completes inside an open shadow root")


def test_sourcepoint_shape_resolves_inside_an_iframe(page) -> None:
    """Sourcepoint renders into an iframe; its controls never appear in the main
    frame. Frame traversal is the only thing that reaches them."""
    inner = """
        <!doctype html><html><body style='margin:0'>
          <div style='padding:20px'>
            <p>We use cookies for analytics and advertising.</p>
            <button class='sp_choice_type_11' title='Accept All'>Accept All</button>
            <button class='sp_choice_type_13' title='Reject All'>Reject All</button>
          </div>
          <script>
            document.querySelector('.sp_choice_type_13').addEventListener('click', () => {
              document.body.innerHTML = '<p>choice recorded</p>';
              try { localStorage.setItem('euconsent-v2', 'denied'); } catch (e) {}
            });
          </script>
        </body></html>
    """
    with _serve_cmp_fixture(page, f"""
        <!doctype html><html><body>
        <iframe id="sp_message_iframe_12345" srcdoc="{inner.replace('"', "&quot;")}"
                style="position:fixed;bottom:0;width:500px;height:220px;border:0"></iframe>
        </body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "sourcepoint", match

        control, _, resolution = find_control(page, "reject", match["entry"])
        assert control is not None, "the reject control is inside the iframe and must still resolve"
        assert resolution["path"] == "cmp_selector_table", resolution
        # It must have been found in a child frame, not the top document.
        assert control["frame"] != page.main_frame, "the control must be located in the CMP's iframe"

        result = _denial_for(page, match["entry"])
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a Sourcepoint-shaped banner resolves and completes inside its iframe")


def test_didomi_shape_resolves_and_save_stays_specific_to_settings(page) -> None:
    """The didomi table entry was written from documentation, not a live capture.
    A first pass (2026-08-22) verified it against https://www.didomi.io itself
    and found the table already correct. A second, wider pass across
    didomi.io plus two customer deployments (Planity, Chantelle) then found a
    real bug in the entry that pass had missed: the accept fallback
    `button.didomi-components-button--color[aria-label*='Agree' i]` also
    matched the DISAGREE button, because the string "agree" is a substring of
    "disagree". This was a live defect, not a hypothetical one - confirmed
    against real ariaLabel text, not just noticed by inspection. The fallback
    was removed; `#didomi-notice-agree-button` alone is sufficient and
    unambiguous. `save` was also corrected to the real `#btn-toggle-save` id,
    which localizes (the old aria-label-substring approach did not: French
    Planity's save button reads "Enregistrer", not "Save")."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="didomi-host">
          <div id="didomi-popup" class="didomi-popup-backdrop didomi-notice-popup didomi-popup__backdrop">
            <p>We use cookies to improve your experience.</p>
            <button id="didomi-notice-disagree-button"
                    class="didomi-components-button didomi-button didomi-disagree-button didomi-components-button--color didomi-button-highlight highlight-button"
                    aria-label="I disagree: Disagree to our data processing and close">I disagree</button>
            <button id="didomi-notice-agree-button"
                    class="didomi-components-button didomi-button didomi-dismiss-button didomi-components-button--color didomi-button-highlight highlight-button"
                    aria-label="I agree: Agree to our data processing and close">I agree</button>
            <button id="didomi-notice-learn-more-button"
                    class="didomi-components-button didomi-button didomi-learn-more-button didomi-button-standard standard-button"
                    aria-label="Configure: Configure your consents">Configure</button>
          </div>
          <div id="didomi-preferences" hidden>
            <button class="didomi-components-radio__option didomi-components-radio__option--unselected">Disagree</button>
            <button class="didomi-components-radio__option didomi-components-radio__option--unselected">Agree</button>
            <button id="btn-toggle-save"
                    class="didomi-components-button didomi-button didomi-button-standard standard-button"
                    aria-label="Save: Save your choices and close">Save</button>
          </div>
        </div>
        <script>
          document.querySelector('#didomi-notice-learn-more-button').addEventListener('click', () => {
            document.querySelector('#didomi-preferences').hidden = false;
          });
          document.querySelector('#didomi-notice-disagree-button').addEventListener('click', () => {
            document.querySelector('#didomi-host').remove();
            document.cookie = 'didomi_token=denied; path=/';
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "didomi", match

        # Before the settings panel opens, "save" must not resolve at all - the
        # first-layer agree/disagree buttons share its base class, and if the
        # selector were too broad it would match one of them here.
        premature_save, _, premature_resolution = find_control(page, "save", match["entry"])
        assert premature_save is None, premature_resolution

        page.click("#didomi-notice-learn-more-button")

        # Now the real save control must resolve, and must resolve to itself - not
        # to either first-layer button that shares its base class.
        save_control, _, save_resolution = find_control(page, "save", match["entry"])
        assert save_control is not None, save_resolution
        assert save_resolution["path"] == "cmp_selector_table", save_resolution
        assert save_control["id"] == "btn-toggle-save", (
            f"save must resolve to the real save control, not a first-layer button "
            f"sharing its base class: {save_control.get('id')!r}"
        )

        # Structural guard against reintroduction: _locate_by_selectors returns
        # the first visible match in list order, so if the buggy fallback were
        # ever added back *behind* the correct id, find_control would still
        # resolve correctly and the mutation check below (which replaces the
        # list wholesale) would not catch it. Assert directly against the table.
        assert "button.didomi-components-button--color[aria-label*='Agree' i]" not in match["entry"]["accept"], (
            "the historically buggy accept fallback (matches both agree and disagree) must not return to the table"
        )

        # The current table's accept resolves to the real agree button, and only
        # that. Checked before the denial click below, which removes the host
        # element entirely.
        accept_control, _, accept_resolution = find_control(page, "accept", match["entry"])
        assert accept_control is not None, accept_resolution
        assert accept_control["id"] == "didomi-notice-agree-button", accept_control

        # Mutation check: the fallback this entry used to carry -
        # `button.didomi-components-button--color[aria-label*='Agree' i]` - is
        # proven here to have been a live bug, not a defensive selector removed
        # out of caution. "disagree" contains "agree" as a substring, so the old
        # selector matched BOTH buttons; which one `.first` returned was an
        # accident of DOM order, not a guarantee of the right one.
        buggy_entry = dict(match["entry"])
        buggy_entry["accept"] = ["button.didomi-components-button--color[aria-label*='Agree' i]"]
        buggy_control, _, _ = find_control(page, "accept", buggy_entry)
        assert buggy_control is not None, "the old selector should still match something"
        assert buggy_control["id"] == "didomi-notice-disagree-button", (
            "this pins the actual historical bug: the removed accept fallback resolved "
            f"to the DISAGREE button first, not agree - got {buggy_control.get('id')!r}. "
            "If this ever stops reproducing, the fixture's DOM order changed, not the bug."
        )
        ok("the removed Didomi accept fallback is confirmed to have matched 'I disagree', not just suspected to")

        result = _denial_for(page, match["entry"])
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a Didomi-shaped banner (verified against didomi.io) resolves reject directly and save stays scoped to the settings panel")


def test_axeptio_shape_accept_fallback_no_longer_collides_with_dismiss(page) -> None:
    """The axeptio table entry's accept fallback was written from documentation,
    not a live capture, and carried the same class of bug just fixed on Didomi:
    an aria-label substring collision. Verified 2026-08-22 against
    https://axept.io (Axeptio's own site). Real DOM: `#axeptio_overlay` is a
    light-DOM mount point whose only child is an open shadow-root host; the
    actual controls live inside that shadow root with real aria-label text -
    `#axeptio_btn_dismiss` aria-label 'Close without accepting cookies',
    `#axeptio_btn_configure` aria-label 'I choose the cookies to configure',
    `#axeptio_btn_acceptAll` aria-label 'Accept all cookies'. This fixture
    reproduces that exact shape and those exact aria-label strings.

    The collision is confirmed live, not just suspected: 'accepting' contains
    'Accept' as a substring, so `button[aria-label*='Accept' i]` matched
    #axeptio_btn_dismiss - the reject-side control - ahead of the real accept
    button in DOM order, the same mechanical failure as Didomi's
    'agree'/'disagree'. The fallback was removed; `#axeptio_btn_acceptAll`
    alone is Axeptio's stable element id and is sufficient on its own."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="axeptio_overlay" class="axeptio_mount" data-project-id="000000000000000000000000">
          <div id="axeptio-shadow-host"></div>
        </div>
        <script>
          const host = document.querySelector('#axeptio-shadow-host');
          const root = host.attachShadow({mode: 'open'});
          root.innerHTML = `
            <div style="position:fixed;bottom:0;padding:20px;background:#fff">
              <p>We use cookies to improve your experience and for analytics.</p>
              <button id="axeptio_btn_dismiss" aria-label="Close without accepting cookies">No, thanks</button>
              <button id="axeptio_btn_configure" aria-label="I choose the cookies to configure">I want to choose</button>
              <button id="axeptio_btn_acceptAll" aria-label="Accept all cookies">Ok for me</button>
            </div>`;
          root.querySelector('#axeptio_btn_dismiss').addEventListener('click', () => {
            document.querySelector('#axeptio_overlay').remove();
            document.cookie = 'axeptio_cookies={}; path=/';
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "axeptio", match
        entry = match["entry"]

        # Structural guard against reintroduction: _locate_by_selectors returns
        # the first visible match in list order, so if the buggy fallback were
        # ever added back *behind* the correct id, find_control would still
        # resolve correctly and the mutation check below (which replaces the
        # list wholesale) would not catch it. Assert directly against the table.
        assert "button[aria-label*='Accept' i]" not in entry["accept"], (
            "the historically buggy accept fallback (matches the dismiss button too) must not return to the table"
        )

        # The current table's accept resolves to the real accept-all button, and
        # only that. Checked before the denial click below, which removes the
        # overlay entirely.
        accept_control, _, accept_resolution = find_control(page, "accept", entry)
        assert accept_control is not None, accept_resolution
        assert accept_control["id"] == "axeptio_btn_acceptAll", accept_control

        # Mutation check: the fallback this entry used to carry -
        # `button[aria-label*='Accept' i]` - is proven here to have been a live
        # bug against real Axeptio markup, not a defensive selector removed out
        # of caution. "Close without accepting cookies" contains "accepting",
        # which contains "Accept" as a case-insensitive substring, so the old
        # selector matched the DISMISS button first (DOM order), not acceptAll.
        buggy_entry = dict(entry)
        buggy_entry["accept"] = ["button[aria-label*='Accept' i]"]
        buggy_control, _, _ = find_control(page, "accept", buggy_entry)
        assert buggy_control is not None, "the old selector should still match something"
        assert buggy_control["id"] == "axeptio_btn_dismiss", (
            "this pins the actual historical bug: the removed accept fallback resolved "
            f"to the DISMISS button first, not acceptAll - got {buggy_control.get('id')!r}. "
            "If this ever stops reproducing, the fixture's DOM order changed, not the bug."
        )
        ok("the removed Axeptio accept fallback is confirmed to have matched the dismiss button, not just suspected to")

        result = _denial_for(page, entry)
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("an Axeptio-shaped banner (verified against axept.io) resolves accept and reject to distinct controls")


def test_cookiebot_shape_settings_never_resolves_to_the_category_checkbox(page) -> None:
    """First fixture for cookiebot (19 table entries existed with no fixture at
    all). Verified 2026-08-22 against three live deployments: cookiebot.com,
    University of the People (overlay - Deny stays hidden until Customize is
    opened, mirrored below), and Langley School (bottom multilevel layout).

    The Langley capture surfaced a real bug: the table's `settings` list
    included `#CybotCookiebotDialogBodyLevelButtonPreferences`, which live
    markup shows is `<input type="checkbox" role="switch">` - a per-category
    consent toggle, not a settings launcher. Clicking it during execute_denial's
    settings step would have silently flipped a consent category rather than
    opening the preference panel. Removed from the table; this fixture
    reproduces the real markup (checkbox present, same naming pattern) and
    proves settings resolves past it to the real button."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="CybotCookiebotDialog" role="dialog" data-template="overlay">
          <p>We use cookies to analyze traffic and personalize content.</p>
          <button id="CybotCookiebotDialogBodyLevelButtonCustomize">
            Customize
          </button>
          <button id="CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll">Allow all</button>
          <button id="CybotCookiebotDialogBodyButtonDecline" class="CybotCookiebotDialogHide" style="display:none">
            Deny
          </button>
          <input type="checkbox" id="CybotCookiebotDialogBodyLevelButtonPreferences" role="switch"
                 aria-label="Statistics" checked>
          <button id="CybotCookiebotDialogBodyLevelButtonLevelOptinAllowallSelection" class="CybotCookiebotDialogHide" style="display:none">
            Allow selection
          </button>
        </div>
        <script>
          document.querySelector('#CybotCookiebotDialogBodyLevelButtonCustomize').addEventListener('click', () => {
            const decline = document.querySelector('#CybotCookiebotDialogBodyButtonDecline');
            decline.style.display = '';
            decline.classList.remove('CybotCookiebotDialogHide');
          });
          document.querySelector('#CybotCookiebotDialogBodyButtonDecline').addEventListener('click', () => {
            document.querySelector('#CybotCookiebotDialog').remove();
            document.cookie = 'CookieConsent=%7Bnecessary%3Atrue%2Cpreferences%3Afalse%7D; path=/';
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "cookiebot", match
        entry = match["entry"]

        settings_control, _, settings_resolution = find_control(page, "settings", entry)
        assert settings_control is not None, settings_resolution
        assert settings_control["id"] == "CybotCookiebotDialogBodyLevelButtonCustomize", (
            f"settings must resolve to the real launcher, not the category-toggle checkbox: {settings_control}"
        )

        # Structural guard against reintroduction: _locate_by_selectors returns
        # the first visible match in list order, so if this checkbox selector
        # were ever added back *behind* the real launcher, find_control would
        # still resolve correctly and the mutation check below (which replaces
        # the list wholesale) would not catch it. Assert directly against the
        # table entry itself.
        assert "#CybotCookiebotDialogBodyLevelButtonPreferences" not in entry["settings"], (
            "the category-toggle checkbox (a role=switch input, not a settings launcher) must not return to the table"
        )

        # Mutation check, before anything below removes the fixture from the DOM:
        # the removed checkbox selector is proven to have been a real hazard, not
        # a defensive removal - it resolves and reports itself as a switch, which
        # execute_denial's settings step would have clicked as if it were "open
        # preferences".
        buggy_entry = dict(entry)
        buggy_entry["settings"] = ["#CybotCookiebotDialogBodyLevelButtonPreferences"]
        buggy_control, _, _ = find_control(page, "settings", buggy_entry)
        assert buggy_control is not None, "the removed selector should still match something"
        assert buggy_control["tag"] == "input" and buggy_control.get("role") == "switch", (
            f"this confirms the removed selector resolved to the category-toggle checkbox, not a launcher: {buggy_control}"
        )

        # Deny is hidden until Customize is opened (the UoPeople quirk); the
        # top-level reject lookup must reflect that rather than reporting a false
        # "no reject exists" or matching a hidden element.
        top_level, _, top_resolution = find_control(page, "reject", entry)
        assert top_level is None, "this fixture's Deny button starts hidden, like UoPeople's"
        assert top_resolution["cmp_table_miss"] is True, top_resolution

        result = _denial_for(page, entry)
        assert result["status"] == "second_layer_reject_clicked", result
        assert result["resolution"]["second_layer_reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a Cookiebot-shaped banner (verified live, 3 deployments) keeps settings off the category-toggle checkbox")


def test_termly_shape_settings_resolves_via_the_real_attribute(page) -> None:
    """First fixture for termly (19 table entries existed, most with zero
    coverage). Verified 2026-08-22 against three live deployments
    (termly.io, Alamy, Queen Mary University of London), all on the same
    current runtime.

    The table's settings selector was `[data-tid='banner-preferences']`,
    which was never observed live - the real attribute is
    `data-focus-id='preferences-button'`. Also confirmed live: reject is
    second-layer-only (a Decline All button that appears only inside the
    preferences modal, injected dynamically rather than merely hidden), and
    that modal has no save control at all in any of the three captures -
    `save: []` is a fact about this runtime, not a placeholder for a gap."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="termly-code-snippet-support" class="termly-ready">
          <div aria-label="Cookie Consent Prompt" data-termly-part="consent-banner"
               role="alertdialog" class="t-consentPrompt">
            <p>We use cookies to improve your experience.</p>
            <button aria-haspopup="dialog" data-focus-id="preferences-button" class="t-preference-button">
              Preferences
            </button>
            <button data-tid="banner-accept" class="t-acceptAllButton">Accept</button>
          </div>
        </div>
        <script>
          document.querySelector('.t-preference-button').addEventListener('click', () => {
            document.querySelector('.t-consentPrompt').remove();
            const modal = document.createElement('div');
            modal.setAttribute('role', 'dialog');
            modal.innerHTML = `
              <button class="t-declineAllButton">Decline All</button>
              <button class="t-allowAllButton">Allow All</button>
            `;
            document.getElementById('termly-code-snippet-support').appendChild(modal);
            modal.querySelector('.t-declineAllButton').addEventListener('click', () => {
              modal.remove();
              document.cookie = 'TERMLY_API_CACHE=denied; path=/';
            });
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "termly", match
        entry = match["entry"]

        settings_control, _, settings_resolution = find_control(page, "settings", entry)
        assert settings_control is not None, settings_resolution

        # Pin the specific fix rather than relying on `.t-preference-button` (kept
        # in the table and also present in this fixture) to carry the match by
        # list order: the removed `data-tid` selector must never resolve via the
        # CMP table itself against real markup (generic text-scoring still finds
        # the button by its label - that fallback existing is fine; the table
        # entry being wrong is the thing being checked here), and the added
        # `data-focus-id` selector must resolve through the table alone.
        old_entry = dict(entry, settings=["[data-tid='banner-preferences']"])
        _, _, old_resolution = find_control(page, "settings", old_entry)
        assert old_resolution["cmp_table_miss"] is True, old_resolution
        assert old_resolution["path"] != "cmp_selector_table", old_resolution

        new_entry = dict(entry, settings=["[data-focus-id='preferences-button']"])
        new_control, _, new_resolution = find_control(page, "settings", new_entry)
        assert new_control is not None, new_resolution
        assert new_resolution["path"] == "cmp_selector_table", new_resolution

        # Reject does not exist until the preferences modal is created - this is
        # the second-layer-only shape confirmed on all three live deployments.
        top_level, _, top_resolution = find_control(page, "reject", entry)
        assert top_level is None, "this fixture's Decline All does not exist until Preferences is opened"
        assert top_resolution["cmp_table_miss"] is True, top_resolution

        # save: [] is correct for the current runtime, not an oversight.
        assert entry["save"] == [], entry["save"]

        result = _denial_for(page, entry)
        assert result["status"] == "second_layer_reject_clicked", result
        assert result["resolution"]["second_layer_reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a Termly-shaped banner (verified live, 3 deployments) resolves settings via the real data-focus-id attribute")


def test_osano_shape_completes_via_settings_toggles_and_save(page) -> None:
    """First fixture for osano. Verified 2026-08-22 against three live US-region
    deployments (osano.com, New Relic, JD Supra): none rendered an accept or
    reject control at all - only 'Manage Preferences', and (after opening it)
    a Save button. `.osano-cm-button--type_save` was removed from `save`
    because the live save control never carried that class, only
    `.osano-cm-save`.

    This shape - no first-layer or second-layer reject, only a settings panel
    with toggles and a save control - is exactly what the generic
    toggle-then-save fallback in execute_denial exists for. This fixture
    proves that path still completes correctly with the corrected, narrower
    save selector, ending in `preferences_disabled_and_saved` rather than the
    misleading `manual_required` this whole mechanism was built to avoid."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div class="osano-cm-window">
          <div role="dialog" aria-label="Cookie Consent Banner"
               class="osano-cm-window__dialog osano-cm-dialog osano-cm-dialog--type_bar">
            <p>We use cookies to improve your experience.</p>
            <button class="osano-cm-manage osano-cm-buttons__button osano-cm-button osano-cm-button--type_manage">
              Manage Preferences
            </button>
          </div>
        </div>
        <script>
          document.querySelector('.osano-cm-manage').addEventListener('click', () => {
            document.querySelector('.osano-cm-window').innerHTML = `
              <label><input type="checkbox" checked> Analytics</label>
              <label><input type="checkbox" checked> Marketing</label>
              <button class="osano-cm-save osano-cm-view__button osano-cm-button">Save</button>
            `;
            document.querySelector('.osano-cm-save').addEventListener('click', () => {
              document.querySelector('.osano-cm-window').remove();
              document.cookie = 'osano_consentmanager=denied; path=/';
            });
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "osano", match
        entry = match["entry"]

        # No accept or reject control exists anywhere in this US-shaped fixture,
        # matching all three live captures.
        top_reject, _, top_resolution = find_control(page, "reject", entry)
        assert top_reject is None, "this fixture has no reject control at all, like the live US captures"
        assert top_resolution["cmp_table_miss"] is True, top_resolution

        # The removed `.osano-cm-button--type_save` selector must not be what
        # resolves save; only `.osano-cm-save` may.
        assert entry["save"] == [".osano-cm-save"], entry["save"]

        result = _denial_for(page, entry)
        assert result["status"] == "preferences_disabled_and_saved", result
        assert len(result.get("toggle_result", {}).get("disabled", [])) == 2, result
        assert result["resolution"]["save"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("an Osano-shaped US banner (verified live, 3 deployments) completes via settings, toggles, and the corrected save selector")


def test_cookieyes_shape_scopes_to_the_visible_layer(page) -> None:
    """Last of the five CMPs from the 2026-08-22 live-capture research pass.
    Verified against cookieyes.com and Ahrefs; unlike the other four, no
    correction was needed here - all five table selectors matched real
    markup exactly. Fixtured anyway to close out the set and pin a real quirk
    the research flagged: the standard template's preference-center Accept
    All button shares its class with the first-layer one and both can exist
    in the DOM at once.

    The hidden modal copy is placed BEFORE the visible banner one - the
    adversarial order, and a real shape (a preference center injected ahead
    of the banner in markup order). `_locate_by_selectors` used to check only
    `.first` for visibility and give up on the whole selector if it wasn't
    visible, so this exact fixture used to fall through to text scoring
    (`cmp_table_miss: True`) with a passing-but-vacuous assertion. It now
    checks every match in order, so the CMP table itself must resolve this."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div class="cky-modal" hidden>
          <div class="cky-preference-center" id="ckyPreferenceCenter">
            <button class="cky-btn cky-btn-accept" aria-label="Accept All" data-cky-tag="accept-button">Accept All</button>
            <button class="cky-btn cky-btn-preferences" aria-label="Save My Preferences" data-cky-tag="detail-save-button">
              Save My Preferences
            </button>
          </div>
        </div>
        <div class="cky-consent-container cky-banner-bottom" role="region" aria-label="We value your privacy" tabindex="-1">
          <button class="cky-btn cky-btn-customize" aria-label="Customise" data-cky-tag="settings-button">Customise</button>
          <button class="cky-btn cky-btn-reject" aria-label="Reject All" data-cky-tag="reject-button">Reject All</button>
          <button class="cky-btn cky-btn-accept" aria-label="Accept All" data-cky-tag="accept-button">Accept All</button>
        </div>
        <script>
          document.querySelector('.cky-btn-reject').addEventListener('click', () => {
            document.querySelector('.cky-consent-container').remove();
            document.cookie = 'cookieyes-consent=no,no,no; path=/';
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "cookieyes", match
        entry = match["entry"]

        # Two elements match the accept selector at once, the hidden one first in
        # DOM order; resolution must still land on the CMP table, on the visible
        # instance - not fall through to text scoring because the first match
        # happened to be hidden.
        accept_control, _, accept_resolution = find_control(page, "accept", entry)
        assert accept_control is not None, accept_resolution
        assert accept_resolution["path"] == "cmp_selector_table", (
            f"a hidden first match must not make the whole selector miss and fall back to text scoring: {accept_resolution}"
        )
        assert accept_control["frame_url"] == page.main_frame.url
        box = accept_control.get("box") or {}
        assert box.get("width", 0) > 0 and box.get("height", 0) > 0, (
            f"the resolved accept control must be the visible one, not the hidden modal copy listed first in the DOM: {accept_control}"
        )

        result = _denial_for(page, entry)
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a CookieYes-shaped banner (verified live) scopes accept to the visible layer despite a duplicate hidden copy")


def test_trustarc_shape_resolves_accept_and_reject_directly(page) -> None:
    """First fixture for trustarc. Verified 2026-08-22 against trustarc.com's
    own site: container, accept, reject, and settings selectors all matched
    real markup exactly, and - unlike the enterprise iframe-embed pattern the
    table's notes describe - both 'Accept All' and 'Reject Optional' are
    directly visible at the first layer on this deployment, no settings
    detour needed. Clicking 'Manage Settings' produced no
    consent.trustarc.com iframe here, so the iframe/preference-manager
    behaviour is documented as unverified on this deployment rather than
    fixtured as if it were confirmed."""
    with _serve_cmp_fixture(page, """
        <!doctype html><html><body>
        <div id="truste-consent-track" class="tc-track ta-show ta-display-block" role="banner">
          <div id="truste-consent-content" class="tc-content">
            <p>This site uses cookies and related technologies for site operation, analytics, and advertising.</p>
            <button id="truste-consent-button" class="tc-btn-primary tc-btn-icon">Accept All</button>
            <button id="truste-consent-required" class="tc-btn-primary tc-btn-icon">Reject Optional</button>
            <button id="truste-show-consent" class="tc-btn-secondary tc-btn-icon">Manage Settings</button>
          </div>
        </div>
        <script>
          document.getElementById('truste-consent-required').addEventListener('click', () => {
            document.getElementById('truste-consent-track').remove();
            document.cookie = 'notice_gdpr_prefs=0::; path=/';
          });
        </script></body></html>
    """):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "trustarc", match
        entry = match["entry"]

        accept_control, _, accept_resolution = find_control(page, "accept", entry)
        assert accept_control is not None, accept_resolution
        assert accept_resolution["path"] == "cmp_selector_table", accept_resolution

        result = _denial_for(page, entry)
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a TrustArc-shaped banner (verified live against trustarc.com) resolves accept and reject directly")


def test_iubenda_shape_reject_uses_the_continue_without_accepting_control(page) -> None:
    """First fixture for iubenda. The table entry was written from documentation,
    not a live capture. iubenda.com's own site was checked first and runs no
    CMP of its own (no #iubenda-cs-banner, no iubenda script host, no consent
    popup at all) - so this is instead verified 2026-08-23 against
    https://www.tannico.it, a live Iubenda customer deployment.

    `reject` needed a second control, not a replacement: tannico.it renders no
    `.iubenda-cs-reject-btn` at either layer, but that is because its banner
    config sets `_iub.cs.options.banner.rejectButtonDisplay: false` (caption
    'Rifiuta'), not because the control does not exist. The CMP bundle
    tannico.it itself loads renders `.iubenda-cs-reject-btn` when that flag is
    on, so the selector is retained ahead of the fallback as a
    real-but-not-observed-on-this-capture control. The fallback,
    `.iubenda-cs-cwa-button` ('Continua senza accettare' / 'Continue without
    accepting'), is the same dismiss-without-agreeing shape already documented
    on the Didomi entry (`.didomi-continue-without-agreeing`) and is what
    tannico.it itself renders since its reject button is disabled. Clicking it
    removes the banner and writes `_iub_cs-<id>` with every non-necessary
    purpose false, confirmed live to be a complete one-click denial.

    `save` was also wrong: `.iub-cmp-save-btn` does not exist either; the real
    settings-panel save control is the id `#iubFooterBtn` ('Salva e
    continua'), which carries no distinguishing class at all. The settings
    panel additionally exposes a `.purposes-btn-reject` ('Rifiuta tutto')
    bulk-toggle button, reproduced below - but live testing showed clicking it
    alone only unchecks the optional-purpose checkboxes and writes no cookie
    and does not close the panel; `#iubFooterBtn` still has to be clicked
    afterward to commit. It is deliberately NOT in `reject`: adding it would
    make execute_denial report `second_layer_reject_clicked` for a click that
    saved nothing, the same false-positive shape the Cookiebot
    preferences-checkbox bug was."""
    fixture_html = """
        <!doctype html><html><body>
        <div id="iubenda-cs-banner" class="iubenda-cs-default-floating iubenda-cs-bottom iubenda-cs-center">
          <div class="iubenda-cs-container" role="alertdialog">
            <div class="iubenda-cs-content">
              <p>Utilizziamo i cookie per migliorare la tua esperienza.</p>
              <button class="iubenda-cs-cwa-button" aria-label="Continua senza accettare - Chiudi questa informativa">
                Continua senza accettare &rarr;
              </button>
              <button class="iubenda-cs-customize-btn">Scopri di pi&ugrave; e personalizza</button>
              <button class="iubenda-cs-accept-btn iubenda-cs-btn-primary">Accetta</button>
            </div>
          </div>
        </div>
        <div id="iubenda-iframe" hidden>
          <div id="purposes-content-container" class="iubenda purposes-widget">
            <div class="purposes-content">
              <div class="iub-consent-buttons purposes-buttons">
                <button class="iub-btn iub-btn-consent iub-btn-reject purposes-btn purposes-btn-reject">Rifiuta tutto</button>
                <button class="iub-btn iub-btn-consent iub-btn-accept purposes-btn purposes-btn-accept">Accetta tutto</button>
              </div>
              <label><input type="checkbox" id="purpose-4" checked> Statistiche</label>
              <label><input type="checkbox" id="purpose-5" checked> Marketing</label>
            </div>
          </div>
          <div class="iubenda-iframe-footer iubenda-iframe-footer-absolute">
            <div id="iubFooterBtnContainer">
              <button id="iubFooterBtn">Salva e continua</button>
            </div>
          </div>
        </div>
        <script>
          document.querySelector('.iubenda-cs-customize-btn').addEventListener('click', () => {
            document.querySelector('#iubenda-cs-banner').hidden = true;
            document.querySelector('#iubenda-iframe').hidden = false;
          });
          document.querySelector('.purposes-btn-reject').addEventListener('click', () => {
            // Live behaviour: only unchecks the optional toggles. No cookie,
            // no close - #iubFooterBtn still has to be clicked to commit.
            document.querySelectorAll('#iubenda-iframe input[type=checkbox]').forEach(cb => cb.checked = false);
          });
          document.querySelector('#iubFooterBtn').addEventListener('click', () => {
            const purpose4 = document.querySelector('#purpose-4').checked;
            const purpose5 = document.querySelector('#purpose-5').checked;
            document.querySelector('#iubenda-iframe').remove();
            document.cookie = `_iub_cs-12345={"purposes":{"1":true,"4":${purpose4},"5":${purpose5}}}; path=/`;
          });
          document.querySelector('.iubenda-cs-cwa-button').addEventListener('click', () => {
            document.querySelector('#iubenda-cs-banner').remove();
            document.cookie = '_iub_cs-12345={"purposes":{"1":true,"4":false,"5":false}}; path=/';
          });
        </script></body></html>
    """
    with _serve_cmp_fixture(page, fixture_html):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "iubenda", match
        entry = match["entry"]

        # Structural guard: `.iubenda-cs-reject-btn` is a real control on
        # deployments that enable it (see the second fixture below), so it
        # belongs in the table - but it must stay ordered ahead of the
        # dismiss-without-agreeing fallback, since it is the genuine
        # reject-all and should win when both are present.
        assert ".iubenda-cs-reject-btn" in entry["reject"], (
            "the real Iubenda reject-all control must be present in the table"
        )
        assert entry["reject"].index(".iubenda-cs-reject-btn") < entry["reject"].index(".iubenda-cs-cwa-button"), (
            "the reject-all control must be tried before the dismiss-without-agreeing fallback"
        )
        assert ".iub-cmp-save-btn" not in entry["save"], (
            "the historically wrong save selector (absent from real markup) must not return to the table"
        )

        # Mutation check: the removed save selector is proven here to never
        # have matched this real markup shape, not just assumed absent -
        # find_control must fall through to a CMP-table miss, exactly as it
        # did on the live site.
        old_save_entry = dict(entry, save=[".iub-cmp-save-btn"])
        _, _, old_save_resolution = find_control(page, "save", old_save_entry)
        assert old_save_resolution["cmp_table_miss"] is True, old_save_resolution
        assert old_save_resolution["path"] != "cmp_selector_table", old_save_resolution
        ok("the removed iubenda save selector is confirmed to match nothing on real markup, not just suspected to")

        # The current table's reject resolves to the real 'continue without
        # accepting' control, through the CMP table, before it is clicked.
        reject_control, _, reject_resolution = find_control(page, "reject", entry)
        assert reject_control is not None, reject_resolution
        assert reject_resolution["path"] == "cmp_selector_table", reject_resolution

        settings_control, _, settings_resolution = find_control(page, "settings", entry)
        assert settings_control is not None, settings_resolution
        assert settings_resolution["path"] == "cmp_selector_table", settings_resolution

        result = _denial_for(page, entry)
        assert result["status"] == "direct_reject_clicked", result
        assert result["click_count"] == 1, result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("an Iubenda-shaped banner (verified live against tannico.it) resolves reject via the real "
           "'continue without accepting' control, since this deployment disables .iubenda-cs-reject-btn "
           "via rejectButtonDisplay: false")

    # Positive coverage for the corrected `save` selector, on a fresh copy of
    # the fixture: the structural guard above only proves the corrected
    # selector is absent from the historical entries, never that the current
    # one (`#iubFooterBtn`) actually resolves and commits - `_denial_for`
    # never reaches it via `entry` because `direct_reject_clicked`
    # short-circuits at click_count == 1. Forcing `reject` empty instead
    # routes execute_denial through the settings -> toggle -> save fallback,
    # the same shape as the Osano fixture above.
    with _serve_cmp_fixture(page, fixture_html):
        assert entry["save"] == ["#iubFooterBtn"], entry["save"]

        save_only_entry = dict(entry, reject=[])
        save_result = _denial_for(page, save_only_entry)
        assert save_result["status"] == "preferences_disabled_and_saved", save_result
        assert save_result["resolution"]["save"] == {
            "kind": "save",
            "path": "cmp_selector_table",
            "matched_selector": "#iubFooterBtn",
            "cmp": "iubenda",
        }, save_result["resolution"]
        assert (save_result.get("verification") or {}).get("verified") is True, save_result
        ok("the corrected iubenda save selector (#iubFooterBtn) resolves through the CMP table and completes "
           "preferences_disabled_and_saved via the settings -> toggle -> save fallback")

    # Second layer, on another fresh copy: the docstring stakes a correctness
    # claim on `.purposes-btn-reject` alone doing nothing - no cookie, no
    # closed panel - which is why it is deliberately excluded from `reject`.
    # Nothing asserted that claim before this. Note this exercises save
    # directly through find_control (the same resolver execute_denial uses)
    # rather than via `_denial_for`: the panel, once opened, hides its own
    # `.iubenda-cs-customize-btn` trigger (real site behaviour, reproduced in
    # the fixture), so a second settings-click - which execute_denial's
    # settings -> toggle -> save fallback always attempts first - would find
    # nothing and report `manual_required` instead.
    with _serve_cmp_fixture(page, fixture_html):
        page.click(".iubenda-cs-customize-btn")
        assert page.evaluate(
            "() => { const el = document.getElementById('iubenda-iframe'); return el !== null && !el.hidden; }"
        ), "the settings panel must be open before .purposes-btn-reject is exercised"

        page.click(".purposes-btn-reject")
        assert page.evaluate(
            "() => { const el = document.getElementById('iubenda-iframe'); return el !== null && !el.hidden; }"
        ), "clicking .purposes-btn-reject alone must not close the settings panel"
        assert "_iub_cs-" not in page.evaluate("() => document.cookie"), (
            "clicking .purposes-btn-reject alone must not write a consent cookie - "
            "only #iubFooterBtn commits"
        )

        before = consent_snapshot(page, page.context, entry)
        save_control, _, save_resolution = find_control(page, "save", entry)
        assert save_control is not None, save_resolution
        assert save_resolution == {
            "kind": "save",
            "path": "cmp_selector_table",
            "matched_selector": "#iubFooterBtn",
            "cmp": "iubenda",
        }, save_resolution
        save_control["locator"].click()
        after = consent_snapshot(page, page.context, entry)
        verification = verify_choice_registered(before, after)
        assert verification["verified"] is True, verification
        assert "_iub_cs-" in page.evaluate("() => document.cookie"), (
            "the corrected save selector must be what actually commits the consent cookie"
        )
        ok("an Iubenda settings panel confirms .purposes-btn-reject alone commits nothing, and the "
           "corrected save selector (#iubFooterBtn) is what actually commits the denial")

    # Third fixture: the other real first-layer shape, on a deployment that
    # enables `rejectButtonDisplay`. tannico.it disables this control, but the
    # shipped CMP bundle renders it - with exactly this markup, tabindex and
    # role - whenever the flag is on, so the restored `.iubenda-cs-reject-btn`
    # selector needs its own coverage rather than shipping untested. No
    # `.iubenda-cs-cwa-button` is present here, so `find_control` can only
    # resolve `reject` via the table if `.iubenda-cs-reject-btn` itself works.
    reject_display_fixture_html = """
        <!doctype html><html><body>
        <div id="iubenda-cs-banner" class="iubenda-cs-default-floating iubenda-cs-bottom iubenda-cs-center">
          <div class="iubenda-cs-container" role="alertdialog">
            <div class="iubenda-cs-content">
              <p>Utilizziamo i cookie per migliorare la tua esperienza.</p>
              <button class="iubenda-cs-reject-btn iubenda-cs-btn-primary" tabindex="0" role="button">Rifiuta</button>
              <button class="iubenda-cs-customize-btn">Scopri di pi&ugrave; e personalizza</button>
              <button class="iubenda-cs-accept-btn iubenda-cs-btn-primary">Accetta</button>
            </div>
          </div>
        </div>
        <script>
          document.querySelector('.iubenda-cs-reject-btn').addEventListener('click', () => {
            document.querySelector('#iubenda-cs-banner').remove();
            document.cookie = '_iub_cs-12345={"purposes":{"1":true,"4":false,"5":false}}; path=/';
          });
        </script></body></html>
    """
    with _serve_cmp_fixture(page, reject_display_fixture_html):
        display_match = fingerprint_cmp(page, load_cmp_table())
        assert display_match and display_match["id"] == "iubenda", display_match
        display_entry = display_match["entry"]

        # Without the table, the Italian caption alone does not resolve:
        # REJECT_PATTERNS is English-only, so this proves the table entry is
        # load-bearing rather than redundant with text scoring.
        no_table_control, _, no_table_resolution = find_control(page, "reject", None)
        assert no_table_control is None, no_table_resolution

        reject_control, _, reject_resolution = find_control(page, "reject", display_entry)
        assert reject_control is not None, reject_resolution
        assert reject_resolution["path"] == "cmp_selector_table", reject_resolution
        assert reject_resolution["matched_selector"] == ".iubenda-cs-reject-btn", reject_resolution

        result = _denial_for(page, display_entry)
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("an Iubenda deployment with rejectButtonDisplay enabled resolves reject directly via the "
           "restored .iubenda-cs-reject-btn selector, which text scoring alone cannot reach")


def test_complianz_shape_settings_resolves_via_the_real_view_preferences_button(page) -> None:
    """The complianz table entry's `accept`, `reject`, `save`, and
    `consent_storage` were already correct - verified 2026-08-23 against two
    live WordPress deployments: complianz.io itself (dogfooding - its own DOM
    templates both an 'optin' and a region-detected 'optout' banner at once,
    only one shown per visitor's detected region) and wpcodetips.com, a real
    customer site on the default first-layer 'banner-1 banner-a optin'
    template. Clicking `.cmplz-deny` on wpcodetips.com actually wrote
    `cmplz_marketing=deny; cmplz_statistics=deny; cmplz_preferences=deny`
    cookies live, confirming both the selector and the consent_storage names.

    `settings` was wrong, on both captures. The real, functioning first-layer
    settings launcher is `<button class="cmplz-btn cmplz-view-preferences">`
    - confirmed live: clicking it adds `cmplz-categories-visible` to the
    banner and reveals the category toggles plus Save. The table instead had
    `.cmplz-manage-options`, which matches two elements on real markup and
    neither is that launcher: a permanently-hidden (0x0) footer text link
    `<a class="cmplz-link cmplz-manage-options cookie-statement"
    href=".../#cmplz-manage-consent-container">Manage options</a>` that
    navigates to a *different page* rather than opening the panel in place,
    and an equally-hidden TCF-only variant `<a class="cmplz-btn
    cmplz-manage-options tcf cookie-statement">`. On both live captures this
    left `settings` unresolvable (cmp_table_miss) despite a real, visible,
    working launcher sitting right next to it under a different class. Both
    captures also show Deny directly reachable at the first layer whenever
    the settings launcher is present, so this particular bug never actually
    blocked a live denial outright the way the Cookiebot/Termly bugs could -
    but a CMP-table settings resolution failure is still exactly the shape
    that would strand a denial with no working path on any deployment where
    reject is second-layer-only, and the launcher itself is proven below to
    genuinely open the real panel and, paired with the already-correct save
    selector, commit a real consent write.

    Also confirmed live and reproduced below: the 'Functional' category's
    checkbox (`#cmplz-functional-optin`, always-active) is present in the DOM
    but `display: none` - it is not just unchecked, it is not interactable."""
    fixture_html = """
        <!doctype html><html><body>
        <div id="cmplz-cookiebanner-container">
          <div id="cmplz-cookiebanner-1-optin"
               class="cmplz-cookiebanner banner-1 banner-a optin cmplz-bottom-right cmplz-categories-type-view-preferences cmplz-show"
               role="dialog" aria-modal="true">
            <div class="cmplz-header">
              <div class="cmplz-title" id="cmplz-header-1-optin">Manage Consent</div>
            </div>
            <div class="cmplz-body">
              <div class="cmplz-message" id="cmplz-message-1-optin">
                We use cookies to improve your experience.
              </div>
              <div class="cmplz-categories" style="display:none">
                <details class="cmplz-category cmplz-functional">
                  <summary>
                    <span class="cmplz-category-header">
                      <span class="cmplz-category-title">Functional</span>
                      <span class="cmplz-always-active">
                        <span class="cmplz-banner-checkbox">
                          <input type="checkbox" id="cmplz-functional-optin" data-category="cmplz_functional"
                                 class="cmplz-consent-checkbox cmplz-functional" checked style="display:none">
                          <label class="cmplz-label" for="cmplz-functional-optin">
                            <span class="screen-reader-text">Functional</span>
                          </label>
                        </span>
                        Always active
                      </span>
                    </span>
                  </summary>
                </details>
                <details class="cmplz-category cmplz-statistics">
                  <summary>
                    <span class="cmplz-category-header">
                      <span class="cmplz-category-title">Statistics</span>
                      <span class="cmplz-banner-checkbox">
                        <input type="checkbox" id="cmplz-statistics-optin" data-category="cmplz_statistics"
                               class="cmplz-consent-checkbox cmplz-statistics">
                        <label class="cmplz-label" for="cmplz-statistics-optin">
                          <span class="screen-reader-text">Statistics</span>
                        </label>
                      </span>
                    </span>
                  </summary>
                </details>
                <details class="cmplz-category cmplz-marketing">
                  <summary>
                    <span class="cmplz-category-header">
                      <span class="cmplz-category-title">Marketing</span>
                      <span class="cmplz-banner-checkbox">
                        <input type="checkbox" id="cmplz-marketing-optin" data-category="cmplz_marketing"
                               class="cmplz-consent-checkbox cmplz-marketing">
                        <label class="cmplz-label" for="cmplz-marketing-optin">
                          <span class="screen-reader-text">Marketing</span>
                        </label>
                      </span>
                    </span>
                  </summary>
                </details>
              </div>
              <div class="cmplz-links cmplz-information">
                <ul>
                  <li><a class="cmplz-link cmplz-manage-options cookie-statement"
                         href="https://cmp-fixture.test/cookie-policy/#cmplz-manage-consent-container"
                         style="display:none">Manage options</a></li>
                </ul>
              </div>
              <div class="cmplz-buttons">
                <button class="cmplz-btn cmplz-accept">Accept</button>
                <button class="cmplz-btn cmplz-deny">Deny</button>
                <button class="cmplz-btn cmplz-view-preferences">View preferences</button>
                <button class="cmplz-btn cmplz-save-preferences" style="display:none">Save preferences</button>
                <a class="cmplz-btn cmplz-manage-options tcf cookie-statement"
                   href="https://cmp-fixture.test/cookie-policy/#cmplz-manage-consent-container"
                   style="display:none">View preferences</a>
              </div>
            </div>
          </div>
        </div>
        <script>
          function cmplzDeny() {
            document.cookie = 'cmplz_banner-status=dismissed; path=/';
            document.cookie = 'cmplz_marketing=deny; path=/';
            document.cookie = 'cmplz_statistics=deny; path=/';
            document.cookie = 'cmplz_preferences=deny; path=/';
            document.cookie = 'cmplz_functional=allow; path=/';
            document.cookie = 'cmplz_consented_services=; path=/';
            document.querySelector('.cmplz-cookiebanner').classList.add('cmplz-dismissed');
            document.querySelector('.cmplz-cookiebanner').style.display = 'none';
          }
          document.querySelector('.cmplz-deny').addEventListener('click', cmplzDeny);
          document.querySelector('.cmplz-view-preferences').addEventListener('click', () => {
            const banner = document.querySelector('.cmplz-cookiebanner');
            banner.classList.add('cmplz-categories-visible');
            document.querySelector('.cmplz-categories').style.display = '';
            document.querySelector('.cmplz-save-preferences').style.display = 'block';
          });
          document.querySelector('.cmplz-save-preferences').addEventListener('click', () => {
            const statistics = document.querySelector('#cmplz-statistics-optin').checked;
            const marketing = document.querySelector('#cmplz-marketing-optin').checked;
            document.cookie = 'cmplz_banner-status=dismissed; path=/';
            document.cookie = `cmplz_statistics=${statistics ? 'allow' : 'deny'}; path=/`;
            document.cookie = `cmplz_marketing=${marketing ? 'allow' : 'deny'}; path=/`;
            document.cookie = 'cmplz_preferences=deny; path=/';
            document.cookie = 'cmplz_functional=allow; path=/';
            document.cookie = 'cmplz_consented_services=; path=/';
            document.querySelector('.cmplz-cookiebanner').classList.add('cmplz-dismissed');
            document.querySelector('.cmplz-cookiebanner').style.display = 'none';
          });
        </script></body></html>
    """
    with _serve_cmp_fixture(page, fixture_html):
        match = fingerprint_cmp(page, load_cmp_table())
        assert match and match["id"] == "complianz", match
        entry = match["entry"]

        # Structural guard against reintroduction: `_locate_by_selectors`
        # returns the first VISIBLE match in list order, so if the buggy
        # selector were ever added back *behind* the real launcher,
        # find_control would still resolve correctly and the mutation check
        # below (which replaces the list wholesale) would not catch it.
        # Assert directly against the table entry itself.
        assert ".cmplz-manage-options" not in entry["settings"], (
            "the historically buggy settings selector (matches only a hidden "
            "cross-page link and a hidden TCF variant, never the real launcher) "
            "must not return to the table"
        )

        # Mutation check: the removed selector is proven here to resolve to
        # nothing on this real markup shape, not just assumed broken -
        # find_control must fall through to a CMP-table miss, exactly as it
        # did on both live captures.
        buggy_entry = dict(entry, settings=[".cmplz-manage-options"])
        _, _, buggy_resolution = find_control(page, "settings", buggy_entry)
        assert buggy_resolution["cmp_table_miss"] is True, buggy_resolution
        assert buggy_resolution["path"] != "cmp_selector_table", buggy_resolution
        ok("the removed complianz settings selector is confirmed to match nothing visible on real markup, not just suspected to")

        # The corrected selector resolves through the CMP table, and clicking
        # it is what actually opens the real preferences panel.
        settings_control, _, settings_resolution = find_control(page, "settings", entry)
        assert settings_control is not None, settings_resolution
        assert settings_resolution["path"] == "cmp_selector_table", settings_resolution
        assert settings_resolution["matched_selector"] == ".cmplz-view-preferences", settings_resolution
        settings_control["locator"].click()
        assert "cmplz-categories-visible" in (page.get_attribute(".cmplz-cookiebanner", "class") or ""), (
            "the corrected settings selector must resolve to the control that actually opens the panel"
        )
        ok("the corrected complianz settings selector (.cmplz-view-preferences) resolves through the CMP table and actually opens the real preferences panel")

        # `save` was already correct in the table; confirm the pair actually
        # works together - opening the panel via the corrected selector, then
        # committing via save - and that the commit is a real, verified
        # consent write, matching the real cmplz_marketing/cmplz_statistics
        # cookies observed live on wpcodetips.com. This uses find_control
        # directly (the same resolver execute_denial calls internally)
        # rather than `_denial_for`, since Deny is directly reachable on this
        # real shape and `_denial_for` would take that shortcut instead of
        # the settings route (see below).
        before = consent_snapshot(page, page.context, entry)
        save_control, _, save_resolution = find_control(page, "save", entry)
        assert save_control is not None, save_resolution
        assert save_resolution["path"] == "cmp_selector_table", save_resolution
        save_control["locator"].click()
        after = consent_snapshot(page, page.context, entry)
        verification = verify_choice_registered(before, after)
        assert verification["verified"] is True, verification
        ok("the settings panel opened via the corrected selector commits a real, verified denial once Save is clicked")

    # Fresh fixture: confirms `_denial_for`'s real first-layer path is
    # unaffected by the settings fix - Deny is directly reachable on this
    # real shape (unlike the second-layer-only shapes documented on
    # Cookiebot/Termly above), so a settings detour is correctly never taken.
    with _serve_cmp_fixture(page, fixture_html):
        result = _denial_for(page, entry)
        assert result["status"] == "direct_reject_clicked", result
        assert result["resolution"]["reject"]["path"] == "cmp_selector_table", result["resolution"]
        assert (result.get("verification") or {}).get("verified") is True, result
        ok("a Complianz-shaped banner (verified live, complianz.io and wpcodetips.com) resolves reject directly")


def test_safe_internal_links_refuses_dangerous_and_offsite(page) -> None:
    """This decides what the auditor navigates to on a live site the user owns.
    The skill promises no logout, no account change, no purchase and no
    download, and this function is the only thing enforcing it."""
    page.set_content("""
        <!doctype html><html><body>
          <a href="https://fixture.test/about">About us</a>
          <a href="https://fixture.test/services">Services</a>
          <a href="https://fixture.test/logout">Log out</a>
          <a href="https://fixture.test/account/delete">Delete account</a>
          <a href="https://fixture.test/cart/checkout">Checkout</a>
          <a href="https://fixture.test/unsubscribe">Unsubscribe</a>
          <a href="https://fixture.test/sign-in">Sign in</a>
          <a href="https://fixture.test/brochure.pdf">Brochure</a>
          <a href="https://fixture.test/installer.dmg">Download</a>
          <a href="https://other.test/about">Offsite</a>
          <a href="mailto:x@fixture.test">Email</a>
          <a href="javascript:doThing()">Script</a>
          <a href="https://fixture.test/">Home</a>
          <a href="https://fixture.test/quiet" style="display:none">Hidden</a>
        </body></html>
    """)
    links = safe_internal_links(page, "https://fixture.test/", limit=10)

    for banned in (
        "https://fixture.test/logout",
        "https://fixture.test/account/delete",
        "https://fixture.test/cart/checkout",
        "https://fixture.test/unsubscribe",
        "https://fixture.test/sign-in",
        "https://fixture.test/brochure.pdf",
        "https://fixture.test/installer.dmg",
        "https://other.test/about",
    ):
        assert banned not in links, f"must never be navigated to: {banned}"
    assert not any(l.startswith(("mailto:", "javascript:")) for l in links), links
    # The start page itself is not a second page to visit.
    assert "https://fixture.test/" not in links, links
    # An invisible link is not something a user could follow.
    assert "https://fixture.test/quiet" not in links, links

    assert "https://fixture.test/about" in links, links
    assert "https://fixture.test/services" in links, links

    # The limit is a hard cap, and limit<=0 means no navigation at all.
    assert len(safe_internal_links(page, "https://fixture.test/", limit=1)) == 1
    assert safe_internal_links(page, "https://fixture.test/", limit=0) == []
    ok("internal-link selection refuses logout, account, purchase, download, and offsite links")


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


def test_form_submission_never_touches_an_unsafe_form(page) -> None:
    """--submit-forms is the only flag in the tool with a real-world side effect:
    it creates a genuine record in the site's CRM. The promise is that login,
    signup, payment, and account forms are skipped *entirely* even then. Nothing
    exercised the submitting path at all, so that promise was untested."""
    page.set_content("""
        <!doctype html><html><body>
        <form id="login-form" action="/session">
          <input name="username" type="text">
          <input name="password" type="password">
          <button type="submit">Sign in</button>
        </form>
        <form id="contact-us" action="/contact">
          <input name="email" type="email">
          <input name="phone" type="tel">
          <input name="full_name" type="text">
          <input name="secret" type="password">
          <button type="submit">Send</button>
        </form>
        <script>
          window.__submitted = [];
          for (const f of document.querySelectorAll('form')) {
            f.addEventListener('submit', e => { e.preventDefault(); window.__submitted.push(f.id); });
          }
        </script></body></html>
    """)
    config = ScenarioConfig(url="https://example.test", wait_ms=10, submit_forms=True)
    record = exercise_forms(page, config)

    skipped = {s["index"]: s for s in record["skipped_forms"]}
    assert 0 in skipped, f"the login form must be skipped outright: {record['skipped_forms']}"
    assert "unsafe" in skipped[0]["reason"], skipped[0]

    filled = {f["field"] for f in record["fields_filled"]}
    assert not any("username" in f for f in filled), f"no field of a login form may be filled: {filled}"

    # A password input is refused by type as well as by form signature, so a
    # safe-looking form containing one still never has it filled.
    assert not any("secret" in f for f in filled), f"password fields must never be filled: {filled}"
    values = page.evaluate(
        "() => ({secret: document.querySelector('[name=secret]').value,"
        " username: document.querySelector('[name=username]').value,"
        " email: document.querySelector('[name=email]').value})"
    )
    assert values["secret"] == "", "a password field must be left empty"
    assert values["username"] == "", "a login form's fields must be left empty"

    # The safe form was filled with obviously synthetic, undeliverable values.
    assert "@example.com" in values["email"], values
    assert values["email"] == SYNTHETIC_VALUES["email"], values

    # And only the safe form was submitted.
    assert record["submitted"] is True, record
    submitted = page.evaluate("() => window.__submitted")
    assert submitted == ["contact-us"], f"only the safe form may be submitted: {submitted}"
    ok("--submit-forms fills and submits only a safe form, never a login or a password field")


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


def test_capture_checkpoint_writes_state_and_screenshots(page) -> None:
    """capture_checkpoint is the one function that touches disk on every scenario
    step: raw + redacted state JSON, viewport/full screenshots, and - when a
    banner container resolves in the main frame - a cropped banner screenshot.
    None of the disk-writing or banner-crop paths were exercised at all."""
    page.set_content(HUBSPOT_BANNER)
    with tempfile.TemporaryDirectory(prefix="cookie-auditor-checkpoint-") as temp:
        temp_path = Path(temp)
        private_dir = temp_path / "private"
        share_dir = temp_path / "share"
        result = capture_checkpoint(page, page.context, "baseline", "before", private_dir, share_dir)

        assert result["scenario"] == "baseline"
        assert result["checkpoint"] == "before"
        # This fixture is loaded via set_content (no navigation, no CMP click),
        # so the context must hold zero cookies here. A bare isinstance check
        # would pass even with a cookie leaked from an earlier CMP fixture
        # test sharing this same page/context - this catches that leak.
        assert result["cookies"] == [], result["cookies"]
        assert "storage_state" in result
        assert result["banner"]["containers"], "the HubSpot banner container should be detected"

        # Viewport and full-page screenshots are always attempted; the banner
        # crop only fires when the top container resolved in the main frame
        # with a usable rect, which this fixture satisfies.
        assert len(result["screenshots"]) == 3, result["screenshots"]
        for shot in result["screenshots"]:
            assert Path(shot).exists() and Path(shot).stat().st_size > 0, shot
        assert any(shot.endswith("-banner.png") for shot in result["screenshots"]), result["screenshots"]

        raw_path = private_dir / "baseline" / "before-state.raw.json"
        redacted_path = share_dir / "baseline" / "before-state.json"
        assert raw_path.exists()
        assert redacted_path.exists()
    ok("capture_checkpoint writes raw+redacted state and viewport/full/banner screenshots")


def test_dwell_and_nudge_scrolls_when_thorough(page) -> None:
    page.set_content("<!doctype html><html><body><div style='height:4000px'>tall</div></body></html>")
    config = ScenarioConfig(url="https://example.test", wait_ms=10, thorough=True, dwell_ms=200, scroll_stages=2)
    record = dwell_and_nudge(page, config)
    assert record["scrolled_to"] == [0.5, 1.0], record
    assert page.evaluate("() => window.scrollY") == 0, "must scroll back to the top when finished"
    ok("dwell_and_nudge scrolls through stages and returns to the top when thorough")


def test_dwell_and_nudge_skips_scrolling_when_not_thorough(page) -> None:
    page.set_content("<!doctype html><html><body><div style='height:4000px'>tall</div></body></html>")
    page.evaluate("() => window.scrollTo(0, 500)")
    config = ScenarioConfig(url="https://example.test", wait_ms=10, thorough=False)
    record = dwell_and_nudge(page, config)
    assert record == {"scrolled_to": [], "dwell_ms": 10}
    assert page.evaluate("() => window.scrollY") == 500, "non-thorough mode must not touch scroll position"
    ok("dwell_and_nudge is a no-op scroll when the profile is not thorough")


def test_exercise_search_fills_and_submits(page) -> None:
    page.set_content("""
        <!doctype html><html><body>
        <form id="site-search" onsubmit="window.__query = document.querySelector('#q').value; return false;">
          <input id="q" type="search" name="q">
        </form>
        </body></html>
    """)
    config = ScenarioConfig(url="https://example.test", wait_ms=10, timeout_ms=2000)
    record = exercise_search(page, config, query="widgets")
    assert record["attempted"] is True
    assert record["submitted"] is True
    assert record["selector"] == "input[type='search']"
    assert page.evaluate("() => window.__query") == "widgets"
    ok("exercise_search fills the on-site search box and submits via Enter")


def test_exercise_search_no_input_present(page) -> None:
    page.set_content("<!doctype html><html><body><p>no search here</p></body></html>")
    config = ScenarioConfig(url="https://example.test", wait_ms=10)
    record = exercise_search(page, config)
    assert record["attempted"] is False
    assert "selector" not in record
    ok("exercise_search is a no-op when no search input is present")


def test_assert_clean_context_detects_dirty_state(page) -> None:
    """assert_clean_context (B5) is the evidence that persistence findings rely
    on - 'the context started with nothing' - rather than an assumption. Its
    cookie/localStorage/sessionStorage checks, and the case where it correctly
    reports the context as NOT clean, were never exercised."""
    context = page.context.browser.new_context()
    try:
        fresh_page = context.new_page()

        def handler(route) -> None:
            route.fulfill(status=200, content_type="text/html", body="<!doctype html><html><body>fixture</body></html>")

        fresh_page.route("**/*", handler)
        fresh_page.goto("https://clean-context.test/")

        clean = assert_clean_context(context, fresh_page)
        assert clean["clean"] is True, clean
        assert clean["cookie_count"] == 0, clean

        context.add_cookies([{"name": "sid", "value": "x", "url": "https://clean-context.test/"}])
        fresh_page.evaluate("() => localStorage.setItem('k', 'v')")
        dirty = assert_clean_context(context, fresh_page)
        assert dirty["clean"] is False, dirty
        assert dirty["cookie_count"] == 1, dirty
        assert dirty["local_storage_keys"] == 1, dirty
    finally:
        context.close()
    ok("assert_clean_context reports a fresh context as clean and a seeded one as not")


def test_run_scenario_end_to_end(browser) -> None:
    """run_scenario is the orchestrator wiring together nearly every other
    function in this module - checkpoints, exercises, event capture, HAR
    sanitization, validity gating - and none of that wiring was exercised end
    to end, only its pieces in isolation."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            body = HUBSPOT_BANNER.encode("utf-8")
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
            url = f"http://127.0.0.1:{port}/"
            config = ScenarioConfig(
                url=url, wait_ms=50, timeout_ms=8000, pages=0,
                thorough=True, dwell_ms=100, scroll_stages=1,
            )
            with tempfile.TemporaryDirectory(prefix="cookie-auditor-scenario-") as temp:
                temp_path = Path(temp)
                result = run_scenario(
                    browser=browser, scenario="denial", config=config,
                    private_dir=temp_path / "private", share_dir=temp_path / "share",
                    action="deny", cmp_table=load_cmp_table(),
                )

                assert result["scenario"] == "denial"
                assert result["action_result"]["status"] == "direct_reject_clicked", result["action_result"]
                assert result["validity"]["valid"] is True, result["validity"]
                assert result["cmp"] and result["cmp"]["id"] == "hubspot", result["cmp"]
                checkpoint_names = [c["checkpoint"] for c in result["checkpoints"]]
                assert checkpoint_names == [
                    "01-pre-interaction", "02-post-denial", "03-after-refresh", "09-post-exercise",
                ], checkpoint_names
                assert result["isolation_assertion"]["clean"] is True, result["isolation_assertion"]
                assert result["errors"] == [], result["errors"]
                assert result["consent_mode"]["summary"]["present"] is False, result["consent_mode"]

                private_scenario = temp_path / "private" / "denial"
                share_scenario = temp_path / "share" / "denial"
                assert (private_scenario / "denial-result.raw.json").exists()
                assert (share_scenario / "denial-result.json").exists()
                assert (private_scenario / "denial-events.raw.json").exists()
                assert (share_scenario / "denial-events.json").exists()

                written = json.loads((share_scenario / "denial-result.json").read_text())
                assert "final_storage_state" not in written, "the share copy must not carry final_storage_state"
        finally:
            server.shutdown()
    ok("run_scenario wires checkpoints, exercises, event capture, and validity gating end to end")


def test_capture_policy_texts_archives_and_skips_for_real_reasons() -> None:
    """capture_policy_texts (E6) had never actually run in a test - only ever
    stubbed out entirely (see test_time_budget_skips_only_corroborating_work).
    Its skip-reason branches are exactly the kind of thing that broke live
    twice already (see the handoff: a decorated link archived four times, and
    a GA client id transmitted to the policy host by fetching the decorated
    URL) - this exercises every skip reason plus the successful archive path
    through the injected `fetch_url` seam, so the real fetcher - and the
    network, even loopback - is never exercised by this suite. The
    tracking-param regression itself is covered directly by
    test_policy_link_selection, against strip_tracking_params."""
    from lib import capture

    policy_text = "This Privacy Policy describes how we collect, use, and share information. " * 10
    assert len(policy_text) >= 200
    origin = "https://policies.example.test"

    routes = {
        f"{origin}/privacy": {
            "status": 200, "ok": True, "content_type": "text/html",
            "text": policy_text, "final_url": f"{origin}/privacy",
        },
        f"{origin}/cookie-policy-login": {
            "status": 200, "ok": True, "content_type": "text/html",
            "text": "Please sign in to continue.", "final_url": f"{origin}/cookie-policy-login",
        },
        f"{origin}/privacy-short": {
            "status": 200, "ok": True, "content_type": "text/html",
            "text": "We use cookies.", "final_url": f"{origin}/privacy-short",
        },
        f"{origin}/privacy-data": {
            "status": 200, "ok": True, "content_type": "application/json",
            "text": "", "final_url": f"{origin}/privacy-data",
        },
        f"{origin}/blocked-privacy": {
            "status": 200, "ok": True, "content_type": "text/html",
            "text": policy_text, "final_url": f"{origin}/blocked-privacy",
        },
        f"{origin}/privacy-not-found": {
            "status": 404, "ok": False, "content_type": "text/html",
            "text": "", "final_url": f"{origin}/privacy-not-found",
        },
    }
    fetch_calls: list[str] = []

    def fake_fetch(url: str) -> dict:
        fetch_calls.append(url)
        if url == f"{origin}/privacy-timeout":
            raise TimeoutError("navigation timeout")
        return dict(routes[url])

    robots_bodies = {f"{origin}/robots.txt": "User-agent: *\nDisallow: /blocked-privacy\n"}

    class _FakeRobotsResponse:
        def __init__(self, body: str) -> None:
            self._body = body.encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

    def fake_urlopen(url, timeout=8.0):
        if url not in robots_bodies:
            raise OSError("no robots.txt at this origin")
        return _FakeRobotsResponse(robots_bodies[url])

    links = [
        {"text": "Privacy Policy", "href": f"{origin}/privacy"},
        {"text": "Cookie Policy", "href": f"{origin}/cookie-policy-login"},
        {"text": "Privacy Notice (short)", "href": f"{origin}/privacy-short"},
        {"text": "Privacy Data", "href": f"{origin}/privacy-data"},
        {"text": "Blocked Privacy Policy", "href": f"{origin}/blocked-privacy"},
        {"text": "Privacy Policy (missing)", "href": f"{origin}/privacy-not-found"},
        {"text": "Privacy Policy (timeout)", "href": f"{origin}/privacy-timeout"},
    ]

    original_urlopen = capture.urlopen
    capture.urlopen = fake_urlopen
    try:
        with tempfile.TemporaryDirectory(prefix="cookie-auditor-policies-") as temp:
            share_dir = Path(temp)
            result = capture.capture_policy_texts(
                None, links, share_dir, timeout_ms=8000, limit=7, fetch_url=fake_fetch,
            )

            assert "error" not in result, result
            assert result["attempted"] == 7, result
            assert result["archived"] == 1, result
            by_url = {r["url"]: r for r in result["records"]}

            archived = by_url[f"{origin}/privacy"]
            assert archived["archived"] is True, archived
            archived_path = Path(archived["path"])
            assert archived_path.exists()
            archived_text = archived_path.read_text(encoding="utf-8")
            assert archived_text.startswith(f"Source URL: {origin}/privacy\n"), archived_text
            assert "This Privacy Policy describes" in archived_text, archived_text
            assert archived["retrieved_at"], archived
            assert f"Retrieved at: {archived['retrieved_at']}\n" in archived_text, archived_text
            # The recorded hash must match what was actually written, not a
            # hand-computed expectation.
            body_text = archived_text.split("-" * 72 + "\n\n", 1)[1]
            assert archived["sha256"] == hashlib.sha256(body_text.encode("utf-8")).hexdigest(), archived

            login = by_url[f"{origin}/cookie-policy-login"]
            assert login["archived"] is False and "login wall" in login["skipped_reason"], login

            short = by_url[f"{origin}/privacy-short"]
            assert short["archived"] is False and "too little text" in short["skipped_reason"], short

            not_text = by_url[f"{origin}/privacy-data"]
            assert not_text["archived"] is False and "not extractable as text" in not_text["skipped_reason"], not_text

            blocked = by_url[f"{origin}/blocked-privacy"]
            assert blocked["archived"] is False, blocked
            assert "robots.txt disallows" in blocked["skipped_reason"], blocked
            assert blocked["robots_note"] == "robots.txt consulted", blocked
            # robots.txt is checked before the fetch seam is ever invoked - a
            # disallowed URL must never reach the fetcher, real or fake.
            assert f"{origin}/blocked-privacy" not in fetch_calls, fetch_calls

            # A non-200 response is recorded as a skip, not a raised error -
            # the run must not fail just because one link 404s.
            not_found = by_url[f"{origin}/privacy-not-found"]
            assert not_found["archived"] is False, not_found
            assert not_found["skipped_reason"] == "fetch returned HTTP 404", not_found

            # A raising fetcher (timeout, DNS failure, etc.) is likewise
            # recorded as a skip rather than propagating out of the scenario.
            timed_out = by_url[f"{origin}/privacy-timeout"]
            assert timed_out["archived"] is False, timed_out
            assert timed_out["skipped_reason"].startswith("fetch failed:"), timed_out
            assert "navigation timeout" in timed_out["skipped_reason"], timed_out

            # Only the one real archive exists on disk - a skip must never
            # leave a stray file behind under any of its reasons.
            archived_files = list((share_dir / "policies").glob("*.txt"))
            assert len(archived_files) == 1, archived_files
    finally:
        capture.urlopen = original_urlopen
    ok("capture_policy_texts archives one real policy and records the six distinct real skip reasons, entirely through an injected fake fetcher")


def test_run_detect_only_reports_and_annotates_a_real_control() -> None:
    """run_detect_only is the documented first step ("Always run the pre-flight
    first" in SKILL.md) and had zero test coverage before this: the CMP
    fingerprint print, the per-kind resolved-control loop, and the annotated-
    screenshot path (which re-draws and re-verifies immediately before the
    shutter, per its own docstring) were only ever checked by hand against a
    live site."""
    import contextlib
    import io
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            body = HUBSPOT_BANNER.encode("utf-8")
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
            executable = discover_browser_executable(None)
            with tempfile.TemporaryDirectory(prefix="cookie-auditor-detect-") as temp:
                screenshot_path = Path(temp) / "detect.png"
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    code = audit_site.run_detect_only(
                        target_url=f"http://127.0.0.1:{port}/",
                        executable=executable,
                        headless=True,
                        timeout_ms=8000,
                        viewport_label="desktop",
                        screenshot_path=screenshot_path,
                    )
                output = buffer.getvalue()

                assert code == 0, output
                assert "Consent platform detected: HubSpot cookie banner" in output, output
                assert "[reject] resolved via: cmp_selector_table" in output, output
                assert "WOULD CLICK: 'Decline'" in output, output
                assert "No audit was performed" in output, output

                assert screenshot_path.exists() and screenshot_path.stat().st_size > 0, screenshot_path
                # The happy path: the overlay survived to the shutter, so the
                # image is captioned as annotated and no fallback note fires.
                assert "Annotated screenshot:" in output, output
                assert "NOTE:" not in output, output
        finally:
            server.shutdown()
    ok("run_detect_only fingerprints a real CMP, resolves every control kind, and writes an annotated screenshot")


# ---------------------------------------------------------------------------
# C - transmission classification and consent mode
# ---------------------------------------------------------------------------

def test_transmission_classification() -> None:
    # Read the same way production does (audit_site.py loads this file's
    # "transmission_patterns" key directly) rather than through a loader.
    vendor_patterns = read_json(SCRIPT_DIR.parent / "references" / "vendor-patterns.json")
    patterns = vendor_patterns["transmission_patterns"]
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


def test_choose_headless_platform_rules() -> None:
    """choose_headless decides whether the whole capture runs visibly or not,
    and had no direct test - only ever exercised incidentally through whatever
    platform happened to run the suite."""
    import argparse

    def args(headless=False, headed=False):
        return argparse.Namespace(headless=headless, headed=headed)

    assert audit_site.choose_headless(args(headless=True, headed=True)) is True, (
        "--headless must win even if --headed was also somehow set"
    )
    assert audit_site.choose_headless(args(headed=True)) is False

    original_platform = sys.platform
    original_display = os.environ.pop("DISPLAY", None)
    original_wayland = os.environ.pop("WAYLAND_DISPLAY", None)
    try:
        sys.platform = "linux"
        assert audit_site.choose_headless(args()) is True, (
            "linux with no DISPLAY/WAYLAND_DISPLAY and neither flag set must default headless"
        )
        os.environ["DISPLAY"] = ":0"
        assert audit_site.choose_headless(args()) is False, "a DISPLAY means a visible X session is available"

        sys.platform = "darwin"
        os.environ.pop("DISPLAY", None)
        assert audit_site.choose_headless(args()) is False, "non-linux platforms default to visible"
    finally:
        sys.platform = original_platform
        if original_display is not None:
            os.environ["DISPLAY"] = original_display
        else:
            os.environ.pop("DISPLAY", None)
        if original_wayland is not None:
            os.environ["WAYLAND_DISPLAY"] = original_wayland
    ok("choose_headless defaults headless only on a DISPLAY-less Linux session, and lets explicit flags win")


def test_launch_browser_sandbox_args_and_error_message() -> None:
    """launch_browser adds the no-sandbox flags only when running as root (a
    common container/CI shape that otherwise refuses to launch Chromium at
    all), and turns a launch failure into an actionable message rather than a
    raw Playwright traceback - neither path had a test."""
    calls: list[dict] = []

    class _RaisingChromium:
        def launch(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("no usable browser found")

    class _StubPlaywrightModule:
        chromium = _RaisingChromium()

    original_geteuid = getattr(os, "geteuid", None)
    try:
        os.geteuid = lambda: 0
        try:
            audit_site.launch_browser(_StubPlaywrightModule(), executable=None, headless=True)
            assert False, "the stub always raises; launch_browser must propagate a failure"
        except RuntimeError as error:
            assert "No launchable Chrome" in str(error), error
            assert "no usable browser found" in str(error), "the original error must be chained in, not swallowed"
        assert calls[-1].get("chromium_sandbox") is False, calls
        assert calls[-1].get("args") == ["--no-sandbox"], calls

        os.geteuid = lambda: 1000
        calls.clear()
        try:
            audit_site.launch_browser(_StubPlaywrightModule(), executable=None, headless=True)
        except RuntimeError:
            pass
        assert "chromium_sandbox" not in calls[-1], (
            f"sandbox must only be disabled for root, not a regular user: {calls[-1]}"
        )

        # With an explicit executable, a launch failure must propagate the
        # original error unchanged rather than being rewritten into the
        # generic "no browser found" message - the user already told us
        # exactly which browser to use.
        calls.clear()
        try:
            audit_site.launch_browser(_StubPlaywrightModule(), executable="/opt/custom/chrome", headless=True)
            assert False
        except RuntimeError as error:
            assert str(error) == "no usable browser found", (
                f"an explicit --browser failure must not be rewritten: {error}"
            )
    finally:
        if original_geteuid is not None:
            os.geteuid = original_geteuid
        else:
            del os.geteuid
    ok("launch_browser scopes --no-sandbox to root and chains the real error into an actionable message")


#: Subscript keys and helpers whose values are wall-clock readings from
#: `utc_now()`. Comparing two of these with an ordering operator is the bug
#: pattern `test_no_wall_clock_ordering_assertions` exists to ban - see its
#: docstring.
_TIMESTAMP_EXPRESSIONS = frozenset({
    "time", "probe_started", "probe_finished", "timestamp", "started_at", "finished_at",
})

#: Opt out of the ban on one `assert`, by putting this marker plus a reason in
#: a comment on any line of that statement. It is deliberately awkward: the
#: point is to make an author state why a clock reading is adequate here,
#: not to make the check easy to silence.
_TIME_ASSERTION_WAIVER = "time-assertion-ok:"


def test_no_wall_clock_ordering_assertions() -> None:
    """No test may assert an ordering by comparing two wall-clock readings.

    `utc_now()` truncates to whole seconds. Anything this suite drives -
    a reload, a settle, a click - finishes well inside one second, so both
    readings routinely land in the same second and a `<=` between them holds
    whichever order they were actually taken in. A guard like that does not
    fail loudly when the ordering it protects is inverted; it fails *rarely*,
    which is worse, because a suite that passes reads as proof.

    This has now cost the project twice: once in the Didomi-adjacent CMP work,
    and again in #7, where `consent_snapshot_after["time"] <= probe_started`
    caught the exact inversion it existed to catch in only 3 of 4 runs. Both
    times the fix was the same - assert on a load-time side effect that names
    *which* load or state a reading came from (see `load_seq` and
    `fixture_reload_marker` in the autosave tests), so no clock resolution can
    blur it. Reach for that first.

    Scans this file with `ast`, not a grep, so the check sees the shape of the
    comparison rather than a substring and cannot be dodged by reformatting.
    """
    def references_a_clock(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Subscript)
                and isinstance(child.slice, ast.Constant)
                and child.slice.value in _TIMESTAMP_EXPRESSIONS
            ):
                return True
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "utc_now":
                return True
        return False

    test_files = sorted((SCRIPT_DIR / "tests").glob("*.py"))
    assert test_files, "no test sources found to scan"

    offences: list[str] = []
    scanned = 0
    for path in test_files:
        source = path.read_text()
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Assert):
                continue
            comparisons = [n for n in ast.walk(node.test) if isinstance(n, ast.Compare)]
            for comparison in comparisons:
                ordering = any(
                    isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in comparison.ops
                )
                if not ordering or not references_a_clock(comparison):
                    continue
                scanned += 1
                # The waiver may sit on the statement's own lines or in the
                # contiguous comment block immediately above it, which is
                # where a reason long enough to be worth reading belongs.
                start = node.lineno - 1
                while start > 0 and lines[start - 1].strip().startswith("#"):
                    start -= 1
                statement = "\n".join(lines[start:(node.end_lineno or node.lineno)])
                if _TIME_ASSERTION_WAIVER in statement:
                    continue
                offences.append(f"{path.name}:{node.lineno}: {ast.unparse(comparison)[:120]}")

    assert not offences, (
        "these assertions order two wall-clock readings, which utc_now()'s whole-second truncation makes "
        "an unreliable guard. Assert on a structural marker that names which load or state the reading "
        f"came from, or waive with a `# {_TIME_ASSERTION_WAIVER} <reason>` comment:\n  "
        + "\n  ".join(offences)
    )
    assert scanned >= 1, (
        "the scanner matched no clock comparisons at all, including the waived one below - it has stopped "
        "recognising the pattern it exists to find"
    )
    ok(f"no test asserts an ordering from wall-clock readings ({len(test_files)} test source(s) scanned)")


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

        # A settings-panel denial with no save control (#6) has exactly one
        # remaining automated verification path: a namespaced consent-storage
        # write. Every entry must carry the namespace, and it is mandatory -
        # not merely helpful - for the CMPs that have no save control at all.
        assert entry.get("consent_storage"), f"{entry['id']} has no consent_storage namespace"
        if not entry.get("save"):
            assert entry.get("consent_storage"), (
                f"{entry['id']} has an empty 'save' list and no consent_storage namespace - a "
                "settings-path denial for it can never be verified."
            )

    ids = [e["id"] for e in table]
    assert len(ids) == len(set(ids)), "CMP ids must be unique"
    ok(f"CMP table integrity: {len(table)} entries, no save/accept or reject/accept collisions, "
       "all carry a consent_storage namespace")


def test_consent_namespace_and_key_matching() -> None:
    """consent_namespace reads the table field; consent_key_matches applies the
    cookie-key-splitting, prefix-rule, and case-insensitivity rules from #6."""
    table = load_cmp_table()
    hubspot = next(e for e in table if e["id"] == "hubspot")
    iubenda = next(e for e in table if e["id"] == "iubenda")

    ns = checks.consent_namespace(hubspot)
    assert ns == ["__hs_cookie_cat_pref", "__hs_do_not_track", "__hs_initial_opt_in"], ns
    assert checks.consent_namespace(None) == []
    assert checks.consent_namespace({}) == []
    assert checks.consent_namespace({"consent_storage": "not-a-list"}) == []

    # Cookie snapshot keys are "{domain}|{name}"; split on the LAST '|' and
    # match the name half.
    assert checks.consent_key_matches(".example.test|__hs_cookie_cat_pref", ns, cookie_key=True) == "__hs_cookie_cat_pref"
    assert checks.consent_key_matches(".example.test|_ga", ns, cookie_key=True) is None
    # A domain-only key with no '|' at all still matches on its whole value.
    assert checks.consent_key_matches("__hs_cookie_cat_pref", ns, cookie_key=False) == "__hs_cookie_cat_pref"

    # A prefix rule ("_iub_cs-") matches only at the start.
    iub_ns = checks.consent_namespace(iubenda)
    assert checks.consent_key_matches("_iub_cs-9f3a", iub_ns, cookie_key=False) == "_iub_cs-"
    assert checks.consent_key_matches("my_iub_cs-x", iub_ns, cookie_key=False) is None

    # Exact rules are case-insensitive.
    assert checks.consent_key_matches("__HS_COOKIE_CAT_PREF", ns, cookie_key=False) == "__hs_cookie_cat_pref"

    ok("consent_namespace reads the CMP table and consent_key_matches applies prefix/exact/case rules")


def test_narrow_consent_diff_ignores_noise_and_catches_namespaced_writes() -> None:
    """The narrow diff must ignore ordinary analytics/session churn - a before/
    after differing only in _ga, an unrelated localStorage key, or cmp_api -
    and must still catch a real namespaced write. Both halves are asserted:
    an implementation that always returned False would pass the noise half
    alone."""
    ns = ["__hs_cookie_cat_pref"]
    before = {
        "cookies": {".example.test|_ga": "h1"},
        "local_storage": {"unrelated_key": "h1"},
        "cmp_api": {"hasTCF": False},
    }
    noisy_after = {
        "cookies": {".example.test|_ga": "h2"},
        "local_storage": {"unrelated_key": "h9", "cmp_api": "h1"},
        "cmp_api": {"hasTCF": True},
    }
    noisy_diff = checks.narrow_consent_diff(before, noisy_after, ns)
    assert noisy_diff["namespaced_state_changed"] is False, noisy_diff
    assert noisy_diff["new_keys"] == [] and noisy_diff["changed_keys"] == [] and noisy_diff["removed_keys"] == [], noisy_diff

    real_after = {
        "cookies": {".example.test|_ga": "h2", ".example.test|__hs_cookie_cat_pref": "h9"},
        "local_storage": {"unrelated_key": "h9"},
        "cmp_api": {"hasTCF": True},
    }
    real_diff = checks.narrow_consent_diff(before, real_after, ns)
    assert real_diff["namespaced_state_changed"] is True, real_diff
    assert real_diff["new_keys"] == [
        {"store": "cookies", "key": ".example.test|__hs_cookie_cat_pref", "matched_rule": "__hs_cookie_cat_pref"}
    ], real_diff

    # An unknown/empty namespace is never "available", regardless of what changed.
    unknown = checks.narrow_consent_diff(before, real_after, [])
    assert unknown["namespace_available"] is False
    assert unknown["namespaced_state_changed"] is False, unknown
    ok("narrow_consent_diff ignores analytics/session/cmp_api noise and still catches a real namespaced write")


def test_classify_autosave_denial_truth_table() -> None:
    """Exercises every row of the #6 acceptance-criteria truth table."""
    disabled_toggle = {"frame_url": "https://example.test/", "index": 0, "label": "Analytics", "state_before": True, "state_after": False}
    examined_only = {"frame_url": "https://example.test/", "index": 0, "label": "Analytics", "state_before": True}
    already_off = {"frame_url": "https://example.test/", "index": 0, "label": "Analytics", "state_before": False}

    def reload_probe(states):
        return {"toggle_states": [{"label": "Analytics", "state": s} for s in states], "banner_visible": True}

    no_write = {"namespace_available": True, "namespaced_state_changed": False}
    write = {"namespace_available": True, "namespaced_state_changed": True}
    unavailable_but_flagged = {"namespace_available": False, "namespaced_state_changed": True}

    # Row 1: >=1 disabled, all optional read back OFF -> verified via reload, regardless of diff.
    r1 = checks.classify_autosave_denial(
        {"examined": [examined_only], "disabled": [disabled_toggle], "unknown": []},
        write, reload_probe([False]),
    )
    assert r1["status"] == checks.AUTOSAVE_VERIFIED_RELOAD and r1["verified"] is True, r1

    # Row 2: >=1 disabled, inconclusive reload, namespaced write -> verified via storage.
    r2 = checks.classify_autosave_denial(
        {"examined": [examined_only], "disabled": [disabled_toggle], "unknown": []},
        write, reload_probe([]),
    )
    assert r2["status"] == checks.AUTOSAVE_VERIFIED_STORAGE and r2["verified"] is True, r2

    # Row 3 (load-bearing): >=1 disabled, read back ON again -> NOT verified even
    # with a namespaced write present. Must beat row 2's storage evidence.
    r3 = checks.classify_autosave_denial(
        {"examined": [examined_only], "disabled": [disabled_toggle], "unknown": []},
        write, reload_probe([True]),
    )
    assert r3["status"] == checks.AUTOSAVE_NO_SAVE_CONTROL and r3["verified"] is False, r3
    assert "operated" in r3["note"] and "mutated" in r3["note"], r3["note"]

    # Row 3 also beats a mix where some toggles read back off and one reads back on.
    r3_mixed = checks.classify_autosave_denial(
        {"examined": [examined_only], "disabled": [disabled_toggle], "unknown": []},
        write, reload_probe([False, True]),
    )
    assert r3_mixed["verified"] is False, r3_mixed

    # Row 4: >=1 disabled, inconclusive reload, no namespaced write -> not verified.
    r4 = checks.classify_autosave_denial(
        {"examined": [examined_only], "disabled": [disabled_toggle], "unknown": []},
        no_write, reload_probe([]),
    )
    assert r4["status"] == checks.AUTOSAVE_NO_SAVE_CONTROL and r4["verified"] is False, r4

    # Row 5: 0 disabled, some examined and already off, namespaced write -> verified via storage.
    r5 = checks.classify_autosave_denial(
        {"examined": [already_off], "disabled": [], "unknown": []},
        write, reload_probe([True]),  # reload result is irrelevant on this branch
    )
    assert r5["status"] == checks.AUTOSAVE_VERIFIED_STORAGE and r5["verified"] is True, r5

    # Row 6: 0 disabled, some examined and already off, no namespaced write -> not verified.
    r6 = checks.classify_autosave_denial(
        {"examined": [already_off], "disabled": [], "unknown": []},
        no_write, reload_probe([False]),
    )
    assert r6["status"] == checks.AUTOSAVE_NO_SAVE_CONTROL and r6["verified"] is False, r6

    # Row 7: none examined at all -> never verified, regardless of anything else.
    r7 = checks.classify_autosave_denial(
        {"examined": [], "disabled": [], "unknown": []},
        write, reload_probe([False]),
    )
    assert r7["status"] == checks.AUTOSAVE_NO_SAVE_CONTROL and r7["verified"] is False, r7

    # A namespace_available:False can never produce a _verified_storage status,
    # even if some buggy caller left namespaced_state_changed True alongside it.
    r_guard = checks.classify_autosave_denial(
        {"examined": [already_off], "disabled": [], "unknown": []},
        unavailable_but_flagged, reload_probe([]),
    )
    assert r_guard["status"] != checks.AUTOSAVE_VERIFIED_STORAGE, r_guard
    assert r_guard["verified"] is False, r_guard

    # Banner absence must never verify on its own: a probe reporting only
    # "banner not visible", with no read-back and no namespaced write.
    banner_only_probe = {"toggle_states": [], "banner_visible": False}
    r_banner = checks.classify_autosave_denial(
        {"examined": [examined_only], "disabled": [disabled_toggle], "unknown": []},
        no_write, banner_only_probe,
    )
    assert r_banner["verified"] is False, r_banner

    ok("classify_autosave_denial implements the #6 truth table, with reload-reversion beating a namespaced write")


def test_repeat_stability() -> None:
    result = checks.compare_repeat_runs([{"a", "b", "c"}, {"a", "b"}, {"a", "b", "d"}])
    assert result["stable"] == ["a", "b"]
    assert result["unstable"] == ["c", "d"]
    assert result["run_count"] == 3
    ok("endpoints seen in only some repeats are marked unstable")


# ---------------------------------------------------------------------------
# B - validity gating
# ---------------------------------------------------------------------------

class _StubPlaywright:
    """Enough of the sync_playwright context manager for main() to run with no browser."""
    def __enter__(self): return self
    def __exit__(self, *exc): return False


class _StubBrowser:
    version = "stub/0.0"
    def close(self): pass


def test_main_orchestrates_bundles_gates_and_exit_codes() -> None:
    """main() is ~150 lines of orchestration that no test touched: bundle
    layout, per-profile metadata, the union of gate signals, and the exit code.
    It was only ever verified by hand against a live site, so a refactor could
    silently change which bundle a report lands in or let a clean desktop run
    mask a broken mobile one."""
    captured_labels: list[str] = []

    def fake_run_all_scenarios(browser, config, private_dir, share_dir, **kwargs):
        captured_labels.append(config.viewport_label)
        # The mobile profile fails its denial; desktop succeeds. A run where
        # both profiles agree could not detect a union bug.
        return synthetic_results(denial_completed=(config.viewport_label != "mobile"))

    originals = {
        name: getattr(audit_site, name)
        for name in ("sync_playwright", "launch_browser", "run_all_scenarios",
                     "resolve_egress_region", "render_pdf_from_html")
    }
    audit_site.sync_playwright = lambda: _StubPlaywright()
    audit_site.launch_browser = lambda *a, **k: _StubBrowser()
    audit_site.run_all_scenarios = fake_run_all_scenarios
    audit_site.resolve_egress_region = lambda *a, **k: {"resolved": False, "region": None}
    audit_site.render_pdf_from_html = lambda *a, **k: {"ok": False, "error": "stubbed"}

    def run(argv: list[str]) -> int:
        original_argv = sys.argv
        sys.argv = ["audit_site.py", *argv]
        try:
            return audit_site.main()
        finally:
            sys.argv = original_argv

    try:
        # --- single profile: the historical flat layout must be preserved ---
        single = Path(tempfile.mkdtemp()) / "single"
        code = run(["--url", "https://example.test", "--out", str(single), "--headless",
                    "--no-zip", "--no-pdf", "--no-geo", "--viewport", "desktop"])
        assert captured_labels == ["desktop"], captured_labels
        assert (single / "audit-report.md").exists(), "single-profile runs must stay flat"
        assert not (single / "desktop").exists(), "a single profile must not create a subdirectory"
        assert code == 0, f"a fully valid run exits 0, got {code}"

        # --- both profiles: one complete bundle each, never merged ---
        captured_labels.clear()
        both = Path(tempfile.mkdtemp()) / "both"
        code = run(["--url", "https://example.test", "--out", str(both), "--headless",
                    "--no-zip", "--no-pdf", "--no-geo", "--viewport", "both"])
        assert captured_labels == ["desktop", "mobile"], captured_labels
        for label in ("desktop", "mobile"):
            assert (both / label / "audit-report.md").exists(), f"{label} needs its own report"
            assert (both / label / "findings.json").exists(), f"{label} needs its own findings"
        assert not (both / "audit-report.md").exists(), (
            "there must be no merged top-level report; a mobile and a desktop finding "
            "must not share one table"
        )
        assert (both / "README.txt").exists() and (both / "manifest.sha256").exists()

        # Each profile records its own conditions, and the fingerprints differ
        # so the two can never be mistaken for repeat runs of the same thing.
        meta = {label: read_json(both / label / "run-metadata.json") for label in ("desktop", "mobile")}
        assert meta["desktop"]["viewport"] == "1440x1000", meta["desktop"]["viewport"]
        assert meta["mobile"]["viewport"] == "412x915", meta["mobile"]["viewport"]
        assert meta["desktop"]["run_fingerprint"] != meta["mobile"]["run_fingerprint"]

        # The mobile denial failed, so the run is INCOMPLETE overall even though
        # desktop was clean, and the offending scenario is named by profile.
        assert code == 4, f"a broken mobile profile must not be masked by a clean desktop one, got {code}"
        mobile_data = read_json(both / "mobile" / "audit-data.json")
        assert mobile_data["run_complete"] is False, mobile_data["run_complete"]
        assert read_json(both / "desktop" / "audit-data.json")["run_complete"] is True

        # --- guard rails that must reject before any capture happens ---
        captured_labels.clear()
        assert run(["--url", "ftp://example.test", "--out", str(Path(tempfile.mkdtemp()) / "x"),
                    "--headless"]) == 2, "a non-http URL must be refused"
        assert run(["--url", "https://user:pw@example.test", "--out", str(Path(tempfile.mkdtemp()) / "y"),
                    "--headless"]) == 2, "credentials in the URL must be refused"
        assert captured_labels == [], "nothing may be captured after a configuration error"

        # A non-empty output directory must not be written over.
        occupied = Path(tempfile.mkdtemp())
        (occupied / "existing.txt").write_text("keep me", encoding="utf-8")
        assert run(["--url", "https://example.test", "--out", str(occupied), "--headless"]) == 2
        assert (occupied / "existing.txt").read_text(encoding="utf-8") == "keep me"
    finally:
        for name, value in originals.items():
            setattr(audit_site, name, value)
    ok("main() lays out bundles per profile, unions gate signals, and refuses unsafe configurations")


def _assert_readme_matches_directory(directory: Path, *, label: str) -> None:
    """Both directions of the README.txt <-> directory-contents claim, against
    one real directory on disk. Forward: every name README.txt lists is
    something that directory actually holds (a stale or misspelled entry).
    Reverse: every top-level entry that directory actually holds (other than
    README.txt itself and the timestamped *.zip, whose presence is already
    checked separately) is named in README.txt (an omission - the defect this
    test exists for: a future output file added to a writer and never added
    to the README template would otherwise go uncaught)."""

    readme = (directory / "README.txt").read_text(encoding="utf-8")
    produced_top_level = {p.name for p in directory.iterdir()}
    # Every "name<spaces>description" line names something a reader would go
    # looking for. A trailing "/" marks a directory; "*.zip" is the one entry
    # whose exact name is only known at run time (host + timestamp).
    named = sorted(set(re.findall(r"^([A-Za-z0-9_.*-]+/?)  +\S", readme, flags=re.MULTILINE)))
    assert len(named) >= 4, f"[{label}] expected README.txt to name the directory's files, found: {named}"

    for name in named:
        if name == "*.zip":
            assert any(p.suffix == ".zip" for p in directory.iterdir()), (
                f"[{label}] README.txt promises a zip archive but the directory does not hold one"
            )
            continue
        assert name.rstrip("/") in produced_top_level, (
            f"[{label}] README.txt names {name!r}, which the directory does not hold. "
            f"Actually holds: {sorted(produced_top_level)}"
        )

    for actual in produced_top_level:
        if actual == "README.txt" or actual.endswith(".zip"):
            continue
        expected = actual + "/" if (directory / actual).is_dir() else actual
        assert expected in named, (
            f"[{label}] directory holds {actual!r}, which README.txt does not name. "
            f"README.txt names: {named}"
        )


def test_readme_txt_lists_only_files_the_run_actually_writes() -> None:
    """The bundle `README.txt` is a reader's map of the evidence: every name it
    lists must be something the run actually wrote, and everything the run
    wrote must be named. A renamed or misspelled entry sends someone looking
    for a file that was never produced; an omitted one (like
    `suppressed-findings.json`) lets a reader miss evidence that matters -
    and an omission would also hide a future output file that a writer
    starts producing without the README template being updated to match, so
    both directions are checked, against real bundles on disk rather than
    eyeballing the template string. Runs both a single-profile bundle (with
    PDF and zip packaging both enabled, unlike the orchestration test above
    which disables them, so those two conditional lines are checked too) and
    a `--viewport both` two-profile bundle, since the two-profile root
    README.txt and the per-profile README.txt are different templates
    (audit_site.py's `bundle_contents` block vs. the two-profile summary)
    that could each independently drift from what main() actually writes."""

    def fake_run_all_scenarios(browser, config, private_dir, share_dir, **kwargs):
        return synthetic_results(denial_completed=True)

    def fake_render_pdf_from_html(html_path, pdf_path, executable=None):
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake\n")
        return {"ok": True}

    originals = {
        name: getattr(audit_site, name)
        for name in ("sync_playwright", "launch_browser", "run_all_scenarios",
                     "resolve_egress_region", "render_pdf_from_html")
    }
    audit_site.sync_playwright = lambda: _StubPlaywright()
    audit_site.launch_browser = lambda *a, **k: _StubBrowser()
    audit_site.run_all_scenarios = fake_run_all_scenarios
    audit_site.resolve_egress_region = lambda *a, **k: {"resolved": False, "region": None}
    audit_site.render_pdf_from_html = fake_render_pdf_from_html

    def run(argv: list[str]) -> int:
        original_argv = sys.argv
        sys.argv = ["audit_site.py", *argv]
        try:
            return audit_site.main()
        finally:
            sys.argv = original_argv

    try:
        out = Path(tempfile.mkdtemp()) / "bundle"
        code = run(["--url", "https://example.test", "--out", str(out), "--headless", "--no-geo"])
        assert code == 0, f"expected a clean run, got exit {code}"
        _assert_readme_matches_directory(out, label="single-profile")

        out_both = Path(tempfile.mkdtemp()) / "bundle-both"
        code = run([
            "--url", "https://example.test", "--out", str(out_both),
            "--headless", "--no-geo", "--viewport", "both",
        ])
        assert code == 0, f"expected a clean --viewport both run, got exit {code}"
        _assert_readme_matches_directory(out_both, label="two-profile root")
        _assert_readme_matches_directory(out_both / "desktop", label="desktop profile")
    finally:
        for name, value in originals.items():
            setattr(audit_site, name, value)
    ok("bundle README.txt names exactly the files the run actually wrote, in both directions, "
       "for single-profile and --viewport both (root and per-profile) bundles")


def test_main_validates_manual_flag_and_wires_detect_only() -> None:
    """--manual has two preconditions main() must enforce before anything runs
    (a visible browser, an interactive terminal) - a scenario that blocks on
    input() with neither would hang or silently continue as if a human had
    declined. --detect-only's dispatch (viewport "both" has no meaning for a
    single-rendering preview, so it previews mobile instead) was also
    untested - only run_detect_only itself was, not main()'s wiring into it."""

    def run(argv: list[str]) -> int:
        original_argv = sys.argv
        sys.argv = ["audit_site.py", *argv]
        try:
            return audit_site.main()
        finally:
            sys.argv = original_argv

    out = Path(tempfile.mkdtemp())
    assert run(["--url", "https://example.test", "--out", str(out), "--manual", "--headless"]) == 2, (
        "--manual with --headless must be refused before any capture"
    )

    class _FakeStdin:
        def isatty(self) -> bool:
            return False

    original_stdin = sys.stdin
    sys.stdin = _FakeStdin()
    try:
        assert run(["--url", "https://example.test", "--out", str(Path(tempfile.mkdtemp())),
                    "--manual", "--headed"]) == 2, "--manual without an interactive terminal must be refused"
    finally:
        sys.stdin = original_stdin

    original_detect = audit_site.run_detect_only
    captured: dict = {}

    def fake_run_detect_only(target_url, executable, headless, timeout_ms, viewport_label, screenshot_path):
        captured.update(target_url=target_url, viewport_label=viewport_label, screenshot_path=screenshot_path)
        return 0

    audit_site.run_detect_only = fake_run_detect_only
    try:
        detect_out = Path(tempfile.mkdtemp())
        code = run(["--url", "https://example.test", "--out", str(detect_out),
                    "--headless", "--detect-only", "--viewport", "both"])
        assert code == 0, code
        assert captured["viewport_label"] == "mobile", (
            f"--viewport both has no meaning for a one-rendering preview; must fall back to mobile: {captured}"
        )
        assert "mobile" in captured["screenshot_path"].name, captured["screenshot_path"]

        # A bogus --browser must be refused before run_detect_only is even reached.
        captured.clear()
        code = run(["--url", "https://example.test", "--out", str(Path(tempfile.mkdtemp())),
                    "--headless", "--detect-only", "--browser", "/nonexistent/definitely-not-a-browser"])
        assert code == 2, code
        assert captured == {}, "run_detect_only must not be reached when the browser path is invalid"
    finally:
        audit_site.run_detect_only = original_detect
    ok("main() refuses --manual without a visible, interactive terminal and wires --detect-only correctly")


def test_main_handles_fatal_errors_and_writes_real_artifacts() -> None:
    """Two things main()'s happy-path tests couldn't reach: a scenario runner
    that raises (KeyboardInterrupt must exit 130 without a traceback dumped to
    the user; anything else must exit 3 and leave a fatal-error.txt behind
    rather than losing whatever partial evidence exists), and the real
    (non-stubbed) zip and PDF-failure-message paths, which every other test
    skips via --no-zip/--no-pdf for speed."""
    originals = {
        name: getattr(audit_site, name)
        for name in ("sync_playwright", "launch_browser", "run_all_scenarios",
                     "resolve_egress_region", "render_pdf_from_html")
    }
    audit_site.sync_playwright = lambda: _StubPlaywright()
    audit_site.launch_browser = lambda *a, **k: _StubBrowser()
    audit_site.resolve_egress_region = lambda *a, **k: {"resolved": False, "region": None}
    audit_site.render_pdf_from_html = lambda *a, **k: {"ok": False, "error": "stubbed"}

    def run(argv: list[str]) -> int:
        original_argv = sys.argv
        sys.argv = ["audit_site.py", *argv]
        try:
            return audit_site.main()
        finally:
            sys.argv = original_argv

    try:
        # --- a real zip and the PDF-failure message, neither skipped here ---
        real_out = Path(tempfile.mkdtemp()) / "real"
        audit_site.run_all_scenarios = lambda *a, **k: synthetic_results(denial_completed=True)
        code = run(["--url", "https://example.test", "--out", str(real_out), "--headless", "--no-geo"])
        assert code == 0, code
        zips = list(real_out.glob("*.zip"))
        assert len(zips) == 1, f"a real zip archive must be written when --no-zip is not passed: {zips}"
        assert zips[0].stat().st_size > 0, zips[0]

        # --- --submit-forms prints its side-effect warning, and
        # --assert-no-preconsent-tracking's FAILED block prints against the
        # synthetic baseline's real tracking request - both untested before ---
        import contextlib
        import io

        buffer_out, buffer_err = io.StringIO(), io.StringIO()
        gated_out = Path(tempfile.mkdtemp()) / "gated"
        with contextlib.redirect_stdout(buffer_out), contextlib.redirect_stderr(buffer_err):
            code = run(["--url", "https://example.test", "--out", str(gated_out), "--headless", "--no-geo",
                        "--no-zip", "--no-pdf", "--submit-forms", "--assert-no-preconsent-tracking"])
        assert code == 5, (code, buffer_err.getvalue())
        assert "*** --submit-forms is enabled ***" in buffer_err.getvalue(), buffer_err.getvalue()
        assert "--assert-no-preconsent-tracking FAILED" in buffer_err.getvalue(), buffer_err.getvalue()
        assert "google-analytics.com/g/collect" in buffer_err.getvalue(), buffer_err.getvalue()

        # --- a bogus --browser must be refused in the main (non-detect-only)
        # flow too, before any capture is attempted ---
        code = run(["--url", "https://example.test", "--out", str(Path(tempfile.mkdtemp())), "--headless",
                    "--browser", "/nonexistent/definitely-not-a-browser"])
        assert code == 2, code

        # --- KeyboardInterrupt must exit 130, not propagate as a crash ---
        def raise_keyboard_interrupt(*a, **k):
            raise KeyboardInterrupt()

        audit_site.run_all_scenarios = raise_keyboard_interrupt
        interrupted_out = Path(tempfile.mkdtemp()) / "interrupted"
        code = run(["--url", "https://example.test", "--out", str(interrupted_out), "--headless", "--no-geo"])
        assert code == 130, code

        # --- any other exception must exit 3 and preserve a diagnosis trail ---
        def raise_value_error(*a, **k):
            raise ValueError("synthetic capture failure")

        audit_site.run_all_scenarios = raise_value_error
        fatal_out = Path(tempfile.mkdtemp()) / "fatal"
        code = run(["--url", "https://example.test", "--out", str(fatal_out), "--headless", "--no-geo"])
        assert code == 3, code
        fatal_text = (fatal_out / "fatal-error.txt").read_text(encoding="utf-8")
        assert "ValueError" in fatal_text and "synthetic capture failure" in fatal_text, fatal_text
    finally:
        for name, value in originals.items():
            setattr(audit_site, name, value)
    ok("main() exits 130 on interrupt, exits 3 with a fatal-error.txt on any other failure, and writes a real zip")


def test_redact_storage_state_does_not_leak_or_mutate() -> None:
    """redact_storage_state produces what goes into evidence-shareable, so an
    under-redaction here leaks identifiers to anyone the bundle is sent to. It
    must also leave its input untouched: mutating in place would redact the RAW
    private evidence too, destroying the thing the bundle exists to preserve."""
    state = {
        "cookies": [{"name": "sid", "value": "super-secret-session", "domain": "a.test", "path": "/"}],
        "origins": [{
            "origin": "https://a.test",
            "localStorage": [
                {"name": "consent", "value": "granted"},
                {"name": "ga_client", "value": "1234567890.1234567890"},
            ],
            "indexedDB": [{"name": "db", "stores": [{"name": "s", "records": [{"k": "pii@example.com"}, {"k": "x"}]}]}],
        }],
    }
    import copy
    original = copy.deepcopy(state)
    redacted = redact_storage_state(state)

    assert state == original, "the caller's state must not be mutated; raw evidence depends on it"

    serialized = json.dumps(redacted)
    for secret in ("super-secret-session", "1234567890.1234567890", "pii@example.com", "granted"):
        assert secret not in serialized, f"{secret!r} survived redaction into the shareable bundle"

    stored = redacted["origins"][0]["localStorage"]
    for item in stored:
        assert item["value"].startswith("[REDACTED len="), item
    # The key names survive: which keys exist is the evidence, their contents are not.
    assert {i["name"] for i in stored} == {"consent", "ga_client"}
    assert redacted["origins"][0]["indexedDB"][0]["stores"][0]["records"] == "[REDACTED 2 RECORDS]"

    # A same-length value must still be distinguishable, or a reviewer cannot
    # tell a changed preference from an unchanged one in the redacted view.
    a = redacted_value("AAAA")
    b = redacted_value("ZZZZ")
    assert a != b, "redaction must preserve a content hash, not just a length"
    assert "len=4" in a and "len=4" in b
    ok("storage redaction leaks nothing into the shareable bundle and never mutates the raw state")


def test_registrable_domain_and_third_party_edges() -> None:
    """Third-party classification rests on this, and 'third party' drives most
    findings. A multi-label suffix handled wrong makes a first-party subdomain
    look like a third-party recipient, or the reverse."""
    assert registrable_domain("www.example.com") == "example.com"
    assert registrable_domain("example.com") == "example.com"
    assert registrable_domain("a.b.c.example.com") == "example.com"
    # Multi-label public suffixes: .co.uk is not a registrable domain on its own.
    assert registrable_domain("shop.example.co.uk") == "example.co.uk"
    assert registrable_domain("example.co.uk") == "example.co.uk"
    # Degenerate inputs must not raise or silently produce a bogus domain.
    assert registrable_domain(None) == ""
    assert registrable_domain("") == ""
    assert registrable_domain("localhost") == "localhost"
    assert registrable_domain("127.0.0.1") == "127.0.0.1"
    assert registrable_domain("EXAMPLE.COM.") == "example.com", "trailing dot and case must normalise"

    assert same_site("www.example.com", "cdn.example.com") is True
    assert same_site("example.com", "example.co.uk") is False
    assert same_site("example.com", None) is False
    ok("registrable-domain derivation handles multi-label suffixes, IPs, and degenerate hosts")


def test_hash_manifest_covers_the_bundle() -> None:
    """The report tells the reader to verify the bundle against manifest.sha256
    before relying on it, so the manifest must actually cover the files and the
    hashes must be real."""
    root = Path(tempfile.mkdtemp())
    (root / "sub").mkdir()
    (root / "audit-report.md").write_text("report body", encoding="utf-8")
    (root / "sub" / "evidence.json").write_text('{"a": 1}', encoding="utf-8")
    create_hash_manifest(root)

    manifest = (root / "manifest.sha256").read_text(encoding="utf-8")
    assert "audit-report.md" in manifest, manifest
    assert "sub/evidence.json" in manifest, manifest
    # The manifest must not claim to hash itself, which can never verify.
    assert "manifest.sha256" not in manifest.replace("manifest.sha256\n", ""), manifest

    expected = hashlib.sha256(b"report body").hexdigest()
    assert expected in manifest, "the recorded digest must be the file's real sha256"

    # A tampered file must no longer match its recorded digest.
    (root / "audit-report.md").write_text("tampered", encoding="utf-8")
    assert sha256_file(root / "audit-report.md") != expected
    ok("the hash manifest covers the bundle's files with real, tamper-detecting digests")


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
    assert checks.endpoint_key("https://cdn.example.com/tag.js?cb=123") == "cdn.example.com/tag.js"
    assert checks.endpoint_key("https://example.com") == "example.com"
    assert checks.endpoint_key("https://example.com/") == "example.com/"

    # The query string is excluded on purpose: cache busters and per-request
    # identifiers would make every run look entirely different from every other.
    assert checks.endpoint_key("https://a.test/p?x=1") == checks.endpoint_key("https://a.test/p?x=2")

    # Not network endpoints, and must not appear in either answer.
    for url in ("data:text/html,<p>hi", "about:blank", "blob:https://a.test/abc", ""):
        assert checks.endpoint_key(url) is None, url

    # The capture-side helper and the compare_runs-side helper must both go
    # through the same definition and land on identical keys for the same
    # requests - the drift this test guards against was exactly this pair
    # disagreeing at the edges.
    scenario = {"events": {"requests": [
        {"url": "https://a.test/one"},
        {"url": "https://a.test/one?cb=9"},
        {"url": "data:text/html,x"},
        {"url": "https://b.test/two"},
        {"url": "https://example.test/page"},
    ]}}
    from lib import capture
    import compare_runs
    expected = {"a.test/one", "b.test/two", "example.test/page"}
    # First-party endpoints (example.test is the audited site itself) are
    # counted on purpose, not filtered out - both helpers answer "which
    # endpoints were contacted", not "which third parties were contacted".
    assert capture._endpoint_set(scenario) == expected
    bundle = {
        "metadata": {"target_url": "https://example.test"},
        "scenario_results": {"only": scenario},
    }
    assert set(compare_runs._endpoints(bundle)) == expected
    ok("endpoint identity has one definition, shared by the stability check and the run diff, and counts first-party endpoints too")


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


def test_compare_runs_main_writes_outputs_and_never_touches_inputs() -> None:
    """compare_runs.main was untested end to end - the same gap audit_site.main
    had. Its docstring promises "Neither input bundle is modified", which is the
    whole basis for re-running it against archived evidence, so that promise
    needs a test rather than a comment."""
    import compare_runs

    def bundle(root: Path, findings: list[dict], fingerprint: str = "abc123", complete: bool = True) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        write_json(root / "audit-data.json", {
            "run_fingerprint": fingerprint,
            "overall_status": "Review required",
            "run_complete": complete,
            "metadata": {"target_url": "https://example.test", "profile": "thorough", "tool_version": "2.0.0"},
            "findings": findings,
            "scenario_results": {"baseline": {"events": {"requests": [{"url": "https://a.test/tag.js"}]}}},
        })
        return root

    workspace = Path(tempfile.mkdtemp())
    before = bundle(workspace / "before", [{"id": "F-A", "title": "A", "severity": "high"}])
    after = bundle(workspace / "after", [])
    out = workspace / "out"

    before_snapshot = (before / "audit-data.json").read_bytes()
    after_snapshot = (after / "audit-data.json").read_bytes()
    before_listing = sorted(p.name for p in before.iterdir())

    def run(argv: list[str]) -> int:
        original = sys.argv
        sys.argv = ["compare_runs.py", *argv]
        try:
            return compare_runs.main()
        finally:
            sys.argv = original

    original_pdf = compare_runs.render_pdf_from_html
    compare_runs.render_pdf_from_html = lambda *a, **k: {"ok": False, "error": "stubbed"}
    try:
        code = run(["--before", str(before), "--after", str(after), "--out", str(out), "--no-pdf"])
        assert code == 0, code
        for name in ("comparison-report.md", "comparison-report.html", "comparison-data.json"):
            assert (out / name).is_file(), f"{name} was not written"

        delta = read_json(out / "comparison-data.json")
        assert [f["id"] for f in delta["findings"]["resolved"]] == ["F-A"], delta["findings"]

        # The documented promise.
        assert (before / "audit-data.json").read_bytes() == before_snapshot, "the earlier bundle was modified"
        assert (after / "audit-data.json").read_bytes() == after_snapshot, "the later bundle was modified"
        assert sorted(p.name for p in before.iterdir()) == before_listing, (
            "nothing may be written into an input bundle"
        )

        # With no --out, the comparison lands in the later bundle. That writes to
        # `after`, so it is checked after the untouched-inputs assertions above.
        assert run(["--before", str(before), "--after", str(after), "--no-pdf"]) == 0
        assert (after / "comparison-report.md").is_file(), "default output goes beside the later bundle"

        # A directory that is not a bundle must be refused, not half-processed.
        not_a_bundle = workspace / "empty"
        not_a_bundle.mkdir()
        assert run(["--before", str(before), "--after", str(not_a_bundle), "--no-pdf"]) == 2
        assert run(["--before", str(workspace / "missing"), "--after", str(after), "--no-pdf"]) == 2

        # An incomplete run must still compare, but the caller has to be able to
        # see that an "absent" finding may simply never have been tested.
        incomplete = bundle(workspace / "incomplete", [], fingerprint="zzz", complete=False)
        assert run(["--before", str(before), "--after", str(incomplete),
                    "--out", str(workspace / "out2"), "--no-pdf"]) == 0
        delta2 = read_json(workspace / "out2" / "comparison-data.json")
        assert delta2["after_complete"] is False, delta2
        assert delta2["fingerprints_match"] is False, delta2
        report = (workspace / "out2" / "comparison-report.md").read_text(encoding="utf-8")
        assert "Run conditions differ" in report, "a fingerprint mismatch must be visible in the report"
    finally:
        compare_runs.render_pdf_from_html = original_pdf
    ok("compare_runs.main writes its three outputs, refuses non-bundles, and never modifies its inputs")


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


# ---------------------------------------------------------------------------
# Viewport scenario keys, planning, and finding collapse (#10)
# ---------------------------------------------------------------------------

def test_scenario_key_and_parsing() -> None:
    assert checks.scenario_key("denial") == "denial"
    assert checks.scenario_key("denial", "desktop") == "denial"
    assert checks.scenario_key("denial", "mobile") == "denial@mobile"
    assert checks.parse_scenario_key("denial") == ("denial", "desktop")
    assert checks.parse_scenario_key("denial@mobile") == ("denial", "mobile")
    # The collision guard: '-' already appears in real scenario names, which
    # is exactly why '@' and not '-' is the separator.
    assert checks.parse_scenario_key("baseline-repeat-1") == ("baseline-repeat-1", "desktop")
    assert checks.scenario_dir_name("denial@mobile") == "denial-mobile"
    assert checks.scenario_dir_name("denial") == "denial"
    ok("scenario_key/parse_scenario_key/scenario_dir_name round-trip and keep desktop bare")


def test_plan_scenarios_desktop_only_matches_today() -> None:
    plan = checks.plan_scenarios(
        include_gpc=True, include_accept=True, baseline_repeats=2,
        include_persistence=True, viewport_labels=["desktop"],
    )
    keys = [entry["key"] for entry in plan]
    assert keys == [
        "baseline", "denial", "gpc", "accept",
        "baseline-repeat-1", "baseline-repeat-2", "persistence",
    ], keys
    assert not any("@" in key for key in keys), "a desktop-only plan must never contain the viewport separator"

    # Every field must mirror the real run_scenario_with_retry calls in
    # capture.py exactly - a mismatch here means the plan would change
    # behaviour, not just describe it, once a caller wires it in.
    by_key = {entry["key"]: entry for entry in plan}
    expected = {
        "baseline": {"action": "none", "gpc": False, "pages": 0, "run_exercises": False, "storage_state_from": None},
        "denial": {"action": "deny", "gpc": False, "pages": None, "run_exercises": True, "storage_state_from": None},
        "gpc": {"action": "none", "gpc": True, "pages": None, "run_exercises": True, "storage_state_from": None},
        "accept": {"action": "accept", "gpc": False, "pages": None, "run_exercises": True, "storage_state_from": None},
        "baseline-repeat-1": {"action": "none", "gpc": False, "pages": 0, "run_exercises": False, "storage_state_from": None},
        "baseline-repeat-2": {"action": "none", "gpc": False, "pages": 0, "run_exercises": False, "storage_state_from": None},
        "persistence": {"action": "none", "gpc": False, "pages": 0, "run_exercises": False, "storage_state_from": "denial"},
    }
    for key, fields in expected.items():
        entry = by_key[key]
        for field, value in fields.items():
            assert entry[field] == value, f"{key}.{field}: expected {value!r}, got {entry[field]!r}"
        assert entry["viewport_label"] == "desktop"

    # Disabling the optional steps drops exactly those keys and nothing else.
    minimal = checks.plan_scenarios(
        include_gpc=False, include_accept=False, baseline_repeats=0,
        include_persistence=False, viewport_labels=["desktop"],
    )
    assert [entry["key"] for entry in minimal] == ["baseline", "denial"]
    ok("plan_scenarios(desktop-only) reproduces today's exact scenario sequence and names")


def test_plan_scenarios_multi_viewport() -> None:
    plan = checks.plan_scenarios(
        include_gpc=True, include_accept=True, baseline_repeats=2,
        include_persistence=True, viewport_labels=["desktop", "mobile"],
    )
    keys = [entry["key"] for entry in plan]
    desktop_block = ["baseline", "denial", "gpc", "accept", "baseline-repeat-1", "baseline-repeat-2", "persistence"]
    assert keys[: len(desktop_block)] == desktop_block, keys
    assert "denial@mobile" in keys
    assert "persistence@mobile" in keys
    assert not any(key.startswith("baseline-repeat") and "@" in key for key in keys), (
        "baseline repeats must stay desktop-only"
    )
    mobile_entries = {e["key"]: e for e in plan if e["viewport_label"] == "mobile"}
    assert mobile_entries["denial@mobile"]["base"] == "denial"

    # Desktop-first is an invariant the code enforces, not an accident of
    # caller ordering: a caller-supplied ["mobile", "desktop"] must still
    # come out desktop-first, matching the plan above key-for-key.
    reordered = checks.plan_scenarios(
        include_gpc=True, include_accept=True, baseline_repeats=2,
        include_persistence=True, viewport_labels=["mobile", "desktop"],
    )
    assert [entry["key"] for entry in reordered] == keys, [entry["key"] for entry in reordered]

    # Duplicate viewport labels must not produce colliding scenario keys.
    deduped = checks.plan_scenarios(
        include_gpc=True, include_accept=True, baseline_repeats=2,
        include_persistence=True, viewport_labels=["mobile", "mobile"],
    )
    deduped_keys = [entry["key"] for entry in deduped]
    assert deduped_keys.count("denial@mobile") == 1, deduped_keys
    assert deduped_keys.count("persistence@mobile") == 1, deduped_keys

    ok("plan_scenarios([desktop, mobile]) runs desktop first and adds @mobile scenarios without touching repeats")
    ok("plan_scenarios normalises viewport_labels: desktop is hoisted first and duplicates are dropped")


def _viewport_test_finding(**overrides: Any) -> dict[str, Any]:
    finding = {
        "id": "F-DENIAL-EXAMPLE",
        "check_type": "denial-example",
        "title": "Example finding",
        "severity": "critical",
        "certainty": "high",
        "observation": "Something was observed.",
        "strict_us_composite_baseline": "Non-compliant.",
        "potential_legal_relevance": "Relevant.",
        "applicability_needed": None,
        "evidence": [],
        "all_evidence": [],
        "recommendation": "Fix it.",
        "depends_on_scenarios": ["denial"],
        "evidence_strength": "beacon_observed",
        "evidence_strength_label": checks.STRENGTH_LABEL["beacon_observed"],
        "evidence_strength_caveat": checks.STRENGTH_CAVEAT["beacon_observed"],
    }
    finding.update(overrides)
    return finding


def test_collapse_viewport_findings() -> None:
    desktop_finding = _viewport_test_finding(id="F-DENIAL-DESKTOP")
    mobile_finding = _viewport_test_finding(id="F-DENIAL-MOBILE", depends_on_scenarios=["denial@mobile"])

    collapsed = checks.collapse_viewport_findings([desktop_finding, mobile_finding])
    assert len(collapsed) == 1, "identical findings differing only by viewport must merge to one"
    merged = collapsed[0]
    assert merged["id"] == "F-DENIAL-DESKTOP", "the merged finding keeps the desktop id"
    assert merged["observed_viewports"] == ["desktop", "mobile"]
    assert merged["also_observed_in_scenarios"] == ["denial@mobile"]
    assert merged["depends_on_scenarios"] == ["denial"], "depends_on_scenarios must stay desktop-only after collapse"

    # Divergent severity is a real finding about mobile, not noise to merge away.
    desktop_critical = _viewport_test_finding(id="F-SEV-DESKTOP", severity="critical")
    mobile_moderate = _viewport_test_finding(
        id="F-SEV-MOBILE", severity="moderate", depends_on_scenarios=["denial@mobile"],
    )
    not_collapsed = checks.collapse_viewport_findings([desktop_critical, mobile_moderate])
    assert len(not_collapsed) == 2, "findings differing in severity must not be collapsed"

    # Same for evidence_strength.
    desktop_beacon = _viewport_test_finding(id="F-STR-DESKTOP", evidence_strength="beacon_observed")
    mobile_identifier = _viewport_test_finding(
        id="F-STR-MOBILE", evidence_strength="identifier_transmitted", depends_on_scenarios=["denial@mobile"],
    )
    not_collapsed_strength = checks.collapse_viewport_findings([desktop_beacon, mobile_identifier])
    assert len(not_collapsed_strength) == 2, "findings differing in evidence_strength must not be collapsed"

    # A mobile-only finding, with no desktop counterpart, passes through untouched.
    mobile_only = _viewport_test_finding(id="F-MOBILE-ONLY", depends_on_scenarios=["gpc@mobile"])
    passthrough = checks.collapse_viewport_findings([desktop_finding, mobile_only])
    assert len(passthrough) == 2
    kept = next(f for f in passthrough if f["id"] == "F-MOBILE-ONLY")
    assert kept["depends_on_scenarios"] == ["gpc@mobile"], "a mobile-only finding keeps its @mobile dependency intact"

    # Collapse must preserve input order, not push non-desktop findings to
    # the back: generate_findings sorts by (severity, id) over the order
    # collapse hands back, so a mobile-only high-severity finding placed
    # before a lower-severity desktop finding must still precede it.
    mobile_high = _viewport_test_finding(
        id="F-ORDER-MOBILE", severity="high", depends_on_scenarios=["gpc@mobile"],
    )
    desktop_low = _viewport_test_finding(id="F-ORDER-DESKTOP", severity="low")
    ordered = checks.collapse_viewport_findings([mobile_high, desktop_low])
    assert [f["id"] for f in ordered] == ["F-ORDER-MOBILE", "F-ORDER-DESKTOP"], (
        "collapse_viewport_findings must preserve input order, not append non-desktop findings at the end"
    )
    ok("collapse_viewport_findings merges identical cross-viewport findings and preserves real divergence")


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
    test_choose_headless_platform_rules()
    test_launch_browser_sandbox_args_and_error_message()
    test_cmp_table_integrity()
    test_no_wall_clock_ordering_assertions()
    test_consent_namespace_and_key_matching()
    test_narrow_consent_diff_ignores_noise_and_catches_namespaced_writes()
    test_classify_autosave_denial_truth_table()
    test_repeat_stability()
    test_main_orchestrates_bundles_gates_and_exit_codes()
    test_readme_txt_lists_only_files_the_run_actually_writes()
    test_main_validates_manual_flag_and_wires_detect_only()
    test_main_handles_fatal_errors_and_writes_real_artifacts()
    test_redact_storage_state_does_not_leak_or_mutate()
    test_registrable_domain_and_third_party_edges()
    test_hash_manifest_covers_the_bundle()
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
    test_compare_runs_main_writes_outputs_and_never_touches_inputs()
    test_scenario_failure_classification()
    test_retry_recovers_from_transient_navigation_failure()
    test_retry_gives_up_after_second_transient_failure()
    test_retry_never_fires_for_a_failed_consent_interaction()
    test_robots_allows_respects_disallow()
    test_capture_policy_texts_archives_and_skips_for_real_reasons()
    test_collect_consent_mode_extracts_signals_from_request_log()
    test_scenario_key_and_parsing()
    test_plan_scenarios_desktop_only_matches_today()
    test_plan_scenarios_multi_viewport()
    test_collapse_viewport_findings()

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
            test_settings_path_autosave_verified_by_reload(page)
            test_settings_path_autosave_reload_reverts_stays_unverified(page)
            test_settings_path_autosave_verified_by_storage_write(page)
            test_probe_autosave_reload_ordering_and_phase_tagging(page)
            test_execute_denial_wires_phase_ref_into_autosave_probe(page)
            test_manual_precedence_over_autosave_path(page)
            test_manual_eof_with_operated_toggles_falls_back_to_autosave_classification(page)
            test_settings_path_no_toggles_still_reports_manual_required(page)
            test_tab_order_direction(page)
            test_tab_order_unreachable_control(page)
            test_tab_order_reaches_iframe_hosted_controls(page)
            test_symmetry_early_exit_survives_new_fields(page)
            test_focus_visibility_detection(page)
            test_measure_tab_order_distinguishes_cap_from_unreachable(page)
            test_execute_denial_measures_focus_visibility_per_control(page)
            test_measure_tab_order_bounded(page)
            test_onetrust_shape_uses_the_second_layer_reject(page)
            test_usercentrics_shape_resolves_inside_a_shadow_root(page)
            test_sourcepoint_shape_resolves_inside_an_iframe(page)
            test_didomi_shape_resolves_and_save_stays_specific_to_settings(page)
            test_axeptio_shape_accept_fallback_no_longer_collides_with_dismiss(page)
            test_cookiebot_shape_settings_never_resolves_to_the_category_checkbox(page)
            test_termly_shape_settings_resolves_via_the_real_attribute(page)
            test_osano_shape_completes_via_settings_toggles_and_save(page)
            test_cookieyes_shape_scopes_to_the_visible_layer(page)
            test_trustarc_shape_resolves_accept_and_reject_directly(page)
            test_iubenda_shape_reject_uses_the_continue_without_accepting_control(page)
            test_complianz_shape_settings_resolves_via_the_real_view_preferences_button(page)
            test_safe_internal_links_refuses_dangerous_and_offsite(page)
            test_annotate_controls_marks_resolved_controls(page)
            test_annotation_labels_are_painted_above_every_outline(page)
            test_mobile_emulation_reaches_the_page(page)
            test_form_exercise_does_not_submit(page)
            test_form_submission_never_touches_an_unsafe_form(page)
            test_capture_checkpoint_writes_state_and_screenshots(page)
            test_dwell_and_nudge_scrolls_when_thorough(page)
            test_dwell_and_nudge_skips_scrolling_when_not_thorough(page)
            test_exercise_search_fills_and_submits(page)
            test_exercise_search_no_input_present(page)
            test_assert_clean_context_detects_dirty_state(page)
            test_run_scenario_end_to_end(browser)
        finally:
            browser.close()

    # run_detect_only launches its own sync_playwright() context internally,
    # which cannot nest inside the one used for the browser-backed checks
    # above - Playwright's sync API raises "using Playwright Sync API inside
    # the asyncio loop" if attempted from within an already-active one.
    test_run_detect_only_reports_and_annotates_a_real_control()

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

    test_function_count = sum(
        1 for name, value in globals().items() if name.startswith("test_") and callable(value)
    )
    print(
        f"\nAll {len(PASSED)} checks passed across {test_function_count} cookie-banner-auditor "
        "smoke test functions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
