"""
build_index.py
==============
Indexes documentation files into a local ChromaDB vector database.
Run once after installation, and again whenever docs change.

Usage:
    cd ~/Projects/flame-mcp
    source .venv/bin/activate
    python rag/build_index.py

What it indexes:
    - FLAME_API.md  (Flame 2026 Python API cheatsheet)
    - Any .md files placed in the docs/ folder

The index is stored in rag/index/ (local only, not in git).
"""

import os
import re
import sys

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_DIR = os.path.join(ROOT, 'rag', 'index')
DOCS_DIR  = os.path.join(ROOT, 'docs')

# Documents to always index
PRIMARY_DOCS = [
    os.path.join(ROOT, 'FLAME_API.md'),
]


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_markdown(text: str, source: str) -> list[dict]:
    """
    Split a markdown file into meaningful chunks by section (## headers).
    Each chunk gets an id, the raw text, and metadata (source + section title).
    Chunks shorter than 80 chars are skipped (likely empty headers).
    """
    chunks = []
    # Split on level-2 or level-3 headers
    sections = re.split(r'\n(?=#{1,3} )', text)

    for i, section in enumerate(sections):
        section = section.strip()
        if len(section) < 80:
            continue

        header_match = re.match(r'^#{1,3} (.+)', section)
        header = header_match.group(1).strip() if header_match else f"section_{i}"

        chunks.append({
            'id':       f"{source}::{i}::{header[:40]}",
            'text':     section,
            'metadata': {'source': source, 'section': header},
        })

    return chunks


def collect_docs() -> list[str]:
    """Return all .md files to index."""
    paths = []
    for p in PRIMARY_DOCS:
        if os.path.isfile(p):
            paths.append(p)
        else:
            print(f"  [warn] not found: {p}")

    # Also pick up anything in docs/
    if os.path.isdir(DOCS_DIR):
        for fname in os.listdir(DOCS_DIR):
            if fname.endswith('.md'):
                paths.append(os.path.join(DOCS_DIR, fname))

    return paths


# ── Main ───────────────────────────────────────────────────────────────────────

def build():
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed.\n"
              "Run: pip install chromadb")
        sys.exit(1)

    print(f"Building RAG index in: {INDEX_DIR}")
    os.makedirs(INDEX_DIR, exist_ok=True)

    client = chromadb.PersistentClient(path=INDEX_DIR)

    # Fresh rebuild every time
    try:
        client.delete_collection("flame_docs")
        print("  Deleted existing collection.")
    except Exception:
        pass

    collection = client.create_collection(
        name="flame_docs",
        metadata={"hnsw:space": "cosine"},
    )

    all_chunks: list[dict] = []
    for doc_path in collect_docs():
        with open(doc_path, 'r', encoding='utf-8') as f:
            text = f.read()
        source  = os.path.basename(doc_path)
        chunks  = chunk_markdown(text, source)
        all_chunks.extend(chunks)
        print(f"  {source}: {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks to index — nothing was added.")
        return

    collection.add(
        ids       = [c['id']       for c in all_chunks],
        documents = [c['text']     for c in all_chunks],
        metadatas = [c['metadata'] for c in all_chunks],
    )

    print(f"\nDone. {len(all_chunks)} chunks indexed.")
    print(f"Index location: {INDEX_DIR}")


if __name__ == '__main__':
    build()
