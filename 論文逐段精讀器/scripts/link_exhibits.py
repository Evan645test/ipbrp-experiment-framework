#!/usr/bin/env python3
"""Verify figure crops and link exhibits to captions and explanatory passages."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any


MANUAL_CROPS: dict[tuple[str, str, int], list[float]] = {
    ("paper-02", "Table 1", 7): [305, 44, 552, 548],
    ("paper-03", "Figure 4", 10): [150, 45, 393, 285],
    ("paper-03", "Figure 6", 11): [150, 462, 393, 610],
    ("paper-03", "Table 1", 14): [155, 45, 393, 220],
    ("paper-03", "Table 4", 15): [50, 120, 393, 220],
    ("paper-07", "Figure 1", 4): [45, 430, 550, 735],
    ("paper-07", "Figure 2", 5): [45, 145, 550, 735],
    ("paper-07", "Figure 3", 6): [45, 360, 550, 735],
    ("paper-07", "Table 1", 7): [43.35, 44.74, 554.06, 365],
    ("paper-07", "Figure 4", 8): [45, 34, 550, 275],
    ("paper-07", "Figure 5", 8): [45, 285, 550, 600],
    ("paper-07", "Figure 8", 13): [45, 325, 550, 540],
}

MANUAL_ADDITIONS: dict[str, list[dict[str, Any]]] = {
    "paper-08": [
        {
            "label": "Figure 8",
            "kind": "figure",
            "number": "8",
            "page": 11,
            "caption": "FIGURE 8 | The behavioural transition diagram of the experimental group.",
            "captionZh": "圖 8｜實驗組的行為轉移圖。",
            "bbox": [45, 390, 550, 520],
            "output": "public/figures/paper-08/fig8_p11.png",
            "explanationSegmentIds": ["paper-08-s-622299feae2d"],
        },
        {
            "label": "Figure 9",
            "kind": "figure",
            "number": "9",
            "page": 11,
            "caption": "FIGURE 9 | The behavioural transition diagram of the control group.",
            "captionZh": "圖 9｜控制組的行為轉移圖。",
            "bbox": [45, 532, 550, 653],
            "output": "public/figures/paper-08/fig9_p11.png",
            "explanationSegmentIds": ["paper-08-s-622299feae2d"],
        },
    ]
}

REFERENCE_PATTERN = re.compile(
    r"\b(?P<kind>fig(?:ure)?s?|tables?)\.?\s*"
    r"(?P<numbers>\d+(?:\s*(?:,|and|&|–|—|-)\s*\d+)*)",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def reference_keys(text: str) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for match in REFERENCE_PATTERN.finditer(text):
        kind = "table" if match.group("kind").casefold().startswith("table") else "figure"
        numbers = [int(value) for value in re.findall(r"\d+", match.group("numbers"))]
        if not numbers:
            continue
        if re.search(r"[–—-]", match.group("numbers")) and len(numbers) == 2:
            start, end = sorted(numbers)
            numbers = list(range(start, end + 1)) if end - start <= 20 else numbers
        keys.update((kind, str(number)) for number in numbers)
    return keys


def page_size_for(paper: dict[str, Any], page: int) -> list[float]:
    for segment in paper["segments"]:
        for fragment in segment["fragments"]:
            if fragment["page"] == page:
                return fragment["pageSize"]
    raise ValueError(f"{paper['id']}: page {page} has no known page size")


def find_caption_segment(
    paper: dict[str, Any], exhibit: dict[str, Any]
) -> dict[str, Any] | None:
    target = normalize_text(exhibit["caption"])
    candidates: list[tuple[float, dict[str, Any]]] = []
    key = (exhibit["kind"], str(exhibit["number"]))
    for segment in paper["segments"]:
        pages = {fragment["page"] for fragment in segment["fragments"]}
        if exhibit["page"] not in pages or key not in reference_keys(segment["sourceText"]):
            continue
        candidate = normalize_text(segment["sourceText"])
        similarity = difflib.SequenceMatcher(None, target, candidate).ratio()
        prefix_bonus = 0.2 if candidate.startswith(target) or target.startswith(candidate) else 0
        candidates.append((similarity + prefix_bonus, segment))
    if not candidates:
        return None
    score, segment = max(candidates, key=lambda item: item[0])
    return segment if score >= 0.55 else None


def manifest_entry_from_addition(addition: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": addition["label"],
        "kind": addition["kind"],
        "number": addition["number"],
        "page": addition["page"],
        "caption": addition["caption"],
        "bbox": addition["bbox"],
        "column_layout": "multi",
        "spans_columns": True,
        "referenced_in_body": 1,
        "suggested_tier": "A",
        "method": "manual-verified-crop",
        "dpi": 180,
        "status": "ok",
        "quality_score": 1.0,
        "quality_reasons": [],
        "output": addition["output"],
    }


def refresh_counts(manifest: dict[str, Any]) -> None:
    figures = manifest["figures"]
    manifest["counts"] = {
        "total": len(figures),
        "rendered": sum(item["status"] in {"ok", "suspect"} for item in figures),
        "skipped_by_tier": 0,
        "ok": sum(item["status"] == "ok" for item in figures),
        "suspect": sum(item["status"] == "suspect" for item in figures),
        "failed": sum(item["status"] == "failed" for item in figures),
        "figures": sum(item["kind"] == "figure" for item in figures),
        "tables": sum(item["kind"] == "table" for item in figures),
    }


def process_paper(project: Path, paper_id: str) -> dict[str, int]:
    data_path = project / "public" / "data" / f"{paper_id}.json"
    manifest_path = project / "public" / "figures" / paper_id / "manifest.json"
    paper = json.loads(data_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    manual_keys: set[tuple[str, int]] = set()
    for item in manifest["figures"]:
        crop_key = (paper_id, item["label"], item["page"])
        if crop_key in MANUAL_CROPS:
            item.update(
                bbox=MANUAL_CROPS[crop_key],
                method="manual-verified-crop",
                status="ok",
                quality_score=1.0,
                quality_reasons=[],
            )
            manual_keys.add((item["label"], item["page"]))

    additions = MANUAL_ADDITIONS.get(paper_id, [])
    existing = {(item["label"], item["page"]) for item in manifest["figures"]}
    for addition in additions:
        key = (addition["label"], addition["page"])
        if key not in existing:
            manifest["figures"].append(manifest_entry_from_addition(addition))
        manual_keys.add(key)

    unresolved = [item["label"] for item in manifest["figures"] if item["status"] != "ok"]
    if unresolved:
        raise ValueError(f"{paper_id}: unresolved extraction status for {', '.join(unresolved)}")
    refresh_counts(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    segment_by_id = {segment["id"]: segment for segment in paper["segments"]}
    for segment in paper["segments"]:
        segment.pop("exhibitIds", None)

    addition_by_key = {
        (addition["label"], addition["page"]): addition for addition in additions
    }
    exhibits: list[dict[str, Any]] = []
    linked_explanations = 0
    for item in sorted(
        manifest["figures"], key=lambda value: (value["page"], value["kind"], int(value["number"]))
    ):
        image_path = project / item["output"]
        if not image_path.is_file() or image_path.stat().st_size == 0:
            raise ValueError(f"{paper_id}: missing rendered crop {item['output']}")
        caption_segment = find_caption_segment(paper, item)
        key = (item["kind"], str(item["number"]))
        explanation_ids = [
            segment["id"]
            for segment in paper["segments"]
            if segment["id"] != (caption_segment or {}).get("id")
            and key in reference_keys(segment["sourceText"])
        ]
        addition = addition_by_key.get((item["label"], item["page"]))
        if addition:
            for segment_id in addition.get("explanationSegmentIds", []):
                if segment_id not in segment_by_id:
                    raise ValueError(f"{paper_id}: unknown manual explanation segment {segment_id}")
                if segment_id not in explanation_ids:
                    explanation_ids.append(segment_id)

        exhibit_id = f"{paper_id}-{item['kind']}-{item['number']}"
        caption_zh = addition.get("captionZh", "") if addition else ""
        if caption_segment:
            caption_zh = caption_segment["translation"]["faithfulZh"] or caption_zh
        exhibit = {
            "id": exhibit_id,
            "label": item["label"],
            "kind": item["kind"],
            "number": str(item["number"]),
            "page": item["page"],
            "caption": item["caption"],
            "captionZh": caption_zh,
            "bbox": item["bbox"],
            "pageSize": page_size_for(paper, item["page"]),
            "imageUrl": "/" + str(image_path.relative_to(project / "public")),
            "extractionStatus": (
                "manual-crop" if (item["label"], item["page"]) in manual_keys else "ok"
            ),
            "extractionMethod": item["method"],
            "captionSegmentId": caption_segment["id"] if caption_segment else None,
            "explanationSegmentIds": explanation_ids,
        }
        exhibits.append(exhibit)
        relation_ids = explanation_ids + ([caption_segment["id"]] if caption_segment else [])
        for segment_id in relation_ids:
            segment = segment_by_id[segment_id]
            segment.setdefault("exhibitIds", [])
            if exhibit_id not in segment["exhibitIds"]:
                segment["exhibitIds"].append(exhibit_id)
        linked_explanations += len(explanation_ids)

    paper["exhibits"] = exhibits
    data_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "exhibits": len(exhibits),
        "manualCrops": len(manual_keys),
        "explanationLinks": linked_explanations,
        "withoutExplanation": sum(not item["explanationSegmentIds"] for item in exhibits),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root containing public/data and public/figures.",
    )
    return value


def main() -> int:
    args = parser().parse_args()
    totals = {"papers": 0, "exhibits": 0, "manualCrops": 0, "explanationLinks": 0, "withoutExplanation": 0}
    for data_path in sorted((args.project / "public" / "data").glob("paper-*.json")):
        counts = process_paper(args.project, data_path.stem)
        totals["papers"] += 1
        for key, value in counts.items():
            totals[key] += value
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
