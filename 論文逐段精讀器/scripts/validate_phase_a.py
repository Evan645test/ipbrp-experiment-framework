#!/usr/bin/env python3
"""Validate Phase-A paper data, source identity, geometry, and review gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


VALID_KINDS = {"heading", "body", "caption"}
VALID_TRANSLATION_STATUS = {"untranslated", "ai-draft", "reviewed"}
VALID_REVIEW_STATUS = {"auto-generated", "needs-review", "reviewed", "published"}
VALID_EXHIBIT_KINDS = {"figure", "table"}
VALID_EXTRACTION_STATUS = {"ok", "manual-crop"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_paper(paper: Any, public_dir: Path, publication_gate: bool = False) -> dict[str, int]:
    require(isinstance(paper, dict), "paper must be a JSON object")
    paper_id = paper.get("id", "unknown")
    require(paper.get("schemaVersion") == "1.0.0", f"{paper_id}: unsupported schemaVersion")
    require(isinstance(paper.get("sourceSha256"), str) and len(paper["sourceSha256"]) == 64, f"{paper_id}: invalid sourceSha256")
    require(isinstance(paper.get("pageCount"), int) and paper["pageCount"] > 0, f"{paper_id}: invalid pageCount")
    require(paper.get("publicationStatus") in {"draft", "reviewed", "published"}, f"{paper_id}: invalid publicationStatus")

    pdf_url = paper.get("pdfUrl")
    require(isinstance(pdf_url, str) and pdf_url.startswith("/papers/") and ".." not in pdf_url, f"{paper_id}: unsafe pdfUrl")
    pdf_path = public_dir / pdf_url.lstrip("/")
    require(pdf_path.is_file(), f"{paper_id}: bundled PDF is missing")
    require(sha256_file(pdf_path) == paper["sourceSha256"], f"{paper_id}: bundled PDF hash mismatch")

    segments = paper.get("segments")
    require(isinstance(segments, list) and segments, f"{paper_id}: segments must be non-empty")
    ids: set[str] = set()
    counters = {"segments": len(segments), "included": 0, "excluded": 0, "reviewed": 0, "aiDraft": 0, "untranslated": 0, "exhibits": 0, "references": 0, "citations": 0, "referenceAbstracts": 0, "referenceTranslationsZh": 0, "referenceSummariesZh": 0}
    for index, segment in enumerate(segments, start=1):
        key = f"{paper_id}/segment-{index}"
        require(isinstance(segment, dict), f"{key}: segment must be an object")
        segment_id = segment.get("id")
        require(isinstance(segment_id, str) and segment_id, f"{key}: missing id")
        require(segment_id not in ids, f"{paper_id}: duplicate segment id {segment_id}")
        ids.add(segment_id)
        require(segment.get("order") == index, f"{segment_id}: order must be contiguous and one-based")
        require(segment.get("kind") in VALID_KINDS, f"{segment_id}: invalid kind")
        require(isinstance(segment.get("section"), str) and segment["section"].strip(), f"{segment_id}: empty section")
        require(isinstance(segment.get("sourceText"), str) and segment["sourceText"].strip(), f"{segment_id}: empty sourceText")
        require(segment.get("reviewStatus") in VALID_REVIEW_STATUS, f"{segment_id}: invalid reviewStatus")
        require(isinstance(segment.get("confidence"), (int, float)) and 0 <= segment["confidence"] <= 1, f"{segment_id}: confidence out of range")

        fragments = segment.get("fragments")
        require(isinstance(fragments, list) and fragments, f"{segment_id}: missing fragments")
        for fragment in fragments:
            require(isinstance(fragment, dict), f"{segment_id}: fragment must be an object")
            page = fragment.get("page")
            bbox = fragment.get("bbox")
            page_size = fragment.get("pageSize")
            require(isinstance(page, int) and 1 <= page <= paper["pageCount"], f"{segment_id}: page out of range")
            require(isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox), f"{segment_id}: invalid bbox")
            require(isinstance(page_size, list) and len(page_size) == 2 and all(isinstance(value, (int, float)) and value > 0 for value in page_size), f"{segment_id}: invalid pageSize")
            x0, y0, x1, y1 = bbox
            width, height = page_size
            require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, f"{segment_id}: bbox outside page")

        translation = segment.get("translation")
        require(isinstance(translation, dict), f"{segment_id}: missing translation")
        status = translation.get("status")
        require(status in VALID_TRANSLATION_STATUS, f"{segment_id}: invalid translation status")
        require(isinstance(translation.get("faithfulZh"), str), f"{segment_id}: faithfulZh must be a string")
        require(isinstance(translation.get("plainZh"), str), f"{segment_id}: plainZh must be a string")
        require(translation.get("reviewedAt") is None or isinstance(translation.get("reviewedAt"), str), f"{segment_id}: invalid reviewedAt")
        if status == "reviewed":
            require(translation["faithfulZh"].strip() and translation["plainZh"].strip(), f"{segment_id}: reviewed translation is incomplete")
            require(isinstance(translation.get("reviewedAt"), str) and translation["reviewedAt"].strip(), f"{segment_id}: reviewedAt is required")
        else:
            require(translation.get("reviewedAt") is None, f"{segment_id}: unreviewed translation cannot set reviewedAt")

        if segment.get("excluded") is True:
            counters["excluded"] += 1
        else:
            counters["included"] += 1
            counters[{"reviewed": "reviewed", "ai-draft": "aiDraft", "untranslated": "untranslated"}[status]] += 1
            if publication_gate:
                require(status == "reviewed" and segment.get("reviewStatus") in {"reviewed", "published"}, f"{segment_id}: publication gate requires human review")

    require(counters["included"] > 0, f"{paper_id}: at least one segment must be included")
    order_repair = paper.get("readingOrderRepair")
    if order_repair is not None:
        require(isinstance(order_repair, dict), f"{paper_id}: invalid reading order repair")
        require(isinstance(order_repair.get("revision"), str) and order_repair["revision"].strip(), f"{paper_id}: missing order repair revision")
        previous_ids = order_repair.get("previousSegmentIds")
        require(isinstance(previous_ids, list) and previous_ids and all(isinstance(value, str) and value for value in previous_ids), f"{paper_id}: invalid pre-repair segment IDs")
        require(len(previous_ids) == len(set(previous_ids)), f"{paper_id}: duplicate pre-repair segment IDs")
    for segment in segments:
        assessment = segment.get("paragraphAssessment")
        if assessment is None:
            continue
        require(isinstance(assessment, dict), f"{segment['id']}: invalid paragraphAssessment")
        require(assessment.get("status") in {"fragment", "needs-review"}, f"{segment['id']}: invalid paragraph completeness status")
        require(assessment.get("sourceTextSha256") == hashlib.sha256(segment["sourceText"].encode("utf-8")).hexdigest(), f"{segment['id']}: stale paragraph assessment")
        require(isinstance(assessment.get("reasons"), list) and assessment["reasons"] and all(isinstance(value, str) and value.strip() for value in assessment["reasons"]), f"{segment['id']}: missing paragraph assessment reasons")
        related = assessment.get("relatedSegmentIds")
        require(isinstance(related, list) and len(related) == len(set(related)) and all(value in ids and value != segment["id"] for value in related), f"{segment['id']}: invalid related paragraph fragments")

    exhibits = paper.get("exhibits", [])
    require(isinstance(exhibits, list), f"{paper_id}: exhibits must be a list")
    exhibit_ids: set[str] = set()
    for index, exhibit in enumerate(exhibits, start=1):
        key = f"{paper_id}/exhibit-{index}"
        require(isinstance(exhibit, dict), f"{key}: exhibit must be an object")
        exhibit_id = exhibit.get("id")
        require(isinstance(exhibit_id, str) and exhibit_id, f"{key}: missing id")
        require(exhibit_id not in exhibit_ids, f"{paper_id}: duplicate exhibit id {exhibit_id}")
        exhibit_ids.add(exhibit_id)
        require(exhibit.get("kind") in VALID_EXHIBIT_KINDS, f"{exhibit_id}: invalid kind")
        require(isinstance(exhibit.get("number"), str) and exhibit["number"], f"{exhibit_id}: missing number")
        require(isinstance(exhibit.get("label"), str) and exhibit["label"], f"{exhibit_id}: missing label")
        require(isinstance(exhibit.get("caption"), str) and exhibit["caption"], f"{exhibit_id}: missing caption")
        require(isinstance(exhibit.get("captionZh"), str), f"{exhibit_id}: captionZh must be a string")
        require(exhibit.get("extractionStatus") in VALID_EXTRACTION_STATUS, f"{exhibit_id}: invalid extractionStatus")
        require(isinstance(exhibit.get("extractionMethod"), str) and exhibit["extractionMethod"], f"{exhibit_id}: missing extractionMethod")
        page = exhibit.get("page")
        bbox = exhibit.get("bbox")
        page_size = exhibit.get("pageSize")
        require(isinstance(page, int) and 1 <= page <= paper["pageCount"], f"{exhibit_id}: page out of range")
        require(isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox), f"{exhibit_id}: invalid bbox")
        require(isinstance(page_size, list) and len(page_size) == 2 and all(isinstance(value, (int, float)) and value > 0 for value in page_size), f"{exhibit_id}: invalid pageSize")
        x0, y0, x1, y1 = bbox
        width, height = page_size
        require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, f"{exhibit_id}: bbox outside page")
        image_url = exhibit.get("imageUrl")
        require(isinstance(image_url, str) and image_url.startswith("/figures/") and ".." not in image_url, f"{exhibit_id}: unsafe imageUrl")
        require((public_dir / image_url.lstrip("/")).is_file(), f"{exhibit_id}: crop image is missing")
        caption_segment_id = exhibit.get("captionSegmentId")
        require(caption_segment_id is None or caption_segment_id in ids, f"{exhibit_id}: unknown captionSegmentId")
        explanation_ids = exhibit.get("explanationSegmentIds")
        require(isinstance(explanation_ids, list) and len(explanation_ids) == len(set(explanation_ids)), f"{exhibit_id}: invalid explanationSegmentIds")
        require(all(segment_id in ids for segment_id in explanation_ids), f"{exhibit_id}: unknown explanation segment")
        counters["exhibits"] += 1

    companion = paper.get("exhibitCompanion")
    if companion is not None:
        require(isinstance(companion, dict) and isinstance(companion.get("revision"), str), f"{paper_id}: invalid companion revision")
        by_id = {s["id"]: s for s in segments}
        captions = {e["captionSegmentId"] for e in exhibits}
        body_ids = {s["id"] for s in segments if not s.get("excluded") and not s.get("readingRole") and s["kind"] != "caption" and s["id"] not in captions}
        links = companion.get("links")
        require(isinstance(links, list), f"{paper_id}: invalid companion links")
        pairs = set()
        for link in links:
            require(isinstance(link, dict), f"{paper_id}: invalid companion link")
            pair = (link.get("segmentId"), link.get("exhibitId"))
            require(pair[0] in body_ids and pair[1] in exhibit_ids and pair not in pairs, f"{paper_id}: unknown or duplicate companion pair")
            pairs.add(pair)
            require(link.get("method") in {"explicit", "semantic"} and link.get("confidence") in {"high", "candidate"}, f"{pair}: invalid companion classification")
            require(isinstance(link.get("relationshipZh"), str) and link["relationshipZh"].strip(), f"{pair}: empty companion relationship")
            require(link.get("sourceTextSha256") == hashlib.sha256(by_id[pair[0]]["sourceText"].encode()).hexdigest(), f"{pair}: stale relationship source")
            require(isinstance(link.get("evidenceQuote"), str) and bool(link["evidenceQuote"]) and link["evidenceQuote"] in by_id[pair[0]]["sourceText"], f"{pair}: fabricated relationship evidence")
            require(isinstance(link.get("sourceSegmentIds"), list) and link["sourceSegmentIds"] and all(i in body_ids for i in link["sourceSegmentIds"]), f"{pair}: unknown companion evidence")
        studies = companion.get("studies")
        require(isinstance(studies, dict) and set(studies) == exhibit_ids, f"{paper_id}: incomplete exhibit studies")
        for key, study in studies.items():
            require(isinstance(study, dict) and study.get("status") == "ai-draft", f"{key}: companion cannot claim human review")
            require(isinstance(study.get("summaryZh"), str) and study["summaryZh"].strip(), f"{key}: missing study summary")
            for name in ("guideZh", "limitsZh"):
                require(isinstance(study.get(name), list) and study[name] and all(isinstance(t, str) and t.strip() for t in study[name]), f"{key}: missing study {name}")
            require(isinstance(study.get("sourceSegmentIds"), list) and all(i in body_ids for i in study["sourceSegmentIds"]), f"{key}: unknown study evidence")
        if publication_gate:
            require(False, f"{paper_id}: companion interpretations remain AI drafts and require human review")

    quality = paper.get("readingQuality")
    if quality is not None:
        require(isinstance(quality, dict) and isinstance(quality.get("revision"), str), f"{paper_id}: invalid reading quality")
        by_id = {s["id"]: s for s in segments}
        for segment in segments:
            require(segment.get("readingRole") in {None,"statement","appendix"}, f"{segment['id']}: invalid reading role")
        repairs = quality.get("explanationRepairs")
        require(isinstance(repairs,list), f"{paper_id}: missing explanation provenance")
        repair_ids = set()
        for repair in repairs:
            sid = repair.get("segmentId")
            require(sid in ids and sid not in repair_ids, f"{paper_id}: invalid explanation repair ID")
            repair_ids.add(sid)
            require(isinstance(repair.get("sourceText"),str) and repair["sourceText"].strip(), f"{sid}: missing explanation source")
            require(isinstance(repair.get("previousTranslation"),dict) and isinstance(repair.get("translation"),dict), f"{sid}: missing explanation versions")
            require(isinstance(repair["translation"].get("plainZh"),str) and repair["translation"]["plainZh"].strip(), f"{sid}: empty repaired explanation")
            if publication_gate:
                require(repair["sourceText"]==by_id[sid]["sourceText"] and repair["translation"]["plainZh"]==by_id[sid]["translation"]["plainZh"], f"{sid}: changed explanation must be rechecked")
        appendices = quality.get("appendices")
        require(isinstance(appendices,list), f"{paper_id}: missing complete appendices")
        appendix_ids = set()
        for appendix in appendices:
            exhibit=appendix.get("exhibit",{})
            aid=exhibit.get("id")
            require(isinstance(aid,str) and aid not in appendix_ids, f"{paper_id}: invalid appendix ID")
            appendix_ids.add(aid)
            require(exhibit.get("captionSegmentId") in ids, f"{aid}: missing appendix record")
            require(isinstance(exhibit.get("page"),int) and 1<=exhibit["page"]<=paper["pageCount"], f"{aid}: invalid appendix page")
            box=exhibit.get("bbox"); size=exhibit.get("pageSize")
            require(isinstance(box,list) and len(box)==4 and all(isinstance(v,(int,float)) for v in box) and isinstance(size,list) and len(size)==2, f"{aid}: invalid appendix geometry")
            require(0<=box[0]<box[2]<=size[0] and 0<=box[1]<box[3]<=size[1], f"{aid}: appendix outside page")
            url=exhibit.get("imageUrl")
            require(isinstance(url,str) and url.startswith("/figures/") and ".." not in url and (public_dir/url.lstrip("/")).is_file(), f"{aid}: missing or unsafe appendix image")
            require(isinstance(appendix.get("faithfulZh"),str) and appendix["faithfulZh"].strip() and isinstance(appendix.get("guideZh"),list) and appendix["guideZh"], f"{aid}: missing appendix explanation")
            require(isinstance(appendix.get("relatedSegmentIds"),list) and all(sid in ids for sid in appendix["relatedSegmentIds"]), f"{aid}: missing appendix sources")

    for segment in segments:
        related = segment.get("exhibitIds", [])
        require(isinstance(related, list) and len(related) == len(set(related)), f"{segment['id']}: invalid exhibitIds")
        require(all(exhibit_id in exhibit_ids for exhibit_id in related), f"{segment['id']}: unknown exhibit id")
        merged_target = segment.get("mergedIntoSegmentId")
        if merged_target is not None:
            require(merged_target in ids and merged_target != segment["id"], f"{segment['id']}: invalid merged target")
        mentions = segment.get("exhibitMentions", [])
        require(isinstance(mentions, list), f"{segment['id']}: invalid exhibit mentions")
        for mention in mentions:
            require(isinstance(mention, dict) and mention.get("exhibitId") in exhibit_ids, f"{segment['id']}: unknown inline exhibit")
            require(isinstance(mention.get("label"), str) and mention["label"], f"{segment['id']}: missing inline exhibit label")
            fragment = next((fragment for fragment in segment["fragments"] if fragment["page"] == mention.get("page")), None)
            require(fragment is not None, f"{segment['id']}: inline exhibit outside segment pages")
            box = mention.get("bbox")
            require(isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box), f"{segment['id']}: invalid inline exhibit bbox")
            width, height = fragment["pageSize"]
            require(0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height, f"{segment['id']}: inline exhibit outside page")
    for repair in paper.get("readingUnitRepairs", []):
        require(isinstance(repair, dict) and isinstance(repair.get("revision"), str), f"{paper_id}: invalid reading-unit repair")
        require(repair.get("targetId") in ids and isinstance(repair.get("absorbedIds"), list) and all(id in ids and id != repair["targetId"] for id in repair["absorbedIds"]), f"{paper_id}: invalid reading-unit repair IDs")
        previous = repair.get("previousSegments")
        require(isinstance(previous, list) and {s.get("id") for s in previous if isinstance(s, dict)} == {repair["targetId"], *repair["absorbedIds"]}, f"{paper_id}: incomplete repair provenance")

    references = paper.get("references", [])
    require(isinstance(references, list), f"{paper_id}: references must be a list")
    reference_ids: set[str] = set()
    for reference in references:
        require(isinstance(reference, dict), f"{paper_id}: reference must be an object")
        reference_id = reference.get("id")
        require(isinstance(reference_id, str) and reference_id and reference_id not in reference_ids, f"{paper_id}: invalid or duplicate reference id")
        reference_ids.add(reference_id)
        for field in ["label", "authors", "firstAuthor", "year", "title", "sourceText"]:
            require(isinstance(reference.get(field), str) and reference[field].strip(), f"{reference_id}: missing {field}")
        require(bool(re.fullmatch(r"\d{4}[a-z]?", reference["year"])), f"{reference_id}: invalid year")
        require(reference.get("extractionStatus") in {"needs-review", "reviewed"}, f"{reference_id}: invalid extractionStatus")
        require(reference.get("identityStatus") in {"not-checked", "verified", "title-mismatch"}, f"{reference_id}: invalid identityStatus")
        doi = reference.get("doi")
        require(doi is None or isinstance(doi, str) and bool(re.fullmatch(r"10\.\d{4,9}/\S+", doi)), f"{reference_id}: invalid DOI")
        resolution = reference.get("doiResolution")
        if resolution is not None:
            require(isinstance(resolution, dict) and resolution.get("method") == "title-author-year" and isinstance(resolution.get("sourceUrl"), str) and resolution["sourceUrl"].startswith("https://api.crossref.org/works?") and isinstance(resolution.get("checkedAt"), str), f"{reference_id}: invalid DOI resolution evidence")
            require("printedDoi" in reference and (reference["printedDoi"] is None or isinstance(reference["printedDoi"], str) and re.fullmatch(r"10\.\d{4,9}/\S+", reference["printedDoi"])), f"{reference_id}: resolved DOI must preserve printed DOI")
        fragments = reference.get("fragments")
        require(isinstance(fragments, list) and fragments, f"{reference_id}: missing source geometry")
        for fragment in fragments:
            require(isinstance(fragment, dict), f"{reference_id}: invalid fragment")
            page, bbox, size = fragment.get("page"), fragment.get("bbox"), fragment.get("pageSize")
            require(isinstance(page, int) and 1 <= page <= paper["pageCount"], f"{reference_id}: invalid page")
            require(isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, (int, float)) and math.isfinite(value) for value in bbox), f"{reference_id}: invalid bbox")
            require(isinstance(size, list) and len(size) == 2 and all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0 for value in size), f"{reference_id}: invalid pageSize")
            require(0 <= bbox[0] < bbox[2] <= size[0] and 0 <= bbox[1] < bbox[3] <= size[1], f"{reference_id}: bbox outside page")
        abstract = reference.get("abstract")
        require(isinstance(abstract, dict) and abstract.get("status") in {"available", "not-found", "not-checked"}, f"{reference_id}: invalid abstract")
        require(isinstance(abstract.get("originalText"), str) and isinstance(abstract.get("summaryZh"), str), f"{reference_id}: invalid abstract text")
        require(abstract.get("summaryMethod") in {None, "model-summary", "extractive-translation", "source-grounded"}, f"{reference_id}: invalid summaryMethod")
        require(len(abstract["originalText"].split()) <= 25, f"{reference_id}: source excerpt exceeds limit")
        faithful = abstract.get("faithfulZh", "")
        require(isinstance(faithful, str), f"{reference_id}: invalid faithful Abstract translation")
        if faithful:
            require(abstract["status"] == "available" and abstract.get("translationStatus") == "ai-draft" and re.fullmatch(r"[a-f0-9]{64}", abstract.get("translationSourceSha256", "")), f"{reference_id}: translation lacks source identity")
        require(abstract.get("sourceType") in {None, "crossref", "publisher", "author", "openalex", "semantic-scholar", "europe-pmc", "eric", "openaire", "doaj", "ebsco"}, f"{reference_id}: invalid abstract sourceType")
        require(isinstance(abstract.get("abstractOrigin", ""), str), f"{reference_id}: invalid Abstract origin")
        require(isinstance(abstract.get("retrievalReason", ""), str), f"{reference_id}: invalid retrieval reason")
        url = abstract.get("sourceUrl")
        require(url is None or isinstance(url, str) and url.startswith("https://"), f"{reference_id}: unsafe abstract source URL")
        require(abstract.get("checkedAt") is None or isinstance(abstract["checkedAt"], str), f"{reference_id}: invalid abstract checkedAt")
        if abstract["status"] == "available":
            require(abstract["originalText"].strip() and url and abstract.get("checkedAt"), f"{reference_id}: available abstract lacks source evidence")
            counters["referenceAbstracts"] += 1
        else:
            require(not abstract["originalText"] and not abstract["summaryZh"], f"{reference_id}: unavailable abstract cannot contain invented text")
        counters["references"] += 1
        counters["referenceSummariesZh"] += bool(abstract["summaryZh"])
        counters["referenceTranslationsZh"] += bool(faithful)

    citations = paper.get("citations", [])
    require(isinstance(citations, list), f"{paper_id}: citations must be a list")
    citation_ids: set[str] = set()
    segment_by_id = {segment["id"]: segment for segment in segments}
    for citation in citations:
        require(isinstance(citation, dict), f"{paper_id}: citation must be an object")
        citation_id = citation.get("id")
        require(isinstance(citation_id, str) and citation_id not in citation_ids, f"{paper_id}: invalid or duplicate citation id")
        citation_ids.add(citation_id)
        segment_id = citation.get("segmentId")
        require(segment_id in ids, f"{citation_id}: unknown segment")
        require(isinstance(citation.get("label"), str) and citation["label"], f"{citation_id}: missing label")
        context = citation.get("sourceContext")
        require(isinstance(context, str) and context and context in segment_by_id[segment_id]["sourceText"], f"{citation_id}: source context is not grounded in segment")
        linked = citation.get("referenceIds")
        require(isinstance(linked, list) and linked and len(linked) == len(set(linked)) and all(value in reference_ids for value in linked), f"{citation_id}: invalid referenceIds")
        require(citation.get("matchStatus") == ("matched" if len(linked) == 1 else "ambiguous"), f"{citation_id}: unsafe matchStatus")
        if "relationshipZh" in citation:
            require(citation["matchStatus"] == "matched" and isinstance(citation["relationshipZh"], str) and citation["relationshipZh"].strip(), f"{citation_id}: invalid relationshipZh")
        counters["citations"] += 1

    if publication_gate:
        require(paper.get("publicationStatus") in {"reviewed", "published"}, f"{paper_id}: publicationStatus is still draft")
    return counters


def parser() -> argparse.ArgumentParser:
    project = Path(__file__).resolve().parent.parent
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--data-dir", type=Path, default=project / "public" / "data")
    value.add_argument("--public-dir", type=Path, default=project / "public")
    value.add_argument("--publication-gate", action="store_true", help="Require every included segment to be human-reviewed.")
    return value


def main() -> int:
    args = parser().parse_args()
    manifest_path = args.data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schemaVersion") == "1.0.0", "manifest: unsupported schemaVersion")
    entries = manifest.get("papers")
    require(isinstance(entries, list) and entries, "manifest: papers must be non-empty")
    require(manifest.get("paperCount") == len(entries), "manifest: paperCount mismatch")
    require(len({entry.get("id") for entry in entries if isinstance(entry, dict)}) == len(entries), "manifest: duplicate paper id")

    total = {"papers": len(entries), "segments": 0, "included": 0, "excluded": 0, "reviewed": 0, "aiDraft": 0, "untranslated": 0, "exhibits": 0, "references": 0, "citations": 0, "referenceAbstracts": 0, "referenceTranslationsZh": 0, "referenceSummariesZh": 0}
    for entry in entries:
        require(isinstance(entry, dict), "manifest: each paper entry must be an object")
        paper_id = entry.get("id")
        data_url = entry.get("dataUrl")
        require(isinstance(paper_id, str) and paper_id, "manifest: paper id is required")
        require(data_url == f"/data/{paper_id}.json", f"{paper_id}: unexpected dataUrl")
        paper_path = args.public_dir / data_url.lstrip("/")
        require(paper_path.is_file(), f"{paper_id}: paper JSON is missing")
        paper = json.loads(paper_path.read_text(encoding="utf-8"))
        require(paper.get("id") == paper_id, f"{paper_id}: document id mismatch")
        require(paper.get("sourceSha256") == entry.get("sourceSha256"), f"{paper_id}: manifest hash mismatch")
        counts = validate_paper(paper, args.public_dir, args.publication_gate)
        require(entry.get("segmentCount") == counts["segments"], f"{paper_id}: manifest segmentCount mismatch")
        if "includedSegmentCount" in entry:
            require(entry["includedSegmentCount"] == counts["included"], f"{paper_id}: manifest includedSegmentCount mismatch")
        if "bodySegmentCount" in entry:
            captions = {e["captionSegmentId"] for e in paper.get("exhibits", [])}
            body_count = sum(not s.get("excluded") and not s.get("readingRole") and s["kind"] != "caption" and s["id"] not in captions for s in paper["segments"])
            require(entry["bodySegmentCount"] == body_count, f"{paper_id}: manifest bodySegmentCount mismatch")
        require(entry.get("pageCount") == paper.get("pageCount"), f"{paper_id}: manifest pageCount mismatch")
        for key, count in counts.items():
            total[key] += count

    print(json.dumps(total, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
