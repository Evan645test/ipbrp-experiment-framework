#!/usr/bin/env python3
"""Cache identity-checked source abstracts from the public OpenAlex database."""
import argparse
import concurrent.futures
import difflib
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from build_references import PROJECT, HTTPS_CONTEXT, atomic_json
from resolve_reference_dois import normalize


def reconstruct_abstract(index):
    if not isinstance(index, dict) or not index:
        return ""
    positions = {}
    for word, offsets in index.items():
        if not isinstance(word, str) or not isinstance(offsets, list):
            raise ValueError("Malformed database Abstract index")
        for offset in offsets:
            if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset < 5000 or offset in positions:
                raise ValueError("Database Abstract has invalid or duplicate word positions")
            positions[offset] = word
    if not positions or set(positions) != set(range(max(positions) + 1)):
        raise ValueError("Database Abstract has missing word positions")
    text = " ".join(positions[position] for position in range(len(positions)))
    if len(text) < 40:
        raise ValueError("Database Abstract is incomplete")
    return text


def request_json(url):
    last_error = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PaperFocusReader/1.0 (local source Abstract lookup)", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30, context=HTTPS_CONTEXT) as response:
                return json.load(response)
        except (OSError, ValueError) as error:
            last_error = error
            if isinstance(error, urllib.error.HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}:
                break
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(str(last_error))


def match_work(reference, work, metadata):
    expected, actual = normalize(reference["title"]), normalize(work.get("title") or "")
    similarity = difflib.SequenceMatcher(None, expected, actual).ratio()
    doi = (work.get("doi") or "").removeprefix("https://doi.org/").lower()
    if reference.get("doi"):
        if doi != reference["doi"] or reference.get("identityStatus") == "title-mismatch":
            return False
        deposited_title = normalize(metadata.get(reference["doi"], {}).get("metadataTitle", ""))
        deposited_matches = reference.get("identityStatus") == "verified" and deposited_title and difflib.SequenceMatcher(None, deposited_title, actual).ratio() >= 0.95
        return similarity >= 0.93 or bool(deposited_matches)
    authors = work.get("authorships") or []
    first = normalize(authors[0].get("author", {}).get("display_name", "")) if authors else ""
    source_author = normalize(reference["firstAuthor"])
    author_matches = bool(first and (source_author in first or source_author.endswith(" " + first.split()[-1])))
    year = work.get("publication_year")
    return similarity >= 0.93 and author_matches and isinstance(year, int) and abs(int(reference["year"][:4]) - year) <= 1


def source_record(work):
    text = reconstruct_abstract(work.get("abstract_inverted_index"))
    return {"status": "available" if text else "not-found", "originalText": text, "sourceUrl": "https://api.openalex.org/works/" + work["id"].rsplit("/", 1)[-1], "sourceType": "openalex", "metadataTitle": work.get("title", ""), "databaseId": work["id"], "checkedAt": datetime.now(timezone.utc).isoformat(), "acquisitionMethod": "source Abstract reconstructed in exact indexed word order; no summary generation"}


def search_reference(reference, metadata):
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": reference["title"], "per_page": 5})
    base = {"sourceType": "openalex", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest(), "originalText": ""}
    try:
        records = request_json(url)["results"]
        matches = [work for work in records if match_work(reference, work, metadata)]
        # A book, edition or article with multiple plausible identities is held.
        if len({work["id"] for work in matches}) != 1:
            return {**base, "status": "not-found", "reason": "ambiguous-identity" if matches else "no-exact-identity"}
        return {**base, **source_record(matches[0])}
    except (RuntimeError, ValueError, KeyError) as error:
        return {**base, "status": "not-checked", "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    refs = [r for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for r in json.loads(path.read_text())["references"]]
    metadata = json.loads((PROJECT / "content/reference-metadata-cache.json").read_text())
    publisher = json.loads((PROJECT / "content/reference-publisher-cache.json").read_text())
    output_path = PROJECT / "content/reference-database-cache.json"
    output = json.loads(output_path.read_text()) if output_path.exists() else {}
    pending = [r for r in refs if r.get("identityStatus") != "title-mismatch" and metadata.get(r.get("doi"), {}).get("status") != "available" and publisher.get(r.get("doi"), {}).get("status") != "available" and (args.refresh or output.get(r.get("doi") or r["id"], {}).get("status") not in {"available", "not-found"})]
    grouped = {}
    for reference in pending:
        if reference.get("doi"):
            grouped.setdefault(reference["doi"], []).append(reference)
    dois = sorted(grouped)
    for offset in range(0, len(dois), 40):
        batch = dois[offset:offset + 40]
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"filter": "doi:" + "|".join("https://doi.org/" + doi for doi in batch), "per_page": 100})
        try:
            records = request_json(url)["results"]
            by_doi = {(work.get("doi") or "").removeprefix("https://doi.org/").lower(): work for work in records}
            for doi in batch:
                work = by_doi.get(doi)
                result = {"status": "not-found", "originalText": "", "sourceType": "openalex", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "database-has-no-record"}
                if work:
                    if all(match_work(reference, work, metadata) for reference in grouped[doi]):
                        try:
                            result = source_record(work)
                        except (ValueError, KeyError) as error:
                            result.update({"status": "not-checked", "error": str(error)})
                    else:
                        result.update({"status": "not-checked", "error": "Database record identity did not match the local bibliography"})
                if output.get(doi, {}).get("status") != "available" or result["status"] == "available":
                    output[doi] = result
                print(f"{doi}: {result['status']}", flush=True)
            atomic_json(output_path, output)
        except (RuntimeError, KeyError) as error:
            print(f"Database batch failed: {error}; successful sources preserved.", flush=True)
            return 1
    no_doi = {r["id"]: r for r in pending if not r.get("doi")}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(search_reference, reference, metadata): key for key, reference in no_doi.items()}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            key = futures[future]
            result = future.result()
            if output.get(key, {}).get("status") != "available" or result["status"] == "available":
                output[key] = result
            atomic_json(output_path, output)
            print(f"{index}/{len(no_doi)} {key}: {result['status']}", flush=True)
    return 1 if any(record.get("status") == "not-checked" for record in output.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
