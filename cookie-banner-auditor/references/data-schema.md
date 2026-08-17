# Output schema

`audit-data.json`, `schema_version` **2.0**. This is the contract `compare_runs.py` relies on; changing a field name here breaks comparison against older bundles, so bump `schema_version` when you do.

## Top level

| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | `"2.0"`. |
| `target_url`, `site_host` | string | Audited origin. |
| `metadata` | object | Run parameters. See below. |
| `run_fingerprint` | string | 16-char hash of the comparability parameters. |
| `overall_status` | string | Prefixed `INCOMPLETE - ` when any scenario is invalid. |
| `run_complete` | bool | False when any required interaction did not complete and verify. |
| `scenario_validity` | object | Per scenario: `required_interaction`, `interaction_completed`, `verification_passed`, `valid`, `invalid_reason`. |
| `invalid_scenarios` | object | Subset of the above where `valid` is false. |
| `findings` | array | Reported findings. |
| `suppressed_findings` | array | Findings **withheld** because a scenario they depend on is invalid. Never treat their absence from `findings` as a clean result. |
| `baseline_stability` | object | `stable`, `unstable`, `run_count` across identical baseline repeats. |
| `persistence_check` | object | Whether a stored denial survived into a fresh context. |
| `evidence_strength_counts` | object | Count of request observations per strength. |
| `scenario_results` | object | Per-scenario checkpoints, events, CMP, exercises, consent mode. |
| `classification_reference_version` | string | `vendor-patterns.json` version. A change here can alter classifications without the site changing. |

## `metadata`

Fields feeding `run_fingerprint`: `target_url`, `pages`, `wait_ms`, `locale`, `timezone`, `viewport`, `egress_region`, `profile`, `headless`, `browser_version`, `tool_version`, `classification_reference_version`. Timestamps and output paths are deliberately excluded so two runs under identical conditions produce identical fingerprints.

Also recorded: `dwell_ms`, `baseline_repeats`, `forms_exercised`, `forms_submitted`, `search_exercised`, `persistence_check_included`, `egress_resolution`, `isolation_method`, `limitations`.

## Finding object

| Field | Notes |
|---|---|
| `id` | Stable, derived from `check_type` (plus host/scenario where relevant) — **not** emission order, so the same issue keeps its id across runs. |
| `check_type` | Kebab-case slug, e.g. `post-denial-tracking`. |
| `severity` | `critical` / `high` / `medium` / `low` / `informational`. |
| `certainty` | `high` / `medium` / `low`. |
| `observation` | Evidence-backed statement of fact. |
| `strict_us_composite_baseline` | Pass, fail, or not assessable, and why. |
| `potential_legal_relevance` | Theory and assumptions. Never a conclusion. |
| `applicability_needed` | Facts required before any legal conclusion. |
| `evidence` | Bundle-relative references and sample rows. |
| `recommendation` | Change, owner, and retest criterion. |
| `depends_on_scenarios` | Scenarios this finding rests on. Drives suppression. |
| `evidence_strength` | `script_loaded_only` / `beacon_observed` / `identifier_transmitted`. |
| `evidence_strength_label`, `evidence_strength_caveat` | Human-readable form and the standing caveat. |

Suppressed findings additionally carry `suppressed`, `suppression_reason`, and `blocking_scenarios`.

## Request inventory columns

`scenario`, `time`, `phase`, `url` (query values redacted), `host`, `path`, `method`, `resource_type`, `is_navigation_request`, `vendor`, `category`, `necessity`, `confidence`, `third_party`, `request_role`, `evidence_strength`, `identifier_params`, `transmission_vendor`, `post_denial`, `gpc_active`.

## Compatibility

`compare_runs.py` reads `findings[].id`, `findings[].severity`, `findings[].evidence_strength`, `run_fingerprint`, `run_complete`, `overall_status`, `metadata`, and `scenario_results[].events.requests[].url`. A 1.0 bundle lacks `run_fingerprint`, `run_complete`, and `evidence_strength`; comparison still runs but reports those as absent rather than as changes.
