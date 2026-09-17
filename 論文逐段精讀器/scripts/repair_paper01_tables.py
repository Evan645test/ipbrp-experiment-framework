#!/usr/bin/env python3
"""Keep each verified paper-01 table as a complete, independent reading unit."""
import copy
import json
import re

import fitz

from build_references import atomic_json
from extract_phase_a import sha256_file
from repair_paper01_order import PROJECT, SOURCE_SHA, position
from repair_paper01_spots import attach_mentions, update_translation_cache
from validate_phase_a import validate_paper

REVISION = "paper-01-complete-tables-v1"
# Verified against original PDF captions, table rules, all rows and table notes.
SPECS = {
    "2": (11, [37, 613.84, 510.51, 689], "paper-01-s-e01f1753f441"),
    "3": (12, [37, 200.55, 510.51, 344], "paper-01-s-42e110a0ef05"),
    "4": (12, [37, 351.01, 510.51, 424], "paper-01-s-e30e9b5f5b12"),
    "5": (13, [37, 48.55, 510.51, 192.01], "paper-01-s-4929a6263b9b"),
    "6": (13, [37, 204.97, 510.51, 278], "paper-01-s-9505108def93"),
    "7": (13, [37, 455.10, 510.51, 598.55], "paper-01-s-993ba6f8e4a1"),
    "8": (13, [37, 613.84, 510.51, 689], "paper-01-s-8c7b6ee36d4a"),
    "9": (15, [37, 203.15, 510.51, 346.61], "paper-01-s-7dacb7deddd0"),
    "10": (15, [37, 353.56, 510.51, 512.20], "paper-01-s-a08ebd32f061"),
}
TERMS = {
    "Fixed effect": "固定效應", "Random effect": "隨機效應", "Model fit": "模型配適",
    "Model equation": "模型公式", "Participant": "參與者", "participant": "參與者",
    "Intercept": "截距", "Residual": "殘差", "Variance": "變異數",
    "Marginal": "邊際", "Conditional": "條件", "Mean": "平均數",
    "Group": "組別", "group": "組別", "Time": "時間", "time": "時間",
    "Working memory": "工作記憶", "Cognitive flexibility": "認知彈性", "Inhibition": "抑制控制",
    "Earlier phase": "前期", "Middle phase": "中期", "Later phase": "後期",
    "SE": "標準誤（SE）", "SD": "標準差（SD）", "CI": "信賴區間（CI）",
    "ICC": "組內相關係數（ICC）",
}
CODES = {"LI": "聆聽教師", "II": "與教師互動", "DP": "與同伴討論", "CA": "建立演算法",
         "PB": "放置積木", "EP": "執行程式", "AH": "尋求協助", "DA": "演算法除錯",
         "DB": "積木除錯", "ET": "延伸任務", "SH": "分享", "IB": "與任務無關的行為"}
TERM_PATTERN = re.compile(r"\b(?:" + "|".join(re.escape(term) for term in sorted(TERMS, key=len, reverse=True)) + r")\b")


def translate_table(parts, exhibit):
    lines = [exhibit["captionZh"]]
    for segment in parts:
        if re.match(r"^Table\s+\d+\b", segment["sourceText"]):
            continue
        text = segment["sourceText"].replace("\u200b", "")
        # Retain every number and formula operator; add row breaks, not new values.
        text = re.sub(r"\s+(?=Group\b|Residual\b|Participant\b|C-PBRP\b)", "\n", text)
        if exhibit["number"] == "10":
            text = re.sub(r"\s+(?=(?:" + "|".join(CODES) + r")\s+\d)", "\n", text)
            text = re.sub(r"\b(" + "|".join(CODES) + r")(?=\s+\d)", lambda match: match[0] + "（" + CODES[match[0]] + "）", text)
        lines.append(TERM_PATTERN.sub(lambda match: TERMS[match[0]], text).strip())
    if exhibit["number"] in {"3", "5", "7", "9"}:
        plain = "整張表包含固定效應、隨機效應、模型配適與模型公式，必須把欄名和同一列的數值一起閱讀。β 是係數，SE 是標準誤，95% CI 是 95% 信賴區間；模型配適區列出邊際與條件 R²。這些部分屬於同一張表，不再分成不同閱讀步驟。研究結果的解釋請搭配下方「論文內的解釋」閱讀。"
        if exhibit["number"] == "5":
            plain += "表下注記的公式依原 PDF 保留，未自行補寫原文中未列出的符號。"
    elif exhibit["number"] == "10":
        plain = "這張表一起呈現前期、中期、後期兩組的 12 種行為，各列要對照行為代碼、組別、次數與比例。代碼的完整定義見表 1。粗體與上標以左側原表為準，不拆開單列當成獨立段落。"
    else:
        plain = "這張表呈現兩組在 T0、T1、T2 的平均數與標準差，以及 F、p、η2 等統計量。欄名、時間點與兩組資料列一起保留；這些是同一張表的內容，不是數個正文段落。研究結果的解釋請搭配下方「論文內的解釋」閱讀。"
    return {"faithfulZh": "\n".join(lines), "plainZh": plain, "status": "ai-draft", "reviewedAt": None,
            "generatedAt": "2026-09-17T12:00:00Z", "generatedBy": "Codex verified complete-table labels translation; numeric values preserved"}


