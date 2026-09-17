#!/usr/bin/env python3
"""Supplement missing source Abstracts with exact DOI records from Europe PMC."""
import html
import json
import re
import urllib.parse
from datetime import datetime, timezone

from build_references import PROJECT, atomic_json, clean_text
from fetch_database_abstracts import match_work, request_json


def main():
    refs = [r for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for r in json.loads(path.read_text())["references"]]
    metadata = json.loads((PROJECT / "content/reference-metadata-cache.json").read_text())
    publisher = json.loads((PROJECT / "content/reference-publisher-cache.json").read_text())
    cache_path = PROJECT / "content/reference-database-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    attempts_path = PROJECT / "content/reference-europe-pmc-attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    grouped = {}
    for reference in refs:
        doi = reference.get("doi")
        if not doi or reference.get("identityStatus") == "title-mismatch" or any(source.get(doi, {}).get("status") == "available" for source in [metadata, publisher, cache]) or attempts.get(doi, {}).get("status") == "not-found":
            continue
        grouped.setdefault(doi, []).append(reference)
    dois = sorted(grouped)
    for offset in range(0, len(dois), 25):
        batch = dois[offset:offset + 25]
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"query": " OR ".join('DOI:"' + doi.replace('"', '') + '"' for doi in batch), "format": "json", "resultType": "core", "pageSize": 100})
        try:
            response = request_json(url)
            records = response["resultList"]["result"]
            if response.get("hitCount", 0) > 100:
                raise ValueError("Europe PMC returned more records than the verified DOI batch allows")
            for doi in batch:
                matches = [r for r in records if (r.get("doi") or "").lower() == doi]
                result = {"status": "not-found", "sourceType": "europe-pmc", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "database-has-no-abstract"}
                for record in matches:
                    work = {"doi": "https://doi.org/" + record["doi"].lower(), "title": record.get("title", "")}
                    if not all(match_work(reference, work, metadata) for reference in grouped[doi]):
                        result.update({"status": "not-checked", "error": "Database record identity did not match the local bibliography"})
                        continue
                    original = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", record.get("abstractText") or "")))
                    if len(original) >= 40:
                        result = {"status": "available", "originalText": original, "sourceType": "europe-pmc", "sourceUrl": "https://europepmc.org/article/" + urllib.parse.quote(record["source"], safe="") + "/" + urllib.parse.quote(record["id"], safe=""), "metadataTitle": record["title"], "checkedAt": result["checkedAt"], "acquisitionMethod": "complete source abstractText field; no generated summary"}
                        cache[doi] = result
                        break
                attempts[doi] = {key: value for key, value in result.items() if key != "originalText"}
                print(f"{doi}: {result['status']}", flush=True)
            atomic_json(cache_path, cache)
            atomic_json(attempts_path, attempts)
        except (RuntimeError, ValueError, KeyError) as error:
            print(f"Europe PMC lookup failed: {error}; successful sources preserved.", flush=True)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
