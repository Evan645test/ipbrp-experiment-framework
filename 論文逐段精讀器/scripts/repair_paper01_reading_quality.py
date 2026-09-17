#!/usr/bin/env python3
"""First-paper-only, reversible role routing, future-list recovery and grounded explanations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import fitz
from build_references import atomic_json
from build_paper01_companion import ROOT, SOURCE_SHA
from companion_metadata import reconcile_companion
from validate_phase_a import validate_paper

REVISION = "paper-01-reading-quality-v1"
ANCHOR = "paper-01-s-806f9b6ab1aa"
ABSORBED = ["paper-01-s-8f57a26a733c", "paper-01-s-603255494860"]
ROLES = {
    "7871d7663630": ("statement", "CRediT authorship contribution statement"),
    "309d9d9f2ba9": ("statement", "Ethics approval and informed consent"),
    "2a879afd88e1": ("statement", "Availability of data and material"),
    "c8ece8616b3d": ("statement", "Competing interests"),
    "e604986f06c6": ("statement", "Acknowledgment"),
    "d3a81bdfa161": ("appendix", "Appendix I"),
    "6731c7284556": ("appendix", "Appendix II"),
    "bbba8f6ed395": ("statement", "Data availability"),
}
PLAIN = {
    "d32eb93a5c39": "這段交代本研究如何測量運算思維：使用 15 題的 TechCheck-K，滿分 15 分。過去研究曾驗證這個工具；本研究另得到 KR-20 = 0.87，支持此次測驗的信度。這兩項證據來源不同，不能把本研究的數值歸給先前研究。附錄 I 提供一道範例題，不是整份測驗。",
    "77bbe7d39176": "這段解釋運算思維的組間比較。線性混合模型解釋了 47% 的變異；6 週時兩組差異不顯著，12 週時增量式組較傳統式組多 1.27 分，差異達顯著。不能把結果說成整段期間一直有顯著優勢。",
    "806f9b6ab1aa": "作者提出五項未來研究方向：增加樣本的數量與多樣性、延長研究；加入更完整的認知評估；把 IPBL 用於其他學科；考慮空間或數學能力；繼續發展支持 CT 與 EF 的教學方法。這些是後續研究建議，不是本研究已完成或已證明的結果。",
    "a0ff9a97bba8": "這段談教學與理論應用上的貢獻：把原本用於程式設計的 IPBL 應用到幼兒機器人學習，並依研究結果提出教學上的啟示。作者也建議教育工作者接受實施這套方法的培訓；這不是在介紹行為分析方法的貢獻。",
    "59c018b7a55f": "這段談研究方法上的貢獻：除了比較測驗成績，作者用漸進式序列分析觀察不同階段的行為模式，讓教學方法的效果有學習過程上的解釋。這與上一段的教學貢獻不同。",
}

def repair(paper):
    if paper["id"] != "paper-01" or paper["sourceSha256"] != SOURCE_SHA:
        raise ValueError("Only the verified paper-01 can be changed")
    if paper.get("readingQuality", {}).get("revision") == REVISION:
        return corrected_appendix(copy.deepcopy(paper))
    result = copy.deepcopy(paper)
    by_id = {s["id"]: s for s in result["segments"]}
    targets = [ANCHOR, *ABSORBED] + ["paper-01-s-"+key for key in ROLES]
    for sid in targets:
        if by_id[sid]["translation"]["status"] == "reviewed" or by_id[sid]["reviewStatus"] in {"reviewed", "published"}:
            raise ValueError("Human-reviewed content requires an explicit manual revision: "+sid)
    anchor = by_id[ANCHOR]
    if anchor["sourceText"] != "To extend the research scope, several recommendations are offered." or not by_id[ABSORBED[0]]["sourceText"].startswith("(1)") or not by_id[ABSORBED[1]]["sourceText"].startswith("(2)"):
        raise ValueError("Future directions no longer match inspected source")
    result.setdefault("readingUnitRepairs", []).append({"revision": REVISION, "targetId": ANCHOR, "absorbedIds": ABSORBED,
        "previousSegments": [copy.deepcopy(by_id[i]) for i in [ANCHOR, *ABSORBED]]})
    anchor["sourceText"] = " ".join(by_id[i]["sourceText"] for i in [ANCHOR, *ABSORBED])
    anchor["fragments"] = [copy.deepcopy(f) for i in [ANCHOR, *ABSORBED] for f in by_id[i]["fragments"]]
    grouped = {}
    for fragment in anchor["fragments"]:
        if fragment["page"] not in grouped:
            grouped[fragment["page"]] = fragment
        else:
            box = grouped[fragment["page"]]["bbox"]; other = fragment["bbox"]
            grouped[fragment["page"]]["bbox"] = [min(box[0],other[0]),min(box[1],other[1]),max(box[2],other[2]),max(box[3],other[3])]
    anchor["fragments"] = list(grouped.values())
    anchor["translation"]["faithfulZh"] = "為了拓展研究範圍，作者提出以下建議：\n（1）增加參與者的數量與多樣性，並延長研究時間，以驗證目前的發現。\n（2）為了更完整掌握兒童的運算思維（CT）與執行功能（EF）發展，可考慮更廣泛的認知概況評估，並加入任務式評量或訪談等測量。\n（3）IPBL 適合透過漸進式知識建構獲益的兒童；研究者可將它應用於其他學科，支持知識與技能的發展。\n（4）未來研究可納入空間或數學能力等變項，進一步釐清 I-PBRP 方法的效益。\n（5）本研究提出 I-PBRP，作為提升兒童 CT 與 EF 的可行方案；研究者可繼續發展有效的相關教學方法。"
    for sid in ABSORBED:
        by_id[sid].update(excluded=True, mergedIntoSegmentId=ANCHOR)
    for key, (role, section) in ROLES.items():
        by_id["paper-01-s-"+key].update(readingRole=role, section=section)
    patches = {"paper-01-s-"+key: text for key, text in PLAIN.items() if text}
    # Locate these original paragraphs by their unique inspected source rather than guessing IDs.
    for prefix, text in [
        ("Table 2 shows", "這段搭配表 2 與圖 11，說明兩組運算思維（CT）的變化：兩組在 12 週後都有顯著改善，增量式組的上升趨勢更明顯。這裡的 CT 是運算思維，不是認知訓練；組間差異仍需與表 3 一起核對。"),
        ("Table 8 shows", "這段搭配表 8 與圖 14，說明認知彈性的變化。兩組在 12 週後都有顯著改善，增量式組的上升趨勢更明顯；不能只提增量式組而漏掉傳統式組的改善。"),
        ("This research proposed an I-PBRP", "這段總結研究：比較兩種教學方法對運算思維（CT）、執行功能（EF）及學習行為的影響。12 週後增量式組的表現較好，行為分析也顯示較順暢的任務完成與較正向的學習行為。認知彈性是 EF 的其中一個構面，不是 CT 的意思。"),
    ]:
        matches = [s for s in result["segments"] if s["sourceText"].startswith(prefix)]
        if len(matches) != 1:
            raise ValueError("Expected exactly one inspected paragraph: "+prefix)
        patches[matches[0]["id"]] = text
    repairs = []
    for sid, text in patches.items():
        segment = by_id[sid]
        if segment["translation"]["status"] == "reviewed" or segment["reviewStatus"] in {"reviewed", "published"}:
            raise ValueError("Cannot overwrite human explanation: "+sid)
        previous = copy.deepcopy(segment["translation"])
        if sid == ANCHOR:
            previous = copy.deepcopy(next(r for r in result["readingUnitRepairs"] if r["revision"] == REVISION)["previousSegments"][0]["translation"])
        segment["translation"].update(plainZh=text, status="ai-draft", reviewedAt=None, generatedBy="Codex source-grounded reading-quality repair", generatedAt=datetime.now(timezone.utc).isoformat())
        repairs.append({"segmentId": sid, "sourceText": segment["sourceText"], "previousTranslation": previous, "translation": copy.deepcopy(segment["translation"])})
    # Preserve the two original data-availability statements, correcting only their translation direction.
    availability = by_id["paper-01-s-2a879afd88e1"]
    previous_availability = copy.deepcopy(availability["translation"])
    availability["translation"].update(faithfulZh="資料可向通訊作者提出請求取得。", plainZh="作者表示可向通訊作者索取資料，不代表資料已公開下載。")
    repairs.append({"segmentId":availability["id"],"sourceText":availability["sourceText"],"previousTranslation":previous_availability,"translation":copy.deepcopy(availability["translation"])})
    appendices = []
    for number, page, bbox, sid, related, faithful, guide in [
        ("I", 18, [39, 413, 509, 688], "d3a81bdfa161", "d32eb93a5c39", "附錄 I：TechCheck-K 運算思維測驗的範例題（Relkin 與 Bers，2021）。圖中問題為『接下來是哪一個形狀？』，並列出三個選項。", ["這是一道範例題，不是完整 15 題試卷，也不是研究結果。", "配合正文的測量工具段落理解題型，不根據示例推論兒童的測驗分數。"]),
        ("II", 19, [39, 66, 509, 601], "6731c7284556", "e57b858d5ac0", "附錄 II：執行功能測量的詳細內容（Howard 與 Melhuish，2017）。\n\nGo/No-Go（抑制控制）：分數範圍 0–1，滿分 1。兒童在 Go 試次點擊畫面抓魚，在 No-Go 試次避免點擊鯊魚。Go 占 80%，No-Go 占 20%；刺激呈現 1,500 毫秒，刺激間隔 1,000 毫秒。最終分數是兩種試次正確率的乘積。\n\nMr. Ant（視覺空間工作記憶）：分數範圍 0–8，滿分 8。兒童短暫觀看後，回憶並點選螞蟻身上彩色貼紙的位置。難度由 1 至 8 個貼紙逐級增加，每級有三次嘗試；若同級三次都失敗，測驗終止。從第一級開始，各級至少兩次正確得 1 分；僅一次正確得 1/3 分。\n\nCard Sorting（認知彈性）：分數範圍 0–12，滿分 12。兒童依顏色或形狀，把卡片分到以紅船或藍兔標示的區域。每次有規則提醒，同一刺激不連續出現超過兩次。前六次後改用另一分類規則，卡片加上黑框，再做六次；以正確分類次數計分。\n\n註：作者已取得設計者授權，在出版品中附上適當引用並使用畫面截圖。", ["三列分別測量抑制控制、工作記憶與認知彈性，量尺範圍不同，不能直接比較原始分數大小。", "畫面是工具示例，不是參與者的作答紀錄或研究成效。"]),
    ]:
        exhibit = {"id": "paper-01-appendix-"+number.lower(), "label": "Appendix "+number, "kind": "figure", "number": number,
            "page": page, "bbox": bbox, "pageSize": [544.25,742.68], "caption": "Appendix "+number,
            "captionZh": "附錄 "+number, "imageUrl": "/figures/paper-01/appendix-"+number.lower()+"_complete.png",
            "extractionStatus": "manual-crop", "extractionMethod": "figure-extractor-source-verified-300dpi-complete-appendix",
            "captionSegmentId": "paper-01-s-"+sid, "explanationSegmentIds": ["paper-01-s-"+related]}
        appendices.append({"exhibit": exhibit, "relatedSegmentIds": exhibit["explanationSegmentIds"], "faithfulZh": faithful, "guideZh": guide})
    result["readingQuality"] = {"revision": REVISION, "explanationRepairs": repairs, "appendices": appendices}
    return corrected_appendix(reconcile_companion(result, result))

def corrected_appendix(result):
    for appendix in result["readingQuality"]["appendices"]:
        if appendix["exhibit"]["number"] == "II":
            appendix["faithfulZh"] = appendix["faithfulZh"].replace("前六次後改用另一分類規則，卡片加上黑框，再做六次；以正確分類次數計分。", "原表表示：若在規則轉換前、後的六次試次中至少五次正確，則轉換至另一分類規則，卡片帶有黑框；最終分數依規則改變後正確分類的卡片數計算。")
            caution = "Card Sorting 原表對轉換前／後試次與計分的敘述較簡略；保留其條件式說法，不自行推定每位兒童一律完成六次後再做六次。"
            if caution not in appendix["guideZh"]:
                appendix["guideZh"].append(caution)
    return result

def main():
    path = ROOT/"public/data/paper-01.json"
    paper = json.loads(path.read_text())
    pdf = ROOT/"public/papers/paper-01.pdf"
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("Immutable PDF hash mismatch")
    updated = repair(paper)
    extractor = Path(os.environ.get("FIGURE_EXTRACTOR_SRC", Path.home()/".codex/skills/figure-extractor/src"))
    env = dict(os.environ, PYTHONPATH=str(extractor)+os.pathsep+os.environ.get("PYTHONPATH", ""))
    for appendix in updated["readingQuality"]["appendices"]:
        e = appendix["exhibit"]; image = ROOT/"public"/e["imageUrl"].lstrip("/")
        if not image.exists():
            subprocess.run([sys.executable,"-m","figure_extractor","crop",str(pdf),"--page",str(e["page"]),"--bbox",",".join(map(str,e["bbox"])),"--out",str(image),"--dpi","300"],env=env,check=True)
        pix = fitz.Pixmap(image)
        if pix.width < 1900 or pix.height < 1000:
            raise ValueError("Incomplete appendix crop: "+str(image))
    validate_paper(updated, ROOT/"public")
    manifest_path = ROOT/"public/data/manifest.json"; manifest = json.loads(manifest_path.read_text())
    entry = next(e for e in manifest["papers"] if e["id"] == "paper-01")
    cache_path = ROOT/"content/full-translation-overrides.json"; cache = json.loads(cache_path.read_text())
    backup = ROOT/"content/paper-01-before-reading-quality.json"
    if not backup.exists():
        atomic_json(backup,{"paper":paper,"manifestEntry":copy.deepcopy(entry),"cacheSegments":copy.deepcopy(cache["papers"]["paper-01"]["segments"]),
            "otherPaperHashes":{str(n):hashlib.sha256((ROOT/f"public/data/paper-{n:02d}.json").read_bytes()).hexdigest() for n in range(2,9)}})
    for segment in updated["segments"]:
        previous = next(s for s in paper["segments"] if s["id"] == segment["id"])
        if segment["translation"] != previous["translation"]:
            old = cache["papers"]["paper-01"]["segments"][segment["id"]]
            if old.get("status") == "reviewed":
                raise ValueError("Cannot overwrite reviewed translation cache")
            cache["papers"]["paper-01"]["segments"][segment["id"]] = copy.deepcopy(segment["translation"])
    captions = {e["captionSegmentId"] for e in updated["exhibits"]}
    entry.update(includedSegmentCount=sum(not s.get("excluded") for s in updated["segments"]),bodySegmentCount=sum(not s.get("excluded") and not s.get("readingRole") and s["kind"]!="caption" and s["id"] not in captions for s in updated["segments"]))
    atomic_json(path,updated); atomic_json(manifest_path,manifest); atomic_json(cache_path,cache)
    print(json.dumps({"revision":REVISION,"bodySteps":entry["bodySegmentCount"],"statements":6,"appendices":2,"explanations":len(updated["readingQuality"]["explanationRepairs"]),"originalRecords":len(updated["segments"])},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
