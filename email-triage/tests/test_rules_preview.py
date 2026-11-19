import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rules_preview", ROOT / "scripts" / "rules_preview.py")
preview_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview_mod)


def item(i, sender="billing@example.invalid", received="2026-11-18T12:00:00-05:00", protected=False, mailbox="INBOX"):
    # A caller-supplied protected flag is deliberately ignored. Date and frozen
    # run time determine long-term protection.
    return {"item": i, "account": "acct-test", "message_id": f"<m{i}@example.invalid>",
            "current_id": 100 + ord(i) - ord("a"), "observed_mailbox": mailbox,
            "to_display": "billing@example.test", "subject": "Payment notice", "received": received,
            "size_bytes": 1000, "gist": "A synthetic payment notice.",
            "email_context": {"sender": sender, "to": ["billing@example.test"], "cc": []},
            "protected_long_term": protected}


def proposal(targets=None):
    return {"schema_version": 1, "id": "proposal-1", "reason": "Repeated confirmed correction",
            "action": "ARCHIVE", "examples": ["a"], "exceptions": ["b"],
            "target_identities": targets or [{"account": "acct-test", "message_id": "<ma@example.invalid>", "current_id": 100}],
            "predicates": [{"field": "sender", "op": "contains", "value": "billing@"}]}


