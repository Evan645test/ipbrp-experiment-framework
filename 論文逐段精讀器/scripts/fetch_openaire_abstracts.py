#!/usr/bin/env python3
"""Retrieve identity-checked source abstracts from OpenAIRE repository metadata."""
import argparse
import concurrent.futures
import difflib
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone

from build_references import PROJECT, atomic_json, clean_text
from fetch_database_abstracts import request_json
from resolve_reference_dois import normalize

BASE = "https://api.openaire.eu/search/publications"


def items(value):
    return value if isinstance(value, list) else [value] if value is not None else []


def scalar(value):
    return str(value.get("$", "")) if isinstance(value, dict) else value if isinstance(value, str) else ""


def title_key(value):
    # Edition annotations are not part of a book's title; author and year remain
    # mandatory for records without a DOI, so editions are not chosen by title.
    value = re.sub(r"\s*[.(]?\s*\d+(?:st|nd|rd|th)\s+ed\.?\)?\s*$", "", value, flags=re.I)
    return normalize(value)


def matches(reference, record, metadata):
    if reference.get("identityStatus") == "title-mismatch":
        return False
    titles = [scalar(title) for title in items(record.get("title"))]
    expected = title_key(reference["title"])
    deposited = title_key(metadata.get(reference.get("doi"), {}).get("metadataTitle", ""))
    title_match = any(difflib.SequenceMatcher(None, expected, title_key(title)).ratio() >= 0.93 or (reference.get("identityStatus") == "verified" and deposited and difflib.SequenceMatcher(None, deposited, title_key(title)).ratio() >= 0.95) for title in titles)
    if not title_match:
        return False
    if reference.get("doi"):
        dois = {scalar(pid).removeprefix("https://doi.org/").lower() for pid in items(record.get("pid")) if isinstance(pid, dict) and pid.get("@classid") == "doi"}
        return reference["doi"].lower() in dois
    authors = items(record.get("creator"))
    if not authors:
        return False
    ranked = [author for author in authors if isinstance(author, dict) and str(author.get("@rank")) == "1"]
    first = normalize(scalar((ranked or authors)[0]))
    surname = normalize(reference["firstAuthor"])
    author_match = first == surname or first.endswith(" " + surname) or first.startswith(surname + " ")
    date = scalar(record.get("dateofacceptance"))
    return bool(author_match and re.match(r"^\d{4}", date) and abs(int(reference["year"][:4]) - int(date[:4])) <= 1)


def complete_description(record):
    texts = []
    for description in items(record.get("description")):
        if isinstance(description, dict):
            if description.get("@inferred") in {True, "true"}:
                continue
            language = description.get("@lang", description.get("@xml:lang", "en")).lower()
            if language not in {"en", "eng", "en-us", "en-gb", "english"}:
                continue
        text = clean_text(scalar(description))
        if len(text) >= 40 and not re.search(r"[\u4e00-\u9fff]", text) and not re.search(r"(?:\.\.\.|…)\s*$", text):
            if normalize(text) not in {normalize(previous) for previous in texts}:
                texts.append(text)
    if not texts:
        return ""
    # Several repositories may deposit the same text with minor punctuation
    # changes. Do not splice genuinely different abstracts into a new summary.
    longest = max(texts, key=len)
    if any(difflib.SequenceMatcher(None, normalize(longest), normalize(text)).ratio() < 0.98 for text in texts):
        raise ValueError("OpenAIRE contains different source descriptions; manual source selection required")
    return longest


def records(response):
    body = response.get("response")
    if not isinstance(body, dict) or not isinstance(body.get("header"), dict):
        raise ValueError("Invalid OpenAIRE response")
    total = int(scalar(body["header"].get("total")) or 0)
    results = body.get("results") or {}
    rows = items(results.get("result"))
    if total > len(rows):
        raise ValueError("OpenAIRE response was truncated; narrower identity query required")
    return rows


def lookup(reference, metadata):
    query = {"format": "json", "size": 100}
    if reference.get("doi"):
        query["doi"] = reference["doi"]
    else:
        query.update({"title": title_key(reference["title"]), "author": reference["firstAuthor"]})
    url = BASE + "?" + urllib.parse.urlencode(query)
    base = {"status": "not-found", "sourceType": "openaire", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest(), "reason": "no-exact-identity"}
    try:
        matched = []
        for row in records(request_json(url)):
            record = row.get("metadata", {}).get("oaf:entity", {}).get("oaf:result", {})
            if matches(reference, record, metadata):
                matched.append((row, record))
        identities = {scalar(row.get("header", {}).get("dri:objIdentifier")) for row, _ in matched}
        if len(identities) != 1 or not next(iter(identities), ""):
            return {**base, "reason": "ambiguous-identity" if matched else "no-exact-identity"}
        row, record = matched[0]
        original = complete_description(record)
        if not original:
            return {**base, "reason": "database-has-no-abstract"}
        title = next((scalar(title) for title in items(record.get("title")) if scalar(title)), "")
        return {**base, "status": "available", "originalText": original, "metadataTitle": title, "databaseId": scalar(row["header"]["dri:objIdentifier"]), "abstractOrigin": "OpenAIRE source repository metadata", "acquisitionMethod": "complete non-inferred source description field; no generated summary; identity checked by DOI and title or title, author and year"}
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
    attempts_path = PROJECT / "content/reference-openaire-attempts.json"
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
