#!/usr/bin/env python3
"""
Update re_Requirement_Document content with block references to all linked requirements.

What it does
- Finds all Requirement IDs related to a given document via re_ReqDocBlockReference (source_id -> related_id)
- Builds TechDoc XML content containing a short intro Text block + an <aras:block .../> entry per requirement
- Updates the re_Requirement_Document item's `content` property

Prereqs
- Run from the repo root so `src` is importable, e.g.:
    cd C:\aras-claude-agent
    python update_requirement_document.py
- Ensure src/__init__.py exists (so relative imports in src work)
- Ensure src/config.py + src/auth.py are configured for your Aras instance

Default document ID is set to the Requirement Document ID you used earlier, but you can override it.

Usage
  python update_requirement_document.py
  python update_requirement_document.py --doc-id 543952AF0E7C449BAD92719067FEDAC9
  python update_requirement_document.py --ids-file requirement_ids.json
  python update_requirement_document.py --dry-run

The ids-file format (optional) should be JSON:
  ["ID1","ID2",...]
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

# --- Repo client ---
try:
    from src.api_client import APIClient
except ImportError as e:
    print("ERROR: Could not import src.api_client.APIClient.", file=sys.stderr)
    print("Make sure you are running from the repo root (where the 'src' folder exists),", file=sys.stderr)
    print("and that 'src/__init__.py' exists.", file=sys.stderr)
    raise

def guid() -> str:
    return str(uuid.uuid4()).upper().replace("-", "")

def xml_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def build_document_content(requirement_ids, title, subtitle) -> str:
    """
    Build the TechDoc XML content:
      <Text ...>...</Text>
      <aras:block ... />
      <aras:block ... />
      ...
    """
    text = f"{title}\n\n{subtitle}"
    content = (
        f'<Text xmlns:aras="http://aras.com/ArasTechDoc" '
        f'xmlns="http://www.aras.com/REStandard" '
        f'aras:id="{guid()}">'
        f'<aras:emph xmlns="" emphtype="text">{xml_escape(text)}</aras:emph>'
        f'</Text>'
    )

    for req_id in requirement_ids:
        rid = (req_id or "").strip()
        if not rid:
            continue
        content += (
            f'<aras:block xmlns:aras="http://aras.com/ArasTechDoc" '
            f'ref-id="{rid}" by-reference="external" aras:id="{guid()}" />'
        )
    return content

def load_ids_from_file(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise ValueError("ids-file must be a JSON array of strings, e.g. ['ID1','ID2']")
    return data

def fetch_ids_from_relationships(client: APIClient, rel_endpoint: str, doc_id: str):
    # OData string literal uses single quotes; doc_id is a GUID-like string
    filter_param = f"source_id eq '{doc_id}'"
    res = client.get_items(rel_endpoint, filter_param=filter_param, select="related_id")
    values = res.get("value", [])
    ids = []
    for row in values:
        # "related_id" should be present if select worked; otherwise try common fallbacks
        rid = row.get("related_id") or row.get("related_id@aras.id") or row.get("related_id_id")
        if isinstance(rid, dict) and "id" in rid:
            rid = rid["id"]
        if rid:
            ids.append(str(rid))
    return ids

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", default="543952AF0E7C449BAD92719067FEDAC9",
                        help="ID of the re_Requirement_Document item to update")
    parser.add_argument("--doc-endpoint", default="re_Requirement_Document",
                        help="OData entity set / endpoint name for the document ItemType")
    parser.add_argument("--rel-endpoint", default="re_ReqDocBlockReference",
                        help="OData endpoint for the relationship linking doc->requirement")
    parser.add_argument("--ids-file", default=None,
                        help="Optional JSON file with a list of requirement IDs to use instead of querying relationships")
    parser.add_argument("--title", default="Imported Requirement Document",
                        help="Heading text inserted into the document content")
    parser.add_argument("--subtitle", default="This document contains all requirements from a parsed PDF",
                        help="Subheading text inserted into the document content")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build content and report counts, but do not update Aras")
    parser.add_argument("--output", default="updated_document_content.xml",
                        help="Write the generated content XML to this file (for review/auditing)")
    args = parser.parse_args()

    client = APIClient()

    # Collect requirement IDs
    if args.ids_file:
        ids_path = Path(args.ids_file)
        if not ids_path.exists():
            print(f"ERROR: ids-file not found: {ids_path}", file=sys.stderr)
            return 2
        requirement_ids = load_ids_from_file(ids_path)
        source = f"file: {ids_path}"
    else:
        requirement_ids = fetch_ids_from_relationships(client, args.rel_endpoint, args.doc_id)
        source = f"relationships: {args.rel_endpoint} where source_id={args.doc_id}"

    # De-dupe while preserving order
    seen = set()
    unique_ids = []
    for rid in requirement_ids:
        if rid not in seen:
            seen.add(rid)
            unique_ids.append(rid)

    if not unique_ids:
        print("No requirement IDs found. Nothing to update.")
        print(f"Source: {source}")
        return 1

    # Build content
    content = build_document_content(unique_ids, args.title, args.subtitle)

    # Write for review
    Path(args.output).write_text(content, encoding="utf-8")

    print(f"Found {len(unique_ids)} requirement IDs ({source})")
    print(f"Wrote generated content to: {args.output}")
    print(f"Document endpoint: {args.doc_endpoint}")
    print(f"Document ID: {args.doc_id}")

    if args.dry_run:
        print("Dry run enabled: NOT updating Aras.")
        return 0

    # Update document
    try:
        client.update_item(args.doc_endpoint, args.doc_id, {"content": content}, return_minimal=True)
        print("✅ Document updated successfully.")
        return 0
    except Exception as e:
        print(f"❌ Update failed: {e}", file=sys.stderr)
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
