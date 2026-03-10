"""
flame_mcp_server.py
===================
MCP server that exposes tools for controlling Autodesk Flame.
Communicates with the TCP bridge (flame_mcp_bridge.py) running inside Flame.

Usage:
    Register with Claude Code:
        claude mcp add flame -- /path/to/.venv/bin/python /path/to/flame_mcp_server.py

    Or add manually to ~/.claude.json

Requirements:
    pip install mcp>=1.26.0

Bridge port: 4444 (must match flame_mcp_bridge.py)
"""

import socket
import json
import os
import re
import sys
import subprocess
import datetime
import time
from pathlib import Path
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP

_SERVER_DIR = Path(__file__).parent

# Make rag/ importable when running from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Tool annotations (MCP ≥ 1.x) ────────────────────────────────────────────
try:
    from mcp.types import ToolAnnotations
    _RO  = ToolAnnotations(readOnlyHint=True,  destructiveHint=False, openWorldHint=False)  # read-only local
    _RW  = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)  # write, not destructive
    _DST = ToolAnnotations(readOnlyHint=False, destructiveHint=True,  openWorldHint=False)  # potentially destructive
except ImportError:
    _RO = _RW = _DST = None  # older mcp versions — gracefully ignored by FastMCP

# ─── Safety: known-crasher patterns ──────────────────────────────────────────
# Each entry: (regex, explanation, safe_alternative)
_DANGEROUS_PATTERNS = [
    (
        r'len\s*\(\s*flame\.projects\s*\)',
        "flame.projects has no len() — PyProjectSelector is not a list.",
        "Use flame.projects.current_project.name for the active project, "
        "or read /opt/Autodesk/project directory to list all projects."
    ),
    (
        r'for\s+\w+\s+in\s+flame\.projects\b',
        "flame.projects is not iterable — iterating it crashes Flame.",
        "Use flame.projects.current_project for the active project, "
        "or os.listdir('/opt/Autodesk/project') to enumerate all projects."
    ),
    (
        r'flame\.projects\s*\[\s*\d',
        "flame.projects is not subscriptable — indexing it crashes Flame.",
        "Use flame.projects.current_project to access the current project."
    ),
    (
        r'flame\.projects\.current_project\.libraries\b',
        "project.libraries returns None — libraries live on the workspace.",
        "Use: ws = flame.projects.current_project.current_workspace; ws.libraries"
    ),
    (
        r'flame\.batch\.render\s*\(\s*\)',
        "flame.batch.render() blocks Flame's main thread and can freeze or crash it.",
        "Use: flame.schedule_idle_event(lambda: flame.batch.render(render_option='Background Reactor'))"
    ),
    (
        r'\bimport\s+wiretap\b',
        "The wiretap module is crash-prone for general scripting tasks.",
        "Use the standard flame module API. Call search_flame_docs for the correct pattern."
    ),
    (
        r'WireTapServerHandle|WireTapClientHandle|libwiretap|wiretapPythonClient',
        "Direct access to WireTap C-bindings crashes or destabilises Flame. "
        "WireTap is already loaded in Flame's process — accessing it directly is unsafe.",
        "Use the standard flame module API only. Call search_flame_docs for the correct pattern."
    ),
    (
        r'\.createNode\s*\(|\.getNumChildren\s*\(|\.getNodeInfo\s*\(',
        "WireTap tree-traversal methods (createNode, getNumChildren, getNodeInfo) "
        "are unreliable from Python hooks and can crash Flame.",
        "Use the standard flame module API. Call search_flame_docs for the correct pattern."
    ),
    (
        r'\.replace_desktop\s*\(',
        "ws.replace_desktop() is an internal Flame method that can corrupt the workspace "
        "state and crash Flame when called from a Python hook.",
        "To work with desktops use ws.desktop and its reel_groups/reels attributes. "
        "Call search_flame_docs('desktop reel group') for the correct pattern."
    ),
    (
        r'\bdir\s*\(\s*flame\b',
        "Using dir() to discover the Flame API is unsafe and causes speculative/crashing code.",
        "Call search_flame_docs(query) instead — it returns verified, working patterns."
    ),
    (
        r'\.\s*clear\s*\(\s*\)',
        "Calling .clear() on Flame objects (PyReelGroup, PyLibrary, PyReel, etc.) "
        "crashes Flame — it is a raw C-level destructor, not a public API.",
        "To empty a container, iterate its children and call flame.delete(item) on each one. "
        "See FLAME_API.md §Delete / Remove Objects for the correct pattern."
    ),
    (
        r'flame\s*\.\s*clear_desktop\s*\(',
        "flame.clear_desktop() does not exist in the public Flame Python API.",
        "To clear the desktop, delete individual reels/items using flame.delete(). "
        "See search_flame_docs('clear all reels from reel group') for the correct pattern."
    ),
    (
        r'for\s+\w+\s+in\s+list\s*\(\s*\w*\s*\.reels\s*\)\s*:\s*\n\s*flame\s*\.\s*delete',
        "This loop deletes ALL reels from the reel group — Flame crashes when a "
        "desktop reel group has zero reels.",
        "Always keep at least one reel: use reels[:-1] to delete all but the last, "
        "or filter by name with a 'keep' set. "
        "See FLAME_API.md 'Clear Desktop' for the confirmed safe pattern."
    ),
    (
        r'flame\s*\.\s*delete\s*\(\s*list\s*\(\s*\w*\s*\.reels\s*\)\s*\)',
        "flame.delete(list(rg.reels)) deletes ALL reels at once — "
        "Flame crashes when a desktop reel group has zero reels.",
        "Always keep at least one reel: flame.delete(list(rg.reels)[:-1]) "
        "or filter by name. See FLAME_API.md 'Clear Desktop' for the safe pattern."
    ),
    (
        r'if\s+\w+\.name\s*[=!]=\s*["\']|\.name\s+in\s+\{|\.name\s+not\s+in\s+\{',
        "Flame .name attributes return PyAttribute objects, not strings. "
        "Direct comparison with == or 'in' always fails silently (returns []).",
        "Always wrap with str(): str(reel.name) == 'Reel 1', "
        "or str(reel.name) in {'Reel 1', 'Reel 2'}. "
        "See FLAME_API.md 'PyAttribute' section."
    ),
    (
        r'\.name\s*\.\s*(?:startswith|endswith|lower|upper|split|strip|replace|find|contains)\s*\(',
        "Flame .name returns a PyAttribute object, not a string. "
        "String methods like .startswith(), .lower(), .split() crash with AttributeError.",
        "Always wrap with str() first: str(clip.name).startswith('VFX_')"
    ),
    (
        r'next\s*\(\s*\w+\s+for\s+\w+\s+in\s+\w+\.(?:reels|clips|libraries|reel_groups|folders)\b(?!\s*,)',
        "next() without a default raises StopIteration if no item matches, "
        "leaving Flame in an incomplete state.",
        "Always provide a default: next((r for r in rg.reels if ...), None) "
        "and check for None before using the result."
    ),
    (
        r'=\s*next\s*\(.*\bNone\b.*\)(?![\s\S]{0,200}if\s+\w+\s+is\s+(?:not\s+)?None)',
        "Result of next(..., None) is used without a None check. "
        "Accessing attributes on None causes AttributeError.",
        "Always check: result = next(..., None); if result is None: print('not found'); else: use result"
    ),
    (
        r'seg\.delete\s*\(|\.remove_gap\s*\(|\.ripple\s*\(|flame\.timeline\.',
        "These timeline edit methods do not exist in Flame 2026 and crash Flame: "
        "seg.delete(), track.remove_gap(), track.ripple(), flame.timeline.*",
        "To close gaps / ripple delete: rebuild the sequence by iterating "
        "non-gap segments and overwriting them back-to-back into a new sequence. "
        "See FLAME_API.md 'Timeline / Sequence Editing — Close Gap' for the working pattern."
    ),
]


