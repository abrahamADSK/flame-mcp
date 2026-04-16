"""
conftest.py
===========
Shared fixtures and path setup for flame-mcp tests.

The package is installed in editable mode (pip install -e .) so that
``from flame_mcp.server import ...`` works directly.

Stubs the MCP SDK (mcp.server.fastmcp + mcp.types) so the server module
can be imported without the full MCP package installed.

Provides:
  - mock_bridge: patches _call_flame for tool tests
  - mock_bridge_error: patches _call_flame to simulate connection failure
  - Mini Flame RAG corpus + deterministic ChromaDB fixtures for RAG tests
"""

import hashlib
import json
import sys
import types as _types
from pathlib import Path
from unittest.mock import patch

import pytest

# ── ulimit check ──────────────────────────────────────────────────────────────
import resource
_soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
if _soft < 4096:
    import warnings
    warnings.warn(
        f"Low file descriptor limit ({_soft}). ChromaDB may crash. "
        "Run: ulimit -n 4096",
        stacklevel=1,
    )

# ── MCP SDK stub ──────────────────────────────────────────────────────────────
# flame_mcp.server imports at module level:
#   from mcp.server.fastmcp import FastMCP
#   from mcp.types import ToolAnnotations  (inside try/except ImportError)
# Install minimal stubs so ``import flame_mcp.server`` succeeds without the SDK.

if "mcp" not in sys.modules:
    _mcp_pkg        = _types.ModuleType("mcp")
    _mcp_server_mod = _types.ModuleType("mcp.server")
    _mcp_fastmcp    = _types.ModuleType("mcp.server.fastmcp")
    _mcp_types_mod  = _types.ModuleType("mcp.types")

    class _StubFastMCP:
        """Minimal FastMCP stand-in: captures @mcp.tool() decorators."""
        def __init__(self, *a, **kw):
            pass

        def tool(self, *a, **kw):
            def decorator(fn):
                return fn
            return decorator

    class _StubToolAnnotations:
        """Minimal ToolAnnotations stand-in."""
        def __init__(self, *a, **kw):
            pass

    _mcp_fastmcp.FastMCP                = _StubFastMCP
    _mcp_types_mod.ToolAnnotations      = _StubToolAnnotations
    _mcp_pkg.server                     = _mcp_server_mod
    _mcp_server_mod.fastmcp             = _mcp_fastmcp
    _mcp_pkg.types                      = _mcp_types_mod

    sys.modules["mcp"]                  = _mcp_pkg
    sys.modules["mcp.server"]           = _mcp_server_mod
    sys.modules["mcp.server.fastmcp"]   = _mcp_fastmcp
    sys.modules["mcp.types"]            = _mcp_types_mod


# ── Bridge mock fixtures ──────────────────────────────────────────────────────
# _call_flame is the single point of contact with the Flame bridge.
# All dedicated tool tests patch it to avoid real TCP/socket connections.
# Tools are synchronous — no asyncio needed.

_DEFAULT_BRIDGE_RESPONSE = {
    "output":     "ok",
    "error":      "",
    "_bridge_ms": 0,
}

_BRIDGE_CONNECTION_ERROR = {
    "status": "error",
    "error":  (
        "Cannot connect to Flame on port 4444.\n"
        "Check that:\n"
        "  1. Flame is open\n"
        "  2. flame_mcp_bridge.py is in /opt/Autodesk/shared/python/\n"
        "  3. Flame was restarted after installing the bridge"
    ),
}


@pytest.fixture()
def mock_bridge():
    """Patch flame_mcp_server._call_flame with a configurable MagicMock.

    Default return value: {'output': 'ok', 'error': '', '_bridge_ms': 0}
    Override per-test with:  mock_bridge.return_value = {...}
    """
    with patch("flame_mcp.server._call_flame") as m:
        m.return_value = dict(_DEFAULT_BRIDGE_RESPONSE)
        # Satisfy the hard RAG gate (Architecture 3.4) so execute_python tests
        # are not blocked.  Tests that specifically need the gate OFF should
        # patch _rag_called_this_session back to False.
        with patch("flame_mcp.server._rag_called_this_session", True):
            yield m


