#!/usr/bin/env python3
import json
import unittest
import fitz
from repair_paper01_spots import PROJECT, SOURCE_SHA, ANCHOR, TAIL, TABLE, repair, update_translation_cache


class Paper01SpotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((PROJECT / 'content/paper-01-before-page10-11-repair.json').read_text())['paper']
        cls.after = repair(cls.before)
        cls.by_id = {s['id']: s for s in cls.after['segments']}

    def test_cross_page_paragraph_complete_not_combined_with_table(self):
        anchor = self.by_id[ANCHOR]
        self.assertEqual([f['page'] for f in anchor['fragments']], [10, 11])
        self.assertTrue(anchor['sourceText'].endswith('indicating good reliability (Campbell et al., 2013).'))
        self.assertNotIn('LI Listen to the instructor', anchor['sourceText'])
        self.assertTrue(self.by_id[TAIL]['excluded'])
        self.assertEqual(self.by_id[TAIL]['mergedIntoSegmentId'], ANCHOR)

    def test_complete_table_one_unit(self):
        table = self.by_id[TABLE]
        self.assertTrue(table['sourceText'].startswith('Table 1 Coding scheme. Code Behavior Description'))
        self.assertEqual(table['fragments'][0]['bbox'], [37, 541.27, 510.51, 689])
        self.assertEqual(table['kind'], 'caption')
        for code in ['LI', 'II', 'DP', 'CA', 'PB', 'EP', 'AH', 'DA', 'DB', 'ET', 'SH', 'IB']:
            self.assertIn(code+'｜', table['translation']['faithfulZh'])

    def test_native_link_is_within_explanatory_paragraph(self):
        paragraph = self.by_id['paper-01-s-3b225b28632e']
        self.assertEqual(paragraph['kind'], 'body')
        mention = next(m for m in paragraph['exhibitMentions'] if m['exhibitId'] == 'paper-01-table-2')
        self.assertEqual(mention['page'], 11)
        self.assertLess(mention['bbox'][1], 310)
        with fitz.open(PROJECT/'public/papers/paper-01.pdf') as pdf:
            box=fitz.Rect(mention['bbox'])+(-1,-1,1,1)
            text=pdf[10].get_text('text',clip=box)
            self.assertIn('Table',text)
            self.assertIn('2',text)

    def test_crops_include_title_and_exclude_page_number(self):
        with fitz.open(PROJECT/'public/papers/paper-01.pdf') as pdf:
            for exhibit in self.after['exhibits']:
                if exhibit['kind'] != 'table' or exhibit['number'] not in ['1','2']:
                    continue
                text=pdf[exhibit['page']-1].get_text('text',clip=fitz.Rect(exhibit['bbox']))
                self.assertIn('Table '+exhibit['number'],text)
                self.assertNotIn('\n'+str(exhibit['page'])+' ',text)
                self.assertTrue((PROJECT/'public'/exhibit['imageUrl'].lstrip('/')).is_file())

    def test_record_and_reference_preservation(self):
        self.assertEqual({s['id'] for s in self.before['segments']},set(self.by_id))
        self.assertEqual(self.before['references'],self.after['references'])
        for segment in self.before['segments']:
            if segment['id'] not in [ANCHOR,TABLE]:
                self.assertEqual(segment['sourceText'],self.by_id[segment['id']]['sourceText'])
                self.assertEqual(segment['translation'],self.by_id[segment['id']]['translation'])
        self.assertEqual(sum(not s.get('excluded') for s in self.after['segments']),117)

    def test_idempotent(self):
        self.assertEqual(repair(self.after),self.after)

    def test_translation_cache_updates_only_two_verified_records(self):
        cache = {'papers': {'paper-01': {'sourceSha256': SOURCE_SHA, 'segments': {
            s['id']: s['translation'] for s in self.before['segments']}},
            'paper-02': {'segments': {'unchanged': {'faithfulZh': '保留'}}}}}
        updated = update_translation_cache(cache, self.after)
        self.assertEqual(updated['papers']['paper-02'], cache['papers']['paper-02'])
        for segment_id, translation in cache['papers']['paper-01']['segments'].items():
            expected = self.by_id[segment_id]['translation'] if segment_id in [ANCHOR, TABLE] else translation
            self.assertEqual(updated['papers']['paper-01']['segments'][segment_id], expected)
        self.assertNotEqual(cache['papers']['paper-01']['segments'][ANCHOR], updated['papers']['paper-01']['segments'][ANCHOR])
        self.assertEqual(update_translation_cache(updated, self.after), updated)

    def test_translation_cache_rejects_source_mismatch_and_reviewed_replacement(self):
        cache = {'papers': {'paper-01': {'sourceSha256': 'wrong', 'segments': {}}}}
        with self.assertRaises(ValueError):
            update_translation_cache(cache, self.after)
        cache['papers']['paper-01']['sourceSha256'] = SOURCE_SHA
        cache['papers']['paper-01']['segments'][ANCHOR] = {'status': 'reviewed', 'faithfulZh': '人工譯文'}
        with self.assertRaises(ValueError):
            update_translation_cache(cache, self.after)


if __name__ == '__main__':
    unittest.main()