class RulesPreviewTests(unittest.TestCase):
    def setUp(self):
        missing = item("g")
        del missing["email_context"]["sender"]
        del missing["email_context"]["to"]
        self.snapshot = {"run_id": "synthetic", "scope": "synthetic", "snapshot_as_of": "2026-11-19T12:00:00-05:00", "timezone": "America/New_York", "records": [item("a"), item("b"), item("c", received="2026-10-19T11:59:59-04:00", protected=False), item("d", "other@example.invalid"), item("e"), item("f", received="2026-10-19T11:59:59-04:00"), missing]}

    def test_matches_exact_identity_exceptions_and_protection_without_mutation(self):
        before = repr(self.snapshot)
        p = proposal()
        p["predicates"].append({"field": "to", "op": "contains", "value": "billing@"})
        result = preview_mod.preview(p, self.snapshot)
        self.assertEqual(result["matched_item_ids"], ["a"])
        self.assertEqual(result["predicate_match_ids"], ["a", "b", "c", "e", "f"])
        self.assertEqual(result["matches_outside_selected_targets"], ["b", "c", "e", "f"])
        self.assertEqual(result["selected_target_match_ids"], ["a"])
        self.assertEqual(result["unselected_future_rule_impact"]["eligible_item_ids"], ["e"])
        self.assertEqual(result["unselected_future_rule_impact"]["protected_item_ids"], ["c", "f"])
        self.assertIn("does not expand exact selected action scope", result["unselected_future_rule_impact"]["scope_note"])
        self.assertEqual(result["missing_field_coverage"]["sender"], {"count": 1, "item_ids": ["g"]})
        self.assertEqual(result["missing_field_coverage"]["to"], {"count": 1, "item_ids": ["g"]})
        self.assertEqual(result["excluded_exception_ids"], [])
        self.assertEqual(result["protected_item_ids"], ["c", "f"])
        self.assertEqual(result["potentially_affected_ids"], ["a"])
        self.assertEqual(result["example_coverage"], "1/1")
        self.assertIn("requires explicit user approval", result["adoption"]["future_rule"])
        self.assertFalse(result["adoption"]["approval_metadata_authorizes_external_action"])
        self.assertEqual(repr(self.snapshot), before)

    def test_exceptions_and_protected_matches_are_reported_but_not_affected(self):
        p = proposal(targets=[{"account": "acct-test", "message_id": f"<m{x}@example.invalid>", "current_id": 100 + ord(x) - ord("a")} for x in "abc"])
        result = preview_mod.preview(p, self.snapshot)
        self.assertEqual(result["matched_item_ids"], ["a", "c"])
        self.assertEqual(result["excluded_exception_ids"], ["b"])
        self.assertEqual(result["protected_item_ids"], ["c", "f"])
        self.assertEqual(result["matches_outside_selected_targets"], ["e", "f"])
        self.assertEqual(result["unselected_future_rule_impact"]["eligible_item_ids"], ["e"])
        self.assertEqual(result["potentially_affected_ids"], ["a"])

    def test_missing_selected_identity_is_reported_and_does_not_expand_action_scope(self):
        p = proposal()
        p["target_identities"].append({"account": "acct-test", "message_id": "<missing@example.invalid>", "current_id": 999})
        result = preview_mod.preview(p, self.snapshot)
        self.assertEqual(result["selected_target_coverage"]["requested"], 2)
        self.assertEqual(result["selected_target_coverage"]["found"], ["a"])
        self.assertEqual(result["selected_target_coverage"]["missing"], [{"account": "acct-test", "message_id": "<missing@example.invalid>", "current_id": 999}])
        self.assertEqual(result["potentially_affected_ids"], ["a"])

    def test_preview_scan_has_explicit_upper_bound(self):
        snapshot = dict(self.snapshot, records=[item("x") for _ in range(preview_mod.MAX_PREVIEW_RECORDS + 1)])
        with self.assertRaisesRegex(preview_mod.ProposalError, "bounded preview limit"):
            preview_mod.preview(proposal(), snapshot)

    def test_refuses_broad_sender_only_rule_and_unsupported_regex_or_code(self):
        p = proposal()
        p.pop("target_identities")
        with self.assertRaisesRegex(preview_mod.ProposalError, "exact target_identities"):
            preview_mod.validate_proposal(p)
        p = proposal()
        p["predicates"] = [{"field": "sender", "op": "regex", "value": ".*"}]
        with self.assertRaises(preview_mod.ProposalError):
            preview_mod.validate_proposal(p)
        p = proposal()
        p["predicates"] = [{"field": "__import__", "op": "contains", "value": "os"}]
        with self.assertRaises(preview_mod.ProposalError):
            preview_mod.validate_proposal(p)

    def test_rejects_unknown_examples_and_incomplete_copy_identity(self):
        p = proposal()
        p["examples"] = ["missing"]
        with self.assertRaisesRegex(preview_mod.ProposalError, "unknown example"):
            preview_mod.preview(p, self.snapshot)
        p = proposal()
        p["exceptions"] = []
        p["target_identities"][0]["message_id"] = ""
        with self.assertRaises(preview_mod.ProposalError):
            preview_mod.validate_proposal(p)
        snap = {"run_id": "synthetic", "scope": "synthetic", "snapshot_as_of": "2026-11-19T12:00:00-05:00", "timezone": "America/New_York", "records": [dict(item("a"), current_id="")] }
        p = proposal()
        p["exceptions"] = []
        with self.assertRaisesRegex(preview_mod.ProposalError, "requires account, full message_id"):
            preview_mod.preview(p, snap)

    def test_cutoff_is_derived_from_snapshot_time_and_unknown_date_is_protected(self):
        exact = item("h", received="2026-10-20T13:00:00-04:00", protected=True)
        unknown = item("i", received=None, protected=False)
        snapshot = dict(self.snapshot, records=self.snapshot["records"] + [exact, unknown])
        p = proposal(targets=[{"account": "acct-test", "message_id": "<mh@example.invalid>", "current_id": 107},
                              {"account": "acct-test", "message_id": "<mi@example.invalid>", "current_id": 108}])
        p["examples"] = ["h", "i"]
        p["exceptions"] = []
        result = preview_mod.preview(p, snapshot)
        self.assertEqual(result["protected_item_ids"], ["c", "f", "i"])
        self.assertEqual(result["potentially_affected_ids"], ["h"])
        self.assertEqual(result["potentially_affected_ids"], ["h"])

    def test_literal_matching_is_case_insensitive_and_missing_field_fails_closed(self):
        self.assertTrue(preview_mod.matches({"subject": "PAYMENT notice"}, [{"field": "subject", "op": "contains", "value": "payment"}]))
        self.assertFalse(preview_mod.matches({}, [{"field": "subject", "op": "contains", "value": "payment"}]))


if __name__ == "__main__":
    unittest.main()
