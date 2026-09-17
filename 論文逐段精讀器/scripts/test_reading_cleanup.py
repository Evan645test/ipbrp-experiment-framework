#!/usr/bin/env python3
"""Regression tests for conservative standalone-reading cleanup."""
import unittest
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from cleanup_reading_units import atomic_json, classify, overlap_fraction, restore, word_count


def segment(text, kind='body', box=None):
    return {'id': 'test', 'sourceText': text, 'kind': kind, 'fragments': [{'page': 1, 'bbox': box or [10, 10, 100, 20]}]}


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.bold = {'matchedCharacters': 20, 'boldFraction': 1.0}
        self.normal = {'matchedCharacters': 20, 'boldFraction': 0.0}
        self.table = [{'page': 1, 'bbox': [0, 0, 200, 200]}]

    def test_short_complete_sentence_is_kept(self):
        self.assertIsNone(classify(segment('To extend the research scope, several recommendations are offered.'), self.normal, []))

    def test_word_fragment_is_not_deleted_as_a_heading(self):
        self.assertIsNone(classify(segment('iors compared to the C-AI-MAF approach?'), self.normal, []))

    def test_shortness_alone_never_excludes(self):
        self.assertIsNone(classify(segment('Useful short content'), self.normal, []))

    def test_bold_heading_uses_pdf_typography(self):
        self.assertEqual(classify(segment('Study design'), self.bold, []), 'short-bold-label')

    def test_numbered_and_bulleted_items_are_kept(self):
        for text in ['(1) Preparation and Map Arrangement', '1. Prepare the materials', '○ Teachers should balance learning strategies.']:
            self.assertIsNone(classify(segment(text), self.bold, []))

    def test_table_title_is_not_a_standalone_step(self):
        self.assertEqual(classify(segment('TABLE 2 | ANCOVA results of learning achievement.', 'caption'), self.normal, []), 'table-title')

    def test_table_explanation_is_kept_even_if_misclassified_as_caption(self):
        for text in ['Table 2 shows that students performed better.', 'Table 2 reports the differences.', 'Table 2 demonstrates the results.']:
            self.assertIsNone(classify(segment(text, 'caption'), self.normal, []))

    def test_whole_table_matrix_is_not_deleted_as_a_title(self):
        self.assertIsNone(classify(segment('Table 5 Residuals Given: L W L 2 3 W 4 5', 'caption'), self.normal, []))

    def test_stats_footnotes_are_auxiliary_not_body_steps(self):
        for text in ['**p <.01', '*p < .05, **p < .001.', '*Z > 1.96.']:
            self.assertEqual(classify(segment(text), self.normal, []), 'statistical-table-note')

    def test_formula_in_body_is_kept(self):
        for text in ['x = 2', 'F = 4.25', 'p < .05', '0.25 0.32 0.45']:
            self.assertIsNone(classify(segment(text), self.bold if '=' in text else self.normal, []))

    def test_numeric_fragments_need_table_geometry(self):
        self.assertEqual(classify(segment('Control 28 75.36 13.19'), self.normal, self.table), 'numeric-table-fragment')
        self.assertIsNone(classify(segment('Control 28 75.36 13.19', box=[10, 300, 100, 320]), self.normal, self.table))

    def test_stats_headers_use_table_context(self):
        self.assertEqual(classify(segment('Group N Mean SD F p η2'), self.normal, self.table), 'table-header')
        self.assertIsNone(classify(segment('Group N Mean SD F p η2'), self.normal, []))

    def test_mathematical_table_model_label_is_contextual(self):
        text = 'Model equation:CT~1+time+group+(1|participant).'
        self.assertEqual(classify(segment(text), self.normal, self.table), 'table-model-label')
        self.assertIsNone(classify(segment(text), self.normal, []))

    def test_cited_and_human_reviewed_content_is_protected(self):
        self.assertIsNone(classify(segment('Summary'), self.bold, [], cited=True))
        item = segment('Summary'); item['reviewStatus'] = 'reviewed'
        self.assertIsNone(classify(item, self.bold, []))

    def test_figure_entry_points_are_not_removed_in_table_cleanup(self):
        self.assertIsNone(classify(segment('Fig. 1 System structure', 'caption'), self.bold, []))

    def test_overlap_is_containment_not_intersection_only(self):
        self.assertEqual(overlap_fraction([0, 0, 10, 10], [5, 5, 20, 20]), .25)
        self.assertEqual(overlap_fraction([0, 0, 10, 10], [0, 0, 20, 20]), 1)

    def test_hyphenated_words_and_numbers_count_consistently(self):
        self.assertEqual(word_count('C-AI-MAF 28 75.36'), 3)

    def test_restore_only_changes_cleanup_owned_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'public/data'; data.mkdir(parents=True)
            a = segment('Summary'); a['excluded'] = True
            b = segment('User excluded content'); b['id'] = 'manual'; b['excluded'] = True
            atomic_json(data / 'paper-01.json', {'id': 'paper-01', 'sourceSha256': 'a' * 64, 'segments': [a, b]})
            atomic_json(data / 'manifest.json', {'papers': [{'id': 'paper-01'}]})
            journal = {'papers': {'paper-01': {'sourceSha256': 'a' * 64, 'segments': {'test': {'sourceTextSha256': hashlib.sha256(b'Summary').hexdigest(), 'hadExcludedField': False, 'previousExcluded': None}}}}}
            with patch('builtins.print'):
                restore(root, journal)
            result = json.loads((data / 'paper-01.json').read_text())
            self.assertNotIn('excluded', result['segments'][0])
            self.assertTrue(result['segments'][1]['excluded'])
            self.assertEqual(json.loads((data / 'manifest.json').read_text())['papers'][0]['includedSegmentCount'], 1)

    def test_restore_refuses_changed_source_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'public/data'; data.mkdir(parents=True)
            a = segment('Changed text'); a['excluded'] = True
            path = data / 'paper-01.json'
            atomic_json(path, {'id': 'paper-01', 'sourceSha256': 'a' * 64, 'segments': [a]})
            before = path.read_bytes()
            journal = {'papers': {'paper-01': {'sourceSha256': 'a' * 64, 'segments': {'test': {'sourceTextSha256': hashlib.sha256(b'Summary').hexdigest(), 'hadExcludedField': False, 'previousExcluded': None}}}}}
            with self.assertRaisesRegex(ValueError, 'changed source text'):
                restore(root, journal)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
