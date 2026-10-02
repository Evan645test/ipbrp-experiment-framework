#!/usr/bin/env python3
"""Restore paper 3 section names using source-guarded PDF heading evidence."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'content/paper-03-section-repairs.json'


def apply_section_repairs(paper):
    if paper['id'] != 'paper-03':
        return paper
    plan = json.loads(PLAN.read_text())
    if paper['sourceSha256'] != plan['sourceSha256']:
        raise ValueError('Section repair belongs to a different PDF.')
    result = copy.deepcopy(paper)
    segments = {s['id']: s for s in result['segments']}
    for repair in plan['repairs']:
        segment = segments[repair['segmentId']]
        if segment['sourceText'] != repair['sourceText'] or hashlib.sha256(segment['sourceText'].encode()).hexdigest() != repair['sourceTextSha256']:
            raise ValueError('Section repair source changed: ' + segment['id'])
        if segment['section'] not in (repair['previousSection'], repair['section']):
            raise ValueError('Preserving an independently edited section: ' + segment['id'])
        if segment['section'] != repair['section'] and (segment['reviewStatus'] in ('reviewed', 'published') or segment['translation']['status'] == 'reviewed'):
            raise ValueError('Preserving a human-reviewed record: ' + segment['id'])
        segment['section'] = repair['section']
    result['sectionRepairs'] = plan['repairs']
    return result


if __name__ == '__main__':
    path = ROOT / 'public/data/paper-03.json'
    paper = json.loads(path.read_text())
    pdf = ROOT / 'public' / paper['pdfUrl'].lstrip('/')
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != paper['sourceSha256']:
        raise ValueError('Original PDF hash changed.')
    result = apply_section_repairs(paper)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f"Corrected {len(result['sectionRepairs'])} section labels; paragraph content and IDs preserved.")
