#!/usr/bin/env python3
"""Validate structured paper evidence and build one integrated study-page HTML."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
BLOCK_TYPES = {"paragraph", "subheading", "note", "bullets", "numbered", "table"}
TOKENS = (
    "__PAGE_TITLE__",
    "__DOCUMENT_TITLE__",
    "__DOCUMENT_SUBTITLE__",
    "__SOURCE_NOTE__",
    "__MERMAID_SOURCE_JSON__",
    "__NODE_DETAILS_JSON__",
    "__STATISTICS_JSON__",
    "__GLOSSARY_JSON__",
    "__DISCUSSIONS_JSON__",
    "__EASY_READ_JSON__",
)


class BuildError(ValueError):
    """Raised when the input cannot safely produce a complete page."""


def require_string(
    mapping: dict[str, Any], key: str, context: str, *, allow_empty: bool = False, max_length: int = 20_000
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise BuildError(f"{context}.{key} must be a string")
    value = value.strip()
    if not value and not allow_empty:
        raise BuildError(f"{context}.{key} must not be empty")
    if len(value) > max_length:
        raise BuildError(f"{context}.{key} exceeds the {max_length}-character limit")
    return value


def validate_color(value: Any, context: str) -> str:
    if not isinstance(value, str) or not HEX_COLOR.fullmatch(value):
        raise BuildError(f"{context}.color must be a six-digit hex color such as #315F91")
    return value.upper()


def validate_string_list(value: Any, context: str, *, minimum: int = 1, maximum: int = 100) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise BuildError(f"{context} must contain between {minimum} and {maximum} strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise BuildError(f"{context}[{index}] must be a non-empty string")
        if len(item) > 20_000:
            raise BuildError(f"{context}[{index}] exceeds the 20,000-character limit")
        result.append(item.strip())
    return result


def validate_blocks(raw_blocks: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise BuildError(f"{context} must be a non-empty array")
    if len(raw_blocks) > 100:
        raise BuildError(f"{context} exceeds the 100-block limit")

    blocks: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_blocks):
        block_context = f"{context}[{index}]"
        if not isinstance(raw, dict):
            raise BuildError(f"{block_context} must be an object")
        block_type = require_string(raw, "type", block_context, max_length=32)
        if block_type not in BLOCK_TYPES:
            raise BuildError(f"{block_context}.type must be one of {', '.join(sorted(BLOCK_TYPES))}")

        if block_type in {"paragraph", "subheading", "note"}:
            blocks.append({"type": block_type, "text": require_string(raw, "text", block_context)})
            continue

        if block_type in {"bullets", "numbered"}:
            blocks.append(
                {"type": block_type, "items": validate_string_list(raw.get("items"), f"{block_context}.items")}
            )
            continue

        headers = validate_string_list(raw.get("headers"), f"{block_context}.headers", minimum=2, maximum=12)
        raw_rows = raw.get("rows")
        if not isinstance(raw_rows, list) or not raw_rows or len(raw_rows) > 200:
            raise BuildError(f"{block_context}.rows must contain between 1 and 200 rows")
        rows: list[list[str]] = []
        for row_index, raw_row in enumerate(raw_rows):
            row = validate_string_list(
                raw_row, f"{block_context}.rows[{row_index}]", minimum=len(headers), maximum=len(headers)
            )
            rows.append(row)
        blocks.append({"type": "table", "headers": headers, "rows": rows})
    return blocks


def validate_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BuildError("input root must be a JSON object")

    payload: dict[str, Any] = {
        "page_title": require_string(raw, "page_title", "root", max_length=300),
        "title": require_string(raw, "title", "root", max_length=500),
        "subtitle": require_string(raw, "subtitle", "root", max_length=1_000),
        "source_note": require_string(raw, "source_note", "root", max_length=2_000),
        "mermaid": require_string(raw, "mermaid", "root", max_length=200_000),
    }

    first_line = payload["mermaid"].lstrip().splitlines()[0].strip().lower()
    if not (first_line.startswith("flowchart ") or first_line.startswith("graph ")):
        raise BuildError("root.mermaid must begin with a Mermaid flowchart or graph declaration")
    if re.search(r"%%\s*\{", payload["mermaid"]):
        raise BuildError("Mermaid configuration directives are not allowed")

    raw_details = raw.get("node_details")
    if not isinstance(raw_details, dict) or not raw_details:
        raise BuildError("root.node_details must be a non-empty object")
    details: dict[str, dict[str, str]] = {}
    for node_id, item in raw_details.items():
        context = f"root.node_details[{node_id!r}]"
        if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id):
            raise BuildError(f"{context} uses an invalid node ID")
        if not isinstance(item, dict):
            raise BuildError(f"{context} must be an object")
        declaration = r"(?<![A-Za-z0-9_-])" + re.escape(node_id) + r"(?=\s*(?:\[|\(|\{))"
        if not re.search(declaration, payload["mermaid"]):
            raise BuildError(f"node detail {node_id!r} has no matching Mermaid declaration")
        details[node_id] = {
            "title": require_string(item, "title", context, max_length=300),
            "summary": require_string(item, "summary", context, max_length=2_000),
            "explanation": require_string(item, "explanation", context),
            "page": require_string(item, "page", context, max_length=500),
            "color": validate_color(item.get("color"), context),
        }
    payload["node_details"] = details

    raw_statistics = raw.get("statistics")
    if not isinstance(raw_statistics, list) or len(raw_statistics) > 50:
        raise BuildError("root.statistics must be an array with at most 50 entries")
    statistics: list[dict[str, str]] = []
    for index, item in enumerate(raw_statistics):
        context = f"root.statistics[{index}]"
        if not isinstance(item, dict):
            raise BuildError(f"{context} must be an object")
        statistics.append(
            {
                "name": require_string(item, "name", context, max_length=300),
                "label": require_string(item, "label", context, allow_empty=True, max_length=100),
                "meaning": require_string(item, "meaning", context, max_length=4_000),
                "reason": require_string(item, "reason", context, max_length=4_000),
                "caution": require_string(item, "caution", context, allow_empty=True, max_length=4_000),
                "color": validate_color(item.get("color"), context),
            }
        )
    payload["statistics"] = statistics

    raw_glossary = raw.get("glossary")
    if not isinstance(raw_glossary, list) or len(raw_glossary) > 100:
        raise BuildError("root.glossary must be an array with at most 100 entries")
    glossary: list[dict[str, str]] = []
    seen_terms: set[str] = set()
    for index, item in enumerate(raw_glossary):
        context = f"root.glossary[{index}]"
        if not isinstance(item, dict):
            raise BuildError(f"{context} must be an object")
        term = require_string(item, "term", context, max_length=100)
        normalized = term.casefold()
        if normalized in seen_terms:
            raise BuildError(f"duplicate glossary term: {term}")
        seen_terms.add(normalized)
        glossary.append(
            {
                "term": term,
                "full_name": require_string(item, "full_name", context, max_length=500),
                "explanation": require_string(item, "explanation", context, max_length=8_000),
                "page": require_string(item, "page", context, max_length=500),
                "color": validate_color(item.get("color"), context),
            }
        )
    payload["glossary"] = glossary

    raw_discussions = raw.get("discussions")
    if not isinstance(raw_discussions, list) or not 4 <= len(raw_discussions) <= 5:
        raise BuildError("root.discussions must contain four core entries and at most one optional fifth entry")
    discussions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_discussions):
        context = f"root.discussions[{index}]"
        if not isinstance(item, dict):
            raise BuildError(f"{context} must be an object")
        discussions.append(
            {
                "title": require_string(item, "title", context, max_length=500),
                "question": require_string(item, "question", context, max_length=4_000),
                "blocks": validate_blocks(item.get("blocks"), f"{context}.blocks"),
                "page": require_string(item, "page", context, max_length=500),
            }
        )
    payload["discussions"] = discussions

    raw_easy = raw.get("easy_read")
    if not isinstance(raw_easy, dict):
        raise BuildError("root.easy_read must be an object")
    raw_sections = raw_easy.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections or len(raw_sections) > 50:
        raise BuildError("root.easy_read.sections must contain between 1 and 50 sections")
    easy_sections: list[dict[str, Any]] = []
    for index, item in enumerate(raw_sections):
        context = f"root.easy_read.sections[{index}]"
        if not isinstance(item, dict):
            raise BuildError(f"{context} must be an object")
        easy_sections.append(
            {
                "title": require_string(item, "title", context, max_length=500),
                "blocks": validate_blocks(item.get("blocks"), f"{context}.blocks"),
            }
        )
    payload["easy_read"] = {
        "intro": require_string(raw_easy, "intro", "root.easy_read", max_length=8_000),
        "sections": easy_sections,
    }
    return payload


def script_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_html(payload: dict[str, Any], template_path: Path) -> str:
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot read template {template_path}: {exc}") from exc
    replacements = {
        "__PAGE_TITLE__": html.escape(payload["page_title"]),
        "__DOCUMENT_TITLE__": html.escape(payload["title"]),
        "__DOCUMENT_SUBTITLE__": html.escape(payload["subtitle"]),
        "__SOURCE_NOTE__": html.escape(payload["source_note"]),
        "__MERMAID_SOURCE_JSON__": script_json(payload["mermaid"]),
        "__NODE_DETAILS_JSON__": script_json(payload["node_details"]),
        "__STATISTICS_JSON__": script_json(payload["statistics"]),
        "__GLOSSARY_JSON__": script_json(payload["glossary"]),
        "__DISCUSSIONS_JSON__": script_json(payload["discussions"]),
        "__EASY_READ_JSON__": script_json(payload["easy_read"]),
    }
    output = template
    for token, value in replacements.items():
        if token not in output:
            raise BuildError(f"template is missing required token {token}")
        output = output.replace(token, value)
    remaining = [token for token in TOKENS if token in output]
    if remaining:
        raise BuildError(f"unreplaced template tokens: {', '.join(remaining)}")
    if "<!doctype html>" not in output[:100].lower() or "</html>" not in output.lower():
        raise BuildError("generated output failed the HTML structure check")
    return output


def atomic_write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise BuildError(f"output already exists: {path}; pass --force only if replacement is intended")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = handle.name
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
        raise BuildError(f"cannot write output {path}: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path, help="UTF-8 JSON content file")
    parser.add_argument("output_html", type=Path, nargs="?", help="destination HTML file")
    parser.add_argument("--force", action="store_true", help="replace an existing destination")
    parser.add_argument("--validate-only", action="store_true", help="validate input without writing HTML")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with args.input_json.open("r", encoding="utf-8") as handle:
            payload = validate_payload(json.load(handle))
        if args.validate_only:
            print(
                "valid: "
                f"nodes={len(payload['node_details'])}; statistics={len(payload['statistics'])}; "
                f"glossary={len(payload['glossary'])}; discussions={len(payload['discussions'])}; "
                f"easy_sections={len(payload['easy_read']['sections'])}"
            )
            return 0
        if args.output_html is None:
            raise BuildError("output_html is required unless --validate-only is used")
        if args.output_html.suffix.lower() not in {".html", ".htm"}:
            raise BuildError("output filename must end in .html or .htm")
        template = Path(__file__).resolve().parent.parent / "assets" / "integrated-study-template.html"
        document = build_html(payload, template)
        destination = args.output_html.expanduser().resolve()
        atomic_write(destination, document, args.force)
    except (OSError, json.JSONDecodeError, BuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"created: {destination}")
    print(
        f"nodes={len(payload['node_details'])}; statistics={len(payload['statistics'])}; "
        f"glossary={len(payload['glossary'])}; discussions={len(payload['discussions'])}; "
        f"easy_sections={len(payload['easy_read']['sections'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
