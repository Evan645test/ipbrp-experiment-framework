#!/usr/bin/env python3
"""Regression checks for source retention, reconstructed units, and all seven crops."""
import copy
import hashlib
import json
import unittest
import fitz
from build_remaining_companions import ROOT, REVISION, core
from companion_metadata import reconcile_companion
from validate_phase_a import validate_paper
from audit_reading_quality import audit

class RemainingCompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papers={f'paper-{n:02d}':json.loads((ROOT/f'public/data/paper-{n:02d}.json').read_text()) for n in range(2,9)}
        cls.before={pid:json.loads((ROOT/f'content/{pid}-before-remaining-companion.json').read_text()) for pid in cls.papers}

    def test_sources_ids_and_reference_material_retained(self):
        for pid,p in self.papers.items():
            with self.subTest(paper=pid):
                old=self.before[pid];current={s['id']:s for s in p['segments']}
                baseline=ROOT/f'content/{pid}-before-remaining-companion.json'
                self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),p['remainingPaperProcessing']['beforeDataSha256'])
                self.assertEqual(p['sourceSha256'],old['sourceSha256']);self.assertEqual(p['references'],old['references'])
                self.assertEqual(p['citations'][:len(old['citations'])],old['citations'])
                provenance={s['id']:s for r in p['readingUnitRepairs'] if r['revision']==REVISION for s in r['previousSegments']}
                for s in old['segments']:
                    self.assertIn(s['id'],current)
                    if current[s['id']]['sourceText']!=s['sourceText'] or current[s['id']]['fragments']!=s['fragments']:
                        self.assertEqual(provenance[s['id']]['sourceText'],s['sourceText'])
                        self.assertEqual(provenance[s['id']]['fragments'],s['fragments'])
                self.assertEqual(p['publicationStatus'],'draft')

    def test_every_dataset_and_companion_are_valid(self):
        total=0;library=json.loads((ROOT/'public/data/manifest.json').read_text())
        for pid,p in self.papers.items():
            with self.subTest(paper=pid):
                validate_paper(p,ROOT/'public')
                self.assertEqual(p['exhibitCompanion']['revision'],REVISION)
                self.assertEqual(len(p['exhibitCompanion']['studies']),len(p['exhibits']))
                self.assertEqual(audit(p)['errors'],0)
                self.assertFalse(any(f['category']=='table-cell-as-body' for f in audit(p)['findings']))
                self.assertTrue(all(s['translation']['faithfulZh'].strip() and s['translation']['plainZh'].strip() for s in core(p)))
                self.assertTrue(all('```' not in s['translation']['plainZh'] and '"explanation":' not in s['translation']['plainZh'] for s in core(p)))
                entry=next(e for e in library['papers'] if e['id']==pid)
                self.assertEqual(entry['bodySegmentCount'],len(core(p)));self.assertEqual(entry['segmentCount'],len(p['segments']))
                total+=len(p['exhibits'])
        self.assertEqual(total,107)

    def test_complete_300dpi_images(self):
        for pid,p in self.papers.items():
            with fitz.open(ROOT/'public'/p['pdfUrl'].lstrip('/')) as pdf:
                for e in p['exhibits']:
                    with self.subTest(exhibit=e['id']):
                        pix=fitz.Pixmap(ROOT/'public'/e['imageUrl'].lstrip('/'))
                        self.assertAlmostEqual(pix.width,(e['bbox'][2]-e['bbox'][0])*300/72,delta=2)
                        self.assertAlmostEqual(pix.height,(e['bbox'][3]-e['bbox'][1])*300/72,delta=2)
                        self.assertGreater(pix.width,500);self.assertGreater(pix.height,100)
                        if e['kind']=='figure':
                            images=pdf[e['page']-1].get_image_info()
                            self.assertTrue(any((fitz.Rect(e['bbox'])&fitz.Rect(i['bbox'])).get_area()/fitz.Rect(i['bbox']).get_area()>.99 for i in images))

    def test_old_unedited_drafts_migrate_without_discarding_records(self):
        for pid,p in self.papers.items():
            with self.subTest(paper=pid):
                migrated=reconcile_companion(self.before[pid],p)
                validate_paper(migrated,ROOT/'public')
                self.assertEqual({s['id'] for s in migrated['segments']},{s['id'] for s in p['segments']})
                self.assertEqual([s['id'] for s in core(migrated)],[s['id'] for s in core(p)])
                repair=next(r for r in p['readingUnitRepairs'] if r['revision']==REVISION and r['absorbedIds'])
                edited=copy.deepcopy(self.before[pid]);old=next(s for s in edited['segments'] if s['id']==repair['absorbedIds'][0]);old['translation']['plainZh']='保留我的手動稿'
                result=reconcile_companion(edited,p)
                self.assertIn(repair['targetId'],result['pendingReadingUnitRepairs'])
                self.assertEqual(next(s for s in result['segments'] if s['id']==old['id'])['translation']['plainZh'],'保留我的手動稿')

    def test_known_source_recoveries_and_discrepancies_are_visible(self):
        p3=self.papers['paper-03'];self.assertTrue(any(s['sourceText'].startswith('In physical education (PE)') for s in core(p3)))
        p8=self.papers['paper-08'];self.assertEqual(sum(e['kind']=='figure' for e in p8['exhibits']),11)
        self.assertTrue(any(s['sourceRecovery']['method'].startswith('Tesseract') for s in core(p8) if s.get('sourceRecovery')))
        for number,statistic in [('2','t = 2.30'),('3','t = 2.22'),('4','t = 2.11'),('5','t = 2.40')]:
            self.assertIn(statistic,p8['exhibitCompanion']['studies']['paper-08-table-'+number]['summaryZh'])
        self.assertTrue(any('9 次' in text and '7 次' in text for text in p8['exhibitCompanion']['studies']['paper-08-figure-10']['limitsZh']))
        p6=self.papers['paper-06'];self.assertEqual(sum(l['method']=='semantic' and l['confidence']=='high' for l in p6['exhibitCompanion']['links']),3)
        p5=self.papers['paper-05'];self.assertEqual(len(p5['readingQuality']['appendices']),1)
        for label in('A1–08','A2–10','A3–11','A4–07'):self.assertIn(label,p5['readingQuality']['appendices'][0]['faithfulZh'])

if __name__=='__main__':unittest.main()
