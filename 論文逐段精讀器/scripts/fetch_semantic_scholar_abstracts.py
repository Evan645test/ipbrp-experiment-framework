#!/usr/bin/env python3
"""Read only original Abstract fields from Semantic Scholar, never its TLDR."""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from build_references import PROJECT, HTTPS_CONTEXT, atomic_json, clean_text
from fetch_database_abstracts import match_work

FIELDS = "title,authors,year,abstract,externalIds,url"
BASE = "https://api.semanticscholar.org/graph/v1/paper/"


def request_json(url, body=None):
    error_message = "Request failed"
    for attempt in range(3):
        try:
            headers = {"User-Agent": "PaperFocusReader/1.0 (local original Abstract lookup)", "Accept": "application/json"}
            data = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(body).encode()
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, context=HTTPS_CONTEXT, timeout=30) as response:
                return json.load(response)
        except (OSError, ValueError) as error:
            error_message = str(error)
            if isinstance(error, urllib.error.HTTPError):
                if error.code not in {408, 429, 500, 502, 503, 504}:
                    break
                retry = error.headers.get("Retry-After", "")
                if retry.isdigit() and int(retry) > 30:
                    break
                pause = int(retry) if retry.isdigit() else 5 * (attempt + 1)
            else:
                pause = attempt + 1
            if attempt < 2:
                time.sleep(pause)
    raise RuntimeError(error_message)


def as_work(record):
    return {"title": record.get("title", ""), "doi": "https://doi.org/" + (record.get("externalIds", {}).get("DOI") or "").lower(), "publication_year": record.get("year"), "authorships": [{"author": {"display_name": author.get("name", "")}} for author in record.get("authors", [])]}


def source_record(record):
    original = clean_text(record.get("abstract") or "")
    if original and (len(original) < 40 or len(original) > 50000):
        raise ValueError("Database Abstract is incomplete or exceeds the size limit")
    return {"status": "available" if original else "not-found", "originalText": original, "sourceType": "semantic-scholar", "sourceUrl": BASE + record["paperId"] + "?fields=" + FIELDS, "metadataTitle": record["title"], "databaseId": record.get("url"), "checkedAt": datetime.now(timezone.utc).isoformat(), "acquisitionMethod": "complete abstract field; no TLDR, summary or generative content"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()
    refs = [r for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for r in json.loads(path.read_text())["references"]]
    metadata = json.loads((PROJECT / "content/reference-metadata-cache.json").read_text())
    publisher = json.loads((PROJECT / "content/reference-publisher-cache.json").read_text())
    cache_path = PROJECT / "content/reference-database-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    attempts_path = PROJECT / "content/reference-semantic-scholar-attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    pending = {}
    for reference in refs:
        key = reference.get("doi") or reference["id"]
        if reference.get("identityStatus") == "title-mismatch" or metadata.get(key, {}).get("status") == "available" or publisher.get(key, {}).get("status") == "available" or cache.get(key, {}).get("status") == "available":
            continue
        previous = attempts.get(key, {})
        if previous and (previous.get("status") != "not-checked" or not args.retry_errors):
            continue
        pending.setdefault(key, []).append(reference)
    dois = sorted(key for key in pending if key.startswith("10."))
    for offset in range(0, len(dois), 100):
        batch = dois[offset:offset + 100]
        try:
            records = request_json(BASE + "batch?fields=" + FIELDS, {"ids": ["DOI:" + doi for doi in batch]})
            if not isinstance(records, list) or len(records) != len(batch):
                raise ValueError("Database returned an incomplete batch")
            for doi, record in zip(batch, records, strict=True):
                result = {"status": "not-found", "originalText": "", "sourceType": "semantic-scholar", "sourceUrl": BASE + "DOI:" + urllib.parse.quote(doi, safe="") + "?fields=" + FIELDS, "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "database-has-no-record"}
                if record:
                    if all(match_work(reference, as_work(record), metadata) for reference in pending[doi]):
                        result = source_record(record)
                    else:
                        result.update({"status": "not-checked", "error": "Database record identity did not match the local bibliography"})
                attempts[doi] = {key: value for key, value in result.items() if key != "originalText"}
                if result["status"] == "available":
                    cache[doi] = result
                print(f"{doi}: {result['status']}", flush=True)
            atomic_json(cache_path, cache)
            atomic_json(attempts_path, attempts)
        except (RuntimeError, ValueError, KeyError) as error:
            print(f"Database batch failed: {error}; successful sources preserved.", flush=True)
            return 1
        time.sleep(1)
    for index, (key, references) in enumerate(((key, refs) for key, refs in pending.items() if not key.startswith("10.")), 1):
        reference = references[0]
        url = BASE + "search?" + urllib.parse.urlencode({"query": reference["title"], "limit": 5, "fields": FIELDS})
        base = {"status": "not-found", "sourceType": "semantic-scholar", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "no-exact-identity", "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest()}
        try:
            records = request_json(url).get("data", [])
            matches = [record for record in records if all(match_work(ref, as_work(record), metadata) for ref in references)]
            if len({record["paperId"] for record in matches}) == 1:
                result = {**base, **source_record(matches[0])}
                if result["status"] == "available":
                    cache[key] = result
                    atomic_json(cache_path, cache)
                base = {k: v for k, v in result.items() if k != "originalText"}
            elif matches:
                base["reason"] = "ambiguous-identity"
        except (RuntimeError, ValueError, KeyError) as error:
            base.update({"status": "not-checked", "error": str(error)})
        attempts[key] = base
        atomic_json(attempts_path, attempts)
        print(f"Search {index} {key}: {base['status']}", flush=True)
        if base.get("error") and any(code in base["error"] for code in ["429", "401", "403"]):
            print("Public API unavailable; stop rather than bypass rate limits or authentication.", flush=True)
            return 1
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
