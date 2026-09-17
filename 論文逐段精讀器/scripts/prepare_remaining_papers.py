#!/usr/bin/env python3
"""Build a PDF-bound inspection plan; never modifies the reader datasets."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path
import fitz
from extract_phase_a import normalize_text
from build_references import atomic_json

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / 'content/remaining-papers-source-plan.json'
# Rectangles were checked against the supplied PDF pages, including table notes.
# The table's page comes from the existing source-bound exhibit identity.
TABLES = {
    2: [(305,28,552,546),(43,28,552,113),(43,127,552,211),(43,28,552,102),(43,114,294,210),(43,28,552,113),(43,117,552,387),(43,398,552,668),(43,525,294,734)],
    3: [(49,49,392,215),(49,231,392,294),(49,49,392,94),(49,111,392,218),(49,229,392,337)],
    4: [(58,50,438,216),(58,446,438,643),(58,50,438,320)],
    5: [(54,592,490,690),(37,609,510,690),(37,48,510,166),(37,301,510,691),(37,609,510,690),(37,48,510,123),(37,609,510,690),(37,48,510,199)],
    6: [(70,632,527,737),(70,623,527,737),(70,660,527,740),(70,50,527,239),(70,588,527,740),(70,408,527,530),(70,544,527,675),(70,50,527,181)],
    7: [(43,28,553,431),(43,463,553,734),(43,558,553,641),(43,652,553,734),(43,28,553,248),(43,258,294,411),(43,90,294,185),(43,477,553,561),(43,575,553,735)],
    8: [(304,28,553,306),(304,328,553,421),(43,640,294,734),(304,536,553,628),(304,652,553,734),(43,28,553,198),(43,214,553,383),(43,346,553,712)],
}
# PDF page, image index on that page, complete caption extent.
FIGURES = {
    2: [(5,0,(43,269,292,285)),(5,1,(43,507,293,524)),(5,2,(304,474,553,490)),(6,2,(43,200,294,227)),(6,0,(43,429,294,456)),(6,1,(304,221,553,248)),(7,0,(304,720,553,737)),(11,0,(43,311,294,328)),(11,1,(43,551,294,567)),(11,2,(43,720,553,737)),(12,0,(43,356,553,373)),(12,1,(43,529,553,546)),(12,2,(43,720,553,737))],
    3: [(7,0,(49,596,392,612)),(8,0,(49,596,392,612)),(9,0,(49,219,392,235)),(10,0,(49,49,148,75)),(10,1,(49,592,392,609)),(11,0,(49,460,151,481)),(12,0,(49,592,392,609)),(16,0,(49,146,392,171))],
    4: [(6,0,(58,244,438,259)),(7,0,(58,244,438,259))],
    5: [(4,0,(207,676,338,693)),(5,0,(123,676,422,693)),(6,0,(137,676,407,693)),(7,0,(152,676,392,693)),(8,0,(218,301,327,319))],
    6: [(7,0,(70,236,527,251)),(7,1,(70,727,527,742)),(8,0,(70,727,527,742)),(10,0,(70,468,527,483)),(10,1,(70,727,527,742)),(11,0,(70,244,527,259)),(13,0,(70,338,527,353)),(13,1,(70,727,527,742)),(14,0,(70,378,527,393))],
    7: [(4,0,(43,720,553,737)),(5,0,(43,720,553,737)),(6,0,(43,720,553,737)),(8,0,(43,260,553,277)),(8,1,(43,584,553,602)),(9,0,(304,720,553,737)),(13,0,(43,293,553,311)),(13,1,(43,521,553,539)),(14,0,(43,444,294,462))],
    8: [(4,0,(304,698,553,725)),(5,0,(43,445,553,462)),(5,1,(43,720,553,737)),(6,0,(43,200,553,217)),(7,0,(43,401,553,419)),(7,1,(43,720,553,737)),(8,0,(43,229,553,246)),(11,0,(43,498,553,517)),(11,1,(43,633,553,652)),(12,0,(43,240,553,257)),(12,1,(43,495,553,512))],
}
CAPTIONS_08 = [
 'Self-explanation-guided virtual museum learning model.',
 'Contextual learning in the virtual museum.', 'Structured guiding questions.',
 'Self-explanation task.', 'Collaborative concept mapping.',
 'Structure of the SE-VML system.', 'Experimental procedure.',
 'The behavioural transition diagram of the experimental group.',
 'The behavioural transition diagram of the control group.',
 'The interview results of the experimental group.', 'The interview results of the control group.',
]
CUTOFF = {2:(15,306,575),3:(19,49,87),4:(16,58,273),5:(17,37,623),6:(18,70,508),7:(16,306,533),8:(18,304,678)}

def rectangle_union(*boxes):
    rect = fitz.Rect(boxes[0])
    for box in boxes[1:]: rect |= fitz.Rect(box)
    return list(rect)

def main():
    if PLAN.exists():
        raise ValueError('Inspection plan exists; preserve its curated annotations.')
    output = {'revision':'remaining-papers-companion-v1','papers':{}}
    for n in range(2,9):
        pid=f'paper-{n:02d}'
        path=ROOT/f'public/data/{pid}.json'; original_bytes=path.read_bytes(); p=json.loads(original_bytes)
        with fitz.open(ROOT/f'public/papers/{pid}.pdf') as pdf:
            sha=hashlib.sha256((ROOT/f'public/papers/{pid}.pdf').read_bytes()).hexdigest()
            if sha != p['sourceSha256']: raise ValueError('PDF hash mismatch: '+pid)
            item={'sourceSha256':sha,'beforeDataSha256':hashlib.sha256(original_bytes).hexdigest(),'layout':'two-column' if n in(2,7,8) else 'single-column','exhibits':{},'merges':[],'replacements':[],'additions':[],'explanations':{},'semanticLinks':[],'roles':{},'exclusions':{},'appendices':[]}
            for j,box in enumerate(TABLES[n],1):
                e=next(e for e in p['exhibits'] if e['kind']=='table' and e['number']==str(j))
                updated=copy.deepcopy(e); updated['bbox']=list(box)
                # Use only the caption region, not accidental data appended to it.
                region=fitz.Rect(box);region.y1=min(region.y0+29,region.y1)
                updated['caption']=normalize_text(pdf[e['page']-1].get_textbox(region))
                item['exhibits'][e['id']]=updated
            for j,(page,index,captionbox) in enumerate(FIGURES[n],1):
                images=pdf[page-1].get_image_info(); imagebox=fitz.Rect(images[index]['bbox']); imagebox+=(-2,-2,2,2)
                eid=f'{pid}-figure-{j}'; existing=next((e for e in p['exhibits'] if e['id']==eid),None)
                e=copy.deepcopy(existing) if existing else {'id':eid,'label':f'Figure {j}','kind':'figure','number':str(j),'captionZh':'','captionSegmentId':None,'explanationSegmentIds':[]}
                e.update(page=page,bbox=rectangle_union(imagebox,captionbox),pageSize=[pdf[page-1].rect.width,pdf[page-1].rect.height])
                if n==8: e['caption']=f'FIGURE {j} | '+CAPTIONS_08[j-1]
                item['exhibits'][eid]=e
            output['papers'][pid]=item
    atomic_json(PLAN,output)
    print(json.dumps({'plan':str(PLAN),'exhibits':sum(len(p['exhibits']) for p in output['papers'].values())}))

if __name__=='__main__': main()
