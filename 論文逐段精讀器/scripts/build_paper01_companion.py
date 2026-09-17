#!/usr/bin/env python3
"""Add source-grounded companion metadata to paper 01 only, preserving every record."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
import importlib.util
import shutil
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from build_references import atomic_json
from link_exhibits import reference_keys
from validate_phase_a import validate_paper

ROOT = Path(__file__).resolve().parent.parent
REVISION = "paper-01-exhibit-companion-v1"
SOURCE_SHA = "f115fdd76360d2b81f11162f81a419d30c973b58bdeb13a4b504a1f1a63a3ca1"
FIGURES = {
    "1": ("PBL 的六階段循環", "依箭頭閱讀：任務情境介紹→知識與技能建立→溝通與方案設計→任務探究→展示與評估→修訂與延伸。", "循環表示教學流程，不是統計結果，也不表示每一階段花費相同時間。"),
    "2": ("CPBL 與 IPBL 的設計原則對照", "左側 CPBL、右側 IPBL；逐項對照子專題安排、舊知識與新知識的連結，以及子專題情境是否一致。", "這是設計原則整理，不能單靠此圖證明哪種方法的成效較好。"),
    "3": ("Matatalab 機器人程式設計工具", "對照程式積木、控制板、指令塔、MatataBot 及地圖；正文說明放置積木後按按鈕，讓機器人在地圖執行指令。", "這是工具示意圖，不是兒童表現或介入效果的比較。"),
    "4": ("I-PBRP 如何連結已學與新增知識", "每列是一個學習子專題；中欄 Consolidated knowledge 是已學知識，右欄 Incremental knowledge 是新增知識。由上往下看知識如何逐步累積，最後綜合應用。", "此圖呈現課程安排，沒有測量每個子專題的學習效果。"),
    "5": ("C-PBRP 各子專題的新知識安排", "對照子專題名稱及 New knowledge 欄；再與圖 4 的已學／新增知識分欄比較。兩組最後仍有綜合應用任務。", "沒有要求系統性串連舊知識，不等於兒童完全不會運用舊知識。"),
    "6": ("I-PBRP 子專題內及子專題間的流程", "每個子專題內有六階段循環；跨子專題的連線表示前一子專題的已學知識與下一子專題新知識相連。", "圖形大小及連線不代表效果量或學習時間；須搭配正文理解漸進安排。"),
    "7": ("介紹左轉與辨認左右的課堂活動", "完整保留兩個面板：(a) 左轉路標活動；(b) 辨認左右活動。正文說明先複習舊積木，再介紹新的左轉積木。", "照片是教學示例，不是兩組成效對照或獨立測量。"),
    "8": ("教師交代 Red Fish 任務目標與要求", "對照投影片的起點、終點及地圖，再看教師向全班說明的課堂照片；與本段的同儕討論和方案設計階段一起閱讀。", "照片呈現任務情境，不能單憑照片推定兒童已理解或完成任務。"),
    "9": ("小組共同建立與執行機器人程式", "圖中標示工具與地圖；對照正文的合作執行、發現錯誤、調整方案，以及教師必要時協助。", "這是任務探究示例，不能據此估計除錯次數或活動成效。"),
    "10": ("兩組介入及三次測量的實驗流程", "橘色 I-PBRP（N=48）、綠色 C-PBRP（N=47）；由上往下看 T0 前測、6 週介入、T1 中測、再 6 週介入與 T2 後測。每週介入 60 分鐘，測驗各 30 分鐘。", "流程圖沒有解釋所有研究設計細節；抽樣與分組方式仍須核對方法段落。"),
    "11": ("兩組 CT 分數隨時間的變化", "橫軸 T0／T1／T2，縱軸 CT 分數；橘色 I-PBRP、綠色 C-PBRP，圖例註明 95% CI。比較各組上升趨勢，再用表 3 核對組別×時間效果。", "趨勢及信賴區間不能代替正式組間檢定；不從圖片估讀精確分數。"),
    "12": ("兩組抑制控制分數隨時間的變化", "橫軸 T0／T1／T2，縱軸 Inhibition；橘色 I-PBRP、綠色 C-PBRP，圖例註明 95% CI。搭配表 4 看組內時間效果，表 5 看組別×時間效果。", "兩組曲線的間距不是 p 值，也不能只靠誤差棒重疊判定是否顯著。"),
    "13": ("兩組工作記憶分數隨時間的變化", "橫軸 T0／T1／T2，縱軸 Working memory；橘色 I-PBRP、綠色 C-PBRP，圖例註明 95% CI。搭配表 6、7 區分描述統計與混合模型檢定。", "精確平均數以表 6 為準；組間變化的檢定以表 7 為準。"),
    "14": ("兩組認知彈性分數隨時間的變化", "橫軸 T0／T1／T2，縱軸 Cognitive flexibility；橘色 I-PBRP、綠色 C-PBRP，圖例註明 95% CI。搭配表 8、9 核對平均數與組別×時間效果。", "曲線呈現變化，不單獨證明教學方法造成的因果效果。"),
    "15": ("兩組前、中、後期的行為轉移模式", "上排 I-PBRP、下排 C-PBRP；三欄依序是前期、中期、後期。圓圈為行為代碼，箭頭為轉移方向，連線數字為分析的 Z 值。黑線為兩組都有的序列，紅線為某一組獨有的序列；代碼定義見圖下注記及表 1。", "正文設定 Z > 1.96 篩選顯著序列；箭頭不是因果關係，Z 值不是行為次數。正文中期的 LT→DP 與表 1 的 LI 代碼不一致，保留原文並提示核對。"),
}
METRICS = {"2": "CT", "4": "抑制控制", "6": "工作記憶", "8": "認知彈性"}
MODELS = {"3": "CT", "5": "抑制控制", "7": "工作記憶", "9": "認知彈性"}
# Semantic links below were checked against the original passage, figure labels,
# and the author's explicitly associated passages. No probability is fabricated.
SEMANTIC = [
    ("190b05a24c0c", "figure-2", "本段未寫圖號，但直接比較 CPBL／IPBL 如何串連已學與新增知識，對應圖 2 的設計原則。圖 2 不證明本段提出的成效機制。"),
    ("d70bdab7383f", "figure-2", "本段說明 CPBL 各子專題主要引入不同新知識且連結有限，對應圖 2 左側的三項原則。"),
    ("40757fb92c91", "figure-2", "本段定義 IPBL 從基礎出發並累積先前知識，對應圖 2 右側的漸進知識與相近情境安排。"),
    ("102dea33da1b", "figure-4", "本段提出 I-PBRP 由簡至繁、重複與連結舊知識的理論依據；圖 4 呈現此原則如何落實為課程知識安排，不是理論有效性的檢定。"),
    ("c295e5bf0f9c", "figure-6", "本段詳述第一階段的任務情境介紹，對應圖 6 各子專題流程的起點。"),
    ("613524e050b0", "figure-6", "本段詳述第五階段的展示與評估，對應圖 6 子專題內的同名階段。"),
    ("e4bc8d87e80d", "figure-6", "本段詳述第六階段的修訂與延伸，對應圖 6 子專題內的同名階段。"),
    ("13ebaa9517c6", "figure-6", "本段說明完成六階段後進入新的、更複雜子專題，對應圖 6 子專題間串連舊知識與新增知識的流程。"),
    ("cebf56f7d36b", "figure-10", "本段概述 12 週研究設計與組內、組間比較；圖 10 補充兩組介入與三次測量的時間安排。"),
    ("70f25539ff85", "figure-10", "本段列出 95 名參與者及兩組人數；圖 10 的 N=48 與 N=47 對應此分組資訊，但抽樣細節以正文為準。"),
    ("1bf2486fad12", "figure-10", "本段說明同教師、同介入時長及測驗執行的一致性；圖 10 補充共同測量時程，不呈現所有忠實度措施。"),
    ("cf031c71b7e5", "figure-15", "本段定義前、中、後期錄影分析與 Z > 1.96 的序列篩選；圖 15 是這套分析產生的行為轉移圖。"),
    ("4bf7a5b21ad1", "figure-15", "本段未重複圖號，但逐項解釋前期行為序列，對應圖 15 左欄兩組的前期網絡。整張圖保留，不裁掉其他階段。"),
    ("2b0657e18a04", "figure-15", "本段承接圖 15，比較中期兩組的程式建立、求助、除錯與分享／延伸序列，對應圖 15 中欄。"),
    ("89aaea93bb6b", "figure-15", "本段承接圖 15，解釋後期兩組的行為序列差異，對應圖 15 右欄；不將序列推論為因果。"),
    ("4fe4eaa10af4", "table-5", "本段討論抑制控制在 6 週與 12 週的組間差異及可能機制，對應表 5 的組別×時間結果；機制是作者討論，不是表格直接測量。"),
    ("1993a4d8d46e", "table-7", "本段討論工作記憶隨介入時間出現的組間差異，對應表 7；舊知識連結的解釋屬於作者提出的可能機制。"),
    ("e4aa3b962c51", "table-9", "本段討論認知彈性的時間差異與可能機制，對應表 9 的組別×時間結果。"),
    ("e10106e5cd6e", "figure-15", "本段整合前、中、後期行為模式，對應圖 15 的三階段網絡；正文的機制說明須與圖中直接觀察的序列區分。"),
]
STOP = set("a an the and or of to in on for from with as by is are was were be been this that these those it its their they we our both each all some more most such can could may might would should have has had at after before over under between through into also than then while study research children child young learning learned knowledge programming robot project sub projects approach approaches pbrp ipbrp cpbrp pbl ipbl group groups results development showed shows indicated based respectively used found time".split())

def tokens(text):
    return set(w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP)

def build(paper):
    if paper.get("readingQuality") and paper.get("exhibitCompanion"):
        # A new source reconstruction must not silently regenerate semantic links.
        from companion_metadata import reconcile_companion
        return reconcile_companion(paper,paper)
    result = copy.deepcopy(paper)
    segments = {s["id"]: s for s in paper["segments"]}
    body = [s for s in paper["segments"] if not s.get("excluded") and s["kind"] == "body"]
    exhibits = {e["id"]: e for e in result["exhibits"]}
    links = []
    baseline_path = ROOT / "content/paper-01-before-companion.json"
    verified_sources = {s["id"]: s["sourceText"] for s in json.loads(baseline_path.read_text())["segments"]} if baseline_path.exists() else {s["id"]: s["sourceText"] for s in paper["segments"]}
    def add(s, e, method, confidence, reason):
        if any(l["segmentId"] == s["id"] and l["exhibitId"] == e["id"] for l in links):
            return
        links.append({"segmentId": s["id"], "exhibitId": e["id"], "method": method, "confidence": confidence,
                      "relationshipZh": reason, "evidenceQuote": s["sourceText"], "sourceSegmentIds": [s["id"]],
                      "sourceTextSha256": hashlib.sha256(s["sourceText"].encode()).hexdigest()})
    for s in body:
        keys = reference_keys(s["sourceText"])
        matching = [e for e in exhibits.values() if (e["kind"], e["number"]) in keys]
        def mention_position(e):
            prefix = r"Tables?" if e["kind"] == "table" else r"Fig(?:ure)?s?\.?"
            match = re.search(r"\b" + prefix + r"\s*" + re.escape(e["number"]) + r"(?!\d)", s["sourceText"], re.I)
            return match.start() if match else len(s["sourceText"])
        matching.sort(key=mention_position)
        for e in matching:
            if e["kind"] == "figure":
                purpose = FIGURES[e["number"]][0]
            else:
                purpose = ("行為編碼定義" if e["number"] == "1" else "分期行為次數與比例" if e["number"] == "10" else f'{METRICS[e["number"]]}描述統計與組內時間效果' if e["number"] in METRICS else f'{MODELS[e["number"]]}混合模型與組別×時間效果')
            add(s, e, "explicit", "high", f'本段明確提及 {e["label"]}，可用原圖表核對「{purpose}」。下方作者說明保留整段；單純提及編號不等於本段解釋了全部圖表內容。')
    for suffix, slug, reason in SEMANTIC:
        s = segments.get(f"paper-01-s-{suffix}")
        if not s or s not in body:
            continue
        if s["sourceText"] != verified_sources.get(s["id"]):
            continue
        add(s, exhibits[f"paper-01-{slug}"], "semantic", "high", reason)
    # Discussion of CT: match the unique passage's actual claim, not PDF proximity.
    for s in body:
        if s["sourceText"] == verified_sources.get(s["id"]) and s["section"].startswith("6.1.") and "12 weeks" in s["sourceText"] and "6 weeks" in s["sourceText"]:
            add(s, exhibits["paper-01-table-3"], "semantic", "high", "本段討論 CT 在 6 週未顯著、12 週出現差異的結果，對應表 3 的組別×時間檢定；知識累積的機制屬作者討論。")
    # Topic retrieval can only propose candidates. It never becomes an automatic
    # high-confidence semantic link, nor uses physical proximity as evidence.
    docs = {e["id"]: tokens(e["caption"] + " " + " ".join(segments[i]["sourceText"] for i in e["explanationSegmentIds"])) for e in exhibits.values()}
    counts = Counter(w for words in docs.values() for w in words)
    weights = {w: math.log((len(docs)+1)/(n+1))+1 for w,n in counts.items()}
    for s in body:
        words = tokens(s["sourceText"])
        scored = []
        for eid, target in docs.items():
            common = words & target
            if len(common) < 4:
                continue
            numerator = sum(weights[w]**2 for w in common)
            denominator = math.sqrt(sum(weights.get(w, 1)**2 for w in words) * sum(weights[w]**2 for w in target))
            score = numerator/denominator if denominator else 0
            if score >= 0.34:
                scored.append((score, eid, common))
        for _, eid, common in sorted(scored, reverse=True)[:2]:
            add(s, exhibits[eid], "semantic", "candidate", "語意候選：本段與此圖表的作者說明共享主題詞（" + ", ".join(sorted(common)[:6]) + "）。僅主題相近尚不足以確認解釋關係，請核對後加入。")
    studies = {}
    for e in exhibits.values():
        if e["kind"] == "figure":
            title, guide, limit = FIGURES[e["number"]]
            e["captionZh"] = f'圖 {e["number"]}．{title}'
            guides, limits = [guide], [limit]
        elif e["number"] in METRICS:
            title = f'{METRICS[e["number"]]}：兩組三次測量與組內時間效果'
            guides = ["每列是一組，T0／T1／T2 分別是前測、中測、後測。Mean ± SD 是平均數±標準差，不是平均數的信賴區間。", "對照 F、p 與 η² 讀取各組時間效果。組內有顯著進步，不等於兩組進步幅度有顯著差異；組別×時間效果須搭配混合模型表。"]
            limits = ["保留所有欄名及資料列；精確數值以完整原表為準，不從圖像猜測或補寫。"]
        elif e["number"] in MODELS:
            title = f'{MODELS[e["number"]]}：組別×時間的線性混合模型'
            guides = ["固定效應區一起對照 β（係數）、SE（標準誤）、95% CI、t 與 p；特別核對 Group × Time 的 T0→T1 和 T0→T2 兩列，不能混同 Group 單獨一列的效果。", "隨機效應區包含參與者截距、殘差、變異數、SD 及 ICC；模型配適區的邊際 R² 對應固定因子，條件 R² 對應整個模型。完整保留表下注記與公式。"]
            limits = ["係數需依作者的組別與時間編碼解釋；不能只讀截距或單一資料列就推定介入效果。"]
            if e["number"] == "5":
                limits.append("原表公式寫作 Inhibition+time…，未自行補入缺少的符號。")
            if e["number"] == "7":
                limits.append("原正文稱 T0→T1 未顯著，卻寫 p < 0.05；原表對應列為 t=0.65、p=0.518。兩處不一致，並列提示，不改寫作者原文。")
        elif e["number"] == "1":
            title = "錄影中的 12 種行為如何編碼"
            guides = ["由左到右對照 Code（代碼）、Behavior（行為名稱）、Description（操作定義）。LI／II 是教師相關互動；DP／CA／PB／EP 是討論、建立演算法、放積木、執行程式；AH／DA／DB 是求助及除錯；ET／SH／IB 是延伸、分享及無關行為。", "這是表 10 行為次數及圖 15 行為轉移節點的共同代碼字典；閱讀序列時先確認行為的操作定義。"]
            limits = ["表 1 不是成效比較；不能從編碼名稱推定次數或因果關係。"]
        else:
            title = "兩組三階段行為的次數與比例"
            guides = ["逐列對照 12 個行為代碼，再按前期／中期／後期比較兩組的次數與百分比。粗體及上標標示每階段前三項行為，依原表辨識。", "表 1 提供代碼定義；表 10 是頻率分布，圖 15 才呈現時間先後的行為轉移。"]
            limits = ["單一行為的比例不顯示事件先後順序；不同階段總次數不同，不能只比較原始次數。"]
        evidence_ids = [i for i in dict.fromkeys(e["explanationSegmentIds"] + [l["segmentId"] for l in links if l["exhibitId"] == e["id"] and l["confidence"] == "high"]) if i in segments and not segments[i].get("excluded") and segments[i]["kind"] == "body"]
        if e["kind"] == "figure" and e["number"] in {"11", "12", "13", "14"}:
            title += "。圖中兩組皆隨時間提高，I-PBRP 在後測呈現較高分數；是否有顯著組間差異須核對相應混合模型表。"
        if e["kind"] == "figure" and e["number"] == "15":
            title += "。作者描述前期兩組模式相近，後期 I-PBRP 的討論→程式建立→執行與分享／延伸較順暢；C-PBRP 出現較多求助及除錯循環。此解讀來源是正文，不是箭頭的因果證明。"
        if e["kind"] == "table" and e["number"] in METRICS:
            title += "。作者報告兩組在 12 週介入後均有顯著組內進步；本表不單獨證明兩組進步幅度不同。"
        if e["kind"] == "table" and e["number"] in MODELS:
            estimates = {"3": "β=1.27，p=0.008", "5": "β=0.03，p=0.005", "7": "β=0.31，p=0.003", "9": "β=0.64，t=2.16，p=0.032"}
            # CT/inhibition/working-memory/cognitive-flexibility numbers are
            # checked against the complete native table, never estimated in pixels.
            title += f'。作者報告 6 週的組間變化差異未顯著，12 週 I-PBRP 表現較佳；T0→T2 對應列為 {estimates[e["number"]]}。'
        studies[e["id"]] = {"summaryZh": title, "guideZh": guides, "limitsZh": limits, "sourceSegmentIds": evidence_ids, "status": "ai-draft"}
    result["exhibitCompanion"] = {"revision": REVISION, "links": links, "studies": studies}
    return result

def main():
    path = ROOT / "public/data/paper-01.json"
    paper = json.loads(path.read_text())
    pdf = ROOT / "public/papers/paper-01.pdf"
    if paper["id"] != "paper-01" or paper["sourceSha256"] != SOURCE_SHA or hashlib.sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("Only the verified original first paper may be changed")
    backup = ROOT / "content/paper-01-before-companion.json"
    if not backup.exists():
        atomic_json(backup, paper)
    updated = build(paper)
    manifest_path = ROOT / "public/figures/paper-01/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    env = os.environ.copy()
    skill_root = Path(os.environ.get("FIGURE_EXTRACTOR_SRC", str(Path.home() / ".codex/skills/figure-extractor/src"))).expanduser()
    for e in updated["exhibits"]:
        if e["kind"] != "figure":
            continue
        number = int(e["number"])
        bbox = [37, 433, 510.51, 582] if number == 12 else [37, 286, 510.51, 442] if number == 13 else e["bbox"][:]
        if bbox[1] < 45:
            bbox[1] = 45
        if bbox != e["bbox"] or "_companion.png" in e["imageUrl"]:
            name = f"fig{number}_p{e['page']:02d}_companion.png"
            output = ROOT / "public/figures/paper-01" / name
            if not output.exists():
                cli = shutil.which("figure-extractor")
                if cli:
                    command = [cli]
                elif importlib.util.find_spec("figure_extractor"):
                    command = [sys.executable, "-m", "figure_extractor"]
                elif skill_root.is_dir():
                    env["PYTHONPATH"] = str(skill_root)
                    command = [sys.executable, "-m", "figure_extractor"]
                else:
                    raise RuntimeError("Figure extractor CLI/module is required for new crops; set FIGURE_EXTRACTOR_SRC to the source directory. Existing images were not overwritten")
                subprocess.run(command + ["crop", str(pdf), "--page", str(e["page"]), "--bbox", ",".join(map(str,bbox)), "--out", str(output), "--dpi", "300"], env=env, check=True)
            e.update(bbox=bbox, imageUrl=f"/figures/paper-01/{name}", extractionStatus="manual-crop", extractionMethod="source-verified-300dpi-companion-crop")
            item = next(i for i in manifest["figures"] if i["label"] == e["label"])
            item.update(bbox=bbox, output=f"public/figures/paper-01/{name}", dpi=300, method=e["extractionMethod"], status="ok", quality_score=1.0, quality_reasons=[])
    validate_paper(updated, ROOT / "public")
    atomic_json(path, updated)
    atomic_json(manifest_path, manifest)
    library_path = ROOT / "public/data/manifest.json"
    library = json.loads(library_path.read_text())
    entry = next(e for e in library["papers"] if e["id"] == "paper-01")
    entry["bodySegmentCount"] = sum(not s.get("excluded") and s["kind"] != "caption" and s["id"] not in {e["captionSegmentId"] for e in updated["exhibits"]} for s in paper["segments"])
    atomic_json(library_path, library)
    counts = Counter((l["method"], l["confidence"]) for l in updated["exhibitCompanion"]["links"])
    print(json.dumps({"revision": REVISION, "recordsPreserved": len(paper["segments"]), "bodySteps": sum(not s.get("excluded") and s["kind"] != "caption" and s["id"] not in {e["captionSegmentId"] for e in updated["exhibits"]} for s in paper["segments"]), "links": {"/".join(k): v for k,v in counts.items()}, "studies": len(updated["exhibitCompanion"]["studies"])}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