def repair(paper):
    pdf_path = PROJECT / "public/papers/paper-01.pdf"
    if paper["id"] != "paper-01" or paper["sourceSha256"] != SOURCE_SHA or sha256_file(pdf_path) != SOURCE_SHA:
        raise ValueError("Only the verified paper-01 PDF can be repaired")
    if not any(r["revision"] == "paper-01-exhibit-interruptions-v1" for r in paper.get("readingUnitRepairs", [])):
        raise ValueError("Apply the verified interrupted-prose repair first")
    result = copy.deepcopy(paper)
    by_id = {s["id"]: s for s in result["segments"]}
    with fitz.open(pdf_path) as pdf:
        for number, (page, bbox, target_id) in SPECS.items():
            exhibit = next(e for e in result["exhibits"] if e["kind"] == "table" and e["number"] == number)
            sections = {by_id[segment_id]["section"] for segment_id in exhibit["explanationSegmentIds"] if not by_id[segment_id].get("excluded")}
            if len(sections) != 1:
                raise ValueError(f"Table {number}: explanatory section is not unambiguous")
            section = next(iter(sections))
            if not any(r["revision"] == REVISION and r["targetId"] == target_id for r in result.get("readingUnitRepairs", [])):
                rect = fitz.Rect(bbox)
                parts = sorted([s for s in result["segments"] if all(f["page"] == page and rect.contains(fitz.Rect(f["bbox"])) for f in s["fragments"])], key=position)
                if not parts or parts[0]["sourceText"] != exhibit["caption"] or target_id not in {s["id"] for s in parts}:
                    raise ValueError(f"Table {number}: inspected caption or row boundaries differ")
                if any(s["translation"]["status"] == "reviewed" or s["reviewStatus"] in {"reviewed", "published"} for s in parts):
                    raise ValueError(f"Table {number}: preserve human-reviewed content")
                if any(s.get("mergedIntoSegmentId") or len(s["fragments"]) != 1 for s in parts):
                    raise ValueError(f"Table {number}: existing merge requires manual inspection")
                if by_id[target_id].get("excluded"):
                    raise ValueError(f"Table {number}: original reading position was explicitly excluded")
                absorbed = [s["id"] for s in parts if s["id"] != target_id]
                result.setdefault("readingUnitRepairs", []).append({"revision": REVISION, "targetId": target_id,
                    "absorbedIds": absorbed, "previousSegments": copy.deepcopy(parts)})
                target = by_id[target_id]
                target.update(sourceText="\n".join(s["sourceText"] for s in parts), kind="caption", section=section,
                    fragments=[{"page": page, "bbox": bbox, "pageSize": exhibit["pageSize"]}],
                    exhibitIds=[exhibit["id"]], translation=translate_table(parts, exhibit))
                target.pop("paragraphAssessment", None)
                for segment_id in absorbed:
                    by_id[segment_id].update(excluded=True, mergedIntoSegmentId=target_id)
            else:
                target = by_id[target_id]
                record = next(r for r in result["readingUnitRepairs"] if r["revision"] == REVISION and r["targetId"] == target_id)
                previous = next(s for s in record["previousSegments"] if s["id"] == target_id)
                if target["section"] == previous["section"] and target["translation"].get("generatedBy") == "Codex verified complete-table labels translation; numeric values preserved" and target["translation"]["status"] == "ai-draft" and target["reviewStatus"] not in {"reviewed", "published"}:
                    target["section"] = section
            exhibit.update(bbox=bbox, captionSegmentId=target_id,
                imageUrl=f"/figures/paper-01/tab{number}_p{page}_complete.png",
                extractionStatus="manual-crop", extractionMethod="source-verified-300dpi-complete-table")
        attach_mentions(result, pdf)
    result["segments"].sort(key=position)
    for index, segment in enumerate(result["segments"], 1):
        segment["order"] = index
    # Each known table must own exactly one reader step and cover all its archived parts.
    for exhibit in [e for e in result["exhibits"] if e["kind"] == "table"]:
        rect = fitz.Rect(exhibit["bbox"])
        owned = [s for s in result["segments"] if not s.get("excluded") and len(s["fragments"]) == 1
                 and s["fragments"][0]["page"] == exhibit["page"] and rect.contains(fitz.Rect(s["fragments"][0]["bbox"]))]
        if len(owned) != 1 or owned[0]["id"] != exhibit["captionSegmentId"]:
            raise ValueError(f"{exhibit['label']}: expected one complete reader step")
    return result


def main():
    path = PROJECT / "public/data/paper-01.json"
    original = json.loads(path.read_text())
    repaired = repair(original)
    validate_paper(repaired, PROJECT / "public")
    cache_path = PROJECT / "content/full-translation-overrides.json"
    cache = update_translation_cache(json.loads(cache_path.read_text()), repaired, [spec[2] for spec in SPECS.values()])
    manifest_path = PROJECT / "public/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(e for e in manifest["papers"] if e["id"] == "paper-01")
    figures_path = PROJECT / "public/figures/paper-01/manifest.json"
    figures = json.loads(figures_path.read_text())
    original_figures = copy.deepcopy(figures)
    for item in figures["figures"]:
        if item["kind"] == "table" and str(item["number"]) in SPECS:
            exhibit = next(e for e in repaired["exhibits"] if e["kind"] == "table" and e["number"] == str(item["number"]))
            item.update(bbox=exhibit["bbox"], output="public" + exhibit["imageUrl"], dpi=300,
                        method="source-verified-complete-table-crop", status="ok", quality_reasons=[])
    backup = PROJECT / "content/paper-01-before-complete-table-repair.json"
    if not backup.exists():
        atomic_json(backup, {"paper": original, "manifestEntry": copy.deepcopy(entry), "figuresManifest": original_figures})
    entry.update(segmentCount=len(repaired["segments"]), includedSegmentCount=sum(not s.get("excluded") for s in repaired["segments"]))
    atomic_json(path, repaired)
    atomic_json(cache_path, cache)
    atomic_json(manifest_path, manifest)
    atomic_json(figures_path, figures)
    print(json.dumps({"paperId": repaired["id"], "completeTables": 10, "readingUnits": entry["includedSegmentCount"]}, indent=2))


if __name__ == "__main__":
    main()