@pytest.fixture()
def mock_bridge_error():
    """Patch _call_flame to return a connection-refused error response."""
    with patch("flame_mcp.server._call_flame") as m:
        m.return_value = dict(_BRIDGE_CONNECTION_ERROR)
        with patch("flame_mcp.server._rag_called_this_session", True):
            yield m


# ── Mini Flame RAG corpus ─────────────────────────────────────────────────────
# 12 chunks across 3 API domains: flame_api (workspace/library),
# flame_batch (batch groups/renders), flame_clips (reels/clips).
# Small enough for fast tests; rich enough to verify BM25, RRF, and
# the search() plumbing without downloading any embedding model.

MINI_FLAME_CORPUS = [
    # ── flame_api domain (5 chunks) ──────────────────────────────────────────
    {
        "id": "FLAME_API.md::0::workspace_libraries",
        "text": (
            "## Access Libraries\n\n"
            "Access workspace libraries via current_workspace:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "HIDDEN = {'Timeline FX', 'Grabbed References'}\n"
            "visible = [l for l in ws.libraries if str(l.name) not in HIDDEN]\n"
            "for lib in visible:\n"
            "    print(str(lib.name))\n"
            "```\n\n"
            "Never use `flame.projects.current_project.libraries` — it returns None.\n"
            "Always use `current_workspace.libraries`."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "workspace_libraries", "api": "flame_api"},
    },
    {
        "id": "FLAME_API.md::1::project_info",
        "text": (
            "## Project Info\n\n"
            "Access active project metadata via current_project:\n\n"
            "```python\n"
            "import flame\n"
            "p = flame.projects.current_project\n"
            "print(f'Name: {str(p.name)}')\n"
            "print(f'Description: {str(p.description)}')\n"
            "print(f'Workspaces: {str(p.workspaces_count)}')\n"
            "```\n\n"
            "frame_rate, width, height, bit_depth are only accessible via\n"
            "Wiretap XML metadata — they return None from the Python API."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "project_info", "api": "flame_api"},
    },
    {
        "id": "FLAME_API.md::2::create_library",
        "text": (
            "## Create Library\n\n"
            "Create a new library in the current workspace:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "new_lib = ws.create_library('VFX_Shots')\n"
            "print(f'Created: {str(new_lib.name)}')\n"
            "```\n\n"
            "Returns a PyLibrary object. Library names must be unique."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "create_library", "api": "flame_api"},
    },
    {
        "id": "FLAME_API.md::3::delete_objects",
        "text": (
            "## Delete Objects\n\n"
            "Use `flame.delete()` to remove clips, reels, or libraries:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "lib = next((l for l in ws.libraries if str(l.name) == 'OldLib'), None)\n"
            "if lib:\n"
            "    flame.delete(lib)\n"
            "```\n\n"
            "Never call `.clear()` on Flame containers — it crashes Flame.\n"
            "Always use `flame.delete(item)` on individual objects."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "delete_objects", "api": "flame_api"},
    },
    {
        "id": "FLAME_API.md::4::pyattribute",
        "text": (
            "## PyAttribute\n\n"
            "Flame object attributes return PyAttribute objects, not plain strings.\n"
            "Always wrap with str():\n\n"
            "```python\n"
            "# WRONG — always False:\n"
            "if reel.name == 'Reel 1':\n"
            "# CORRECT:\n"
            "if str(reel.name) == 'Reel 1':\n"
            "```\n\n"
            "String methods (.lower(), .startswith()) also require str() first."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "pyattribute", "api": "flame_api"},
    },
    # ── flame_batch domain (3 chunks) ────────────────────────────────────────
    {
        "id": "FLAME_API.md::5::batch_groups",
        "text": (
            "## Batch Groups\n\n"
            "Access batch groups from the desktop:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "desktop = ws.desktop\n"
            "batch_groups = list(desktop.batch_groups)\n"
            "for bg in batch_groups:\n"
            "    print(f'Batch: {str(bg.name)} — {len(bg.reels)} reels')\n"
            "```\n\n"
            "Never call `flame.batch.render()` directly — it blocks the main thread."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "batch_groups", "api": "flame_batch"},
    },
    {
        "id": "FLAME_API.md::6::schedule_idle_event",
        "text": (
            "## schedule_idle_event\n\n"
            "Use `flame.schedule_idle_event()` for renders and exports:\n\n"
            "```python\n"
            "import flame\n"
            "\n"
            "def _do_render():\n"
            "    flame.batch.render(render_option='Background Reactor')\n"
            "\n"
            "flame.schedule_idle_event(_do_render)\n"
            "print('Render scheduled.')\n"
            "```\n\n"
            "Required for batch renders and PyExporter.export() calls."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "schedule_idle_event", "api": "flame_batch"},
    },
    {
        "id": "FLAME_API.md::7::create_batch_group",
        "text": (
            "## Create Batch Group\n\n"
            "Create a new batch group on the desktop:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "desktop = ws.desktop\n"
            "bg = desktop.create_batch_group('Shot_010', reels=['Input', 'Output'])\n"
            "print(f'Created: {str(bg.name)}')\n"
            "```\n\n"
            "Batch groups appear alongside reel groups on the desktop."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "create_batch_group", "api": "flame_batch"},
    },
    # ── flame_clips domain (3 chunks) ─────────────────────────────────────────
    {
        "id": "FLAME_API.md::8::list_reels",
        "text": (
            "## List Reels\n\n"
            "Access reels within a library:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "lib = next((l for l in ws.libraries if str(l.name) == 'VFX'), None)\n"
            "if lib:\n"
            "    for reel in lib.reels:\n"
            "        print(f'  {str(reel.name)}  ({len(reel.clips)} clips)')\n"
            "```\n\n"
            "Each reel exposes a `.clips` attribute returning PyClip objects."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "list_reels", "api": "flame_clips"},
    },
    {
        "id": "FLAME_API.md::9::create_sequence",
        "text": (
            "## Create Sequence\n\n"
            "Create a new sequence clip in a reel:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "lib = ws.libraries[0]\n"
            "reel = lib.reels[0]\n"
            "seq = reel.create_sequence(name='SH010', nb_tracks=1, start_frame=1001)\n"
            "print(f'Sequence: {str(seq.name)}')\n"
            "```\n\n"
            "Use `create_sequence` for timeline-based PySequence clips."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "create_sequence", "api": "flame_clips"},
    },
    {
        "id": "FLAME_API.md::10::import_clips",
        "text": (
            "## Import Clips\n\n"
            "Import media files into a reel:\n\n"
            "```python\n"
            "import flame\n"
            "ws = flame.projects.current_project.current_workspace\n"
            "lib = next((l for l in ws.libraries if str(l.name) == 'VFX'), None)\n"
            "reel = lib.reels[0]\n"
            "flame.import_clips('/path/to/clip.mov', reel)\n"
            "print('Import complete.')\n"
            "```\n\n"
            "Accepts file paths, wildcards, and lists of paths."
        ),
        "metadata": {"source": "FLAME_API.md", "section": "import_clips", "api": "flame_clips"},
    },
    # ── Filler (for no-match / changelog tests) ───────────────────────────────
    {
        "id": "FLAME_API.md::99::changelog",
        "text": (
            "## Changelog\n\n"
            "- Flame 2026: Python 3.10 runtime, improved schedule_idle_event\n"
            "- Flame 2025.3: New create_batch_group() API enhancements\n"
            "- Flame 2025.2: PyExporter reliability improvements\n"
        ),
        "metadata": {"source": "FLAME_API.md", "section": "changelog", "api": "flame_api"},
    },
]


