"""Verify guide completeness, citations and preservation of original content."""
from pathlib import Path
import base64
import hashlib
import json
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'content/guide-alignment'
ORDER = ['literatureInterpretationSection','glossarySection','researchGapSection','discussionSection','assignmentSection','readerQuestionsSection','mapSection','easyReadSection']
audit = json.loads((ROOT / 'content/guide-version-audit.json').read_text())
homepage = (ROOT.parent / '論文互動導讀首頁.html')
embedded = json.loads(re.search(r'const papers\s*=\s*(\[.*?\]);',homepage.read_text(),re.S).group(1)) if homepage.exists() else None

for number in range(2,9):
    pid = f'paper-{number:02d}'
    text = (ROOT / f'public/guides/{pid}.html').read_text()
    original = (CONTENT / f'originals/{pid}.html').read_text()
    data = json.loads((CONTENT / f'{pid}.json').read_text())
    paper = json.loads((ROOT / f'public/data/{pid}.json').read_text())
    soup = BeautifulSoup(text, 'html.parser')
    ids = [t['id'] for t in soup.select('[id]')]
    assert len(ids) == len(set(ids)), pid
    assert [t.get('id') for t in soup.select('main > section')] == ORDER, pid
    assert len(soup.select('.assignment-card')) == 8, pid
    assert len(soup.select('.reader-question-card')) == 6, pid
    assert not soup.select('.assignment-card[open],.reader-question-card[open]'), pid
    for card in soup.select('.assignment-card,.reader-question-card'):
        assert card.select_one('.page-ref'), pid
        assert len(card.get_text()) > 130, pid
    for name in ('mermaidSource','nodeDetails','statistics','glossary','discussions','easyRead'):
        pattern = rf'const {name}\s*=\s*(.*?);\n'
        assert json.loads(re.search(pattern,text).group(1)) == json.loads(re.search(pattern,original).group(1)), (pid,name)
    assert 'discussions.slice(0,4).forEach' in text, pid
    critique = json.loads(re.search(r'const discussions\s*=\s*(.*?);\n',original).group(1))[4]
    reflection = soup.select('.assignment-card')[-1].get_text()
    for block in critique['blocks']:
        for value in ([block['text']] if 'text' in block else block.get('items',[])):
            assert value in reflection, (pid, value)
    source_hash = hashlib.sha256((ROOT / f'public/papers/{pid}.pdf').read_bytes()).hexdigest()
    assert data['sourceSha256'] == paper['sourceSha256'] == source_hash, pid
    segments = {s['id']:s for s in paper['segments']}
    for gap in data['gaps']:
        assert gap['sourceEnglish'] == segments[gap['sourceSegmentId']]['sourceText'], pid
        assert hashlib.sha256(gap['sourceEnglish'].encode()).hexdigest() == gap['sourceTextSha256'], pid
    page_lists = [data[k] for k in data if k.endswith('Pages') and isinstance(data[k],list)]
    page_lists += [x['pages'] for x in data['gaps']+data['questions']]
    assert all(values and all(isinstance(p,int) and 1 <= p <= paper['pageCount'] for p in values) for values in page_lists), pid
    assert len(data['extensions']) == 3 and len(data['questions']) == 6, pid
    record = next(r for r in audit['papers'] if r['id'] == pid)
    assert record['sha256'] == hashlib.sha256(text.encode()).hexdigest(), pid
    standalone = ROOT.parent / record['sourceFile']
    if standalone.exists():
        assert standalone.read_text() == text, pid
    if embedded:
        assert base64.b64decode(embedded[number-1]['html']).decode() == text, pid
    print(f'{pid}: eight answers, six questions, four core discussions; source evidence and original tools preserved.')

assert len({json.loads((CONTENT/f'paper-{n:02d}.json').read_text())['reflection'] for n in range(2,9)}) == 7
print('Seven guides passed.')
