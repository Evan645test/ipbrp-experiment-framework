#!/usr/bin/env python3
"""Merge six PDF-verified paragraph interruptions; preserve separate exhibits and IDs."""
import copy
import json
import re

import fitz

from build_references import atomic_json, citation_index
from extract_phase_a import sha256_file
from repair_paper01_order import PROJECT, SOURCE_SHA, position
from repair_paper01_spots import REVISION as SPOT_REVISION, attach_mentions, update_translation_cache
from validate_phase_a import validate_paper

REVISION = "paper-01-exhibit-interruptions-v1"
GROUPS = [
    ("paper-01-s-1a15e48ca5e3", "paper-01-s-43c126f8360c", "and all", "knowledge from previous sub-projects.", " ",
     "既有研究已在電腦程式設計中實施 IPBL 的設計原則，並報告了正面成果。例如，Vega et al.（2012）發現電腦程式設計對學生而言具有難度，因此引入 IPBL，讓各子專案使用相似的真實生活情境，在強化既有知識的同時導入新知識。這個方法提升了學生的程式設計表現與學習動機。Huang（2016）發現 CPBL 涉及複雜專案，學生理解關鍵知識時會面臨挑戰。因此，Huang 為 Java 程式設計課程設計了 IPBL 方法，並發現它能提升學生的學習效率與滿意度。Huang 指出，設計 IPBL 時，教師應先規劃完整專案，確保從基礎開始再逐步增加知識；後續子專案應包含新知識，以及先前子專案的所有知識。根據 Vega et al.（2012）與 Huang（2016），我們歸納出 IPBL 的三項設計原則：（1）教師預先安排完整專案，將它分成數個彼此相關的子專案，確保各子專案所涉及的知識難度逐步增加；（2）每個子專案整合增量知識（新知識），以及先前子專案中已學會的全部或大部分知識；（3）各子專案的情境應彼此相似，並與完整專案一致。圖 2 呈現 CPBL 與 IPBL 設計原則的差異（Capraro et al., 2013；Huang, 2016；Vega et al., 2012；Wang et al., 2023）。",
     "這段從既有研究整理出 IPBL 的設計方式：先規劃整體，再讓子專案循序漸進；每次加入新知識，也要運用先前學過的知識；各子專案則維持相關且一致的情境。圖 2 是兩種專題式學習設計的對照，不是新段落的分界。"),
    ("paper-01-s-adeafd695d68", "paper-01-s-1304821abdca", "press the button to", "make MatataBot perform actions", " ",
     "兩組都使用適合 4–9 歲兒童的 Matatalab 機器人程式設計套件。兒童以 2–3 人組成小組，每組配有一套工具。兒童將程式設計積木放在控制板上，再按下按鈕，讓 MatataBot 在地圖上執行動作（圖 3）。研究已顯示，Matatalab 可用於促進兒童的運算思維（CT）與執行功能（EF）（Fu et al., 2023；Zhang et al., 2025）。此外，這套工具能支援專題式學習（PBL），讓兒童在真實生活情境中動手操作、合作解決問題；不同的程式設計模組也能逐步導入複雜知識與任務。研究另外提供蠟筆、貼紙、膠水與紙杯等材料，讓兒童發揮創意裝飾機器人與地圖，藉此提升專案情境的真實性及兒童的參與程度。",
     "這段介紹兩組共同使用的工具與活動方式：每組 2–3 人共用 Matatalab，以積木控制機器人在地圖上移動，並用材料裝飾場景。作者說明這個工具如何支援合作、動手解題，以及逐步增加知識與任務難度。圖 3 顯示工具的外觀與組件。"),
    ("paper-01-s-c295e5bf0f9c", "paper-01-s-aefabf9c9ac4", "questions to spark", "children’s interest.", " ",
     "第一階段是介紹機器人程式設計任務的情境。教師為任務設定與兒童日常生活相關、且與其他子專案相似的真實情境，並提出驅動問題，以引起兒童的興趣。例如，在「嗨，紅魚」子專案中，教師先安排猜謎遊戲，引導兒童在地圖上找到紅魚，接著介紹當天任務的驅動問題：幫助 MatataBot 抵達紅魚的家。",
     "這段完整說明第一階段如何引起兒童的興趣：先用生活情境與猜謎活動帶入，再提出具體任務——讓機器人走到紅魚家。原本圖表前後的兩段文字，其實是在描述同一個教學階段。"),
    ("paper-01-s-70f25539ff85", "paper-01-s-21d579fded22", "Forty-eight children (Meanage =", "5.68 years, 24 boys and 24 girls)", " ",
     "Wang 與 Xie（2024）及 Zhang et al.（2021）報告，機器人程式設計對運算思維（CT）與執行功能（EF）具有中等效果量。研究事前以 G*power 進行統計檢定力分析，設定 f = 0.25、α = 0.05、檢定力 = 0.9、組別數 = 2、測量次數 = 3、重複測量間的相關 = 0.5，結果建議樣本數為 36（Faul et al., 2007）。研究採便利抽樣，從中國東部一所幼兒園招募 95 名 5–6 歲兒童。參與者先前未接受相關訓練，也未被報告有認知困難。I-PBRP 組有 48 名兒童，平均年齡為 5.68 歲，包括 24 名男孩及 24 名女孩；C-PBRP 組有 47 名兒童，平均年齡為 5.65 歲，包括 24 名男孩及 23 名女孩。兩組的年齡與性別沒有顯著差異（p > 0.05）。研究計畫已通過倫理審查（WZUED20250101），並取得兒童監護人的知情同意。",
     "這段交代樣本數的規劃、招募方式、兩組兒童的組成及倫理程序。實際共有 95 名兒童：增量式組 48 人、傳統式組 47 人。兩組年齡與性別未呈現顯著差異；這不等於證明兩組在所有條件上完全相同。圖表插在平均年齡數字中間，不能因此把年齡與人數拆開解讀。"),
    ("paper-01-s-2f2cfe8f1c19", "paper-01-s-6c5979a9d16b", "than the C-", "PBRP group over time.", "",
     "表 6 顯示兩組工作記憶的描述性統計與時間效應。時間效應顯示，經過 12 週後，I-PBRP 組（F = 10.91，p < 0.001，η² = 0.13）與 C-PBRP 組（F = 3.11，p < 0.05，η² = 0.04）的工作記憶都有顯著改善。圖 13 也顯示，隨著時間推進，I-PBRP 組的工作記憶上升趨勢比 C-PBRP 組更明顯。",
     "這段是在解釋表 6 與圖 13：兩組在 12 週後的工作記憶均有顯著改善，增量式組的上升趨勢更明顯。跨頁處的「C-」和「PBRP」合起來才是完整的 C-PBRP 組名；不能把後半句當成獨立段落。"),
    ("paper-01-s-f2f3f7d0c580", "paper-01-s-911670e9a711", "than the C-PBRP", "approach over time, echoing", " ",
     "時間效應的結果顯示，I-PBRP 與 C-PBRP 兩種方法在 12 週後都顯著促進兒童的運算思維（CT）。線性混合效應模型顯示，6 週後 I-PBRP 組的 CT 表現並未顯著優於 C-PBRP 組，但在 12 週後則顯著優於該組。這表示，隨著時間推進，I-PBRP 比 C-PBRP 更能促進幼兒的 CT，呼應 Huang（2016）與 Vega et al.（2012）關於 IPBL 在電腦程式設計中成效的研究。一個可能的原因是，初期兩組都學習基礎知識並執行相對簡單的任務，因此 6 週後兩組的 CT 沒有統計上顯著的差異。根據既有研究（Saad & Zainudin, 2024；Sáez-López et al., 2019），將 PBL 融入機器人程式設計的 C-PBRP 方法強調在各子專案導入不同的新知識，這可能提升兒童的 CT。隨著時間推進，程式設計知識逐漸變複雜，兒童必須連結先前學會的知識，並運用 CT 解決問題。I-PBRP 對幼兒 CT 的累積益處開始擴大，使兩組在 12 週後出現統計上顯著的 CT 差異。不同於 C-PBRP，I-PBRP 從基礎知識開始，在各子專案中逐步整合既有與新的程式設計知識。這個方法符合兒童認知發展的階段特徵（Piaget, 1971），也銜接兒童目前的能力與潛在發展，確保各項任務維持在近側發展區（ZPD）內（Vygotsky, 1987）。透過重複練習，以及將新資訊與既有知識連結，它也有助於有效儲存資訊。這樣的動態推進支援 CT 持續成長。因此，研究結果顯示，I-PBRP 在促進幼兒 CT 方面具有較佳的效果。",
     "這段是運算思維結果的討論，不是執行功能結果：兩組在 12 週後均有改善，但組間差異在 6 週時不顯著、12 週時才顯著。作者推測，增量式教學不斷整合新舊知識，其累積優勢要等任務變難後才比較明顯。這是作者對結果的可能解釋，不是另一次實驗直接證明的機制。"),
]