def _make_deterministic_embedding_fn():
    """Build a ChromaDB-compatible deterministic embedding function.

    Generates 64-dimensional float vectors from SHA-256 hashes.
    No model download required — fast and reproducible.
    """
    import chromadb

    class _DetEF(chromadb.EmbeddingFunction):
        def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
            vectors = []
            for text in input:
                digest = hashlib.sha256(text.encode("utf-8")).digest()
                vec = [(b / 127.5) - 1.0 for b in digest]
                vec = (vec * 2)[:64]
                vectors.append(vec)
            return vectors

        @staticmethod
        def name() -> str:
            return "deterministic_test"

        def build_from_config(self, config):
            return _DetEF()

        def get_config(self):
            return {}

    return _DetEF()


@pytest.fixture
def mini_flame_corpus():
    """Return a deep copy of the mini Flame RAG corpus (12 chunks, 3 API domains)."""
    import copy
    return copy.deepcopy(MINI_FLAME_CORPUS)


@pytest.fixture
def rag_chroma_collection(tmp_path, mini_flame_corpus):
    """Build a temporary ChromaDB collection from the mini Flame corpus.

    Returns (collection, index_dir) where index_dir is the persistent DB path.
    """
    import chromadb

    index_dir = str(tmp_path / "rag_index")
    client = chromadb.PersistentClient(path=index_dir)

    embedding_fn = _make_deterministic_embedding_fn()
    collection = client.create_collection(
        name="flame_docs",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=[c["id"] for c in mini_flame_corpus],
        documents=[c["text"] for c in mini_flame_corpus],
        metadatas=[c["metadata"] for c in mini_flame_corpus],
    )

    return collection, index_dir


