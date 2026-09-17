#!/usr/bin/env python3
"""Cache complete, identity-checked abstracts deposited in DOAJ."""
import argparse
import concurrent.futures
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone

from build_references import PROJECT, atomic_json, clean_text
from fetch_database_abstracts import match_work, request_json
from resolve_reference_dois import normalize

BASE = "https://doaj.org/api/"


def as_work(record):
    bib = record.get("bibjson", {})
    dois = {str(item.get("id", "")).removeprefix("https://doi.org/").lower() for item in bib.get("identifier", []) if item.get("type") == "doi"}
    year = str(bib.get("year", ""))
    return {"doi": next(iter(dois)) if len(dois) == 1 else "", "title": bib.get("title", ""), "publication_year": int(year) if re.fullmatch(r"\d{4}", year) else None, "authorships": [{"author": {"display_name": item.get("name", "")}} for item in bib.get("author", [])]}


def lookup(reference, metadata):
    if reference.get("doi"):
        # Both bare DOIs and https://doi.org identifiers occur in DOAJ deposits.
        values = [reference["doi"], "https://doi.org/" + reference["doi"]]
        query = " OR ".join('bibjson.identifier.id:"' + value.replace('"', '\\"') + '"' for value in values)
    else:
        query = 'bibjson.title:"' + normalize(reference["title"]) + '"'
    url = BASE + "search/articles/" + urllib.parse.quote(query, safe="") + "?pageSize=100"
    base = {"status": "not-found", "sourceType": "doaj", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest(), "reason": "no-exact-identity"}
    try:
        response = request_json(url)
        records = response["results"]
        if int(response["total"]) > len(records):
            raise ValueError("DOAJ query exceeded the record limit; narrower identity query required")
        matched = [record for record in records if match_work(reference, as_work(record), metadata)]
        if len({record["id"] for record in matched}) != 1:
            return {**base, "reason": "ambiguous-identity" if matched else "no-exact-identity"}
        record = matched[0]
        text = clean_text(record["bibjson"].get("abstract", ""))
        if len(text) < 40:
            return {**base, "reason": "database-has-no-abstract"}
        if re.search(r"[\u4e00-\u9fff]", text) or re.search(r"(?:\.\.\.|…)\s*$", text):
            raise ValueError("DOAJ source is not a complete English Abstract")
        return {**base, "status": "available", "originalText": text, "metadataTitle": record["bibjson"]["title"], "sourceUrl": "https://doaj.org/article/" + urllib.parse.quote(record["id"], safe=""), "databaseId": record["id"], "acquisitionMethod": "complete deposited bibjson.abstract field; DOI/title or title/author/year checked; no AI summary"}
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        return {**base, "status": "not-checked", "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    refs = [r for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for r in json.loads(path.read_text())["references"]]
    sources = [json.loads((PROJECT / "content" / name).read_text()) for name in ["reference-metadata-cache.json", "reference-publisher-cache.json"]]
    cache_path = PROJECT / "content/reference-database-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    attempts_path = PROJECT / "content/reference-doaj-attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    pending = {}
    for reference in refs:
        key = reference.get("doi") or reference["id"]
        previous = attempts.get(key, {})
        if reference["identityStatus"] == "title-mismatch" or any(source.get(key, {}).get("status") == "available" for source in [*sources, cache]):
            continue
        if previous and not (args.retry_errors and previous.get("status") == "not-checked"):
            continue
        pending.setdefault(key, reference)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(lookup, reference, sources[0]): key for key, reference in pending.items()}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            key = futures[future]
            result = future.result()
            if result["status"] == "available" and cache.get(key, {}).get("status") != "available":
                cache[key] = result
                atomic_json(cache_path, cache)
            attempts[key] = {field: value for field, value in result.items() if field != "originalText"}
            atomic_json(attempts_path, attempts)
            print(f"{index}/{len(pending)} {key}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    return 1 if any(result.get("status") == "not-checked" for result in attempts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
