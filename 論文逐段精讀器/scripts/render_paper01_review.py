#!/usr/bin/env python3
"""Render every authorized paper-01 page with the current reading-unit boxes.

This creates review artifacts only; source PDF, reading JSON and browser state
are never modified. All geometry is copied from the current reader dataset.
"""
from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import fitz

from build_references import atomic_json

PROJECT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT / "public/review/paper-01"
COLORS = {
    "body": (0.12, 0.34, 0.83),
    "caption": (0.52, 0.23, 0.73),
    "review": (0.85, 0.40, 0.04),
    "excluded": (0.52, 0.55, 0.59),
    "exhibit": (0.0, 0.55, 0.52),
}
LEFT = 92
TOP = 64


def spaced_labels(labels: list[dict], height: float) -> None:
    labels.sort(key=lambda record: record["anchor"])
    previous = TOP - 5
    for label in labels:
        label["y"] = max(label["anchor"], previous + 12)
        previous = label["y"]
    ceiling = TOP + height - 4
    for label in reversed(labels):
        label["y"] = min(label["y"], ceiling)
        ceiling = label["y"] - 12


def main() -> int:
    data_path = PROJECT / "public/data/paper-01.json"
    data_bytes = data_path.read_bytes()
    paper = json.loads(data_bytes)
    pdf_path = PROJECT / "public" / paper["pdfUrl"].lstrip("/")
    pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if paper["id"] != "paper-01" or pdf_sha != paper["sourceSha256"]:
        raise ValueError("Paper identity/source PDF hash mismatch")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reading_number = {}
    excluded_number = {}
    companion_number = {}
    captions = {e["captionSegmentId"] for e in paper.get("exhibits", [])}
    for segment in paper["segments"]:
        companion_only = segment.get("readingRole") or paper.get("exhibitCompanion") and (segment["kind"] == "caption" or segment["id"] in captions)
        numbers = excluded_number if segment.get("excluded") else companion_number if companion_only else reading_number
        numbers[segment["id"]] = len(numbers) + 1
    manifest = {"paperId": paper["id"], "sourceSha256": pdf_sha,
                "dataSha256": hashlib.sha256(data_bytes).hexdigest(),
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "includedReadingUnits": len(reading_number), "excludedRecords": len(excluded_number),
                "companionUnits": len(companion_number),
                "pages": []}
    annotated = fitz.open()
    cards = []
    with fitz.open(pdf_path) as original:
        if len(original) != paper["pageCount"]:
            raise ValueError("Page count mismatch")
        for index, source_page in enumerate(original):
            number = index + 1
            width, height = source_page.rect.width, source_page.rect.height
            page = annotated.new_page(width=LEFT + width + 16, height=TOP + height + 16)
            page.show_pdf_page(fitz.Rect(LEFT, TOP, LEFT + width, TOP + height), original, index)
            page.insert_text((12, 20), f"PAPER-01 / PDF PAGE {number:02d} / READING-UNIT REVIEW", fontsize=11)
            page.insert_text((12, 36), "R = reader step   C = chart/statement/appendix only   X = excluded   E = exhibit", fontsize=9)
            page.insert_text((12, 50), "Blue: body   Purple: caption/exhibit unit   Gray dashed: excluded   Teal dashed: exhibit", fontsize=8)
            record = {"page": number, "image": f"page-{number:02d}.png", "readingUnits": [], "companionUnits": [], "excluded": [], "exhibits": []}
            for exhibit in paper.get("exhibits", []) + [a["exhibit"] for a in (paper.get("readingQuality") or {}).get("appendices", [])]:
                if exhibit["page"] != number:
                    continue
                x0, y0, x1, y1 = exhibit["bbox"]
                rect = fitz.Rect(x0 + LEFT, y0 + TOP, x1 + LEFT, y1 + TOP)
                page.draw_rect(rect, color=COLORS["exhibit"], width=0.8, dashes="[4 3] 0")
                page.insert_text((rect.x0 + 2, rect.y0 + 9), f"E: {exhibit['label']}", fontsize=7, color=COLORS["exhibit"])
                record["exhibits"].append({"id": exhibit["id"], "label": exhibit["label"], "bbox": exhibit["bbox"]})
            labels = []
            for segment in paper["segments"]:
                excluded = bool(segment.get("excluded"))
                assessment = segment.get("paragraphAssessment", {})
                category = "excluded" if excluded else "review" if assessment else segment["kind"]
                if category not in COLORS:
                    raise ValueError(f"Unsupported segment category: {category}")
                color = COLORS[category]
                companion_only = segment["id"] in companion_number
                label = f"X{excluded_number[segment['id']]:03d}" if excluded else f"C{companion_number[segment['id']]:03d}" if companion_only else f"R{reading_number[segment['id']]:03d}"
                if assessment and not excluded:
                    label += " !"
                fragments = [fragment for fragment in segment["fragments"] if fragment["page"] == number]
                if not fragments:
                    continue
                unit = {"id": segment["id"], "label": label, "kind": segment["kind"],
                        "section": segment["section"], "assessment": assessment or None,
                        "sourceText": segment["sourceText"], "boxes": [fragment["bbox"] for fragment in fragments]}
                record["excluded" if excluded else "companionUnits" if companion_only else "readingUnits"].append(unit)
                for fragment in fragments:
                    x0, y0, x1, y1 = fragment["bbox"]
                    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                        raise ValueError(f"Invalid bbox: {segment['id']}")
                    rect = fitz.Rect(x0 + LEFT, y0 + TOP, x1 + LEFT, y1 + TOP)
                    page.draw_rect(rect, color=color, width=0.8 if excluded else 1.0,
                                   dashes="[2 2] 0" if excluded else None)
                    labels.append({"anchor": rect.y0 + 6, "rect": rect, "text": label, "color": color})
            spaced_labels(labels, height)
            for label in labels:
                y = label["y"]
                page.insert_text((12, y), label["text"], fontsize=8, color=label["color"])
                page.draw_line(fitz.Point(49, y - 2), fitz.Point(label["rect"].x0 - 2, label["anchor"] - 2),
                               color=label["color"], width=0.45)
            page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False).save(OUTPUT / record["image"])
            manifest["pages"].append(record)
            rows = []
            for unit in record["readingUnits"]:
                annotation = "圖說" if unit["kind"] == "caption" else "正文單位"
                if unit["assessment"]:
                    annotation += "／待複核"
                rows.append(f'<li><code>{unit["label"]}</code> <span>{annotation}</span> {html.escape(unit["sourceText"][:160])}</li>')
            content = "".join(rows) if rows else "<li>本頁目前沒有納入正文閱讀的單位，仍請核對是否存在漏段。</li>"
            cards.append(f'''<section id="page-{number:02d}"><h2>PDF 第 {number} 頁</h2>
<p>{len(record['readingUnits'])} 個閱讀單位・{len(record['excluded'])} 筆排除紀錄・{len(record['exhibits'])} 個圖表框</p>
<a href="{record['image']}" target="_blank" rel="noopener"><img src="{record['image']}" alt="第一篇 PDF 第 {number} 頁段落框核對圖" loading="{'eager' if number < 3 else 'lazy'}" width="{round((LEFT+width+16)*2.2)}" height="{round((TOP+height+16)*2.2)}"></a>
<details><summary>查看本頁閱讀編號與原文開頭</summary><ul>{content}</ul></details></section>''')
    annotated.save(OUTPUT / "paper-01-paragraph-boxes.pdf", garbage=4, deflate=True)
    annotated.close()
    atomic_json(OUTPUT / "snapshot.json", manifest)
    navigation = " ".join(f'<a href="#page-{number:02d}">{number}</a>' for number in range(1, paper["pageCount"] + 1))
    document = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>第一篇・逐頁段落框核對</title>
