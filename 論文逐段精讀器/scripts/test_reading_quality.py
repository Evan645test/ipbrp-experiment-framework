#!/usr/bin/env python3
import copy
import hashlib
import json
import unittest
import fitz
from audit_reading_quality import ROOT, audit, core_segments
from repair_paper01_reading_quality import repair, ANCHOR, ABSORBED, REVISION
from companion_metadata import reconcile_companion
from validate_phase_a import validate_paper

class ReadingQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paper=json.loads((ROOT/'public/data/paper-01.json').read_text())
        cls.before=json.loads((ROOT/'content/paper-01-before-reading-quality.json').read_text())['paper']

    def test_order_roles_and_archives(self):
        p=self.paper; original={s['id']:s for s in self.before['segments']}; current={s['id']:s for s in p['segments']}
        self.assertEqual(list(original),list(current))
        self.assertEqual(len(core_segments(p)),66)
        self.assertEqual(sum(s.get('readingRole')=='statement' for s in p['segments']),6)
        self.assertEqual(sum(s.get('readingRole')=='appendix' for s in p['segments']),2)
        target=current[ANCHOR]
        self.assertEqual(target['sourceText'],' '.join(original[i]['sourceText'] for i in [ANCHOR,*ABSORBED]))
        self.assertEqual([f['page'] for f in target['fragments']],[17,18])
        for n in range(1,6):
            self.assertIn(f'（{n}）',target['translation']['faithfulZh'])
        for i in ABSORBED:
            self.assertTrue(current[i]['excluded'])
            self.assertEqual(current[i]['mergedIntoSegmentId'],ANCHOR)
            for key in ('sourceText','fragments','translation'):
                self.assertEqual(current[i][key],original[i][key])
        for key in ('references','citations','readingOrderRepair','exhibits'):
            self.assertEqual(p[key],self.before[key])
        allowed={r['segmentId'] for r in p['readingQuality']['explanationRepairs']}|{ANCHOR}
        for sid,old in original.items():
            if sid!=ANCHOR:
                self.assertEqual(old['sourceText'],current[sid]['sourceText'])
                self.assertEqual(old['fragments'],current[sid]['fragments'])
            if sid not in allowed:
                self.assertEqual(old['translation'],current[sid]['translation'])

    def test_complete_appendices_and_interpretation_limits(self):
        with fitz.open(ROOT/'public/papers/paper-01.pdf') as pdf:
            for a in self.paper['readingQuality']['appendices']:
                e=a['exhibit']; text=pdf[e['page']-1].get_textbox(fitz.Rect(e['bbox']))
                self.assertIn('Appendix '+e['number'],text)
                self.assertNotIn('Y. Chen et al.',text)
                self.assertNotIn('Data availability',text)
                pix=fitz.Pixmap(ROOT/'public'/e['imageUrl'].lstrip('/'))
                self.assertGreater(pix.width,1900)
                self.assertAlmostEqual(pix.height,(e['bbox'][3]-e['bbox'][1])*300/72,delta=2)
                if e['number']=='II':
                    for name in ('Go/No-Go','Mr. Ant','Card Sorting'):
                        self.assertIn(name,a['faithfulZh'])
                    # The native appendix table is an embedded raster, not text.
                    images=pdf[e['page']-1].get_image_info()
                    self.assertTrue(any(fitz.Rect(e['bbox']).intersects(fitz.Rect(i['bbox'])) and i['width']>500 for i in images))
                    self.assertIn('條件式',a['guideZh'][-1])

    def test_old_curator_safe_migration_and_manual_edits(self):
        migrated=reconcile_companion(self.before,self.paper)
        self.assertEqual(len(core_segments(migrated)),66)
        self.assertEqual(next(s for s in migrated['segments'] if s['id']==ANCHOR)['sourceText'],next(s for s in self.paper['segments'] if s['id']==ANCHOR)['sourceText'])
        validate_paper(migrated,ROOT/'public')
        edited=copy.deepcopy(self.before)
        next(s for s in edited['segments'] if s['id']==ABSORBED[0])['translation']['plainZh']='手動保留的內容'
        result=reconcile_companion(edited,self.paper)
        self.assertIn(ANCHOR,result['pendingReadingUnitRepairs'])
        self.assertFalse(next(s for s in result['segments'] if s['id']==ABSORBED[0]).get('excluded',False))
        self.assertEqual(next(s for s in result['segments'] if s['id']==ABSORBED[0])['translation']['plainZh'],'手動保留的內容')
        deleted=copy.deepcopy(self.paper)
        removed=deleted['readingQuality']['appendices'][0]['relatedSegmentIds'][0]
        deleted['segments']=[s for s in deleted['segments'] if s['id']!=removed]
        result=reconcile_companion(deleted,self.paper)
        self.assertFalse(any(removed in a['relatedSegmentIds'] for a in result['readingQuality']['appendices']))

    def test_audit_is_read_only_and_known_errors_cleared(self):
        paths=list((ROOT/'public/data').glob('paper-*.json'))
        hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        before=audit(self.before); after=audit(self.paper)
        self.assertTrue(any(f['category']=='list-introduction' and f['segmentId']==ANCHOR for f in before['findings']))
        self.assertGreater(before['errors'],0)
        self.assertEqual(after['errors'],0)
        baseline=ROOT/'content/paper-02-before-remaining-companion.json'
        p2=audit(json.loads((baseline if baseline.exists() else ROOT/'public/data/paper-02.json').read_text()))
        self.assertTrue(any(f['category']=='table-cell-as-body' for f in p2['findings']))
        self.assertEqual(hashes,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def test_idempotence_and_human_review_protection(self):
        self.assertEqual(repair(self.paper),self.paper)
        edited=copy.deepcopy(self.before)
        next(s for s in edited['segments'] if s['id']==ANCHOR)['translation']['status']='reviewed'
        with self.assertRaises(ValueError):
            repair(edited)
        self.assertEqual(self.paper['readingUnitRepairs'][-1]['revision'],REVISION)

if __name__=='__main__':
    unittest.main()
