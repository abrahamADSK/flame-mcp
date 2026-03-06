"""
rag/config.py
=============
Shared constants for the RAG pipeline.

IMPORTANT: EMBEDDING_MODEL must be consistent across build_index.py (write)
and search.py (read). If you change it here, delete rag/index/ and rebuild.
"""

# BAAI/bge-small-en-v1.5 — state-of-the-art retrieval model, specifically
# trained for semantic search. ~130 MB, downloaded once from HuggingFace.
# Much better than all-MiniLM-L6-v2 for intent-based technical queries.
# No external service required — runs locally via sentence-transformers.
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
