#!/usr/bin/env python3
"""Validate and atomically import one curator-exported paper JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from validate_phase_a import validate_paper
from companion_metadata import reconcile_companion


def atomic_json_write(path: Path, value: object) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def parser() -> argparse.ArgumentParser:
    project = Path(__file__).resolve().parent.parent
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("file", type=Path, help="JSON file exported by the local curator.")
    value.add_argument("--project-dir", type=Path, default=project)
    value.add_argument("--mark-paper-reviewed", action="store_true", help="Set paper status to reviewed; fails unless every included segment is reviewed.")
    value.add_argument("--check-only", action="store_true", help="Validate the file and manifest match without writing anything.")
    return value


def main() -> int:
    args = parser().parse_args()
    project = args.project_dir.resolve()
    public_dir = project / "public"
    data_dir = public_dir / "data"
    incoming = json.loads(args.file.read_text(encoding="utf-8"))
    if not isinstance(incoming, dict) or not isinstance(incoming.get("id"), str):
        raise ValueError("curated file must contain a paper id")
    paper_id = incoming["id"]
    target = data_dir / f"{paper_id}.json"
    if not target.is_file():
        raise ValueError(f"unknown paper id: {paper_id}")
    current = json.loads(target.read_text(encoding="utf-8"))
    if incoming.get("sourceSha256") != current.get("sourceSha256"):
        raise ValueError("curated file belongs to a different PDF version")
    for immutable in ("schemaVersion", "id", "number", "title", "sourceFileName", "sourceSha256", "pdfUrl", "pageCount", "language", "readerLanguage"):
        if incoming.get(immutable) != current.get(immutable):
            raise ValueError(f"curated file changes immutable field: {immutable}")

    incoming["publicationStatus"] = "reviewed" if args.mark_paper_reviewed else "draft"
    incoming["generatedAt"] = datetime.now(timezone.utc).isoformat()
    # References are derived from the immutable PDF, not editable curator
    # content. Older exports must not erase the current bibliography index.
    incoming["references"] = current.get("references", [])
    incoming_segments = incoming.get("segments", [])
    source_by_segment = {segment["id"]: segment["sourceText"] for segment in incoming_segments
                         if isinstance(segment, dict) and isinstance(segment.get("id"), str) and isinstance(segment.get("sourceText"), str)} if isinstance(incoming_segments, list) else {}
    incoming["citations"] = [citation for citation in current.get("citations", [])
                             if citation.get("sourceContext") in source_by_segment.get(citation.get("segmentId"), "")]
    incoming = reconcile_companion(incoming, current)
    validate_paper(incoming, public_dir, publication_gate=args.mark_paper_reviewed)

    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((value for value in manifest.get("papers", []) if value.get("id") == paper_id), None)
    if entry is None:
        raise ValueError(f"manifest does not contain {paper_id}")
    entry["segmentCount"] = len(incoming["segments"])
    entry["publicationStatus"] = incoming["publicationStatus"]
    if incoming.get("exhibitCompanion"):
        captions = {e["captionSegmentId"] for e in incoming.get("exhibits", [])}
        entry["includedSegmentCount"] = sum(not s.get("excluded") for s in incoming["segments"])
        entry["bodySegmentCount"] = sum(not s.get("excluded") and not s.get("readingRole") and s["kind"] != "caption" and s["id"] not in captions for s in incoming["segments"])
    manifest["generatedAt"] = incoming["generatedAt"]

    if args.check_only:
        print(json.dumps({"validated": paper_id, "segments": len(incoming["segments"]), "publicationStatus": incoming["publicationStatus"]}, ensure_ascii=False))
        return 0

    atomic_json_write(target, incoming)
    atomic_json_write(manifest_path, manifest)
    print(json.dumps({"imported": paper_id, "segments": len(incoming["segments"]), "publicationStatus": incoming["publicationStatus"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"import error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
