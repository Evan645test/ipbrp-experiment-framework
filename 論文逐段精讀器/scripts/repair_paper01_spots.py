#!/usr/bin/env python3
"""Source-verified page 10/11 repair, limited to paper-01."""
import copy
import json
import re
import fitz
from build_references import atomic_json, citation_index
from extract_phase_a import sha256_file
from repair_paper01_order import PROJECT, SOURCE_SHA, position
from validate_phase_a import validate_paper

REVISION = "paper-01-page10-11-v1"
ANCHOR = "paper-01-s-c92507a4832b"
TAIL = "paper-01-s-11c642e44a44"
TABLE = "paper-01-s-68079e87c86d"
TITLE = "paper-01-s-da6334e3a079"
HEADER = "paper-01-s-cb710b102e05"


def attach_mentions(paper, document):
    exhibits = {(e["kind"], e["number"]): e for e in paper["exhibits"]}
    for segment in paper["segments"]:
        found = []
        if not segment.get("excluded"):
            for fragment in segment["fragments"]:
                x0, y0, x1, y1 = fragment["bbox"]
                words = [w for w in document[fragment["page"] - 1].get_text("words")
                         if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
                for first, second in zip(words, words[1:]):
                    numeric = re.fullmatch(r"(\d+)[.,:]?", second[4])
                    if not re.fullmatch(r"(?:table|fig(?:ure)?s?\.?)", first[4], re.I) or not numeric or first[5:7] != second[5:7]:
                        continue
                    kind = "table" if first[4].lower().startswith("table") else "figure"
                    exhibit = exhibits.get((kind, numeric[1]))
                    if exhibit:
                        found.append({"exhibitId": exhibit["id"], "label": exhibit["label"], "page": fragment["page"],
                                      "bbox": [round(min(first[0], second[0]), 2), round(min(first[1], second[1]), 2), round(max(first[2], second[2]), 2), round(max(first[3], second[3]), 2)]})
        if found:
            segment["exhibitMentions"] = found
            segment["exhibitIds"] = list(dict.fromkeys(segment.get("exhibitIds", []) + [m["exhibitId"] for m in found]))
        else:
            segment.pop("exhibitMentions", None)


def draft(faithful, plain):
    return {"faithfulZh": faithful, "plainZh": plain, "status": "ai-draft", "reviewedAt": None,
            "generatedAt": "2026-09-17T07:13:24Z", "generatedBy": "Codex source-grounded page 10/11 repair"}


def repair(paper):
    pdf = PROJECT / "public/papers/paper-01.pdf"
    if paper["id"] != "paper-01" or paper["sourceSha256"] != SOURCE_SHA or sha256_file(pdf) != SOURCE_SHA:
        raise ValueError("Only the verified paper-01 PDF can be repaired")
    result = copy.deepcopy(paper)
    by_id = {s["id"]: s for s in result["segments"]}
    if not any(r["revision"] == REVISION for r in result.get("readingUnitRepairs", [])):
        anchor, tail, table = by_id[ANCHOR], by_id[TAIL], by_id[TABLE]
        if not anchor["sourceText"].endswith("indicating") or tail["sourceText"] != "good reliability (Campbell et al., 2013).":
            raise ValueError("Split paragraph differs from inspected source")
        if any(by_id[id]["translation"]["status"] == "reviewed" or by_id[id]["reviewStatus"] in {"reviewed", "published"} for id in [ANCHOR, TAIL, TABLE]):
            raise ValueError("Human-reviewed material cannot be replaced automatically")
        groups = [(ANCHOR, [TAIL]), (TABLE, [TITLE, HEADER])]
        records = [{"revision": REVISION, "targetId": target, "absorbedIds": absorbed,
                    "previousSegments": [copy.deepcopy(by_id[id]) for id in [target] + absorbed]} for target, absorbed in groups]
        anchor["sourceText"] += " " + tail["sourceText"]
        anchor["fragments"] += copy.deepcopy(tail["fragments"])
        anchor.pop("paragraphAssessment", None)
        anchor["translation"] = draft(
            "根據具代表性的文獻（Di Lieto et al., 2017；Robledo-Castro et al., 2023），研究者建立了初步編碼架構。這個架構依循專題式學習（PBL）的階段，以及機器人程式設計情境中兒童運算思維（CT）與執行功能（EF）的特徵。研究者檢視影片片段，確認架構的可行性並建立各編碼的範例，再邀請兩位專家確定最終編碼架構（表 1）。兩名有經驗的研究者參與編碼，遇到不同判斷時立即討論並解決分歧。Kappa 值為 0.83，顯示具有良好的信度（Campbell et al., 2013）。",
            "這一段說明兒童學習行為如何被分類與編碼：先依文獻和學習活動建立分類，透過影片確認分類可用，再由專家確認。兩位研究者負責編碼，並討論不一致的判斷。Kappa 值 0.83 是用來支持編碼一致性的指標。表 1 列出各行為代碼、名稱與判定說明；下一頁的最後一句是本段結尾，不是獨立段落。")
        table["sourceText"] = by_id[TITLE]["sourceText"] + " " + by_id[HEADER]["sourceText"] + " " + table["sourceText"]
        table.update(kind="caption", exhibitIds=["paper-01-table-1"],
                     fragments=[{"page": 10, "bbox": [37, 541.27, 510.51, 689], "pageSize": [544.25, 742.68]}])
        table["translation"] = draft(
            "表 1：行為編碼架構。欄位依序為代碼、行為及說明。\nLI｜聆聽教師：兒童在課堂上聽教師說明。\nII｜與教師互動：兒童與教師互動，例如回答問題或提供回饋。\nDP｜與同伴討論：兒童與同伴交流程式設計方案或想法。\nCA｜建立演算法：兒童規劃路線或逐步執行的順序。\nPB｜放置積木：兒童將程式設計積木放在控制板上。\nEP｜執行程式：兒童按下啟動按鈕並執行程式。\nAH｜尋求協助：兒童向教師或同伴尋求協助。\nDA｜演算法除錯：兒童反思並調整規劃的步驟或路線。\nDB｜積木除錯：兒童更換、新增或移除程式設計積木，以修正或改善程式。\nET｜延伸任務：兒童完成規定任務後，嘗試其他解法或延伸任務。\nSH｜分享：兒童向教師或同伴分享解法或成果。\nIB｜與任務無關的行為：兒童表現出偏離任務的行為，例如玩耍或聊天。",
            "這張表是觀察兒童學習行為的分類表，不是統計結果。整張表共有 12 個行為代碼，每一列都要一起看代碼、行為名稱與說明。此閱讀單位保留整張表的原始外觀，不再把表名、欄名與資料列拆開閱讀。")
        for target, absorbed in groups:
            for id in absorbed:
                by_id[id].update(excluded=True, mergedIntoSegmentId=target)
        result.setdefault("readingUnitRepairs", []).extend(records)
    for segment in result["segments"]:
        if re.match(r"^(?:Table\s+\d+|Fig\.\s+\d+)\s+(?:shows|displays|presents)\b", segment["sourceText"], re.I):
            segment["kind"] = "body"
    for exhibit in result["exhibits"]:
        if exhibit["kind"] == "table" and exhibit["number"] in {"1", "2"}:
            number = exhibit["number"]
            exhibit.update(bbox=[37, 541.27 if number == "1" else 613.84, 510.51, 689],
                           imageUrl=f"/figures/paper-01/tab{number}_p{exhibit['page']}_complete.png",
                           extractionStatus="manual-crop", extractionMethod="source-verified-300dpi-complete-table")
            if number == "1":
                exhibit["captionSegmentId"] = TABLE
    with fitz.open(pdf) as document:
        attach_mentions(result, document)
    result["inlineExhibitsEnabled"] = True
    result["segments"].sort(key=position)
    for index, segment in enumerate(result["segments"], 1):
        segment["order"] = index
    existing = {c["id"] for c in result["citations"]}
    for citation in citation_index({"segments": [by_id[ANCHOR]]}, result["references"]):
        if citation["id"] not in existing:
            result["citations"].append(citation)
    return result


def update_translation_cache(cache, paper, segment_ids=None):
    result = copy.deepcopy(cache)
    cached_paper = result["papers"]["paper-01"]
    if cached_paper["sourceSha256"] != SOURCE_SHA:
        raise ValueError("Translation cache source differs from verified paper-01")
    segments = {s["id"]: s for s in paper["segments"]}
    for segment_id in ([ANCHOR, TABLE] if segment_ids is None else segment_ids):
        previous = cached_paper["segments"][segment_id]
        translation = segments[segment_id]["translation"]
        if previous.get("status") == "reviewed" and previous != translation:
            raise ValueError("Human-reviewed cached translation cannot be replaced automatically")
        cached_paper["segments"][segment_id] = copy.deepcopy(translation)
    return result


def main():
    path = PROJECT / "public/data/paper-01.json"
    original = json.loads(path.read_text())
    repaired = repair(original)
    validate_paper(repaired, PROJECT / "public")
    cache_path = PROJECT / "content/full-translation-overrides.json"
    cache = update_translation_cache(json.loads(cache_path.read_text()), repaired)
    manifest_path = PROJECT / "public/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(e for e in manifest["papers"] if e["id"] == "paper-01")
    backup = PROJECT / "content/paper-01-before-page10-11-repair.json"
    if not backup.exists():
        atomic_json(backup, {"paper": original, "manifestEntry": copy.deepcopy(entry)})
    entry.update(segmentCount=len(repaired["segments"]), includedSegmentCount=sum(not s.get("excluded") for s in repaired["segments"]))
    atomic_json(path, repaired)
    atomic_json(manifest_path, manifest)
    atomic_json(cache_path, cache)
    figures_path = PROJECT / 'public/figures/paper-01/manifest.json'
    figures = json.loads(figures_path.read_text())
    for item in figures['figures']:
        if item['kind'] == 'table' and str(item['number']) in {'1', '2'}:
            exhibit = next(e for e in repaired['exhibits'] if e['kind'] == 'table' and e['number'] == str(item['number']))
            item.update(bbox=exhibit['bbox'], output='public'+exhibit['imageUrl'], dpi=300,
                        method='source-verified-complete-table-crop', status='ok', quality_reasons=[])
    atomic_json(figures_path, figures)
    print(json.dumps({"paperId": repaired["id"], "readingUnits": entry["includedSegmentCount"], "revision": REVISION}, indent=2))


if __name__ == "__main__":
    main()
