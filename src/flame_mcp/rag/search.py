"""
search.py
=========
Hybrid search over the local ChromaDB index.

C3 — Hybrid BM25 + semantic retrieval fused via Reciprocal Rank Fusion (RRF).
     BM25 excels at exact Flame API method names; semantic search covers
     synonyms and paraphrased queries. RRF combines both without score calibration.

C4 — HyDE (Hypothetical Document Embedding): the query is expanded with a
     Flame-specific code template before embedding, bridging the gap between
     short natural-language queries and code-heavy documentation chunks.

The index must be built first:
    python rag/build_index.py
"""

import json
import os
import datetime
from typing import Any

_PKG_DIR    = os.path.dirname(os.path.abspath(__file__))            # src/flame_mcp/rag/
ROOT        = os.path.dirname(os.path.dirname(os.path.dirname(_PKG_DIR)))  # repo root
# RAG data lives at <repo>/rag/, outside the Python package, so it is
# shared with build_index.py and validate_index.py and travels with the
# repo (not with the installed wheel). The src/ refactor moved the RAG
# code into src/flame_mcp/rag/ but left the corpus and ChromaDB index
# where they were — this constant pair must point at the canonical
# <repo>/rag/ location, not at _PKG_DIR, or search() silently returns
# "index not found" for every query.
INDEX_DIR   = os.path.join(ROOT, 'rag', 'index')
CORPUS_PATH = os.path.join(ROOT, 'rag', 'corpus.json')

LOG_FILE = os.path.join(ROOT, 'logs', 'flame_rag.log')


def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{ts}] {msg}\n")


# ── Lazy singletons ────────────────────────────────────────────────────────────

_client     = None
_collection = None
_bm25       = None        # rank_bm25.BM25Okapi instance
_bm25_docs: list[dict] = []   # parallel corpus list for BM25 id lookup


def _get_embedding_fn() -> Any:
    """
    Returns the BGE embedding function used by build_index.py.
    MUST match rag/config.py — build and query must use the same model
    or cosine similarity scores will be meaningless.
    """
    from flame_mcp.rag.config import EMBEDDING_MODEL
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)


def _get_collection() -> Any | None:
    global _client, _collection
    if _collection is not None:
        return _collection

    if not os.path.isdir(INDEX_DIR):
        _log("ERROR: index not found — run python rag/build_index.py")
        return None

    try:
        import chromadb
        _client     = chromadb.PersistentClient(path=INDEX_DIR)
        _collection = _client.get_collection(
            "flame_docs",
            embedding_function=_get_embedding_fn(),
        )
        _log(f"Index loaded — {_collection.count()} chunks")
        return _collection
    except Exception as e:
        _log(f"ERROR loading index: {e}")
        return None


def _get_bm25() -> tuple[Any | None, list[dict]]:
    """
    C3 — Lazy-load BM25 index from corpus.json.
    Returns (BM25Okapi | None, corpus_list).
    Falls back gracefully if rank-bm25 not installed or corpus missing.
    """
    global _bm25, _bm25_docs
    if _bm25 is not None:
        return _bm25, _bm25_docs

    if not os.path.isfile(CORPUS_PATH):
        _log("BM25: corpus.json not found — run build_index.py to generate it")
        return None, []

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        _log("BM25: rank-bm25 not installed — pip install rank-bm25")
        return None, []

    try:
        with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
            corpus = json.load(f)

        # Tokenise: lowercase, split on whitespace
        tokenised  = [entry['text'].lower().split() for entry in corpus]
        _bm25      = BM25Okapi(tokenised)
        _bm25_docs = corpus
        _log(f"BM25 index ready — {len(corpus)} docs")
        return _bm25, _bm25_docs
    except Exception as e:
        _log(f"BM25 load error: {e}")
        return None, []


# ── C4 — HyDE query expansion ──────────────────────────────────────────────────

def _hyde_expand(query: str) -> str:
    """
    C4 — Hypothetical Document Embedding (HyDE).

    Embeds a hypothetical Flame code snippet instead of the raw query,
    bridging the semantic gap between natural-language questions and
    code-heavy documentation chunks. Template approach — no LLM call needed.
    """
    return (
        f"# Flame Python API — {query}\n"
        f"import flame\n"
        f"ws = flame.projects.current_project.current_workspace\n"
        f"# {query}\n"
        f"# Usage example: {query}"
    )


# ── C3 — RRF fusion ────────────────────────────────────────────────────────────

