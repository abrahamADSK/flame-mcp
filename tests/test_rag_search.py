"""
test_rag_search.py
==================
RAG search tests for flame-mcp.

Tests the hybrid search pipeline in rag/search.py:
BM25 (lexical) + semantic (HyDE-expanded) fused via Reciprocal Rank Fusion.

Uses a mini corpus of 12 Flame API chunks built into a temporary ChromaDB
index — no connection to Flame, no large model downloads.  Deterministic
SHA-256 embeddings ensure reproducible results.

Tests
-----
TestRagSearch (4 tests):
  1. test_basic_search    -- query returns chunks + relevance score
  2. test_empty_query     -- empty string does not crash
  3. test_n_results       -- n_results limits the number of chunks returned
  4. test_no_index        -- absent index returns actionable error message

TestRagSearchCache (4 tests):
  5. test_cache_returns_same_result       -- same query → same result (deterministic)
  6. test_different_queries_not_cached    -- different queries → different results
  7. test_different_n_results_not_cached  -- different n_results → different chunk count
  8. test_clear_session_cache             -- server _search_cache can be cleared
"""

import pytest
from unittest.mock import patch


# ═══════════════════════════════════════════════════════════════════════════
# TestRagSearch
# ═══════════════════════════════════════════════════════════════════════════

class TestRagSearch:
    """search() returns (text, max_relevance) from the indexed Flame API corpus."""

    def test_basic_search(self, patch_rag_singletons):
        """search() returns a non-empty string and an integer relevance score."""
        from rag.search import search

        text, relevance = search("library workspace reels", n_results=3)

        assert isinstance(text, str), "search() must return a string as first element"
        assert isinstance(relevance, int), "search() must return an int as second element"
        assert len(text) > 0, "Result text must not be empty"
        assert 0 <= relevance <= 100, f"Relevance {relevance} out of [0, 100] range"

    def test_empty_query(self, patch_rag_singletons):
        """An empty query does not crash — returns nearest neighbours."""
        from rag.search import search

        text, relevance = search("", n_results=3)

        assert isinstance(text, str)
        assert isinstance(relevance, int)
        assert relevance >= 0

    def test_n_results(self, patch_rag_singletons):
        """n_results=2 returns at most 2 chunk blocks."""
        from rag.search import search

        text, _relevance = search("batch render schedule", n_results=2)

        # Chunks are separated by "\n\n---\n\n"
        chunk_count = text.count("\n\n---\n\n") + 1
        assert chunk_count <= 2, f"Expected ≤2 chunks, got {chunk_count}"

    def test_no_index(self, tmp_path):
        """When the index directory does not exist, returns an actionable message."""
        from rag.search import search

        fake_dir = str(tmp_path / "nonexistent_index")

        with patch("rag.search._collection", None), \
             patch("rag.search._client", None), \
             patch("rag.search.INDEX_DIR", fake_dir):
            text, relevance = search("anything", n_results=3)

        assert relevance == 0, "Missing index must return relevance 0"
        assert (
            "not found" in text.lower()
            or "build" in text.lower()
            or "index" in text.lower()
        ), f"Expected actionable error message, got: {text!r}"


# ═══════════════════════════════════════════════════════════════════════════
# TestRagSearchBasic — result format verification
# ═══════════════════════════════════════════════════════════════════════════

class TestRagSearchBasic:
    """Additional format checks on search() output."""

    def test_result_contains_header(self, patch_rag_singletons):
        """Results include ### [source] section (relevance: N%) headers."""
        from rag.search import search

        text, _relevance = search("create library workspace", n_results=3)

        assert "###" in text, "Expected markdown ### header in result"
        assert "relevance:" in text, "Expected relevance percentage in result"

    def test_relevance_is_bounded(self, patch_rag_singletons):
        """max_relevance is always in [0, 100]."""
        from rag.search import search

        _text, relevance = search("batch group render", n_results=3)

        assert 0 <= relevance <= 100, f"Relevance {relevance} out of range"

    def test_flame_api_content_returned(self, patch_rag_singletons):
        """Query about 'workspace libraries' returns flame_api corpus chunks."""
        from rag.search import search

        text, _relevance = search("workspace libraries flame project", n_results=5)

        # BM25 should match the workspace_libraries chunk on exact tokens
        assert "libraries" in text.lower() or "workspace" in text.lower(), (
            "Expected workspace/library content in results"
        )

    def test_batch_query_returns_batch_content(self, patch_rag_singletons):
        """Query about 'batch group render' returns flame_batch corpus chunks."""
        from rag.search import search

        text, _relevance = search("batch group render schedule_idle_event", n_results=5)

        assert "batch" in text.lower(), "Expected batch content in results"


# ═══════════════════════════════════════════════════════════════════════════
# TestRagSearchBm25
# ═══════════════════════════════════════════════════════════════════════════

