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
    - FLAME_API.md              (Flame 2026 Python API cheatsheet + patterns)
    - docs/flame_vocabulary.md  (editorial terms → API mapping)
    - docs/flame_api_full.md    (full auto-generated API reference)
    - Any other .md in docs/

The index is stored in rag/index/ and committed to git so that
users who clone the repo get a ready-to-use index without rebuilding.

Rebuild the index whenever you change the docs:
    python rag/build_index.py

First run downloads the embedding model (~130 MB from HuggingFace, once).
"""

import os
import re
import sys

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    # Split on level-1, 2 or level-3 headers
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
        for fname in sorted(os.listdir(DOCS_DIR)):
            if fname.endswith('.md'):
                paths.append(os.path.join(DOCS_DIR, fname))

    return paths


# ── Embedding ──────────────────────────────────────────────────────────────────

def _make_embedding_fn():
    """
    Returns a ChromaDB-compatible embedding function using the BGE model.
    Downloads the model on first use (~130 MB, cached in ~/.cache/huggingface/).
    """
    from rag.config import EMBEDDING_MODEL
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        print(f"  Embedding model : {EMBEDDING_MODEL}")
        print(f"  (downloading from HuggingFace on first run — cached afterwards)")
        fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        # Warm-up probe so any download happens now, not silently during indexing
        fn(["probe"])
        print(f"  Embedding model : ready ✓")
        return fn
    except ImportError:
        print("  ERROR: sentence-transformers not installed.")
        print("  Run:   pip install sentence-transformers")
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR loading embedding model: {e}")
        sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────────

def build():
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed.\nRun: pip install chromadb")
        sys.exit(1)

    print(f"Building RAG index in: {INDEX_DIR}")
    os.makedirs(INDEX_DIR, exist_ok=True)

    embedding_fn = _make_embedding_fn()

    client = chromadb.PersistentClient(path=INDEX_DIR)

    # Fresh rebuild every time
    try:
        client.delete_collection("flame_docs")
        print("  Deleted existing collection.")
    except Exception:
        pass

    collection = client.create_collection(
        name="flame_docs",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    all_chunks: list[dict] = []
    for doc_path in collect_docs():
        with open(doc_path, 'r', encoding='utf-8') as f:
            text = f.read()
        source = os.path.basename(doc_path)
        chunks = chunk_markdown(text, source)
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
    print()
    print("Next step: commit the index to git so other users don't need to rebuild:")
    print("  git add rag/index/")
    print("  git commit -m 'rag: update pre-built index'")
    print("  git push")


if __name__ == '__main__':
    build()
