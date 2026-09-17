#!/usr/bin/env python3
"""Source-bound, additive single-column order repair for paper-01 only."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import fitz

from build_references import atomic_json, citation_index
from extract_phase_a import build_segments, collect_blocks, sha256_file

PROJECT = Path(__file__).resolve().parent.parent
SOURCE_SHA = "f115fdd76360d2b81f11162f81a419d30c973b58bdeb13a4b504a1f1a63a3ca1"
REVISION = "paper-01-single-column-v1"


def position(segment: dict) -> tuple:
    fragment = segment["fragments"][0]
    return fragment["page"], fragment["bbox"][1], fragment["bbox"][0]


def repair(paper: dict, pdf: Path, overrides: dict) -> tuple[dict, dict]:
    if paper["id"] != "paper-01" or paper["sourceSha256"] != SOURCE_SHA or sha256_file(pdf) != SOURCE_SHA:
        raise ValueError("Repair is authorized only for the verified paper-01 PDF")
    if overrides["sourceSha256"] != SOURCE_SHA:
        raise ValueError("Translation source binding does not match")
    with fitz.open(pdf) as document:
        # This paper's main text has been visually checked as single-column.
        # Do not reuse this rule for unverified or multi-column papers.
        blocks = sorted(collect_blocks(document), key=lambda b: (b.page, b.bbox[1], b.bbox[0]))
        expected = build_segments(blocks, paper["id"])
    expected_by_id = {segment["id"]: segment for segment in expected}
    result = copy.deepcopy(paper)
    previous_ids = [segment["id"] for segment in paper["segments"]]
    existing = {segment["id"]: segment for segment in result["segments"]}
    additions = [segment for segment in expected if segment["id"] not in existing]
    if {segment["id"] for segment in additions} - set(overrides["segments"]):
        raise ValueError("Unexpected missing paragraphs; refuse to add untranslated material")
    for segment in additions:
        value = overrides["segments"][segment["id"]]
        if segment["sourceText"] != value["sourceText"]:
            raise ValueError("Recovered source paragraph differs from translation source")
        segment["translation"] = value["translation"]
        segment["reviewStatus"] = "needs-review"
        result["segments"].append(segment)
    outside = []
    for segment in result["segments"]:
        current = expected_by_id.get(segment["id"])
        if current is not None:
            # Keep local translations, IDs, original text, geometry and exclusions.
            if segment["reviewStatus"] not in {"reviewed", "published"}:
                segment["section"] = current["section"]
        else:
            # Never delete existing records. Only the known bibliography leak
            # may be removed from navigation by this one-paper repair.
            if segment["id"] != "paper-01-s-fb4b491173bb":
                raise ValueError("Unexpected unmatched segment; manual review required")
            segment["excluded"] = True
            outside.append(segment["id"])
    result["segments"].sort(key=position)
    for order, segment in enumerate(result["segments"], 1):
        segment["order"] = order
    result.setdefault("readingOrderRepair", {"revision": REVISION, "previousSegmentIds": previous_ids})
    # Add only newly recovered citations, preserving existing relationship edits.
    indexed_ids = {citation["id"] for citation in result.get("citations", [])}
    for citation in citation_index({"segments": additions}, result.get("references", [])):
        if citation["id"] not in indexed_ids:
            result.setdefault("citations", []).append(citation)
    segment_orders = {segment["id"]: segment["order"] for segment in result["segments"]}
    result.get("citations", []).sort(key=lambda c: (segment_orders[c["segmentId"]], int(c["id"].rsplit("-", 1)[1])))
    audit = {"paperId": paper["id"], "sourceSha256": SOURCE_SHA, "revision": REVISION,
             "addedSegmentIds": [segment["id"] for segment in additions], "excludedBibliographyIds": outside,
             "totalRecords": len(result["segments"]),
             "includedReadingUnits": sum(not segment.get("excluded") for segment in result["segments"])}
    return result, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Update paper-01 and only its manifest entry")
    args = parser.parse_args()
    path = PROJECT / "public/data/paper-01.json"
    original = json.loads(path.read_text())
    overrides = json.loads((PROJECT / "content/paper-01-order-repair.json").read_text())
    repaired, audit = repair(original, PROJECT / "public/papers/paper-01.pdf", overrides)
    manifest_path = PROJECT / "public/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(entry for entry in manifest["papers"] if entry["id"] == "paper-01")
    entry["segmentCount"] = audit["totalRecords"]
    entry["includedSegmentCount"] = audit["includedReadingUnits"]
    if args.apply:
        backup = PROJECT / "content/paper-01-before-order-repair.json"
        if not backup.exists():
            atomic_json(backup, {"paper": original, "manifestEntry": next(e for e in json.loads(manifest_path.read_text())["papers"] if e["id"] == "paper-01")})
        atomic_json(path, repaired)
        atomic_json(manifest_path, manifest)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
