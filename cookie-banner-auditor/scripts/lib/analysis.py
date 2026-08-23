from __future__ import annotations

import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import checks
from .capture import (
    ACCEPT_PATTERNS,
    COMPLETED_DENIAL_STATUSES,
    REJECT_PATTERNS,
)
from .util import (
    escape_markdown_cell,
    markdown_to_html,
    read_json,
    same_site,
    sanitize_event_log,
    sanitize_url,
    utc_now,
    write_csv,
    write_json,
    write_text,
)

TRACKING_CATEGORIES = {"advertising", "analytics", "session_replay", "social", "possible_tracking"}
GPC_RELEVANT_CATEGORIES = {"advertising", "social"}
POST_DENIAL_PHASES = {"denial_interaction", "post_denial", "refresh"}
AUTH_COOKIE = re.compile(r"(?:^|_)(auth|session|sess|sid|jwt|token)(?:_|$)", re.I)


def _load_patterns(path: Path) -> dict[str, Any]:
    return read_json(path)


def _domain_match(host: str, pattern: str) -> bool:
    host = (host or "").lower().strip(".")
    pattern = pattern.lower().strip(".")
    return host == pattern or host.endswith("." + pattern)


def classify_request(url: str, site_host: str, patterns: dict[str, Any]) -> dict[str, Any]:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or "/"
    except Exception:
        return {"vendor": "Unknown", "category": "unknown", "necessity": "unknown", "confidence": "low", "third_party": None}
    for rule in patterns.get("domains", []):
        if not _domain_match(host, str(rule.get("match", ""))):
            continue
        path_regex = rule.get("path_regex")
        if path_regex and not re.search(str(path_regex), path, re.I):
            continue
        return {
            "vendor": rule.get("vendor", "Unknown"),
            "category": rule.get("category", "unknown"),
            "necessity": rule.get("necessity", "unknown"),
            "confidence": rule.get("confidence", "low"),
            "matched_rule": rule,
            "third_party": not same_site(host, site_host),
            "host": host,
            "path": path,
        }
    if same_site(host, site_host):
        for rule in patterns.get("first_party_path_patterns", []):
            if re.search(str(rule.get("path_regex", "")), path, re.I):
                return {
                    "vendor": "First-party endpoint",
                    "category": rule.get("category", "possible_tracking"),
                    "necessity": rule.get("necessity", "unknown"),
                    "confidence": rule.get("confidence", "low"),
                    "matched_rule": rule,
                    "third_party": False,
                    "host": host,
                    "path": path,
                }
    return {
        "vendor": "Unknown",
        "category": "unknown",
        "necessity": "unknown",
        "confidence": "low",
        "third_party": not same_site(host, site_host),
        "host": host,
        "path": path,
    }


def classify_cookie(cookie: dict[str, Any], site_host: str, patterns: dict[str, Any]) -> dict[str, Any]:
    name = str(cookie.get("name", ""))
    domain = str(cookie.get("domain", "")).lstrip(".").lower()
    for rule in patterns.get("cookies", []):
        if re.search(str(rule.get("name_regex", "")), name, re.I):
            return {
                "vendor": rule.get("vendor", "Unknown"),
                "category": rule.get("category", "unknown"),
                "necessity": rule.get("necessity", "unknown"),
                "confidence": rule.get("confidence", "low"),
                "matched_rule": rule,
                "third_party": not same_site(domain, site_host),
            }
    for rule in patterns.get("domains", []):
        if _domain_match(domain, str(rule.get("match", ""))):
            return {
                "vendor": rule.get("vendor", "Unknown"),
                "category": rule.get("category", "unknown"),
                "necessity": rule.get("necessity", "unknown"),
                "confidence": rule.get("confidence", "low"),
                "matched_rule": rule,
                "third_party": not same_site(domain, site_host),
            }
    return {
        "vendor": "Unknown",
        "category": "unknown",
        "necessity": "unknown",
        "confidence": "low",
        "third_party": not same_site(domain, site_host),
    }


def _checkpoint_index(checkpoint: str) -> int:
    match = re.match(r"(\d+)", checkpoint or "")
    return int(match.group(1)) if match else 999


def build_cookie_inventory(results: dict[str, Any], site_host: str, patterns: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario, result in results.items():
        if not isinstance(result, dict):
            continue
        for checkpoint in result.get("checkpoints", []) or []:
            for cookie in checkpoint.get("cookies", []) or []:
                classification = classify_cookie(cookie, site_host, patterns)
                expires = cookie.get("expires")
                expiration_iso = "session"
                if isinstance(expires, (int, float)) and expires > 0:
                    try:
                        expiration_iso = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    except Exception:
                        expiration_iso = str(expires)
                rows.append({
                    "scenario": scenario,
                    "checkpoint": checkpoint.get("checkpoint"),
                    "checkpoint_index": _checkpoint_index(str(checkpoint.get("checkpoint", ""))),
                    "observed_at": checkpoint.get("time"),
                    "page_url": sanitize_url(str(checkpoint.get("url", ""))),
                    "name": cookie.get("name"),
                    "domain": cookie.get("domain"),
                    "path": cookie.get("path"),
                    "expires": expiration_iso,
                    "http_only": cookie.get("httpOnly"),
                    "secure": cookie.get("secure"),
                    "same_site": cookie.get("sameSite"),
                    "partition_key": cookie.get("partitionKey"),
                    "vendor": classification.get("vendor"),
                    "category": classification.get("category"),
                    "necessity": classification.get("necessity"),
                    "confidence": classification.get("confidence"),
                    "third_party": classification.get("third_party"),
                })
    return rows


def build_request_inventory(results: dict[str, Any], site_host: str, patterns: dict[str, Any]) -> list[dict[str, Any]]:
    transmission_patterns = patterns.get("transmission_patterns") or []
    rows: list[dict[str, Any]] = []
    for scenario, result in results.items():
        if not isinstance(result, dict):
            continue
        for request in (result.get("events") or {}).get("requests", []) or []:
            url = str(request.get("url", ""))
            classification = classify_request(url, site_host, patterns)
            # C1/C5: separate "the tag loaded" from "the tag transmitted".
            transmission = checks.classify_request(
                url,
                request.get("resource_type"),
                str(request.get("method", "GET")),
                transmission_patterns=transmission_patterns,
            )
            phase = str(request.get("phase", ""))
            rows.append({
                "scenario": scenario,
                "time": request.get("time"),
                "phase": phase,
                "url": sanitize_url(url),
                "host": classification.get("host"),
                "path": classification.get("path"),
                "method": request.get("method"),
                "resource_type": request.get("resource_type"),
                "is_navigation_request": request.get("is_navigation_request"),
                "vendor": classification.get("vendor"),
                "category": classification.get("category"),
                "necessity": classification.get("necessity"),
                "confidence": classification.get("confidence"),
                "third_party": classification.get("third_party"),
                "request_role": transmission.get("request_role"),
                "evidence_strength": transmission.get("evidence_strength"),
                "identifier_params": transmission.get("identifier_params"),
                "transmission_vendor": transmission.get("transmission_vendor"),
                "post_denial": scenario == "denial" and (phase in POST_DENIAL_PHASES or phase.startswith("internal_navigation_") or phase.startswith("exercise_")),
                "gpc_active": scenario == "gpc",
            })
    return rows


def _dedupe_requests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("scenario"), row.get("phase"), row.get("host"), row.get("path"), row.get("category"), row.get("resource_type"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _cookie_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("name", "")), str(row.get("domain", "")), str(row.get("path", "")))


def _cookies_at(cookie_rows: list[dict[str, Any]], scenario: str, checkpoint_prefix: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        _cookie_key(row): row
        for row in cookie_rows
        if row.get("scenario") == scenario and str(row.get("checkpoint", "")).startswith(checkpoint_prefix)
    }


def _is_accept_text(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in ACCEPT_PATTERNS)


def _is_reject_text(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in REJECT_PATTERNS)


def _banner_visible(checkpoint: dict[str, Any]) -> bool:
    banner = checkpoint.get("banner") or {}
    containers = banner.get("containers") or []
    if not containers:
        return False
    controls = banner.get("controls") or []
    return any(_is_accept_text(str(c.get("text", ""))) or _is_reject_text(str(c.get("text", ""))) for c in controls)


def _stable_id(check_type: str, *parts: str) -> str:
    """Derive a finding id from what the finding is about, not emission order.

    Order-derived ids (F-001, F-002) shift whenever an unrelated check starts or
    stops firing, which makes run-to-run comparison meaningless.
    """
    tail = "-".join(re.sub(r"[^A-Za-z0-9]+", "-", p).strip("-").upper() for p in parts if p)
    base = f"F-{re.sub(r'[^A-Za-z0-9]+', '-', check_type).strip('-').upper()}"
    return f"{base}-{tail}" if tail else base


