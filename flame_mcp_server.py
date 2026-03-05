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
from pathlib import Path
from mcp.server.fastmcp import FastMCP

_SERVER_DIR = Path(__file__).parent

# Make rag/ importable when running from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
]


def _check_dangerous(code: str):
    """
    Scan code for patterns known to crash Flame.
    Returns a formatted error string if any are found, else None.
    """
    hits = []
    for pattern, reason, alternative in _DANGEROUS_PATTERNS:
        if re.search(pattern, code):
            hits.append(f"  • {reason}\n    ✅ Instead: {alternative}")
    if not hits:
        return None
    return (
        "🛑 Blocked — contains pattern(s) known to crash Flame:\n\n"
        + "\n\n".join(hits)
        + "\n\nRevise the code and try again. "
        "If unsure of the correct approach, call search_flame_docs first."
    )

# ─── Token tracking ───────────────────────────────────────────────────────────

# Combined size of all indexed docs in tokens (baseline for RAG savings display).
# FLAME_API.md ~4,700 + flame_api_full.md ~33,600 = ~38,300 total.
# RAG returns ~3 chunks (~600 tokens) → saving ~37,000 tokens per call vs
# loading all documentation into context.
_FULL_DOC_TOKENS = 38000

_stats = {
    'exec_calls':      0,
    'tokens_in':       0,   # tokens sent to Flame (code)
    'tokens_out':      0,   # tokens received from Flame (output)
    'rag_calls':       0,
    'tokens_saved':    0,   # tokens saved by RAG vs loading full doc
    'patterns_learned': 0,  # auto-learned patterns added to FLAME_API.md
}

# Tracks the max relevance score of the most recent search_flame_docs call.
# Used by the LLM to decide whether to call learn_pattern after a success.
_last_rag_score: int = 100  # default high so we don't nag on first call