<style>body{{font-family:system-ui,sans-serif;background:#f4f3ef;color:#182234;margin:0;line-height:1.7}}main{{max-width:1100px;margin:auto;padding:20px}}header,section{{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin:0 0 24px}}h1{{font-size:24px}}h2{{font-size:20px;margin:0}}img{{display:block;width:100%;height:auto;border:1px solid #ddd}}nav{{display:flex;flex-wrap:wrap;gap:8px}}nav a{{padding:3px 10px;background:#eef2f7;border-radius:4px}}li{{margin:10px 0}}code{{font-size:15px;font-weight:700}}a{{color:#164ca3}}.legend{{display:flex;flex-wrap:wrap;gap:16px}}.blue{{color:#1e56d4}}.purple{{color:#853bb9}}.orange{{color:#d9660a}}.gray{{color:#737d8c}}.teal{{color:#008c85}}section{{scroll-margin-top:16px}}</style>
<main><header><h1>第一篇・逐頁段落框核對</h1><p>這是目前閱讀資料的視覺化快照，不是已完成人工驗收的段落判定。共 {paper['pageCount']} 頁、{len(reading_number)} 個閱讀單位。點擊圖片可開啟高解析度原圖。</p>
<p class="legend"><span class="blue">藍框：正文閱讀單位</span><span class="purple">紫框：圖說／完整圖表閱讀單位</span><span class="orange">橘框：已標記待複核</span><span class="gray">灰虛線：已排除</span><span class="teal">青虛線：圖表區域</span></p>
<p>R001–R{len(reading_number):03d} 與讀者的切換順序一致；同一 R 編號跨頁出現，表示目前資料將它視為同一閱讀單位。C 為完整圖表伴讀紀錄，X 為排除紀錄，兩者不加入下一段流程。圖表框是輔助框，不表示圖表文字已被正確解析。</p>
<p>請檢查：一框是否對應一個原作者段落？有無框到標題、表格儲存格或公式？有無漏掉正文？編號是否符合閱讀順序？沒有框線的文字只是目前沒有段落紀錄，不能直接視為正確排除。</p>
<p><a href="paper-01-paragraph-boxes.pdf" target="_blank" rel="noopener">開啟／下載完整 21 頁核對 PDF</a> · <a href="snapshot.json">座標及原文快照</a></p><nav aria-label="頁碼">{navigation}</nav></header>{''.join(cards)}</main></html>'''
    (OUTPUT / "index.html").write_text(document, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "pages": len(manifest["pages"]), "readingUnits": len(reading_number)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
