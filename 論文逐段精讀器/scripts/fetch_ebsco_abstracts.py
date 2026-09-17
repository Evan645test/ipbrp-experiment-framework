#!/usr/bin/env python3
"""Read Abstract fields from public EBSCO OpenURL pages without authentication."""
import argparse
import concurrent.futures
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from build_references import PROJECT, HTTPS_CONTEXT, atomic_json, clean_text
from fetch_database_abstracts import match_work


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme == "http" and target.hostname == "openurl.ebsco.com":
            target = target._replace(scheme="https")
            newurl = urllib.parse.urlunparse(target)
        if target.scheme != "https" or target.hostname != "openurl.ebsco.com":
            raise ValueError(f"EBSCO redirected outside its public HTTPS record host ({target.scheme}://{target.hostname})")
        return super().redirect_request(request, fp, code, message, headers, newurl)


class RecordParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capture = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.capture = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)


def source_record(reference, response, url, metadata):
    props = response.get("props") or {}
    if props.get("isAuthenticated") is True:
        raise ValueError("Only unauthenticated public EBSCO records are supported")
    item = (props.get("pageProps") or {}).get("data", {}).get("item") or {}
    info = item.get("itemInfo") or {}
    actual_doi = str(info.get("doi") or "").lower()
    if not match_work(reference, {"doi": actual_doi, "title": info.get("title") or ""}, metadata):
        raise ValueError("Public EBSCO record DOI/title identity did not match the local bibliography")
    original = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", str(info.get("ab") or ""))))
    if original and (len(original) < 40 or re.search(r"(?:\.\.\.|…)\s*$", original)):
        raise ValueError("Public EBSCO Abstract is incomplete")
    return {"status": "available" if original else "not-found", "originalText": original, "sourceType": "ebsco", "sourceUrl": url, "metadataTitle": info["title"], "abstractOrigin": "EBSCO Abstract field; abstractor unspecified", "databaseId": info.get("id"), "checkedAt": datetime.now(timezone.utc).isoformat(), "reason": "database-has-no-abstract" if not original else "", "acquisitionMethod": "complete public itemInfo.ab Abstract field; no login or generated summary"}


def lookup(reference, metadata):
    doi = reference["doi"]
    url = "https://openurl.ebsco.com/contentitem/" + urllib.parse.quote("doi:" + doi, safe="") + "?" + urllib.parse.urlencode({"id": "ebsco:doi:" + doi, "sid": "ebsco:plink:crawler"})
    base = {"status": "not-checked", "sourceType": "ebsco", "sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat()}
    try:
        opener = urllib.request.build_opener(PublicRedirect(), urllib.request.HTTPSHandler(context=HTTPS_CONTEXT))
        request = urllib.request.Request(url, headers={"User-Agent": "PaperFocusReader/1.0", "Accept": "text/html"})
        with opener.open(request, timeout=25) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024 or "html" not in response.headers.get("Content-Type", ""):
                raise ValueError("EBSCO did not return a supported HTML response")
            final_url = response.url
            parser = RecordParser()
            parser.feed(raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
        if not parser.parts:
            raise ValueError("Public EBSCO record metadata unavailable; no access restriction is bypassed")
        return source_record(reference, json.loads("".join(parser.parts)), final_url, metadata)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {**base, "error": str(error)}


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
    attempts_path = PROJECT / "content/reference-ebsco-attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    pending = {}
    for reference in refs:
        key = reference.get("doi")
        previous = attempts.get(key, {})
        if not key or reference["identityStatus"] == "title-mismatch" or any(source.get(key, {}).get("status") == "available" for source in [*sources, cache]):
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
