#!/usr/bin/env python3
"""Resolve missing or conflicting printed DOIs using title, author and year."""
import argparse
import concurrent.futures
import difflib
import hashlib
import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from build_references import PROJECT, HTTPS_CONTEXT, atomic_json, clean_text, crossref_title


def normalize(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^\w]+", " ", "".join(c for c in value if not unicodedata.combining(c))).strip()


def matching_candidate(reference, candidate):
    title = crossref_title(candidate)
    expected = normalize(re.sub(r"\s*\([^)]*(?:ed\.|Eds\.)[^)]*\)", "", reference["title"]))
    actual = normalize(title)
    ratio = difflib.SequenceMatcher(None, expected, actual).ratio()
    authors = candidate.get("author") or []
    first = normalize(authors[0].get("family", "")) if authors else ""
    source_author = normalize(reference["firstAuthor"])
    author_matches = bool(first and (first == source_author or source_author.endswith(" " + first)))
    years = {parts[0] for key in ["published", "published-print", "published-online", "issued"] for parts in candidate.get(key, {}).get("date-parts", []) if parts and isinstance(parts[0], int)}
    year = int(reference["year"][:4])
    year_matches = any(abs(year - value) <= 1 for value in years)
    # A short main book title is insufficient to resolve an edition safely.
    if ratio < 0.93 or not author_matches or not year_matches:
        return None
    doi = candidate.get("DOI", "").lower()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return None
    return {"doi": doi, "metadataTitle": title, "titleSimilarity": ratio, "matchedAuthor": first, "matchedYears": sorted(years), "workType": candidate.get("type", "")}


def lookup(reference):
    parameters = urllib.parse.urlencode({"query.bibliographic": reference["title"], "query.author": reference["firstAuthor"], "rows": 5})
    url = "https://api.crossref.org/works?" + parameters
    base = {"sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest(), "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat()}
    last_error = "Lookup failed"
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PaperFocusReader/1.0 (local bibliography identity verification)", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=25, context=HTTPS_CONTEXT) as response:
                candidates = json.load(response)["message"]["items"]
            matches = [(matching_candidate(reference, candidate), candidate) for candidate in candidates]
            matches = [(match, candidate) for match, candidate in matches if match]
            distinct = {match["doi"] for match, _ in matches}
            if len(distinct) != 1:
                return {**base, "status": "ambiguous" if distinct else "no-exact-match", "candidateCount": len(distinct)}, None
            match, candidate = matches[0]
            original = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", candidate.get("abstract", ""))))
            metadata = {"status": "available" if original else "not-found", "originalText": original, "summaryZh": "", "metadataTitle": match["metadataTitle"], "sourceUrl": "https://api.crossref.org/works/" + urllib.parse.quote(match["doi"], safe=""), "sourceType": "crossref", "checkedAt": base["checkedAt"], "workType": match["workType"]}
            return {**base, **match, "status": "verified"}, metadata
        except (OSError, ValueError, KeyError) as error:
            last_error = str(error)
            if isinstance(error, urllib.error.HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}:
                break
            if attempt < 2:
                time.sleep(attempt + 1)
    return {**base, "status": "access-error", "error": last_error}, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    references = [r for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for r in json.loads(path.read_text())["references"] if not r.get("doi") or r.get("identityStatus") == "title-mismatch"]
    output_path = PROJECT / "content/reference-doi-resolutions.json"
    output = json.loads(output_path.read_text()) if output_path.exists() else {}
    cache_path = PROJECT / "content/reference-metadata-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    pending = [r for r in references if args.refresh or output.get(r["id"], {}).get("sourceTextSha256") != hashlib.sha256(r["sourceText"].encode()).hexdigest() or output.get(r["id"], {}).get("status") == "access-error"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(lookup, reference): reference for reference in pending}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            reference = futures[future]
            result, metadata = future.result()
            output[reference["id"]] = result
            if metadata and (cache.get(result["doi"], {}).get("status") != "available" or metadata["status"] == "available"):
                cache[result["doi"]] = metadata
                atomic_json(cache_path, cache)
            atomic_json(output_path, output)
            print(f"{index}/{len(pending)} {reference['id']}: {result['status']}" + (f" {result['doi']}" if result.get("doi") else ""), flush=True)
    return 1 if any(r.get("status") == "access-error" for r in output.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
