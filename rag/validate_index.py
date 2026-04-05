"""
validate_index.py
=================
B6 — Validates the local ChromaDB RAG index for integrity and coverage.

Checks:
  1. Pattern count and source model breakdown
  2. Chunks with missing or malformed metadata
  3. Patterns added by non-whitelisted (read-only) models
  4. Coverage by Flame API category

Usage:
    cd <flame-mcp repo root>
    source .venv/bin/activate
    python rag/validate_index.py

Exit codes:
    0  — all checks passed
    1  — warnings found (non-fatal)
    2  — critical errors (missing index, corrupt chunks)
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import Any

ROOT      = Path(__file__).parent.parent
INDEX_DIR = ROOT / 'rag' / 'index'
API_DOC   = ROOT / 'FLAME_API.md'
CONFIG    = ROOT / 'config.json'

# ── Allowed model substrings (mirrors flame_mcp_server.py WRITE_ALLOWED_MODELS)
_DEFAULT_WRITE_ALLOWED = {
    "claude-opus", "claude-sonnet", "claude-3-5-sonnet",
    "claude-3-7-sonnet", "claude-sonnet-4", "claude-sonnet-4-6", "claude-opus-4",
}

# ── Flame API categories to check coverage for
_CATEGORIES = {
    "projects":  ["project", "workspace"],
    "libraries": ["library", "reel"],
    "clips":     ["clip", "sequence", "segment"],
    "batch":     ["batch", "node", "schematic"],
    "export":    ["export", "render", "publish"],
    "import":    ["import", "media", "conform"],
}


def _load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {}


def _get_write_allowed() -> set:
    cfg_list = _load_config().get("write_allowed_models")
    if cfg_list:
        return {m.lower() for m in cfg_list}
    return _DEFAULT_WRITE_ALLOWED


def _get_embedding_fn() -> Any:
    from rag.config import EMBEDDING_MODEL
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)


def _get_collection() -> Any | None:
    if not INDEX_DIR.is_dir():
        return None
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(INDEX_DIR))
        return client.get_collection("flame_docs", embedding_function=_get_embedding_fn())
    except Exception as e:
        print(f"  ❌ Could not open collection: {e}")
        return None


def _check_index(collection: Any, write_allowed: set) -> tuple[int, int]:
    """
    Inspect all chunks in the collection.
    Returns (warning_count, error_count).
    """
    warnings = 0
    errors   = 0

    try:
        total = collection.count()
    except Exception as e:
        print(f"  ❌ Cannot count collection: {e}")
        return 0, 1

    print(f"\n{'─'*50}")
    print(f"  📦 Total chunks in index : {total}")

    if total == 0:
        print("  ❌ Index is empty — run python rag/build_index.py")
        return 0, 1

    # Fetch all chunks (metadata only, no embeddings)
    try:
        result = collection.get(include=["documents", "metadatas"])
    except Exception as e:
        print(f"  ❌ Cannot fetch chunks: {e}")
        return 0, 1

    docs      = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    ids       = result.get("ids") or []

    # ── 1. Metadata completeness ───────────────────────────────────────────────
    missing_meta = 0
    for i, meta in enumerate(metadatas):
        if not meta or not meta.get("source") or not meta.get("section"):
            missing_meta += 1
            if missing_meta <= 5:  # show first 5 only
                print(f"  ⚠️  Missing metadata on chunk: {ids[i] if i < len(ids) else '?'}")
    if missing_meta > 0:
        print(f"  ⚠️  {missing_meta} chunk(s) with incomplete metadata → review needed")
        warnings += missing_meta

    # ── 2. Source model breakdown (from <!-- model:... --> tags in documents) ──
    model_re  = re.compile(r'<!--\s*model:([\w\.\-:]+)\s+date:[\d\-]+\s*-->')
    auto_total    = 0
    model_counts: dict[str, int] = {}
    unauthorized: list[str]      = []

    for doc in docs:
        m = model_re.search(doc or "")
        if m:
            auto_total += 1
            model_id = m.group(1).lower()
            model_counts[model_id] = model_counts.get(model_id, 0) + 1
            if not any(allowed in model_id for allowed in write_allowed):
                unauthorized.append(model_id)

    print(f"\n  🧠 Auto-learned patterns  : {auto_total}")
    if model_counts:
        for model_id, count in sorted(model_counts.items(), key=lambda x: -x[1]):
            badge = "✅" if any(a in model_id for a in write_allowed) else "⛔"
            print(f"     {badge} {model_id:<45} {count} chunk(s)")

    if unauthorized:
        unauth_set = set(unauthorized)
        print(f"\n  ⛔ {len(unauthorized)} chunk(s) written by unauthorized model(s): {unauth_set}")
        print("     These may contain hallucinated API paths.")
        print("     Remove them from FLAME_API.md and rebuild the index.")
        warnings += len(unauthorized)

    # ── 3. Coverage by Flame API category ─────────────────────────────────────
    print(f"\n{'─'*50}")
    print("  📊 Coverage by category:\n")

    all_text = " ".join((doc or "").lower() for doc in docs)
    for category, keywords in _CATEGORIES.items():
        hits = sum(all_text.count(kw) for kw in keywords)
        if   hits >= 20: bar = "████████ 100%"
        elif hits >= 10: bar = "██████░░  75%"
        elif hits >= 5:  bar = "████░░░░  50%"
        elif hits >= 1:  bar = "██░░░░░░  25%"
        else:            bar = "░░░░░░░░   0%"
        note = "" if hits >= 5 else "  ← sparse"
        print(f"     {category:<12} {bar}{note}")
        if hits < 5:
            warnings += 1

    # ── 4. Doc file sizes (quick check that sources aren't empty) ─────────────
    print(f"\n{'─'*50}")
    print("  📄 Source documents:\n")
    doc_sources = sorted({(meta or {}).get("source", "?") for meta in metadatas})
    for src in doc_sources:
        src_path = ROOT / src
        if not src_path.exists():
            src_path = ROOT / "docs" / src
        if src_path.exists():
            kb = src_path.stat().st_size // 1024
            print(f"     ✅ {src:<40} {kb} KB")
        else:
            print(f"     ⚠️  {src:<40} (file not found)")
            warnings += 1

    return warnings, errors


def validate() -> int:
    """Run all validation checks. Returns shell exit code."""
    print("flame-mcp RAG index validator")
    print("=" * 50)

    # ── Guard: index directory exists ─────────────────────────────────────────
    if not INDEX_DIR.is_dir():
        print(f"\n  ❌ Index not found at {INDEX_DIR}")
        print("     Run: python rag/build_index.py")
        return 2

    # ── Load config for write-allowed models ──────────────────────────────────
    write_allowed = _get_write_allowed()

    # ── Load collection ───────────────────────────────────────────────────────
    print("\n  Loading index…")
    collection = _get_collection()
    if collection is None:
        print("  ❌ Could not open 'flame_docs' collection.")
        return 2

    # ── Run checks ────────────────────────────────────────────────────────────
    warnings, errors = _check_index(collection, write_allowed)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*50}")
    if errors > 0:
        print(f"  ❌ Validation FAILED  — {errors} critical error(s), {warnings} warning(s)")
        return 2
    elif warnings > 0:
        print(f"  ⚠️  Validation PASSED with warnings — {warnings} issue(s) found")
        return 1
    else:
        print("  ✅ Validation PASSED — index looks healthy")
        return 0


if __name__ == "__main__":
    # Ensure project root on sys.path so `from rag.config import ...` works
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.exit(validate())
