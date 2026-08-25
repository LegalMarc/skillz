# Instrumented capture runner

Install once:

```bash
python -m pip install -r scripts/requirements.txt
```

The runner uses installed Chrome, Edge, or Chromium. If none is available:

```bash
python -m playwright install chromium
```

## Pre-flight first

```bash
python scripts/audit_site.py --url https://example.com --detect-only
```

Loads the page, reports the detected consent platform and every candidate control with its score and geometry, says what it would click, and exits without auditing. Takes seconds. Run it before every new target — it answers whether the denial control is reachable, which determines whether the audit will mean anything.

## Run the audit

```bash
python scripts/audit_site.py --url https://example.com --out ./audit-example --accept-control
```

Default is the **thorough** profile, roughly 15 minutes: 15-second dwell with staged scrolling per page, form-field entry, on-site search, two baseline repeats, and a fresh-context persistence check. `--quick` restores the older ~4-minute behaviour and should be disclosed in the report, because it under-observes tags that fire on engagement rather than load.

Scenarios: clean baseline, denial, GPC, optional accept control, baseline repeats, persistence. Raw HAR and state go to `evidence-private/`; sanitized copies to `evidence-shareable/`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Completed; every scenario valid. |
| 2 | Configuration error. |
| 3 | Capture failed; partial evidence written. |
| 4 | **Run incomplete.** A required interaction did not complete and verify. Findings depending on it were withheld into `suppressed-findings.json`. |
| 6 | **Pre-flight only.** A control could not be resolved unambiguously; the CMP table and the text scorer disagreed. Both candidates are listed in `detect-only-<host>-<profile>-conflicts.json`. No audit ran. |
| 130 | Interrupted. |

Exit 4 is not a crash. It means the audit ran but cannot answer some of what it was asked. Fix the cause — usually by adding selectors to `references/cmp-selectors.json` — and re-run.

### Options worth knowing

| Flag | Effect |
|---|---|
| `--detect-only` | Pre-flight control detection, then exit. |
| `--quick` | Fast profile, no exercises or repeats. |
| `--dwell-ms N` | Dwell per page in the thorough profile (default 15000). |
| `--repeat-baseline N` | Extra baseline runs for stability detection (default 2). |
| `--submit-forms` | **Actually submits a form.** Creates real CRM records and may trigger workflows. Off by default. |
| `--no-forms`, `--no-search` | Skip an exercise. |
| `--no-persistence` | Skip the fresh-context persistence check. |
| `--no-geo` | Do not resolve the public egress region. |
| `--zip-shareable-only` | Build the archive without `evidence-private/`. |
| `--no-zip`, `--no-pdf` | Skip packaging steps. |
| `--headed`, `--manual` | Watch it run; pause for a human choice. `--manual` requires a real terminal and fails fast without one. |

## Outputs

`audit-report.pdf` / `.html` / `.md` are the same 14-section report rendered from one Markdown source. `suppressed-findings.json` lists findings withheld as unsupported — read it before concluding anything is clean. `request-inventory.csv` grades every request by evidence strength. The archive `<host>-<timestamp>-CONTAINS-RAW-EVIDENCE.zip` holds the complete bundle including raw HAR, with a warning README inside.

## Compare two runs

```bash
python scripts/compare_runs.py --before ./audit-2026-08 --after ./audit-2026-09
```

Writes `comparison-report.md`, `.html`, and `.pdf`. Neither input bundle is modified. Heed the two warnings it can raise: mismatched run conditions, and an incomplete run on either side. Both mean a difference may not be a site change.

## Tests

```bash
python scripts/tests/smoke_test.py
```

99 test functions, 110 checks total. Most are pure-function checks against in-process data; the browser-backed ones launch a real headless Chromium against in-memory fixtures — so the suite is not purely offline, but it never contacts an external site or the network. Covers control detection (including the bare-label regression that once produced a false critical finding), click verification, validity gating, transmission classification, Consent Mode parsing, embedded-identifier and rights-mechanism scans, symmetry measurement, CMP table integrity, report rendering, packaging, and comparison. A live site is still needed to validate real CMP behaviour.

## Safety

Use a public, logged-out URL by default. Never put credentials in a URL, command line, or chat. Never bypass a CAPTCHA or access control. A raw HAR can contain identifiers, cookie values, authorization material, query strings, and request bodies.