@pytest.fixture
def rag_corpus_json(tmp_path, mini_flame_corpus):
    """Write the mini corpus as corpus.json for BM25 and return the file path."""
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(mini_flame_corpus, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(corpus_path)


@pytest.fixture
def rag_empty_collection(tmp_path):
    """Build an empty ChromaDB collection (0 chunks) for edge-case tests.

    Returns (collection, index_dir).
    """
    import chromadb

    index_dir = str(tmp_path / "empty_index")
    client = chromadb.PersistentClient(path=index_dir)

    embedding_fn = _make_deterministic_embedding_fn()
    collection = client.create_collection(
        name="flame_docs",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    return collection, index_dir


@pytest.fixture
def patch_rag_singletons(rag_chroma_collection, rag_corpus_json):
    """Patch rag.search module-level singletons to use the test mini-corpus index.

    Replaces:
      - _collection  → test ChromaDB collection (flame_docs)
      - _bm25        → BM25Okapi built from mini corpus
      - _bm25_docs   → mini corpus list (for BM25 id→doc lookup)
      - INDEX_DIR    → temporary index directory
      - CORPUS_PATH  → temporary corpus.json path

    Yields (collection, bm25, corpus) for test assertions.
    """
    from rank_bm25 import BM25Okapi
    from flame_mcp.rag.search import search as _ensure_imported  # noqa: F401 — loads module

    collection, index_dir = rag_chroma_collection

    with open(rag_corpus_json, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    tokenised = [entry["text"].lower().split() for entry in corpus]
    bm25 = BM25Okapi(tokenised)

    with patch("flame_mcp.rag.search._collection", collection), \
         patch("flame_mcp.rag.search._bm25", bm25), \
         patch("flame_mcp.rag.search._bm25_docs", corpus), \
         patch("flame_mcp.rag.search.INDEX_DIR", index_dir), \
         patch("flame_mcp.rag.search.CORPUS_PATH", rag_corpus_json):
        yield collection, bm25, corpus
