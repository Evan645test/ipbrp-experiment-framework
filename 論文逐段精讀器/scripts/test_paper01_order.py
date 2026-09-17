#!/usr/bin/env python3
"""Regression tests against the authorized PDF and pre-repair checkpoint."""
import copy
import json
import unittest

from repair_paper01_order import PROJECT, SOURCE_SHA, position, repair


class Paper01OrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((PROJECT / "content/paper-01-before-order-repair.json").read_text())["paper"]
        cls.overrides = json.loads((PROJECT / "content/paper-01-order-repair.json").read_text())
        cls.pdf = PROJECT / "public/papers/paper-01.pdf"
        cls.fixed, cls.audit = repair(cls.original, cls.pdf, cls.overrides)

    def test_intro_paragraphs_restored_in_native_order(self):
        included = [s for s in self.fixed["segments"] if not s.get("excluded")]
        self.assertEqual([s["id"] for s in included[1:4]], list(self.overrides["segments"]))
        self.assertTrue(included[4]["sourceText"].startswith("The teaching approach"))
        self.assertEqual(len(included), 118)

    def test_page_order_is_monotonic(self):
        positions = [position(s) for s in self.fixed["segments"]]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual([s["order"] for s in self.fixed["segments"]], list(range(1, 157)))

    def test_existing_content_ids_and_enrichments_preserved(self):
        new = {s["id"]: s for s in self.fixed["segments"]}
        for segment in self.original["segments"]:
            for field in ("sourceText", "translation", "fragments", "exhibitIds", "paragraphAssessment"):
                self.assertEqual(segment.get(field), new[segment["id"]].get(field))
        self.assertEqual(self.fixed["references"], self.original["references"])
        self.assertEqual(self.fixed["exhibits"], self.original["exhibits"])
        by_id = {c["id"]: c for c in self.fixed["citations"]}
        for citation in self.original["citations"]:
            self.assertEqual(by_id[citation["id"]], citation)

    def test_bibliography_kept_but_outside_reading_navigation(self):
        segment = next(s for s in self.fixed["segments"] if s["id"] == "paper-01-s-fb4b491173bb")
        self.assertTrue(segment["excluded"])
        self.assertTrue(segment["sourceText"].startswith("Ahmed,"))

    def test_recovered_translations_and_citations_grounded(self):
        for segment in self.fixed["segments"]:
            if segment["id"] not in self.overrides["segments"]:
                continue
            self.assertEqual(segment["section"], "1. Introduction")
            self.assertEqual(segment["translation"]["status"], "ai-draft")
            self.assertTrue(segment["translation"]["faithfulZh"])
            citations = [c for c in self.fixed["citations"] if c["segmentId"] == segment["id"]]
            self.assertTrue(citations)
            self.assertTrue(all(c["sourceContext"] in segment["sourceText"] for c in citations))

    def test_idempotent_and_revision_retains_original_sequence(self):
        again, _ = repair(self.fixed, self.pdf, self.overrides)
        self.assertEqual(again, self.fixed)
        self.assertEqual(again["readingOrderRepair"]["previousSegmentIds"], [s["id"] for s in self.original["segments"]])

    def test_other_papers_and_wrong_pdf_rejected(self):
        for field, value in (("id", "paper-02"), ("sourceSha256", "0" * 64)):
            paper = copy.deepcopy(self.original)
            paper[field] = value
            with self.assertRaises(ValueError):
                repair(paper, self.pdf, self.overrides)

    def test_translation_source_mismatch_rejected(self):
        overrides = copy.deepcopy(self.overrides)
        overrides["segments"]["paper-01-s-bd0df1233583"]["sourceText"] = "Wrong article"
        with self.assertRaises(ValueError):
            repair(self.original, self.pdf, overrides)


if __name__ == "__main__":
    unittest.main()
