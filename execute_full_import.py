#!/usr/bin/env python3
"""
Import - Requirements and Requirement Document

This script imports parsed content from a PDF into Aras Innovator
by calling the same API client used by the aras-claude-agent project
without running through the Claude Agent UI itself

PREREQUISITES:
1. import_sequence.json must be in the same directory as this script
2. aras-claude-agent src/ package must be present (this repo layout)
3. src/auth.py + src/config.py must be configured to authenticate (same as MCP server)
   - i.e., whatever get_bearer_token() expects is already set up for your MCP server.

USAGE (from repo root, where this script lives):
    python execute_full_import.py

WHAT THIS DOES:
- Creates requirement items (re_Requirement)
- Updates each with the generated XML content (content property)
- Creates relationships to document Requirement Document via re_ReqDocBlockReference
"""

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Tuple

def guid() -> str:
    return str(uuid.uuid4()).upper().replace("-", "")

# Constants (from your original script)
DOC_ID = "543952AF0E7C449BAD92719067FEDAC9"  #ID of the document -- replace as appropriate
REQ_MANAGED_BY = "5C1E015B631946D3AEE0B69D52070C42"  #ID of the managed by Identity (Requirements Manager in this case)
REQ_DOC_TYPE = "8DF7037346A64816B8BBD8700AFCFE15"  #ID of the XML schema (this is RE_Standard)

REQ_ITEMTYPE = "re_Requirement"
REL_ITEMTYPE = "re_ReqDocBlockReference"

def _xml_escape(s: str) -> str:
    s = s or ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def generate_requirement_xml(req_text: str, req_id: str, chapter: str, req_number: str, req_title: str) -> str:
    """Generate XML content for requirement"""
    g1, g2, g3, g4, g5, g6 = guid(), guid(), guid(), guid(), guid(), guid()

    req_text = _xml_escape(req_text)
    chapter = _xml_escape(chapter)
    req_title = _xml_escape(req_title)

    xml = (
        f'<Requirement xmlns:aras="http://aras.com/ArasTechDoc" '
        f'xmlns="http://www.aras.com/REStandard" aras:id="{g1}" reqId="{req_id}">'
        f'<Requirement-Info aras:id="{g2}">'
        f'<Requirement-Chapter aras:id="{g3}"><aras:emph emphtype="text">{chapter}</aras:emph></Requirement-Chapter>'
        f'<Requirement-Title aras:id="{g4}"><aras:emph emphtype="text">{req_title}</aras:emph></Requirement-Title>'
        f'<Requirement-Number aras:id="{g5}"><aras:emph emphtype="text">{req_number}</aras:emph></Requirement-Number>'
        f'</Requirement-Info>'
        f'<Text aras:id="{g6}"><aras:emph xmlns="" emphtype="text">{req_text}</aras:emph></Text>'
        f'</Requirement>'
    )
    return xml

def _script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))

