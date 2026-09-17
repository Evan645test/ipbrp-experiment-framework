#!/usr/bin/env python3
"""Validate source evidence, immutable records, full crops and deterministic metadata."""
import copy
import hashlib
import json
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
import fitz
from build_paper01_companion import build, ROOT, SOURCE_SHA
from validate_phase_a import validate_paper
from companion_metadata import reconcile_companion
from build_references import atomic_json

class CompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paper=json.loads((ROOT/"public/data/paper-01.json").read_text())
        cls.before=json.loads((ROOT/"content/paper-01-before-companion.json").read_text())

    def test_all_original_records_and_references_preserved(self):
        for key in ("references","citations","readingOrderRepair"):
            self.assertEqual(self.paper[key],self.before[key])
        self.assertEqual([s['id'] for s in self.paper['segments']],[s['id'] for s in self.before['segments']])
        self.assertEqual(self.paper['readingUnitRepairs'][:-1],self.before['readingUnitRepairs'])
        self.assertEqual(hashlib.sha256((ROOT/"public/papers/paper-01.pdf").read_bytes()).hexdigest(),SOURCE_SHA)
        self.assertEqual(len(self.paper["segments"]),156)

    def test_every_link_has_actual_passage_evidence(self):
        segments={s["id"]:s for s in self.paper["segments"]}
        links=self.paper["exhibitCompanion"]["links"]
        self.assertEqual(len({(l["segmentId"],l["exhibitId"]) for l in links}),len(links))
        self.assertEqual(sum(l["method"]=="semantic" and l["confidence"]=="high" for l in links),20)
        self.assertGreater(sum(l["confidence"]=="candidate" for l in links),0)
        for link in links:
            source=segments[link["segmentId"]]
            self.assertFalse(source.get("excluded"))
            self.assertEqual(source["kind"],"body")
            self.assertIn(link["evidenceQuote"],source["sourceText"])
            self.assertEqual(hashlib.sha256(source["sourceText"].encode()).hexdigest(),link["sourceTextSha256"])

    def test_all_25_studies_grounded_and_not_human_reviewed(self):
        studies=self.paper["exhibitCompanion"]["studies"]
        self.assertEqual(set(studies),{e["id"] for e in self.paper["exhibits"]})
        for study in studies.values():
            self.assertEqual(study["status"],"ai-draft")
            self.assertTrue(study["sourceSegmentIds"])
        self.assertIn("p=0.518",studies["paper-01-table-7"]["limitsZh"][-1])
        self.assertIn("LT→DP",studies["paper-01-figure-15"]["limitsZh"][-1])
        self.assertEqual(build(self.paper),self.paper)

    def test_corrected_line_charts_do_not_contain_tables_or_headers(self):
        with fitz.open(ROOT/"public/papers/paper-01.pdf") as pdf:
            for number, forbidden in ((12,"Table 4"),(13,"Table 6")):
                e=next(e for e in self.paper["exhibits"] if e["kind"]=="figure" and e["number"]==str(number))
                text=pdf[e["page"]-1].get_textbox(fitz.Rect(e["bbox"]))
                self.assertNotIn(forbidden,text)
                self.assertNotIn("Y. Chen",text)
                self.assertIn(f"Fig. {number}.",text)
                pix=fitz.Pixmap(ROOT/"public"/e["imageUrl"].lstrip("/"))
                self.assertGreater(pix.width,1900)
                self.assertGreater(pix.height,500)

    def test_validator_rejects_stale_or_fabricated_evidence(self):
        validate_paper(self.paper,ROOT/"public")
        for key,value in (("sourceTextSha256","wrong"),("evidenceQuote","Fabricated original statement.")):
            changed=copy.deepcopy(self.paper);changed["exhibitCompanion"]["links"][0][key]=value
            with self.assertRaises(ValueError):
                validate_paper(changed,ROOT/"public")

    def test_other_seven_paper_sources_preserved(self):
        expected={"02":"b1804aef466fb7d21b0bac4d5ec8ee0bb9f10f17688ab2ee6c6c6ff15807fe0b","03":"b64d215ea8702f181894419d28317a3d119d9418de44ae0f1248c253fe49acc2","04":"0baa0df0855d0f54a23d3bbbe855683dbadc44fa1fd0f8285e37b83c9464b242","05":"73b8470a7b80915304591edb888b25d91c2eea5f9628af65e8560fc26b683b10","06":"9b28051f7109062a5407da5ef6f9df58c9692d4104ebfea4cc0020071b5ba18f","07":"85c80e6ce68b12df48522c36c3ff4421391596ddacd85f444fde74d6d521b833","08":"8d160791c671f8ea25778bc3bb58848af83ea77912fd63bb79aa33c7b05f5c3d"}
        for number,digest in expected.items():
            current=ROOT/f"public/data/paper-{number}.json"
            paper=json.loads(current.read_text())
            baseline=ROOT/f"content/paper-{number}-before-remaining-companion.json" if paper.get('remainingPaperProcessing') else current
            self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),digest)
            if paper.get('remainingPaperProcessing'):
                self.assertEqual(paper['remainingPaperProcessing']['beforeDataSha256'],digest)

    def test_curator_source_changes_invalidate_but_do_not_erase_companion(self):
        incoming=copy.deepcopy(self.before)
        sid="paper-01-s-40757fb92c91"
        next(s for s in incoming["segments"] if s["id"]==sid)["sourceText"] += " Additional manually corrected extraction."
        reconciled=reconcile_companion(incoming,self.paper)
        self.assertEqual(reconciled["exhibits"],self.paper["exhibits"])
        self.assertFalse(any(l["segmentId"]==sid for l in reconciled["exhibitCompanion"]["links"]))
        self.assertEqual(len(reconciled["exhibitCompanion"]["studies"]),25)
        validate_paper(reconciled,ROOT/"public")
        rebuilt=build(reconciled)
        self.assertFalse(any(l["segmentId"]==sid and l["method"]=="semantic" and l["confidence"]=="high" for l in rebuilt["exhibitCompanion"]["links"]))
        original_bytes=(ROOT/"public/data/paper-01.json").read_bytes()
        manifest_bytes=(ROOT/"public/data/manifest.json").read_bytes()
        with tempfile.TemporaryDirectory(prefix="paper01-curator-check-") as directory:
            fixture=Path(directory)/"edited.json"
            atomic_json(fixture,incoming)
            checked=subprocess.run([sys.executable,str(ROOT/"scripts/import_curated_paper.py"),str(fixture),"--check-only"],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)
        self.assertEqual((ROOT/"public/data/paper-01.json").read_bytes(),original_bytes)
        self.assertEqual((ROOT/"public/data/manifest.json").read_bytes(),manifest_bytes)

if __name__=="__main__":
    unittest.main()
