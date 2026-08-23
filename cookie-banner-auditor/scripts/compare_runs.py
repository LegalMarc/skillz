#!/usr/bin/env python3
"""Compare two cookie-banner audit bundles.

Answers the question a retest actually asks: what changed, and is the change a
change in the site or a change in the tool? Neither input bundle is modified.

    python scripts/compare_runs.py --before ./audit-2026-08 --after ./audit-2026-09
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.capture import render_pdf_from_html
from lib.checks import endpoint_key
from lib.util import (
    discover_browser_executable,
    escape_markdown_cell,
    markdown_to_html,
    read_json,
    write_json,
    write_text,
)

VERSION = "1.0.0"

#: Metadata fields that must match for a comparison to be apples-to-apples.
COMPARABILITY_FIELDS = [
    ("target_url", "Target URL"),
    ("pages", "Pages per scenario"),
    ("locale", "Locale"),
    ("viewport", "Viewport"),
    ("egress_region", "Egress region"),
    ("profile", "Thoroughness profile"),
    ("tool_version", "Tool version"),
]


def _load_bundle(path: Path) -> dict[str, Any]:
    data_path = path / "audit-data.json"
    if not data_path.is_file():
        raise FileNotFoundError(f"Not an audit bundle (no audit-data.json): {path}")
    return read_json(data_path)


def _endpoints(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """host+path -> summary, taken from the scenario request logs.

    Identity comes from `checks.endpoint_key`, shared with the capture-side
    stability check so both answer "which endpoints were contacted" the same
    way.
    """
    output: dict[str, dict[str, Any]] = {}
    for scenario, result in (bundle.get("scenario_results") or {}).items():
        for request in ((result or {}).get("events") or {}).get("requests", []) or []:
            key = endpoint_key(str(request.get("url", "")))
            if not key:
                continue
            entry = output.setdefault(key, {"key": key, "scenarios": set()})
            entry["scenarios"].add(scenario)
    return output


def _findings_by_id(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(f.get("id")): f for f in bundle.get("findings") or []}


def _comparability(before_meta: dict[str, Any], after_meta: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label in COMPARABILITY_FIELDS:
        b, a = before_meta.get(key), after_meta.get(key)
        rows.append({"field": label, "before": b, "after": a, "match": b == a})
    return rows


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_meta = before.get("metadata") or {}
    after_meta = after.get("metadata") or {}

    before_endpoints = _endpoints(before)
    after_endpoints = _endpoints(after)
    added = sorted(set(after_endpoints) - set(before_endpoints))
    removed = sorted(set(before_endpoints) - set(after_endpoints))
    unchanged = sorted(set(before_endpoints) & set(after_endpoints))

    before_findings = _findings_by_id(before)
    after_findings = _findings_by_id(after)
    new_findings = [after_findings[i] for i in sorted(set(after_findings) - set(before_findings))]
    resolved = [before_findings[i] for i in sorted(set(before_findings) - set(after_findings))]
    persisting = [after_findings[i] for i in sorted(set(after_findings) & set(before_findings))]

    severity_changes = []
    for finding_id in sorted(set(after_findings) & set(before_findings)):
        b_sev = before_findings[finding_id].get("severity")
        a_sev = after_findings[finding_id].get("severity")
        b_str = before_findings[finding_id].get("evidence_strength")
        a_str = after_findings[finding_id].get("evidence_strength")
        if b_sev != a_sev or b_str != a_str:
            severity_changes.append({
                "id": finding_id, "title": after_findings[finding_id].get("title"),
                "severity_before": b_sev, "severity_after": a_sev,
                "strength_before": b_str, "strength_after": a_str,
            })

    comparability = _comparability(before_meta, after_meta)
    mismatches = [row for row in comparability if not row["match"]]

    return {
        "tool": "cookie-banner-auditor compare_runs",
        "tool_version": VERSION,
        "before_fingerprint": before.get("run_fingerprint"),
        "after_fingerprint": after.get("run_fingerprint"),
        "fingerprints_match": before.get("run_fingerprint") == after.get("run_fingerprint"),
        "comparability": comparability,
        "comparability_mismatches": mismatches,
        "before_status": before.get("overall_status"),
        "after_status": after.get("overall_status"),
        "before_complete": before.get("run_complete", True),
        "after_complete": after.get("run_complete", True),
        "endpoints": {
            "added": added, "removed": removed,
            "added_count": len(added), "removed_count": len(removed), "unchanged_count": len(unchanged),
        },
        "findings": {
            "new": new_findings, "resolved": resolved, "persisting": persisting,
            "severity_changes": severity_changes,
        },
        "classification_version_before": before.get("classification_reference_version"),
        "classification_version_after": after.get("classification_reference_version"),
    }


def render_comparison_markdown(delta: dict[str, Any], before_path: Path, after_path: Path) -> str:
    lines = [
        "# Cookie Banner Audit - Run Comparison",
        "",
        f"**Before:** `{before_path}` - {delta['before_status']}  ",
        f"**After:** `{after_path}` - {delta['after_status']}",
        "",
    ]

    if not delta["before_complete"] or not delta["after_complete"]:
        lines.extend([
            "> **One or both runs are incomplete.** A scenario that did not complete produces no findings, "
            "so a finding that 'disappeared' may simply not have been tested. Check the incomplete run before "
            "reading anything below as remediation.",
            "",
        ])

    if not delta["fingerprints_match"]:
        lines.extend([
            "> **Run conditions differ.** These two runs were not taken under identical conditions, so some "
            "differences below may be caused by the change in conditions rather than by a change in the site. "
            "The mismatched parameters are listed under Comparability.",
            "",
        ])

    lines.extend(["## Comparability", "", "| Parameter | Before | After | Match |", "|---|---|---|---|"])
    for row in delta["comparability"]:
        lines.append(
            f"| {row['field']} | {escape_markdown_cell(row['before'])} | "
            f"{escape_markdown_cell(row['after'])} | {'yes' if row['match'] else '**NO**'} |"
        )
    lines.extend([
        "",
        f"Classification reference: `{delta['classification_version_before']}` to `{delta['classification_version_after']}`. "
        "A change here means the vendor pattern table was updated, which can add or remove classifications "
        "without the site changing at all.",
        "",
        "## Findings",
        "",
        f"- Resolved (present before, absent after): **{len(delta['findings']['resolved'])}**",
        f"- New (absent before, present after): **{len(delta['findings']['new'])}**",
        f"- Persisting: **{len(delta['findings']['persisting'])}**",
        f"- Changed severity or evidence strength: **{len(delta['findings']['severity_changes'])}**",
        "",
    ])

    for label, key in (("Resolved", "resolved"), ("New", "new")):
        items = delta["findings"][key]
        if not items:
            continue
        lines.extend([f"### {label}", "", "| ID | Title | Severity |", "|---|---|---|"])
        for item in items:
            lines.append(f"| `{item.get('id')}` | {escape_markdown_cell(item.get('title'))} | {item.get('severity')} |")
        lines.append("")

    if delta["findings"]["severity_changes"]:
        lines.extend([
            "### Changed severity or evidence strength", "",
            "| ID | Title | Severity | Evidence strength |", "|---|---|---|---|",
        ])
        for item in delta["findings"]["severity_changes"]:
            lines.append(
                f"| `{item['id']}` | {escape_markdown_cell(item['title'])} | "
                f"{item['severity_before']} to {item['severity_after']} | "
                f"{item['strength_before']} to {item['strength_after']} |"
            )
        lines.append("")

    endpoints = delta["endpoints"]
    lines.extend([
        "## Endpoints",
        "",
        f"- Removed: **{endpoints['removed_count']}**",
        f"- Added: **{endpoints['added_count']}**",
        f"- Unchanged: **{endpoints['unchanged_count']}**",
        "",
    ])
    for label, key in (("Removed since the previous run", "removed"), ("Added since the previous run", "added")):
        items = endpoints[key]
        if not items:
            continue
        lines.extend([f"### {label}", ""])
        lines.extend(f"- `{item}`" for item in items[:120])
        if len(items) > 120:
            lines.append(f"- ...and {len(items) - 120} more")
        lines.append("")

    lines.extend([
        "## How to read this",
        "",
        "An endpoint disappearing is consistent with remediation, but also with an A/B test, a geo "
        "difference, a shorter observation window, or a tag that simply did not fire this time. Check the "
        "baseline stability section of each run before treating a disappearance as a fix. Endpoints appearing "
        "or disappearing while the comparability table shows mismatches should be attributed to the changed "
        "conditions first.",
        "",
        "This comparison is technical evidence, not a compliance conclusion.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two cookie-banner audit bundles.")
    parser.add_argument("--before", required=True, help="Path to the earlier audit bundle directory")
    parser.add_argument("--after", required=True, help="Path to the later audit bundle directory")
    parser.add_argument("--out", help="Output directory for the comparison (default: alongside the later bundle)")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF rendering")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()

    before_path = Path(args.before).expanduser().resolve()
    after_path = Path(args.after).expanduser().resolve()
    try:
        before = _load_bundle(before_path)
        after = _load_bundle(after_path)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    delta = compare(before, after)
    out_dir = Path(args.out).expanduser().resolve() if args.out else after_path
    out_dir.mkdir(parents=True, exist_ok=True)

    markdown = render_comparison_markdown(delta, before_path, after_path)
    write_text(out_dir / "comparison-report.md", markdown)
    write_json(out_dir / "comparison-data.json", delta)

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Audit run comparison</title>
<style>
body{{margin:0;background:#f4f6f8;color:#17212b;font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}
main{{max-width:1000px;margin:32px auto;background:#fff;padding:44px 52px;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
h1{{margin:0 0 16px}} h2{{margin-top:34px;border-bottom:1px solid #d9dee3;padding-bottom:8px}}
blockquote{{border-left:4px solid #8b1e2d;background:#fdf0f1;padding:12px 16px;margin:16px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th,td{{border:1px solid #d9dee3;padding:7px 9px;text-align:left}} th{{background:#f4f6f8}}
code{{background:#f4f6f8;padding:1px 4px;border-radius:3px}} ul{{margin-left:20px}}
@media print{{body{{background:#fff}} main{{box-shadow:none;margin:0;padding:0}} table,blockquote{{page-break-inside:avoid}}}}
</style></head><body><main>{markdown_to_html(markdown)}</main></body></html>"""
    write_text(out_dir / "comparison-report.html", html)

    if not args.no_pdf:
        result = render_pdf_from_html(
            out_dir / "comparison-report.html", out_dir / "comparison-report.pdf",
            discover_browser_executable(None),
        )
        if not result.get("ok"):
            print(f"PDF rendering failed: {result.get('error')}", file=sys.stderr)

    print("\nComparison complete.")
    print(f"  Findings: {len(delta['findings']['resolved'])} resolved, {len(delta['findings']['new'])} new, {len(delta['findings']['persisting'])} persisting")
    print(f"  Endpoints: {delta['endpoints']['removed_count']} removed, {delta['endpoints']['added_count']} added")
    if not delta["fingerprints_match"]:
        print("  WARNING: run conditions differ; some differences may not be site changes.")
    if not delta["before_complete"] or not delta["after_complete"]:
        print("  WARNING: one or both runs were incomplete; absent findings may simply be untested.")
    print(f"  Report: {out_dir / 'comparison-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
