"""Evaluate model-supplied email triage assessments against synthetic cases.

Usage: python3 scripts/evaluate.py --export-inputs assessment-inputs.json
       python3 scripts/evaluate.py --predictions assessments.json --output results.json
The first command exports synthetic email evidence with labels/rubrics removed.
Predictions are authored separately by the invoking model. This module never
calls a model, API, Mail, or local account configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "references" / "evaluation-cases.json"
DISPOSITIONS = {"INBOX", "ARCHIVE", "SPAM", "TRASH"}


class EvaluationError(ValueError):
    """Input data is malformed or incomplete."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read valid JSON from {path}: {exc}") from exc


def _strings(value: Any, where: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise EvaluationError(f"{where} must be a list of strings")
    if nonempty and not value:
        raise EvaluationError(f"{where} must not be empty")
    return value


def validate_cases(raw: Any) -> list[dict[str, Any]]:
    cases = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("case corpus must contain a nonempty cases list")
    ids: set[str] = set()
    required = {"id", "stratum", "scenario", "email", "expected_dispositions", "required_evidence", "task_expectation"}
    for i, case in enumerate(cases):
        if not isinstance(case, dict) or not required <= case.keys():
            raise EvaluationError(f"case {i} is missing required fields")
        cid = case["id"]
        if not isinstance(cid, str) or not cid or cid in ids:
            raise EvaluationError(f"case {i} has an invalid or duplicate id")
        ids.add(cid)
        if not isinstance(case["stratum"], str) or not case["stratum"] or not isinstance(case["scenario"], str):
            raise EvaluationError(f"case {cid} has invalid stratum/scenario")
        email = case["email"]
        if not isinstance(email, dict) or not isinstance(email.get("headers"), dict) or not all(isinstance(email.get(k), str) for k in ("subject", "body", "thread_context", "review_state")) or not isinstance(email.get("snapshot_context"), dict):
            raise EvaluationError(f"case {cid} requires synthetic headers, body, and thread_context")
        if not all(isinstance(v, str) or (k == "date" and v is None) for k, v in email["headers"].items()):
            raise EvaluationError(f"case {cid} headers must be strings")
        allowed = _strings(case["expected_dispositions"], f"case {cid} expected_dispositions", nonempty=True)
        if any(x not in DISPOSITIONS for x in allowed) or len(set(allowed)) != len(allowed):
            raise EvaluationError(f"case {cid} has invalid/duplicate expected disposition")
        _strings(case["required_evidence"], f"case {cid} required_evidence")
        task = case["task_expectation"]
        if not isinstance(task, dict) or task.get("kind") not in {"required", "none", "optional"}:
            raise EvaluationError(f"case {cid} has invalid task_expectation")
        if task["kind"] == "required" and not _strings(task.get("any_of"), f"case {cid} task_expectation.any_of", nonempty=True):
            raise EvaluationError(f"case {cid} required task expectation must have alternatives")
    opaque_ids = [_opaque_id(case) for case in cases]
    if len(set(opaque_ids)) != len(opaque_ids):
        raise EvaluationError("cases must have distinct synthetic email evidence for opaque assessment IDs")
    return cases


def _opaque_id(case: dict[str, Any]) -> str:
    """Opaque, stable identifier bound to canonical synthetic message evidence."""
    canonical = json.dumps(case["email"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "CASE-" + hashlib.sha256(canonical).hexdigest()


def assessment_inputs(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Export blind messages plus the exact strict prediction-file contract."""
    markers = sorted({marker for case in cases for marker in case["required_evidence"]})
    opaque_ids = [_opaque_id(case) for case in cases]
    prediction_schema = {
        "title": "Email triage assessment predictions",
        "description": "Strict prediction file. Use exactly the top-level predictions array and preserve each opaque input ID.",
        "type": "object",
        "required": ["predictions"],
        "additionalProperties": False,
        "properties": {"predictions": {
            "type": "array",
            "minItems": len(cases),
            "maxItems": len(cases),
            "uniqueItems": True,
            "items": {
                "type": "object",
                "required": ["case_id", "disposition", "task", "evidence"],
                "additionalProperties": False,
                "properties": {
                    "case_id": {"type": "string", "pattern": r"^CASE-[0-9a-f]{64}$", "enum": opaque_ids,
                                 "description": "Copy the opaque case_id from the matching exported input."},
                    "disposition": {"type": "string", "enum": sorted(DISPOSITIONS)},
                    "task": {"type": "string", "description": "A concrete follow-up instruction, or empty when none is warranted."},
                    "evidence": {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": markers}},
                },
            },
        }},
    }
    prediction_example = {"predictions": [{"case_id": opaque_id, "disposition": "INBOX", "task": "", "evidence": []}
                                            for opaque_id in opaque_ids]}
    return {"provenance": "synthetic fabricated messages; labels, scenarios, strata and per-case rubrics omitted",
            "assessment_schema": {"prediction_fields": ["case_id", "disposition", "task", "evidence"],
                                  "case_id": "Use the opaque CASE- plus 64 lowercase hexadecimal characters shown on each input.",
                                  "disposition_values": sorted(DISPOSITIONS),
                                  "task": "A concise concrete follow-up, or an empty string when no task is warranted.",
                                  "evidence": "A list of zero or more IDs from global_evidence_vocabulary that best describe evidence actually used. Self-reported markers are not verified citations.",
                                  "prediction_file_schema": prediction_schema,
                                  "prediction_file_example": prediction_example,
                                  "example_note": "This is a shape-only example with neutral placeholder predictions. Replace every disposition, task and evidence list based on the email; retain each opaque case_id exactly."},
            "global_evidence_vocabulary": markers,
            "cases": [{"case_id": opaque_id, "email": c["email"]} for c, opaque_id in zip(cases, opaque_ids)]}


def score(cases: list[dict[str, Any]], raw_predictions: Any) -> dict[str, Any]:
    if not isinstance(raw_predictions, dict) or set(raw_predictions) != {"predictions"}:
        raise EvaluationError("prediction file must contain exactly one top-level predictions field")
    predictions = raw_predictions["predictions"]
    if not isinstance(predictions, list):
        raise EvaluationError("prediction file must contain a predictions list")
    by_id: dict[str, dict[str, Any]] = {}
    case_by_raw_id = {c["id"]: c for c in cases}
    opaque_to_raw = {_opaque_id(c): c["id"] for c in cases}
    allowed_markers = {marker for c in cases for marker in c["required_evidence"]}
    for i, pred in enumerate(predictions):
        if not isinstance(pred, dict) or set(pred) != {"case_id", "disposition", "task", "evidence"} or not isinstance(pred.get("case_id"), str):
            raise EvaluationError(f"prediction {i} must contain exactly case_id, disposition, task, and evidence")
        external_id = pred["case_id"]
        cid = opaque_to_raw.get(external_id, external_id)
        if cid not in case_by_raw_id:
            raise EvaluationError(f"unknown prediction case_id: {external_id}")
        if cid in by_id:
            raise EvaluationError(f"duplicate prediction for case_id: {external_id}")
        if pred.get("disposition") not in DISPOSITIONS:
            raise EvaluationError(f"prediction {cid} has invalid disposition")
        if not isinstance(pred.get("task"), str):
            raise EvaluationError(f"prediction {cid} task must be a string")
        evidence = _strings(pred.get("evidence"), f"prediction {cid} evidence")
        if len(set(evidence)) != len(evidence):
            raise EvaluationError(f"prediction {external_id} has duplicate evidence entries")
        unknown_markers = set(evidence) - allowed_markers
        if unknown_markers:
            raise EvaluationError(f"prediction {external_id} has unknown evidence markers: {', '.join(sorted(unknown_markers))}")
        by_id[cid] = pred
    missing = set(case_by_raw_id) - by_id.keys()
    if missing:
        raise EvaluationError("missing predictions: " + ", ".join(sorted(missing)))

    scored = []
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        pred = by_id[case["id"]]
        disposition_ok = pred["disposition"] in case["expected_dispositions"]
        # Harmful filing means an unsafe move out of Inbox, especially across a
        # protected/uncertain boundary. Extra retention is reported separately.
        harmful = not disposition_ok and pred["disposition"] != "INBOX"
        extra_retention = not disposition_ok and pred["disposition"] == "INBOX"
        required_evidence = set(case["required_evidence"])
        marker_complete = required_evidence <= set(pred["evidence"])
        task_text_present = bool(pred["task"].strip())
        row = {"case_id": case["id"], "stratum": case["stratum"], "disposition_ok": disposition_ok,
               "harmful_automatic_filing": harmful, "extra_inbox_retention": extra_retention,
               "self_reported_evidence_markers_complete": marker_complete,
               "task_text_present": task_text_present,
               "missing_evidence_markers": sorted(required_evidence - set(pred["evidence"]))}
        scored.append(row)
        strata[case["stratum"]].append(row)

    def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        return {"cases": n, "disposition_accuracy": sum(r["disposition_ok"] for r in rows) / n,
                "harmful_automatic_filings": sum(r["harmful_automatic_filing"] for r in rows),
                "harmful_automatic_filing_rate": sum(r["harmful_automatic_filing"] for r in rows) / n,
                "extra_inbox_retention": sum(r["extra_inbox_retention"] for r in rows),
                "extra_inbox_retention_rate": sum(r["extra_inbox_retention"] for r in rows) / n,
                "self_reported_evidence_marker_coverage": sum(r["self_reported_evidence_markers_complete"] for r in rows) / n,
                "task_text_presence_rate_descriptive_only": sum(r["task_text_present"] for r in rows) / n}
    strata_metrics = {k: metrics(v) for k, v in sorted(strata.items())}
    def macro(key: str) -> float:
        return sum(m[key] for m in strata_metrics.values()) / len(strata_metrics)
    overall_metrics = metrics(scored)
    overall_metrics["macro_stratum_disposition_accuracy"] = macro("disposition_accuracy")
    overall_metrics["macro_stratum_harmful_filing_rate"] = macro("harmful_automatic_filing_rate")
    overall_metrics["macro_stratum_extra_retention_rate"] = macro("extra_inbox_retention_rate")
    return {"provenance": {"corpus": "synthetic, rule-derived examples; not user-adjudicated gold labels",
                           "predictions": "separate assessment JSON supplied by caller; opaque IDs bind to canonical email evidence; legacy semantic IDs are accepted unbound for compatibility; no model/API invoked here",
                           "evidence": "self-reported marker coverage only; marker selection is not independently verified against the message text",
                           "task": "Only nonempty task-text presence is counted. Task meaning, negation, paraphrase, existing-to-do preservation, and sending authorization are not scored and require semantic review after scoring.",
                           "coverage": f"{len(scored)}/{len(cases)} predictions; complete coverage required"},
            "overall": overall_metrics, "by_stratum": strata_metrics,
            "cases": scored}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="synthetic case corpus JSON")
    parser.add_argument("--predictions", type=Path, help="separate model assessment JSON")
    parser.add_argument("--export-inputs", type=Path, help="write label-free synthetic email evidence for model assessment; does not score")
    parser.add_argument("--output", type=Path, help="write report JSON here; stdout by default")
    args = parser.parse_args(argv)
    try:
        cases = validate_cases(_load(args.cases))
        if args.export_inputs:
            if args.predictions:
                parser.error("--export-inputs and --predictions are separate modes")
            payload = json.dumps(assessment_inputs(cases), indent=2, ensure_ascii=False) + "\n"
            args.export_inputs.write_text(payload, encoding="utf-8")
            return 0
        if not args.predictions:
            parser.error("--predictions is required unless --export-inputs is used")
        report = score(cases, _load(args.predictions))
        payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
    except EvaluationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
