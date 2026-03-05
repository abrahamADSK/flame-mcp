"""
search.py
=========
Semantic search over the local ChromaDB index.
Called by the search_flame_docs MCP tool in flame_mcp_server.py.

The index must be built first:
    python rag/build_index.py
"""

import os

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_DIR = os.path.join(ROOT, 'rag', 'index')

# Lazy singletons — loaded once, reused across calls
_client     = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    if not os.path.isdir(INDEX_DIR):
        return None

    try:
        import chromadb
        _client     = chromadb.PersistentClient(path=INDEX_DIR)
        _collection = _client.get_collection("flame_docs")
        return _collection
    except Exception:
        return None


def search(query: str, n_results: int = 3) -> str:
    """
    Search the documentation index for content relevant to `query`.
    Returns the top n_results sections as a single formatted string.

    If the index has not been built yet, returns an actionable error message.
    """
    collection = _get_collection()

    if collection is None:
        return (
            "RAG index not found. Build it first:\n"
            "  cd ~/Projects/flame-mcp\n"
            "  source .venv/bin/activate\n"
            "  python rag/build_index.py"
        )

    count = collection.count()
    if count == 0:
        return "Index is empty. Run: python rag/build_index.py"

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, count),
    )

    docs      = results.get('documents', [[]])[0]
    metadatas = results.get('metadatas', [[]])[0]
    distances = results.get('distances', [[]])[0]

    if not docs:
        return "No relevant documentation found for that query."

    parts = []
    for doc, meta, dist in zip(docs, metadatas, distances):
        section  = meta.get('section', '')
        source   = meta.get('source', '')
        relevance = round((1 - dist) * 100)
        header   = f"### [{source}] {section}  (relevance: {relevance}%)"
        parts.append(f"{header}\n\n{doc}")

    return "\n\n---\n\n".join(parts)
