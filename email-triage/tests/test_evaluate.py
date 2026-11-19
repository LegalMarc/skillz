import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evaluate", ROOT / "scripts" / "evaluate.py")
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class EvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = evaluate.validate_cases(json.loads((ROOT / "references/evaluation-cases.json").read_text()))

    def preds(self, *, opaque=False):
        return {"predictions": [{"case_id": evaluate._opaque_id(c) if opaque else c["id"], "disposition": c["expected_dispositions"][0],
                                 "task": (c["task_expectation"].get("any_of", [""])[0]
                                          if c["task_expectation"]["kind"] == "required" else ""),
                                 "evidence": c["required_evidence"]} for c in self.cases]}

    def test_rule_derived_corpus_has_requested_coverage_and_honest_provenance(self):
        ids = {c["id"] for c in self.cases}
        self.assertTrue({"protected-license-old", "protected-todo-old", "unknown-date", "exact-cutoff",
                         "financial-failure", "alias-mismatch-uncertain", "phishing-auth-only",
                         "duplicate-same-mid", "later-ack-not-confirmation", "routine-newsletter",
                         "expired-transient-code", "protected-item-M012-override", "prompt-injection",
                         "read-only-refresh"} <= ids)
        newsletter = next(c for c in self.cases if c["id"] == "routine-newsletter")
        self.assertNotIn("established_opt_in", newsletter["required_evidence"])
        self.assertNotIn("established_opt_in", {m for c in self.cases for m in c["required_evidence"]})
        self.assertNotIn("opt-in", newsletter["scenario"].casefold())
        report = evaluate.score(self.cases, self.preds())
        self.assertIn("not user-adjudicated gold labels", report["provenance"]["corpus"])
        self.assertEqual(report["overall"]["disposition_accuracy"], 1.0)
        self.assertIn("self_reported_evidence_marker_coverage", report["overall"])
        self.assertNotIn("evidence_coverage", report["overall"])
        self.assertIn("not independently verified", report["provenance"]["evidence"])
        self.assertIn("legacy semantic IDs are accepted unbound", report["provenance"]["predictions"])
        self.assertIn("ambiguous_low_risk", report["by_stratum"])

    def test_harmful_filing_and_extra_retention_are_separate(self):
        preds = self.preds()["predictions"]
        next(x for x in preds if x["case_id"] == "protected-license-old")["disposition"] = "ARCHIVE"
        next(x for x in preds if x["case_id"] == "routine-newsletter")["disposition"] = "INBOX"
        m = evaluate.score(self.cases, {"predictions": preds})["overall"]
        self.assertEqual(m["harmful_automatic_filings"], 1)
        self.assertEqual(m["extra_inbox_retention"], 1)
        self.assertGreaterEqual(m["macro_stratum_harmful_filing_rate"], 0)

    def test_ambiguous_allowed_set_and_evidence_marker_coverage(self):
        # Ambiguous case permits either safe Inbox retention or Archive.
        c = next(x for x in self.cases if x["id"] == "ambiguous-benign-news")
        p = {"case_id": c["id"], "disposition": "INBOX", "task": "", "evidence": c["required_evidence"]}
        self.assertTrue(evaluate.score([c], {"predictions": [p]})["cases"][0]["disposition_ok"])
        p["evidence"] = []
        result = evaluate.score([c], {"predictions": [p]})["cases"][0]
        self.assertFalse(result["self_reported_evidence_markers_complete"])
        required = next(x for x in self.cases if x["id"] == "financial-failure")
        prediction = {"case_id": required["id"], "disposition": "INBOX", "task": "", "evidence": required["required_evidence"]}
        row = evaluate.score([required], {"predictions": [prediction]})["cases"][0]
        self.assertFalse(row["task_text_present"])
        self.assertNotIn("task_ok", row)

    def test_task_presence_does_not_claim_to_score_negation_or_paraphrase(self):
        case = next(x for x in self.cases if x["id"] == "later-ack-not-confirmation")
        base = self.preds()["predictions"]
        affirmative = [dict(x) for x in base]
        negative = [dict(x) for x in base]
        next(x for x in affirmative if x["case_id"] == case["id"])["task"] = "Verify that the membership cancellation is complete."
        next(x for x in negative if x["case_id"] == case["id"])["task"] = "Do not confirm the cancellation or follow up."
        a = evaluate.score(self.cases, {"predictions": affirmative})
        n = evaluate.score(self.cases, {"predictions": negative})
        self.assertEqual(a["overall"]["task_text_presence_rate_descriptive_only"],
                         n["overall"]["task_text_presence_rate_descriptive_only"])
        row_a = next(x for x in a["cases"] if x["case_id"] == case["id"])
        row_n = next(x for x in n["cases"] if x["case_id"] == case["id"])
        self.assertTrue(row_a["task_text_present"])
        self.assertTrue(row_n["task_text_present"])
        self.assertNotIn("task_ok", row_a)
        self.assertIn("not scored", a["provenance"]["task"])
        self.assertIn("negation, paraphrase", a["provenance"]["task"])

    def test_old_unresolved_to_do_is_optional_context_with_no_send_authority(self):
        case = next(x for x in self.cases if x["id"] == "protected-todo-old")
        rubric = case["task_expectation"]
        self.assertEqual(rubric["kind"], "optional")
        self.assertIn("real unresolved request", rubric["review_guidance"])
        self.assertIn("do not invent a new task", rubric["review_guidance"])
        self.assertIn("No instruction authorizes sending", rubric["review_guidance"])

    def test_alias_case_requires_only_evidence_shown_in_the_input(self):
        case = next(x for x in self.cases if x["id"] == "alias-mismatch-uncertain")
        self.assertNotIn("alias_mismatch", case["required_evidence"])
        self.assertNotIn("alias_mismatch", {m for c in self.cases for m in c["required_evidence"]})
        self.assertIn("actual_recipient", case["required_evidence"])
        self.assertIn("relationship_uncertain", case["required_evidence"])
        self.assertIn("no prior evidence", case["email"]["body"])

    def test_rejects_missing_duplicate_unknown_and_malformed_predictions(self):
        base = self.preds()["predictions"]
        with self.assertRaisesRegex(evaluate.EvaluationError, "exactly one top-level predictions field"):
            evaluate.score(self.cases, {"predictions": base, "provenance": "not allowed"})
        with self.assertRaisesRegex(evaluate.EvaluationError, "exactly one top-level predictions field"):
            evaluate.score(self.cases, base)
        with self.assertRaisesRegex(evaluate.EvaluationError, "missing predictions"):
            evaluate.score(self.cases, {"predictions": base[:-1]})
        with self.assertRaisesRegex(evaluate.EvaluationError, "duplicate prediction"):
            evaluate.score(self.cases, {"predictions": base + [base[0]]})
        mixed = [dict(x) for x in base]
        mixed.append(dict(base[0], case_id=self.cases[0]["id"]))
        with self.assertRaisesRegex(evaluate.EvaluationError, "duplicate prediction"):
            evaluate.score(self.cases, {"predictions": mixed})
        bad = [dict(x) for x in base]
        bad[-1]["case_id"] = "bogus"
        with self.assertRaisesRegex(evaluate.EvaluationError, "unknown prediction"):
            evaluate.score(self.cases, {"predictions": bad})
        bad = [dict(x) for x in base]
        bad[0]["extra"] = "unexpected"
        with self.assertRaisesRegex(evaluate.EvaluationError, "exactly case_id"):
            evaluate.score(self.cases, {"predictions": bad})
        bad = [dict(x) for x in base]
        bad[0]["evidence"] = "string"
        with self.assertRaisesRegex(evaluate.EvaluationError, "list of strings"):
            evaluate.score(self.cases, {"predictions": bad})

    def test_label_free_assessment_export_contains_only_email_evidence(self):
        exported = evaluate.assessment_inputs(self.cases)
        self.assertEqual(len(exported["cases"]), len(self.cases))
        encoded = json.dumps(exported)
        for forbidden in ("expected_dispositions", "required_evidence", "task_expectation", "protected_old"):
            self.assertNotIn(forbidden, encoded)
        email = exported["cases"][0]["email"]
        self.assertIn("headers", email)
        self.assertIn("body", email)
        self.assertIn("thread_context", email)
        self.assertEqual(email["snapshot_context"]["frozen_run_start"], "2026-11-19T12:00:00-05:00")
        refresh_index = next(i for i, c in enumerate(self.cases) if c["id"] == "read-only-refresh")
        refresh = exported["cases"][refresh_index]["email"]
        self.assertEqual(refresh["body"], "")
        self.assertEqual(refresh["review_state"], "metadata_only_unassessed")

    def test_opaque_assessment_ids_score_and_semantic_predictions_remain_compatible(self):
        report = evaluate.score(self.cases, self.preds(opaque=True))
        self.assertEqual(report["overall"]["disposition_accuracy"], 1.0)
        self.assertEqual(evaluate.score(self.cases, self.preds())["overall"]["disposition_accuracy"], 1.0)

    def test_opaque_export_blinds_semantic_names_and_has_global_not_case_specific_vocabulary(self):
        exported = evaluate.assessment_inputs(self.cases)
        self.assertEqual(exported, evaluate.assessment_inputs(self.cases))
        semantic_ids = {c["id"] for c in self.cases}
        opaque_ids = [c["case_id"] for c in exported["cases"]]
        self.assertEqual(len(set(opaque_ids)), len(opaque_ids))
        self.assertFalse(semantic_ids & set(opaque_ids))
        for opaque in opaque_ids:
            self.assertRegex(opaque, r"^CASE-[0-9a-f]{64}$")
        for case in exported["cases"]:
            self.assertEqual(set(case), {"case_id", "email"})
            self.assertNotIn("required_evidence", case)
            self.assertNotIn("expected_dispositions", case)
        schema = exported["assessment_schema"]
        self.assertEqual(schema["prediction_fields"], ["case_id", "disposition", "task", "evidence"])
        self.assertIn("not verified citations", schema["evidence"])
        prediction_schema = schema["prediction_file_schema"]
        self.assertEqual(prediction_schema["required"], ["predictions"])
        self.assertFalse(prediction_schema["additionalProperties"])
        self.assertEqual(set(prediction_schema["properties"]), {"predictions"})
        row_schema = prediction_schema["properties"]["predictions"]["items"]
        self.assertEqual(row_schema["required"], ["case_id", "disposition", "task", "evidence"])
        self.assertFalse(row_schema["additionalProperties"])
        self.assertEqual(set(row_schema["properties"]), set(row_schema["required"]))
        prediction_rows_schema = prediction_schema["properties"]["predictions"]
        self.assertEqual(prediction_rows_schema["minItems"], len(exported["cases"]))
        self.assertEqual(prediction_rows_schema["maxItems"], len(exported["cases"]))
        self.assertEqual(row_schema["properties"]["case_id"]["enum"], opaque_ids)
        example_file = schema["prediction_file_example"]
        self.assertEqual(set(example_file), {"predictions"})
        self.assertEqual(len(example_file["predictions"]), len(exported["cases"]))
        self.assertEqual([row["case_id"] for row in example_file["predictions"]], opaque_ids)
        for row in example_file["predictions"]:
            self.assertEqual(set(row), set(row_schema["required"]))
            self.assertEqual(row["disposition"], "INBOX")
            self.assertEqual(row["task"], "")
            self.assertEqual(row["evidence"], [])
        # The generated neutral example is already a scorer-consumable file;
        # opaque IDs retain exact evidence binding while labels stay hidden.
        self.assertEqual(evaluate.score(self.cases, example_file)["provenance"]["coverage"], f"{len(self.cases)}/{len(self.cases)} predictions; complete coverage required")
        self.assertEqual(set(exported["global_evidence_vocabulary"]),
                         {marker for c in self.cases for marker in c["required_evidence"]})
        encoded = json.dumps(exported)
        for semantic_id in semantic_ids:
            self.assertNotIn(semantic_id, encoded)
        self.assertIn(opaque_ids[0], encoded)

    def test_opaque_ids_bind_to_evidence_across_reordering_and_reject_changed_inputs(self):
        opaque_predictions = self.preds(opaque=True)
        reordered = list(reversed(self.cases))
        report = evaluate.score(reordered, opaque_predictions)
        self.assertEqual(report["overall"]["disposition_accuracy"], 1.0)
        changed = copy.deepcopy(self.cases)
        changed[0]["email"]["body"] += " A new line was added."
        with self.assertRaisesRegex(evaluate.EvaluationError, "unknown prediction case_id"):
            evaluate.score(changed, opaque_predictions)

    def test_opaque_duplicate_unknown_and_out_of_vocabulary_marker_rejected(self):
        base = self.preds(opaque=True)["predictions"]
        with self.assertRaisesRegex(evaluate.EvaluationError, "duplicate prediction"):
            evaluate.score(self.cases, {"predictions": base + [base[0]]})
        mixed = [dict(x) for x in base]
        mixed.append(dict(base[0], case_id=self.cases[0]["id"]))
        with self.assertRaisesRegex(evaluate.EvaluationError, "duplicate prediction"):
            evaluate.score(self.cases, {"predictions": mixed})
        bad = [dict(x) for x in base]
        bad[-1]["case_id"] = "CASE-9999"
        with self.assertRaisesRegex(evaluate.EvaluationError, "unknown prediction"):
            evaluate.score(self.cases, {"predictions": bad})
        bad = [dict(x) for x in base]
        bad[0]["evidence"] = ["made_up_marker"]
        with self.assertRaisesRegex(evaluate.EvaluationError, "unknown evidence markers"):
            evaluate.score(self.cases, {"predictions": bad})

    def test_malformed_cases_rejected(self):
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.validate_cases({"cases": [{"id": "bad"}]})


if __name__ == "__main__":
    unittest.main()