def prose(segment):
    text = segment["sourceText"]
    return segment["kind"] == "body" and bool(re.search(r"[A-Za-z]{3,}[.!?]|\)\.", text)) and not text.startswith("Model equation:")


def interrupted_candidates(paper):
    """Audit only: a missing sentence ending is never sufficient to auto-merge."""
    body = [s for s in sorted(paper["segments"], key=position) if not s.get("excluded") and prose(s)]
    return [(a["id"], b["id"]) for a, b in zip(body, body[1:])
            if not re.search(r"[.!?][\"’”]?\s*$", a["sourceText"])
            and b["fragments"][0]["page"] > a["fragments"][-1]["page"]]


def repair(paper):
    pdf_path = PROJECT / "public/papers/paper-01.pdf"
    if paper["id"] != "paper-01" or paper["sourceSha256"] != SOURCE_SHA or sha256_file(pdf_path) != SOURCE_SHA:
        raise ValueError("Only the PDF-verified paper-01 can be repaired")
    if not any(r["revision"] == SPOT_REVISION for r in paper.get("readingUnitRepairs", [])):
        raise ValueError("Apply the source-verified page 10/11 repair first")
    result = copy.deepcopy(paper)
    by_id = {s["id"]: s for s in result["segments"]}
    with fitz.open(pdf_path) as pdf:
        for target_id, tail_id, ending, beginning, separator, faithful, plain in GROUPS:
            if any(r["revision"] == REVISION and r["targetId"] == target_id for r in result.get("readingUnitRepairs", [])):
                continue
            target, tail = by_id[target_id], by_id[tail_id]
            if not target["sourceText"].endswith(ending) or not tail["sourceText"].startswith(beginning):
                raise ValueError(f"Inspected paragraph boundary changed: {target_id}")
            if target.get("excluded") or tail.get("excluded") or target["kind"] != "body" or tail["kind"] != "body":
                raise ValueError(f"Inspected prose inclusion changed: {target_id}")
            if any(s["translation"]["status"] == "reviewed" or s["reviewStatus"] in {"reviewed", "published"} for s in [target, tail]):
                raise ValueError("Human-reviewed material cannot be replaced automatically")
            first, last = target["fragments"][-1], tail["fragments"][0]
            if last["page"] != first["page"] + 1:
                raise ValueError("Expected adjacent source pages")
            start, finish = (first["page"], first["bbox"][3]), (last["page"], last["bbox"][1])
            intervening = [s for s in result["segments"] if s["id"] not in [target_id, tail_id]
                           and start < (s["fragments"][0]["page"], s["fragments"][0]["bbox"][1]) < finish]
            captions = [s for s in intervening if re.match(r"^(?:Fig\.\s*\d+\.|Table\s+\d+\b)", s["sourceText"])]
            if not captions or any(not s.get("excluded") and prose(s) for s in intervening):
                raise ValueError("Exhibit interruption evidence is absent or other prose intervenes")
            # Continuations align with the text margin, unlike indented new paragraphs.
            words = pdf[last["page"] - 1].get_text("words")
            box = fitz.Rect(last["bbox"])
            first_line = [w for w in words if box.contains(fitz.Point((w[0]+w[2])/2, (w[1]+w[3])/2)) and abs(w[1]-box.y0)<3]
            if not first_line or abs(min(w[0] for w in first_line)-first["bbox"][0])>3:
                raise ValueError("Continuation starts at a new-paragraph indent")
            result["readingUnitRepairs"].append({"revision": REVISION, "targetId": target_id,
                "absorbedIds": [tail_id], "previousSegments": [copy.deepcopy(target), copy.deepcopy(tail)]})
            target["sourceText"] += separator + tail["sourceText"]
            target["fragments"] += copy.deepcopy(tail["fragments"])
            target["exhibitIds"] = list(dict.fromkeys(target.get("exhibitIds", []) + tail.get("exhibitIds", [])))
            target.pop("paragraphAssessment", None)
            target["translation"] = {"faithfulZh": faithful, "plainZh": plain, "status": "ai-draft", "reviewedAt": None,
                "generatedAt": "2026-09-17T10:00:00Z", "generatedBy": "Codex PDF-verified full paragraph translation"}
            tail.update(excluded=True, mergedIntoSegmentId=target_id)
        attach_mentions(result, pdf)
    for exhibit in result["exhibits"]:
        exhibit["explanationSegmentIds"] = list(dict.fromkeys(
            by_id[segment_id].get("mergedIntoSegmentId", segment_id)
            for segment_id in exhibit["explanationSegmentIds"]))
    result["segments"].sort(key=position)
    for index, segment in enumerate(result["segments"], 1):
        segment["order"] = index
    existing = {c["id"]: c for c in result["citations"]}
    for citation in citation_index({"segments": [by_id[group[0]] for group in GROUPS]}, result["references"]):
        if citation["id"] not in existing:
            result["citations"].append(citation)
            existing[citation["id"]] = citation
        else:
            # Refresh the complete source sentence, preserving curated relationship text.
            existing[citation["id"]].update(citation)
    if interrupted_candidates(result):
        raise ValueError("Unresolved interrupted prose remains; inspect it before writing")
    return result


def main():
    path = PROJECT / "public/data/paper-01.json"
    original = json.loads(path.read_text())
    repaired = repair(original)
    validate_paper(repaired, PROJECT / "public")
    manifest_path = PROJECT / "public/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(e for e in manifest["papers"] if e["id"] == "paper-01")
    cache_path = PROJECT / "content/full-translation-overrides.json"
    cache = update_translation_cache(json.loads(cache_path.read_text()), repaired, [group[0] for group in GROUPS])
    backup = PROJECT / "content/paper-01-before-interruption-repair.json"
    if not backup.exists():
        atomic_json(backup, {"paper": original, "manifestEntry": copy.deepcopy(entry)})
    entry.update(segmentCount=len(repaired["segments"]), includedSegmentCount=sum(not s.get("excluded") for s in repaired["segments"]))
    atomic_json(path, repaired)
    atomic_json(cache_path, cache)
    atomic_json(manifest_path, manifest)
    print(json.dumps({"paperId": repaired["id"], "additionalMergedParagraphs": len(GROUPS),
                      "readingUnits": entry["includedSegmentCount"], "unresolvedCandidates": interrupted_candidates(repaired)}, indent=2))


if __name__ == "__main__":
    main()