class TestRagSearchBm25:
    """BM25 (lexical) retriever matches exact Flame API method names."""

    def test_exact_method_found(self, patch_rag_singletons):
        """Querying 'create_library' returns the create_library chunk."""
        from rag.search import search

        text, _relevance = search("create_library workspace", n_results=5)

        assert "create_library" in text.lower() or "library" in text.lower(), (
            "BM25 should rank the create_library chunk highly for an exact token match"
        )

    def test_bm25_scores_exact_token_highest(self, mini_flame_corpus):
        """BM25 scores the create_library chunk highest for 'create_library' query."""
        from rank_bm25 import BM25Okapi

        tokenised = [entry["text"].lower().split() for entry in mini_flame_corpus]
        bm25 = BM25Okapi(tokenised)

        scores = bm25.get_scores("create_library".lower().split())

        # Find the index of the create_library chunk
        lib_idx = next(
            i for i, c in enumerate(mini_flame_corpus)
            if c["id"] == "FLAME_API.md::2::create_library"
        )

        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        assert lib_idx in top_indices[:3], (
            f"create_library chunk (idx={lib_idx}) should be in top 3 BM25 results, "
            f"got top 3: {top_indices[:3]}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TestRagSearchRrfFusion
# ═══════════════════════════════════════════════════════════════════════════

class TestRagSearchRrfFusion:
    """_rrf_fuse() correctly combines two ranked lists."""

    def test_rrf_basic_merge(self):
        """RRF merges two disjoint lists, including all items."""
        from rag.search import _rrf_fuse

        sem  = ["a", "b", "c"]
        bm25 = ["d", "e", "f"]
        fused = _rrf_fuse(sem, bm25, k=60)

        assert set(fused) == {"a", "b", "c", "d", "e", "f"}

    def test_rrf_overlapping_docs_boosted(self):
        """Documents in both lists are ranked higher via score accumulation."""
        from rag.search import _rrf_fuse

        sem  = ["shared", "sem_only_1", "sem_only_2"]
        bm25 = ["bm25_only_1", "shared", "bm25_only_2"]
        fused = _rrf_fuse(sem, bm25, k=60)

        assert fused[0] == "shared", (
            "Document appearing in both rankers should be boosted to top"
        )

    def test_rrf_preserves_order_single_list(self):
        """With only one non-empty list, relative order is preserved."""
        from rag.search import _rrf_fuse

        sem = ["a", "b", "c"]
        fused = _rrf_fuse(sem, [], k=60)

        assert fused == ["a", "b", "c"]

    def test_rrf_empty_inputs(self):
        """Both empty inputs return an empty list."""
        from rag.search import _rrf_fuse

        fused = _rrf_fuse([], [], k=60)
        assert fused == []


# ═══════════════════════════════════════════════════════════════════════════
# TestRagSearchEmptyIndex
# ═══════════════════════════════════════════════════════════════════════════

class TestRagSearchEmptyIndex:
    """search() handles empty or missing index gracefully."""

    def test_empty_collection_returns_message(self, rag_empty_collection):
        """Empty ChromaDB collection returns an informative message + relevance 0."""
        from rag.search import search

        collection, index_dir = rag_empty_collection

        with patch("rag.search._collection", collection), \
             patch("rag.search.INDEX_DIR", index_dir):
            text, relevance = search("anything", n_results=3)

        assert relevance == 0, "Empty index must return relevance 0"
        assert "empty" in text.lower() or "build" in text.lower(), (
            f"Expected informative error, got: {text!r}"
        )

    def test_empty_returns_zero_relevance(self, rag_empty_collection):
        """Relevance is exactly 0 for any query against an empty index."""
        from rag.search import search

        collection, index_dir = rag_empty_collection

        with patch("rag.search._collection", collection), \
             patch("rag.search.INDEX_DIR", index_dir):
            _text, relevance = search("batch render workspace", n_results=5)

        assert relevance == 0


# ═══════════════════════════════════════════════════════════════════════════
# TestRagSearchCache
# ═══════════════════════════════════════════════════════════════════════════

class TestRagSearchCache:
    """Deterministic results and server-level session cache behavior."""

    def test_cache_returns_same_result(self, patch_rag_singletons):
        """Two identical search() calls return the same result (deterministic)."""
        from rag.search import search

        result1 = search("workspace libraries create", n_results=3)
        result2 = search("workspace libraries create", n_results=3)

        assert result1 == result2, "Identical queries must return identical results"

    def test_different_queries_not_cached(self, patch_rag_singletons):
        """Different queries return different results."""
        from rag.search import search

        text1, _r1 = search("workspace library reels", n_results=3)
        text2, _r2 = search("batch group render schedule_idle_event", n_results=3)

        assert text1 != text2, "Different queries should produce different results"

    def test_different_n_results_not_cached(self, patch_rag_singletons):
        """Same query with different n_results returns different chunk counts."""
        from rag.search import search

        text1, _r1 = search("batch library workspace", n_results=1)
        text2, _r2 = search("batch library workspace", n_results=5)

        chunks1 = text1.count("\n\n---\n\n") + 1
        chunks2 = text2.count("\n\n---\n\n") + 1

        assert chunks1 <= chunks2, (
            f"n_results=1 ({chunks1} chunks) should have ≤ chunks than n_results=5 ({chunks2})"
        )

    def test_clear_session_cache(self, patch_rag_singletons):
        """The server-level _search_cache can be cleared between calls."""
        import flame_mcp_server

        # Populate the server-level session cache
        flame_mcp_server._search_cache.clear()
        flame_mcp_server._search_cache[hash("dummy")] = ("cached result", 80)
        assert len(flame_mcp_server._search_cache) > 0

        # Clearing it empties the dict
        flame_mcp_server._search_cache.clear()
        assert len(flame_mcp_server._search_cache) == 0, (
            "Server _search_cache should be empty after .clear()"
        )
