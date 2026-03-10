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
    - Any other .md in docs/    (except ARCHITECTURE.md — project metadata, not API)

The index is stored in rag/index/ and committed to git so that
users who clone the repo get a ready-to-use index without rebuilding.

Rebuild the index whenever you change the docs:
    python rag/build_index.py

First run downloads the embedding model (~570 MB from HuggingFace, once).

Chunking strategy
-----------------
Most .md files are split on ## headers — one chunk per section.

For API reference files (FLAME_API.md, flame_advanced_api.md,
flame_segment_timeline_api.md and similar), sections that list many
methods as bullet lines are further split into groups of METHOD_GROUP_SIZE
methods each. This prevents large class sections (e.g. PySegment with 69
methods) from burying specific method names in retrieval noise.

A section is eligible for method-group chunking when:
  • it contains ≥ METHOD_GROUP_THRESHOLD method bullets, AND
  • its total character count exceeds CHUNK_SPLIT_THRESHOLD
"""

import json
import os
import re
import sys
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_DIR = os.path.join(ROOT, 'rag', 'index')

# Ensure project root is on sys.path so `from rag.config import ...` works
# whether this script is run directly (python rag/build_index.py) or imported.
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
DOCS_DIR  = os.path.join(ROOT, 'docs')

# Documents to always index (processed first, in order)
PRIMARY_DOCS = [
    os.path.join(ROOT, 'FLAME_API.md'),
]

# docs/ files to skip — not API documentation
DOCS_EXCLUDE = {
    'ARCHITECTURE.md',          # project metadata, not useful for RAG queries
    'AUDIT_REPORT_2026-03-10.md',  # audit report, not API docs
}

# ── Chunking config ────────────────────────────────────────────────────────────
METHOD_BULLET     = re.compile(r'^- `\w', re.MULTILINE)  # matches: - `method_name(
METHOD_GROUP_SIZE      = 4     # methods per sub-chunk in API files
METHOD_GROUP_THRESHOLD = 8     # min methods in section to trigger sub-chunking
CHUNK_SPLIT_THRESHOLD  = 700   # min section chars to trigger sub-chunking
MIN_CHUNK_CHARS        = 80    # skip chunks shorter than this


# ── Chunking ───────────────────────────────────────────────────────────────────

def _method_group_chunks(section: str, source: str, section_idx: int) -> list[dict]:
    """
    Split an API section that lists many methods into groups of METHOD_GROUP_SIZE.

    Layout of a typical FLAME_API.md section:
        ## ClassName
        Brief description paragraph.

        - `method_one(...)` — description
        - `method_two(...)` — description
        ...

    Strategy:
      1. Separate the intro text (before the first method bullet).
      2. Split remaining text into individual method entries.
      3. Group entries into batches of METHOD_GROUP_SIZE.
      4. Prepend the section header to each group chunk for context.
         If the intro is short (<150 chars), merge it into the first group.
    """
    header_match = re.match(r'^#{1,3} (.+)', section)
    header       = header_match.group(1).strip() if header_match else f"section_{section_idx}"
    section_name = section.split('\n')[0]          # e.g. "## PySegment"

    first_method = METHOD_BULLET.search(section)
    if not first_method:
        return []  # caller falls back to the whole section

    intro        = section[:first_method.start()].rstrip()
    methods_text = section[first_method.start():]

    # Split on the start of each new bullet entry
    entries = re.split(r'(?m)(?=^- `\w)', methods_text)
    entries = [e.strip() for e in entries if e.strip()]

    groups  = [entries[i:i + METHOD_GROUP_SIZE]
               for i in range(0, len(entries), METHOD_GROUP_SIZE)]

    chunks = []

    if groups:
        if intro.strip() and len(intro.strip()) < 150:
            # Short intro: merge into first group for context
            first_text = intro.strip() + '\n\n' + ''.join(groups[0]).strip()
            chunks.append({
                'id':       f"{source}::{section_idx}::{header[:40]}::g0",
                'text':     first_text,
                'metadata': {'source': source, 'section': header},
            })
            groups = groups[1:]
        elif intro.strip():
            # Long intro: its own chunk
            chunks.append({
                'id':       f"{source}::{section_idx}::{header[:40]}::intro",
                'text':     intro.strip(),
                'metadata': {'source': source, 'section': header},
            })

    for g_idx, group in enumerate(groups):
        group_text = section_name + '\n\n' + ''.join(group).strip()
        if len(group_text.strip()) >= MIN_CHUNK_CHARS:
            chunks.append({
                'id':       f"{source}::{section_idx}::{header[:40]}::g{g_idx + (1 if not (intro.strip() and len(intro.strip()) < 150) else 1)}",
                'text':     group_text,
                'metadata': {'source': source, 'section': header},
            })

    return chunks


def chunk_markdown(text: str, source: str) -> list[dict]:
    """
    Split a markdown file into meaningful chunks by section (## headers).

    For API-heavy sections (many method bullets, large character count),
    further splits into METHOD_GROUP_SIZE-method sub-chunks so individual
    method names are retrievable without noise from unrelated methods.

    Each chunk: {'id': str, 'text': str, 'metadata': {'source', 'section'}}
    Chunks shorter than MIN_CHUNK_CHARS are skipped.
    """
    chunks = []
    sections = re.split(r'\n(?=#{1,3} )', text)

    for i, section in enumerate(sections):
        section = section.strip()
        if len(section) < MIN_CHUNK_CHARS:
            continue

        header_match = re.match(r'^#{1,3} (.+)', section)
        header = header_match.group(1).strip() if header_match else f"section_{i}"

        method_count = len(METHOD_BULLET.findall(section))
        should_split = (
            method_count >= METHOD_GROUP_THRESHOLD
            and len(section) >= CHUNK_SPLIT_THRESHOLD
        )

        if should_split:
            sub = _method_group_chunks(section, source, i)
            if sub:
                chunks.extend(sub)
                continue
            # fallthrough: sub-chunking found nothing, use whole section

        chunks.append({
            'id':       f"{source}::{i}::{header[:40]}",
            'text':     section,
            'metadata': {'source': source, 'section': header},
        })

    return chunks


def collect_docs() -> list[str]:
    """Return all .md files to index, excluding non-API docs."""
    paths = []
    for p in PRIMARY_DOCS:
        if os.path.isfile(p):
            paths.append(p)
        else:
            print(f"  [warn] not found: {p}")

    if os.path.isdir(DOCS_DIR):
        for fname in sorted(os.listdir(DOCS_DIR)):
            if not fname.endswith('.md'):
                continue
            if fname in DOCS_EXCLUDE:
                print(f"  [skip] {fname} (excluded)")
                continue
            paths.append(os.path.join(DOCS_DIR, fname))

    return paths


# ── Embedding ──────────────────────────────────────────────────────────────────

def _make_embedding_fn() -> Any:
    """
    Returns a ChromaDB-compatible embedding function using the BGE model.
    Downloads the model on first use (~570 MB, cached in ~/.cache/huggingface/).
    """
    from rag.config import EMBEDDING_MODEL
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        print(f"  Embedding model : {EMBEDDING_MODEL}")
        print(f"  (downloading from HuggingFace on first run ~570 MB — cached afterwards)")
        fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        fn(["probe"])  # warm-up so download happens now, not silently during indexing
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

def build() -> None:
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

        method_chunks = sum(1 for c in chunks if '::g' in c['id'])
        if method_chunks:
            print(f"  {source}: {len(chunks)} chunks  ({method_chunks} method-group sub-chunks)")
        else:
            print(f"  {source}: {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks to index — nothing was added.")
        return

    # Deduplicate ids (safety net — shouldn't happen with well-formed docs)
    seen = set()
    deduped = []
    for c in all_chunks:
        if c['id'] not in seen:
            seen.add(c['id'])
            deduped.append(c)
    if len(deduped) < len(all_chunks):
        print(f"  [warn] Removed {len(all_chunks) - len(deduped)} duplicate chunk ids.")
    all_chunks = deduped

    collection.add(
        ids       = [c['id']       for c in all_chunks],
        documents = [c['text']     for c in all_chunks],
        metadatas = [c['metadata'] for c in all_chunks],
    )

    # Save plain-text corpus for BM25 (no embeddings needed)
    corpus_path = os.path.join(ROOT, 'rag', 'corpus.json')
    corpus = [
        {'id': c['id'], 'text': c['text'], 'metadata': c['metadata']}
        for c in all_chunks
    ]
    with open(corpus_path, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, separators=(',', ':'))
    print(f"  BM25 corpus saved: {len(corpus)} chunks → rag/corpus.json")

    # Stats
    avg_chars = sum(len(c['text']) for c in all_chunks) // len(all_chunks)
    max_chunk = max(all_chunks, key=lambda c: len(c['text']))
    print(f"\nDone. {len(all_chunks)} chunks indexed.")
    print(f"  avg chunk size : {avg_chars} chars")
    print(f"  largest chunk  : {len(max_chunk['text'])} chars  ({max_chunk['id'][:60]})")
    print(f"Index location: {INDEX_DIR}")
    print()
    print("Next step: commit the updated index and corpus to git:")
    print("  git add rag/corpus.json rag/index/")
    print("  git commit -m 'rag: rebuild index'")
    print("  git push")


if __name__ == '__main__':
    build()
