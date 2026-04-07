"""
rag/config.py
=============
Shared constants for the RAG pipeline.

IMPORTANT: EMBEDDING_MODEL must be consistent across build_index.py (write)
and search.py (read). If you change it here, delete rag/index/ and rebuild.
"""

# C6 — Embedding model selection.
# IMPORTANT: build and query MUST use the same model. If you change this,
# delete rag/index/ and run python rag/build_index.py to rebuild.
#
# Option A — bge-small-en-v1.5 (default, ~130 MB): fast, good for semantic queries
# Option B — bge-large-en-v1.5 (~570 MB): higher accuracy on technical code queries
# Option C — nomic-embed-text-v1.5 (~270 MB): strong code + natural language mix
#
# Switched to bge-large for better recall on exact Flame API method names (C6).
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"

# C3 — Hybrid BM25 + semantic search via Reciprocal Rank Fusion
# BM25_CANDIDATES: how many candidates each retriever fetches before fusion
# RRF_K: RRF damping constant (higher = less aggressive rank compression; 60 is standard)
BM25_CANDIDATES = 20
RRF_K           = 60
