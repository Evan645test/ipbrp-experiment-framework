#!/usr/bin/env python3
"""Source-evidence regressions for incomplete reading units."""
import unittest
from assess_paragraph_completeness import assess


def unit(identifier, text, box):
    return {'id': identifier, 'sourceText': text, 'kind': 'body', 'fragments': [{'page': 1, 'bbox': box, 'pageSize': [600, 800]}]}


class CompletenessTests(unittest.TestCase):
    def setUp(self):
        self.words = [(10, 10, 60, 20, 'learning', 0, 0, 0), (80, 10, 100, 20, 'engage\u00ad', 0, 0, 1), (10, 25, 30, 35, 'ment', 1, 0, 0), (40, 25, 90, 35, 'compared', 1, 0, 1)]
        self.left = unit('a', 'Does the approach improve learning engage', [10, 10, 110, 20])
        self.right = unit('b', 'ment compared to the control?', [10, 25, 110, 35])

    def test_split_word_invalidates_independent_explanation(self):
        issues, evidence = assess({'segments': [self.left, self.right]}, {1: self.words})
        self.assertEqual(issues['a']['status'], 'fragment')
        self.assertEqual(issues['b']['status'], 'fragment')
        self.assertEqual(issues['a']['relatedSegmentIds'], ['b'])
        self.assertEqual(evidence[0]['word'], 'engagement')

    def test_normal_pdf_line_wrap_is_not_a_fragment(self):
        complete = unit('a', 'Does the approach improve learning engagement compared to the control?', [10, 10, 110, 35])
        issues, _ = assess({'segments': [complete]}, {1: self.words})
        self.assertEqual(issues, {})

    def test_complete_short_sentence_and_bullet_are_preserved(self):
        for text in ['Further recommendations are offered.', '○ Teachers should balance learning strategies.', 'This finding supports the previous result.']:
            issues, _ = assess({'segments': [unit('a', text, [10, 10, 110, 20])]}, {1: []})
            self.assertEqual(issues, {})

    def test_context_dependency_is_a_review_cue_not_a_verdict(self):
        issues, _ = assess({'segments': [unit('a', 'these technological tools in learning.', [10, 10, 110, 20])]}, {1: []})
        self.assertEqual(issues['a']['status'], 'needs-review')

    def test_missing_word_prefix_is_not_guessed_or_discarded(self):
        issues, _ = assess({'segments': [self.right]}, {1: self.words})
        self.assertEqual(issues['b']['status'], 'fragment')
        self.assertEqual(issues['b']['relatedSegmentIds'], [])
        self.assertEqual(self.right['sourceText'], 'ment compared to the control?')

    def test_other_column_cannot_supply_a_continuation(self):
        words = [(310, 10, 360, 20, 'learning', 0, 0, 0), (380, 10, 400, 20, 'engage\u00ad', 0, 0, 1), (10, 25, 30, 35, 'ment', 1, 0, 0)]
        left = unit('a', 'learning engage', [310, 10, 410, 20])
        right = unit('b', 'ment compared to control?', [10, 25, 110, 35])
        issues, _ = assess({'segments': [left, right]}, {1: words})
        self.assertNotEqual(issues['a']['status'], 'fragment')

    def test_numbered_question_must_be_whole(self):
        left = unit('a', '(1) Does the approach improve movement skills', [10, 10, 110, 20])
        right = unit('b', 'performance compared to the control?', [10, 25, 110, 35])
        words = [(10, 10, 60, 20, 'movement', 0, 0, 0), (80, 10, 100, 20, 'skills', 0, 0, 1), (10, 25, 90, 35, 'performance', 1, 0, 0)]
        issues, _ = assess({'segments': [left, right]}, {1: words})
        self.assertEqual(issues['a']['status'], 'fragment')
        self.assertEqual(issues['b']['status'], 'fragment')

    def test_auxiliary_and_human_reviewed_content_is_not_overwritten(self):
        self.left['reviewStatus'] = 'reviewed'; self.right['excluded'] = True
        issues, _ = assess({'segments': [self.left, self.right]}, {1: self.words})
        self.assertEqual(issues, {})


if __name__ == '__main__':
    unittest.main()