def _finding(
    check_type: str,
    title: str,
    severity: str,
    observation: str,
    strict_baseline: str,
    legal_relevance: str,
    evidence: list[dict[str, Any]],
    recommendation: str,
    certainty: str = "medium",
    applicability_needed: str | None = None,
    depends_on_scenarios: list[str] | None = None,
    evidence_strength: str | None = None,
    id_parts: tuple[str, ...] = (),
    all_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one finding.

    `depends_on_scenarios` is what makes validity gating possible: a finding
    naming a scenario that did not complete is suppressed rather than reported.
    `evidence_strength` records whether the underlying requests merely loaded a
    script or actually transmitted, which the report is required to state.
    `evidence` may be truncated for display; `all_evidence` carries the
    complete, untruncated row set for callers - such as a CI assertion gate -
    that must not silently miss rows past the display cutoff. It defaults to
    `evidence` when the caller has nothing longer to offer.
    """
    return {
        "id": _stable_id(check_type, *id_parts),
        "check_type": check_type,
        "title": title,
        "severity": severity,
        "certainty": certainty,
        "observation": observation,
        "strict_us_composite_baseline": strict_baseline,
        "potential_legal_relevance": legal_relevance,
        "applicability_needed": applicability_needed,
        "evidence": evidence,
        "all_evidence": all_evidence if all_evidence is not None else evidence,
        "recommendation": recommendation,
        "depends_on_scenarios": depends_on_scenarios or [],
        "evidence_strength": evidence_strength,
        "evidence_strength_label": checks.STRENGTH_LABEL.get(evidence_strength or "", None),
        "evidence_strength_caveat": checks.STRENGTH_CAVEAT.get(evidence_strength or "", None),
    }


def _strength_of(rows: list[dict[str, Any]]) -> str:
    return checks.strongest(str(r.get("evidence_strength") or "") for r in rows)


def scenario_validity_map(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-scenario validity, defaulting to valid for anything without a verdict."""
    output: dict[str, dict[str, Any]] = {}
    for scenario, result in results.items():
        if not isinstance(result, dict):
            continue
        validity = result.get("validity")
        if isinstance(validity, dict):
            output[scenario] = validity
        elif is_scenario(result):
            # A captured scenario with no verdict recorded: treat as valid, since
            # only scenarios requiring an interaction can fail to complete one.
            output[scenario] = {"valid": True, "required_interaction": None, "invalid_reason": None}
    return output


def partition_findings(
    findings: list[dict[str, Any]],
    validity: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split findings into those that may be reported and those that may not.

    This is the guard against the failure mode that produced a false critical
    finding in the 2026-08-17 run: a denial scenario whose click never happened
    still emitted a "tracking continued after denial" finding.
    """
    emitted: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for finding in findings:
        blockers = []
        for name in finding.get("depends_on_scenarios") or []:
            if name not in validity:
                # Fail closed: an unrecognized dependency is not evidence the
                # interaction succeeded. It may be a typo'd or renamed scenario
                # key, or one the runner never created for this profile.
                blockers.append({"scenario": name, "reason": f"scenario '{name}' was not present in this run"})
            elif not validity[name].get("valid", True):
                blockers.append({"scenario": name, "reason": validity[name].get("invalid_reason")})
        if blockers:
            suppressed.append({
                **finding,
                "suppressed": True,
                "suppression_reason": (
                    "Withheld because this finding depends on a scenario that did not complete a "
                    "verified interaction, so the evidence it would rest on was never captured."
                ),
                "blocking_scenarios": blockers,
            })
        else:
            emitted.append(finding)
    return emitted, suppressed


def generate_findings(results: dict[str, Any], cookie_rows: list[dict[str, Any]], request_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    unique_requests = _dedupe_requests(request_rows)

    baseline_tracking = [r for r in unique_requests if r.get("scenario") == "baseline" and r.get("category") in TRACKING_CATEGORIES]
    if baseline_tracking:
        strength = _strength_of(baseline_tracking)
        findings.append(_finding(
            "pre-consent-tracking",
            "Known or likely nonessential tracking loaded before any banner choice",
            "high",
            f"The clean baseline recorded {len(baseline_tracking)} distinct known or likely tracking endpoint patterns before any consent interaction. "
            f"Strongest evidence observed: {checks.STRENGTH_LABEL.get(strength, strength)}.",
            "Fails the conservative baseline, which permits only narrowly necessary processing before affirmative choice.",
            "U.S. law does not universally require opt-in for every analytics request. Legal significance depends on the banner's promises, sale/share or targeted-advertising status, sensitive-data context, children, applicable state law, and wiretap facts. A banner that promises gating but does not gate may create FTC or state deceptive-practices risk.",
            baseline_tracking[:20],
            "Gate advertising, session replay, behavioral analytics, and similar tags at the tag-manager and server-side layers; document any claimed necessary analytics purpose.",
            certainty="high",
            depends_on_scenarios=["baseline"],
            evidence_strength=strength,
            all_evidence=baseline_tracking,
        ))

    post_denial_tracking = [r for r in unique_requests if r.get("post_denial") and r.get("category") in TRACKING_CATEGORIES]
    if post_denial_tracking:
        strength = _strength_of(post_denial_tracking)
        findings.append(_finding(
            "post-denial-tracking",
            "Tracking continued after the denial action",
            "critical" if strength in {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER} else "high",
            f"The denial scenario recorded {len(post_denial_tracking)} distinct tracking endpoint patterns during or after the denial interaction, refresh, or subsequent same-origin navigation. "
            f"Strongest evidence observed: {checks.STRENGTH_LABEL.get(strength, strength)}.",
            "Fails the conservative baseline and indicates that the denial choice did not fully propagate to all relevant tags or endpoints.",
            "Potentially significant under FTC deception principles and state privacy laws where the flow represents sale, sharing, targeted advertising, sensitive-data processing, or other activity subject to an opt-out or consent requirement. The scan alone cannot determine contractual service-provider status or all data uses.",
            post_denial_tracking[:30],
            "Trace each endpoint through the CMP, tag manager, first-party scripts, server-side container, and vendor configuration. Retest after remediation in a clean context.",
            certainty="high",
            depends_on_scenarios=["denial"],
            evidence_strength=strength,
        ))

    denial_pre = _cookies_at(cookie_rows, "denial", "01-")
    denial_post_rows = [r for r in cookie_rows if r.get("scenario") == "denial" and int(r.get("checkpoint_index") or 999) >= 2]
    post_nonessential = []
    for row in denial_post_rows:
        if _cookie_key(row) not in denial_pre and row.get("category") in TRACKING_CATEGORIES:
            post_nonessential.append(row)
    if post_nonessential:
        dedup: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in post_nonessential:
            dedup[_cookie_key(row)] = row
        findings.append(_finding(
            "post-denial-cookies",
            "New nonessential cookies appeared after denial",
            "high",
            f"At least {len(dedup)} known or likely nonessential cookie(s) first appeared after the denial action.",
            "Fails the conservative baseline.",
            "Potentially supports a conclusion that the denial was not honored, subject to confirming each cookie's actual purpose and the applicable law.",
            list(dedup.values())[:30],
            "Confirm the source and purpose of each cookie, then block creation unless the applicable preference authorizes it.",
            certainty="high",
            depends_on_scenarios=["denial"],
        ))

    denial_result = results.get("denial", {})
    action = denial_result.get("action_result", {}) or {}
    status = str(action.get("status", ""))
    resolution = action.get("resolution") or {}
    if status == checks.AUTOSAVE_NO_SAVE_CONTROL:
        toggle_result = action.get("toggle_result") or {}
        disabled = toggle_result.get("disabled") or []
        save_resolution = resolution.get("save") or {}
        autosave_verification = action.get("verification")

        if autosave_verification is None:
            # No autosave classification ran for this CMP (checks.classify_
            # autosave_denial was never invoked); the only fact this run
            # establishes is that no save control could be resolved after the
            # toggles were flipped.
            findings.append(_finding(
                "denial-not-committed",
                "Optional categories were switched off but no save control could be operated",
                "high",
                (
                    f"The scanner opened the preferences layer and switched {len(disabled)} "
                    "optional-category toggle(s) off, but no save control could be resolved "
                    + (
                        f"(candidates were visible but none reached the confidence threshold; "
                        f"best score {save_resolution.get('best_score')} against a threshold of "
                        f"{save_resolution.get('threshold')})."
                        if action.get("save_candidates") else
                        "and no candidate save control was found in any frame."
                    )
                    + " The preference was therefore never committed."
                ),
                "Cannot be assessed. No denial was recorded, so nothing about post-denial behaviour is evidenced by this run.",
                (
                    "No legal inference should be drawn about how denial is honoured. The interface "
                    "observation is separately relevant: a preferences layer that can be changed but "
                    "not saved would not record a choice for a real user either, though that must be "
                    "confirmed by hand before being treated as a UI defect rather than a scanner gap."
                ),
                (action.get("save_candidates", [])[:10] + disabled[:10]),
                (
                    "Confirm by hand whether a save control exists in this CMP's preferences layer. If it "
                    "does, add its selector to references/cmp-selectors.json - taking care that the selector "
                    "is the save control and not the accept control, which would convert a denial into an "
                    "acceptance. If it does not, that is a UI finding to raise with the site owner."
                ),
                certainty="high",
            ))
        else:
            # An autosave classification did run - branch the report on its
            # basis rather than asserting a fixed mutation claim, since some
            # bases (no toggle found at all) never mutated anything and one
            # basis (a reload reading a toggle back ON) is affirmative
            # evidence of a discard, not merely an unconfirmed choice.
            basis = autosave_verification.get("basis")
            mutated = bool(disabled)

            if basis == "reload_reverted":
                findings.append(_finding(
                    "denial-autosave-discarded",
                    "Optional categories were switched off but a reload showed the CMP discarded the choice",
                    # `high`, not `critical`, for the same reason
                    # `denial-autosave-unconfirmed` is: the tool did not observe
                    # tracking continuing after a denial. It observed that the
                    # choice was not kept, which is a stronger *certainty* than
                    # the unconfirmed case - hence `certainty="high"` below -
                    # but not a more severe observed harm.
                    "high",
                    (
                        f"The scanner opened the preferences layer and switched {len(disabled)} "
                        "optional-category toggle(s) off. A subsequent reload read at least one toggle "
                        "back ON, which is affirmative evidence that this CMP has no save control on "
                        f"this path and discarded the choice. {autosave_verification.get('note', '')}"
                    ),
                    (
                        "Fails the persistence limb of the conservative baseline: the reload read-back is "
                        "affirmative evidence that the denial was not kept, rather than merely unconfirmed."
                    ),
                    (
                        "No legal inference should be drawn here. The observation - that the interface "
                        "let a choice be made and a reload showed it had not been kept - is recorded as "
                        "an interface fact; whether it supports any legal theory is decided by the "
                        "issue matrix from the full set of findings, not asserted by this finding. "
                        "Confirm by hand before treating it as anything more than a scanner observation."
                    ),
                    [autosave_verification] + disabled[:10],
                    (
                        "Confirm by hand that this CMP's settings path discards the choice without a "
                        "save control, then raise it with the site owner as a UI defect."
                    ),
                    certainty="high",
                    depends_on_scenarios=[],
                ))
            elif basis == "no_controls_examined":
                findings.append(_finding(
                    "denial-autosave-unconfirmed",
                    "No optional denial control was found to operate in the preferences layer",
                    "high",
                    (
                        "The scanner opened the preferences layer but found no optional-category toggle "
                        "to operate, so no choice was made and there is nothing to verify. "
                        f"{autosave_verification.get('note', '')}"
                    ),
                    "Cannot be assessed. No denial was performed, so nothing about post-denial behaviour is evidenced by this run.",
                    (
                        "No legal inference should be drawn. This may be a scanner gap or a genuine "
                        "absence of a denial control on this path; confirm by hand whether one exists in "
                        "this CMP's preferences layer."
                    ),
                    [autosave_verification],
                    (
                        "Review screenshots and confirm by hand whether a denial control exists on this "
                        "settings path. If it does, add its selector to references/cmp-selectors.json; if "
                        "it does not, that is a UI finding to raise with the site owner."
                    ),
                    certainty="medium",
                    depends_on_scenarios=[],
                ))
            else:
                findings.append(_finding(
                    "denial-autosave-unconfirmed",
                    "Optional categories were switched off but the recorded choice could not be confirmed",
                    "high",
                    (
                        (
                            f"The scanner opened the preferences layer and switched {len(disabled)} "
                            "optional-category toggle(s) off, "
                            if mutated else
                            "The scanner opened the preferences layer, "
                        )
                        + "but neither a post-reload read-back nor a namespaced consent-storage write "
                        "could confirm that the CMP recorded the choice. "
                        f"{autosave_verification.get('note', '')}"
                    ),
                    "Cannot be assessed as a completed denial. No recorded choice is evidenced by this run.",
                    (
                        "No legal inference should be drawn about whether the denial is honoured or "
                        "discarded. The tool cannot tell whether the CMP is persisting the choice "
                        "server-side in a way a browser scan cannot see; this is an observation of "
                        "unconfirmed persistence, not a finding that tracking continued."
                    ),
                    [autosave_verification],
                    "Confirm by hand whether this CMP's settings path persists the choice without a save "
                    "control. If it does not, that is a UI finding to raise with the site owner.",
                    certainty="medium",
                    depends_on_scenarios=[],
                ))
    elif status == "manual_required":
        reject_resolution = resolution.get("reject") or {}
        best_score = reject_resolution.get("best_score")
        candidates_exist = bool(action.get("reject_candidates"))
        findings.append(_finding(
            "denial-control-unresolved",
            "The auditor could not operate a denial choice",
            "high",
            (
                "The scanner did not operate a denial control. "
                + (
                    f"Candidate controls were visible but none reached the confidence threshold "
                    f"(best score {best_score} against a threshold of {reject_resolution.get('threshold')}). "
                    "This is a scanner limitation, not evidence that the page lacks a denial control."
                    if candidates_exist else
                    "No candidate denial control was found in any frame."
                )
            ),
            "Cannot be assessed. No denial was performed, so nothing about post-denial behaviour is evidenced by this run.",
            "No legal inference should be drawn. Where candidates were visible, this is a tooling gap; where none were found, a manual review should confirm whether a denial control exists at all.",
            action.get("reject_candidates", [])[:10] + action.get("settings_candidates", [])[:10],
            "Review the candidate list and screenshots. If a denial control exists, add its selectors to references/cmp-selectors.json so future runs resolve it directly; if none exists, that is itself a UI finding to raise with the site owner.",
            certainty="high",
        ))
    if action.get("direct_accept_available") and status not in {"direct_reject_clicked", "manual_required"}:
        clicks = int(action.get("click_count") or 0)
        findings.append(_finding(
            "asymmetric-choice",
            "Accept was directly available while denial required a different or longer path",
            "high" if clicks > 1 else "medium",
            f"A direct accept control was detected, but denial completed through status '{status}' with approximately {clicks} interaction(s).",
            "Fails the conservative symmetry rule when the more privacy-protective choice takes more steps or is materially less prominent.",
            "California's consent-interface rules expressly address symmetry when consent is sought. Applicability depends on whether the interface is obtaining CCPA consent or processing CCPA requests and on the exact rendered design.",
            (action.get("accept_candidates", [])[:5] + action.get("reject_candidates", [])[:5] + action.get("settings_candidates", [])[:5]),
            "Place 'Accept All' and 'Decline All' in the same layer with comparable size, contrast, wording, and click count.",
            certainty="medium",
            depends_on_scenarios=["denial"],
        ))

    # A5 - a click that Playwright reported as successful but which changed no
    # cookie, storage key, CMP state, or banner visibility has not registered.
    verification = action.get("verification") or {}
    if status in COMPLETED_DENIAL_STATUSES and verification.get("verified") is False:
        findings.append(_finding(
            "denial-not-registered",
            "The denial control was clicked but no consent state change followed",
            "critical",
            "A denial control was operated successfully, yet no cookie, local-storage key, CMP API state, or banner visibility change was observed afterwards. "
            f"{verification.get('note', '')}",
            "Fails the conservative baseline, which requires the choice to be recorded and propagated rather than merely acknowledged in the interface.",
            "A choice the interface offers but does not record is a strong FTC Section 5 deception fact pattern, because the consumer is told the click has an effect it does not have.",
            [verification],
            "Confirm that the consent platform writes and persists a preference on denial, then verify the tag layer reads it.",
            certainty="high",
        ))

    # E3 - measured symmetry, rather than an inference from click counts alone.
    accept_candidates = action.get("accept_candidates") or []
    reject_candidates = action.get("reject_candidates") or []
    if accept_candidates and reject_candidates:
        symmetry = checks.measure_symmetry(accept_candidates[0], reject_candidates[0])
        if symmetry.get("comparable") and not symmetry.get("symmetric"):
            differences = [
                label for label, ok in [
                    ("not in the same layer", symmetry.get("same_layer")),
                    ("different rendered size", symmetry.get("area_equivalent")),
                    ("different background colour", symmetry.get("same_background_color")),
                    ("different font size", symmetry.get("same_font_size")),
                    ("different font weight", symmetry.get("same_font_weight")),
                ] if ok is False
            ]
            findings.append(_finding(
                "measured-asymmetry",
                "Accept and decline controls differ in measured presentation",
                "medium",
                "The rendered accept and decline controls differ on: " + ", ".join(differences) + ".",
                "Fails the symmetry limb of the conservative baseline, which asks for comparable size, contrast, colour, placement, and wording.",
                "California's regulations reject visual prominence that favours acceptance over refusal. Whether they apply depends on whether the interface is seeking CCPA consent.",
                [symmetry],
                "Render both controls in the same layer with equivalent size, colour, contrast, and typography.",
                certainty="high",
                depends_on_scenarios=["denial"],
            ))
        elif symmetry.get("comparable") and symmetry.get("symmetric"):
            findings.append(_finding(
                "measured-symmetry-satisfied",
                "Accept and decline controls are presented symmetrically",
                "informational",
                "The rendered accept and decline controls sit in the same layer with equivalent size, background colour, font size, and font weight. "
                f"Measured contrast ratios: accept {symmetry.get('accept_contrast_ratio')}, decline {symmetry.get('reject_contrast_ratio')}.",
                "Satisfies the symmetry limb of the conservative baseline and matches the regulator's own example of an equal choice.",
                "Recorded so the report distinguishes a presentation problem from an enforcement problem; this is a point in the site's favour.",
                [symmetry],
                "No change needed on symmetry. Keep this in mind if the banner is redesigned.",
                certainty="high",
                depends_on_scenarios=["denial"],
            ))

    if status in COMPLETED_DENIAL_STATUSES:
        later = [cp for cp in denial_result.get("checkpoints", []) if _checkpoint_index(str(cp.get("checkpoint", ""))) >= 3]
        reappeared = [cp for cp in later if _banner_visible(cp)]
        if reappeared:
            findings.append(_finding(
                "banner-reprompt",
                "The consent banner appeared again after denial and refresh or navigation",
                "high",
                f"The banner or its accept/reject controls remained visible at {len(reappeared)} later checkpoint(s) after the denial action.",
                "Fails the preference-persistence portion of the conservative baseline, unless the banner is accurately showing a stored denied status without nagging or resetting the choice.",
                "Repeated prompting can be relevant to dark-pattern analysis; a technical false positive is possible and the screenshots should be reviewed.",
                [{"checkpoint": cp.get("checkpoint"), "url": sanitize_url(str(cp.get("url", ""))), "banner_text": str((cp.get("banner") or {}).get("best_text", ""))[:1200]} for cp in reappeared],
                "Persist the denial preference and ensure later pages honor it without re-prompting unless a valid expiration or material-purpose change requires a new choice.",
                certainty="medium",
                depends_on_scenarios=["denial"],
            ))

    gpc_ad = [r for r in unique_requests if r.get("scenario") == "gpc" and r.get("category") in GPC_RELEVANT_CATEGORIES]
    if gpc_ad:
        strength = _strength_of(gpc_ad)
        findings.append(_finding(
            "gpc-not-honored",
            "Advertising or social-tracking endpoints loaded while GPC was active",
            "critical" if strength in {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER} else "high",
            f"The GPC context sent Sec-GPC: 1 and exposed navigator.globalPrivacyControl=true, yet {len(gpc_ad)} distinct advertising or social-tracking endpoint pattern(s) loaded. "
            f"Strongest evidence observed: {checks.STRENGTH_LABEL.get(strength, strength)}.",
            "Fails the conservative baseline, which treats GPC as an immediate opt-out of sale, sharing, and targeted advertising nationwide.",
            "Potentially relevant in jurisdictions requiring recognized universal opt-out signals. Loading an endpoint is not conclusive proof of sale, sharing, or targeted advertising; payload, contract, and use must be examined.",
            gpc_ad[:30],
            "Map GPC to CMP, client-side tags, server-side tags, account profiles, and downstream vendors. Suppress sale/share/targeted-advertising flows before the first affected transmission.",
            certainty="high",
            applicability_needed="Confirm business coverage, consumer location, the endpoint's use, and whether the recipient is a service provider/contractor or third party.",
            depends_on_scenarios=["gpc"],
            evidence_strength=strength,
        ))

    # C4 - the counterpart finding: tags load but nothing transmits, and the
    # consent signal says denied. That is what a correct transmission-layer
    # implementation looks like, and reporting it as a failure would be wrong.
    for scenario_name in ("denial", "gpc"):
        scenario_result = results.get(scenario_name)
        if not isinstance(scenario_result, dict):
            continue
        scenario_rows = [
            r for r in unique_requests
            if r.get("scenario") == scenario_name and r.get("category") in TRACKING_CATEGORIES
        ]
        if not scenario_rows:
            continue
        transmitted = [r for r in scenario_rows if r.get("evidence_strength") in {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER}]
        consent_mode = (scenario_result.get("consent_mode") or {}).get("summary") or {}
        if transmitted or not consent_mode.get("present"):
            continue
        if not consent_mode.get("all_signals_denied"):
            continue
        findings.append(_finding(
            "consent-enforced-at-transmission",
            f"Tags loaded but no transmission was observed in the {scenario_name} scenario",
            "informational",
            f"In the {scenario_name} scenario {len(scenario_rows)} tracking-related resource(s) loaded, but no request to a known collection "
            f"endpoint was observed, and every Google Consent Mode signal seen carried a denied state "
            f"({', '.join(consent_mode.get('distinct_gcs_values') or []) or 'no gcs value'}). "
            "This is the signature of consent being enforced at the transmission layer rather than by blocking the tag from loading.",
            "Consistent with the baseline's intent. The conservative baseline still prefers not loading nonessential tags at all, because loading discloses IP address, user agent, and referring URL to the vendor.",
            "Reported as a favourable observation, not a failure. Confirm against the tag configuration and a payload review before relying on it, since absence of an observed beacon within the capture window is weaker evidence than a positive observation.",
            [{"scenario": scenario_name, "consent_mode": consent_mode, "sample_requests": scenario_rows[:10]}],
            "No remediation required on this evidence. To strengthen the position, consider blocking nonessential tags from loading at all so no third-party disclosure occurs before a choice.",
            certainty="medium",
            depends_on_scenarios=[scenario_name],
            evidence_strength=checks.STRENGTH_SCRIPT_ONLY,
            id_parts=(scenario_name,),
        ))

    unknown_cookies = {}
    for row in cookie_rows:
        if row.get("category") == "unknown":
            unknown_cookies[_cookie_key(row)] = row
    unknown_third_party = {}
    for row in unique_requests:
        if row.get("category") == "unknown" and row.get("third_party"):
            unknown_third_party[(row.get("host"), row.get("path"))] = row
    if unknown_cookies or unknown_third_party:
        findings.append(_finding(
            "unresolved-purposes",
            "Unresolved cookie or endpoint purposes require research",
            "medium",
            f"The evidence contains {len(unknown_cookies)} unclassified cookie(s) and {len(unknown_third_party)} unclassified third-party endpoint pattern(s).",
            "Unknown processing is not presumed necessary under the conservative baseline.",
            "No legal conclusion should be assigned until the controller identifies purpose, data fields, recipient, contract status, retention, and whether the processing is sale/share/targeted advertising or sensitive-data use.",
            list(unknown_cookies.values())[:20] + list(unknown_third_party.values())[:20],
            "Research primary vendor documentation and code/configuration; obtain a written purpose and data-flow confirmation from the site owner and vendor.",
            certainty="high",
        ))

    insecure_auth = []
    for row in cookie_rows:
        if row.get("secure") is False and AUTH_COOKIE.search(str(row.get("name", ""))):
            insecure_auth.append(row)
    if insecure_auth:
        findings.append(_finding(
            "insecure-auth-cookie",
            "Potential session or authentication cookies lacked the Secure attribute",
            "high",
            f"{len({_cookie_key(r) for r in insecure_auth})} cookie(s) with session/authentication-like names were observed without Secure.",
            "Fails the security hygiene portion of the conservative baseline for HTTPS sites.",
            "This is primarily a security configuration issue rather than a cookie-consent conclusion. Confirm actual function before treating the name heuristic as definitive.",
            insecure_auth[:20],
            "Set Secure on cookies used for authentication or session state and review HttpOnly and SameSite settings according to the application threat model.",
            certainty="medium",
        ))

    # E2 - identifiers baked into the served markup, seen by every visitor.
    embedded: list[dict[str, Any]] = []
    for scenario_result in results.values():
        if not isinstance(scenario_result, dict):
            continue
        embedded.extend((scenario_result.get("page_scan") or {}).get("embedded_identifiers") or [])
    if embedded:
        unique_embedded = {json.dumps(item, sort_keys=True, default=str): item for item in embedded}
        samples = list(unique_embedded.values())
        dates = sorted({
            part.get("identifier_created")
            for item in samples for part in (item.get("decoded") or [])
            if part.get("identifier_created")
        })
        findings.append(_finding(
            "embedded-identifier",
            "Durable identifiers are hardcoded into the served markup",
            "medium",
            f"{len(samples)} embedded identifier pattern(s) were found in the page source, served identically to every visitor"
            + (f". The oldest recovered identifier was created {dates[0]}." if dates else "."),
            "Fails the evidence and governance limb of the conservative baseline: one person's identifier is republished to everyone.",
            "Low severity but real. A staff member's persistent identifier is exposed in public page source and propagated on outbound clicks, and analytics attribution is corrupted because every visitor stitches to the same client id.",
            samples[:20],
            "Strip _gl, _ga, _ga_*, _gcl_au, and click identifiers from CMS-managed links. If cross-domain measurement is wanted, configure it so the linker is generated per visitor rather than pasted into content.",
            certainty="high",
        ))

    # E1 - a separate sale/share mechanism, which a cookie banner does not supply.
    rights_scan = None
    for scenario_name in ("baseline", "denial"):
        scenario_result = results.get(scenario_name)
        if not isinstance(scenario_result, dict):
            continue
        page_scan = scenario_result.get("page_scan") or {}
        if page_scan.get("links") is not None:
            checkpoint = (scenario_result.get("checkpoints") or [{}])[0]
            rights_scan = checks.scan_rights_mechanisms(
                page_scan.get("page_text", ""),
                page_scan.get("links") or [],
                checkpoint.get("browser_state") or {},
            )
            break
    if rights_scan and not rights_scan.get("mechanism_observed"):
        findings.append(_finding(
            "rights-mechanism-absent",
            "No separate sale/share or privacy-choices mechanism was observed",
            "medium",
            "The scanned pages contained no 'Do Not Sell', 'Do Not Share', 'Your Privacy Choices', or opt-out link, and no USP or GPP consent API was exposed.",
            "Fails the separate-rights limb of the conservative baseline, which does not treat a cookie banner as a sale/share opt-out.",
            "California's position is that cookie controls address collection and are not by themselves an acceptable sale/share opt-out. This finding is conditional: if the operator does not sell or share as defined, no such mechanism is required and it falls away.",
            [rights_scan],
            "Complete the coverage and sale/share analysis first, since it determines whether anything is required. If it is, add a conspicuous link that operates independently of the cookie banner.",
            certainty="medium",
            applicability_needed="Whether the operator meets state coverage thresholds, whether it sells or shares personal information or processes it for targeted advertising, and the contractual role of each recipient.",
        ))

    # E4 - does the preference survive into a brand-new browser context?
    persistence = results.get("persistence")
    if isinstance(persistence, dict) and persistence.get("ran") and persistence.get("banner_reprompted"):
        findings.append(_finding(
            "persistence-across-session",
            "The denial preference did not survive into a fresh browser context",
            "high",
            "A stored post-denial state was replayed into a new context and the consent banner prompted again.",
            "Fails the persistence limb of the conservative baseline, which asks that a choice hold across refreshes, navigation, and reasonable session boundaries.",
            "Repeated prompting after a recorded denial can be relevant to dark-pattern analysis, particularly where the effect is to wear the visitor down into accepting.",
            [{k: v for k, v in persistence.items() if k != "scenario_result"}],
            "Persist the preference with an appropriate lifetime and confirm the consent platform reads it on a cold start.",
            certainty="medium",
            depends_on_scenarios=["denial"],
        ))

    # D4 - endpoints that appeared in only some repeats are not settled fact.
    stability = results.get("baseline_stability")
    if isinstance(stability, dict) and stability.get("unstable"):
        findings.append(_finding(
            "unstable-tag-behaviour",
            "Some endpoints appeared in only a subset of identical baseline runs",
            "informational",
            f"Across {stability.get('run_count')} identical baseline runs, {len(stability.get('unstable') or [])} of "
            f"{stability.get('total_distinct')} distinct endpoints appeared in some runs but not others.",
            "Not a baseline pass or fail. It bears on how confidently any other finding can be stated.",
            "Variation between identical runs suggests an A/B test, a geo or cohort experiment, or a flaky tag. Findings touching these endpoints should be treated as provisional until a run reproduces them consistently.",
            [{"unstable_endpoints": (stability.get("unstable") or [])[:40], "run_count": stability.get("run_count")}],
            "Re-run the audit to see whether these endpoints reproduce, and check for experiment frameworks that vary tag behaviour between visitors.",
            certainty="high",
        ))

    for scenario, result in results.items():
        if isinstance(result, dict) and result.get("errors"):
            findings.append(_finding(
                "capture-errors",
                f"The {scenario} scenario encountered capture errors",
                "medium",
                f"The scenario recorded {len(result.get('errors') or [])} error(s); affected evidence may be incomplete.",
                "An incomplete capture cannot establish compliance.",
                "No adverse legal inference should be drawn solely from a tooling error.",
                result.get("errors")[:10],
                "Review the errors, repeat the scenario, and preserve both runs if the issue is intermittent.",
                certainty="high",
                id_parts=(scenario,),
            ))

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
    findings.sort(key=lambda f: (severity_order.get(str(f.get("severity")), 9), str(f.get("id"))))
    return findings


# Evidence strong enough to gate a build on. `script_loaded_only` is deliberately
# excluded: a tag can load and still have its transmission gated (Google Consent
# Mode does exactly this), which the report treats as a favourable informational
# finding, not a failure. Gating CI on script loads alone would fail correct
# implementations and get disabled within a week.
CONFIRMED_TRANSMISSION_STRENGTHS = {checks.STRENGTH_BEACON, checks.STRENGTH_IDENTIFIER}


def preconsent_tracking_assertion_hits(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evidence rows that should trip `--assert-no-preconsent-tracking`.

    This reads directly off the `pre-consent-tracking` finding produced by
    `generate_findings` - the same category set (`TRACKING_CATEGORIES`), the
    same baseline-scenario scoping, and the same validity gating (a finding
    that was suppressed because the baseline scenario did not complete never
    reaches here). That is deliberate: the CI gate and the report finding must
    use one categorisation, not two that can quietly drift apart.

    It reads `all_evidence` rather than `evidence`: the finding's `evidence`
    list is truncated to the first 20 rows for display, and a confirmed
    transmission past that cutoff must still trip the gate. `all_evidence`
    carries the complete, untruncated row set (falling back to `evidence` if a
    finding has nothing longer to offer).

    The one condition this adds on top of the finding is the evidence_strength
    threshold: only `beacon_observed` or `identifier_transmitted` rows count.
    See `CONFIRMED_TRANSMISSION_STRENGTHS`.
    """
    hits: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("check_type") != "pre-consent-tracking":
            continue
        rows = finding.get("all_evidence")
        if rows is None:
            rows = finding.get("evidence") or []
        for row in rows:
            if row.get("evidence_strength") in CONFIRMED_TRANSMISSION_STRENGTHS:
                hits.append(row)
    return hits


def _summary_status(findings: list[dict[str, Any]], invalid_scenarios: dict[str, Any] | None = None) -> str:
    """Overall verdict.

    An incomplete run is reported as incomplete rather than clean: a scenario
    that never ran produces no findings, and silence from a check that did not
    execute must never read as a pass.
    """
    severities = Counter(str(f.get("severity")) for f in findings)
    prefix = "INCOMPLETE - " if invalid_scenarios else ""
    if severities.get("critical"):
        return f"{prefix}Critical issues observed"
    if severities.get("high"):
        return f"{prefix}High-risk issues observed"
    if severities.get("medium"):
        return f"{prefix}Review required"
    if invalid_scenarios:
        return "INCOMPLETE - no verdict; required scenarios did not complete"
    return "No material issue observed in this limited scan"


def render_invalidity_banner(invalid_scenarios: dict[str, Any], suppressed: list[dict[str, Any]]) -> str:
    """Markdown warning that leads the report when a scenario did not complete."""
    if not invalid_scenarios:
        return ""
    lines = [
        "> ## RUN INCOMPLETE - READ BEFORE RELYING ON THIS REPORT",
        ">",
        "> One or more scenarios did not complete a verified interaction. Findings that would have",
        "> depended on them have been withheld rather than reported, because the evidence they would",
        "> rest on was never captured.",
        ">",
    ]
    for name, detail in invalid_scenarios.items():
        lines.append(f"> - **{name}**: {detail.get('invalid_reason') or 'did not complete'}")
    if suppressed:
        lines.append(">")
        lines.append(f"> {len(suppressed)} finding(s) withheld. See `suppressed-findings.json`:")
        for item in suppressed[:10]:
            lines.append(f">   - `{item.get('id')}` - {item.get('title')}")
    lines.append(">")
    lines.append("> Absence of a finding below is not evidence of absence of the underlying issue.")
    return "\n".join(lines) + "\n"


def _relative(path: str | None, root: Path) -> str | None:
    if not path:
        return None
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path


def is_scenario(result: Any) -> bool:
    """Is this results entry a captured scenario?

    `results` also carries summaries (`baseline_stability`), a list of repeat
    runs, and the persistence-check wrapper. Those must not be rendered as
    scenarios or they show up as empty rows implying a scenario ran and found
    nothing.
    """
    return isinstance(result, dict) and "checkpoints" in result


def _evidence_summary(results: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario, result in results.items():
        if not is_scenario(result):
            continue
        rows.append({
            "scenario": scenario,
            "action_status": (result.get("action_result") or {}).get("status"),
            "checkpoints": len(result.get("checkpoints") or []),
            "requests": len((result.get("events") or {}).get("requests") or []),
            "raw_har": _relative(result.get("raw_har"), root),
            "sanitized_har": _relative(result.get("sanitized_har"), root),
            "errors": len(result.get("errors") or []),
        })
    return rows


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int | None = None) -> str:
    use = rows if limit is None else rows[:limit]
    if not use:
        return "_None observed._\n"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(escape_markdown_cell(row.get(key, "")) for key, _ in columns) + " |" for row in use]
    return "\n".join([header, separator, *body]) + "\n"


def _first_screenshot(results: dict[str, Any], scenario: str, root: Path, contains: str) -> str | None:
    result = results.get(scenario, {})
    for checkpoint in result.get("checkpoints", []) or []:
        for screenshot in checkpoint.get("screenshots", []) or []:
            if contains in Path(screenshot).name:
                return _relative(screenshot, root)
    return None


EVIDENCE_STRENGTH_EXPLAINER = (
    "**How to read the evidence in this report.** Every request observation is graded. "
    "*Script loaded only* means a tag was fetched: the vendor necessarily received the visitor's IP "
    "address, user agent, and referring URL, but no measurement event is shown to have been sent. "
    "*Collection endpoint contacted* means a request reached a known measurement endpoint. "
    "*Identifier transmitted* means such a request also carried a value matching a durable identifier. "
    "The distinction matters: a correct implementation can deliberately load a tag and then suppress or "
    "redact its transmission (Google Consent Mode works this way), so a script load on its own is not "
    "evidence that consent was ignored. Conversely, a script load is still a third-party disclosure."
)


def render_markdown_report(
    root: Path,
    target_url: str,
    metadata: dict[str, Any],
    findings: list[dict[str, Any]],
    cookie_rows: list[dict[str, Any]],
    request_rows: list[dict[str, Any]],
    results: dict[str, Any],
    validity: dict[str, dict[str, Any]] | None = None,
    suppressed: list[dict[str, Any]] | None = None,
) -> str:
    validity = validity or {}
    suppressed = suppressed or []
    invalid = {name: v for name, v in validity.items() if not v.get("valid", True)}
    status = _summary_status(findings, invalid)
    counts = Counter(str(f.get("severity")) for f in findings)

    cmp_names = sorted({
        str((r.get("cmp") or {}).get("name"))
        for r in results.values()
        if isinstance(r, dict) and r.get("cmp")
    })
    exercised = next(
        (r.get("exercises") for r in results.values() if isinstance(r, dict) and r.get("exercises")),
        {},
    ) or {}
    forms = exercised.get("forms") or {}
    search = exercised.get("search") or {}

    lines = ["# Cookie Banner, Tracking, and Privacy Preference Audit", ""]
    banner_block = render_invalidity_banner(invalid, suppressed)
    if banner_block:
        lines.extend([banner_block, ""])

    lines.extend([
        "## 1. Executive summary",
        "",
        f"**Target:** {target_url}  ",
        f"**Audit completed:** {metadata.get('completed_at')}  ",
        f"**Egress region:** {metadata.get('egress_region') or metadata.get('location_label') or 'Not established'}  ",
        f"**Consent platform:** {', '.join(cmp_names) if cmp_names else 'Not identified'}  ",
        f"**Overall result:** {status}",
        "",
        f"This limited, logged-out browser audit produced {len(findings)} reported finding(s): "
        f"{counts.get('critical', 0)} critical, {counts.get('high', 0)} high, {counts.get('medium', 0)} medium, "
        f"{counts.get('low', 0)} low, and {counts.get('informational', 0)} informational."
        + (f" A further {len(suppressed)} finding(s) were withheld as unsupported; see section 12." if suppressed else ""),
        "",
        "> This report is technical evidence and issue spotting, not a legal opinion. It does not prove what "
        "data a vendor ultimately uses, whether a recipient is a contracted service provider, whether a law "
        "covers the operator, or what happens in other geographies, devices, browsers, authenticated sessions, "
        "or server-side systems. A clean result is reported as *no material issue observed in this limited "
        "test*, never as compliance.",
        "",
        EVIDENCE_STRENGTH_EXPLAINER,
        "",
        "## 2. Scope and authorization",
        "",
        f"| Item | Value |",
        f"|---|---|",
        f"| Target URL | {target_url} |",
        f"| Audit window | {metadata.get('started_at')} to {metadata.get('completed_at')} |",
        f"| Tool version | {metadata.get('tool')} {metadata.get('tool_version')} |",
        f"| Run fingerprint | `{metadata.get('run_fingerprint', 'n/a')}` |",
        f"| Browser | {metadata.get('browser_executable')} |",
        f"| Viewport | {metadata.get('viewport')} |",
        f"| Locale / timezone | {metadata.get('locale')} / {metadata.get('timezone') or 'host default'} |",
        f"| Egress region | {metadata.get('egress_region') or metadata.get('location_label') or 'Not established'} |",
        f"| Thoroughness profile | {metadata.get('profile')} |",
        f"| Pages per scenario | {metadata.get('pages', 0)} |",
        f"| Baseline repeats | {metadata.get('baseline_repeats', 0)} |",
        f"| Form fields exercised | {len(forms.get('fields_filled') or [])} |",
        f"| Form submitted | {'YES - explicitly enabled' if forms.get('submitted') else 'No'} |",
        f"| Site search exercised | {'Yes' if search.get('submitted') else 'No'} |",
        "",
        "**Exclusions.** Mobile web and native apps; authenticated areas; other geographies; other browsers and "
        "cohorts; server-side tagging and offline transfers; vendor contracts and data processing agreements.",
        "",
        "## 3. Methodology",
        "",
        "- Separate pristine browser contexts for every scenario. Playwright launches a throwaway browser "
        "profile and each context starts with no cookies or storage; section 13 records the assertion that "
        "each context was empty before navigation.",
        "- Consent controls are resolved from a known-CMP selector table first and text scoring second, so a "
        "plain `Accept`/`Decline` button is reachable regardless of wording.",
        "- Every consent click is verified against cookie, storage, CMP-API, and banner-visibility state. A "
        "scenario whose required interaction did not complete and verify is marked invalid, and findings that "
        "would depend on it are withheld rather than reported.",
        "- Pages are dwelled on and scrolled in stages, and form fields and site search are exercised, so tags "
        "that fire on engagement rather than load are observed.",
        "- The baseline is repeated so endpoints appearing in only some runs are reported as unstable rather "
        "than as settled fact.",
        "- GPC is expressed as `Sec-GPC: 1` and `navigator.globalPrivacyControl = true` before page scripts run.",
        "- Raw HAR and raw browser state are retained locally as sensitive evidence; shareable copies redact "
        "values while retaining names and attributes.",
        "",
        "## 4. Banner and interaction analysis",
        "",
    ])

    denial = results.get("denial") if isinstance(results.get("denial"), dict) else {}
    denial_action = (denial or {}).get("action_result") or {}
    banner_text = ""
    for checkpoint in (denial or {}).get("checkpoints", []) or []:
        banner_text = str((checkpoint.get("banner") or {}).get("best_text", ""))
        if banner_text:
            break
    if banner_text:
        lines.extend(["**Banner text, as displayed:**", "", "> " + banner_text[:2000].replace("\n", "\n> "), ""])
    resolution = denial_action.get("resolution") or {}
    lines.extend([
        f"- Consent platform: {', '.join(cmp_names) if cmp_names else 'not identified'}",
        f"- Denial control resolved via: {(resolution.get('reject') or {}).get('path', 'not resolved')}"
        + (f" (`{(resolution.get('reject') or {}).get('matched_selector')}`)" if (resolution.get('reject') or {}).get('matched_selector') else ""),
        f"- Accept control resolved via: {(resolution.get('accept') or {}).get('path', 'not resolved')}",
        f"- Denial status: `{denial_action.get('status')}` after {denial_action.get('click_count', 0)} interaction(s)",
        f"- Choice verified as registered: {(denial_action.get('verification') or {}).get('verified')}"
        + (f" - {(denial_action.get('verification') or {}).get('note', '')}" if (denial_action.get('verification') or {}).get('note') else ""),
        "",
        "Automated accessibility testing is limited to keyboard-focusability, tab order, and computed contrast. "
        "Screen-reader validation still requires a manual pass.",
        "",
        "## 5. Findings",
        "",
    ])

    if not findings:
        lines.extend([
            "No material issue was identified among the checks that completed. That is not a certification of "
            "compliance, and it says nothing about any scenario listed as incomplete above.",
            "",
        ])
    for finding in findings:
        lines.extend([
            f"### {finding.get('id')} - {finding.get('title')}",
            "",
            f"**Severity:** {str(finding.get('severity')).upper()}  ",
            f"**Certainty:** {finding.get('certainty')}  ",
        ])
        if finding.get("evidence_strength"):
            lines.append(f"**Evidence strength:** {finding.get('evidence_strength_label')}  ")
        if finding.get("depends_on_scenarios"):
            lines.append(f"**Depends on scenarios:** {', '.join(finding.get('depends_on_scenarios'))}  ")
        lines.extend([
            "",
            f"**Observed fact.** {finding.get('observation')}",
            "",
            f"**Strict U.S. composite baseline.** {finding.get('strict_us_composite_baseline')}",
            "",
            f"**Potential legal relevance.** {finding.get('potential_legal_relevance')}",
            "",
        ])
        if finding.get("evidence_strength_caveat"):
            lines.extend([f"**Evidence caveat.** {finding.get('evidence_strength_caveat')}", ""])
        if finding.get("applicability_needed"):
            lines.extend([f"**Applicability facts needed.** {finding.get('applicability_needed')}", ""])
        lines.extend([f"**Recommendation.** {finding.get('recommendation')}", ""])
        evidence = finding.get("evidence") or []
        if evidence:
            lines.extend(["**Evidence.**", "", "```json", json.dumps(evidence[:6], indent=2, ensure_ascii=False, default=str)[:12000], "```", ""])

    # ---- 6. Scenario results -------------------------------------------------
    evidence_rows = _evidence_summary(results, root)
    lines.extend([
        "## 6. Scenario results",
        "",
        _markdown_table(evidence_rows, [
            ("scenario", "Scenario"), ("action_status", "Action status"), ("checkpoints", "Checkpoints"),
            ("requests", "Requests"), ("sanitized_har", "Shareable HAR"), ("raw_har", "Raw HAR (sensitive)"), ("errors", "Errors")
        ]),
        "",
    ])
    if validity:
        lines.extend([
            "| Scenario | Required interaction | Completed | Verified | Valid |",
            "|---|---|---|---|---|",
        ])
        for name, detail in validity.items():
            lines.append(
                f"| {name} | {detail.get('required_interaction') or 'none'} | "
                f"{detail.get('interaction_completed')} | {detail.get('verification_passed')} | "
                f"{'YES' if detail.get('valid') else '**NO**'} |"
            )
        lines.append("")

    for scenario, label in (("baseline", "Baseline before any choice"), ("denial", "Denial flow"), ("gpc", "GPC flow")):
        shot = _first_screenshot(results, scenario, root, "viewport.png")
        if shot:
            lines.extend([f"### {label}", "", f"![{label}]({shot})", ""])

    # ---- 7. Inventory --------------------------------------------------------
    dedup_cookies: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in cookie_rows:
        key = (str(row.get("scenario")), str(row.get("name")), str(row.get("domain")), str(row.get("category")))
        dedup_cookies[key] = row
    lines.extend([
        "## 7. Inventory",
        "",
        _markdown_table(list(dedup_cookies.values()), [
            ("scenario", "Scenario"), ("name", "Cookie"), ("domain", "Domain"), ("category", "Category"),
            ("vendor", "Vendor"), ("necessity", "Necessity"), ("secure", "Secure"), ("http_only", "HttpOnly"), ("same_site", "SameSite")
        ], limit=100),
        "",
        "The complete inventories are in `cookie-inventory.csv` and `request-inventory.csv`; appendix A below "
        "groups requests by host with their evidence strength.",
        "",
    ])

    # ---- 8. GPC and separate statutory rights --------------------------------
    gpc_result = results.get("gpc") if isinstance(results.get("gpc"), dict) else {}
    gpc_consent_mode = ((gpc_result or {}).get("consent_mode") or {}).get("summary") or {}
    lines.extend([
        "## 8. Global Privacy Control and separate statutory rights",
        "",
        "GPC and cookie consent are separate mechanisms and are analysed separately here. GPC is expressed by "
        "HTTP header and JavaScript object before page scripts run, so this scenario does not depend on any "
        "click succeeding.",
        "",
        f"- Consent Mode signals seen in the GPC scenario: {gpc_consent_mode.get('signal_count', 0)}"
        + (f" (values: {', '.join(gpc_consent_mode.get('distinct_gcs_values') or [])})" if gpc_consent_mode.get("distinct_gcs_values") else ""),
        f"- All observed Consent Mode signals denied: {gpc_consent_mode.get('all_signals_denied')}",
        "",
        "A cookie banner is not by itself a sale/share opt-out. Whether a separate mechanism is required "
        "depends on coverage and on whether the operator sells or shares, which a scan cannot establish.",
        "",
        "## 9. Legal issue-spotting matrix",
        "",
        _markdown_table(checks.build_issue_matrix(findings), [
            ("authority", "Authority"), ("requirement", "Requirement or theory"),
            ("evidence", "Observed evidence"), ("missing_facts", "Missing applicability facts"),
        ]),
        "",
        "Include only authorities relevant to the operator, audience, data, and observed conduct. This table is "
        "a prompt for counsel, not a conclusion.",
        "",
    ])

    # ---- 10. Unknowns --------------------------------------------------------
    unknown_cookie_rows = list({(r.get("name"), r.get("domain")): r for r in cookie_rows if r.get("category") == "unknown"}.values())
    unknown_request_rows = list({(r.get("host"), r.get("path")): r for r in request_rows if r.get("category") == "unknown" and r.get("third_party")}.values())
    script_only_rows = [r for r in request_rows if r.get("evidence_strength") == checks.STRENGTH_SCRIPT_ONLY and r.get("category") in TRACKING_CATEGORIES]
    lines.extend([
        "## 10. Unknowns and research queue",
        "",
        "Unknown items are not presumed compliant or noncompliant. Research primary vendor documentation, "
        "inspect the site's code and tag-manager configuration, and obtain written purpose, recipient, and "
        "retention confirmation.",
        "",
        f"1. **Do the loaded tags actually transmit?** {len(script_only_rows)} tracking-related observation(s) "
        "are graded *script loaded only*. Re-run with a longer window and inspect payloads to resolve whether "
        "these represent suppressed transmission or merely unobserved transmission.",
        "2. **Coverage analysis** - which state privacy laws apply to the operator?",
        "3. **Sale/share determination** and the contractual role of each recipient.",
        "4. **Policy text review** - do the cookie and privacy policies describe the observed behaviour?",
        "5. **Geographic variance** - this run used one egress region.",
        "",
        "### Unknown cookies",
        "",
        _markdown_table(unknown_cookie_rows, [("name", "Cookie"), ("domain", "Domain"), ("scenario", "Scenario"), ("checkpoint", "First observed checkpoint")], limit=100),
        "",
        "### Unknown third-party endpoints",
        "",
        _markdown_table(unknown_request_rows, [("host", "Host"), ("path", "Path"), ("scenario", "Scenario"), ("phase", "Phase")], limit=100),
        "",
        "## 11. Remediation plan",
        "",
        "| Priority | Action | Retest criterion |",
        "|---|---|---|",
        "| 1 | Stop optional transmissions before any choice | Baseline context loads no advertising, social, or session-replay resources |",
        "| 2 | Honour denial across the tag layer, not only in the consent platform | After denial in a fresh context, no request to those hosts |",
        "| 3 | Honour GPC before the first affected transmission | Fresh GPC context with no interaction produces no such requests |",
        "| 4 | Provide same-layer symmetric choices | Measured size, colour, and typography equivalent |",
        "| 5 | Persist and propagate the preference | Choice survives refresh, navigation, and a fresh context |",
        "| 6 | Reconcile banner, notice, CMP, tag manager, and vendors | Banner text matches observed behaviour |",
        "| 7 | Add consent-regression testing to the release process | A scheduled re-audit reproduces the clean result |",
        "",
    ])

    # ---- 12. Withheld findings ----------------------------------------------
    lines.extend(["## 12. Withheld findings", ""])
    if suppressed:
        lines.extend([
            "The following findings were generated but **withheld** because they depend on a scenario that did "
            "not complete a verified interaction. They are recorded here so their absence from section 5 is "
            "visible rather than silent.",
            "",
            "| Finding | Title | Blocking scenario |",
            "|---|---|---|",
        ])
        for item in suppressed:
            blockers = ", ".join(b.get("scenario", "") for b in item.get("blocking_scenarios") or [])
            lines.append(f"| `{item.get('id')}` | {escape_markdown_cell(item.get('title'))} | {blockers} |")
        lines.extend(["", "Full detail is in `suppressed-findings.json`.", ""])
    else:
        lines.extend(["No findings were withheld: every scenario a finding depended on completed and verified.", ""])

    # ---- 13. Limitations and integrity ---------------------------------------
    isolation_rows = [
        (name, r.get("isolation_assertion") or {})
        for name, r in results.items()
        if isinstance(r, dict) and r.get("isolation_assertion")
    ]
    lines.extend([
        "## 13. Limitations, integrity, and evidence index",
        "",
        "A single scan is a point-in-time, single-region, logged-out, desktop-browser sample. It cannot "
        "establish statutory coverage or exemption, whether a visitor is protected by a particular law, "
        "whether a recipient is a service provider under contract, downstream use, server-side or offline "
        "transfers, consent records held in back-end systems, whether a wiretap or pen-register claim is "
        "viable, or whether behaviour is identical in every region, browser, device, or experiment cohort.",
        "",
        "### Context isolation assertions",
        "",
        "Each scenario ran in a fresh browser context on a throwaway browser profile. The following was "
        "asserted before navigation in each case:",
        "",
        "| Scenario | Cookies at start | localStorage keys | sessionStorage keys | Clean |",
        "|---|---|---|---|---|",
    ])
    for name, assertion in isolation_rows:
        if not assertion.get("checked"):
            lines.append(f"| {name} | - | - | - | seeded deliberately (persistence check) |")
        else:
            lines.append(
                f"| {name} | {assertion.get('cookie_count')} | {assertion.get('local_storage_keys')} | "
                f"{assertion.get('session_storage_keys')} | {'yes' if assertion.get('clean') else '**no**'} |"
            )
    policies = results.get("policies") or {}
    policy_records = policies.get("records") or []
    if policy_records:
        lines.extend([
            "",
            "### Archived policy documents",
            "",
            "The site's own linked policies, retrieved and stored verbatim so that what the site "
            "*said* can be read beside what it *did*. **No comparison has been made and no finding "
            "here derives from this text** - reading it against the observed behaviour is a job for "
            "a reviewer, not for this tool.",
            "",
            "| Kind | Source | Retrieved | Archived |",
            "|---|---|---|---|",
        ])
        for record in policy_records:
            status = "yes" if record.get("archived") else f"no - {record.get('skipped_reason') or 'unknown'}"
            lines.append(
                f"| {escape_markdown_cell(str(record.get('kind', '')))} "
                f"| {escape_markdown_cell(str(record.get('url', ''))[:110])} "
                f"| {escape_markdown_cell(str(record.get('retrieved_at', '')))} "
                f"| {escape_markdown_cell(status)} |"
            )
        lines.extend([
            "",
            f"Archived {policies.get('archived', 0)} of {policies.get('attempted', 0)} candidate documents "
            "into `evidence-shareable/policies/`. Each file carries its source URL, retrieval timestamp, "
            "and a SHA-256 of the text.",
        ])

    lines.extend([
        "",
        "### Evidence index",
        "",
        "| Path | Contents | Handling |",
        "|---|---|---|",
        "| `evidence-private/` | Raw HAR and raw browser state | **Sensitive** - unredacted identifiers and headers |",
        "| `evidence-shareable/` | Sanitized HAR, redacted state, screenshots, event logs | Suitable for collaboration |",
        "| `cookie-inventory.csv`, `request-inventory.csv` | Full inventories with evidence strength | Shareable |",
        "| `audit-data.json`, `findings.json` | Structured results | Shareable |",
        "| `suppressed-findings.json` | Findings withheld as unsupported | Shareable |",
        "| `evidence-shareable/policies/` | Archived text of the site's linked policies | Shareable - reference only, no conclusion drawn |",
        "| `manifest.sha256` | Integrity hashes | Verify before relying on the bundle |",
        "",
        "## 14. Conclusion",
        "",
        f"Overall result: **{status}**. "
        + (
            "Required scenarios did not complete, so this run does not support a verdict on the questions those "
            "scenarios exist to answer. Re-run after addressing the cause noted at the top of this report."
            if invalid else
            "The findings above reflect the checks that completed. Re-run after remediation into a new output "
            "directory, preserving this bundle, and compare with `compare_runs.py`."
        ),
        "",
        "This report is technical evidence and legal issue spotting. It is not a compliance certification, and "
        "no finding here is a legal conclusion that any law has been violated.",
        "",
        "---",
        "",
        "## Appendix A - requests by host and evidence strength",
        "",
    ])

    by_host: dict[str, dict[str, Any]] = {}
    for row in request_rows:
        host = str(row.get("host") or "")
        if not host:
            continue
        entry = by_host.setdefault(host, {
            "host": host, "vendor": row.get("vendor"), "category": row.get("category"),
            "third_party": row.get("third_party"), "count": 0, "scenarios": set(), "strengths": [],
        })
        entry["count"] += 1
        entry["scenarios"].add(str(row.get("scenario")))
        entry["strengths"].append(str(row.get("evidence_strength") or ""))
    appendix_rows = []
    for entry in by_host.values():
        appendix_rows.append({
            **entry,
            "scenarios": ", ".join(sorted(entry["scenarios"])),
            "strongest": checks.STRENGTH_LABEL.get(checks.strongest(entry["strengths"]), "-"),
        })
    appendix_rows.sort(key=lambda r: (-r["count"], r["host"]))
    lines.extend([
        _markdown_table(appendix_rows, [
            ("host", "Host"), ("vendor", "Vendor"), ("category", "Category"),
            ("third_party", "Third party"), ("count", "Requests"), ("scenarios", "Scenarios"),
            ("strongest", "Strongest evidence"),
        ], limit=250),
        "",
        "## Appendix B - consent state by scenario",
        "",
        "| Scenario | CMP | Denial status | Verified | Consent Mode signals |",
        "|---|---|---|---|---|",
    ])
    for name, result in results.items():
        if not isinstance(result, dict) or "action_result" not in result:
            continue
        action_result = result.get("action_result") or {}
        summary = (result.get("consent_mode") or {}).get("summary") or {}
        lines.append(
            f"| {name} | {(result.get('cmp') or {}).get('name', '-')} | `{action_result.get('status', '-')}` | "
            f"{(action_result.get('verification') or {}).get('verified', '-')} | {summary.get('signal_count', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_html_report(markdown_like_data: dict[str, Any], results: dict[str, Any], root: Path) -> str:
    """Render the report HTML from the same Markdown the .md file contains.

    Deriving all three artefacts (Markdown, HTML, PDF) from one source removes
    the drift that comes from maintaining a parallel HTML template, and means a
    new report section appears everywhere at once.
    """
    findings = markdown_like_data["findings"]
    metadata = markdown_like_data["metadata"]
    target_url = markdown_like_data["target_url"]
    validity = markdown_like_data.get("validity") or {}
    invalid = {name: v for name, v in validity.items() if not v.get("valid", True)}
    status = _summary_status(findings, invalid)
    body = markdown_to_html(markdown_like_data.get("markdown") or "")

    def e(value: Any) -> str:
        return html.escape(str(value if value is not None else ""))

    warning = ""
    if invalid:
        warning = (
            '<div class="alert"><strong>RUN INCOMPLETE.</strong> '
            + e(", ".join(invalid)) +
            " did not complete a verified interaction. Findings depending on them were withheld, "
            "so absence of a finding is not evidence of absence.</div>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cookie Banner Audit - {e(target_url)}</title>
<style>
:root{{--ink:#17212b;--muted:#5b6570;--line:#d9dee3;--paper:#fff;--wash:#f4f6f8;--critical:#8b1e2d;--high:#a44716;--medium:#7a5c00;--accent:#204b70}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--wash);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}
main{{max-width:1120px;margin:32px auto;background:var(--paper);padding:48px 56px;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
h1{{font-size:32px;line-height:1.15;margin:0 0 6px}}
h2{{margin-top:38px;border-bottom:1px solid var(--line);padding-bottom:8px;font-size:23px;page-break-after:avoid}}
h3{{margin:26px 0 10px;font-size:18px;page-break-after:avoid}}
h4{{margin:18px 0 8px;font-size:15px;color:var(--muted)}}
p{{margin:10px 0}}
blockquote{{border-left:4px solid var(--accent);padding:12px 16px;background:#eef4f9;margin:16px 0}}
blockquote ul{{margin:8px 0 0 18px}}
.alert{{border-left:6px solid var(--critical);background:#fdf0f1;padding:16px 18px;margin:20px 0;font-size:15px}}
pre{{white-space:pre-wrap;overflow:auto;background:#111820;color:#e9eef2;padding:14px;font-size:11.5px;border-radius:3px}}
code{{background:var(--wash);padding:1px 4px;border-radius:3px;font-size:12.5px}}
pre code{{background:none;padding:0;color:inherit;font-size:11.5px}}
.table-wrap{{overflow-x:auto;margin:14px 0}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th,td{{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}}
th{{background:var(--wash)}}
img{{max-width:100%;height:auto;border:1px solid var(--line);margin:10px 0}}
hr{{border:0;border-top:2px solid var(--line);margin:34px 0}}
ul{{margin:10px 0 10px 22px}} li{{margin:4px 0}}
.small{{color:var(--muted);font-size:13px}}
@media print{{
  body{{background:#fff;font-size:10.5pt}}
  main{{box-shadow:none;margin:0;max-width:none;padding:0}}
  h2{{margin-top:22px}}
  pre{{background:#f4f6f8;color:#17212b;border:1px solid var(--line);font-size:8pt}}
  table{{font-size:8.5pt}}
  blockquote,.alert,table,pre,h2,h3{{page-break-inside:avoid}}
}}
</style></head>
<body><main>
<p class="small">Point-in-time technical evidence and U.S. privacy issue spotting &middot; {e(metadata.get('tool'))} {e(metadata.get('tool_version'))} &middot; fingerprint <code>{e(metadata.get('run_fingerprint', 'n/a'))}</code></p>
{warning}
{body}
</main></body></html>"""


def render_research_queue(cookie_rows: list[dict[str, Any]], request_rows: list[dict[str, Any]]) -> str:
    unknown_cookies = list({(r.get("name"), r.get("domain")): r for r in cookie_rows if r.get("category") == "unknown"}.values())
    unknown_requests = list({(r.get("host"), r.get("path")): r for r in request_rows if r.get("category") == "unknown" and r.get("third_party")}.values())
    lines = [
        "# Unknown Cookie and Endpoint Research Queue",
        "",
        "Use primary vendor documentation, source code/configuration, and written vendor confirmation before secondary cookie databases. Record the source, access date, purpose, data fields, recipient role, retention, and confidence. Do not infer necessity from a first-party domain or a generic cookie name.",
        "",
        "## Cookies",
        "",
    ]
    if not unknown_cookies:
        lines.append("_None._")
    for row in unknown_cookies:
        lines.extend([
            f"### `{row.get('name')}` on `{row.get('domain')}`",
            "",
            f"Search: `\"{row.get('name')}\" cookie {row.get('domain')} purpose`",
            "",
            "Record: vendor; purpose; data categories; cross-site use; retention; opt-out/consent behavior; contract role; primary source; confidence.",
            "",
        ])
    lines.extend(["## Third-party endpoints", ""])
    if not unknown_requests:
        lines.append("_None._")
    for row in unknown_requests:
        lines.extend([
            f"### `{row.get('host')}{row.get('path')}`",
            "",
            f"Search: `{row.get('host')} tracking privacy documentation`",
            "",
            "Inspect request initiator, query-parameter names, payload schema, response cookies, vendor privacy documentation, and site tag-manager configuration.",
            "",
        ])
    return "\n".join(lines) + "\n"


def analyze_and_write(
    root: Path,
    target_url: str,
    results: dict[str, Any],
    metadata: dict[str, Any],
    patterns_path: Path,
) -> dict[str, Any]:
    patterns = _load_patterns(patterns_path)
    site_host = (urlsplit(target_url).hostname or "").lower()
    cookie_rows = build_cookie_inventory(results, site_host, patterns)
    request_rows = build_request_inventory(results, site_host, patterns)

    # B2 - gate findings on the validity of the scenarios they rest on before
    # anything is written or rendered.
    validity = scenario_validity_map(results)
    all_findings = generate_findings(results, cookie_rows, request_rows)
    findings, suppressed = partition_findings(all_findings, validity)

    cookie_fields = [
        "scenario", "checkpoint", "observed_at", "page_url", "name", "domain", "path", "expires",
        "http_only", "secure", "same_site", "partition_key", "vendor", "category", "necessity", "confidence", "third_party",
    ]
    request_fields = [
        "scenario", "time", "phase", "url", "host", "path", "method", "resource_type", "is_navigation_request",
        "vendor", "category", "necessity", "confidence", "third_party",
        "request_role", "evidence_strength", "identifier_params", "transmission_vendor",
        "post_denial", "gpc_active",
    ]
    write_csv(root / "cookie-inventory.csv", cookie_rows, cookie_fields)
    write_csv(root / "request-inventory.csv", request_rows, request_fields)
    write_json(root / "findings.json", findings)
    write_json(root / "suppressed-findings.json", suppressed)

    shareable_results: dict[str, Any] = {}
    for scenario, result in results.items():
        if not isinstance(result, dict) or "checkpoints" not in result:
            continue
        shareable_results[scenario] = {
            "scenario": scenario,
            "url": target_url,
            "started": result.get("started"),
            "finished": result.get("finished"),
            "gpc": result.get("gpc"),
            "action": result.get("action"),
            "action_result": result.get("action_result"),
            "validity": result.get("validity"),
            "cmp": result.get("cmp"),
            "isolation_assertion": result.get("isolation_assertion"),
            "exercises": result.get("exercises"),
            "consent_mode": result.get("consent_mode"),
            "errors": result.get("errors"),
            "raw_har": _relative(result.get("raw_har"), root),
            "sanitized_har": _relative(result.get("sanitized_har"), root),
            "checkpoints": [
                {
                    "scenario": cp.get("scenario"), "checkpoint": cp.get("checkpoint"), "time": cp.get("time"),
                    "url": sanitize_url(str(cp.get("url", ""))), "title": cp.get("title"),
                    "banner": cp.get("banner"), "browser_state": cp.get("browser_state"),
                    "screenshots": [_relative(p, root) for p in cp.get("screenshots", [])],
                }
                for cp in result.get("checkpoints", []) or []
            ],
            "events": sanitize_event_log(result.get("events") or {}),
        }

    invalid_scenarios = {name: v for name, v in validity.items() if not v.get("valid", True)}
    audit_data = {
        "schema_version": "2.0",
        "target_url": target_url,
        "site_host": site_host,
        "metadata": metadata,
        "run_fingerprint": metadata.get("run_fingerprint"),
        "overall_status": _summary_status(findings, invalid_scenarios),
        "run_complete": not invalid_scenarios,
        "scenario_validity": validity,
        "invalid_scenarios": invalid_scenarios,
        "findings": findings,
        "suppressed_findings": suppressed,
        "baseline_stability": results.get("baseline_stability"),
        "persistence_check": {k: v for k, v in (results.get("persistence") or {}).items() if k != "scenario_result"} or None,
        "policies": results.get("policies"),
        "cookie_count_observations": len(cookie_rows),
        "request_count_observations": len(request_rows),
        "evidence_strength_counts": dict(Counter(str(r.get("evidence_strength")) for r in request_rows)),
        "scenario_results": shareable_results,
        "classification_reference_version": patterns.get("version"),
        "classification_notice": patterns.get("notice"),
        "evidence_strength_notice": (
            "Every request observation carries an evidence_strength. 'script_loaded_only' means a tag was "
            "fetched and the vendor necessarily received the visitor's IP address, user agent, and referring "
            "URL - it does NOT establish that any measurement event was transmitted. 'beacon_observed' and "
            "'identifier_transmitted' are progressively stronger. Consent enforced at the transmission layer "
            "(for example Google Consent Mode) produces script loads without beacons, which is a correct "
            "implementation and must not be reported as a failure."
        ),
    }
    write_json(root / "audit-data.json", audit_data)

    markdown = render_markdown_report(root, target_url, metadata, findings, cookie_rows, request_rows, results, validity, suppressed)
    write_text(root / "audit-report.md", markdown)
    html_report = render_html_report({
        "target_url": target_url,
        "metadata": metadata,
        "findings": findings,
        "cookie_rows": cookie_rows,
        "request_rows": request_rows,
        "validity": validity,
        "suppressed": suppressed,
        "markdown": markdown,
    }, results, root)
    write_text(root / "audit-report.html", html_report)
    write_text(root / "research-queue.md", render_research_queue(cookie_rows, request_rows))

    questionnaire = """# Legal Applicability Questionnaire\n\nComplete before converting technical findings into legal conclusions.\n\n- Operator legal name and relevant business units:\n- Consumer locations served and audit egress region(s):\n- State privacy laws believed applicable and basis:\n- Claimed exemptions:\n- Site audience, including children under 13 or teens:\n- Health, biometric, precise geolocation, financial, race/ethnicity, immigration, sexual-orientation, or other sensitive-data flows:\n- Whether any observed recipient is a service provider/contractor and contract citation:\n- Whether any flow is sale, sharing, targeted advertising, profiling, or secondary use:\n- Banner and privacy-notice promises that apply to the tested page:\n- CMP, tag manager, server-side tagging, CDP, analytics, session replay, and advertising vendors:\n- GPC/UOOM implementation owner and mapping rules:\n- Consent-log retention, policy versioning, and downstream propagation evidence:\n- Known geofencing, A/B testing, authenticated-session, mobile, or app differences:\n- Remediation owner and target date:\n"""
    write_text(root / "legal-applicability-questionnaire.md", questionnaire)

    return {
        "findings": findings,
        "suppressed_findings": suppressed,
        "scenario_validity": validity,
        "invalid_scenarios": invalid_scenarios,
        "cookie_rows": cookie_rows,
        "request_rows": request_rows,
        "overall_status": audit_data["overall_status"],
    }
