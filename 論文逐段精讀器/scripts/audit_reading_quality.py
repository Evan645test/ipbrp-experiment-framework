#!/usr/bin/env python3
"""Read-only triage of reader units; candidates always require source inspection."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS = re.compile(r"\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b")
BRIDGE = re.compile(r"(?:following (?:suggestions|recommendations)|(?:suggestions|recommendations) (?:are|were) (?:proposed|offered)|as follows)\b", re.I)
BAD_CT = re.compile(r"CT\s*[（(]\s*(?:可能是)?(?:認知訓練|認知彈性)|(?:認知訓練|認知彈性|執行功能)\s*[（(]\s*CT|運算思維\s*[（(]\s*EF", re.I)
STATEMENT = re.compile(r"^(?:CRediT|Ethics approval|Availability of data|Competing interests|Acknowledg|Data availability|Appendix)\b", re.I)

def core_segments(paper):
    captions = {e.get('captionSegmentId') for e in paper.get('exhibits', [])}
    return [s for s in paper['segments'] if not s.get('excluded')
            and not (paper.get('readingQuality') and s.get('readingRole'))
            and not (paper.get('exhibitCompanion') and (s.get('kind') == 'caption' or s['id'] in captions))]

def overlap_fraction(inner, outer):
    area = (inner[2]-inner[0])*(inner[3]-inner[1])
    if area <= 0:
        return 0
    return max(0, min(inner[2],outer[2])-max(inner[0],outer[0]))*max(0,min(inner[3],outer[3])-max(inner[1],outer[1]))/area

def audit(paper):
    findings=[]
    glossary = any(re.search(r'computational thinking\s*\(CT\)',s['sourceText'],re.I) for s in paper['segments'])
    repairs={r['segmentId']:r for r in (paper.get('readingQuality') or {}).get('explanationRepairs',[])}
    for segment in core_segments(paper):
        text=segment['sourceText']; count=len(WORDS.findall(text))
        def add(category,reason,severity='review'):
            findings.append({'segmentId':segment['id'],'pages':sorted({f['page'] for f in segment['fragments']}),
                             'wordCount':count,'category':category,'severity':severity,'reason':reason,'sourceText':text})
        if segment.get('kind')=='body':
            if count<10:
                add('short-unit','不足十個英文單字：核對是否完整句、標題、公式或跨頁續文；不得只憑長度刪除。')
            if count<25 and BRIDGE.search(text):
                add('list-introduction','只有清單引導句，核對並與後續條目組成完整單位。')
            if STATEMENT.search(segment.get('section','')) or (count<10 and STATEMENT.search(text)):
                add('supplement-in-core','研究聲明或附錄應保留，但可移至獨立入口，不占正文步驟。')
            if count and len(re.findall(r'\d',text))>count*2:
                add('numeric-fragment','數字比例高，核對是否誤讀表格資料列或公式；完整結果段不可因此刪除。')
            for exhibit in paper.get('exhibits',[]):
                if exhibit['kind']!='table' or exhibit.get('captionSegmentId')==segment['id']:
                    continue
                if any(f['page']==exhibit['page'] and overlap_fraction(f['bbox'],exhibit['bbox'])>=.92 for f in segment['fragments']):
                    add('table-cell-as-body',f"正文框幾乎完全位於 {exhibit['label']} 內，核對是否應歸入整張表。")
                    break
        checked=repairs.get(segment['id'])
        if checked and segment['translation']['status']!='reviewed' and (text!=checked['sourceText'] or segment['translation']['plainZh']!=checked['translation']['plainZh']):
            add('changed-explanation','原文或白話稿已改變，本次核對證據失效；保留修改並重新核對。','error')
        if glossary and segment['translation']['status']!='reviewed' and BAD_CT.search(segment['translation'].get('plainZh','')):
            add('term-mismatch','本篇 CT 定義為運算思維，白話稿出現已知錯譯。','error')
        assessment=segment.get('paragraphAssessment') or {}
        if assessment.get('status') in ('fragment','needs-review'):
            add('semantic-completeness','既有段落完整性評估要求核對，不能當作已確認完整段落。')
    return {'paperId':paper['id'],'coreUnits':len(core_segments(paper)),
            'errors':sum(f['severity']=='error' for f in findings),'reviewCandidates':sum(f['severity']=='review' for f in findings),
            'findings':findings}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper-id',action='append',help='可重複指定，如 paper-01；預設檢查八篇。')
    parser.add_argument('--fail-on-known-errors',action='store_true')
    args=parser.parse_args()
    paths=sorted((ROOT/'public/data').glob('paper-*.json'))
    selected=set(args.paper_id or [])
    available={p.stem for p in paths}
    if selected-available:
        parser.error('未知論文 ID：'+', '.join(sorted(selected-available)))
    reports=[audit(json.loads(p.read_text())) for p in paths if not selected or p.stem in selected]
    print(json.dumps({'readOnly':True,'interpretation':'候選項不是刪除指令；語意與閱讀順序仍需核對 PDF 頁面。','papers':reports},ensure_ascii=False,indent=2))
    if args.fail_on_known_errors and any(r['errors'] for r in reports):
        raise SystemExit(1)

if __name__=='__main__':
    main()
