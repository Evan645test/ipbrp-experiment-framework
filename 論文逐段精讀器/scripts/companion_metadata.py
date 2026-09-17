"""Keep generated companion evidence consistent with explicit curator changes."""
import copy
import hashlib
import re

def reconcile_companion(incoming, current):
    if not current.get("exhibitCompanion"):
        return incoming
    result=copy.deepcopy(incoming)
    result["readingQuality"]=copy.deepcopy(current.get("readingQuality"))
    source_segments={s["id"]:s for s in current.get("segments",[])}
    order=current.get('readingOrderRepair')
    if order and incoming.get('readingOrderRepair',{}).get('revision')!=order['revision']:
        local={s['id']:s for s in result.get('segments',[])}
        previous=order['previousSegmentIds']
        if [s['id'] for s in result.get('segments',[])]==previous:
            result['segments']=[local.get(s['id'],copy.deepcopy(s)) for s in current['segments']]
        else:
            previous_ids=set(previous)
            for index,s in enumerate(current['segments']):
                if s['id'] in local or s['id'] in previous_ids:continue
                next_ids={v['id'] for v in current['segments'][index+1:]}
                position=next((i for i,v in enumerate(result['segments']) if v['id'] in next_ids),len(result['segments']))
                result['segments'].insert(position,copy.deepcopy(s))
        result['readingOrderRepair']=copy.deepcopy(order)
    pending=[]
    blocked_absorbed=set()
    for repair in current.get("readingUnitRepairs",[]):
        local={s["id"]:s for s in result.get("segments",[])}
        target=local.get(repair["targetId"])
        source=source_segments.get(repair["targetId"])
        if not target or not source:
            continue
        updated=target["sourceText"]==source["sourceText"] and target["fragments"]==source["fragments"]
        untouched=all(p["id"] in local and all(local[p["id"]].get(k)==p.get(k) for k in ("sourceText","fragments","translation"))
                      and local[p["id"]].get("reviewStatus") not in ("reviewed","published") for p in repair["previousSegments"])
        if not updated and not untouched:
            pending.append(repair["targetId"])
            blocked_absorbed.update(repair['absorbedIds'])
            continue
        for index,segment in enumerate(result["segments"]):
            if segment["id"]==source["id"] and untouched and not updated:
                replacement=copy.deepcopy(source)
                if "excluded" in segment:
                    replacement["excluded"]=segment["excluded"]
                result["segments"][index]=replacement
            elif segment["id"] in repair["absorbedIds"]:
                segment["mergedIntoSegmentId"]=source["id"]
                segment.setdefault("excluded",True)
    result["readingUnitRepairs"]=copy.deepcopy(current.get("readingUnitRepairs",[]))
    if pending or "pendingReadingUnitRepairs" in result:
        result["pendingReadingUnitRepairs"]=pending
    for segment in result.get("segments",[]):
        source=source_segments.get(segment.get("id"))
        if source and source['sourceText']==segment['sourceText'] and segment.get('reviewStatus') not in ('reviewed','published') and segment['id'] not in blocked_absorbed:
            if 'excluded' not in segment and 'excluded' in source:segment['excluded']=source['excluded']
            if source.get('mergedIntoSegmentId') and 'mergedIntoSegmentId' not in segment:segment['mergedIntoSegmentId']=source['mergedIntoSegmentId']
            if segment.get('kind')=='caption' and source.get('kind')=='body' and re.match(r'^(?:Table|Fig(?:ure)?\.?)\s*\d+\s+(?:shows|displays|presents|illustrates|represents|depicts)\b',segment['sourceText'],re.I):segment['kind']='body'
        if source and source.get("sourceText")==segment.get("sourceText") and "readingRole" not in segment and source.get("readingRole"):
            segment.update(readingRole=source["readingRole"],section=source["section"])
        repairs=(current.get("readingQuality") or {}).get("explanationRepairs",[])
        checked=next((r for r in repairs if r["segmentId"]==segment["id"]),None)
        if checked and segment["sourceText"]==checked["sourceText"] and segment["translation"]==checked["previousTranslation"] and segment.get("reviewStatus") not in ("reviewed","published"):
            segment["translation"]=copy.deepcopy(source["translation"])
    if result.get("readingQuality"):
        ids={s["id"] for s in result["segments"]}
        quality=result["readingQuality"]
        quality["explanationRepairs"]=[r for r in quality["explanationRepairs"] if r["segmentId"] in ids]
        quality["appendices"]=[a for a in quality["appendices"] if a["exhibit"]["captionSegmentId"] in ids]
        for appendix in quality["appendices"]:
            appendix["relatedSegmentIds"]=[i for i in appendix["relatedSegmentIds"] if i in ids]
    # Source crops and exhibit identity are generated from the immutable PDF.
    result["exhibits"]=copy.deepcopy(current.get("exhibits",[]))
    captions={e["captionSegmentId"] for e in result["exhibits"]}
    body={s["id"]:s for s in result.get("segments",[]) if isinstance(s,dict) and isinstance(s.get("id"),str) and not s.get("excluded") and not s.get("readingRole") and s.get("kind")!="caption" and s["id"] not in captions}
    companion=copy.deepcopy(current["exhibitCompanion"])
    companion["links"]=[link for link in companion["links"] if link["segmentId"] in body
        and link["evidenceQuote"] == body[link["segmentId"]].get("sourceText")
        and link["sourceTextSha256"] == hashlib.sha256(body[link["segmentId"]]["sourceText"].encode()).hexdigest()
        and all(i in body for i in link["sourceSegmentIds"])]
    for study in companion["studies"].values():
        study["sourceSegmentIds"]=[i for i in study["sourceSegmentIds"] if i in body]
    result["exhibitCompanion"]=companion
    result["inlineExhibitsEnabled"]=current.get("inlineExhibitsEnabled",False)
    for index,s in enumerate(result.get('segments',[]),1):s['order']=index
    return result
