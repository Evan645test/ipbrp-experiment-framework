#!/usr/bin/env python3
"""Read-only regression tests for conservative citation and DOI matching."""
import unittest

from build_references import NOISE, citation_index, context_for, doi_for, is_entry_start, title_for, crossref_title
from fetch_publisher_abstracts import AbstractParser
from fetch_database_abstracts import reconstruct_abstract, match_work
from resolve_reference_dois import matching_candidate
from fetch_eric_abstracts import matches as eric_matches
from fetch_openaire_abstracts import matches as openaire_matches, complete_description, records as openaire_records
from fetch_ebsco_abstracts import source_record as ebsco_source_record
from fetch_doaj_abstracts import as_work as doaj_work
from fetch_curated_reference_abstracts import english_abstract, verify_identity


class FakePage:
    def __init__(self, uris):
        self.uris = uris

    def get_links(self):
        return [{"uri": uri} for uri in self.uris]


class ReferenceTests(unittest.TestCase):
    def test_ebsco_uses_only_complete_public_abstract_field(self):
        reference = {'doi': '10.1007/right', 'title': 'A complete title of an educational research article', 'identityStatus': 'verified'}
        text = 'This complete database Abstract describes educational research methods and findings.'
        info = {'doi': reference['doi'], 'title': reference['title'], 'ab': text}
        response = {'props': {'isAuthenticated': False, 'pageProps': {'data': {'item': {'itemInfo': info}}}}}
        self.assertEqual(ebsco_source_record(reference, response, 'https://openurl.ebsco.com/example', {})['originalText'], text)
        info['ab'] = ''
        info['tldr'] = text
        self.assertEqual(ebsco_source_record(reference, response, 'https://openurl.ebsco.com/example', {})['status'], 'not-found')
        info['doi'] = '10.1007/wrong'
        with self.assertRaises(ValueError):
            ebsco_source_record(reference, response, 'https://openurl.ebsco.com/example', {})
        info['doi'] = reference['doi']
        response['props']['isAuthenticated'] = True
        with self.assertRaises(ValueError):
            ebsco_source_record(reference, response, 'https://openurl.ebsco.com/example', {})

    def test_doaj_conflicting_identifiers_are_not_chosen(self):
        work = doaj_work({'bibjson': {'title': 'A complete title', 'year': '2024', 'identifier': [{'type': 'doi', 'id': 'https://doi.org/10.1007/one'}, {'type': 'doi', 'id': '10.1007/two'}]}})
        self.assertEqual(work['doi'], '')

    def test_official_bilingual_abstract_extracts_full_english_section(self):
        parser = AbstractParser()
        text = 'This complete English abstract describes an educational study with methods and findings.'
        parser.feed('<section class="abstract"><h2>Abstract</h2><p>Abstrak</p><p>Teks bahasa Indonesia.</p><p>Abstract</p><p>' + text + '</p><p>Keywords: research</p></section>')
        self.assertEqual(english_abstract(parser), text)

    def test_official_metadata_retains_first_author_and_checks_year(self):
        parser = AbstractParser()
        parser.feed('<meta name="citation_title" content="A complete research title"><meta name="citation_author" content="Alice Chen"><meta name="citation_author" content="Bob Lin"><meta name="citation_date" content="2024/01/01">')
        reference = {'title': 'A complete research title', 'doi': None, 'firstAuthor': 'Chen', 'year': '2024'}
        self.assertEqual(verify_identity(reference, parser), reference['title'])
        reference['year'] = '1997'
        with self.assertRaises(ValueError):
            verify_identity(reference, parser)

    def test_openaire_requires_exact_doi_or_author_and_year(self):
        reference = {'title': 'A complete title of an educational research article', 'doi': '10.1007/right', 'identityStatus': 'verified', 'firstAuthor': 'Chen', 'year': '2024'}
        record = {'title': {'$': reference['title']}, 'pid': {'@classid': 'doi', '$': reference['doi']}, 'creator': {'@rank': '1', '$': 'Alice Chen'}, 'dateofacceptance': {'$': '2024-01-01'}}
        self.assertTrue(openaire_matches(reference, record, {}))
        record['pid']['$'] = '10.1007/wrong'
        self.assertFalse(openaire_matches(reference, record, {}))
        reference['doi'] = None
        self.assertTrue(openaire_matches(reference, record, {}))
        record['creator']['$'] = 'Alice Lin'
        self.assertFalse(openaire_matches(reference, record, {}))

    def test_openaire_does_not_merge_different_or_inferred_descriptions(self):
        text = 'This complete source abstract describes educational research methods and findings.'
        self.assertEqual(complete_description({'description': {'$': text}}), text)
        self.assertEqual(complete_description({'description': {'$': text, '@inferred': True}}), '')
        self.assertEqual(complete_description({'description': {'$': text + '...'}}), '')
        with self.assertRaises(ValueError):
            complete_description({'description': [{'$': text}, {'$': 'Another unrelated source description reports different experiments and conclusions.'}]})

    def test_openaire_truncated_results_are_not_treated_as_complete(self):
        with self.assertRaises(ValueError):
            openaire_records({'response': {'header': {'total': {'$': 2}}, 'results': {'result': [{}]}}})

    def test_eric_matches_author_year_not_only_title(self):
        reference = {'title': 'A study of concept maps and learning outcomes', 'firstAuthor': 'Chen', 'year': '2024', 'identityStatus': 'not-checked', 'doi': None}
        record = {'title': reference['title'], 'author': ['Chen, Alice'], 'publicationdateyear': 2024}
        self.assertTrue(eric_matches(reference, record, {}))
        record['author'] = ['Lin, Alice']
        self.assertFalse(eric_matches(reference, record, {}))
        record['author'] = ['Chen, Alice']
        record['publicationdateyear'] = 2011
        self.assertFalse(eric_matches(reference, record, {}))

    def test_crossref_subtitle_is_part_of_identity(self):
        self.assertEqual(crossref_title({'title': ['Observing Interaction'], 'subtitle': ['An Introduction to Sequential Analysis']}), 'Observing Interaction: An Introduction to Sequential Analysis')
        self.assertEqual(crossref_title({'title': ['Complete title: Existing subtitle'], 'subtitle': ['Existing subtitle']}), 'Complete title: Existing subtitle')

    def test_database_abstract_reconstructs_full_word_order(self):
        self.assertEqual(reconstruct_abstract({'This': [0], 'source': [1, 4], 'abstract': [2], 'preserves': [3], 'word': [5], 'order.': [6]}), 'This source abstract preserves source word order.')

    def test_database_abstract_missing_or_duplicate_positions_are_rejected(self):
        for index in [{'One': [0], 'word': [2]}, {'One': [0], 'Two': [0]}, {'One': [-1]}, {'One': [True]}]:
            with self.assertRaises(ValueError):
                reconstruct_abstract(index)

    def test_database_doi_identity_cannot_be_guessed_from_title(self):
        reference = {'doi': '10.1007/right', 'title': 'Exactly matching title', 'identityStatus': 'verified'}
        self.assertFalse(match_work(reference, {'doi': 'https://doi.org/10.1007/wrong', 'title': reference['title']}, {}))

    def test_doi_search_requires_author_and_year_and_handles_null_dates(self):
        reference = {'title': 'A full title of a learning study', 'firstAuthor': 'Chen', 'year': '2024'}
        candidate = {'DOI': '10.1007/verified', 'title': [reference['title']], 'author': [{'family': 'Chen'}], 'published': {'date-parts': [[None]]}}
        self.assertIsNone(matching_candidate(reference, candidate))
        candidate['published']['date-parts'] = [[2024]]
        self.assertIsNotNone(matching_candidate(reference, candidate))
        candidate['author'][0]['family'] = 'Lin'
        self.assertIsNone(matching_candidate(reference, candidate))

    def test_journal_in_bibliography_is_not_a_running_header(self):
        self.assertIsNone(NOISE.search('Games.” Computers & Education 56, no. 3: 604–615. https://doi.org/10.1016/test.'))
        self.assertIsNone(NOISE.search('A Review.” Journal of Computer Assisted Learning 41, no. 1: 1–20.'))
        self.assertTrue(NOISE.search('Journal of Computer Assisted Learning, 2025'))

    def test_title_quotation_and_terminal_question(self):
        self.assertEqual(title_for('“Roles and Trends: A Review.” Interactive Learning Environments 30, no. 4.'), 'Roles and Trends: A Review')
        self.assertEqual(title_for('““Games Are Made for Fun”: Lessons on Learning.” Computers & Education 56.'), '“Games Are Made for Fun”: Lessons on Learning')
        self.assertEqual(title_for('What is computational thinking? Acm Inroads, 2(1).'), 'What is computational thinking')
        self.assertEqual(title_for('April). New frameworks for studying thinking. Conference.'), 'New frameworks for studying thinking')
        self.assertEqual(title_for('Constructivism: From Philosophy to Practice. https:// eric.ed.gov/?id=ED444966.'), 'Constructivism: From Philosophy to Practice')
        self.assertEqual(title_for('A survey on hallucination in large language models. arXiv preprint arXiv:2309.01219.'), 'A survey on hallucination in large language models')
        self.assertEqual(title_for('Mind in Society: Development of Higher Processes, edited by M. Cole.'), 'Mind in Society: Development of Higher Processes')
        self.assertEqual(title_for('Thought and language (A. Kozulin, trans).'), 'Thought and language')

    def lines(self, *texts):
        return [{"page": 1, "text": text} for text in texts]

    def test_overlapping_link_is_not_identity(self):
        lines = self.lines("https://doi.org/10.1007/right")
        document = [FakePage(["https://doi.org/10.1007/wrong", "https://doi.org/10.1007/right"])]
        self.assertEqual(doi_for(lines[0]["text"], lines, document), "10.1007/right")

    def test_split_doi_and_truncated_link(self):
        lines = self.lines("https://doi.org/10.1111/bjet.", "13540.")
        document = [FakePage(["https://doi.org/10.1111/bjet"])]
        self.assertEqual(doi_for(" ".join(line["text"] for line in lines), lines, document), "10.1111/bjet.13540")

    def test_multiple_dois_are_not_guessed(self):
        lines = self.lines("https://doi.org/10.1007/first https://doi.org/10.1111/second")
        document = [FakePage(["https://doi.org/10.1007/first", "https://doi.org/10.1111/second"])]
        self.assertIsNone(doi_for(lines[0]["text"], lines, document))
        self.assertIsNone(doi_for(lines[0]["text"], lines, [FakePage([])]))

    def test_doi_does_not_absorb_next_url(self):
        lines = self.lines("https://doi.org/10.1007/right https://example.org/other")
        self.assertEqual(doi_for(lines[0]["text"], lines, [FakePage([])]), "10.1007/right")

    def test_article_number_is_not_a_doi_suffix(self):
        lines = self.lines('https://doi.org/10.1057/s41599-025-04846-4. Article 558.')
        self.assertEqual(doi_for(lines[0]['text'], lines, [FakePage([])]), '10.1057/s41599-025-04846-4')

    def test_lowercase_surname_prefix(self):
        for author in ["van Peppen, L. M.", "de Bruin, A. B.", "von Eck, R.", "Chen, Y."]:
            self.assertTrue(is_entry_start({"text": author}), author)

    def test_context_is_literal_source(self):
        source = "Earlier finding. Drawing on Huang (2016), we designed the activity. Another claim."
        start = source.index("Huang")
        self.assertEqual(context_for(source, start, start + 12), "Drawing on Huang (2016), we designed the activity.")

    def test_same_author_year_is_ambiguous(self):
        paper = {"segments": [{"id": "s", "sourceText": "Studies support this (Liu et al., 2024)."}]}
        references = [{"id": "r1", "firstAuthor": "Liu", "year": "2024"}, {"id": "r2", "firstAuthor": "Liu", "year": "2024"}]
        citations = citation_index(paper, references)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["matchStatus"], "ambiguous")
        self.assertEqual(citations[0]["referenceIds"], ["r1", "r2"])

    def test_year_suffix_is_preserved(self):
        paper = {"segments": [{"id": "s", "sourceText": "Huang (2024a) supports this."}]}
        references = [{"id": "r1", "firstAuthor": "Huang", "year": "2024a"}, {"id": "r2", "firstAuthor": "Huang", "year": "2024b"}, {"id": "r3", "firstAuthor": "Huang", "year": "2024"}]
        citations = citation_index(paper, references)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["referenceIds"], ["r1"])

    def test_unknown_author_is_not_invented(self):
        paper = {"segments": [{"id": "s", "sourceText": "Unknown (2024) supports this."}]}
        self.assertEqual(citation_index(paper, [{"id": "r1", "firstAuthor": "Huang", "year": "2024"}]), [])

    def test_publisher_abstract_stops_before_references(self):
        parser = AbstractParser()
        parser.feed('<html><head><meta name="citation_title" content="Fixture study"></head><body><section id="Abs1"><h2>Abstract</h2><div><p>The study examined <em>learning</em> outcomes.</p></div></section><section><h2>References</h2><p>Not abstract content.</p></section></body></html>')
        self.assertEqual(parser.abstract(), 'The study examined learning outcomes.')
        self.assertEqual(parser.metadata['citation_title'], 'Fixture study')

    def test_generic_description_is_not_assumed_abstract(self):
        parser = AbstractParser()
        parser.feed('<meta name="description" content="Subscribe to this journal">')
        self.assertEqual(parser.abstract(), '')

    def test_abstract_anchor_on_heading_captures_parent_section(self):
        parser = AbstractParser()
        parser.feed('<section><h2 id="Abs1">Abstract</h2><p>All source sentences belong here.</p></section><section><p>Unrelated references.</p></section>')
        self.assertEqual(parser.abstract(), 'All source sentences belong here.')


if __name__ == "__main__":
    unittest.main()
