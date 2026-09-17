#!/usr/bin/env python3
"""Stage or apply seven reversible, PDF-bound companion datasets."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import fitz
from build_references import atomic_json, citation_index
from build_paper01_companion import tokens
from link_exhibits import reference_keys
from validate_phase_a import validate_paper
from prepare_remaining_papers import ROOT, PLAN

REVISION='remaining-papers-companion-v1'
STAGED=ROOT/'content/remaining-papers-staged.json'
TRANSLATIONS=ROOT/'content/remaining-papers-translation-cache.json'

def digest(text):return hashlib.sha256(text.encode()).hexdigest()

def core(p):
    captions={e['captionSegmentId'] for e in p['exhibits']}
    return [s for s in p['segments'] if not s.get('excluded') and not s.get('readingRole') and s['kind']!='caption' and s['id'] not in captions]

def mutable(s):
    if s['translation']['status']=='reviewed' or s['reviewStatus'] in {'reviewed','published'}:
        raise ValueError('Refusing to replace a human-reviewed record: '+s['id'])

def in_box(f,e):
    if f['page']!=e['page']:return False
    box=fitz.Rect(f['bbox']);intersection=box & fitz.Rect(e['bbox'])
    return box.get_area()>0 and intersection.get_area()/box.get_area()>=.96

def repair(paper,item):
    result=copy.deepcopy(paper);ss={s['id']:s for s in result['segments']};before={s['id']:copy.deepcopy(s) for s in paper['segments']}
    result['readingOrderRepair']={'revision':REVISION,'previousSegmentIds':list(ss)}
    result['readingUnitRepairs']=copy.deepcopy(paper.get('readingUnitRepairs',[]))
    changed=set();new_ids=[]
    def archive(target,absorbed):
        result['readingUnitRepairs'].append({'revision':REVISION,'targetId':target,'absorbedIds':absorbed,'previousSegments':[before[i] for i in [target,*absorbed]]})
    for patch in item['replacements']:
        s=ss[patch['segmentId']];mutable(s)
        if before[s['id']]['sourceText']!=patch['expectedSource']:raise ValueError('Source guard failed: '+s['id'])
        s.update(sourceText=patch['sourceText'],fragments=copy.deepcopy(patch['fragments']),kind='body')
        if patch.get('sourceRecovery'):s['sourceRecovery']=copy.deepcopy(patch['sourceRecovery'])
        changed.add(s['id'])
    for merge in item['merges']:
        ids=[merge['targetId'],*merge['absorbedIds']]
        for sid,text in merge['expectedSources'].items():
            if before[sid]['sourceText']!=text:raise ValueError('Merge source changed: '+sid)
        for sid in ids:mutable(ss[sid])
        target=ss[ids[0]];archive(ids[0],ids[1:])
        source=merge.get('sourceText',' '.join(ss[i]['sourceText'] for i in ids))
        # These word boundaries were checked against the line-wrapped originals.
        for a,b in [('engage ment','engagement'),('behav iors','behaviors'),('understand ing','understanding'),('comple tion','completion'),('Kuder- Richardson','Kuder-Richardson')]:source=source.replace(a,b)
        target.update(sourceText=source,fragments=copy.deepcopy(merge.get('fragments',[f for i in ids for f in ss[i]['fragments']])),kind='body')
        for sid in ids[1:]:ss[sid].update(excluded=True,mergedIntoSegmentId=ids[0])
        changed.add(ids[0])
    for sid in changed:
        if not any(r['targetId']==sid and r['revision']==REVISION for r in result['readingUnitRepairs']):archive(sid,[])
        ss[sid].pop('paragraphAssessment',None)
    for sid,role in item['roles'].items():ss[sid].update(readingRole=role['role'],section=role['section'])
    for sid in item['exclusions']:ss[sid]['excluded']=True
    for addition in item['additions']:
        if addition['id'] in ss:raise ValueError('Duplicate recovered paragraph')
        s=copy.deepcopy(addition);s.update(order=0,reviewStatus='needs-review',confidence=.88 if s.get('sourceRecovery') else .98,exhibitIds=[],exhibitMentions=[],translation={'faithfulZh':'','plainZh':'','status':'untranslated','reviewedAt':None})
        ss[s['id']]=s;result['segments'].append(s);changed.add(s['id']);new_ids.append(s['id'])
    result['exhibits']=[]
    with fitz.open(ROOT/'public'/paper['pdfUrl'].lstrip('/')) as pdf:
        for raw in item['exhibits'].values():
            e=copy.deepcopy(raw);e.pop('study',None)
            if not e['caption'].strip():raise ValueError('Empty caption: '+e['id'])
            # Original captions are kept as records; a missing caption gets its own
            # stable record rather than being confused with an explanation paragraph.
            if not e.get('captionSegmentId'):
                sid=paper['id']+'-s-caption-'+e['kind']+'-'+e['number']
                s={'id':sid,'order':0,'section':e['label'],'kind':'caption','sourceText':e['caption'],'fragments':[{'page':e['page'],'bbox':e['bbox'],'pageSize':e['pageSize']}],'reviewStatus':'needs-review','confidence':.98,'translation':{'faithfulZh':e['captionZh'],'plainZh':e['captionZh'],'status':'ai-draft','reviewedAt':None},'exhibitIds':[e['id']],'exhibitMentions':[]}
                ss[sid]=s;result['segments'].append(s);e['captionSegmentId']=sid;new_ids.append(sid)
            name=f"{e['kind']}{e['number']}_p{e['page']:02d}_remaining_companion.png"
            image=ROOT/f"public/figures/{paper['id']}/{name}";image.parent.mkdir(parents=True,exist_ok=True)
            pdf[e['page']-1].get_pixmap(clip=fitz.Rect(e['bbox']),dpi=300,alpha=False).save(image)
            e.update(imageUrl=f"/figures/{paper['id']}/{name}",extractionStatus='manual-crop',extractionMethod='source-checked-300dpi-complete-companion-crop',explanationSegmentIds=[])
            result['exhibits'].append(e)
        appendices=[]
        for a in item['appendices']:
            name=f"appendix_{a['number']}_remaining_companion.png";image=ROOT/f"public/figures/{paper['id']}/{name}"
            pdf[a['page']-1].get_pixmap(clip=fitz.Rect(a['bbox']),dpi=300,alpha=False).save(image)
            e={k:copy.deepcopy(a[k]) for k in('number','caption','captionZh','page','bbox','captionSegmentId')}
            e.update(id=paper['id']+'-appendix-'+a['number'],label='Appendix '+a['number'],kind='table',pageSize=[pdf[a['page']-1].rect.width,pdf[a['page']-1].rect.height],imageUrl=f"/figures/{paper['id']}/{name}",extractionStatus='manual-crop',extractionMethod='source-checked-300dpi-complete-appendix',explanationSegmentIds=[])
            appendices.append({'exhibit':e,'relatedSegmentIds':a['relatedSegmentIds'],'faithfulZh':'','guideZh':a['guideZh'],'sourceText':a['sourceText']})
    caption_ids={e['captionSegmentId'] for e in result['exhibits']}
    for s in result['segments']:
        if s['id'] in caption_ids:continue
        if re.match(r'^(?:Fig(?:ure)?\.?|Table)\s*\d+\s+(?:shows|displays|presents|illustrates|represents|depicts)\b',s['sourceText'],re.I):s['kind']='body'
        if s.get('excluded') or s.get('readingRole'):continue
        if re.fullmatch(r'\(\d+\)\s+[A-Za-z][A-Za-z ,/-]{3,80}',s['sourceText']):
            s.update(kind='heading',excluded=True)
            continue
        containing=[e for e in result['exhibits'] if e['kind']=='table' and all(in_box(f,e) for f in s['fragments'])]
        if containing:
            e=containing[0];s.update(excluded=True,mergedIntoSegmentId=e['captionSegmentId']);s.pop('paragraphAssessment',None)
    def order_key(s):
        f=s['fragments'][0];x0,y0,x1,y1=f['bbox'];width=f['pageSize'][0]
        column=int((x0+x1)/2>width/2) if item['layout']=='two-column' else 0
        return(f['page'],column,y0,s.get('sourceRecovery',{}).get('paragraphIndex',0))
    result['segments'].sort(key=order_key)
    for index,s in enumerate(result['segments'],1):s['order']=index
    bodies=core(result);exhibits={e['id']:e for e in result['exhibits']};links=[]
    suppress={x['segmentId'] for x in item['semanticLinks'] if x.get('suppressExplicitFigures')}
    def link(s,e,method,reason):
        if any(l['segmentId']==s['id'] and l['exhibitId']==e['id'] for l in links):return
        links.append({'segmentId':s['id'],'exhibitId':e['id'],'method':method,'confidence':'high','relationshipZh':reason,'evidenceQuote':s['sourceText'],'sourceSegmentIds':[s['id']],'sourceTextSha256':digest(s['sourceText'])})
    for s in bodies:
        keys=reference_keys(s['sourceText'])
        for e in result['exhibits']:
            if (e['kind'],e['number']) in keys and not(e['kind']=='figure' and s['id'] in suppress):
                link(s,e,'explicit',f"本段明確提及 {e['label']}，可用完整原圖表核對「{item['exhibits'][e['id']]['study']['summaryZh']}」。提及圖號不代表本段已解釋全部內容。")
    for l in item['semanticLinks']:
        s=ss[l['segmentId']]
        if s in bodies:link(s,exhibits[l['exhibitId']],'semantic',l['relationshipZh'])
    docs={e['id']:tokens(e['caption']+' '+' '.join(l['evidenceQuote'] for l in links if l['exhibitId']==e['id'])) for e in result['exhibits']}
    counts=Counter(w for words in docs.values() for w in words);weights={w:math.log((len(docs)+1)/(count+1))+1 for w,count in counts.items()}
    for s in bodies:
        words=tokens(s['sourceText']);scored=[]
        for eid,target in docs.items():
            common=words&target
            if len(common)<4 or any(l['segmentId']==s['id'] and l['exhibitId']==eid for l in links):continue
            denominator=math.sqrt(sum(weights.get(w,1)**2 for w in words)*sum(weights[w]**2 for w in target))
            score=sum(weights[w]**2 for w in common)/denominator if denominator else 0
            if score>=.34:scored.append((score,eid,common))
        for _,eid,common in sorted(scored,reverse=True)[:2]:
            link(s,exhibits[eid],'semantic','語意候選：本段與圖表的作者說明共享主題詞（'+', '.join(sorted(common)[:6])+'）。主題相近尚不足以確認解釋關係，請核對後再加入。')
            links[-1]['confidence']='candidate'
    studies={}
    for e in result['exhibits']:
        evidence=list(dict.fromkeys(l['segmentId'] for l in links if l['exhibitId']==e['id'] and l['confidence']=='high'))
        e['explanationSegmentIds']=evidence
        study=copy.deepcopy(item['exhibits'][e['id']]['study']);study.update(sourceSegmentIds=evidence,status='ai-draft');studies[e['id']]=study
    for s in result['segments']:
        if not s.get('excluded'):s['exhibitIds']=[l['exhibitId'] for l in links if l['segmentId']==s['id']] if s in bodies else [e['id'] for e in result['exhibits'] if e['captionSegmentId']==s['id']]
        s['exhibitMentions']=[]
    result.update(inlineExhibitsEnabled=False,exhibitCompanion={'revision':REVISION,'links':links,'studies':studies},readingQuality={'revision':REVISION,'explanationRepairs':[],'appendices':appendices})
    result['remainingPaperProcessing']={'revision':REVISION,'beforeDataSha256':item['beforeDataSha256'],'sourceSha256':paper['sourceSha256'],'newSegmentIds':new_ids,'translationTargetIds':sorted(changed),'layout':item['layout']}
    # Preserve every existing citation record. Add a source-hashed citation view
    # for changed/recovered passages, avoiding duplicate current matches.
    existing={(c['segmentId'],c['label'],c['sourceContext']) for c in result['citations']}
    additions=citation_index({'segments':[s for s in result['segments'] if s['id'] in changed]},result['references'])
    for c in additions:
        if (c['segmentId'],c['label'],c['sourceContext']) in existing:continue
        c['id']=c['id']+'-recovered-'+digest(c['sourceContext'])[:8];result['citations'].append(c)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--apply',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    if args.prepare==args.apply:parser.error('Choose exactly one of --prepare or --apply')
    plan=json.loads(PLAN.read_text())
    if args.prepare:
        if STAGED.exists() and not args.refresh:raise ValueError('Staged data exists; use --refresh to rebuild while preserving source-hashed translations.')
        staged={'revision':REVISION,'papers':{}}
        for pid,item in plan['papers'].items():
            data=ROOT/f'public/data/{pid}.json';raw=data.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['beforeDataSha256']:raise ValueError('Source dataset changed: '+pid)
            backup=ROOT/f'content/{pid}-before-remaining-companion.json'
            if backup.exists() and backup.read_bytes()!=raw:raise ValueError('Backup differs from source')
            if not backup.exists():backup.write_bytes(raw)
            p=json.loads(raw);staged['papers'][pid]=repair(p,item)
        atomic_json(STAGED,staged)
        print(json.dumps({pid:{'bodySteps':len(core(p)),'exhibits':len(p['exhibits']),'translationTargets':len(p['remainingPaperProcessing']['translationTargetIds'])} for pid,p in staged['papers'].items()},indent=2));return
    staged=json.loads(STAGED.read_text());cache=json.loads(TRANSLATIONS.read_text());updated=[]
    manual_path=ROOT/'content/remaining-papers-reading-overrides.json';manual=json.loads(manual_path.read_text()) if manual_path.exists() else {'papers':{}}
    overrides_path=ROOT/'content/full-translation-overrides.json';overrides=json.loads(overrides_path.read_text());library_path=ROOT/'public/data/manifest.json';library=json.loads(library_path.read_text())
    for pid,p in staged['papers'].items():
        original=json.loads((ROOT/f'content/{pid}-before-remaining-companion.json').read_text());old={s['id']:s for s in original['segments']}
        current=json.loads((ROOT/f'public/data/{pid}.json').read_text())
        if current.get('remainingPaperProcessing',{}).get('revision')!=REVISION and digest((ROOT/f'public/data/{pid}.json').read_text())!=plan['papers'][pid]['beforeDataSha256']:raise ValueError('Dataset changed since preparation: '+pid)
        targets=list(dict.fromkeys(p['remainingPaperProcessing']['translationTargetIds']+list(manual['papers'].get(pid,{}))))
        for sid in targets:
            s=next(s for s in p['segments'] if s['id']==sid);mutable(s)
            t=cache['papers'][pid]['segments'].get(sid)
            if sid in p['remainingPaperProcessing']['translationTargetIds']:
                if not t or t['sourceTextSha256']!=digest(s['sourceText']):raise ValueError('Stale translation '+sid)
                translation={k:copy.deepcopy(v) for k,v in t.items() if k!='sourceTextSha256'}
            else:translation=copy.deepcopy(s['translation'])
            patch=manual['papers'].get(pid,{}).get(sid)
            if patch:
                if patch['sourceText']!=s['sourceText']:raise ValueError('Manual source guard failed: '+sid)
                for key in ('faithfulZh','plainZh'):
                    if key in patch:translation[key]=patch[key]
                translation['generatedBy']='Codex PDF-grounded reading repair, with local translation draft'
            if not translation['faithfulZh'].strip() or not translation['plainZh'].strip():raise ValueError('Incomplete translation '+sid)
            s['translation']=translation
            for acronym in set(re.findall(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\b',s['sourceText'])):
                if len(acronym)<2:continue
                for key in ('faithfulZh','plainZh'):translation[key]=re.sub(r'\b'+re.escape(acronym)+r'\b',acronym,translation[key],flags=re.I)
            previous=old[sid]['translation'] if sid in old else {'faithfulZh':'','plainZh':'','status':'untranslated','reviewedAt':None}
            p['readingQuality']['explanationRepairs'].append({'segmentId':sid,'sourceText':s['sourceText'],'previousTranslation':previous,'translation':copy.deepcopy(translation)})
        for a in p['readingQuality']['appendices']:
            t=cache['papers'][pid]['appendices'][a['exhibit']['id']]
            if t['sourceTextSha256']!=digest(a['sourceText']):raise ValueError('Stale appendix translation')
            a['faithfulZh']=a['faithfulZh'] or t['faithfulZh'];a.pop('sourceText')
        for s in p['segments']:
            existing=overrides['papers'][pid]['segments'].get(s['id'])
            if existing and existing.get('status')=='reviewed' and existing!=s['translation']:raise ValueError('Reviewed cache cannot be replaced')
            overrides['papers'][pid]['segments'][s['id']]=copy.deepcopy(s['translation'])
        validate_paper(p,ROOT/'public')
        entry=next(e for e in library['papers'] if e['id']==pid)
        entry.update(segmentCount=len(p['segments']),includedSegmentCount=sum(not s.get('excluded') for s in p['segments']),bodySegmentCount=len(core(p)),exhibitCount=len(p['exhibits']))
        manifest={'paperId':pid,'sourceSha256':p['sourceSha256'],'figures':[{'label':e['label'],'page':e['page'],'bbox':e['bbox'],'output':'public'+e['imageUrl'],'dpi':300,'method':e['extractionMethod'],'status':'ok','quality_score':1.0,'quality_reasons':[]} for e in p['exhibits']]}
        updated.append((pid,p,manifest))
    # Validate all seven before replacing any reader dataset.
    for pid,p,m in updated:atomic_json(ROOT/f'public/data/{pid}.json',p);atomic_json(ROOT/f'public/figures/{pid}/manifest.json',m)
    atomic_json(overrides_path,overrides);atomic_json(library_path,library)
    print(json.dumps({pid:{'bodySteps':len(core(p)),'exhibits':len(p['exhibits']),'statements':sum(s.get('readingRole')=='statement' and not s.get('excluded') for s in p['segments']),'appendices':len(p['readingQuality']['appendices'])} for pid,p,_ in updated},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
