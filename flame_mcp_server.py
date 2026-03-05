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
import sys
from mcp.server.fastmcp import FastMCP

# Make rag/ importable when running from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Token tracking ───────────────────────────────────────────────────────────

# Full FLAME_API.md size in tokens (measured once, used as baseline for savings)
_FULL_DOC_TOKENS = 1500

_stats = {
    'exec_calls':   0,
    'tokens_in':    0,   # tokens sent to Flame (code)
    'tokens_out':   0,   # tokens received from Flame (output)
    'rag_calls':    0,
    'tokens_saved': 0,   # tokens saved by RAG vs loading full doc
}


def _tok(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


def _rating(tokens: int) -> str:
    """Return an emoji rating based on token count for a single call."""
    if tokens < 100:
        return "🟢 bajo"
    elif tokens < 400:
        return "🟡 medio"
    else:
        return "🔴 alto"


def _stats_footer() -> str:
    """Return a compact session stats summary."""
    used   = _stats['tokens_in'] + _stats['tokens_out']
    saved  = _stats['tokens_saved']
    ratio  = f"{saved/(used+saved)*100:.0f}%" if (used + saved) > 0 else "—"
    return (
        f"\n─────────────────────────────\n"
        f"📊 Sesión · {_stats['exec_calls']} exec · {_stats['rag_calls']} RAG\n"
        f"   Tokens usados  : ~{used}  {_rating(used)}\n"
        f"   Tokens ahorrados (RAG): ~{saved}  ({ratio} del total)"
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
        f"🔥 Esta llamada · ~{t_in + t_out} tokens  {call_rating}"
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
    return _fmt(_call_flame(code))


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
    return _fmt(_call_flame(code))


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
    return _fmt(_call_flame(code))


@mcp.tool()
def get_flame_version() -> str:
    """Return the running Flame version string."""
    code = "print(flame.get_version())"
    return _fmt(_call_flame(code))


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
    try:
        from rag.search import search
        result = search(query, n_results=3)
        result_tokens = _tok(result)
        saved = max(0, _FULL_DOC_TOKENS - result_tokens)
        _stats['rag_calls']    += 1
        _stats['tokens_saved'] += saved
        footer = (
            f"\n─────────────────────────────\n"
            f"🔍 RAG · ~{result_tokens} tokens devueltos · ~{saved} ahorrados vs doc completo"
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
    return (
        f"📊 Resumen de sesión\n"
        f"{'─'*32}\n"
        f"  Llamadas execute_python : {_stats['exec_calls']}\n"
        f"  Llamadas search_flame_docs: {_stats['rag_calls']}\n"
        f"  Tokens enviados (código)  : ~{_stats['tokens_in']}\n"
        f"  Tokens recibidos (output) : ~{_stats['tokens_out']}\n"
        f"  Total tokens usados       : ~{used}  {_rating(used)}\n"
        f"{'─'*32}\n"
        f"  Tokens ahorrados (RAG)    : ~{saved}\n"
        f"  Ahorro sobre total        : {pct}\n"
        f"{'─'*32}\n"
        f"  {'✅ Eficiente' if saved > used else '⚠️  Considera usar más el RAG'}"
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport='stdio')