def _check_dangerous(code: str):
    """
    Scan code for patterns known to crash Flame (regex + AST).
    Returns a formatted error string if any are found, else None.
    """
    hits = []
    for pattern, reason, alternative in _DANGEROUS_PATTERNS:
        if re.search(pattern, code):
            hits.append(f"  • {reason}\n    ✅ Instead: {alternative}")

    # A2 — AST analysis catches obfuscated calls that bypass regex
    # e.g. getattr(flame, 'batch').render()  or  __import__('wiretap')
    try:
        import ast as _ast
        tree = _ast.parse(code)
        for node in _ast.walk(tree):
            # Catch:  import wiretap  /  __import__('wiretap')
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                for alias in getattr(node, 'names', []):
                    if getattr(alias, 'name', '').startswith('wiretap'):
                        hits.append(
                            "  • [AST] import wiretap — crash-prone module.\n"
                            "    ✅ Instead: use the standard flame module API."
                        )
            # Catch:  flame.batch.render()  via any attribute access chain
            if isinstance(node, _ast.Call):
                func = node.func
                if isinstance(func, _ast.Attribute) and func.attr == 'render':
                    owner = func.value
                    if isinstance(owner, _ast.Attribute) and owner.attr == 'batch':
                        hits.append(
                            "  • [AST] flame.batch.render() — blocks Flame main thread.\n"
                            "    ✅ Instead: use schedule_idle_event(render_fn)."
                        )
    except SyntaxError:
        pass  # syntax errors will be caught later by exec()
    except Exception:
        pass  # AST check is best-effort — never block on parse failure

    # A2-EXT — PyExporter.export() called outside schedule_idle_event hangs Flame
    # even with foreground=False, because the Qt event loop cannot process the export
    # while the Python hook thread is still blocked waiting to return.
    if re.search(r'\bPyExporter\s*\(', code) and not re.search(r'schedule_idle_event', code):
        hits.append(
            "  • PyExporter().export() called without schedule_idle_event — "
            "this hangs Flame's main thread even with foreground=False.\n"
            "    ✅ Instead:\n"
            "       def _do_export():\n"
            "           exporter = flame.PyExporter()\n"
            "           exporter.foreground = False\n"
            "           exporter.export([seq], preset_path, output_dir)\n"
            "       flame.schedule_idle_event(_do_export)"
        )

    if not hits:
        return None
    return (
        "🛑 Blocked — contains pattern(s) known to crash Flame:\n\n"
        + "\n\n".join(hits)
        + "\n\nRevise the code and try again. "
        "If unsure of the correct approach, call search_flame_docs first."
    )


# ─── Model write permissions ──────────────────────────────────────────────────
# Only these model families are trusted to write patterns to FLAME_API.md.
# Lightweight models (Qwen, Llama, etc.) are read-only: they may hallucinate
# API paths that contaminate the knowledge base and cause future failures.

WRITE_ALLOWED_MODELS = {
    "claude-opus",        # any Opus version (opus-4-5, opus-4-6, future…)
    "claude-sonnet",      # any Sonnet version (sonnet-4-5, sonnet-4-6, future…)
    "claude-sonnet-4",    # explicit prefix for Sonnet 4.x family
    "claude-sonnet-4-6",  # explicit current release
    "claude-opus-4-5",    # Opus 4.5
}


def _get_config() -> dict:
    """
    Read config.json and return it as a dict.
    B5 — exposes runtime-tunable keys:
      rag_fallback_threshold  int   default 60  — coverage % below which pattern is undocumented
      fallback_model          str   default ""  — model name shown in "switch to X" hints
      write_allowed_models    list  default []  — overrides WRITE_ALLOWED_MODELS when non-empty
    Returns an empty dict on any read/parse failure (callers use .get() with defaults).
    """
    try:
        return json.loads((_SERVER_DIR / "config.json").read_text())
    except Exception:
        return {}


def _get_current_model() -> str:
    """Return the model string from config.json, or 'unknown' on failure."""
    return _get_config().get("model", "unknown")


def _rag_threshold() -> int:
    """B5 — RAG relevance threshold from config (default 60)."""
    return int(_get_config().get("rag_fallback_threshold", 60))


def _fallback_model_name() -> str:
    """B5 — Suggested write-capable model from config (default 'Sonnet')."""
    name = _get_config().get("fallback_model", "")
    return name if name else "Sonnet"


def _model_can_write() -> bool:
    """
    True if the active model is in the write-allowed list.
    B5 — checks config's write_allowed_models first (operator override);
    falls back to the hardcoded WRITE_ALLOWED_MODELS set.
    """
    model = _get_current_model().lower()
    cfg_list = _get_config().get("write_allowed_models")
    if cfg_list:
        return any(allowed.lower() in model for allowed in cfg_list)
    return any(allowed in model for allowed in WRITE_ALLOWED_MODELS)

# ─── Token tracking ───────────────────────────────────────────────────────────

# Combined size of all indexed docs in tokens (baseline for RAG savings display).
# FLAME_API.md ~4,700 + flame_api_full.md ~33,600 = ~38,300 total.
# RAG returns ~3 chunks (~600 tokens) → saving ~37,000 tokens per call vs
# loading all documentation into context.
_FULL_DOC_TOKENS = 38000

# Estimated tokens saved per dedicated tool call (avoids search_flame_docs
# + execute_python round-trip: ~600 RAG + ~200 LLM code generation overhead).
_DEDICATED_TOOL_SAVINGS = 800

_stats = {
    'exec_calls':         0,
    'tokens_in':          0,   # tokens sent to Flame (code)
    'tokens_out':         0,   # tokens received from Flame (output)
    'rag_calls':          0,
    'tokens_saved':       0,   # tokens saved by RAG vs loading full doc
    'dedicated_calls':    0,   # calls to hardcoded tools (no RAG needed)
    'tokens_saved_tools': 0,   # tokens saved by dedicated tools
    'patterns_learned':   0,   # auto-learned patterns added to FLAME_API.md
    'patterns_staged':    0,   # C5 — candidates staged by non-trusted models
    'patterns_failed':    0,   # C5 — failed executions logged for gap analysis
}
# Records when _stats was last reset (server start or Flame crash recovery)
_stats_reset_at = datetime.datetime.now()

# C5 — Staging paths
_CANDIDATES_PATH = _SERVER_DIR / "rag" / "candidates.json"
_FAILED_PATH     = _SERVER_DIR / "rag" / "failed.json"


def _load_json_list(path: Path) -> list[dict]:
    """Read a JSON list file; return [] on missing/corrupt."""
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    except Exception:
        return []


def _save_json_list(path: Path, data: list[dict]) -> None:
    """Write a JSON list file atomically (best-effort)."""
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

# Tracks the max relevance score of the most recent search_flame_docs call.
# Used by the LLM to decide whether to call learn_pattern after a success.
_last_rag_score: int = 100  # default high so we don't nag on first call

# OBS-013: tracks whether search_flame_docs was called in this session.
# execute_python prepends a reminder if the model skips RAG entirely.
_rag_called_this_session: bool = False

# A12 — In-session RAG cache: identical queries return the same chunks
# without hitting ChromaDB again. Flushed when the server restarts.
_search_cache: dict[int, tuple[str, int]] = {}

# A4 — RAG rebuild in-progress flag.
# Set to True while build_index.py is running to warn search_flame_docs()
# that results may be stale. Cleared by a background thread once rebuild ends.
_rag_rebuild_flag: list[bool] = [False]   # list so inner functions can mutate it


