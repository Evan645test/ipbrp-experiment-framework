#!/usr/bin/env python3
"""Build deterministic Phase-A paper data from born-digital PDFs.

The generated JSON is deliberately a review draft. It never marks inferred
reading order, paragraph boundaries, or translations as human-reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import fitz  # PyMuPDF; local prototype dependency only.
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "PyMuPDF is required for the local Phase-A prototype. "
        "Install it in an isolated environment before running this script."
    ) from exc


SCHEMA_VERSION = "1.0.0"
TERMINAL_PUNCTUATION = re.compile(r"[.!?‼⁇⁈⁉。！？][\]\)\}\"'’”]*$")
REFERENCE_HEADING = re.compile(r"^(references|bibliography)\s*$", re.IGNORECASE)
HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*(?:\.)?\s+.+|abstract|introduction|method(?:s|ology)?|results?|"
    r"discussion|conclusions?|limitations?|appendi(?:x|ces))$",
    re.IGNORECASE,
)
CAPTION_PATTERN = re.compile(r"^(?:fig(?:ure)?\.?|table)\s*\d+", re.IGNORECASE)
PAGE_NUMBER_PATTERN = re.compile(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?$", re.IGNORECASE)
INTRODUCTION_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)*\s*(?:\||\.)?\s*)?introduction\s*$", re.IGNORECASE)
FRONT_MATTER_PATTERN = re.compile(
    r"^(?:\*+\s*)?(?:contents lists available|journal homepage|original article|correspondence:|"
    r"corresponding author|contact\b|article history|received:|received\s+\d|accepted\s+\d|funding:|"
    r"keywords\b|published online:|submit your article|article views:|"
    r"view (?:related|crossmark)|citing articles:|to cite this article:|to link to this article:|"
    r"full terms & conditions|available online|https?://|issn:|\u00a9)",
    re.IGNORECASE,
)
AFFILIATION_PATTERN = re.compile(
    r"^[a-z]\s*(?:department|graduate institute|faculty|school|college|institute|university)\b",
    re.IGNORECASE,
)
AUTHOR_LINE_PATTERN = re.compile(
    r"^[A-Z][\w’'\-]+(?:\s+[A-Z][\w’'\-]+){1,3}\s+[a-z](?:\s*[,;*]|\s+[A-Z])"
)


@dataclass(frozen=True)
class TextBlock:
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    page_width: float
    page_height: float


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parent.parent
    return argparse.ArgumentParser(description=__doc__, add_help=False)


def argument_parser() -> argparse.ArgumentParser:
    project_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=project_dir.parent,
        help="Directory containing the authorized source PDFs.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=project_dir,
        help="Reader project directory.",
    )
    return parser


def normalize_text(raw: str) -> str:
    raw = re.sub(r"\u00ad\s*", "", raw)
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    text = lines[0]
    for line in lines[1:]:
        if text.endswith("-") and line[:1].islower():
            text = text[:-1] + line
        else:
            text += " " + line
    return re.sub(r"\s+", " ", text).strip()


def signature(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"\d+", "#", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:180]


def is_noise(block: TextBlock, repeated_margin_text: set[str]) -> bool:
    text = block.text.strip()
    if not text or len(text) == 1:
        return True
    if PAGE_NUMBER_PATTERN.fullmatch(text):
        return True
    near_margin = block.bbox[1] < 55 or block.bbox[3] > block.page_height - 45
    if near_margin and signature(text) in repeated_margin_text:
        return True
    lowered = text.lower()
    if near_margin and (
        "downloaded from" in lowered
        or "terms and conditions" in lowered
        or lowered.startswith("http")
        or lowered.startswith("doi:")
    ):
        return True
    return False


def block_order_key(block: TextBlock) -> tuple[int, float, float]:
    """Approximate scholarly reading order without discarding source geometry."""
    x0, y0, x1, _ = block.bbox
    width = x1 - x0
    page_mid = block.page_width / 2
    is_full_width = width >= block.page_width * 0.62 or (x0 < page_mid < x1)
    if is_full_width and y0 < block.page_height * 0.25:
        return (0, y0, x0)
    if x1 <= page_mid * 1.08:
        return (1, y0, x0)
    if x0 >= page_mid * 0.92:
        return (2, y0, x0)
    return (3, y0, x0)


def collect_blocks(document: fitz.Document) -> list[TextBlock]:
    all_blocks: list[TextBlock] = []
    margin_signatures: Counter[str] = Counter()
    for page_index, page in enumerate(document):
        for item in page.get_text("blocks", sort=False):
            if len(item) < 7 or item[6] != 0:
                continue
            text = normalize_text(str(item[4]))
            if not text:
                continue
            block = TextBlock(
                page=page_index + 1,
                bbox=(float(item[0]), float(item[1]), float(item[2]), float(item[3])),
                text=text,
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
            )
            all_blocks.append(block)
            if block.bbox[1] < 55 or block.bbox[3] > block.page_height - 45:
                margin_signatures[signature(text)] += 1

    repeated = {key for key, count in margin_signatures.items() if count >= 3}
    page_groups: dict[int, list[TextBlock]] = defaultdict(list)
    for block in all_blocks:
        if not is_noise(block, repeated):
            page_groups[block.page].append(block)

    ordered: list[TextBlock] = []
    for page_number in sorted(page_groups):
        ordered.extend(sorted(page_groups[page_number], key=block_order_key))
    return ordered


def classify(text: str) -> str:
    stripped = text.strip()
    if CAPTION_PATTERN.match(stripped):
        return "caption"
    if len(stripped) <= 140 and HEADING_PATTERN.match(stripped.rstrip(".:")):
        return "heading"
    return "body"


def is_front_matter(segment: dict[str, Any], intro_page: int) -> bool:
    text = segment["sourceText"].strip()
    page = segment["fragments"][0]["page"]
    if page > intro_page:
        return False
    if FRONT_MATTER_PATTERN.match(text):
        return True
    if AFFILIATION_PATTERN.match(text) or AUTHOR_LINE_PATTERN.match(text):
        return True
    if re.fullmatch(r"A\s+R\s+T\s+I\s+C\s+L\s+E\s+I\s+N\s+F\s+O", text, re.IGNORECASE):
        return True
    if re.fullmatch(r"A\s+B\s+S\s+T\s+R\s+A\s+C\s+T", text, re.IGNORECASE):
        return True
    if (
        segment["kind"] != "heading"
        and " | " in text
        and not TERMINAL_PUNCTUATION.search(text)
        and len(text) < 500
    ):
        return True
    return False


def curate_reading_scope(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Start at the abstract, then follow the main article from Introduction."""
    if not segments:
        return []
    intro_index = next(
        (index for index, segment in enumerate(segments) if INTRODUCTION_PATTERN.match(segment["sourceText"].strip())),
        None,
    )
    if intro_index is None:
        return segments

    intro_page = segments[intro_index]["fragments"][0]["page"]
    direct_abstract = [
        (index, segment)
        for index, segment in enumerate(segments)
        if segment["kind"] == "body"
        and re.match(r"^abstract\b", segment["sourceText"].strip(), re.IGNORECASE)
    ]
    abstract_index = direct_abstract[0][0] if direct_abstract else None
    abstract_segment: dict[str, Any] | None = direct_abstract[0][1] if direct_abstract else None
    if abstract_segment is None:
        marker_index = next(
            (
                index
                for index, segment in enumerate(segments)
                if re.fullmatch(
                    r"A\s+B\s+S\s+T\s+R\s+A\s+C\s+T",
                    segment["sourceText"].strip(),
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if marker_index is not None:
            marker_page = segments[marker_index]["fragments"][0]["page"]
            candidates = [
                segment
                for segment in segments[marker_index + 1 :]
                if segment["fragments"][0]["page"] == marker_page
                and segment["kind"] == "body"
                and len(segment["sourceText"]) >= 180
                and not FRONT_MATTER_PATTERN.match(segment["sourceText"].strip())
            ]
            if candidates:
                abstract_segment = max(candidates, key=lambda item: len(item["sourceText"]))
                abstract_index = segments.index(abstract_segment)

    if (
        abstract_segment is not None
        and abstract_index is not None
        and abstract_index < intro_index
        and not TERMINAL_PUNCTUATION.search(abstract_segment["sourceText"])
    ):
        for continuation in segments[abstract_index + 1 : intro_index]:
            if continuation["kind"] != "body" or is_front_matter(continuation, intro_page):
                continue
            abstract_segment["sourceText"] += " " + continuation["sourceText"]
            abstract_segment["fragments"].extend(continuation["fragments"])
            abstract_segment["reviewStatus"] = "needs-review"
            abstract_segment["confidence"] = min(abstract_segment["confidence"], 0.62)
            if TERMINAL_PUNCTUATION.search(continuation["sourceText"]):
                break

    main_segments = []
    for segment in segments[intro_index:]:
        if abstract_segment is not None and segment["id"] == abstract_segment["id"]:
            continue
        if is_front_matter(segment, intro_page):
            continue
        main_segments.append(segment)

    curated = ([abstract_segment] if abstract_segment is not None else []) + main_segments
    # Headings provide section context but are not reading passages. Keeping
    # them as next/previous steps makes a title look like a paragraph.
    curated = [segment for segment in curated if segment["kind"] != "heading"]
    if abstract_segment is not None:
        abstract_segment["section"] = "Abstract"
    for order, segment in enumerate(curated, start=1):
        segment["order"] = order
    return curated


def should_merge_across_page(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    if previous["kind"] != "body" or current["kind"] != "body":
        return False
    if current["fragments"][0]["page"] != previous["fragments"][-1]["page"] + 1:
        return False
    if TERMINAL_PUNCTUATION.search(previous["sourceText"]):
        return False
    first = current["sourceText"].lstrip()[:1]
    return bool(first and (first.islower() or first in ",;:)]"))


def stable_segment_id(paper_id: str, text: str, occurrence: int) -> str:
    digest = hashlib.sha1(re.sub(r"\s+", " ", text.lower()).encode("utf-8")).hexdigest()[:12]
    suffix = f"-{occurrence}" if occurrence > 1 else ""
    return f"{paper_id}-s-{digest}{suffix}"


def build_segments(blocks: Iterable[TextBlock], paper_id: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current_section = "Front matter"
    references_started = False

    for block in blocks:
        text = block.text
        if REFERENCE_HEADING.fullmatch(text.rstrip(".:")):
            references_started = True
        if references_started:
            continue
        kind = classify(text)
        if kind == "heading":
            current_section = text

        x0, y0, x1, y1 = block.bbox
        fragment = {
            "page": block.page,
            "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
            "pageSize": [round(block.page_width, 2), round(block.page_height, 2)],
        }
        draft = {
            "id": "",
            "order": 0,
            "section": current_section,
            "kind": kind,
            "sourceText": text,
            "fragments": [fragment],
            "translation": {
                "faithfulZh": "",
                "plainZh": "",
                "status": "untranslated",
                "reviewedAt": None,
            },
            "seenByDefault": False,
            "reviewStatus": "auto-generated",
            "confidence": 0.9 if kind in {"heading", "caption"} else 0.76,
        }
        if segments and should_merge_across_page(segments[-1], draft):
            segments[-1]["sourceText"] += " " + text
            segments[-1]["fragments"].append(fragment)
            segments[-1]["confidence"] = min(segments[-1]["confidence"], 0.62)
            segments[-1]["reviewStatus"] = "needs-review"
        else:
            segments.append(draft)

    occurrences: Counter[str] = Counter()
    for order, segment in enumerate(segments, start=1):
        key = hashlib.sha1(segment["sourceText"].lower().encode("utf-8")).hexdigest()
        occurrences[key] += 1
        segment["id"] = stable_segment_id(paper_id, segment["sourceText"], occurrences[key])
        segment["order"] = order
    return curate_reading_scope(segments)


def source_title(path: Path) -> str:
    return re.sub(r"^\d+\.\s*", "", path.stem).strip()


def paper_number(path: Path) -> int:
    match = re.match(r"^(\d+)\.", path.name)
    if not match:
        raise ValueError(f"PDF filename must begin with a numeric prefix: {path.name}")
    return int(match.group(1))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_year(document: fitz.Document) -> int | None:
    first_pages = " ".join(document[index].get_text("text") for index in range(min(2, len(document))))
    years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", first_pages)]
    plausible = [year for year in years if 1900 <= year <= datetime.now().year + 2]
    return max(plausible) if plausible else None


def build_paper(path: Path, output_dir: Path, public_pdf_dir: Path) -> dict[str, Any]:
    number = paper_number(path)
    paper_id = f"paper-{number:02d}"
    target_pdf = public_pdf_dir / f"{paper_id}.pdf"
    shutil.copy2(path, target_pdf)
    source_hash = sha256_file(path)

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise RuntimeError(f"Unable to open {path.name}: {exc}") from exc
    try:
        if document.needs_pass:
            raise RuntimeError(f"Password-protected PDF is not supported: {path.name}")
        blocks = collect_blocks(document)
        segments = build_segments(blocks, paper_id)
        if not segments:
            raise RuntimeError(f"No readable text segments were extracted from {path.name}")
        paper = {
            "schemaVersion": SCHEMA_VERSION,
            "id": paper_id,
            "number": number,
            "title": source_title(path),
            "year": detect_year(document),
            "sourceFileName": path.name,
            "sourceSha256": source_hash,
            "pdfUrl": f"/papers/{paper_id}.pdf",
            "pageCount": len(document),
            "language": "en",
            "readerLanguage": "zh-Hant",
            "publicationStatus": "draft",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "segments": segments,
        }
    finally:
        document.close()

    output_path = output_dir / f"{paper_id}.json"
    output_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "id": paper_id,
        "number": number,
        "title": paper["title"],
        "year": paper["year"],
        "pageCount": paper["pageCount"],
        "segmentCount": len(segments),
        "publicationStatus": "draft",
        "dataUrl": f"/data/{paper_id}.json",
        "pdfUrl": paper["pdfUrl"],
        "sourceSha256": source_hash,
    }


def main() -> int:
    args = argument_parser().parse_args()
    source_dir = args.source_dir.resolve()
    project_dir = args.project_dir.resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")

    pdfs = sorted(source_dir.glob("*.pdf"), key=paper_number)
    if not pdfs:
        raise SystemExit(f"No PDF files found in {source_dir}")
    expected = list(range(1, len(pdfs) + 1))
    actual = [paper_number(path) for path in pdfs]
    if actual != expected:
        raise SystemExit(f"Expected consecutive PDF prefixes {expected}, found {actual}")

    output_dir = project_dir / "public" / "data"
    public_pdf_dir = project_dir / "public" / "papers"
    output_dir.mkdir(parents=True, exist_ok=True)
    public_pdf_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = [build_paper(path, output_dir, public_pdf_dir) for path in pdfs]
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "paperCount": len(manifest_entries),
        "papers": manifest_entries,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "papers": len(manifest_entries),
                "segments": sum(item["segmentCount"] for item in manifest_entries),
                "output": str(output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
