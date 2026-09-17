"""Build seven evidence-grounded guides while preserving their original study tools."""
from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import html
import json
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'content/guide-alignment'
TITLES = [
    '一之1．這篇論文的主要目的（主題）是什麼？',
    '一之2．這類研究目的（主題）為什麼很重要？',
    '一之3．過去學者曾經有哪些嘗試或研究成果？',
    '二之1．過去這些研究成果還有什麼不足？',
    '二之2．本研究提出什麼策略？內容與背後教育理論是什麼？',
    '二之3．作者提出什麼研究問題？實驗如何設計、分組、測量與進行？',
    '二之4．實驗結果為何？作者提供了什麼解釋或推論？',
    '1．（1）我由這篇論文學習到什麼？（2）未來還可進行什麼延伸研究？為什麼？',
]


def esc(value):
    return html.escape(str(value), quote=True)


def para(text, cls=''):
    return f'<p class="{cls}">{esc(text)}</p>'


def pages(values):
    return 'PDF 第 ' + '、'.join(map(str, sorted(set(values)))) + ' 頁'


def blocks(items):
    result = []
    for item in items:
        kind = item['type']
        if kind in ('paragraph', 'note'):
            result.append(para(item['text'], 'alignment-note' if kind == 'note' else ''))
        elif kind == 'subheading':
            result.append(f'<h4>{esc(item["text"])}</h4>')
        elif kind in ('bullets', 'numbered'):
            tag = 'ul' if kind == 'bullets' else 'ol'
            result.append(f'<{tag}>' + ''.join(f'<li>{esc(x)}</li>' for x in item['items']) + f'</{tag}>')
        elif kind == 'table':
            result.append('<div class="alignment-table" role="region" aria-label="研究資料表" tabindex="0"><table><thead><tr>' + ''.join(f'<th scope="col">{esc(x)}</th>' for x in item['headers']) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{esc(x)}</td>' for x in row) + '</tr>' for row in item['rows']) + '</tbody></table></div>')
        else:
            raise ValueError(f'Unsupported block: {kind}')
    return ''.join(result)


def section(identifier, title, intro, body, controls=''):
    return f'<section id="{identifier}" class="section alignment-section" aria-labelledby="{identifier}Title"><div class="section-head"><div><h2 id="{identifier}Title">{title}</h2>{para(intro)}</div>{controls}</div>{body}</section>'


def controls(group, label):
    return f'<div class="alignment-controls"><button class="button" id="expand{group}" type="button" aria-label="展開全部{label}">全部展開</button><button class="button" id="collapse{group}" type="button" aria-label="收合全部{label}">全部收合</button></div>'


STYLE = '''
.topbar .brand{min-width:0;flex:1}.topbar .nav-links{min-width:0;flex-shrink:1;max-width:100%}.topbar .nav-links a,.topbar .nav-links button{flex-shrink:0}@media(max-width:760px){.topbar .brand{flex:none}.topbar .nav-links{flex:none}.topbar .nav-links a,.topbar .nav-links button{flex:none}}
.alignment-section{scroll-margin-top:110px}.zone-banner{padding:24px;border-radius:18px;background:#edf1fb;border:1px solid #cbd3eb;margin-bottom:24px;scroll-margin-top:110px}.zone-banner h2{margin:0 0 8px}.zone-banner p{margin:0;line-height:1.8}.gap-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.gap-card{padding:20px;background:#fff7f3;border:1px solid #ebc9bd;border-radius:14px}.gap-card h3{margin-top:0}.gap-card p{line-height:1.85}.alignment-controls{display:flex;gap:8px;flex-wrap:wrap}.assignment-list,.reader-question-list{display:grid;gap:14px}.assignment-card,.reader-question-card{border:1px solid #d8cfb9;border-radius:14px;overflow:hidden;background:#fffdf7;min-width:0}.reader-question-card{background:#f5fbf9;border-color:#b9d9cc}.assignment-card summary,.reader-question-card summary{display:flex;align-items:flex-start;gap:12px;padding:18px;cursor:pointer;font-weight:700;line-height:1.7;list-style:none}.assignment-card summary::after,.reader-question-card summary::after{content:'＋';margin-left:auto;flex-shrink:0}.assignment-card[open] summary::after,.reader-question-card[open] summary::after{content:'−'}.alignment-number{display:inline-grid;place-items:center;min-width:30px;height:30px;border-radius:50%;background:#eee1b7;color:#564313}.reader-question-card .alignment-number{background:#d8eee4;color:#28553f}.assignment-card-body,.reader-question-body{padding:0 22px 22px;line-height:1.9;overflow-wrap:anywhere}.assignment-card-body h4,.reader-question-body h4{margin:20px 0 8px}.assignment-compact{margin-top:18px;padding:16px;background:#f2ead7;border-radius:10px}.alignment-note{padding:14px;background:#eef0f5;border-left:4px solid #9cabc6;border-radius:6px}.alignment-boundary{padding:14px;background:#e8f2ed;border-left:4px solid #649d80;border-radius:6px}.alignment-table{max-width:100%;overflow-x:auto;margin:18px 0}.alignment-table table{border-collapse:collapse;width:100%;min-width:500px}.alignment-table th,.alignment-table td{border:1px solid #d8dce3;padding:10px;text-align:left;vertical-align:top}.alignment-table th{background:#eff1f6}.assignment-group-title{margin-top:24px}.alignment-section .page-ref{font-size:.9em;color:#657183}summary:focus-visible,.alignment-controls button:focus-visible{outline:3px solid #456dba;outline-offset:3px}@media(max-width:640px){.gap-grid{grid-template-columns:1fr}.zone-banner{padding:18px}.assignment-card summary,.reader-question-card summary{padding:15px}.assignment-card-body,.reader-question-body{padding:0 15px 18px}.alignment-section{scroll-margin-top:150px}.alignment-controls{margin-top:10px}}@media print{.alignment-controls{display:none}.assignment-card,.reader-question-card{break-inside:avoid}.assignment-card-body,.reader-question-body{display:block!important}}
'''

CONTROLLER = '''
(()=>{for(const [group,selector] of [['Assignments','.assignment-card'],['ReaderQuestions','.reader-question-card']]){for(const [action,open] of [['expand',true],['collapse',false]]){document.getElementById(action+group).addEventListener('click',()=>document.querySelectorAll(selector).forEach(card=>card.open=open));}}document.querySelectorAll('.topbar a[href^="#"]').forEach(link=>link.addEventListener('click',event=>{const target=document.getElementById(link.getAttribute('href').slice(1));if(target){event.preventDefault();history.replaceState(null,'',link.getAttribute('href'));target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});target.setAttribute('tabindex','-1');target.focus({preventScroll:true});}}));})();
'''


def build(number):
    pid = f'paper-{number:02d}'
    path = ROOT / f'public/guides/{pid}.html'
    original = CONTENT / f'originals/{pid}.html'
    original.parent.mkdir(parents=True, exist_ok=True)
    if not original.exists():
        original.write_bytes(path.read_bytes())
    source = original.read_text()
    data = json.loads((CONTENT / f'{pid}.json').read_text())
    paper = json.loads((ROOT / f'public/data/{pid}.json').read_text())
    assert data['sourceSha256'] == paper['sourceSha256'] == hashlib.sha256((ROOT / f'public/papers/{pid}.pdf').read_bytes()).hexdigest()
    assert len(data['compact']) == 7 and len(data['questions']) == 6
    segments = {s['id']: s for s in paper['segments']}
    for gap in data['gaps']:
        assert gap['sourceEnglish'] == segments[gap['sourceSegmentId']]['sourceText']
        assert hashlib.sha256(gap['sourceEnglish'].encode()).hexdigest() == gap['sourceTextSha256']
    discussions = json.loads(re.search(r'const discussions\s*=\s*(.*?);\n', source).group(1))
    assert len(discussions) == 5
    soup = BeautifulSoup(source, 'html.parser')
    main = soup.find('main', class_='page')
    gap_body = '<div class="gap-grid">' + ''.join('<article class="gap-card"><h3>' + esc(g['title']) + '</h3>' + para(g['text']) + para(pages(g['pages']), 'page-ref') + '</article>' for g in data['gaps']) + '</div><h3>本研究如何回應</h3>' + para(data['response']) + para(pages(data['responsePages']), 'page-ref')
    gap_section = section('researchGapSection', '作者明確提出的研究缺口', '依作者的文獻回顧與問題陳述整理；研究完成後的限制另放在作業反思中。', gap_body)
    answers = [para(data[k]) + para(pages(data[k+'Pages']), 'page-ref') for k in ('purpose', 'importance', 'previous')]
    answers.append(''.join('<h4>'+esc(g['title'])+'</h4>'+para(g['text'])+para(pages(g['pages']),'page-ref') for g in data['gaps']) + para(data['response']) + para(pages(data['responsePages']), 'page-ref'))
    answers.extend(blocks(d['blocks']) + para(d['page'], 'page-ref') for d in discussions[1:4])
    answers.append('<h4>心得參考答案</h4>' + para(data['reflection']) + '<h4>可延伸的研究與理由</h4><ol>' + ''.join('<li>'+esc(x)+'</li>' for x in data['extensions']) + '</ol>' + para(pages(data['reflectionPages']), 'page-ref') + '<h4>研究限制與批判反思</h4>' + blocks(discussions[4]['blocks']) + para(discussions[4]['page'], 'page-ref'))
    assignments = '<h3 class="assignment-group-title">W．觀看及標示重點</h3><div class="assignment-list">'
    for index, (title, answer) in enumerate(zip(TITLES, answers)):
        if index == 7:
            assignments += '</div><h3 class="assignment-group-title">S．總結學習內容並提出感想</h3><div class="assignment-list">'
        compact = data['compact'][index] if index < 7 else data['reflection']
        assignments += f'<details class="assignment-card"><summary><span class="alignment-number">{index+1}</span><span>{esc(title)}</span></summary><div class="assignment-card-body"><h4>詳細參考答案</h4>{answer}<div class="assignment-compact"><strong>精簡作答版</strong>{para(compact)}</div></div></details>'
    assignments += '</div>'
    assignment_section = section('assignmentSection', '作業區', '依第一篇的 W、S 題目逐題整理。心得為可修改的參考答案；延伸研究是閱讀後的建議。', assignments, controls('Assignments', '作業答案'))
    questions = '<div class="reader-question-list">'
    for index, question in enumerate(data['questions']):
        questions += f'<details class="reader-question-card"><summary><span class="alignment-number">{index+1}</span><span>{esc(question["title"])}</span></summary><div class="reader-question-body">{para(question["prompt"], "discussion-question")}<h4>本文的回答與設計判讀</h4>{para(question["answer"])}{para(pages(question["pages"]), "page-ref")}<h4>證據能說到哪裡</h4>{para(question["boundary"], "alignment-boundary")}</div></details>'
    questions += '</div>'
    question_section = section('readerQuestionsSection', '讀者追問區', '從這篇論文的設計、比較與結果提出六個追問，分清楚作者的說法與證據的界線。', questions, controls('ReaderQuestions', '讀者追問'))
    banner = '<section id="literatureInterpretationSection" class="zone-banner" aria-labelledby="literatureInterpretationTitle"><h2 id="literatureInterpretationTitle">文獻解讀區</h2><p>先讀名詞、作者的研究缺口與四項核心討論，再進入作業區及讀者追問區。下方保留研究架構圖、統計方法與易讀解說。</p></section>'
    glossary = soup.find(id='glossarySection').extract()
    discussion = soup.find(id='discussionSection').extract()
    diagram = soup.find(id='mapSection').extract()
    easy = soup.find(id='easyReadSection').extract()
    remaining = [child.extract() for child in list(main.children)]
    for part in [banner, glossary, gap_section, discussion, assignment_section, question_section, diagram, easy, *remaining]:
        if isinstance(part, str):
            fragment = BeautifulSoup(part, 'html.parser')
            for child in list(fragment.contents):
                main.append(child.extract())
        else:
            main.append(part)
    nav = soup.select_one('.topbar .nav-links')
    nav.clear()
    for identifier, label in [('literatureInterpretationSection','文獻解讀區'),('assignmentSection','作業區'),('readerQuestionsSection','讀者追問區'),('researchGapSection','研究缺口'),('mapSection','架構圖'),('glossarySection','名詞'),('discussionSection','討論'),('easyReadSection','易讀解說')]:
        a = soup.new_tag('a', href='#'+identifier)
        a.string = label
        nav.append(a)
    button = soup.new_tag('button', type='button', onclick='window.print()')
    button.string = '列印'
    nav.append(button)
    style = soup.new_tag('style')
    style.string = STYLE
    soup.head.append(style)
    controller = soup.new_tag('script')
    controller.string = CONTROLLER
    soup.body.append(controller)
    output = str(soup).rstrip()
    assert output.count('discussions.forEach((item,index)=>') == 1
    output = output.replace('discussions.forEach((item,index)=>', 'discussions.slice(0,4).forEach((item,index)=>')
    ids = [tag['id'] for tag in BeautifulSoup(output,'html.parser').select('[id]')]
    assert len(ids) == len(set(ids)), pid
    path.write_text(output+'\n')
    return pid


def sync_sources():
    audit_path = ROOT / 'content/guide-version-audit.json'
    audit = json.loads(audit_path.read_text())
    now = datetime.now(timezone.utc).isoformat()
    for record in audit['papers'][1:]:
        content = (ROOT / f'public/guides/{record["id"]}.html').read_bytes()
        standalone = ROOT.parent / record['sourceFile']
        if standalone.exists():
            standalone.write_bytes(content)
        record.update(sha256=hashlib.sha256(content).hexdigest(), sourceModifiedAt=now, homepageMatchesSource=True, unifiedEntryMatchesSource=True, alignmentRevision='first-paper-three-zones-v1')
    homepage_path = ROOT.parent / '論文互動導讀首頁.html'
    if homepage_path.exists():
        homepage = homepage_path.read_text()
        match = re.search(r'const papers\s*=\s*(\[.*?\]);', homepage, re.S)
        papers = json.loads(match.group(1))
        for paper in papers[1:]:
            paper['html'] = base64.b64encode((ROOT / f'public/guides/paper-{paper["id"]}.html').read_bytes()).decode()
        homepage = homepage[:match.start(1)] + json.dumps(papers,ensure_ascii=False,separators=(',',':')) + homepage[match.end(1):]
        homepage_path.write_text(homepage)
    audit['alignment'] = {'checkedAt':now,'reference':'paper-01','papers':7,'assignmentsPerPaper':8,'readerQuestionsPerPaper':6,'coreDiscussionsPerPaper':4,'evidenceDirectory':'content/guide-alignment','originalGuides':'content/guide-alignment/originals'}
    audit['checkedAt'] = now
    audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    for number in range(2,9):
        print(build(number))
    sync_sources()