def _tok(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


def _rating(tokens: int) -> str:
    """Return an emoji rating based on token count for a single call."""
    if tokens < 100:
        return "🟢 low"
    elif tokens < 400:
        return "🟡 medium"
    else:
        return "🔴 high"


def _stats_footer() -> str:
    """Return a compact session stats summary."""
    used   = _stats['tokens_in'] + _stats['tokens_out']
    saved  = _stats['tokens_saved']
    ratio  = f"{saved/(used+saved)*100:.0f}%" if (used + saved) > 0 else "—"
    return (
        f"\n─────────────────────────────\n"
        f"📊 Session · {_stats['exec_calls']} exec · {_stats['rag_calls']} RAG\n"
        f"   Tokens used    : ~{used}  {_rating(used)}\n"
        f"   Tokens saved (RAG): ~{saved}  ({ratio} of total)"
    )

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 4444

mcp = FastMCP(
    "flame",
    instructions="""
You are controlling Autodesk Flame 2026 via a TCP bridge (port 4444).

## MANDATORY WORKFLOW — follow this for every task

1. ALWAYS call search_flame_docs FIRST before writing any execute_python code.
   Use a short query describing what you need, e.g. "import clip to reel",
   "create batch group", "get selected clips". This saves tokens and finds
   the correct API patterns. Only skip this if the task is trivially simple
   (e.g. print project name).

2. Use the correct object hierarchy:
   - Libraries → flame.projects.current_project.current_workspace.libraries
   - Desktop   → flame.projects.current_project.current_workspace.desktop
   - Never use flame.projects.current_project.libraries (returns None)

3. Never call flame.batch.render() directly — it crashes Flame.
   Schedule renders via flame.schedule_idle_event(render_fn).

4. Always print output in execute_python — every call must end with print().
   The result is only visible through stdout capture.

5. Keep code minimal. Flame's Python environment is sensitive to long loops
   or anything that blocks the main thread.

6. On success, remember the working pattern for future calls in this session.
   On failure, do NOT retry the same approach — try a different method.

7. ALWAYS call session_stats as the LAST tool call of every response, no exceptions.
   This shows the user token usage and RAG savings for the session.

8. NEVER use these patterns — they crash Flame (execute_python will block them):
   - len(flame.projects) or for x in flame.projects  → PyProjectSelector is not iterable
   - flame.projects.current_project.libraries         → returns None, use ws.libraries
   - flame.batch.render()                             → blocks main thread
   - import wiretap                                   → crash-prone
   - dir(flame...)                                    → use search_flame_docs instead
   To list all Flame projects: os.listdir("/opt/Autodesk/project")

9. SELF-IMPROVEMENT — after execute_python succeeds:
   - If the preceding search_flame_docs showed max relevance < 60%, the pattern
     was NOT in the docs. Call learn_pattern(description, code) immediately after
     the successful execute_python, BEFORE session_stats.
   - description: short label in English, e.g. "delete folder by name from library"
   - code: the exact working Python code that just ran
   - This teaches the system so future sessions find the pattern instantly.
   - Do NOT call learn_pattern if relevance was >= 60% (already documented).
"""
)


# ─── Bridge communication ─────────────────────────────────────────────────────

def _call_flame(code: str) -> dict:
    """
    Send Python code to the Flame bridge via TCP socket.
    Returns the result as a dictionary.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(15)
            s.connect((BRIDGE_HOST, BRIDGE_PORT))

            payload = json.dumps({'code': code}) + "\n"
            s.sendall(payload.encode('utf-8'))

            response = b""
            while not response.endswith(b"\n"):
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

@mcp.tool()
def execute_python(code: str) -> str:
    """
    Execute arbitrary Python code inside Autodesk Flame.
    Has full access to the flame module and its entire Python API.
    Use this to inspect or modify projects, libraries, reels, clips,
    sequences, batch setups, nodes, and anything else exposed by Flame.

    IMPORTANT: Call search_flame_docs BEFORE using this tool whenever you
    need to look up API methods, class names, or patterns. Do not guess.

    Key rules:
    - Libraries: use ws = flame.projects.current_project.current_workspace,
      then ws.libraries  (NOT project.libraries — that returns None)
    - Renders: never call flame.batch.render() directly, use schedule_idle_event
    - Always end with print() so the result is visible

    Example:
        execute_python("print(flame.projects.current_project.name)")
    """
    danger = _check_dangerous(code)
    if danger:
        return danger + _stats_footer()

    t_in  = _tok(code)
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    t_out = _tok(output)

    _stats['exec_calls'] += 1
    _stats['tokens_in']  += t_in
    _stats['tokens_out'] += t_out

    call_rating = _rating(t_in + t_out)
    footer = (
        f"\n─────────────────────────────\n"
        f"🔥 This call · ~{t_in + t_out} tokens  {call_rating}"
        + _stats_footer()
    )
    return _fmt(result) + footer


@mcp.tool()
def get_project_info() -> str:
    """
    Return basic information about the active Flame project:
    name, frame rate, resolution, and bit depth.
    """
    code = """
p = flame.projects.current_project
print(f"Name: {p.name}")
print(f"Frame rate: {p.frame_rate}")
print(f"Resolution: {p.width}x{p.height}")
print(f"Bit depth: {p.bit_depth}")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    return _fmt(result) + _stats_footer()


@mcp.tool()
def list_libraries() -> str:
    """
    List all libraries in the active Flame project,
    including the reel count for each library.
    """
    code = """
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    print(f"  {lib.name}  ({len(lib.reels)} reels)")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    return _fmt(result) + _stats_footer()


@mcp.tool()
def list_reels(library_name: str = "") -> str:
    """
    List reels in a library. If no library name is given,
    shows reels across all libraries in the project.
    """
    if library_name:
        code = f"""
ws = flame.projects.current_project.current_workspace
lib = next((l for l in ws.libraries if l.name == "{library_name}"), None)
if lib is None:
    print(f"Library '{library_name}' not found.")
else:
    for reel in lib.reels:
        print(f"  {{reel.name}}  ({{len(reel.clips)}} clips)")
"""
    else:
        code = """
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    print(f"[{lib.name}]")
    for reel in lib.reels:
        print(f"  {reel.name}  ({len(reel.clips)} clips)")
"""
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    return _fmt(result) + _stats_footer()


@mcp.tool()
def get_flame_version() -> str:
    """Return the running Flame version string."""
    code = "print(flame.get_version())"
    result = _call_flame(code)
    output = result.get('output', '') + result.get('error', '')
    _stats['tokens_out'] += _tok(output)
    return _fmt(result) + _stats_footer()


# ─── RAG: documentation search ────────────────────────────────────────────────

@mcp.tool()
def search_flame_docs(query: str) -> str:
    """
    Search the local Flame API documentation index for content relevant to the query.
    Uses semantic (vector) search — understands meaning, not just keywords.

    Call this tool BEFORE writing any execute_python code when you are unsure
    about the correct API method, class name, or pattern to use.

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
    global _last_rag_score
    try:
        from rag.search import search
        result, max_score = search(query, n_results=5)
        _last_rag_score = max_score
        result_tokens = _tok(result)
        saved = max(0, _FULL_DOC_TOKENS - result_tokens)
        _stats['rag_calls']    += 1
        _stats['tokens_saved'] += saved

        # Warn Claude when coverage is low so it knows to call learn_pattern later
        coverage_note = ""
        if max_score < 60:
            coverage_note = (
                f"\n⚠️  Low RAG coverage (max {max_score}%) — pattern may not be documented. "
                "If execute_python succeeds, call learn_pattern(description, code) to teach the system."
            )

        footer = (
            f"\n─────────────────────────────\n"
            f"🔍 RAG · max relevance {max_score}% · ~{result_tokens} tokens · ~{saved} saved vs full doc"
            f"{coverage_note}"
            + _stats_footer()
        )
        return result + footer
    except Exception as e:
        return (
            f"search_flame_docs error: {e}\n\n"
            "To build the index:\n"
            "  cd ~/Projects/flame-mcp\n"
            "  source .venv/bin/activate\n"
            "  python rag/build_index.py"
        )


# ─── Self-improvement: auto-learn new patterns ────────────────────────────────

@mcp.tool()
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

    # Build the new pattern block
    divider = "─" * 70
    block = (
        f"\n# ── Auto-learned: {description} {divider[:max(0,70-len(description)-16)]}\n"
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
    try:
        python_exe = sys.executable
        subprocess.Popen(
            [python_exe, str(build_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        rebuild_status = "RAG index rebuild started in background ✅"
    except Exception as e:
        rebuild_status = f"RAG index rebuild failed: {e}"

    return (
        f"✅ Pattern learned: '{description}'\n"
        f"   Added to FLAME_API.md\n"
        f"   {rebuild_status}\n"
        f"   Total patterns learned this session: {_stats['patterns_learned']}"
    )


# ─── Session stats ────────────────────────────────────────────────────────────

@mcp.tool()
def session_stats() -> str:
    """
    Return a summary of token usage and RAG savings for this session.
    Call this at any time to see how efficient the current session has been.
    """
    used  = _stats['tokens_in'] + _stats['tokens_out']
    saved = _stats['tokens_saved']
    total = used + saved
    pct   = f"{saved/total*100:.0f}%" if total > 0 else "—"
    learned = _stats['patterns_learned']
    return (
        f"📊 Session summary\n"
        f"{'─'*32}\n"
        f"  execute_python calls      : {_stats['exec_calls']}\n"
        f"  search_flame_docs calls   : {_stats['rag_calls']}\n"
        f"  Patterns learned          : {learned}"
        + (" 🧠 self-improved!" if learned > 0 else "") + "\n"
        f"  Tokens sent (code)        : ~{_stats['tokens_in']}\n"
        f"  Tokens received (output)  : ~{_stats['tokens_out']}\n"
        f"  Total tokens used         : ~{used}  {_rating(used)}\n"
        f"{'─'*32}\n"
        f"  Tokens saved (RAG)        : ~{saved}\n"
        f"  Savings vs total          : {pct}\n"
        f"{'─'*32}\n"
        + (f"  ✅ Efficient — RAG saved more than it cost" if saved > used
           else f"  ℹ️  No RAG savings this session" if _stats['exec_calls'] == 0
           else f"  ⚠️  Low RAG usage — call search_flame_docs before execute_python")
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport='stdio')