def _load_json(filename: str) -> Any:
    path = os.path.join(_script_dir(), filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(filename: str, data: Any) -> str:
    path = os.path.join(_script_dir(), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path

def _ensure_repo_imports():
    """
    Ensure we can import the repo's src.api_client as a package (relative imports inside it).
    This script is expected to live in the repo root (same level as src/).
    """
    root = _script_dir()
    if root not in sys.path:
        sys.path.insert(0, root)

def _get_api_client():
    """
    Import and instantiate APIClient from the repo.

    api_client.py uses relative imports (from .auth / .config),
    so it must be imported as src.api_client (package import).
    """
    _ensure_repo_imports()

    try:
        from src.api_client import APIClient  # type: ignore
    except Exception as e:
        raise ImportError(
            "Could not import src.api_client.APIClient.\n"
            "Make sure:\n"
            "  - this script is in the repo root (alongside the 'src' folder)\n"
            "  - 'src' contains an __init__.py file (so it's a package)\n"
            "  - src/auth.py and src/config.py exist and are configured\n"
            f"\nOriginal import error: {e}"
        ) from e

    client = APIClient()
    ok = client.authenticate()
    if not ok or not getattr(client, "token", None):
        raise RuntimeError("Authentication failed (no bearer token). Check src/auth.py configuration.")
    return client

def _extract_id(create_response: Any) -> str:
    """
    Aras OData create responses often include an 'id' property. Be defensive.
    """
    if isinstance(create_response, dict):
        for k in ("id", "ID", "Id"):
            if k in create_response and create_response[k]:
                return str(create_response[k])

        # Some APIs wrap results
        if "value" in create_response and isinstance(create_response["value"], list) and create_response["value"]:
            v0 = create_response["value"][0]
            if isinstance(v0, dict):
                for k in ("id", "ID", "Id"):
                    if k in v0 and v0[k]:
                        return str(v0[k])

    raise KeyError(f"Could not find created item id in response: {create_response}")

def execute_import(client, import_sequence: List[Dict[str, Any]], start_index: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Execute the batch import.

    start_index=3 skips the first 3 already imported requirements, matching your previous runs.
    """
    to_import = max(0, len(import_sequence) - start_index)
    print(f"Starting import of {to_import} requirements...")
    print("=" * 80)

    created: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for idx in range(start_index, len(import_sequence)):
        req = import_sequence[idx]
        seq_num = idx + 1  # human-friendly

        req_number = req.get("req_number", f"IDX-{idx}")
        try:
            print(f"\n[{seq_num}/{len(import_sequence)}] Processing: {req_number}")

            # Step 1: Create requirement
            create_data = {
                "req_title": (req.get("title") or "")[:255],
                "req_category": req.get("category"),
                "managed_by_id": REQ_MANAGED_BY,
                "classification": "Requirement",
                "req_document_type": REQ_DOC_TYPE,
            }

            print("  Creating requirement...")
            created_req = client.create_item(REQ_ITEMTYPE, create_data)
            req_id = _extract_id(created_req)
            print(f"  ✓ Created with ID: {req_id}")

            # Step 2: Update XML content
            print("  Generating XML content...")
            xml = generate_requirement_xml(
                req_text=req.get("text") or "",
                req_id=req_id,
                chapter=req.get("chapter") or "",
                req_number=req.get("req_number") or "",
                req_title=req.get("title") or "",
            )

            print("  Updating content...")
            # Use return_minimal to avoid pulling full object back (faster/less payload)
            client.update_item(REQ_ITEMTYPE, req_id, {"content": xml}, action="edit", return_minimal=True)
            print("  ✓ Content updated")

            # Step 3: Create relationship to document
            print("  Creating relationship...")
            rel_data = {
                "source_id": DOC_ID,
                "related_id": req_id,
                "reference_id": req_id,
                "behavior": "hard_fixed",
            }
            client.create_item(REL_ITEMTYPE, rel_data)
            print("  ✓ Relationship created")

            created.append(
                {
                    "req_number": req.get("req_number"),
                    "req_id": req_id,
                    "title": req.get("title"),
                    "section": req.get("section"),
                }
            )
            print(f"✅ SUCCESS: {req_number}")

            # Small delay every 10 items to avoid overwhelming the API
            imported_count = (idx - start_index) + 1
            if imported_count % 10 == 0:
                print("\n  Pausing for 2 seconds...")
                time.sleep(2)

        except Exception as e:
            print(f"❌ FAILED: {req_number}")
            print(f"   Error: {e}")
            failed.append({"req_number": req.get("req_number"), "error": str(e), "section": req.get("section")})
            continue

    return created, failed

def main():
    print(__doc__)
    print()

    seq_path = os.path.join(_script_dir(), "import_sequence.json")
    if not os.path.exists(seq_path):
        print("ERROR: import_sequence.json not found next to this script.")
        print("Expected location:", seq_path)
        sys.exit(1)

    print("Loading import sequence...")
    import_sequence = _load_json("import_sequence.json")
    print(f"✓ Loaded {len(import_sequence)} requirements")
    print(f"  - Already imported: 3")
    print(f"  - To import: {len(import_sequence) - 3}")
    print()

    # Category breakdown
    categories: Dict[str, int] = {}
    for req in import_sequence[3:]:
        cat = req.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1

    print("Breakdown by category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat:20}: {count:3} requirements")
    print()

    print("=" * 80)
    print("INITIALIZING ARAS API CLIENT (repo: src/api_client.py)")
    print("=" * 80)
    print()

    client = _get_api_client()
    print("✓ Authenticated successfully")
    print()

    print("=" * 80)
    print("READY TO START IMPORT")
    print("=" * 80)
    print()
    print(f"This will import {len(import_sequence) - 3} requirements into:")
    print(f"  Document ID: {DOC_ID}")
    print(f"  Relationship ItemType: {REL_ITEMTYPE}")
    print()
    print("Estimated time: 5-8 minutes")
    print()

    # No interactive prompts (terminal-friendly). Set DRY_RUN=1 to test without writing.
    if os.getenv("DRY_RUN", "").strip() == "1":
        print("DRY_RUN=1 set. Exiting without making changes.")
        sys.exit(0)

    start_time = time.time()
    created, failed = execute_import(client, import_sequence, start_index=3)
    end_time = time.time()

    print()
    print("=" * 80)
    print("IMPORT COMPLETE")
    print("=" * 80)
    print()
    print(f"Time taken: {end_time - start_time:.1f} seconds")
    print()
    print(f"✅ Successfully imported: {len(created)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"📄 Total in document: {len(created) + 3} (including 3 previously imported)")
    print()

    results = {
        "summary": {
            "total_attempted": len(import_sequence) - 3,
            "successful": len(created),
            "failed": len(failed),
            "time_seconds": end_time - start_time,
        },
        "created": created,
        "failed": failed,
    }

    out_path = _save_json("import_results.json", results)
    print(f"Results saved to: {out_path}")
    print()

    if failed:
        print("Failed requirements:")
        for item in failed[:10]:
            print(f"  - {item['req_number']}: {item['error']}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more (see import_results.json)")
    else:
        print("🎉 All requirements imported successfully!")
    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
