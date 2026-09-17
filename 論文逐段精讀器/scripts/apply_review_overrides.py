#!/usr/bin/env python3
"""Apply reviewed translation overrides without overwriting extracted geometry."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    project = Path(__file__).resolve().parent.parent
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--data-dir", type=Path, default=project / "public" / "data")
    value.add_argument(
        "--overrides",
        type=Path,
        default=project / "content" / "review-overrides.json",
    )
    return value


def require_string(value: Any, field: str, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}: {field} must be a non-empty string")
    return value.strip()


def main() -> int:
    args = parser().parse_args()
    overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
    if overrides.get("schemaVersion") != "1.0.0" or not isinstance(overrides.get("papers"), dict):
        raise ValueError("review overrides must use schemaVersion 1.0.0 and a papers object")

    applied = 0
    for paper_id, paper_overrides in overrides["papers"].items():
        path = args.data_dir / f"{paper_id}.json"
        if not path.is_file():
            raise ValueError(f"override references missing paper: {paper_id}")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["sourceSha256"] != paper_overrides.get("sourceSha256"):
            raise ValueError(f"{paper_id}: source PDF hash does not match override")
        segments = {segment["id"]: segment for segment in document["segments"]}
        segment_overrides = paper_overrides.get("segments")
        if not isinstance(segment_overrides, dict):
            raise ValueError(f"{paper_id}: segments must be an object")
        for segment_id, value in segment_overrides.items():
            if segment_id not in segments:
                raise ValueError(f"{paper_id}: override references missing segment {segment_id}")
            if not isinstance(value, dict):
                raise ValueError(f"{paper_id}/{segment_id}: override must be an object")
            segment = segments[segment_id]
            status = value.get("status", "ai-draft")
            if status not in {"ai-draft", "reviewed"}:
                raise ValueError(f"{paper_id}/{segment_id}: invalid translation status {status}")
            reviewed_at = value.get("reviewedAt")
            if status == "reviewed":
                reviewed_at = require_string(reviewed_at, "reviewedAt", segment_id)
            elif reviewed_at is not None:
                raise ValueError(f"{paper_id}/{segment_id}: AI drafts cannot set reviewedAt")
            segment["translation"] = {
                "faithfulZh": require_string(value.get("faithfulZh"), "faithfulZh", segment_id),
                "plainZh": require_string(value.get("plainZh"), "plainZh", segment_id),
                "status": status,
                "reviewedAt": reviewed_at,
                "generatedAt": require_string(value.get("generatedAt"), "generatedAt", segment_id),
                "generatedBy": require_string(value.get("generatedBy"), "generatedBy", segment_id),
            }
            segment["reviewStatus"] = "reviewed" if status == "reviewed" else "needs-review"
            applied += 1
        document["generatedAt"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"appliedTranslations": applied}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
