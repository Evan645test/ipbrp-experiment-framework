#!/usr/bin/env python3
"""Read explicit Abstracts from manually located public official record pages."""
import argparse
import difflib
import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from build_references import PROJECT, HTTPS_CONTEXT, atomic_json, clean_text
from fetch_publisher_abstracts import AbstractParser
from resolve_reference_dois import normalize

HOSTS = {"egrove.olemiss.edu": "author", "eprints.soton.ac.uk": "author", "ejournal.unesa.ac.id": "publisher", "ruomoplus.lib.uom.gr": "author"}


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme != "https" or target.hostname not in HOSTS:
            raise ValueError("Official source redirected outside supported public HTTPS record hosts")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def record_title_key(value):
    return normalize(re.sub(r"\s*\((?:pp\.?\s*)?\d+\)\s*$", "", value))


def english_abstract(parser):
    text = parser.abstract() or clean_text(parser.metadata.get("eprints.abstract", parser.metadata.get("dcterms.abstract", "")))
    if text.startswith("Abstrak"):
        # The journal explicitly labels both languages. Translate only the
        # complete English section, rather than feeding Indonesian to en->zh.
        sections = re.split(r"\bAbstract\b", text)
        if len(sections) != 2:
            raise ValueError("Bilingual journal Abstract has no unique English section")
        text = re.split(r"\bKeywords\s*:", sections[1], maxsplit=1, flags=re.I)[0]
    text = clean_text(text)
    if len(text) < 40 or re.search(r"(?:\.\.\.|…)\s*$", text):
        raise ValueError("Official source did not provide a complete English Abstract")
    return text


def verify_identity(reference, parser):
    title = next((parser.metadata[key] for key in ["citation_title", "bepress_citation_title", "eprints.title", "dc.title"] if parser.metadata.get(key)), "")
    if difflib.SequenceMatcher(None, record_title_key(reference["title"]), record_title_key(title)).ratio() < 0.93:
        raise ValueError("Official record title identity did not match the local bibliography")
    if reference.get("doi"):
        identifiers = [value.lower() for key in ["citation_doi", "dc.identifier.doi", "dc.identifier"] for value in parser.metadata_values.get(key, [])]
        dois = {match.group(1).rstrip(".,;") for identifier in identifiers for match in re.finditer(r"(10\.\d{4,9}/[^\s<>]+)", identifier)}
        if reference["doi"].lower() not in dois:
            raise ValueError("Official source metadata did not confirm the expected DOI")
    else:
        authors = next((parser.metadata_values[key] for key in ["citation_author", "bepress_citation_author", "eprints.creators_name", "dc.creator", "author"] if parser.metadata_values.get(key)), [])
        first = normalize(authors[0]) if authors else ""
        surname = normalize(reference["firstAuthor"])
        author_match = first == surname or first.startswith(surname + " ") or first.endswith(" " + surname)
        dates = next((parser.metadata_values[key] for key in ["citation_date", "bepress_citation_date", "eprints.date", "dc.date.issued", "dc.date"] if parser.metadata_values.get(key)), [])
        year_match = any(re.match(r"^\d{4}", date) and abs(int(date[:4]) - int(reference["year"][:4])) <= 1 for date in dates)
        if not author_match or not year_match:
            raise ValueError("Official source author/year identity did not match the local bibliography")
    return title


def lookup(reference, source):
    url = source["url"]
    target = urllib.parse.urlparse(url)
    if target.scheme != "https" or HOSTS.get(target.hostname) != source["sourceType"]:
        raise ValueError("Only pinned, supported official HTTPS source records are allowed")
    base = {"sourceType": source["sourceType"], "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(), "sourceTextSha256": hashlib.sha256(reference["sourceText"].encode()).hexdigest()}
    try:
        opener = urllib.request.build_opener(OfficialRedirect(), urllib.request.HTTPSHandler(context=HTTPS_CONTEXT))
        request = urllib.request.Request(url, headers={"User-Agent": "PaperFocusReader/1.0", "Accept": "text/html"})
        with opener.open(request, timeout=25) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024 or "html" not in response.headers.get("Content-Type", ""):
                raise ValueError("Official source returned unsupported content")
            parser = AbstractParser()
            parser.feed(raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
            base["sourceUrl"] = response.url
        title = verify_identity(reference, parser)
        return {**base, "status": "available", "originalText": english_abstract(parser), "metadataTitle": title, "acquisitionMethod": "complete explicit Abstract section or ePrints abstract metadata; title, author and year or DOI checked; no generated summary"}
    except (OSError, ValueError, LookupError) as error:
        return {**base, "status": "not-checked", "error": str(error)}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    refs = {reference["id"]: reference for path in sorted((PROJECT / "public/data").glob("paper-*.json")) for reference in json.loads(path.read_text())["references"]}
    sources = json.loads((PROJECT / "content/reference-abstract-source-overrides.json").read_text())
    caches = {name: json.loads((PROJECT / "content" / name).read_text()) for name in ["reference-metadata-cache.json", "reference-publisher-cache.json", "reference-database-cache.json"]}
    attempts_path = PROJECT / "content/reference-curated-source-attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    for ref_id, source in sources.items():
        if ref_id not in refs:
            raise ValueError(f"Pinned source references an unknown bibliography entry: {ref_id}")
        reference = refs[ref_id]
        key = reference.get("doi") or reference["id"]
        if reference["identityStatus"] == "title-mismatch" or any(cache.get(key, {}).get("status") == "available" for cache in caches.values()):
            continue
        result = lookup(reference, source)
        if result["status"] == "available":
            destination = "reference-publisher-cache.json" if reference.get("doi") else "reference-database-cache.json"
            caches[destination][key] = result
            atomic_json(PROJECT / "content" / destination, caches[destination])
        attempts[key] = {name: value for name, value in result.items() if name != "originalText"}
        atomic_json(attempts_path, attempts)
        print(f"{key}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    return 1 if any(result.get("status") == "not-checked" for result in attempts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
