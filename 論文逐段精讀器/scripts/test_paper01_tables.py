#!/usr/bin/env python3
import copy
import json
import re
import unittest

import fitz

from repair_paper01_tables import PROJECT, REVISION, SPECS, repair
from cleanup_reading_units import classify


class CompleteTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((PROJECT/'content/paper-01-before-complete-table-repair.json').read_text())['paper']
        cls.after = repair(cls.before)
        cls.by_id = {s['id']: s for s in cls.after['segments']}

    def test_all_ten_tables_have_exactly_one_complete_reading_step(self):
        for exhibit in [e for e in self.after['exhibits'] if e['kind'] == 'table']:
            segment = self.by_id[exhibit['captionSegmentId']]
            self.assertFalse(segment.get('excluded'))
            self.assertEqual(segment['kind'], 'caption')
            self.assertEqual(segment['fragments'][0]['bbox'], exhibit['bbox'])
            self.assertEqual(segment['exhibitIds'], [exhibit['id']])
            self.assertEqual(segment['section'], self.by_id[exhibit['explanationSegmentIds'][0]]['section'])
            box = fitz.Rect(exhibit['bbox'])
            steps = [s for s in self.after['segments'] if not s.get('excluded') and len(s['fragments']) == 1
                     and s['fragments'][0]['page'] == exhibit['page'] and box.contains(fitz.Rect(s['fragments'][0]['bbox']))]
            self.assertEqual([s['id'] for s in steps], [segment['id']])
        self.assertEqual(sum(not s.get('excluded') for s in self.after['segments']), 101)

    def test_table_three_includes_all_sections_and_formula(self):
        segment = self.by_id[SPECS['3'][2]]
        for text in ['Table 3', 'Fixed effect', 'Random effect', 'Model fit', 'Model equation:', '0.29', '0.47']:
            self.assertIn(text, segment['sourceText'])
        for text in ['固定效應', '隨機效應', '模型配適', '模型公式', '0.29', '0.47']:
            self.assertIn(text, segment['translation']['faithfulZh'])
        self.assertTrue(self.by_id['paper-01-s-937fa0a15f54']['excluded'])
        self.assertEqual(self.by_id['paper-01-s-937fa0a15f54']['mergedIntoSegmentId'], segment['id'])

    def test_all_original_values_and_records_are_retained(self):
        self.assertEqual({s['id'] for s in self.before['segments']}, set(self.by_id))
        self.assertEqual(self.before['references'], self.after['references'])
        self.assertEqual(self.before['citations'], self.after['citations'])
        anchors = {s[2] for s in SPECS.values()}
        for previous in self.before['segments']:
            if previous['id'] not in anchors:
                for key in ['sourceText', 'translation', 'fragments']:
                    self.assertEqual(previous[key], self.by_id[previous['id']][key])
        for record in self.after['readingUnitRepairs']:
            if record['revision'] != REVISION:
                continue
            segment = self.by_id[record['targetId']]
            original = '\n'.join(s['sourceText'] for s in record['previousSegments'])
            self.assertEqual(segment['sourceText'], original)
            self.assertEqual(re.findall(r'\d+(?:\.\d+)?', original), re.findall(r'\d+(?:\.\d+)?', segment['translation']['faithfulZh']))

    def test_crops_contain_titles_all_cells_and_no_other_figure_or_table(self):
        with fitz.open(PROJECT/'public/papers/paper-01.pdf') as pdf:
            for number, (page, bbox, target_id) in SPECS.items():
                text = pdf[page-1].get_text('text', clip=fitz.Rect(bbox), sort=True)
                self.assertIn('Table '+number+'\n', text)
                self.assertEqual(re.findall(r'Table\s+(\d+)', text), [number])
                self.assertNotRegex(text, r'Fig\.\s+\d+')
                self.assertNotIn('Y. Chen et al.', text)
                self.assertNotRegex(text, r'\n'+str(page)+r'\s*$')
                exhibit = next(e for e in self.after['exhibits'] if e['kind']=='table' and e['number']==number)
                image_path = PROJECT/'public'/exhibit['imageUrl'].lstrip('/')
                self.assertTrue(image_path.is_file())
                image = fitz.Pixmap(str(image_path))
                self.assertAlmostEqual(image.width, (bbox[2]-bbox[0])*300/72, delta=2)
                self.assertAlmostEqual(image.height, (bbox[3]-bbox[1])*300/72, delta=2)
                self.assertEqual(self.by_id[target_id]['fragments'][0]['page'], page)

    def test_idempotence_and_reviewed_content_protected(self):
        self.assertEqual(repair(self.after), self.after)
        reviewed = copy.deepcopy(self.before)
        next(s for s in reviewed['segments'] if s['id'] == SPECS['3'][2])['translation']['status'] = 'reviewed'
        with self.assertRaises(ValueError):
            repair(reviewed)

    def test_cleanup_does_not_mistake_whole_tables_for_short_titles(self):
        regions = [e for e in self.after['exhibits'] if e['kind'] == 'table']
        for exhibit in regions:
            segment = self.by_id[exhibit['captionSegmentId']]
            self.assertIsNone(classify(segment, {'matchedCharacters': 0, 'boldFraction': 0}, regions))


if __name__ == '__main__':
    unittest.main()