def _rrf_fuse(
    semantic_ids: list[str],
    bm25_ids: list[str],
    k: int = 60,
) -> list[str]:
    """
    Reciprocal Rank Fusion: combines two ranked lists without score calibration.
    RRF score for doc d: Σ 1/(k + rank(d)) across all retrievers.
    k=60 is the standard default; higher values reduce rank compression.
    """
    scores: dict[str, float] = {}
    for rank, doc_id in enumerate(semantic_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(bm25_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda d: scores[d], reverse=True)


# A12 — In-session cache: identical queries skip ChromaDB.
_search_cache: dict[int, tuple[str, int]] = {}

# ── Main search entry point ────────────────────────────────────────────────────

def search(query: str, n_results: int = 3) -> tuple[str, int]:
    """
    Hybrid search: BM25 + semantic (HyDE-expanded), fused via RRF.
    Returns (text: str, max_relevance: int) where max_relevance is 0–100.

    If the index has not been built yet, returns an actionable error message
    and max_relevance = 0.
    """
    # A12 — cache lookup
    cache_key = hash((query, n_results))
    if cache_key in _search_cache:
        return _search_cache[cache_key]

    from flame_mcp.rag.config import BM25_CANDIDATES, RRF_K

    collection = _get_collection()
    if collection is None:
        return (
            "RAG index not found. Build it first:\n"
            "  cd <flame-mcp repo root>\n"
            "  source .venv/bin/activate\n"
            "  python rag/build_index.py",
            0
        )

    count = collection.count()
    if count == 0:
        return "Index is empty. Run: python rag/build_index.py", 0

    _log(f"QUERY: '{query}'")

    # C4 — expand query with HyDE template before embedding
    hyde_query = _hyde_expand(query)

    # ── Semantic search (HyDE-expanded query) ─────────────────────────────────
    n_semantic  = min(BM25_CANDIDATES, count)
    sem_results = collection.query(
        query_texts=[hyde_query],
        n_results=n_semantic,
    )
    sem_ids   = sem_results.get('ids',       [[]])[0]
    sem_docs  = sem_results.get('documents', [[]])[0]
    sem_metas = sem_results.get('metadatas', [[]])[0]
    sem_dists = sem_results.get('distances', [[]])[0]

    # Build lookup maps: id → (doc, meta, distance)
    id_to_doc:  dict[str, str]   = {}
    id_to_meta: dict[str, dict]  = {}
    id_to_dist: dict[str, float] = {}
    for cid, doc, meta, dist in zip(sem_ids, sem_docs, sem_metas, sem_dists):
        id_to_doc[cid]  = doc
        id_to_meta[cid] = meta
        id_to_dist[cid] = dist

    # ── C3: BM25 search ───────────────────────────────────────────────────────
    bm25, bm25_corpus = _get_bm25()
    bm25_ids: list[str] = []
    if bm25 is not None and bm25_corpus:
        tokens = query.lower().split()
        scores = bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        for idx in top_indices[:BM25_CANDIDATES]:
            entry = bm25_corpus[idx]
            cid   = entry['id']
            bm25_ids.append(cid)
            if cid not in id_to_doc:
                id_to_doc[cid]  = entry['text']
                id_to_meta[cid] = entry['metadata']
                id_to_dist[cid] = 0.5  # neutral distance for BM25-only hits
        _log(f"  BM25: {len(bm25_ids)} candidates")
    else:
        _log("  BM25: unavailable — semantic only")

    # ── RRF fusion ────────────────────────────────────────────────────────────
    if bm25_ids:
        fused_ids = _rrf_fuse(sem_ids, bm25_ids, k=RRF_K)
        _log(f"  RRF: {len(sem_ids)} semantic + {len(bm25_ids)} BM25 → {len(fused_ids)} unique")
    else:
        fused_ids = sem_ids

    top_ids = fused_ids[:n_results]

    if not top_ids:
        _log("  → no results")
        return "No relevant documentation found for that query.", 0

    # ── Format results ─────────────────────────────────────────────────────────
    parts: list[str] = []
    max_relevance    = 0

    for cid in top_ids:
        doc  = id_to_doc.get(cid, '')
        meta = id_to_meta.get(cid, {})
        dist = id_to_dist.get(cid, 0.5)

        section   = meta.get('section', '')
        source    = meta.get('source', '')
        relevance = round((1 - dist) * 100)
        if relevance > max_relevance:
            max_relevance = relevance
        _log(f"  → [{relevance}%] {source} :: {section}")
        header = f"### [{source}] {section}  (relevance: {relevance}%)"
        parts.append(f"{header}\n\n{doc}")

    total_chars = sum(len(p) for p in parts)
    _log(
        f"  → returned {len(parts)} chunks, "
        f"~{total_chars} chars (~{total_chars//4} tokens saved vs full doc)"
    )

    result = ("\n\n---\n\n".join(parts), max_relevance)
    # A12 — cache store
    _search_cache[cache_key] = result
    return result


def clear_cache() -> None:
    """Clear the in-session search cache."""
    _search_cache.clear()
