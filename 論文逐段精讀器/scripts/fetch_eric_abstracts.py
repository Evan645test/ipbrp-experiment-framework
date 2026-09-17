#!/usr/bin/env python3
"""Retrieve identified education abstracts from ERIC; retain abstractor origin."""
import difflib
import argparse
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone

from build_references import PROJECT, atomic_json, clean_text
from fetch_database_abstracts import request_json
from resolve_reference_dois import normalize


def matches(reference, record, metadata):
    expected, actual = normalize(reference["title"]), normalize(record.get("title", ""))
    ratio = difflib.SequenceMatcher(None, expected, actual).ratio()
    deposited = normalize(metadata.get(reference.get("doi"), {}).get("metadataTitle", ""))
    deposited_match = reference.get("identityStatus") == "verified" and deposited and difflib.SequenceMatcher(None, deposited, actual).ratio() >= 0.95
    authors = record.get("author") or []
    if isinstance(authors, str):
        authors = [authors]
    first = normalize(authors[0].split(",", 1)[0]) if authors else ""
    source_author = normalize(reference["firstAuthor"])
    author_match = bool(first and (first == source_author or source_author.endswith(" " + first)))
    year = str(record.get("publicationdateyear", ""))
    return (ratio >= 0.93 or deposited_match) and author_match and bool(re.fullmatch(r"\d{4}", year)) and abs(int(reference["year"][:4]) - int(year)) <= 1


def lookup(reference, metadata):
    title = normalize(reference["title"])
    url = "https://api.ies.ed.gov/eric/?" + urllib.parse.urlencode({"search": 'title:"' + title + '"', "format": "json", "rows": 5})
    base = {"status": "not-found", "sourceType": "eric", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "no-exact-identity", "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest()}
    try:
        records = request_json(url)["response"]["docs"]
        exact = [record for record in records if matches(reference, record, metadata)]
        if len({record["id"] for record in exact}) != 1:
            return {**base, "reason": "ambiguous-identity" if exact else "no-exact-identity"}
        record = exact[0]
        original = clean_text(record.get("description") or "")
        if len(original) < 40:
            return {**base, "reason": "database-has-no-abstract"}
        abstractor = record.get("abstractor", "Unspecified")
        return {**base, "status": "available", "originalText": original, "metadataTitle": record["title"], "sourceUrl": "https://eric.ed.gov/?id=" + urllib.parse.quote(record["id"], safe=""), "abstractOrigin": abstractor, "acquisitionMethod": "complete ERIC Abstract field (description); abstractor origin retained; no AI summary"}
    except (RuntimeError, ValueError, KeyError) as error:
        return {**base, "status": "not-checked", "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--refresh", action="store_true", help="Retry absent sources; preserve every successful source.")
    parser.add_argument("--reference", action="append", help="Limit to a local reference ID; repeatable.")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 15:
        parser.error("--batch-size must be between 1 and 15")
    refs = [r for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for r in json.loads(path.read_text())["references"]]
    if args.reference:
        requested = set(args.reference)
        if not requested <= {reference["id"] for reference in refs}:
            parser.error("Every requested reference must be a local bibliography entry")
        refs = [reference for reference in refs if reference["id"] in requested]
    metadata = json.loads((PROJECT / "content/reference-metadata-cache.json").read_text())
    publisher = json.loads((PROJECT / "content/reference-publisher-cache.json").read_text())
    cache_path = PROJECT / "content/reference-database-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    attempts_path = PROJECT / "content/reference-eric-attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    pending = {}
    for reference in refs:
        key = reference.get("doi") or reference["id"]
        if reference["identityStatus"] == "title-mismatch" or any(source.get(key, {}).get("status") == "available" for source in [metadata, publisher, cache]) or (not args.refresh and attempts.get(key, {}).get("status") == "not-found"):
            continue
        pending.setdefault(key, reference)
    # Literal title phrases avoid Solr treating title punctuation as operators.
    # Batch retrieval is also substantially kinder to the public database.
    entries = list(pending.items())
    for offset in range(0, len(entries), args.batch_size):
        batch = entries[offset:offset + args.batch_size]
        query = " OR ".join('title:"' + normalize(reference["title"]) + '"' for _, reference in batch)
        url = "https://api.ies.ed.gov/eric/?" + urllib.parse.urlencode({"search": query, "format": "json", "rows": 250})
        try:
            response = request_json(url)["response"]
            if response["numFound"] > 250:
                raise ValueError("ERIC title batch exceeded the record limit; narrower identity queries required")
            records = response["docs"]
        except (RuntimeError, ValueError, KeyError) as error:
            for key, reference in batch:
                attempts[key] = {"status": "not-checked", "sourceType": "eric", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "error": str(error), "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest()}
            atomic_json(attempts_path, attempts)
            print(f"ERIC batch failed: {error}; previous sources preserved.", flush=True)
            return 1
        for key, reference in batch:
            result = {"status": "not-found", "sourceType": "eric", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "no-exact-identity", "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest()}
            exact = [record for record in records if matches(reference, record, metadata)]
            if len({record["id"] for record in exact}) == 1:
                record = exact[0]
                original = clean_text(record.get("description") or "")
                if len(original) >= 40:
                    result.update({"status": "available", "originalText": original, "metadataTitle": record["title"], "sourceUrl": "https://eric.ed.gov/?id=" + urllib.parse.quote(record["id"], safe=""), "abstractOrigin": record.get("abstractor", "Unspecified"), "acquisitionMethod": "complete ERIC Abstract field (description); no AI summary"})
                else:
                    result["reason"] = "database-has-no-abstract"
            elif exact:
                result["reason"] = "ambiguous-identity"
            if result["status"] == "available":
                cache[key] = result
                atomic_json(cache_path, cache)
            attempts[key] = {field: value for field, value in result.items() if field != "originalText"}
            atomic_json(attempts_path, attempts)
            print(f"{key}: {result['status']}", flush=True)
    return 1 if any(result.get("status") == "not-checked" for result in attempts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
