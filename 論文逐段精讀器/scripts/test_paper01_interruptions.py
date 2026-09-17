#!/usr/bin/env python3
import copy
import json
import unittest

from repair_paper01_interruptions import PROJECT, GROUPS, interrupted_candidates, repair


class InterruptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((PROJECT / 'content/paper-01-before-interruption-repair.json').read_text())['paper']
        cls.after = repair(cls.before)
        cls.old = {s['id']: s for s in cls.before['segments']}
        cls.new = {s['id']: s for s in cls.after['segments']}

    def test_all_six_verified_interruptions_merged_without_exhibit_text(self):
        for anchor, tail, _, _, separator, faithful, plain in GROUPS:
            self.assertEqual(self.new[anchor]['sourceText'], self.old[anchor]['sourceText'] + separator + self.old[tail]['sourceText'])
            self.assertEqual(self.new[anchor]['fragments'], self.old[anchor]['fragments'] + self.old[tail]['fragments'])
            self.assertEqual(self.new[anchor]['translation']['faithfulZh'], faithful)
            self.assertEqual(self.new[anchor]['translation']['plainZh'], plain)
            self.assertTrue(self.new[tail]['excluded'])
            self.assertEqual(self.new[tail]['mergedIntoSegmentId'], anchor)

    def test_archive_and_other_units_preserved(self):
        self.assertEqual(set(self.old), set(self.new))
        anchors = {g[0] for g in GROUPS}
        for segment_id, previous in self.old.items():
            if segment_id not in anchors:
                for field in ['sourceText', 'translation', 'fragments']:
                    self.assertEqual(previous[field], self.new[segment_id][field])
        self.assertEqual(self.before['references'], self.after['references'])
        self.assertEqual(sum(not s.get('excluded') for s in self.after['segments']), 111)
        self.assertFalse(self.new['paper-01-s-68079e87c86d'].get('excluded'))

    def test_hyphenated_group_name_and_numeric_continuation(self):
        self.assertIn('than the C-PBRP group over time.', self.new['paper-01-s-2f2cfe8f1c19']['sourceText'])
        self.assertIn('Meanage = 5.68 years', self.new['paper-01-s-70f25539ff85']['sourceText'])
        self.assertIn('47 名兒童', self.new['paper-01-s-70f25539ff85']['translation']['faithfulZh'])

    def test_all_explanations_and_new_citations_follow_merged_anchor(self):
        exhibits = {e['id']: e for e in self.after['exhibits']}
        self.assertEqual(exhibits['paper-01-figure-2']['explanationSegmentIds'], ['paper-01-s-1a15e48ca5e3'])
        self.assertEqual(exhibits['paper-01-figure-3']['explanationSegmentIds'], ['paper-01-s-adeafd695d68'])
        for anchor, tail, *_ in GROUPS:
            old_reference_ids = {r for c in self.before['citations'] if c['segmentId'] in [anchor, tail] for r in c['referenceIds']}
            new_reference_ids = {r for c in self.after['citations'] if c['segmentId'] == anchor for r in c['referenceIds']}
            self.assertTrue(old_reference_ids.issubset(new_reference_ids))

    def test_idempotent_and_no_unresolved_narrative_candidates(self):
        self.assertEqual(len(interrupted_candidates(self.before)), 6)
        self.assertEqual(interrupted_candidates(self.after), [])
        self.assertEqual(repair(self.after), self.after)

    def test_changed_boundary_or_reviewed_translation_rejected(self):
        altered = copy.deepcopy(self.before)
        altered['segments'][next(i for i,s in enumerate(altered['segments']) if s['id'] == GROUPS[0][0])]['sourceText'] += '.'
        with self.assertRaises(ValueError):
            repair(altered)
        reviewed = copy.deepcopy(self.before)
        next(s for s in reviewed['segments'] if s['id'] == GROUPS[0][1])['translation']['status'] = 'reviewed'
        with self.assertRaises(ValueError):
            repair(reviewed)


if __name__ == '__main__':
    unittest.main()
