#!/usr/bin/env python3
"""Recover inspected gaps from local PDF crops without altering the supplied PDF."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import fitz
from build_references import atomic_json
from extract_phase_a import normalize_text

ROOT = Path(__file__).resolve().parent.parent
REGIONS = {
    4: [(304,283,553,499)],
    5: [(43,213,294,251),(304,28,553,236)],
    6: [(43,237,294,564),(304,386,553,599)],
    8: [(304,630,553,737)],
    9: [(304,638,553,737),(43,455,294,601)],
    10: [(43,120,294,254),(43,339,294,472),(43,558,294,635),(304,28,553,97),(304,119,553,230),(304,361,553,528)],
    11: [(304,662,553,737)],
    12: [(304,535,553,736)],
    13: [(43,154,294,244),(43,265,294,338),(304,28,553,59),(304,178,553,338)],
    14: [(43,143,294,321),(43,489,294,641),(304,142,553,398)],
}

def main():
    executable = shutil.which('tesseract')
    if not executable:
        raise RuntimeError('Tesseract with the English language pack is required.')
    output = ROOT/'content/paper-08-recovered-text.json'
    if output.exists():
        print('Preserving existing OCR evidence: '+str(output))
        return
    source = ROOT/'public/papers/paper-08.pdf'
    result = {'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'engine':'Tesseract eng, 300 dpi, psm 3', 'regions':[]}
    with fitz.open(source) as pdf, tempfile.TemporaryDirectory(prefix='paper08-ocr-') as temporary:
        for page, boxes in REGIONS.items():
            for index, box in enumerate(boxes):
                crop = Path(temporary)/f'p{page}-{index}.png'
                pdf[page-1].get_pixmap(clip=fitz.Rect(box),dpi=300,alpha=False).save(crop)
                text = subprocess.run([executable,str(crop),'stdout','-l','eng','--psm','3'],check=True,capture_output=True,text=True).stdout
                blocks = [normalize_text(t) for t in text.split('\n\n') if normalize_text(t)]
                result['regions'].append({'page':page,'bbox':list(box),'pageSize':list(pdf[page-1].rect)[2:], 'rawText':text,'paragraphs':blocks})
    atomic_json(output,result)
    for index,r in enumerate(result['regions']):
        print(index, 'PDF',r['page'],r['bbox'], '\n'+'\n'.join(r['paragraphs'])+'\n')

if __name__=='__main__':
    main()
