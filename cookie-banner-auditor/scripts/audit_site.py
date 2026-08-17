#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import sys
import traceback
from pathlib import Path
from urllib.parse import urlsplit

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "Playwright is not installed. Run:\n"
        "  python -m pip install -r requirements.txt\n"
        "If no Chrome/Edge/Chromium browser is installed, also run:\n"
        "  python -m playwright install chromium",
        file=sys.stderr,
    )
    raise SystemExit(2)

from lib.analysis import analyze_and_write
from lib.capture import (
    ScenarioConfig,
    fingerprint_cmp,
    find_control,
    load_cmp_table,
    load_transmission_patterns,
    render_pdf_from_html,
    resolve_egress_region,
    run_all_scenarios,
)
from lib.util import (
    build_zip_bundle,
    create_hash_manifest,
    discover_browser_executable,
    ensure_dir,
    host_from_url,
    run_fingerprint,
    slugify,
    timestamp_slug,
    utc_now,
    write_json,
    write_text,
)

VERSION = "2.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture and analyze cookie-banner, cookie, storage, network, denial, and GPC behavior in isolated browser contexts."
    )
    parser.add_argument("--url", required=True, help="Public http(s) URL to audit")
    parser.add_argument("--out", help="Output directory. Defaults to ./cookie-audit-<host>-<timestamp>")
    parser.add_argument("--pages", type=int, default=2, help="Safe same-origin links to visit after denial/GPC (default: 2; max: 5)")
    parser.add_argument("--wait-ms", type=int, default=5000, help="Wait after loads and actions for delayed tags (default: 5000)")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Navigation and action timeout (default: 30000)")
    view = parser.add_mutually_exclusive_group()
    view.add_argument("--headed", action="store_true", help="Show the instrumented browser")
    view.add_argument("--headless", action="store_true", help="Run without a visible browser")
    parser.add_argument("--manual", action="store_true", help="Pause for a human denial click if automatic denial is not reliable; use with --headed")
    parser.add_argument("--no-gpc", action="store_true", help="Skip the GPC scenario")
    parser.add_argument("--accept-control", action="store_true", help="Also run a separate accept-all control scenario")
    parser.add_argument("--browser", help="Path to Chrome, Edge, or Chromium executable")
    parser.add_argument("--proxy", help="Optional proxy server, e.g. http://127.0.0.1:8080")
    parser.add_argument("--location-label", help="Human-readable egress/region label for the report, e.g. California VPN")
    parser.add_argument("--locale", default="en-US", help="Browser locale (default: en-US)")
    parser.add_argument("--timezone", help="IANA timezone, e.g. America/Los_Angeles")
    parser.add_argument("--user-agent", help="Optional user-agent override")
    parser.add_argument("--ignore-https-errors", action="store_true", help="Allow invalid TLS certificates; report this exception")

    thoroughness = parser.add_mutually_exclusive_group()
    thoroughness.add_argument("--quick", action="store_true", help="Fast profile: no dwell, scroll, form, or search exercises, no baseline repeats (~4 min)")
    thoroughness.add_argument("--thorough", action="store_true", help="Default. Dwell, scroll, form-fill, on-site search, and baseline repeats (~15 min)")
    parser.add_argument("--dwell-ms", type=int, default=15000, help="Dwell time per page in the thorough profile (default: 15000)")
    parser.add_argument("--repeat-baseline", type=int, default=2, help="Extra baseline runs used to detect unstable tags (default: 2; 0 disables)")
    parser.add_argument("--submit-forms", action="store_true",
                        help="Actually SUBMIT a form after filling it. Creates real records in the site's CRM and may trigger notification workflows. Off by default.")
    parser.add_argument("--no-forms", action="store_true", help="Skip the form-fill exercise entirely")
    parser.add_argument("--no-search", action="store_true", help="Skip the on-site search exercise")
    parser.add_argument("--no-persistence", action="store_true", help="Skip the fresh-context preference-persistence check")
    parser.add_argument("--no-geo", action="store_true", help="Do not resolve the public egress region")
    parser.add_argument("--detect-only", action="store_true",
                        help="Load the page, report the detected consent platform and every candidate control, then exit without auditing")
    parser.add_argument("--zip-shareable-only", action="store_true", help="Build the archive without evidence-private/ (redacted evidence only)")
    parser.add_argument("--no-zip", action="store_true", help="Skip building the archive")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF rendering")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser.parse_args()


