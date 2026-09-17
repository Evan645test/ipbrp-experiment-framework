#!/usr/bin/env python3
"""Resolve local bibliography DOIs and cache verified publisher Abstracts."""
import argparse
import concurrent.futures
import difflib
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from build_references import PROJECT, HTTPS_CONTEXT, atomic_json, clean_text


class AbstractParser(HTMLParser):
    VOID = {"meta", "link", "img", "br", "hr", "input", "source", "wbr", "area", "base", "embed", "param", "track", "col"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.metadata = {}
        self.metadata_values = {}
        self.fragments = []
        self.capture_depth = None
        self.anchor = ""
        self.refresh_url = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("name", attrs.get("property", "")).lower()
            self.metadata[key] = attrs.get("content", "")
            self.metadata_values.setdefault(key, []).append(attrs.get("content", ""))
            if attrs.get("http-equiv", "").casefold() == "refresh":
                refresh = re.search(r";\s*url\s*=\s*(.+)$", attrs.get("content", ""), re.I)
                if refresh:
                    self.refresh_url = refresh.group(1).strip(" '\"")
        if tag not in self.VOID:
            self.stack.append(tag)
        identifier = attrs.get("id", "")
        classes = {value.casefold() for value in attrs.get("class", "").split()}
        if self.capture_depth is None and (identifier.lower() in {"abs1", "abs1-section", "abstract", "abstract-content", "abstract-section", "html-abstract", "abstract_div"} or bool(classes & {"abstract", "abstractsection", "abstract-content", "article-abstract"}) or attrs.get("role") == "doc-abstract" or attrs.get("data-title", "").lower() == "abstract"):
            self.capture_depth = len(self.stack) - (1 if tag in {"h2", "h3"} else 0)
            self.anchor = identifier

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        if self.capture_depth is not None and index < self.capture_depth:
            if tag in {"p", "h2", "h3", "div"}:
                self.fragments.append("\n\n")
            self.capture_depth = None
        del self.stack[index:]

    def handle_data(self, data):
        if self.capture_depth is not None and not any(tag in {"script", "style"} for tag in self.stack):
            self.fragments.append(data)

    def abstract(self):
        text = clean_text(" ".join(self.fragments))
        text = re.sub(r"^Abstract\s*", "", text, flags=re.I)
        if not text:
            text = clean_text(self.metadata.get("citation_abstract", ""))
        return text


ALLOWED_HOSTS = {"doi.org", "link.springer.com", "link.springernature.com", "idp.springer.com", "idp.springernature.com", "www.sciencepublishinggroup.com", "www.sciencepg.com", "www.sciencepublishgroup.com", "onlinelibrary.wiley.com", "www.mdpi.com", "www.frontiersin.org", "www.tandfonline.com", "journals.sagepub.com", "www.sciencedirect.com", "linkinghub.elsevier.com", "dl.acm.org", "www.cambridge.org", "academic.oup.com", "www.nature.com"}
ALLOWED_HOSTS.update({"doi.apa.org", "psycnet.apa.org", "www.inderscience.com", "www.inderscienceonline.com", "ieeexplore.ieee.org", "arxiv.org", "jime.open.ac.uk", "ro.ecu.edu.au", "ajet.org.au", "www.oecd.org", "da.lib.ntnu.edu.tw", "www.airitilibrary.com", "www.rcis.ro", "journals.sfu.ca", "journal.hep.com.cn"})


class PublisherRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme == "http" and target.hostname in ALLOWED_HOSTS:
            newurl = urllib.parse.urlunparse(target._replace(scheme="https"))
            target = urllib.parse.urlparse(newurl)
        if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"DOI redirected outside supported HTTPS publisher hosts ({target.scheme}://{target.hostname})")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch_publisher(doi, expected_titles):
    opener = urllib.request.build_opener(PublisherRedirect(), urllib.request.HTTPSHandler(context=HTTPS_CONTEXT), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request("https://doi.org/" + urllib.parse.quote(doi, safe="/"), headers={"User-Agent": "Mozilla/5.0 PaperFocusReader/1.0", "Accept": "text/html"})
    last_error = None
    for attempt in range(3):
        try:
            for hop in range(4):
                with opener.open(request, timeout=30) as response:
                    raw = response.read(8 * 1024 * 1024 + 1)
                    if len(raw) > 8 * 1024 * 1024:
                        raise ValueError("Publisher response exceeded the 8 MiB limit")
                    if "html" not in response.headers.get("Content-Type", ""):
                        raise ValueError("Publisher returned a non-HTML response")
                    url = response.url
                    charset = response.headers.get_content_charset() or "utf-8"
                parser = AbstractParser()
                parser.feed(raw.decode(charset, errors="replace"))
                if not parser.refresh_url:
                    break
                target = urllib.parse.urlparse(urllib.parse.urljoin(url, parser.refresh_url))
                if target.scheme == "http" and target.hostname in ALLOWED_HOSTS:
                    target = target._replace(scheme="https")
                if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS or hop == 3:
                    raise ValueError("Publisher meta redirect outside supported HTTPS hosts or redirect limit")
                request = urllib.request.Request(urllib.parse.urlunparse(target), headers={"User-Agent": "Mozilla/5.0 PaperFocusReader/1.0", "Accept": "text/html"})
            title = parser.metadata.get("citation_title", parser.metadata.get("dc.title", ""))
            normalize = lambda value: re.sub(r"\W+", " ", value.casefold()).strip()
            if not title or max(difflib.SequenceMatcher(None, normalize(title), normalize(expected)).ratio() for expected in expected_titles) < 0.55:
                raise ValueError("Publisher title did not match the local bibliography")
            publisher_doi = parser.metadata.get("citation_doi", parser.metadata.get("dc.identifier.doi", parser.metadata.get("dc.identifier", ""))).lower()
            arxiv_id = parser.metadata.get("citation_arxiv_id", "").lower()
            arxiv_confirmed = urllib.parse.urlparse(url).hostname == "arxiv.org" and re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", arxiv_id) and doi.lower() == "10.48550/arxiv." + re.sub(r"v\d+$", "", arxiv_id)
            if doi.lower() not in publisher_doi and doi.lower() not in urllib.parse.unquote(url).lower() and not arxiv_confirmed:
                raise ValueError("Publisher page did not confirm the requested DOI")
            text = parser.abstract()
            if not text:
                return {"status": "not-found", "originalText": "", "sourceUrl": url, "sourceType": "publisher", "metadataTitle": title, "checkedAt": datetime.now(timezone.utc).isoformat()}
            if len(text) < 40:
                raise ValueError("Publisher Abstract was empty or incomplete")
            return {"status": "available", "originalText": text, "sourceUrl": url.split("#", 1)[0] + ("#" + urllib.parse.quote(parser.anchor) if parser.anchor else ""), "sourceType": "publisher", "metadataTitle": title, "checkedAt": datetime.now(timezone.utc).isoformat()}
        except (OSError, ValueError, LookupError) as error:
            last_error = str(error)
            # Authentication blocks, unsupported redirects and identity failures
            # are deterministic; retry only transient transport/server failures.
            if isinstance(error, ValueError) or (isinstance(error, urllib.error.HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}):
                break
            if attempt < 2:
                time.sleep(attempt + 1)
    return {"status": "not-checked", "originalText": "", "error": last_error, "sourceUrl": url if "url" in locals() else request.full_url, "checkedAt": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi", action="append", help="Limit lookup to a DOI in the local bibliography; repeatable.")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--missing-only", action="store_true", help="Do not fetch sources already available in the metadata cache.")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    expected = {}
    for path in (PROJECT / "public/data").glob("paper-*.json"):
        paper = json.loads(path.read_text(encoding="utf-8"))
        for reference in paper.get("references", []):
            if reference.get("doi") and reference.get("identityStatus") != "title-mismatch":
                expected.setdefault(reference["doi"], []).append(reference["title"])
    requested = [value.lower() for value in args.doi] if args.doi else sorted(expected)
    if any(doi not in expected for doi in requested):
        parser.error("Every requested DOI must be a non-mismatched local bibliography entry")
    cache_path = PROJECT / "content/reference-publisher-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    metadata_path = PROJECT / "content/reference-metadata-cache.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    pending = [doi for doi in dict.fromkeys(requested) if (args.refresh or cache.get(doi, {}).get("status") != "available") and (not args.missing_only or metadata.get(doi, {}).get("status") != "available")]
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_publisher, doi, expected[doi]): doi for doi in pending}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            doi = futures[future]
            result = future.result()
            if result["status"] == "not-checked":
                failures += 1
                if cache.get(doi, {}).get("status") == "available":
                    print(f"{index}/{len(pending)} {doi}: refresh failed; previous source preserved", flush=True)
                    continue
            cache[doi] = result
            # A single writer checkpoints every result; workers never mutate caches.
            atomic_json(cache_path, cache)
            print(f"{index}/{len(pending)} {doi}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    print(f"Checked {len(pending)} sources; {failures} require another access path.", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
