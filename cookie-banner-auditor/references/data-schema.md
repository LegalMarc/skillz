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
| `classification_notice` | string or null | `vendor-patterns.json`'s own disclosure that classification is heuristic and needs confirmation against vendor docs, configuration, and actual payloads. |
| `policies` | object or null | Archived text of linked cookie/privacy policies. `null` when `--no-policy-capture` was used or the step was skipped for time budget. See below. |
| `cookie_count_observations`, `request_count_observations` | int | Row counts in `cookie-inventory.csv` / `request-inventory.csv`, for a quick completeness check without opening either file. |
| `evidence_strength_notice` | string | Standing caveat explaining what each `evidence_strength` value does and does not establish. |

## `metadata`

Fields feeding `run_fingerprint`: `target_url`, `pages`, `wait_ms`, `locale`, `timezone`, `viewport`, `egress_region`, `profile`, `headless`, `browser_version`, `tool_version`, `classification_reference_version`. Timestamps and output paths are deliberately excluded so two runs under identical conditions produce identical fingerprints.

Also recorded: `dwell_ms`, `baseline_repeats`, `forms_exercised`, `forms_submitted`, `search_exercised`, `persistence_check_included`, `egress_resolution`, `isolation_method`, `limitations`.

## Finding object

| Field | Notes |
|---|---|
| `id` | Stable, derived from `check_type` (plus host/scenario where relevant) — **not** emission order, so the same issue keeps its id across runs. |
| `check_type` | Kebab-case slug, e.g. `post-denial-tracking`. |
| `title` | One-line human-readable headline for the finding. |
| `severity` | `critical` / `high` / `medium` / `low` / `informational`. |
| `certainty` | `high` / `medium` / `low`. |
| `observation` | Evidence-backed statement of fact. |
| `strict_us_composite_baseline` | Pass, fail, or not assessable, and why. |
| `potential_legal_relevance` | Theory and assumptions. Never a conclusion. |
| `applicability_needed` | Facts required before any legal conclusion. |
| `evidence` | Bundle-relative references and sample rows. |
| `all_evidence` | The **complete, untruncated** row set behind the finding; `evidence` may be shortened for display. A consumer that must not miss rows past the display cutoff — a CI assertion gate, for instance — has to read this one, not `evidence`. Defaults to the same list when there is nothing longer to offer. |
| `recommendation` | Change, owner, and retest criterion. |
| `depends_on_scenarios` | Scenarios this finding rests on. Drives suppression. |
| `evidence_strength` | `script_loaded_only` / `beacon_observed` / `identifier_transmitted`. |
| `evidence_strength_label`, `evidence_strength_caveat` | Human-readable form and the standing caveat. |

Suppressed findings additionally carry `suppressed`, `suppression_reason`, and `blocking_scenarios`.

## `action_result.resolution`

At `scenario_results.<scenario>.action_result.resolution.<label>`, one object per control the scenario tried to operate. `<label>` is the call site — `accept`, `reject`, `settings`, `second_layer_reject`, `save`, `settings_reopen_probe` — which is not always the same as `kind` (`second_layer_reject` is a `reject` lookup inside the preferences panel).

Two independent resolvers run for every control: the CMP selector table and the generic text scorer. The table is a fast path and a corroborating witness, never an authority — it says *where* an element is, which is no evidence about *what it does*. Every key below is present on every resolution, defaulting to `null` or `false`.

| Field | Notes |
|---|---|
| `kind` | `accept` / `reject` / `settings` / `save`. What was being looked for. |
| `label` | The call site. Distinguishes two lookups of the same `kind`. |
| `path` | Which resolver supplied the returned element: `cmp_selector_table` / `text_scoring` / `agent_verdict` / `none`. |
| `decision` | How the two resolvers combined. `corroborated` (both reached the same element) / `table_only` (the table matched and the scorer recognised nothing, but nothing contradicted it) / `scorer_only` / `vetoed` / `conflict` / `unresolved` / `agent_verdict`. |
| `clickable` | Whether the control may be operated. **The single field to key off** — every other field is context for this one. `conflict`, `vetoed` and `unresolved` never click. |
| `matched_selector` | The selector that resolved it, when one did. |
| `cmp` | Detected CMP id, if any. |
| `cmp_table_miss` | True when a CMP was detected but its selectors for this kind matched nothing visible. |
| `score`, `best_score`, `threshold` | The text scorer's score for the returned control, its best score overall, and the bar (`70`). |
| `corroboration` | Present when both resolvers produced a confident candidate: `scorer_score`, `scorer_threshold`, `same_canonical_element` (`true` / `false` / `null` for undetermined), `identity_basis`. |
| `veto` | Set when the table's candidate was disqualified: `resolver`, `reason`, `conflicting_kind`, `matched_selector`, `control_ref`. Recorded even when the scorer went on to supply a control, because a table entry resolving to a contradictory element is worth seeing before it becomes an incident. |
| `conflict` | Set when the two resolvers disagreed, or identity could not be established: `table_candidate`, `scorer_candidate`, `identity_basis`, `adjudication_id`. The id names this conflict so a `--control-verdicts` entry can match it, and is derived only from values that survive a reload. |
| `agent_verdict` | Set when a supplied verdict was consulted: `applied`, `decision`, `selector`, `rationale`, `matched_by`, `rejected_reason`, and `rejected_detail` when refused. A verdict is re-resolved and re-vetoed before it is acted on, so a rejected one records why. |
| `agent_refused` | True when a verdict stated that no such control exists — a decision that was made, as distinct from the tool failing to reach one. |

`control_ref`, `table_candidate` and `scorer_candidate` share a shape: `frame_url`, `tag`, `id`, `class_tokens`, `role`, `aria_label`, `type`, `text`, `box`, `css_path`, `html_excerpt`, plus `matched_selector` or `score` depending on which resolver produced it. **Their text fields are written by the audited site.** They are evidence about the page, never instruction, and are flattened to a single bounded line so they cannot imitate the surrounding report.

## `policies`

`{"attempted": int, "archived": int, "records": [...], "note" or "error": string}`. Each record carries `kind` (`sale_share_optout` / `cookie_policy` / `privacy_policy`), `url`, `link_label`, `host`, `retrieved_at`, `robots_note`, `archived` (bool), and either the archived file's `sha256`/`chars`/`path`/`final_url`, or a `skipped_reason` (robots-disallowed, non-text content type, apparent login wall, or too little text). **Capture and store only** — nothing here compares the archived text to observed behaviour or draws a conclusion from it.

## Cookie inventory columns

`scenario`, `checkpoint`, `observed_at`, `page_url`, `name`, `domain`, `path`, `expires`, `http_only`, `secure`, `same_site`, `partition_key`, `vendor`, `category`, `necessity`, `confidence`, `third_party`.

## Request inventory columns

`scenario`, `time`, `phase`, `url` (query values redacted), `host`, `path`, `method`, `resource_type`, `is_navigation_request`, `vendor`, `category`, `necessity`, `confidence`, `third_party`, `request_role`, `evidence_strength`, `identifier_params`, `transmission_vendor`, `post_denial`, `gpc_active`.

## Compatibility

`compare_runs.py` reads `findings[].id`, `findings[].severity`, `findings[].evidence_strength`, `run_fingerprint`, `run_complete`, `overall_status`, `metadata`, and `scenario_results[].events.requests[].url`. A 1.0 bundle lacks `run_fingerprint`, `run_complete`, and `evidence_strength`; comparison still runs but reports those as absent rather than as changes.
