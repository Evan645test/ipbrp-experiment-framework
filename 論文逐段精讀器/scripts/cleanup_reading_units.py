#!/usr/bin/env python3
"""Reversibly exclude source-backed labels from standalone reading steps."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import fitz

TOKENS = re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*|\d+(?:\.\d+)*")
TABLE_TITLE = re.compile(r"^Table\s+\d+[a-z]?\b[\s.|:–—-]*(.*)$", re.I)
BODY_VERB = re.compile(r"^(?:shows?|showed|presents?|presented|reports?|reported|indicates?|indicated|summari[sz]es?|compares?|illustrates?|lists?|demonstrates?|reveals?|provides?|displays?|is|was|were|has|contains?)\b", re.I)
NUMBER = r"[+\-−]?(?:\d+(?:\.\d+)?|\.\d+)"
STAT_NOTE = re.compile(rf"\s*\*{{1,3}}\s*[pPzZ]\s*[<=>≤≥]\s*{NUMBER}(?:\s*[,;.]\s*\*{{1,3}}\s*[pPzZ]\s*[<=>≤≥]\s*{NUMBER})*\s*\.?\s*")
KNOWN_HEADINGS = {
    "summary", "practitioner notes", "declarations", "funding", "orcid",
    "acknowledgment", "acknowledgments", "acknowledgement", "acknowledgements",
    "author contributions", "author contribution", "credit authorship contribution statement",
    "ethics approval", "ethics statement", "ethical statement", "informed consent",
    "ethics approval and informed consent", "consent", "competing interests",
    "conflicts of interest", "declaration of competing interest", "disclosure statement",
    "data availability", "data availability statement", "availability of data and material",
    "notes on contributors", "ai statement", "peer review", "appendix i", "appendix ii",
    "what is already known about this topic", "what is currently known about this topic",
    "what this paper adds", "what does this paper add",
    "implications for practice and/or policy", "implications for practise and/or policy",
}
TABLE_HEADER_WORDS = set('code behavior behaviour behaviors behaviours description phase group groups mean sd se f p n t d given target fixed effect ci time point adjusted std error dimensions rank post hoc u test model fit marginal conditional metric min max rubrics'.split())


def word_count(text: str) -> int:
    return len(TOKENS.findall(text))


def overlap_fraction(box: list[float], region: list[float]) -> float:
    area = (box[2] - box[0]) * (box[3] - box[1])
    if area <= 0:
        return 0.0
    intersection = max(0.0, min(box[2], region[2]) - max(box[0], region[0])) * max(0.0, min(box[3], region[3]) - max(box[1], region[1]))
    return intersection / area


def typography(segment: dict, page_spans: dict[int, list[dict]]) -> dict:
    total = bold = 0
    for fragment in segment['fragments']:
        x0, y0, x1, y1 = fragment['bbox']
        for span in page_spans[fragment['page']]:
            sx0, sy0, sx1, sy1 = span['bbox']
            if x0 - .05 <= (sx0 + sx1) / 2 <= x1 + .05 and y0 - .05 <= (sy0 + sy1) / 2 <= y1 + .05:
                weight = len(re.sub(r'\s', '', span['text']))
                total += weight
                if span['flags'] & 16 or 'bold' in span['font'].lower():
                    bold += weight
    return {'matchedCharacters': total, 'boldFraction': round(bold / total, 4) if total else 0.0}


def classify(segment: dict, typography_evidence: dict, table_regions: list[dict], cited: bool = False) -> str | None:
    text = segment['sourceText'].strip()
    count = word_count(text)
    if cited or segment.get('reviewStatus') in {'reviewed', 'published'}:
        return None
    # Figure captions remain entry points in this limited first cleanup.
    if re.match(r'^Fig(?:ure)?\.?\s*\d+', text, re.I):
        return None
    title = TABLE_TITLE.match(text)
    if title:
        suffix = title.group(1)
        if count <= 40 and not BODY_VERB.match(suffix) and len(re.findall(NUMBER, suffix)) <= 1 and not re.search(r'\bGiven\s*:', suffix, re.I):
            return 'table-title'
        return None
    if count > 10:
        return None
    label = re.sub(r'^[•○]\s*', '', text).rstrip(':').casefold()
    if label in KNOWN_HEADINGS:
        return 'section-heading'
    if STAT_NOTE.fullmatch(text):
        return 'statistical-table-note'
    is_table_fragment = all(any(
        fragment['page'] == region['page']
        and overlap_fraction(fragment['bbox'], region['bbox']) >= .92
        for region in table_regions
    ) for fragment in segment['fragments'])
    letters = [word.casefold() for word in re.findall(r'[A-Za-z]+', text)]
    if is_table_fragment and letters and all(word in TABLE_HEADER_WORDS for word in letters):
        return 'table-header'
    if is_table_fragment and re.match(r'^Model\s+(?:equation|fit)\b', text, re.I):
        return 'table-model-label'
    # Numeric fragments require both a table location and an array-like shape.
    if is_table_fragment and len(re.findall(NUMBER, text)) >= 2 and len(re.findall(r'[A-Za-z]+', text)) <= 3:
        return 'numeric-table-fragment'
    # Bold short labels are supported by the original PDF typography, not length alone.
    if typography_evidence['matchedCharacters'] and typography_evidence['boldFraction'] >= .9:
        if not is_table_fragment and re.search(r'[=<>≤≥±~]', text):
            return None
        if not re.match(r'^(?:[•○]|\(\d+\)|\d+\.\s)', text) and not re.search(r'[.!?。！？]\s*$', text):
            return 'table-header' if is_table_fragment and len(letters) <= 3 else 'short-bold-label'
    return None


def atomic_json(path: Path, value: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restore(project: Path, journal: dict) -> int:
    updates = []
    restored = 0
    for paper_id, record in journal['papers'].items():
        path = project / 'public/data' / f'{paper_id}.json'
        paper = json.loads(path.read_text(encoding='utf-8'))
        if paper['sourceSha256'] != record['sourceSha256']:
            raise ValueError(f'{paper_id}: cannot restore a different PDF source')
        by_id = {segment['id']: segment for segment in paper['segments']}
        for segment_id, saved in record['segments'].items():
            segment = by_id[segment_id]
            if hashlib.sha256(segment['sourceText'].encode('utf-8')).hexdigest() != saved['sourceTextSha256']:
                raise ValueError(f'{segment_id}: cannot restore changed source text')
            if segment.get('excluded') is True:
                if saved['hadExcludedField']:
                    segment['excluded'] = saved['previousExcluded']
                else:
                    segment.pop('excluded', None)
                restored += 1
        updates.append((path, paper))
    for path, paper in updates:
        atomic_json(path, paper)
    update_manifest(project, [paper for _, paper in updates])
    print(json.dumps({'restored': restored}, ensure_ascii=False))
    return 0


def update_manifest(project: Path, papers: list[dict]) -> None:
    path = project / 'public/data/manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    by_id = {paper['id']: paper for paper in papers}
    for summary in manifest['papers']:
        if summary['id'] in by_id:
            summary['includedSegmentCount'] = sum(not segment.get('excluded') for segment in by_id[summary['id']]['segments'])
    atomic_json(path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Apply exclusions; otherwise only write the audit.')
    mode.add_argument('--restore', action='store_true', help='Restore inclusion flags changed by this source-bound cleanup.')
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    journal_path = project / 'content/reading-unit-cleanup.json'
    previous = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {'schemaVersion': '1.0.0', 'papers': {}}
    if previous.get('schemaVersion') != '1.0.0' or not isinstance(previous.get('papers'), dict):
        raise ValueError('Unsupported cleanup journal')
    if args.restore:
        return restore(project, previous)
    audit = {'schemaVersion': '1.0.0', 'generatedAt': datetime.now(timezone.utc).isoformat(), 'applied': args.apply, 'thresholdWords': 10, 'papers': {}}
    updates = []
    journal = {'schemaVersion': '1.0.0', 'papers': dict(previous['papers'])}
    for path in sorted((project / 'public/data').glob('paper-??.json')):
        paper = json.loads(path.read_text(encoding='utf-8'))
        pdf_path = project / 'public' / paper['pdfUrl'].lstrip('/')
        if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != paper['sourceSha256']:
            raise ValueError(f"{paper['id']}: PDF source hash mismatch")
        prior = previous['papers'].get(paper['id'], {})
        if prior and prior['sourceSha256'] != paper['sourceSha256']:
            raise ValueError(f"{paper['id']}: cleanup journal source mismatch")
        with fitz.open(pdf_path) as pdf:
            spans = {index + 1: [span for block in page.get_text('dict')['blocks'] for line in block.get('lines', []) for span in line['spans']] for index, page in enumerate(pdf)}
        regions = [entry for entry in paper.get('exhibits', []) if entry['kind'] == 'table' and entry['bbox'][3] - entry['bbox'][1] > 30]
        cited_ids = {entry['segmentId'] for entry in paper.get('citations', [])}
        exclusions = dict(prior.get('segments', {}))
        if not set(exclusions).issubset({segment['id'] for segment in paper['segments']}):
            raise ValueError(f"{paper['id']}: cleanup journal contains unknown segment IDs")
        candidates = []
        remaining_short = []
        for segment in paper['segments']:
            proof = typography(segment, spans)
            reason = classify(segment, proof, regions, segment['id'] in cited_ids)
            saved = exclusions.get(segment['id'])
            text_hash = hashlib.sha256(segment['sourceText'].encode('utf-8')).hexdigest()
            if saved and saved['sourceTextSha256'] != text_hash:
                raise ValueError(f"{segment['id']}: cleanup source text changed")
            # Existing manual exclusions are never attributed to this cleanup.
            if reason and (not segment.get('excluded') or saved):
                if not saved:
                    saved = {'sourceTextSha256': text_hash, 'previousExcluded': segment.get('excluded'), 'hadExcludedField': 'excluded' in segment, 'reason': reason}
                    exclusions[segment['id']] = saved
                candidates.append({'id': segment['id'], 'order': segment['order'], 'pages': [entry['page'] for entry in segment['fragments']], 'sourceText': segment['sourceText'], 'words': word_count(segment['sourceText']), 'reason': reason, 'typography': proof})
                if args.apply:
                    segment['excluded'] = True
            elif saved and args.apply:
                # Reapplying the same source-bound journal survives upstream data rebuilds.
                segment['excluded'] = True
            elif not segment.get('excluded') and word_count(segment['sourceText']) <= 10:
                remaining_short.append({'id': segment['id'], 'order': segment['order'], 'sourceText': segment['sourceText'], 'words': word_count(segment['sourceText']), 'action': 'preserved-review-only'})
        if not any(not entry.get('excluded') for entry in paper['segments']):
            raise ValueError(f"{paper['id']}: cleanup would exclude all reading steps")
        journal['papers'][paper['id']] = {'sourceSha256': paper['sourceSha256'], 'segments': exclusions}
        audit['papers'][paper['id']] = {'excludedCandidates': candidates, 'preservedShortUnits': remaining_short, 'reasons': dict(Counter(entry['reason'] for entry in candidates)), 'includedAfter': sum(not entry.get('excluded') for entry in paper['segments'])}
        updates.append((path, paper))
    # Validate the entire batch before committing any source-bound checkpoint.
    if args.apply:
        atomic_json(journal_path, journal)
        for path, paper in updates:
            atomic_json(path, paper)
        update_manifest(project, [paper for _, paper in updates])
    atomic_json(project / 'content/reading-unit-cleanup-audit.json', audit)
    print(json.dumps({'applied': args.apply, 'papers': {key: {'candidates': len(value['excludedCandidates']), 'reasons': value['reasons'], 'includedAfter': value['includedAfter']} for key, value in audit['papers'].items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f'error: {error}', file=sys.stderr)
        raise SystemExit(1)