def _tok(text: str) -> int:
    """Rough token estimate: 1 token ≈ 3 characters (corrected from //4 which underestimates ~25%)."""
    return max(1, len(text) // 3)


def _validate(output: str, required: list[str]) -> str:
    """
    Check that required fields in a dedicated tool's output are not '—' or empty.
    If any are missing, append a self-healing hint so the model can investigate
    and teach the correct pattern via learn_pattern().

    Args:
        output:   The string output of a dedicated tool.
        required: List of field names that must have real values, e.g. ["Frame rate", "Resolution"].

    Returns:
        The original output, optionally with a warning appended.
    """
    missing = []
    for field in required:
        for line in output.splitlines():
            if line.lower().startswith(field.lower()):
                # Field found — check if value is empty or placeholder
                value = line.split(":", 1)[-1].strip()
                if not value or value in ("—", "—x—", "None", "null", ""):
                    missing.append(field)
                break
        else:
            missing.append(field)  # field not present at all

    if missing:
        fields = ", ".join(missing)
        output += (
            f"\n\n⚠️  SELF-HEAL: [{fields}] returned no value from the dedicated tool. "
            "This means the API path used is wrong or incomplete. "
            "Use execute_python to find the correct way to read these values, "
            "then call learn_pattern(description, code) so future sessions get it right."
        )
    return output


def _rating(tokens: int) -> str:
    """Return an emoji rating based on token count for a single call."""
    if tokens < 500:
        return "🟢 low"
    elif tokens < 2000:
        return "🟡 medium"
    else:
        return "🔴 high"


def _stats_footer() -> str:
    """Return a compact session stats summary."""
    used        = _stats['tokens_in'] + _stats['tokens_out']
    saved_rag   = _stats['tokens_saved']
    saved_tools = _stats['tokens_saved_tools']
    saved_total = saved_rag + saved_tools
    ratio       = f"{saved_total/(used+saved_total)*100:.0f}%" if (used + saved_total) > 0 else "—"
    return (
        f"\n─────────────────────────────\n"
        f"📊 Session · {_stats['exec_calls']} exec · {_stats['rag_calls']} RAG"
        f" · {_stats['dedicated_calls']} tools\n"
        f"   Tokens used       : ~{used}  {_rating(used)}\n"
        f"   Avoided by RAG    : ~{saved_rag}\n"
        f"   Avoided by tools  : ~{saved_tools}\n"
        f"   Total avoided     : ~{saved_total}  ({ratio} of context)"
    )

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = int(os.environ.get('FLAME_BRIDGE_PORT', 4444))  # A8: override via env

# A13 — Unix domain socket path (more secure than TCP; owner-only file permissions).
# Override with FLAME_BRIDGE_SOCKET env var. Falls back to TCP if socket file absent.
_BRIDGE_SOCKET = Path(os.environ.get(
    'FLAME_BRIDGE_SOCKET',
    str(_SERVER_DIR / 'run' / 'flame_mcp.sock')
))

mcp = FastMCP(
    "flame",
    instructions="""
You are controlling Autodesk Flame 2026 via a local bridge (Unix socket).

## MANDATORY WORKFLOW — follow this for every task

1. PICK THE SINGLE RIGHT TOOL — do not chain multiple read tools when one suffices.
   Use the most specific dedicated tool and stop. Do NOT run ping + get_project_info
   + list_libraries as a warmup sequence; go directly to the tool that answers the question.

   QUERY → TOOL LOOKUP (use exactly this tool, nothing else):
   "project name / frame rate / resolution"  → get_project_info()
   "is the bridge connected / is Flame up"   → ping()
   "what version of Flame"                   → get_flame_version()
   "list libraries / show libraries"         → list_libraries()
   "reels in library X"                      → list_reels(library_name)
   "clips in reel / library"                 → list_clips(library_name, reel_name)
   "desktop reels / desktop clips"           → list_desktop_reels()
   "batch groups"                            → list_batch_groups()
   "all projects / other projects on disk"   → list_all_projects()
   "metadata for clip X"                     → get_clip_metadata(library, reel, clip)
   "what is selected / selected clips"       → get_selected_clips()
   "wiretap tree / ifffs"                    → flame_wiretap_tree(path)
   "available logs / log files"              → list_flame_logs()
   "read log / debug log"                    → read_flame_log(name, lines, grep)

   One question = one tool. Do NOT call ping() or get_project_info() before other tools.
   Only fall back to search_flame_docs + execute_python for operations not in this list.

   ★ STOP IMMEDIATELY after the first successful tool result that answers the question.
     Do NOT make additional tool calls to verify, explore, or gather extra context.
     Answer the user with the result you have. This is not optional.
     ★ EXPORT SPECIAL CASE: once execute_python confirms "Export scheduled" or prints
     the output path, STOP — do NOT poll the filesystem, do NOT re-export, do NOT
     call execute_python again to "verify" the file. The export runs asynchronously
     after your call returns; a second call will deadlock Flame.

2. GROUNDING RULE — For anything NOT covered by a dedicated tool:
   - ALWAYS call search_flame_docs FIRST before writing any execute_python code.
   - NEVER guess or invent API method names, attribute paths, or class names.
   - If search returns < 60% relevance, note this explicitly and proceed carefully.
   - On failure, call search_flame_docs again with a different query before retrying.
   - This rule has NO exceptions — not even for patterns you "know" from training.

   C2 — MANDATORY CITATION: Before using any Flame API method, name the RAG chunk
   that justifies it (e.g. "per FLAME_API.md § Batch Groups"). If you cannot cite
   a source, say explicitly: "I have no verified documentation for this" and offer
   to search before executing. NEVER invent Flame API methods.

3. Use the correct object hierarchy:
   - Libraries → flame.projects.current_project.current_workspace.libraries
   - Desktop   → flame.projects.current_project.current_workspace.desktop
   - Never use flame.projects.current_project.libraries (returns None)
   - ws.libraries includes hidden system libraries NOT visible to the user:
     "Timeline FX" and "Grabbed References" — always filter them out:
     HIDDEN = {"Timeline FX", "Grabbed References"}
     visible = [l for l in ws.libraries if str(l.name) not in HIDDEN]

4. Never call flame.batch.render() or PyExporter().export() directly — both block
   Flame's main thread and freeze the application (even with foreground=False).
   ALWAYS schedule via flame.schedule_idle_event():
     def _do_export():
         exporter = flame.PyExporter()
         exporter.foreground = False
         exporter.export([seq], preset_path, output_dir)
     flame.schedule_idle_event(_do_export)
   execute_python will BLOCK any PyExporter call not wrapped in schedule_idle_event.

5. Always print output in execute_python — every call must end with print().
   The result is only visible through stdout capture.
   Generate code as if temperature=0: prefer exact, verified API paths over creative
   alternatives. Accuracy over brevity. Do not guess method names.

6. Keep code minimal. Flame's Python environment is sensitive to long loops
   or anything that blocks the main thread.

7. On success, remember the working pattern for future calls in this session.
   On failure, do NOT retry the same approach — try a different method.

8. Call session_stats when the user asks about efficiency, token usage,
   or at the end of long multi-step tasks. It is not required after every response.

9. BRIDGE CONNECTION — If any tool returns an error that contains
   'Cannot connect to Flame on port', STOP immediately.
   Do NOT call search_flame_docs or execute_python as a fallback —
   they will fail for the exact same reason (bridge is not running).
   Just tell the user: "Flame bridge is not connected — open Flame and
   make sure flame_mcp_bridge.py is installed in /opt/Autodesk/shared/python/."

10. NEVER use these patterns — they crash or hang Flame (execute_python will block them):
   - len(flame.projects) or for x in flame.projects  → PyProjectSelector is not iterable
   - flame.projects.current_project.libraries         → returns None, use ws.libraries
   - flame.batch.render()                             → blocks main thread
   - PyExporter().export() without schedule_idle_event → hangs main thread / deadlock
   - import wiretap                                   → crash-prone
   - dir(flame...)                                    → use search_flame_docs instead
   To list all Flame projects: use list_all_projects() or os.listdir("/opt/Autodesk/project")

10. DEBUGGING — when execute_python returns an error or Flame crashes:
   - Call read_flame_log("flame.log", lines=50, grep="Error|Traceback|Python")
     to get the actual crash trace from the application log.
   - For Wiretap/IFFFS errors: read_flame_log("wiretap.log", grep="ERROR|FAIL")
   - For render issues: read_flame_log with backburner logs.
   - Log files are read directly by the MCP server (no bridge needed).

11. SELF-IMPROVEMENT — after execute_python succeeds:
   - If the preceding search_flame_docs showed max relevance < 60%, the pattern
     was NOT in the docs. Call learn_pattern(description, code) immediately after
     the successful execute_python.
   - description: short label in English, e.g. "delete folder by name from library"
   - code: the exact working Python code that just ran
   - This teaches the system so future sessions find the pattern instantly.
   - Do NOT call learn_pattern if relevance was >= 60% (already documented).
"""
)


# ─── Bridge communication ─────────────────────────────────────────────────────

def _call_flame(code: str, timeout: int = 15) -> dict:
    """
    Send Python code to the Flame bridge.
    A13 — Prefers Unix domain socket (owner-only, no network exposure);
    falls back to TCP if the socket file does not exist.
    Returns the result as a dictionary.
    """
    # A13 — choose transport: Unix socket (preferred) or TCP fallback
    use_unix = hasattr(socket, 'AF_UNIX') and _BRIDGE_SOCKET.exists()
    try:
        if use_unix:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            addr: str | tuple = str(_BRIDGE_SOCKET)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            addr = (BRIDGE_HOST, BRIDGE_PORT)

        with sock as s:
            s.settimeout(timeout)
            s.connect(addr)

            payload = json.dumps({'code': code}) + "\n"
            s.sendall(payload.encode('utf-8'))

            # A5 — cumulative deadline prevents partial-response hangs
            response = b""
            deadline = time.monotonic() + timeout
            while not response.endswith(b"\n"):
                if time.monotonic() > deadline:
                    raise TimeoutError("bridge response timeout")
                chunk = s.recv(4096)
                if not chunk:
                    break
                response += chunk

            return json.loads(response.decode('utf-8').strip())

    except ConnectionRefusedError:
        return {
            'status': 'error',
            'error': (
                'Cannot connect to Flame on port 4444.\n'
                'Check that:\n'
                '  1. Flame is open\n'
                '  2. flame_mcp_bridge.py is in /opt/Autodesk/shared/python/\n'
                '  3. Flame was restarted after installing the bridge'
            )
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def _fmt(result: dict) -> str:
    """Format the bridge response for Claude."""
    if result.get('status') == 'error':
        return f"ERROR:\n{result.get('error', 'Unknown error')}"

    parts = []
    output = result.get('output', '').strip()
    return_value = result.get('return_value', '')

    if output:
        parts.append(output)
    if return_value:
        parts.append(f"Return value: {return_value}")

    return '\n'.join(parts) if parts else '(executed successfully, no output)'


# ─── MCP tools ────────────────────────────────────────────────────────────────

@mcp.tool(annotations=_DST)
def execute_python(
    code: str,
    timeout: Annotated[int, Field(ge=1, le=300, description="TCP timeout in seconds (1–300, default 15)")] = 15,
) -> str:
    """
    Execute arbitrary Python code inside Autodesk Flame.
    Has full access to the flame module and its entire Python API.

    *** STOP — CHECK DEDICATED TOOLS FIRST ***
    Before calling execute_python, check if a dedicated tool already answers
    the question. Using a dedicated tool is ALWAYS faster, more reliable, and
    uses fewer API calls:
    - Project info (name, resolution, fps, bit depth) → get_project_info()
    - List libraries                                  → list_libraries()
    - List reels in a library                         → list_reels()
    - List clips in a library/reel                    → list_clips()
    - Desktop structure (reel groups, reels, clips)   → list_desktop_reels()
    - Batch groups on desktop                         → list_batch_groups()
    - All projects on workstation                     → list_all_projects()
    - Clip technical metadata                         → get_clip_metadata()
    - Currently selected items in Flame               → get_selected_clips()
    - Wiretap IFFFS tree                              → flame_wiretap_tree()
    - Flame log files                                 → list_flame_logs() / read_flame_log()
    Only use execute_python when NO dedicated tool covers the operation.

    MANDATORY: Call search_flame_docs BEFORE writing any execute_python code.
    Never guess API methods, class names, or object hierarchy.

    Key rules:
    - Libraries: use ws = flame.projects.current_project.current_workspace,
      then ws.libraries  (NOT project.libraries — that returns None)
    - Renders: never call flame.batch.render() directly, use schedule_idle_event
    - Selected items: use flame.media_panel.selected_entries (NOT flame.selection)
    - Always end with print() so the result is visible

    Args:
        code:    Python code to execute inside Flame.
        timeout: TCP socket timeout in seconds (default 15). Increase for
                 long-running operations like media imports or batch renders.

    Example:
        execute_python("print(flame.projects.current_project.name)")
        execute_python(long_import_code, timeout=60)
    """
    danger = _check_dangerous(code)
    if danger:
        return danger + _stats_footer()

    # Bug 3 (OBS-013): server-side pattern redirect — if the submitted code
    # clearly matches something a dedicated tool does, refuse execution and
    # tell the model exactly which tool to use instead.
    _REDIRECT_PATTERNS = [
        # (regex pattern in code,  redirect message)
        (r'get_project_info|current_project.*\.(name|description|workspaces)',
         "Use get_project_info() — it returns project name, resolution, fps, "
         "bit depth via Wiretap XML. execute_python cannot access those fields."),
        (r'ws\.libraries|current_workspace\.libraries|getLibraries',
         "Use list_libraries() — it filters hidden system libraries automatically."),
        (r'\.reels|getReels\(',
         "Use list_reels(library_name) — returns all reels for a library in one call."),
        (r'getEntries\(|\.clips|getClips\(',
         "Use list_clips(library_name, reel_name) — returns formatted clip list."),
        (r'reel_groups|getReelGroups|desktop.*reel',
         "Use list_desktop_reels() — returns the full desktop hierarchy with clip names."),
        (r'batch_groups|getBatchGroups|\.batch_group',
         "Use list_batch_groups() — returns batch groups with node and reel counts."),
        (r'flame\.selection',
         "flame.selection does not exist. "
         "Use get_selected_clips() — it uses flame.media_panel.selected_entries correctly."),
        (r'media_panel\.selected_entries',
         "Use get_selected_clips() — the dedicated tool handles this."),
        (r'get_version\(\)|flame\.version',
         "Use get_flame_version() — returns the version string directly."),
        (r'wiretap_print_tree|wiretap_get_children',
         "Use flame_wiretap_tree(path) — it handles host flags and error handling."),
        (r'os\.listdir.*log|/opt/Autodesk/logs',
         "Use list_flame_logs() / read_flame_log() — they list and filter log files."),
    ]
    import re as _re
    import sys as _sys2
    print(
        f"[flame-mcp] execute_python called — "
        f"redirect_check=active  patterns={len(_REDIRECT_PATTERNS)}  "
        f"rag_called={_rag_called_this_session}",
        file=_sys2.stderr, flush=True
    )
    for _pattern, _msg in _REDIRECT_PATTERNS:
        if _re.search(_pattern, code):
            print(f"[flame-mcp] REDIRECT matched pattern: {_pattern}", file=_sys2.stderr, flush=True)
            return (
                f"🚫 REDIRECT — a dedicated tool handles this query:\n"
                f"   {_msg}\n"
                f"   Call the dedicated tool instead of execute_python."
            )

    # OBS-013: nudge the model to use search_flame_docs if it hasn't in this session
    rag_nudge = ""
    if not _rag_called_this_session:
        rag_nudge = (
            "⚠️  REMINDER: Call search_flame_docs before execute_python. "
            "Also check if a dedicated tool (get_project_info, list_libraries, "
            "list_clips, get_selected_clips, etc.) already answers this question.\n"
        )

    # B4 — Low-confidence warning when a read-only model has weak RAG grounding
    # Execution still proceeds; the operator sees the warning and can intervene.
    b4_warning = ""
    if _last_rag_score < _rag_threshold() and not _model_can_write():
        b4_warning = (
            f"\n⚠️  LOW CONFIDENCE EXECUTION — RAG score {_last_rag_score}/100 "
            f"with read-only model ({_get_current_model()}).\n"
            f"   The code below may be based on hallucinated API paths. "
            f"Switch to {_fallback_model_name()} if the result looks wrong.\n"
        )

    t_in  = _tok(code)
    result = _call_flame(code, timeout=timeout)
    output = result.get('output', '') + result.get('error', '')
    t_out = _tok(output)

    _stats['exec_calls'] += 1
    _stats['tokens_in']  += t_in
    _stats['tokens_out'] += t_out

    # C5 — Log failed executions when RAG confidence was low (knowledge gap indicator)
    is_error = bool(result.get('error')) or output.startswith('ERROR') or output.startswith('Traceback')
    if is_error and _last_rag_score < _rag_threshold():
        failed = _load_json_list(_FAILED_PATH)
        failed.append({
            'timestamp':  datetime.datetime.now().isoformat()[:19],
            'rag_score':  _last_rag_score,
            'model':      _get_current_model(),
            'error':      output[:300],
            'code_snippet': code.strip()[:200],
        })
        # Keep last 100 failures max
        _save_json_list(_FAILED_PATH, failed[-100:])
        _stats['patterns_failed'] += 1

    call_rating = _rating(t_in + t_out)
    footer = (
        f"\n─────────────────────────────\n"
        f"🔥 This call · ~{t_in + t_out} tokens  {call_rating}"
        + _stats_footer()
    )
    return rag_nudge + b4_warning + _fmt(result) + footer


def _track_dedicated() -> None:
    """Increment dedicated tool counter and accumulate estimated savings."""
    _stats['dedicated_calls']    += 1
    _stats['tokens_saved_tools'] += _DEDICATED_TOOL_SAVINGS


@mcp.tool(annotations=_RO)
def get_project_info() -> str:
    """
    Return information about the active Flame project: name, frame rate,
    resolution (width x height), bit depth, scan mode, colour space,
    description, and workspace count.

    Use this tool whenever the user asks for project metadata — including
    questions like "what resolution is this project?", "what frame rate?",
    "what bit depth?", "what are the project settings?", or "show project info".

    NOTE: PyProject does NOT expose frame_rate, width, height, or bit_depth
    as Python attributes — they are only available via Wiretap XML metadata.
    This tool retrieves them correctly via wiretap_get_metadata.
    Do NOT use execute_python to read these values; it will return None.
    """
    WTAP = "/opt/Autodesk/wiretap/tools/current"

    # Step 1 — get name + workspace count from Python API (always works)
    result = _call_flame("""
p = flame.projects.current_project
print(f"Name: {str(p.name)}")
print(f"Description: {str(p.description) if p.description else '—'}")
print(f"Workspaces: {str(p.workspaces_count)}")
try:
    print(f"WiretapID: {str(p.get_wiretap_node_id())}")
except Exception as e:
    print(f"WiretapID: ERROR {e}")
""")
    py_out = result.get('output', '').strip()

    # Parse wiretap node id from Python output
    wtap_id = None
    for line in py_out.splitlines():
        if line.startswith("WiretapID:"):
            val = line.split(":", 1)[1].strip()
            if not val.startswith("ERROR"):
                wtap_id = val

    # Step 2 — get frame rate / resolution / bit depth from Wiretap XML metadata
    meta_lines = []
    if wtap_id:
        try:
            proc = subprocess.run(
                [f"{WTAP}/wiretap_get_metadata", "-h", "localhost:IFFFS",
                 "-n", wtap_id, "-s", "XML"],
                capture_output=True, text=True, timeout=10
            )
            xml = proc.stdout
            import re as _re
            def _xml(tag):
                m = _re.search(rf"<{tag}[^>]*>([^<]+)</{tag}>", xml, _re.IGNORECASE)
                return m.group(1).strip() if m else "—"
            meta_lines = [
                f"Frame rate: {_xml('FrameRate')}",
                f"Resolution: {_xml('Width')}x{_xml('Height')}",
                f"Bit depth: {_xml('BitDepth')}",
                f"Scan mode: {_xml('ScanMode')}",
                f"Colour space: {_xml('ColourSpace')}",
            ]
        except Exception as e:
            meta_lines = [f"Wiretap metadata: unavailable ({e})"]
    else:
        meta_lines = ["Frame rate: — (PyProject.get_wiretap_node_id() failed)"]

    # Merge outputs (skip the WiretapID line from display)
    display = [l for l in py_out.splitlines() if not l.startswith("WiretapID:")]
    output = "\n".join(display + meta_lines)
    output = _validate(output, ["Frame rate", "Resolution"])
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return output


@mcp.tool(annotations=_RO)
def list_libraries() -> str:
    """
    List all user-visible libraries in the active Flame project.
    Excludes hidden system libraries ("Timeline FX", "Grabbed References")
    which are not shown in the Flame interface.
    Reports reels, folders, and reel_groups per library.
    """
    code = """
ws = flame.projects.current_project.current_workspace
HIDDEN = {"Timeline FX", "Grabbed References"}
visible = [l for l in ws.libraries if str(l.name) not in HIDDEN]
if not visible:
    print("No libraries found.")
for lib in visible:
    name    = str(lib.name)
    reels   = len(lib.reels)
    try:
        folders = len(list(lib.folders or []))
    except Exception:
        folders = 0
    try:
        reel_groups = len(lib.reel_groups)
    except Exception:
        reel_groups = 0
    parts = []
    if reels:       parts.append(f"{reels} reel{'s' if reels != 1 else ''}")
    if folders:     parts.append(f"{folders} folder{'s' if folders != 1 else ''}")
    if reel_groups: parts.append(f"{reel_groups} reel group{'s' if reel_groups != 1 else ''}")
    summary = ", ".join(parts) if parts else "empty"
    print(f"  {name}  ({summary})")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    output = _validate(output, ["Libraries"])
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def list_reels(library_name: str = "") -> str:
    """
    List reels in a library. If no library name is given,
    shows reels across all user-visible libraries.
    Excludes hidden system libraries ("Timeline FX", "Grabbed References").
    """
    if library_name:
        safe_lib = repr(library_name)
        code = f"""
ws = flame.projects.current_project.current_workspace
lib = next((l for l in ws.libraries if str(l.name) == {safe_lib}), None)
if lib is None:
    print(f"Library {safe_lib} not found.")
else:
    for reel in lib.reels:
        print(f"  {{str(reel.name)}}  ({{len(reel.clips)}} clips)")
"""
    else:
        code = """
ws = flame.projects.current_project.current_workspace
HIDDEN = {"Timeline FX", "Grabbed References"}
for lib in ws.libraries:
    if str(lib.name) in HIDDEN:
        continue
    print(f"[{str(lib.name)}]")
    for reel in lib.reels:
        print(f"  {str(reel.name)}  ({len(reel.clips)} clips)")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def list_clips(
    library_name: str = "",
    reel_name: str = "",
    limit: Annotated[int, Field(ge=0, le=5000, description="Max clips per reel (0 = unlimited, default 50)")] = 50,
) -> str:
    """
    List clips inside a library, optionally filtered by reel name.
    If library_name is empty, lists clips across all user-visible libraries.
    If reel_name is also given, shows only that reel's clips.
    Excludes hidden system libraries ("Timeline FX", "Grabbed References").
    Use this instead of execute_python for any 'show/list clips' request.

    Args:
        library_name: Filter to a specific library (empty = all libraries).
        reel_name:    Filter to a specific reel within the library.
        limit:        Maximum clips to show per reel (default 50, 0 = unlimited).
    """
    safe_lib  = repr(library_name)
    safe_reel = repr(reel_name)

    if library_name:
        code = f"""
ws = flame.projects.current_project.current_workspace
lib = next((l for l in ws.libraries if str(l.name) == {safe_lib}), None)
if lib is None:
    print(f"Library {safe_lib} not found.")
else:
    reel_filter = {safe_reel}
    limit = {limit}
    found = False
    for reel in lib.reels:
        if reel_filter and str(reel.name) != reel_filter:
            continue
        found = True
        clips = list(reel.clips)
        total = len(clips)
        shown = clips if limit <= 0 else clips[:limit]
        print(f"[{{str(lib.name)}}] / [{{str(reel.name)}}] — {{total}} clip(s)")
        for c in shown:
            dur = getattr(c, 'duration', None)
            dur_str = f"  {{dur}}" if dur else ""
            print(f"  {{str(c.name)}}{{dur_str}}")
        if limit > 0 and total > limit:
            print(f"  … and {{total - limit}} more (use limit=0 to see all)")
    if not found:
        print(f"No reels matched filter {safe_reel}.")
"""
    else:
        code = f"""
ws = flame.projects.current_project.current_workspace
HIDDEN = {{"Timeline FX", "Grabbed References"}}
limit = {limit}
for lib in ws.libraries:
    if str(lib.name) in HIDDEN:
        continue
    for reel in lib.reels:
        clips = list(reel.clips)
        if clips:
            total = len(clips)
            shown = clips if limit <= 0 else clips[:limit]
            print(f"[{{str(lib.name)}}] / [{{str(reel.name)}}] — {{total}} clip(s)")
            for c in shown:
                print(f"  {{str(c.name)}}")
            if limit > 0 and total > limit:
                print(f"  … and {{total - limit}} more (use limit=0 to see all)")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def list_desktop_reels() -> str:
    """
    List the full desktop structure: reel groups, reels, and clip names.
    Use this for ANY request about desktop contents, clips in desktop, or
    'what's on the desktop' — it returns everything in one call.
    Includes clip names so no follow-up execute_python call is needed.
    """
    code = """
ws = flame.projects.current_project.current_workspace
desktop = ws.desktop
for rg in desktop.reel_groups:
    print(f"[{str(rg.name)}]")
    for reel in rg.reels:
        clips = list(reel.clips)
        print(f"  {str(reel.name)}  ({len(clips)} clips)")
        for c in clips:
            print(f"    {str(c.name)}")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def list_batch_groups() -> str:
    """
    List all batch groups in the active desktop with their reel counts.
    Use this instead of execute_python for any 'show batch groups' request.
    Batch groups live on the desktop alongside regular reel groups.
    """
    code = """
ws = flame.projects.current_project.current_workspace
desktop = ws.desktop
try:
    batch_groups = list(desktop.batch_groups)
except Exception:
    batch_groups = []
if not batch_groups:
    print("No batch groups found on the desktop.")
else:
    print(f"{len(batch_groups)} batch group(s):")
    for bg in batch_groups:
        name = str(bg.name)
        try:
            reels = len(bg.reels)
        except Exception:
            reels = 0
        try:
            nodes = len(bg.nodes) if hasattr(bg, 'nodes') else 0
        except Exception:
            nodes = 0
        parts = []
        if reels: parts.append(f"{reels} reel(s)")
        if nodes: parts.append(f"{nodes} node(s)")
        summary = ", ".join(parts) if parts else "empty"
        print(f"  {name}  ({summary})")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def list_all_projects() -> str:
    """
    List all Flame projects available on this workstation.
    Shows which project is currently active.
    Uses the /opt/Autodesk/project directory — does not require switching projects.
    """
    code = """
import os
projects_dir = "/opt/Autodesk/project"
try:
    entries = sorted(os.listdir(projects_dir))
    projects = [
        e for e in entries
        if os.path.isdir(os.path.join(projects_dir, e)) and not e.startswith('.')
    ]
    current = str(flame.projects.current_project.name)
    print(f"Active project: {current}")
    print(f"All projects ({len(projects)}):")
    for p in projects:
        marker = "  ◀ active" if p == current else ""
        print(f"  {p}{marker}")
except Exception as e:
    print(f"Error listing projects: {e}")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def get_clip_metadata(library_name: str, reel_name: str, clip_name: str) -> str:
    """
    Get detailed metadata for a specific clip: resolution, frame rate, duration,
    timecode, bit depth, tape name, and other available attributes.

    Args:
        library_name: Name of the library containing the clip.
        reel_name:    Name of the reel inside that library.
        clip_name:    Name of the clip to inspect.
    """
    safe_lib  = repr(library_name)
    safe_reel = repr(reel_name)
    safe_clip = repr(clip_name)
    code = f"""
ws = flame.projects.current_project.current_workspace
lib = next((l for l in ws.libraries if str(l.name) == {safe_lib}), None)
if lib is None:
    print(f"Library {safe_lib} not found.")
else:
    reel = next((r for r in lib.reels if str(r.name) == {safe_reel}), None)
    if reel is None:
        print(f"Reel {safe_reel} not found in library {safe_lib}.")
    else:
        clip = next((c for c in reel.clips if str(c.name) == {safe_clip}), None)
        if clip is None:
            print(f"Clip {safe_clip} not found in reel {safe_reel}.")
        else:
            attrs = [
                'name', 'duration', 'frame_rate', 'width', 'height',
                'bit_depth', 'start_frame', 'end_frame', 'timecode',
                'tape_name', 'source_timecode', 'ratio', 'scan_format',
            ]
            print(f"Clip: {{str(clip.name)}}")
            for attr in attrs:
                if attr == 'name':
                    continue
                v = getattr(clip, attr, None)
                if v is not None:
                    try:
                        print(f"  {{attr}}: {{str(v)}}")
                    except Exception:
                        pass
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    output = _validate(output, ["frame_rate", "width", "duration"])
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def get_selected_clips() -> str:
    """
    Return the clips or items currently selected in the Flame media panel or desktop.
    Useful for contextual operations: 'what do I have selected right now?'
    Returns name and type for each selected item.

    IMPORTANT: The correct API is flame.media_panel.selected_entries — NOT
    flame.selection (which does not exist and will raise AttributeError).
    Do NOT use execute_python with flame.selection to answer this question;
    use this dedicated tool instead.
    """
    code = """
try:
    sel = list(flame.media_panel.selected_entries)
    if not sel:
        print("No items currently selected.")
    else:
        print(f"{len(sel)} item(s) selected:")
        for item in sel:
            t = type(item).__name__
            print(f"  {str(item.name)}  [{t}]")
except Exception as e:
    print(f"Could not get selection: {e}")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def flame_wiretap_tree(path: str = "/") -> str:
    """
    Inspect the Wiretap IFFFS node tree at the given path using the
    wiretap_print_tree CLI tool. This exposes the underlying content
    database that Flame uses, including inactive projects and raw node metadata.

    The IFFFS hierarchy is:
        /projects → PROJECT(UUID) → WORKSPACE → DESKTOP / LIBRARY_LIST → ...

    Use this to:
    - Explore projects without switching the active project
    - Find UUIDs for cross-project operations
    - Inspect raw node structure not visible in the Flame UI

    Args:
        path: IFFFS node path to inspect (default "/" = root).
              Examples: "/projects", "/projects/<uuid>", "/projects/<uuid>/workspace"

    Note: Runs the CLI tool via subprocess — does NOT execute code inside Flame.
    """
    wt_tool = "/opt/Autodesk/wiretap/tools/current/wiretap_print_tree"
    host    = "localhost:IFFFS"
    try:
        proc = subprocess.run(
            [wt_tool, "-h", host, "-n", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = proc.stdout.strip()
        err    = proc.stderr.strip()
        if output:
            _track_dedicated()
            return output
        if err:
            # Common failure: IFFFS daemon not running or wrong host
            if "No route to host" in err or "Connection refused" in err or "IFFFS" in err:
                return (
                    f"❌ Cannot connect to IFFFS at {host}\n"
                    f"  Detail: {err}\n"
                    "  Check that the Flame IFFFS daemon is running:\n"
                    "    /opt/Autodesk/wiretap/tools/current/wiretap_ping localhost"
                )
            return f"⚠️  wiretap_print_tree stderr:\n{err}"
        return "(no output — path may be empty or not found)"
    except FileNotFoundError:
        return (
            f"❌ Wiretap CLI not found at:\n  {wt_tool}\n"
            "Check that Flame is installed at /opt/Autodesk/."
        )
    except subprocess.TimeoutExpired:
        return "❌ wiretap_print_tree timed out (>10 s) — tree may be very large."
    except Exception as e:
        return f"❌ Error running wiretap_print_tree: {e}"


@mcp.tool(annotations=_RO)
def get_flame_version() -> str:
    """Return the running Flame version string."""
    code = "print(flame.get_version())"
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    _track_dedicated()
    return _fmt(result)


@mcp.tool(annotations=_RO)
def ping() -> str:
    """
    Check whether the TCP bridge to Autodesk Flame is reachable.
    Use this to answer any question about bridge/connection status.
    Returns 'connected' with Flame version, or a clear error message.
    No Flame state is modified. Safe to call at any time.
    """
    result = _call_flame("print(flame.get_version())")
    if result.get('status') == 'error':
        return f"🔴 Bridge not connected — {result.get('error', 'unknown error')}"
    version = result.get('output', '').strip()
    _stats['tokens_out'] += _tok(version)
    _track_dedicated()
    return f"🟢 Bridge connected — Flame {version}"


# ─── RAG: documentation search ────────────────────────────────────────────────

@mcp.tool(annotations=_RO)
def search_flame_docs(query: str) -> str:
    """
    Search the local Flame API documentation index for content relevant to the query.
    Uses semantic (vector) search — understands meaning, not just keywords.

    Call this tool ALWAYS, before every execute_python call, no exceptions.
    Never assume you know the correct API method, class name, or pattern.

    Examples:
        search_flame_docs("how to import media into a reel")
        search_flame_docs("create batch group with reels")
        search_flame_docs("export clip with preset")
        search_flame_docs("get selected clips from media panel")
        search_flame_docs("library reel clip hierarchy")

    Returns the most relevant sections from FLAME_API.md and any other
    indexed documentation, with relevance scores.

    If the index has not been built yet, returns setup instructions.
    """
    global _last_rag_score, _rag_called_this_session
    try:
        from rag.search import search

        # A12 — Return cached result for identical queries within this session
        cache_key = hash(query)
        if cache_key in _search_cache:
            cached_result, cached_score = _search_cache[cache_key]
            _last_rag_score = cached_score
            _stats['rag_calls'] += 1   # OBS-009: count cache hits too
            _rag_called_this_session = True
            return cached_result + "\n📎 (cached result — same query this session)"

        result, max_score = search(query, n_results=5)
        _last_rag_score = max_score
        result_tokens = _tok(result)
        saved = max(0, _FULL_DOC_TOKENS - result_tokens)
        _stats['rag_calls']    += 1
        _stats['tokens_saved'] += saved
        _rag_called_this_session = True

        # B2 — Coverage note depends on model write permissions
        coverage_note = ""
        if max_score < _rag_threshold():
            if _model_can_write():
                # Sonnet/Opus: offer to learn the new pattern
                coverage_note = (
                    f"\n⚠️  Low RAG coverage (max {max_score}%) — pattern may not be documented. "
                    "If execute_python succeeds, call learn_pattern(description, code) to teach the system."
                )
            else:
                # Read-only model: inform but don't offer to learn
                coverage_note = (
                    f"\n⚠️  Low RAG coverage (max {max_score}%). "
                    f"ℹ️  Read-only mode ({_get_current_model()}) — switch to {_fallback_model_name()} to save new patterns."
                )

        # A4 — Warn if RAG index is being rebuilt right now
        rebuild_note = (
            "\n⏳ Note: RAG index is currently being rebuilt — results may be stale."
            if _rag_rebuild_flag[0] else ""
        )
        footer = (
            f"\n─────────────────────────────\n"
            f"🔍 RAG · max relevance {max_score}% · ~{result_tokens} tokens · ~{saved} saved vs full doc"
            f"{coverage_note}{rebuild_note}"
            + _stats_footer()
        )
        full_result = result + footer
        _search_cache[cache_key] = (result, max_score)   # A12 — cache for this session
        return full_result
    except Exception as e:
        return (
            f"search_flame_docs error: {e}\n\n"
            "To build the index:\n"
            "  cd ~/Projects/flame-mcp\n"
            "  source .venv/bin/activate\n"
            "  python rag/build_index.py"
        )


# ─── Self-improvement: auto-learn new patterns ────────────────────────────────

@mcp.tool(annotations=_RW)
def learn_pattern(description: str, code: str) -> str:
    """
    Add a new working code pattern to FLAME_API.md and rebuild the RAG index.

    Call this after successfully executing code when search_flame_docs returned
    max relevance < 60% — meaning the pattern was not in the documentation.
    The system will learn it so future sessions find it instantly.

    Args:
        description: Short English label, e.g. "delete folder by name from library"
        code:        The exact working Python code that just ran successfully.
    """
    # B1/B3 — Write permission gate: only whitelisted models may modify FLAME_API.md.
    # C5 — Non-trusted models are staged in rag/candidates.json instead of rejected.
    if not _model_can_write():
        current_model = _get_current_model()
        candidates = _load_json_list(_CANDIDATES_PATH)
        # Deduplicate by description
        if not any(c.get('description', '').lower()[:40] == description.lower()[:40]
                   for c in candidates):
            candidates.append({
                'id':          f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(candidates)}",
                'status':      'candidate',
                'description': description,
                'code':        code.strip(),
                'model':       current_model,
                'timestamp':   datetime.datetime.now().isoformat()[:19],
            })
            _save_json_list(_CANDIDATES_PATH, candidates)
            _stats['patterns_staged'] += 1
            return (
                f"📋 Pattern staged for review: '{description}'\n"
                f"   Saved to rag/candidates.json (model: {current_model} — read-only).\n"
                f"   A trusted model (Sonnet/Opus) can promote it to FLAME_API.md."
            )
        return (
            f"📋 Pattern already staged: '{description}' — already in candidates.json."
        )

    api_doc = _SERVER_DIR / "FLAME_API.md"
    build_script = _SERVER_DIR / "rag" / "build_index.py"

    # Normalise code — strip leading/trailing blank lines
    code = code.strip()

    # Avoid duplicates: check if a very similar description already exists
    content = api_doc.read_text(encoding='utf-8')
    safe_desc = re.escape(description[:40])
    if re.search(safe_desc, content, re.IGNORECASE):
        return (
            f"⚠️  Pattern '{description}' already appears to be documented. "
            "No change made."
        )

    # Build the new pattern block with traceability metadata (FASE 4)
    divider = "─" * 70
    model_tag = f"<!-- model:{_get_current_model()} date:{datetime.datetime.now().isoformat()[:10]} -->"
    block = (
        f"\n# ── Auto-learned: {description} {divider[:max(0,70-len(description)-16)]}\n"
        f"{model_tag}\n"
        f"```python\n{code}\n```\n"
    )

    # Insert before "## Notes & Gotchas" so it stays in Common Patterns area
    marker = "## Notes & Gotchas"
    if marker not in content:
        # Fallback: append at end of file
        new_content = content.rstrip() + "\n\n## Auto-learned Patterns\n" + block + "\n"
    else:
        new_content = content.replace(marker, block + "\n" + marker, 1)

    api_doc.write_text(new_content, encoding='utf-8')
    _stats['patterns_learned'] += 1

    # Rebuild RAG index in the background (non-blocking)
    # A4 — Lock file + in-memory flag prevent concurrent readers from using a
    #      partially-rebuilt ChromaDB. Cleared by a cleanup thread once done.
    _lock_file = _SERVER_DIR / "rag" / ".rebuilding"
    try:
        python_exe = sys.executable
        _lock_file.touch(exist_ok=True)
        _rag_rebuild_flag[0] = True
        _search_cache.clear()   # A4 — invalidate stale cached results

        proc = subprocess.Popen(
            [python_exe, str(build_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def _rag_cleanup(p: subprocess.Popen, lock: Path) -> None:
            p.wait()
            _rag_rebuild_flag[0] = False
            try:
                lock.unlink(missing_ok=True)
            except Exception:
                pass

        import threading as _threading
        _threading.Thread(
            target=_rag_cleanup, args=(proc, _lock_file), daemon=True
        ).start()

        rebuild_status = "RAG index rebuild started in background ✅"
    except Exception as e:
        _rag_rebuild_flag[0] = False
        try:
            _lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        rebuild_status = f"RAG index rebuild failed: {e}"

    return (
        f"✅ Pattern learned: '{description}'\n"
        f"   Added to FLAME_API.md\n"
        f"   {rebuild_status}\n"
        f"   Total patterns learned this session: {_stats['patterns_learned']}"
    )


# ─── Session stats ────────────────────────────────────────────────────────────

@mcp.tool(annotations=_RO)
def session_stats() -> str:
    """
    Return a summary of token usage and RAG savings for this session.
    Call this at any time to see how efficient the current session has been.
    """
    used        = _stats['tokens_in'] + _stats['tokens_out']
    saved_rag   = _stats['tokens_saved']
    saved_tools = _stats['tokens_saved_tools']
    saved_total = saved_rag + saved_tools
    total       = used + saved_total
    pct         = f"{saved_total/total*100:.0f}%" if total > 0 else "—"
    learned     = _stats['patterns_learned']
    exec_calls  = _stats['exec_calls']
    rag_calls   = _stats['rag_calls']

    # Warn only when execute_python was called more times than search_flame_docs
    unguarded = max(0, exec_calls - rag_calls)
    if saved_total > used:
        efficiency = "  ✅ Compact — avoided tokens exceed used tokens"
    elif exec_calls == 0 and _stats['dedicated_calls'] > 0:
        efficiency = "  ✅ Compact — all queries handled by dedicated tools"
    elif unguarded > 0:
        efficiency = f"  ⚠️  {unguarded} execute_python call(s) without prior search_flame_docs"
    else:
        efficiency = "  ✅ All execute_python calls preceded by search_flame_docs"

    since = _stats_reset_at.strftime('%H:%M:%S')
    return (
        f"📊 Session summary  (since {since})\n"
        f"{'─'*32}\n"
        f"  execute_python calls      : {exec_calls}\n"
        f"  search_flame_docs calls   : {rag_calls}\n"
        f"  dedicated tool calls      : {_stats['dedicated_calls']}\n"
        f"  Patterns learned          : {learned}"
        + (" 🧠 self-improved!" if learned > 0 else "") + "\n"
        f"  Patterns staged (C5)      : {_stats['patterns_staged']}"
        + (" — review rag/candidates.json" if _stats['patterns_staged'] > 0 else "") + "\n"
        f"  Failed low-RAG execs (C5) : {_stats['patterns_failed']}"
        + (" — gaps logged in rag/failed.json" if _stats['patterns_failed'] > 0 else "") + "\n"
        f"  Tokens sent (code)        : ~{_stats['tokens_in']}\n"
        f"  Tokens received (output)  : ~{_stats['tokens_out']}\n"
        f"  Total tokens used         : ~{used}  {_rating(used)}\n"
        f"{'─'*32}\n"
        f"  Avoided by RAG            : ~{saved_rag}\n"
        f"  Avoided by tools          : ~{saved_tools}\n"
        f"  Total avoided             : ~{saved_total}  ({pct} of context)\n"
        f"{'─'*32}\n"
        + efficiency
    )


# ─── Flame log reader ─────────────────────────────────────────────────────────

_LOGS_DIR = Path("/opt/Autodesk/logs")


@mcp.tool(annotations=_RO)
def list_flame_logs() -> str:
    """
    List all log files available in /opt/Autodesk/logs.
    Shows file name, size, and last-modified time.
    Use this to discover which logs exist before calling read_flame_log.

    Log categories typically found:
    - Flame application logs  (flame*.log)
    - Wiretap / IFFFS logs    (wiretap*.log, IFFFS*.log)
    - Backburner render logs  (backburner*.log, bb_*.log)
    - Python hook logs        (python*.log)
    """
    if not _LOGS_DIR.exists():
        return f"❌ Log directory not found: {_LOGS_DIR}"

    try:
        entries = sorted(_LOGS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        logs = [e for e in entries if e.is_file()]
        if not logs:
            return f"No log files found in {_LOGS_DIR}"

        lines = [f"📁 {_LOGS_DIR}  ({len(logs)} files)\n"]
        for p in logs:
            stat = p.stat()
            size  = stat.st_size
            mtime = stat.st_mtime
            ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            if size >= 1_048_576:
                sz = f"{size/1_048_576:.1f} MB"
            elif size >= 1024:
                sz = f"{size/1024:.0f} KB"
            else:
                sz = f"{size} B"
            lines.append(f"  {p.name:<45}  {sz:>8}  {ts}")

        _track_dedicated()
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error listing logs: {e}"


@mcp.tool(annotations=_RO)
def read_flame_log(
    log_name: Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[^/\\]+$',
                                   description="Log filename only, no path separators")],
    lines: Annotated[int, Field(ge=0, le=50000, description="Lines from end (0 = all, default 100)")] = 100,
    grep: str = "",
) -> str:
    """
    Read the last N lines of a Flame log file from /opt/Autodesk/logs.
    Optionally filter lines by a keyword or regex pattern.

    Runs directly on the MCP server — does NOT require the Flame bridge.
    Works even when Flame is crashed or not running.

    Args:
        log_name: Log filename (e.g. "flame.log", "wiretap.log").
                  Use list_flame_logs() first to see available files.
        lines:    Number of lines to return from the end of the file (default 100).
                  Use a larger value (e.g. 500) for crash analysis.
        grep:     Optional regex/keyword to filter lines (case-insensitive).
                  Examples: "ERROR", "traceback", "python", "IFFFS", "crash"

    Typical use cases:
        read_flame_log("flame.log", lines=50)              # last 50 lines
        read_flame_log("flame.log", grep="ERROR")          # all error lines
        read_flame_log("wiretap.log", grep="IFFFS")        # IFFFS operations
        read_flame_log("flame.log", lines=200, grep="Traceback|Error|crash")
    """
    # A9 — Explicit path traversal guard: Pydantic blocks '/' and '\' but '..' passes through.
    if '..' in log_name or log_name.startswith('.'):
        return "❌ Error: invalid log name (path traversal not allowed)"
    log_path = _LOGS_DIR / log_name
    if not log_path.exists():
        # Suggest close matches
        try:
            candidates = [p.name for p in _LOGS_DIR.iterdir()
                          if p.is_file() and log_name.lower().split('.')[0] in p.name.lower()]
        except Exception:
            candidates = []
        suggestion = f"\nDid you mean: {candidates}" if candidates else ""
        return f"❌ Log file not found: {log_path}{suggestion}\nCall list_flame_logs() to see available files."

    try:
        # A7 — Reverse-chunk tail: read only what we need from the end of the file.
        # Avoids loading gigabyte log files into RAM.
        def _tail_file(path: Path, max_lines: int) -> list[str]:
            with open(path, 'rb') as f:
                f.seek(0, 2)
                pos, collected = f.tell(), []
                partial = b""
                while pos > 0 and len(collected) < max_lines:
                    chunk_size = min(8192, pos)
                    pos -= chunk_size
                    f.seek(pos)
                    chunk = f.read(chunk_size) + partial
                    split = chunk.split(b"\n")
                    partial = split[0]
                    collected = split[1:] + collected
                if partial:
                    collected = [partial] + collected
                return [ln.decode('utf-8', errors='replace') + "\n"
                        for ln in collected[-max_lines:]]

        max_to_read = min(lines if lines > 0 else 50000, 50000)
        all_lines = _tail_file(log_path, max_to_read)
        total_lines = log_path.stat().st_size  # approximate via size for display

        # Apply grep filter if specified
        if grep:
            try:
                pattern = re.compile(grep, re.IGNORECASE)
                filtered = [l for l in all_lines if pattern.search(l)]
                source_desc = f"grep={repr(grep)} matched {len(filtered)} lines"
                tail = filtered[-lines:] if lines > 0 else filtered
            except re.error as e:
                return f"❌ Invalid grep pattern {repr(grep)}: {e}"
        else:
            filtered = all_lines
            source_desc = f"{len(all_lines)} lines read (tail)"
            tail = all_lines[-lines:] if lines > 0 else all_lines

        shown = len(tail)
        header = (
            f"📋 {log_name}  ({source_desc})"
            + (f"  — showing last {shown}" if shown < len(filtered) else f"  — showing all {shown}")
            + "\n" + "─" * 60 + "\n"
        )

        content = "".join(tail)
        _track_dedicated()
        return header + content

    except Exception as e:
        return f"❌ Error reading {log_name}: {e}"


# ─── Startup: auto-sync tool permissions ─────────────────────────────────────

def _sync_tool_permissions() -> None:
    """
    On every server start, ensure all @mcp.tool functions are listed in
    .claude/settings.local.json.  This prevents OBS-006 from recurring:
    any new tool added to flame_mcp_server.py is auto-approved the next
    time the server (re-)starts — no manual settings edit needed.
    """
    settings_path = _SERVER_DIR / ".claude" / "settings.local.json"
    try:
        import ast as _ast
        # Derive all current tool names from this file's own source
        with open(__file__) as _f:
            _tree = _ast.parse(_f.read())
        current_tools = set()
        for _node in _ast.walk(_tree):
            if isinstance(_node, _ast.FunctionDef):
                for _dec in _node.decorator_list:
                    if (isinstance(_dec, _ast.Call)
                            and isinstance(_dec.func, _ast.Attribute)
                            and _dec.func.attr == 'tool'):
                        current_tools.add(f'mcp__flame__{_node.name}')

        # Load existing settings (or start from empty)
        if settings_path.exists():
            existing = json.loads(settings_path.read_text())
        else:
            existing = {}
        existing.setdefault('permissions', {}).setdefault('allow', [])
        allowed = set(existing['permissions']['allow'])

        new_tools = current_tools - allowed
        if new_tools:
            existing['permissions']['allow'] = sorted(
                allowed | new_tools,
                key=lambda x: (not x.startswith('mcp__'), x)
            )
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(existing, indent=2) + '\n')
            # Log to stderr (visible in Claude Code logs, not in tool output)
            import sys
            print(f'[flame-mcp] Auto-approved {len(new_tools)} new tool(s): '
                  f'{", ".join(sorted(new_tools))}', file=sys.stderr)
    except Exception as _e:
        import sys
        print(f'[flame-mcp] Warning: could not sync tool permissions: {_e}',
              file=sys.stderr)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    _mtime = datetime.datetime.fromtimestamp(
        __import__('os').path.getmtime(__file__)
    ).strftime('%Y-%m-%d %H:%M:%S')
    print(
        f"[flame-mcp] server start  file={__file__}  mtime={_mtime}  "
        f"redirects={len(_REDIRECT_PATTERNS)}  pid={__import__('os').getpid()}",
        file=_sys.stderr, flush=True
    )
    _sync_tool_permissions()
    mcp.run(transport='stdio')
