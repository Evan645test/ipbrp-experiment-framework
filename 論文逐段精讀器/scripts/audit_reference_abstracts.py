#!/usr/bin/env python3
"""Verify every embedded translation against its complete local source cache."""
import hashlib
import json
from datetime import datetime, timezone

from build_references import PROJECT, atomic_json


def optional(name):
    path = PROJECT / "content" / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main():
    metadata = optional("reference-metadata-cache.json")
    publisher = optional("reference-publisher-cache.json")
    database = optional("reference-database-cache.json")
    translations = optional("reference-abstract-translations.json")
    totals = {"references": 0, "translated": 0, "translationPending": 0, "identityConflict": 0, "sourceUnavailable": 0}
    rows, papers, source_counts = [], [], {}
    for path in sorted((PROJECT / "public/data").glob("paper-*.json")):
        paper = json.loads(path.read_text(encoding="utf-8"))
        counts = dict.fromkeys(totals, 0)
        for reference in paper.get("references", []):
            abstract = reference["abstract"]
            key = reference.get("doi") or reference["id"]
            source = next((cache[key] for cache in [publisher, metadata, database] if cache.get(key, {}).get("status") == "available"), {})
            faithful = abstract.get("faithfulZh", "")
            if faithful:
                sha = hashlib.sha256(source.get("originalText", "").encode("utf-8")).hexdigest()
                translation = translations.get(key, {})
                if not source.get("originalText") or abstract.get("translationSourceSha256") != sha or translation.get("sourceSha256") != sha or faithful != translation.get("faithfulZh") or abstract.get("sourceType") != source.get("sourceType") or abstract.get("sourceUrl") != source.get("sourceUrl"):
                    raise ValueError(f"{reference['id']}: embedded translation is not bound to the current complete source")
                status = "translated"
                kind = abstract["sourceType"]
                source_counts[kind] = source_counts.get(kind, 0) + 1
            elif reference["identityStatus"] == "title-mismatch":
                status = "identityConflict"
            elif abstract["status"] == "available":
                status = "translationPending"
            else:
                status = "sourceUnavailable"
                if not abstract.get("retrievalReason"):
                    raise ValueError(f"{reference['id']}: missing source must have an explicit reason")
            counts["references"] += 1
            counts[status] += 1
            rows.append({"paperId": paper["id"], "referenceId": reference["id"], "label": reference["label"], "title": reference["title"], "doi": reference.get("doi"), "status": status, "sourceType": abstract.get("sourceType"), "sourceUrl": abstract.get("sourceUrl"), "reason": abstract.get("retrievalReason", ""), "translationSourceSha256": abstract.get("translationSourceSha256", "")})
        papers.append({"paperId": paper["id"], **counts})
        for key, count in counts.items():
            totals[key] += count
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "scope": "all bibliography entries in the eight authorized local PDFs; repeated entries counted per paper", "totals": totals, "translationSources": source_counts, "papers": papers, "references": rows}
    atomic_json(PROJECT / "public/data/reference-abstract-audit.json", report)
    print(json.dumps({"totals": totals, "translationSources": source_counts, "papers": papers}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
