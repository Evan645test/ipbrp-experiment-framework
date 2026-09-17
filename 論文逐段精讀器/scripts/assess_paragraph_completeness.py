#!/usr/bin/env python3
"""Flag incomplete reading fragments without discarding source text or notes."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import fitz
from cleanup_reading_units import atomic_json, word_count


def contains_word(fragment: dict, page: int, word: tuple) -> bool:
    if fragment['page'] != page:
        return False
    x0, y0, x1, y1 = fragment['bbox']
    return x0 - .1 <= (word[0] + word[2]) / 2 <= x1 + .1 and y0 - .1 <= (word[1] + word[3]) / 2 <= y1 + .1


def assess(paper: dict, page_words: dict[int, list[tuple]]) -> tuple[dict, list[dict]]:
    segments = [entry for entry in paper['segments'] if entry['kind'] == 'body' and not entry.get('excluded') and entry.get('reviewStatus') not in {'reviewed', 'published'}]
    evidence = []
    issues: dict[str, dict] = {}

    def flag(entry: dict, status: str, reason: str, related: list[str]) -> None:
        record = issues.setdefault(entry['id'], {'status': status, 'reasons': [], 'relatedSegmentIds': [], 'sourceTextSha256': hashlib.sha256(entry['sourceText'].encode('utf-8')).hexdigest()})
        if status == 'fragment':
            record['status'] = status
        if reason not in record['reasons']:
            record['reasons'].append(reason)
        record['relatedSegmentIds'] = sorted(set(record['relatedSegmentIds'] + [value for value in related if value != entry['id']]))

    for page, words in page_words.items():
        if not any(fragment['page'] == page for entry in segments for fragment in entry['fragments']):
            continue
        for word in words:
            prefix = re.fullmatch(r'([A-Za-z]{2,})\u00ad', word[4])
            if not prefix:
                continue
            line_start = min(other[0] for other in words if other[5:7] == word[5:7])
            # A soft hyphen is source evidence of a line-wrapped word, not a real dash.
            candidates = [other for other in words if re.fullmatch(r'[A-Za-z]+[,.;:!?]?', other[4])
                          and 1 < other[1] - word[1] < max(25, (word[3] - word[1]) * 2)
                          and line_start - 15 <= other[0] <= line_start + min(40, paper_width(paper, page) * .1)]
            if not candidates:
                continue
            first_y = min(other[1] for other in candidates)
            next_line = [other for other in candidates if abs(other[1] - first_y) < 1]
            continuation = min(next_line, key=lambda other: other[0])
            suffix = re.sub(r'[,.;:!?]$', '', continuation[4])
            left = [entry for entry in segments if re.search(r'\b' + re.escape(prefix.group(1)) + r'$', entry['sourceText'].strip(), re.I)
                    and any(contains_word(fragment, page, word) for fragment in entry['fragments'])]
            right = [entry for entry in segments if re.match(re.escape(suffix) + r'\b', entry['sourceText'].lstrip(), re.I)
                     and any(contains_word(fragment, page, continuation) for fragment in entry['fragments'])]
            linked = sorted({entry['id'] for entry in left + right})
            # Do not flag normal wrapping already reconstructed within one segment.
            if not linked or any(entry['id'] in {value['id'] for value in right} for entry in left):
                continue
            for entry in left + right:
                flag(entry, 'fragment', '原 PDF 的同一個單字被切到不同閱讀單位，無法作為完整段落獨立解釋。', linked)
            evidence.append({'page': page, 'word': prefix.group(1) + suffix, 'parts': [prefix.group(1), suffix], 'segmentIds': linked, 'wordBoxes': [list(word[:4]), list(continuation[:4])]})

    for entry in segments:
        text = entry['sourceText'].strip()
        if not re.match(r'^(?:\(\d+\)|\d+\.)\s*(?:Does|Do|Is|Are|Can|What|How|Which)\b', text) or '?' in text:
            continue
        last_token = re.search(r'[A-Za-z]+$', text)
        if not last_token:
            continue
        fragment = entry['fragments'][-1]
        page = fragment['page']; words = page_words.get(page, [])
        ends = [word for word in words if word[4] == last_token.group() and contains_word(fragment, page, word)]
        if not ends:
            continue
        end = max(ends, key=lambda word: (word[1], word[0]))
        line_start = min(word[0] for word in words if word[5:7] == end[5:7])
        candidates = [word for word in words if 1 < word[1] - end[1] < max(25, (end[3] - end[1]) * 2) and line_start - 15 <= word[0] <= line_start + min(40, paper_width(paper, page) * .1)]
        if not candidates:
            continue
        first_y = min(word[1] for word in candidates)
        start = min((word for word in candidates if abs(word[1] - first_y) < 1), key=lambda word: word[0])
        if not re.match(r'^[a-z]', start[4]):
            continue
        peers = [peer for peer in segments if peer['id'] != entry['id'] and peer['sourceText'].lstrip().startswith(start[4]) and any(contains_word(part, page, start) for part in peer['fragments'])]
        if peers:
            linked = [entry['id']] + [peer['id'] for peer in peers]
            for peer in [entry] + peers:
                flag(peer, 'fragment', '編號研究問題尚未結束，原 PDF 的下一行被拆到另一個閱讀單位，需恢復完整問題。', linked)
            evidence.append({'page': page, 'kind': 'unfinished-numbered-question', 'segmentIds': linked, 'wordBoxes': [list(end[:4]), list(start[:4])]})

    for entry in segments:
        text = entry['sourceText'].strip()
        if entry['id'] in issues:
            continue
        # This is a review cue, NOT a semantic verdict. Original author paragraphs
        # may legitimately depend on preceding context or be concise list items.
        if word_count(text) <= 20 and re.match(r'^[a-z]', text):
            flag(entry, 'needs-review', '短文字以小寫起始，可能是前句延續；需核對原 PDF，不因字數或語感直接刪除。', [])
    return issues, evidence


def paper_width(paper: dict, page: int) -> float:
    for entry in paper['segments']:
        for fragment in entry['fragments']:
            if fragment['page'] == page:
                return fragment['pageSize'][0]
    raise ValueError(f'No page geometry for page {page}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    audit = {'schemaVersion': '1.0.0', 'generatedAt': datetime.now(timezone.utc).isoformat(), 'applied': args.apply, 'method': 'PDF soft-hyphen and coordinate evidence; review cues are not semantic judgments', 'papers': {}}
    updates = []
    for path in sorted((project / 'public/data').glob('paper-??.json')):
        paper = json.loads(path.read_text(encoding='utf-8'))
        pdf_path = project / 'public' / paper['pdfUrl'].lstrip('/')
        if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != paper['sourceSha256']:
            raise ValueError(f"{paper['id']}: PDF hash mismatch")
        with fitz.open(pdf_path) as pdf:
            page_words = {index + 1: page.get_text('words') for index, page in enumerate(pdf)}
        issues, evidence = assess(paper, page_words)
        if args.apply:
            for entry in paper['segments']:
                if entry['id'] in issues:
                    entry['paragraphAssessment'] = issues[entry['id']]
                else:
                    entry.pop('paragraphAssessment', None)
        audit['papers'][paper['id']] = {'sourceSha256': paper['sourceSha256'], 'counts': dict(Counter(record['status'] for record in issues.values())), 'units': issues, 'evidence': evidence}
        updates.append((path, paper))
    if args.apply:
        for path, paper in updates:
            atomic_json(path, paper)
    atomic_json(project / 'content/paragraph-completeness-audit.json', audit)
    print(json.dumps({paper_id: record['counts'] for paper_id, record in audit['papers'].items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f'error: {error}', file=sys.stderr)
        raise SystemExit(1)
