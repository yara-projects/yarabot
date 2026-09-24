import json
import unittest
from collections import defaultdict
from pathlib import Path

from nlp_quality.build_and_evaluate import evaluate, role_groups
import nlp_helpers


QUALITY_DIR = Path(__file__).with_name("nlp_quality")


class NlpQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backup = json.loads(next(QUALITY_DIR.glob("intent_phrases_backup_*.json")).read_text(encoding="utf-8"))
        cls.base = defaultdict(list)
        for row in backup["rows"]:
            cls.base[row["intent_name"]].append(row["phrase"])
        cls.approved = json.loads((QUALITY_DIR / "approved_phrases.json").read_text(encoding="utf-8"))
        cls.final = {name: list(values) for name, values in cls.base.items()}
        for row in cls.approved:
            cls.final.setdefault(row["intent"], []).append(row["phrase"])
        cls.groups = role_groups()

    def test_normalization_is_shared_by_queries_and_phrases(self):
        self.assertEqual(nlp_helpers.clean_question("  WHO’S   there?! "), "who is there")
        nlp_helpers._phrase_cache["data"] = {"timetable": ["this week's timetable"]}
        nlp_helpers._phrase_cache["loaded_at"] = float("inf")
        ranked = nlp_helpers.rank_intents("This   weeks timetable!!!", ["timetable"])
        self.assertEqual(ranked[0][0], "timetable")

    def test_ambiguous_and_rejected_candidates_are_not_approved(self):
        candidates = json.loads((QUALITY_DIR / "candidates.json").read_text(encoding="utf-8"))
        approved = {(row["intent"], row["phrase"]) for row in self.approved}
        blocked = {(row["intent"], row["phrase"]) for row in candidates
                   if row["classification"] in {"AMBIGUOUS", "REJECT"}}
        self.assertTrue(approved.isdisjoint(blocked))

    def test_held_out_and_large_synthetic_targets(self):
        held_out = json.loads((QUALITY_DIR / "held_out.json").read_text(encoding="utf-8"))
        synthetic = json.loads((QUALITY_DIR / "synthetic_1000.json").read_text(encoding="utf-8"))
        held_report = evaluate(held_out, self.final, self.groups)
        synthetic_report = evaluate(synthetic, self.final, self.groups)
        self.assertGreaterEqual(held_report["accuracy"], .97)
        self.assertEqual(held_report["wrong_intent_rate"], 0)
        self.assertGreaterEqual(synthetic_report["accuracy"], .97)

    def test_no_previously_correct_golden_case_regresses(self):
        golden = json.loads((QUALITY_DIR / "golden_set.json").read_text(encoding="utf-8"))
        before = evaluate(golden, self.base, self.groups)["details"]
        after = evaluate(golden, self.final, self.groups)["details"]
        for old, new in zip(before, after):
            if old["outcome"] == "CORRECT":
                self.assertEqual(new["outcome"], "CORRECT", new)


if __name__ == "__main__":
    unittest.main()
