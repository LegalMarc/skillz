"""Preview a proposed rule against saved snapshots without changing anything.

Usage: python scripts/rules_preview.py --proposal proposal.json --snapshot snapshot.json
Predicates are bounded JSON literal checks only; this tool never applies rules,
changes Mail/profile data, evaluates code, or calls an external service.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = {"sender", "to", "subject", "gist", "received", "observed_mailbox"}
OPS = {"equals", "contains", "prefix", "suffix"}
DISPOSITIONS = {"INBOX", "ARCHIVE", "SPAM", "TRASH"}
MAX_PREVIEW_RECORDS = 10000


class ProposalError(ValueError):
    pass


def validate_proposal(p: Any) -> dict[str, Any]:
    if not isinstance(p, dict) or p.get("schema_version") != 1:
        raise ProposalError("proposal must be an object with schema_version 1")
    for key in ("id", "reason"):
        if not isinstance(p.get(key), str) or not p[key].strip():
            raise ProposalError(f"proposal {key} must be a nonempty string")
    if p.get("action") not in DISPOSITIONS:
        raise ProposalError("proposal action must be INBOX, ARCHIVE, SPAM, or TRASH")
    examples = p.get("examples")
    exceptions = p.get("exceptions")
    if not isinstance(examples, list) or not examples or any(not isinstance(x, str) or not x for x in examples):
        raise ProposalError("proposal requires example case IDs")
    if not isinstance(exceptions, list) or any(not isinstance(x, str) or not x for x in exceptions):
        raise ProposalError("proposal exceptions must be a list of case IDs")
    identities = p.get("target_identities")
    if not isinstance(identities, list) or not identities:
        raise ProposalError("proposal requires exact target_identities to prevent broad sender rules")
    identity_keys: set[tuple[str, str, str]] = set()
    for i, identity in enumerate(identities):
        if not isinstance(identity, dict) or set(identity) != {"account", "message_id", "current_id"}:
            raise ProposalError(f"target identity {i} requires account, full message_id, and integer current_id")
        if not isinstance(identity["account"], str) or not identity["account"] or not isinstance(identity["message_id"], str) or not identity["message_id"] or type(identity["current_id"]) is not int or identity["current_id"] <= 0:
            raise ProposalError(f"target identity {i} requires nonempty account/full Message-ID and positive integer current_id")
        key = (identity["account"], identity["message_id"], identity["current_id"])
        if key in identity_keys:
            raise ProposalError(f"duplicate target identity {key!r}")
        identity_keys.add(key)
    predicates = p.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        raise ProposalError("proposal requires at least one bounded predicate")
    for i, pred in enumerate(predicates):
        if not isinstance(pred, dict) or set(pred) != {"field", "op", "value"}:
            raise ProposalError(f"predicate {i} must contain only field, op, value")
        if pred["field"] not in FIELDS or pred["op"] not in OPS or not isinstance(pred["value"], str) or not pred["value"]:
            raise ProposalError(f"predicate {i} uses an unsupported field, operator, or value")
    return p


def matches(item: dict[str, Any], predicates: list[dict[str, str]]) -> bool:
    for p in predicates:
        value = item.get(p["field"])
        if not isinstance(value, str):
            return False
        needle = p["value"].casefold()
        value = value.casefold()
        op = p["op"]
        if not ({"equals": lambda: value == needle, "contains": lambda: needle in value,
                 "prefix": lambda: value.startswith(needle), "suffix": lambda: value.endswith(needle)}[op]()):
            return False
    return True


def _parse_stamp(value: Any, label: str, timezone: str):
    if not isinstance(value, str) or not value:
        raise ProposalError(f"snapshot {label} must be an ISO timestamp/date")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProposalError(f"snapshot {label} is invalid") from exc
    if parsed.tzinfo is None:
        if len(value) == 10:  # canonical date-only snapshot convention: local midnight
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
        else:
            raise ProposalError(f"snapshot {label} must include a timezone")
    return parsed


def _identity(record: dict[str, Any]) -> tuple[str, str, int]:
    account, message_id, current_id = record.get("account"), record.get("message_id"), record.get("current_id")
    if not isinstance(account, str) or not account or not isinstance(message_id, str) or not message_id or type(current_id) is not int or current_id <= 0:
        raise ProposalError(f"snapshot record {record.get('item')} requires account, full message_id, and integer current_id")
    return account, message_id, current_id


def _protected(record: dict[str, Any], cutoff: Any, timezone: str) -> bool:
    received = record.get("received")
    if received is None:
        return True
    timestamp = _parse_stamp(received, f"record {record.get('item')} received", timezone)
    return timestamp < cutoff - dt.timedelta(days=30)


def _predicate_record(record: dict[str, Any]) -> dict[str, Any]:
    context = record.get("email_context")
    if context is not None and not isinstance(context, dict):
        raise ProposalError(f"record {record.get('item')} email_context must be an object")
    context = context or {}
    recipients = context.get("to")
    return {"sender": context.get("sender"), "to": ", ".join(recipients) if recipients else None,
            "subject": record.get("subject"), "gist": record.get("gist"),
            "received": record.get("received"), "observed_mailbox": record.get("observed_mailbox")}


def preview(proposal: dict[str, Any], snapshot: Any) -> dict[str, Any]:
    p = validate_proposal(proposal)
    records = snapshot.get("records") if isinstance(snapshot, dict) else None
    if not isinstance(records, list):
        raise ProposalError("canonical snapshot must contain a records list")
    if len(records) > MAX_PREVIEW_RECORDS:
        raise ProposalError(f"snapshot exceeds the bounded preview limit of {MAX_PREVIEW_RECORDS} records")
    timezone = snapshot.get("timezone", "America/New_York")
    if not isinstance(timezone, str):
        raise ProposalError("snapshot timezone must be a string")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ProposalError("snapshot timezone is invalid") from exc
    try:
        cutoff = _parse_stamp(snapshot.get("snapshot_as_of"), "snapshot_as_of", timezone)
    except Exception as exc:
        if isinstance(exc, ProposalError):
            raise
        raise ProposalError("snapshot timezone is invalid") from exc
    seen: set[str] = set()
    for i, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("item"), str) or not record["item"]:
            raise ProposalError(f"snapshot record {i} requires stable item id")
        if record["item"] in seen:
            raise ProposalError(f"duplicate snapshot item id: {record['item']}")
        _identity(record)
        if record.get("observed_mailbox") not in {"INBOX", "Archive", "Junk", "Trash"}:
            raise ProposalError(f"record {record['item']} has invalid observed_mailbox")
        context = record.get("email_context")
        if context is not None:
            if not isinstance(context, dict) or any(not isinstance(context.get(k, []), list) or any(not isinstance(x, str) for x in context.get(k, [])) for k in ("to", "cc")):
                raise ProposalError(f"record {record['item']} has malformed email_context recipients")
        _protected(record, cutoff, timezone)  # validate received timestamp even when not targeted
        seen.add(record["item"])
    unknown = (set(p["examples"]) | set(p["exceptions"])) - seen
    if unknown:
        raise ProposalError("unknown example/exception IDs: " + ", ".join(sorted(unknown)))
    target_ids = {(x["account"], x["message_id"], x["current_id"]) for x in p["target_identities"]}
    by_identity = {_identity(r): r for r in records}
    found_targets = [by_identity[(x["account"], x["message_id"], x["current_id"])]
                     for x in p["target_identities"]
                     if (x["account"], x["message_id"], x["current_id"]) in by_identity]
    missing_targets = [
        {"account": x["account"], "message_id": x["message_id"], "current_id": x["current_id"]}
        for x in p["target_identities"] if (x["account"], x["message_id"], x["current_id"]) not in by_identity
    ]
    predicate_matches = []
    missing_fields: dict[str, set[str]] = {pred["field"]: set() for pred in p["predicates"]}
    # Evaluate predicates over the bounded full snapshot so matching copies outside
    # the selected action scope, and gaps in the saved fields, remain visible.
    for record in records:
        predicate_record = _predicate_record(record)
        for pred in p["predicates"]:
            if not isinstance(predicate_record.get(pred["field"]), str):
                missing_fields[pred["field"]].add(record["item"])
        if matches(predicate_record, p["predicates"]):
            predicate_matches.append(record)
    selected_matches = [r for r in predicate_matches if _identity(r) in target_ids]
    outside_matches = [r for r in predicate_matches if _identity(r) not in target_ids]
    exceptions = set(p["exceptions"])
    selected_exception_matches = [r["item"] for r in selected_matches if r["item"] in exceptions]
    global_exception_matches = [r["item"] for r in predicate_matches if r["item"] in exceptions]
    selected_protected = [r["item"] for r in selected_matches if _protected(r, cutoff, timezone)]
    protected = [r["item"] for r in predicate_matches if _protected(r, cutoff, timezone)]
    eligible = [r["item"] for r in selected_matches if r["item"] not in exceptions and not _protected(r, cutoff, timezone)]
    outside_protected = [r["item"] for r in outside_matches if _protected(r, cutoff, timezone)]
    outside_exceptions = [r["item"] for r in outside_matches if r["item"] in exceptions]
    outside_eligible = [r["item"] for r in outside_matches if r["item"] not in exceptions and not _protected(r, cutoff, timezone)]
    future_eligible = [r["item"] for r in predicate_matches if r["item"] not in exceptions and not _protected(r, cutoff, timezone)]
    selected_nonmatches = [r["item"] for r in found_targets if r not in selected_matches]
    example_hits = set(p["examples"]) & set(eligible)
    matched_ids = [r["item"] for r in selected_matches if r["item"] not in exceptions]
    return {"proposal_id": p["id"], "reason": p["reason"], "action": p["action"],
            "mode": "read-only preview; no rule adoption or Mail/profile mutation",
            "frozen_as_of": snapshot["snapshot_as_of"], "protected_cutoff_before": (cutoff - dt.timedelta(days=30)).isoformat(),
            "records_scanned": len(records),
            "predicate_match_ids": [r["item"] for r in predicate_matches],
            "matches_outside_selected_targets": [r["item"] for r in outside_matches],
            "selected_target_match_ids": [r["item"] for r in selected_matches],
            "selected_targets_not_matching": selected_nonmatches,
            "selected_target_coverage": {"requested": len(p["target_identities"]),
                "found": [r["item"] for r in found_targets], "missing": missing_targets},
            "action_scope_note": "potentially_affected_ids below contains only predicate-matching exact identities selected in this proposal, excluding listed exceptions and protected records; it does not authorize or perform Mail actions.",
            "missing_field_coverage": {field: {"count": len(items), "item_ids": sorted(items)}
                for field, items in missing_fields.items()},
            "matched_item_ids": matched_ids,
            "excluded_exception_ids": selected_exception_matches,
            "exception_predicate_match_ids": global_exception_matches,
            "protected_item_ids": protected,
            "selected_target_protected_ids": selected_protected,
            "unselected_future_rule_impact": {"eligible_item_ids": outside_eligible,
                "protected_item_ids": outside_protected,
                "exception_item_ids": outside_exceptions,
                "eligible_count": len(outside_eligible),
                "scope_note": "Read-only impact estimate over saved records; it does not expand exact selected action scope or authorize any action."},
            "future_rule_impact": {"eligible_item_ids": future_eligible,
                "protected_item_ids": protected,
                "exception_item_ids": global_exception_matches,
                "eligible_count": len(future_eligible),
                "scope_note": "Read-only predicate matches across the bounded saved snapshot; approval and exact-copy checks remain separate."},
            "potentially_affected_ids": eligible,
            "example_ids": p["examples"], "example_ids_matching": sorted(example_hits),
            "example_coverage": f"{len(example_hits)}/{len(p['examples'])}",
            "exceptions": p["exceptions"],
            "adoption": {"item_correction": "record as a one-item correction separately",
                         "future_rule": "requires explicit user approval in chat and normal Learning workflow",
                         "approval_metadata_authorizes_external_action": False}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True, help="structured proposal JSON")
    parser.add_argument("--snapshot", type=Path, required=True, help="saved source snapshot JSON")
    parser.add_argument("--output", type=Path, help="write preview JSON here; stdout by default")
    args = parser.parse_args(argv)
    try:
        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        result = preview(proposal, snapshot)
        text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except (OSError, json.JSONDecodeError, ProposalError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