def run_detect_only(target_url: str, executable: str | None, headless: bool, timeout_ms: int) -> int:
    """Pre-flight check: what would the scanner click, and why?

    Cheap to run and answers the question that matters before committing to a
    full audit - whether the consent controls are reachable at all.
    """
    with sync_playwright() as playwright:
        launch_options: dict = {"headless": headless}
        if executable:
            launch_options["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_options)
        try:
            page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            table = load_cmp_table()
            match = fingerprint_cmp(page, table)
            print(f"\nTarget: {target_url}")
            print(f"CMP table entries loaded: {len(table)}")
            if match:
                print(f"Consent platform detected: {match['name']}  (matched by {match['matched_by']})")
            else:
                print("Consent platform: not identified; text scoring will be used.")

            for kind in ("reject", "accept", "settings", "save"):
                control, candidates, resolution = find_control(page, kind, (match or {}).get("entry"))
                print(f"\n[{kind}] resolved via: {resolution.get('path')}")
                if resolution.get("matched_selector"):
                    print(f"  selector: {resolution['matched_selector']}")
                if resolution.get("path") == "none":
                    print(f"  best score {resolution.get('best_score')} vs threshold {resolution.get('threshold')}")
                for candidate in candidates[:5]:
                    box = candidate.get("box") or {}
                    print(
                        f"    score={candidate.get('score')} text={candidate.get('text', '')[:40]!r} "
                        f"id={candidate.get('id', '')!r} size={box.get('width')}x{box.get('height')}"
                    )
                if control:
                    print(f"  WOULD CLICK: {control.get('text', '')[:60]!r} (id={control.get('id', '')!r})")
            print("\nNo audit was performed. Remove --detect-only to run the full capture.\n")
        finally:
            browser.close()
    return 0


def validate_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("URL must include http:// or https:// and a hostname")
    if parts.username or parts.password:
        raise ValueError("Do not embed credentials in the URL. Use a public logged-out URL for the default audit.")
    return url


def choose_headless(args: argparse.Namespace) -> bool:
    if args.headless:
        return True
    if args.headed:
        return False
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def launch_browser(playwright: object, executable: str | None, headless: bool):
    launch_options = {
        "headless": headless,
        "timeout": 30000,
    }
    if executable:
        launch_options["executable_path"] = executable
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        launch_options["chromium_sandbox"] = False
        launch_options["args"] = ["--no-sandbox"]
    try:
        return playwright.chromium.launch(**launch_options)
    except Exception as first_error:
        if executable:
            raise
        raise RuntimeError(
            "No launchable Chrome/Edge/Chromium browser was found. Install Chrome or run "
            "`python -m playwright install chromium`, then retry or pass --browser /path/to/browser. "
            f"Original error: {first_error}"
        ) from first_error


def main() -> int:
    args = parse_args()
    try:
        target_url = validate_url(args.url)
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    args.pages = max(0, min(args.pages, 5))
    args.wait_ms = max(0, min(args.wait_ms, 60000))
    args.timeout_ms = max(5000, min(args.timeout_ms, 120000))
    headless = choose_headless(args)
    if args.manual and headless:
        print("Configuration error: --manual requires a visible browser. Add --headed.", file=sys.stderr)
        return 2
    # A6 - manual mode blocks on input(). Without a terminal that raises EOF and
    # is swallowed mid-run, which previously let a scenario continue as if a
    # human had declined to intervene. Fail here instead, while it is fixable.
    if args.manual and not sys.stdin.isatty():
        print(
            "Configuration error: --manual needs an interactive terminal, but stdin is not a TTY.\n"
            "Run this command directly in a terminal, or drop --manual and rely on the CMP selector\n"
            "table (references/cmp-selectors.json) to resolve the controls automatically.",
            file=sys.stderr,
        )
        return 2

    if args.detect_only:
        try:
            explicit = discover_browser_executable(args.browser)
        except FileNotFoundError as error:
            print(f"Configuration error: {error}", file=sys.stderr)
            return 2
        return run_detect_only(target_url, explicit, headless, args.timeout_ms)

    if args.submit_forms:
        print(
            "\n*** --submit-forms is enabled ***\n"
            "A form on the target site will be SUBMITTED with synthetic test data. On a site backed by\n"
            "a CRM this creates a real contact record and may trigger sales-notification workflows.\n"
            "Only proceed if you own the site and accept that side effect.\n",
            file=sys.stderr,
        )

    host = host_from_url(target_url)
    root = Path(args.out).expanduser().resolve() if args.out else (Path.cwd() / f"cookie-audit-{slugify(host)}-{timestamp_slug()}").resolve()
    if root.exists() and any(root.iterdir()):
        print(f"Configuration error: output directory is not empty: {root}", file=sys.stderr)
        return 2
    ensure_dir(root)
    private_dir = ensure_dir(root / "evidence-private")
    share_dir = ensure_dir(root / "evidence-shareable")

    write_text(
        private_dir / "README-SENSITIVE.txt",
        "This folder contains raw HAR files and raw browser state. It may contain cookie values, identifiers, URLs, request headers, and other personal or confidential information. Keep it local, restrict access, and do not upload or send it without an intentional privilege and data-minimization review. Use evidence-shareable for ordinary collaboration.\n",
    )
    write_text(
        root / "README.txt",
        "Cookie Banner Auditor evidence bundle\n\n"
        "audit-report-draft.html  Open locally for a visual report with screenshots.\n"
        "audit-report-draft.md    Editable report draft.\n"
        "audit-data.json          Structured shareable audit data.\n"
        "findings.json            Machine-readable findings.\n"
        "cookie-inventory.csv     Every cookie observation by scenario/checkpoint.\n"
        "request-inventory.csv    Every observed request with heuristic classification.\n"
        "research-queue.md        Unknown cookies/endpoints requiring research.\n"
        "evidence-shareable/      Sanitized HAR, redacted state, screenshots, logs.\n"
        "evidence-private/        RAW SENSITIVE HAR/state; do not share casually.\n"
        "manifest.sha256          Integrity hashes for the evidence bundle.\n\n"
        "This is a point-in-time technical audit and issue-spotting work product, not a legal opinion or certification.\n",
    )

    explicit_browser = None
    try:
        explicit_browser = discover_browser_executable(args.browser)
    except FileNotFoundError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    thorough = not args.quick
    viewport = {"width": 1440, "height": 1000}
    egress = {"resolved": False, "region": None} if args.no_geo else resolve_egress_region()

    metadata = {
        "tool": "cookie-banner-auditor",
        "tool_version": VERSION,
        "started_at": utc_now(),
        "target_url": target_url,
        "host": host,
        "location_label": args.location_label,
        "egress_region": egress.get("region") or args.location_label,
        "egress_resolution": egress,
        "profile": "thorough" if thorough else "quick",
        "pages": args.pages,
        "wait_ms": args.wait_ms,
        "dwell_ms": args.dwell_ms if thorough else 0,
        "baseline_repeats": args.repeat_baseline if thorough else 0,
        "timeout_ms": args.timeout_ms,
        "headless": headless,
        "viewport": f"{viewport['width']}x{viewport['height']}",
        "manual_fallback": args.manual,
        "gpc_included": not args.no_gpc,
        "accept_control_included": args.accept_control,
        "persistence_check_included": not args.no_persistence,
        "forms_exercised": thorough and not args.no_forms,
        "forms_submitted": bool(args.submit_forms),
        "search_exercised": thorough and not args.no_search,
        "browser_executable": explicit_browser or "Playwright-managed browser",
        "proxy_configured": bool(args.proxy),
        "locale": args.locale,
        "timezone": args.timezone,
        "user_agent_overridden": bool(args.user_agent),
        "ignore_https_errors": args.ignore_https_errors,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "isolation_method": (
            "Playwright chromium.launch() with a throwaway profile (not launch_persistent_context), "
            "one fresh browser context per scenario, no storage_state reuse except in the persistence check."
        ),
        "limitations": [
            "Public logged-out browser sample only unless separately authorized and configured.",
            "One egress region unless additional runs are performed.",
            "Heuristic vendor and purpose classification requires confirmation.",
            "A script load is not proof of transmission; see evidence_strength on each request observation.",
            "Browser evidence does not reveal all downstream uses, contracts, server-side processing, or offline sharing.",
        ],
    }
    metadata["run_fingerprint"] = run_fingerprint(metadata)
    write_json(root / "run-metadata.json", metadata)

    patterns_path = Path(__file__).resolve().parents[1] / "references" / "vendor-patterns.json"
    config = ScenarioConfig(
        url=target_url,
        wait_ms=args.wait_ms,
        timeout_ms=args.timeout_ms,
        pages=args.pages,
        manual=args.manual,
        locale=args.locale,
        timezone_id=args.timezone,
        user_agent=args.user_agent,
        proxy=args.proxy,
        ignore_https_errors=args.ignore_https_errors,
        viewport=viewport,
        thorough=thorough,
        dwell_ms=args.dwell_ms,
        exercise_forms=thorough and not args.no_forms,
        submit_forms=bool(args.submit_forms),
        exercise_search=thorough and not args.no_search,
        transmission_patterns=load_transmission_patterns(),
    )
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright, explicit_browser, headless)
            try:
                metadata["browser_version"] = browser.version
                results = run_all_scenarios(
                    browser=browser,
                    config=config,
                    private_dir=private_dir,
                    share_dir=share_dir,
                    include_gpc=not args.no_gpc,
                    include_accept=args.accept_control,
                    baseline_repeats=args.repeat_baseline if thorough else 0,
                    include_persistence=not args.no_persistence,
                )
            finally:
                browser.close()
    except KeyboardInterrupt:
        print("Audit interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        write_text(root / "fatal-error.txt", f"{type(error).__name__}: {error}\n\n{traceback.format_exc()}")
        print(f"Audit failed: {error}\nPartial evidence, if any, is in {root}", file=sys.stderr)
        return 3

    metadata["completed_at"] = utc_now()
    write_json(root / "run-metadata.json", metadata)
    analysis = analyze_and_write(root, target_url, results, metadata, patterns_path)

    pdf_result = {"ok": False, "error": "skipped"}
    if not args.no_pdf:
        pdf_result = render_pdf_from_html(root / "audit-report.html", root / "audit-report.pdf", explicit_browser)
        if not pdf_result.get("ok"):
            print(f"PDF rendering failed: {pdf_result.get('error')}", file=sys.stderr)

    create_hash_manifest(root)

    zip_result = None
    if not args.no_zip:
        include_raw = not args.zip_shareable_only
        suffix = "CONTAINS-RAW-EVIDENCE" if include_raw else "shareable"
        zip_path = root / f"{slugify(host)}-{timestamp_slug()}-{suffix}.zip"
        zip_result = build_zip_bundle(root, zip_path, include_raw=include_raw)

    invalid = analysis.get("invalid_scenarios") or {}
    suppressed = analysis.get("suppressed_findings") or []

    print("\nCookie banner audit complete.")
    print(f"Overall result: {analysis['overall_status']}")
    print(f"Findings reported: {len(analysis['findings'])}")
    if suppressed:
        print(f"Findings WITHHELD as unsupported: {len(suppressed)} (see suppressed-findings.json)")
    print(f"Report: {root / 'audit-report.html'}")
    if pdf_result.get("ok"):
        print(f"PDF: {root / 'audit-report.pdf'}")
    if zip_result:
        raw_note = "includes RAW evidence - handle as confidential" if zip_result["raw_included"] else "redacted evidence only"
        print(f"Archive: {zip_result['path']} ({zip_result['files']} files, {raw_note})")
    print(f"Output directory: {root}")

    if invalid:
        print("\n" + "=" * 72, file=sys.stderr)
        print("RUN INCOMPLETE - this audit does not support a verdict on every question.", file=sys.stderr)
        for name, detail in invalid.items():
            print(f"  - {name}: {detail.get('invalid_reason')}", file=sys.stderr)
        print(
            "\nFindings depending on these scenarios were withheld rather than reported.\n"
            "If a consent control exists but was not resolved, add its selectors to\n"
            "references/cmp-selectors.json and re-run. Use --detect-only to inspect what\n"
            "the scanner can see.",
            file=sys.stderr,
        )
        print("=" * 72, file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
