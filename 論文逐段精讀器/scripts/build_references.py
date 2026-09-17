#!/usr/bin/env python3
"""Build page-grounded bibliography/citation indexes; optionally fetch DOI abstracts."""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import hashlib
import html
import json
import os
import re
import ssl
import time
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz


PROJECT = Path(__file__).resolve().parent.parent
SYSTEM_CA = Path("/etc/ssl/cert.pem")
HTTPS_CONTEXT = ssl.create_default_context(
    cafile=str(SYSTEM_CA) if ssl.get_default_verify_paths().cafile is None and SYSTEM_CA.is_file() else None
)
AUTHOR_START = re.compile(r"^(?:(?:van|von|de|del|da)\s+)?[A-ZÀ-ž][^,]{1,80},\s*[A-ZÀ-ž](?:[ .-]|$)")
YEAR = re.compile(r"\((\d{4}[a-z]?)\)\.?|\.\s+(\d{4}[a-z]?)\.\s+")
NOISE = re.compile(
    r"(?:downloaded from|terms and conditions|^journal of computer assisted learning(?:, \d{4})?$|"
    r"^education and information technologies \(20|^computers & education \d[^a-z]*$|"
    r"^thinking skills and creativity \d[^a-z]*$|^interactive learning environments$|"
    r"^innovations in education and teaching international$)", re.I
)


def atomic_json(path: Path, value: Any) -> None:
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def clean_text(text: str) -> str:
    text = text.replace("\u200b", "").replace("\u00ad", "")
    return re.sub(r"\s+", " ", text).strip()


def crossref_title(record: dict[str, Any]) -> str:
    title = (record.get("title") or [""])[0]
    subtitle = (record.get("subtitle") or [""])[0]
    return clean_text(title + (": " + subtitle if subtitle and subtitle.casefold() not in title.casefold() else ""))


def title_for(rest: str) -> str:
    # Wiley places terminal punctuation inside the outer title quotation.
    # Nested quotations followed by a colon must not terminate the title.
    quoted = re.match(r'[“"](.+?)(?:[.!?][”"]|[”"]\.)\s', rest)
    if quoted:
        return quoted.group(1).strip()
    # Some supplied bibliographies print the month after a separate year.
    rest = re.sub(r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\)\.\s+", "", rest)
    rest = re.split(r"\s+https?://|\.\s+arXiv\s+preprint\b|,\s*edited by\b|\s+\([A-Z]\.\s+[^)]*\btrans\)?", rest, maxsplit=1, flags=re.I)[0]
    return re.split(r"\.\s+(?=[A-Z])|\?\s+(?=[A-Z][^?!.]{0,100},\s*\d)", rest, maxsplit=1)[0].strip().rstrip(".")


def lines_for(page: fitz.Page) -> list[dict[str, Any]]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            raw = "".join(span["text"] for span in line["spans"])
            text = clean_text(raw)
            x0, y0, x1, y1 = line["bbox"]
            if not text or NOISE.search(text) or x0 > page.rect.width * 0.94:
                continue
            if re.fullmatch(r"\d+(?:\s+of\s+\d+)?|1\s*3", text) and (y0 < 45 or y0 > page.rect.height - 55):
                continue
            if y0 > page.rect.height - 38:
                continue
            if y0 < 45 and re.search(r"(?:et al\.|ET AL\.|AND [A-Z].*HSU)$", text):
                continue
            lines.append({
                "text": text, "raw": raw, "bbox": [x0, y0, x1, y1],
                "page": page.number + 1,
                "pageSize": [round(page.rect.width, 2), round(page.rect.height, 2)],
            })
    mid = page.rect.width / 2
    crossing = sum(item["bbox"][0] < mid < item["bbox"][2] for item in lines)
    single_column = crossing > len(lines) * 0.3
    for item in lines:
        item["column"] = 0 if single_column or item["bbox"][0] < mid else 1
    return sorted(lines, key=lambda item: (item["column"], item["bbox"][1], item["bbox"][0]))


def is_entry_start(line: dict[str, Any]) -> bool:
    text = line["text"]
    return bool(AUTHOR_START.match(text) or re.match(r"^[A-Z][^.]{3,90}\.\s*\(\d{4}\)", text))


def join_lines(lines: list[dict[str, Any]]) -> str:
    text = ""
    previous_raw = ""
    for line in lines:
        part = line["text"]
        if text and (previous_raw.rstrip().endswith("\u00ad") or (text.endswith("-") and part[:1].islower())):
            text = text.rstrip("-") + part
        else:
            text += (" " if text else "") + part
        previous_raw = line["raw"]
    return clean_text(text)


def fragments_for(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fragments: dict[tuple[int, int], dict[str, Any]] = {}
    for line in lines:
        key = (line["page"], line["column"])
        if key not in fragments:
            fragments[key] = {"page": line["page"], "bbox": line["bbox"][:], "pageSize": line["pageSize"]}
        else:
            current = fragments[key]["bbox"]
            incoming = line["bbox"]
            current[:] = [min(current[0], incoming[0]), min(current[1], incoming[1]), max(current[2], incoming[2]), max(current[3], incoming[3])]
    for fragment in fragments.values():
        fragment["bbox"] = [round(value, 2) for value in fragment["bbox"]]
    return list(fragments.values())


def doi_for(text: str, lines: list[dict[str, Any]], document: fitz.Document) -> str | None:
    # PDF link rectangles can overlap adjacent bibliography entries. Only use
    # the DOI printed inside this entry; geometry alone cannot establish identity.
    compact = re.sub(r"\s+", "", text)
    candidates = []
    for page_number in {line["page"] for line in lines}:
        for link in document[page_number - 1].get_links():
            uri = urllib.parse.unquote(link.get("uri", ""))
            if "doi.org/" not in uri:
                continue
            printed_doi = uri.split("doi.org/", 1)[1].rstrip(".,;").lower()
            if printed_doi in compact.lower() and re.fullmatch(r"10\.\d{4,9}/\S+", printed_doi):
                candidates.append(printed_doi)
    for index, line in enumerate(lines):
        matches = re.finditer(r"(?:https?://(?:dx\.)?doi\.org/|doi:)\s*(10\..*?)(?=\s+https?://|\s+doi:|\.\s+(?:Article|Retrieved|Accessed)\b|$)", line["text"], re.I)
        for match in matches:
            printed = match.group(1)
            if match.end() == len(line["text"]):
                for following in lines[index + 1:]:
                    continuation = following["text"]
                    if not re.fullmatch(r"[\w().;/:-]+", continuation) or continuation.startswith("http"):
                        break
                    printed += continuation
            doi = urllib.parse.unquote(re.sub(r"\s+", "", printed)).rstrip(".,;").lower()
            if re.fullmatch(r"10\.\d{4,9}/\S+", doi):
                candidates.append(doi)
    complete = {candidate for candidate in candidates if not any(other != candidate and other.startswith(candidate) for other in candidates)}
    # More than one independently printed DOI cannot be resolved safely by
    # choosing the longest URL or its geometric position.
    return next(iter(complete)) if len(complete) == 1 else None


def bibliography(paper: dict[str, Any]) -> list[dict[str, Any]]:
    document = fitz.open(PROJECT / "public" / paper["pdfUrl"].lstrip("/"))
    try:
        entries: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        started = False
        for page in document:
            for line in lines_for(page):
                text = line["text"]
                if text.casefold().rstrip(".:") in {"references", "bibliography"}:
                    started = True
                    continue
                if not started:
                    continue
                if re.match(r"^(?:Publisher[’']s Note|Supporting Information|Supplementary Information)\b", text):
                    started = False
                    continue
                if is_entry_start(line):
                    if current:
                        entries.append(current)
                    current = [line]
                elif current:
                    current.append(line)
        if current:
            entries.append(current)

        references = []
        for entry in entries:
            text = join_lines(entry)
            year_match = YEAR.search(text)
            if not year_match:
                continue
            year = year_match.group(1) or year_match.group(2)
            authors = text[:year_match.start()].rstrip(". ")
            rest = text[year_match.end():].strip()
            title = title_for(rest)
            first_author = authors.split(",", 1)[0].strip()
            short_label = f"{first_author} ({year})"
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            references.append({
                "id": f"{paper['id']}-ref-{digest}",
                "label": short_label,
                "authors": authors,
                "firstAuthor": first_author,
                "year": year,
                "title": title,
                "sourceText": text,
                "fragments": fragments_for(entry),
                "doi": doi_for(text, entry, document),
                "extractionStatus": "needs-review",
                "identityStatus": "not-checked",
                "abstract": {
                    "status": "not-checked", "originalText": "", "summaryZh": "", "summaryMethod": None,
                    "faithfulZh": "", "translationSourceSha256": "", "translationStatus": "ai-draft",
                    "sourceUrl": None, "sourceType": None, "checkedAt": None,
                },
            })
        if not references:
            raise ValueError(f"{paper['id']}: no bibliography entries could be extracted")
        return references
    finally:
        document.close()


def context_for(text: str, start: int, end: int) -> str:
    boundaries = [match.end() for match in re.finditer(r"[.!?]\s+(?=[A-Z])", text)]
    before = max([0] + [value for value in boundaries if value <= start])
    after = min([len(text)] + [value for value in boundaries if value >= end])
    return text[before:after].strip()


def citation_index(paper: dict[str, Any], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations = []
    for segment in paper["segments"]:
        occurrences: dict[tuple[int, int], dict[str, Any]] = {}
        for reference in references:
            author = re.escape(reference["firstAuthor"])
            coauthor = r"(?:\s+et\s+al\.?|\s*(?:&|and)\s+[A-ZÀ-ž][\wÀ-ž’'\-]*(?:\s+[A-ZÀ-ž][\wÀ-ž’'\-]*){0,3})?"
            pattern = re.compile(rf"(?<!\w){author}{coauthor}\s*,?\s*\(?\s*{re.escape(reference['year'])}(?![\da-z])\s*\)?", re.I)
            for match in pattern.finditer(segment["sourceText"]):
                key = (match.start(), match.end())
                occurrence = occurrences.setdefault(key, {
                    "id": f"{segment['id']}-cite-{match.start()}",
                    "segmentId": segment["id"],
                    "label": match.group().strip().rstrip(";,").lstrip("("),
                    "sourceContext": context_for(segment["sourceText"], match.start(), match.end()),
                    "referenceIds": [],
                    "matchStatus": "matched",
                })
                occurrence["referenceIds"].append(reference["id"])
        for occurrence in sorted(occurrences.values(), key=lambda value: int(value["id"].rsplit("-", 1)[1])):
            if len(occurrence["referenceIds"]) > 1:
                occurrence["matchStatus"] = "ambiguous"
            citations.append(occurrence)
    return citations


def fetch_abstract(doi: str) -> tuple[str, dict[str, Any]]:
    api_url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    for attempt in range(3):
        try:
            request = urllib.request.Request(api_url, headers={"User-Agent": "PaperFocusReader/1.0 (local authorized-paper bibliography lookup)", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=25, context=HTTPS_CONTEXT) as response:
                record = json.load(response)["message"]
            if record.get("DOI", "").lower() != doi.lower():
                raise ValueError("Crossref returned a different DOI")
            original = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", record.get("abstract", ""))))
            return doi, {
                "status": "available" if original else "not-found",
                "originalText": original,
                "summaryZh": "",
                "sourceUrl": api_url,
                "sourceType": "crossref",
                "checkedAt": datetime.now(timezone.utc).isoformat(),
                "metadataTitle": crossref_title(record),
            }
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return doi, {"status": "not-found", "originalText": "", "summaryZh": "", "sourceUrl": api_url, "sourceType": "crossref", "checkedAt": datetime.now(timezone.utc).isoformat()}
            if attempt == 2:
                return doi, {"status": "not-checked", "error": str(error)}
        except (OSError, ValueError, KeyError) as error:
            if attempt == 2:
                return doi, {"status": "not-checked", "error": str(error)}
        time.sleep(attempt + 1)
    raise RuntimeError("Abstract fetch retries exhausted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-abstracts", action="store_true", help="Fetch publisher-deposited abstracts using exact DOI matches only.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--doi", action="append", help="Refresh selected exact local DOIs; requires --fetch-abstracts.")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    if args.doi and not args.fetch_abstracts:
        parser.error("--doi requires --fetch-abstracts")
    paths = sorted((PROJECT / "public" / "data").glob("paper-*.json"))
    papers = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    all_references = [bibliography(paper) for paper in papers]
    resolutions_path = PROJECT / "content/reference-doi-resolutions.json"
    resolutions = json.loads(resolutions_path.read_text(encoding="utf-8")) if resolutions_path.exists() else {}
    for references in all_references:
        for reference in references:
            resolution = resolutions.get(reference["id"], {})
            if resolution.get("status") == "verified" and resolution.get("sourceTextSha256") == hashlib.sha256(reference["sourceText"].encode()).hexdigest() and resolution.get("titleSimilarity", 0) >= 0.93:
                reference["printedDoi"] = reference["doi"]
                reference["doi"] = resolution["doi"]
                reference["doiResolution"] = {"method": "title-author-year", "sourceUrl": resolution["sourceUrl"], "checkedAt": resolution["checkedAt"]}
    cache_path = PROJECT / "content" / "reference-metadata-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if args.fetch_abstracts:
        current_dois = {reference["doi"] for refs in all_references for reference in refs if reference["doi"]}
        if args.doi and any(doi.lower() not in current_dois for doi in args.doi):
            parser.error("Every requested DOI must be present in the local bibliography")
        dois = sorted({doi.lower() for doi in args.doi}) if args.doi else sorted(doi for doi in current_dois if cache.get(doi, {}).get("status") not in {"available", "not-found"})
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            for index, (doi, result) in enumerate(executor.map(fetch_abstract, dois), start=1):
                if result.get("status") == "not-checked" and cache.get(doi, {}).get("status") == "available":
                    print(f"{index}/{len(dois)} {doi}: refresh failed; existing successful source preserved", flush=True)
                    continue
                cache[doi] = result
                atomic_json(cache_path, cache)
                print(f"{index}/{len(dois)} {doi}: {result['status']}", flush=True)
    overrides_path = PROJECT / "content" / "reference-enrichment.json"
    overrides = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path.exists() else {}
    publisher_path = PROJECT / "content" / "reference-publisher-enrichment.json"
    if publisher_path.exists():
        overrides.update(json.loads(publisher_path.read_text(encoding="utf-8")))
    publisher_cache_path = PROJECT / "content" / "reference-publisher-cache.json"
    publisher_cache = json.loads(publisher_cache_path.read_text(encoding="utf-8")) if publisher_cache_path.exists() else {}
    database_path = PROJECT / "content/reference-database-cache.json"
    database_cache = json.loads(database_path.read_text(encoding="utf-8")) if database_path.exists() else {}
    supplemental_attempts = {}
    for name in ["reference-semantic-scholar-attempts.json", "reference-europe-pmc-attempts.json", "reference-eric-attempts.json", "reference-openaire-attempts.json", "reference-doaj-attempts.json", "reference-ebsco-attempts.json", "reference-curated-source-attempts.json"]:
        attempt_path = PROJECT / "content" / name
        if attempt_path.exists():
            for key, attempt in json.loads(attempt_path.read_text(encoding="utf-8")).items():
                supplemental_attempts.setdefault(key, []).append(attempt)
    translations_path = PROJECT / "content" / "reference-abstract-translations.json"
    abstract_translations = json.loads(translations_path.read_text(encoding="utf-8")) if translations_path.exists() else {}
    relationship_path = PROJECT / "content" / "reference-relationship-overrides.json"
    relationships = json.loads(relationship_path.read_text(encoding="utf-8")) if relationship_path.exists() else {}
    totals = {"papers": len(papers), "references": 0, "citations": 0, "ambiguous": 0, "abstractsAvailable": 0, "abstractTranslationsZh": 0, "abstractSummariesZh": 0, "identityWarnings": 0}
    for path, paper, references in zip(paths, papers, all_references, strict=True):
        for reference in references:
            if reference["doi"] in cache and cache[reference["doi"]].get("status") != "not-checked":
                metadata = cache[reference["doi"]]
                normalize = lambda value: re.sub(r"\W+", " ", value.casefold()).strip()
                source_title = normalize(reference["title"])
                metadata_title = normalize(metadata.get("metadataTitle", ""))
                similarity = difflib.SequenceMatcher(None, source_title, metadata_title).ratio()
                if metadata_title and similarity < 0.55:
                    reference["identityStatus"] = "title-mismatch"
                    totals["identityWarnings"] += 1
                else:
                    reference["identityStatus"] = "verified" if metadata_title else "not-checked"
                    reference["abstract"].update({key: value for key, value in metadata.items() if key in reference["abstract"]})
            enrichment = overrides.get(reference["doi"] or reference["id"], {})
            if enrichment and reference["identityStatus"] != "title-mismatch":
                reference["abstract"].update(enrichment.get("abstract", {}))
            publisher = publisher_cache.get(reference["doi"], {})
            if publisher.get("status") == "available" and reference["identityStatus"] != "title-mismatch":
                reference["abstract"].update({key: publisher[key] for key in ["status", "originalText", "sourceUrl", "sourceType", "checkedAt"]})
            database = database_cache.get(reference["doi"] or reference["id"], {})
            database_bound = bool(reference["doi"]) or database.get("sourceTextSha256") == hashlib.sha256(reference["sourceText"].encode()).hexdigest()
            if database.get("status") == "available" and database_bound and reference["abstract"]["status"] != "available" and reference["identityStatus"] != "title-mismatch":
                reference["abstract"].update({key: database[key] for key in ["status", "originalText", "sourceUrl", "sourceType", "checkedAt"]})
                if database.get("abstractOrigin"):
                    reference["abstract"]["abstractOrigin"] = database["abstractOrigin"]
                reference["identityStatus"] = "verified"
            translation = abstract_translations.get(reference["doi"] or reference["id"], {})
            full_source = publisher if publisher.get("status") == "available" else cache.get(reference["doi"], {})
            if full_source.get("status") != "available":
                full_source = database
            if full_source.get("status") == "available" and database_bound and reference["identityStatus"] != "title-mismatch" and translation:
                source_sha = hashlib.sha256(full_source["originalText"].encode("utf-8")).hexdigest()
                if translation.get("sourceSha256") == source_sha and translation.get("faithfulZh"):
                    reference["abstract"].update({"faithfulZh": translation["faithfulZh"], "translationSourceSha256": source_sha, "translationStatus": "ai-draft"})
            if reference["identityStatus"] == "title-mismatch":
                reference["abstract"]["retrievalReason"] = "書目標題與 DOI 紀錄不一致；未確認文獻身分前，不套用其他文章的摘要。"
            elif not reference["abstract"].get("faithfulZh") and reference["abstract"]["status"] != "available":
                attempts = [cache.get(reference["doi"], {}), publisher, database] + supplemental_attempts.get(reference["doi"] or reference["id"], [])
                labels = {"crossref": "Crossref", "publisher": "出版社公開頁", "author": "作者機構頁", "openalex": "OpenAlex", "semantic-scholar": "Semantic Scholar", "europe-pmc": "Europe PMC", "eric": "ERIC", "openaire": "OpenAIRE", "doaj": "DOAJ", "ebsco": "EBSCO"}
                checked = list(dict.fromkeys(labels[attempt["sourceType"]] for attempt in attempts if attempt.get("sourceType") in labels and attempt.get("checkedAt")))
                prefix = "已查詢「" + "、".join(checked) + "」。" if checked else ""
                blocked = any(any(word in attempt.get("error", "") for word in ["403", "429", "504", "timed out"]) for attempt in attempts)
                identity_failed = any("identity did not match" in attempt.get("error", "") for attempt in attempts)
                if not reference["doi"]:
                    reason = "依標題、作者與年份搜尋後，尚未取得可安全對應的來源摘要；書籍、網頁或報告也可能沒有正式 Abstract。"
                else:
                    reason = "目前查詢來源未提供可核對的摘要；這不代表原文一定沒有 Abstract。"
                if blocked:
                    reason += "部分來源有存取限制、流量限制或連線逾時。"
                if identity_failed:
                    reason += "部分資料庫紀錄與此筆書目身分不符，已排除，不套用其摘要。"
                reference["abstract"]["retrievalReason"] = prefix + reason
            # Display a short source excerpt, not a republication of the full
            # publisher abstract. The complete cached source stays local.
            reference["abstract"]["originalText"] = " ".join(reference["abstract"]["originalText"].split()[:25])
        citations = citation_index(paper, references)
        references_by_id = {reference["id"]: reference for reference in references}
        for citation in citations:
            if citation["matchStatus"] != "matched":
                continue
            doi = references_by_id[citation["referenceIds"][0]]["doi"]
            relation = relationships.get(citation["segmentId"], {}).get(doi, {})
            if relation:
                if not relation.get("sourceQuote") or relation["sourceQuote"] not in citation["sourceContext"]:
                    continue
                if not isinstance(relation.get("relationshipZh"), str) or not relation["relationshipZh"].strip():
                    raise ValueError("Invalid reference relationship override")
                citation["relationshipZh"] = relation["relationshipZh"]
        paper["references"] = references
        paper["citations"] = citations
        atomic_json(path, paper)
        totals["references"] += len(references)
        totals["citations"] += len(citations)
        totals["ambiguous"] += sum(item["matchStatus"] == "ambiguous" for item in citations)
        totals["abstractsAvailable"] += sum(item["abstract"]["status"] == "available" for item in references)
        totals["abstractSummariesZh"] += sum(bool(item["abstract"]["summaryZh"]) for item in references)
        totals["abstractTranslationsZh"] += sum(bool(item["abstract"].get("faithfulZh")) for item in references)
        print(f"{paper['id']}: {len(references)} references, {len(citations)} citations", flush=True)
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    current_dois = {reference["doi"] for refs in all_references for reference in refs if reference["doi"]}
    errors = sum(cache.get(doi, {}).get("status") == "not-checked" for doi in current_dois)
    if args.fetch_abstracts and errors:
        print(f"Abstract retrieval did not complete for {errors} DOI records; existing successful results were preserved.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
