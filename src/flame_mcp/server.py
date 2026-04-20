"""
server.py
=========
MCP server that exposes tools for controlling Autodesk Flame.
Communicates with the Flame hook bridge (flame_mcp_bridge.py) running inside Flame.

Usage:
    python -m flame_mcp.server

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

from flame_mcp.safety import (
    _check_dangerous,
    _DANGEROUS_PATTERNS,
    _REDIRECT_PATTERNS,
    _SOFT_REDIRECT_PATTERNS,
    _CREATION_INTENT_RE,
)
from flame_mcp._session_stats import (
    apply_idle_reset,
    make_empty_stats,
    reset_stats as _reset_stats_helper,
)

_SERVER_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Tool annotations (MCP ≥ 1.x) ────────────────────────────────────────────
try:
    from mcp.types import ToolAnnotations
    _RO  = ToolAnnotations(readOnlyHint=True,  destructiveHint=False, openWorldHint=False)  # read-only local
    _RW  = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)  # write, not destructive
    _DST = ToolAnnotations(readOnlyHint=False, destructiveHint=True,  openWorldHint=False)  # potentially destructive
except ImportError:
    _RO = _RW = _DST = None  # older mcp versions — gracefully ignored by FastMCP

# ─── Model write permissions ──────────────────────────────────────────────────
# Only these model families are trusted to write patterns to FLAME_API.md.
# Lightweight models (Qwen, Llama, etc.) are read-only: they may hallucinate
# API paths that contaminate the knowledge base and cause future failures.

WRITE_ALLOWED_MODELS = {
    # Forward-compatible prefixes — any Opus / Sonnet release satisfies these.
    "claude-opus",
    "claude-sonnet",
    # Explicit current releases (canonical source: ~/Projects/.external_versions.yml).
    "claude-sonnet-4-6",
    "claude-opus-4-7",
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

# Canonical stats dict. Schema lives in flame_mcp._session_stats.make_empty_stats
# so the initialiser and the reset path cannot drift (invariant: stats_keys_schema_shared).
_stats = make_empty_stats()
# Records when _stats was last reset (server start, idle-gap auto-reset, or explicit reset).
_stats_reset_at = datetime.datetime.now()
# Timestamp of the previous MCP tool call — drives the idle-gap auto-reset.
_last_call_at: datetime.datetime | None = None
# Idle window (seconds) after which _stats is auto-zeroed on the next call.
# Overridable via config.json -> stats_idle_reset_seconds (default 30 min).
_STATS_IDLE_RESET_SECONDS = int(
    _get_config().get("stats_idle_reset_seconds", 30 * 60)
)

# C5 — Staging paths
_CANDIDATES_PATH = _SERVER_DIR / "src" / "flame_mcp" / "rag" / "candidates.json"
_FAILED_PATH     = _SERVER_DIR / "src" / "flame_mcp" / "rag" / "failed.json"


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
    """Return an emoji rating based on token count for a single call.

    Suppressed for local/free backends (ollama, ollama_mac, ollama_cloud):
    there are no rate limits or per-token costs to warn about, so showing
    🟡 / 🔴 is noise. The README documents this behaviour in the
    "Token cost warnings" section.
    """
    backend = _get_config().get("backend", "anthropic")
    if backend.startswith("ollama"):
        return ""
    if tokens < 500:
        return "🟢 low"
    elif tokens < 2000:
        return "🟡 medium"
    else:
        return "🔴 high"


def _track_call() -> None:
    """Update last-call timestamp; auto-reset _stats if idle gap exceeded.

    Must be called at the top of every MCP tool entry point that touches
    _stats. Idle threshold is _STATS_IDLE_RESET_SECONDS (default 30 min).
    """
    global _last_call_at, _stats_reset_at
    now = datetime.datetime.now()
    did_reset, reset_at = apply_idle_reset(
        _stats, now, _last_call_at,
        idle_reset_seconds=_STATS_IDLE_RESET_SECONDS,
    )
    if did_reset:
        _stats_reset_at = reset_at
    _last_call_at = now


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
# Socket discovery: env var -> repo run/ -> /tmp/ (installed hook) -> TCP fallback
_BRIDGE_SOCKET = Path(os.environ.get(
    'FLAME_BRIDGE_SOCKET',
    str(_SERVER_DIR / 'run' / 'flame_mcp.sock')
    if (_SERVER_DIR / 'run' / 'flame_mcp.sock').exists()
    else '/tmp/flame_mcp.sock'
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


# ─── Stone+Wire project database (Flame 2026+) ───────────────────────────────

_SW_LIST_PROJECTS = '/opt/Autodesk/sw/tools/sw_listProjects'

def _sw_list_projects() -> list:
    """
    Run sw_listProjects and return parsed project list from the Stone+Wire DB.
    Authoritative source in Flame 2026+: includes projects on all volumes.
    Runs as the current user — no sudo needed.

    Each entry: {'uuid': str, 'name': str, 'path': str, 'modified': str}
    Returns [] on any failure (binary missing, S+W service down, etc.).

    Output line format (one project per line, amid noise):
      UUID: name, /path/to/project, 1, YYYY-MM-DD HH:MM:SS.ffffff+TZ
    """
    try:
        proc = subprocess.run(
            [_SW_LIST_PROJECTS],
            capture_output=True, text=True, timeout=10
        )
        _pat = re.compile(
            r'^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
            r':\s+(.+?),\s+(/\S+?),\s+\d+,\s+(.+)$'
        )
        projects = []
        for line in proc.stdout.splitlines():
            m = _pat.match(line.strip())
            if m:
                projects.append({
                    'uuid':     m.group(1),
                    'name':     m.group(2).strip(),
                    'path':     m.group(3).strip(),
                    'modified': m.group(4).strip(),
                })
        return projects
    except Exception:
        return []


def _sysconfig_project_path(project_name: str) -> 'str | None':
    """
    Compute project home path from sysconfig.cfg when sw_listProjects is unavailable.

    sysconfig.cfg lives in /opt/Autodesk/cfg/.<version>/sysconfig.cfg.
    The default_home key defines the project root template; Flame tokens
    (<project name>, <project>, <host name>, <hostname>, <host>, <workstation>)
    are expanded at project-creation time.

    Returns the resolved path string, or None if sysconfig.cfg cannot be read
    or the template contains unresolvable tokens.
    """
    import glob as _glob
    try:
        candidates = sorted(_glob.glob('/opt/Autodesk/cfg/.*/sysconfig.cfg'))
        if not candidates:
            return None
        # Use the most recently modified sysconfig.cfg (latest installed version)
        cfg_file = max(candidates, key=os.path.getmtime)
        with open(cfg_file) as _f:
            content = _f.read()
        # Parse: "default_home = /some/path/<project name>" (= optional, may use spaces)
        m = re.search(
            r'^\s*default_home\s*[=\s]\s*(.+)$',
            content, re.MULTILINE | re.IGNORECASE
        )
        if not m:
            return None
        template = m.group(1).strip().strip('"').strip("'")
        # Expand project name tokens
        for tok in ('<project name>', '<project>'):
            template = template.replace(tok, project_name)
        # Expand hostname tokens
        try:
            _hn = subprocess.run(['hostname', '-s'], capture_output=True, text=True,
                                 timeout=3).stdout.strip()
        except Exception:
            _hn = ''
        if _hn:
            for tok in ('<host name>', '<hostname>', '<host>', '<workstation>'):
                template = template.replace(tok, _hn)
        # If unexpanded tokens remain, the template is unresolvable
        if '<' in template:
            return None
        return template.rstrip('/')
    except Exception:
        return None


# ─── Bridge communication ─────────────────────────────────────────────────────

def _call_flame(code: str, timeout: int = 15, dedicated_tool: bool = True) -> dict:
    """
    Send Python code to the Flame bridge.
    A13 — Prefers Unix domain socket (owner-only, no network exposure);
    falls back to TCP if the socket file does not exist.
    Returns the result as a dictionary.

    dedicated_tool=True (default): marks the payload as coming from a dedicated MCP
      tool (list_libraries, get_project_info, etc.). The bridge skips redirect check.
    dedicated_tool=False: used by execute_python — bridge enforces redirect patterns
      as a second layer of defence even if the server-side check was bypassed.

    REC-001: Returns '_bridge_ms' key with bridge roundtrip time in milliseconds.
    """
    _track_call()
    _t0_bridge = time.monotonic()
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

            # Dedicated tools prepend '# DT\n' so the bridge skips redirect check.
            # execute_python passes dedicated_tool=False → no prefix → bridge enforces.
            marked_code = ('# DT\n' + code) if dedicated_tool else code
            payload = json.dumps({'code': marked_code}) + "\n"
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

            result = json.loads(response.decode('utf-8').strip())
            result['_bridge_ms'] = round((time.monotonic() - _t0_bridge) * 1000)
            return result

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
    dry_run: Annotated[bool, Field(description="If true, return what WOULD happen without executing. Shows safety checks, redirect matches, and RAG status.")] = False,
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
        dry_run: If true, show what would happen without executing the code.
                 Returns safety check results, redirect matches, and RAG status.

    Example:
        execute_python("print(flame.projects.current_project.name)")
        execute_python(long_import_code, timeout=60)
        execute_python(risky_code, dry_run=True)  # preview without executing
    """
    danger = _check_dangerous(code)
    if danger:
        return danger + _stats_footer()

    # (redirect patterns are defined at module level as _REDIRECT_PATTERNS)
    import re as _re
    import sys as _sys2
    _has_creation = bool(_CREATION_INTENT_RE.search(code))
    print(
        f"[flame-mcp] execute_python called — "
        f"redirect_check=active  patterns={len(_REDIRECT_PATTERNS)}  "
        f"rag_called={_rag_called_this_session}  creation_intent={_has_creation}"
        f"  dry_run={dry_run}",
        file=_sys2.stderr, flush=True
    )

    # Collect redirect matches for dry_run report
    redirect_match = None
    for _pattern, _msg in _REDIRECT_PATTERNS:
        if _re.search(_pattern, code):
            if _has_creation and _pattern in _SOFT_REDIRECT_PATTERNS:
                print(
                    f"[flame-mcp] REDIRECT suppressed (creation intent): {_pattern}",
                    file=_sys2.stderr, flush=True
                )
                continue
            print(f"[flame-mcp] REDIRECT matched pattern: {_pattern}", file=_sys2.stderr, flush=True)
            redirect_match = (
                f"🚫 REDIRECT — a dedicated tool handles this query:\n"
                f"   {_msg}\n"
                f"   Call the dedicated tool instead of execute_python."
            )
            if not dry_run:
                return redirect_match
            break  # capture for dry_run report but continue

    # ── Architecture 3.4: Hard RAG-before-exec gate ──────────────────────────
    # Block execute_python entirely if search_flame_docs has not been called
    # this session.  The previous "nudge" was a soft reminder that models
    # routinely ignored, leading to hallucinated API calls.
    rag_gate_blocked = False
    if not _rag_called_this_session:
        rag_gate_blocked = True
        rag_gate_msg = (
            "🚫 RAG GATE — You must call search_flame_docs before execute_python.\n"
            "   This is a hard requirement, not a suggestion. Flame's Python API has\n"
            "   many traps (flame.selection doesn't exist, project.libraries returns\n"
            "   None, flame.batch.render() crashes Flame). search_flame_docs returns\n"
            "   the correct patterns in ~200 tokens.\n"
            "   Also check if a dedicated tool already answers this question."
        )
        if not dry_run:
            return rag_gate_msg + _stats_footer()

    # ── Architecture 3.3: dry_run mode ───────────────────────────────────────
    if dry_run:
        lines = ["── DRY RUN — execute_python preview ──\n"]
        lines.append(f"Code ({len(code)} chars, ~{_tok(code)} tokens):")
        lines.append(f"  {code[:200]}{'...' if len(code) > 200 else ''}\n")
        lines.append(f"Timeout: {timeout}s")
        lines.append(f"RAG called this session: {_rag_called_this_session}")
        lines.append(f"Last RAG score: {_last_rag_score}/100")
        lines.append(f"Model: {_get_current_model()}")
        lines.append(f"Model can write: {_model_can_write()}")
        if danger:
            lines.append(f"\n⛔ SAFETY BLOCK: {danger}")
        if redirect_match:
            lines.append(f"\n{redirect_match}")
        if rag_gate_blocked:
            lines.append(f"\n{rag_gate_msg}")
        if not danger and not redirect_match and not rag_gate_blocked:
            lines.append("\n✅ All checks pass — code would execute.")
        else:
            lines.append("\n❌ Code would NOT execute due to above blocks.")
        return '\n'.join(lines)

    # OBS-013: soft nudge (post-gate, only fires after RAG was called but
    # score was low — the hard gate above catches the no-RAG case)
    rag_nudge = ""

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
    _t0_exec = time.monotonic()
    # dedicated_tool=False: execute_python is user-facing code. The bridge checks
    # redirect patterns as a second enforcement layer regardless of server-side checks.
    result = _call_flame(code, timeout=timeout, dedicated_tool=False)
    output = result.get('output', '') + result.get('error', '')
    t_out = _tok(output)

    # REC-001: collect timing data
    _bridge_ms = result.get('_bridge_ms', 0)
    _total_ms  = round((time.monotonic() - _t0_exec) * 1000)
    _track_timing({'op': 'exec', 'bridge_ms': _bridge_ms, 'total_ms': _total_ms})

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
        f" · bridge {_bridge_ms}ms · total {_total_ms}ms"
        + _stats_footer()
    )
    return rag_nudge + b4_warning + _fmt(result) + footer


def _track_dedicated() -> None:
    """Increment dedicated tool counter and accumulate estimated savings."""
    _stats['dedicated_calls']    += 1
    _stats['tokens_saved_tools'] += _DEDICATED_TOOL_SAVINGS


def _track_timing(entry: dict) -> None:
    """REC-001: append timing entry to ring buffer (max 20 entries)."""
    _stats['timings'].append(entry)
    if len(_stats['timings']) > 20:
        _stats['timings'].pop(0)


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
    # OBS-028 fallback: if IFFFS is unreachable, read the project .cfg file directly.
    import re as _re

    def _cfg_fallback(project_name: str) -> list:
        """Read frame rate / resolution / colour space from the project .cfg file.

        Three-level path resolution (project paths are site-configurable via
        sysconfig.cfg — never assume /var/opt/Autodesk/flame/projects/):

          1. sw_listProjects  — Stone+Wire DB: real path, all volumes (Flame 2026+)
          2. sysconfig.cfg    — expand default_home template (S+W down, any version)
          3. /var/opt/...     — last resort for vanilla default-install Flame

        {project_home}/setups is always a Flame-managed symlink to the actual
        setups dir, so the path {home}/setups/cfg/{name}.cfg is always correct
        regardless of where default_setups_dir resolves to.
        """
        # Level 1: Stone+Wire DB
        project_path = None
        for p in _sw_list_projects():
            if p['name'] == project_name:
                project_path = p['path']
                break
        # Level 2: sysconfig.cfg template expansion
        if project_path is None:
            project_path = _sysconfig_project_path(project_name)
        # Level 3: vanilla default path
        if project_path is None:
            project_path = f"/var/opt/Autodesk/flame/projects/{project_name}"
        cfg_path = f"{project_path}/setups/cfg/{project_name}.cfg"
        try:
            with open(cfg_path) as _f:
                cfg = _f.read()
        except Exception:
            return ["Frame rate: — (IFFFS unreachable, .cfg not found)"]
        def _cfg(key):
            m = _re.search(rf"^{key}\s+(.+)$", cfg, _re.MULTILINE | _re.IGNORECASE)
            return m.group(1).strip() if m else "—"
        fps    = _cfg("Framerate")
        colour = _cfg("ColourSpace")
        # VideoPreviewWindow = "1920, 1080, 23976p"
        vp     = _cfg("VideoPreviewWindow")
        res    = "—"
        if vp and vp != "—":
            parts = [p.strip() for p in vp.split(",")]
            if len(parts) >= 2:
                res = f"{parts[0]}x{parts[1]}"
        return [
            f"Frame rate: {fps}  (source: .cfg)",
            f"Resolution: {res}  (source: .cfg)",
            f"Bit depth: —  (not in .cfg)",
            f"Colour space: {colour}  (source: .cfg)",
        ]

    meta_lines = []
    project_name_for_cfg = ""
    for line in py_out.splitlines():
        if line.startswith("Name:"):
            project_name_for_cfg = line.split(":", 1)[1].strip()

    if wtap_id:
        try:
            proc = subprocess.run(
                [f"{WTAP}/wiretap_get_metadata", "-h", "localhost:IFFFS",
                 "-n", wtap_id, "-s", "XML"],
                capture_output=True, text=True, timeout=10
            )
            xml = proc.stdout
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
            # If IFFFS returned all dashes, fall back to .cfg
            if all(v.endswith("—") for v in meta_lines):
                meta_lines = _cfg_fallback(project_name_for_cfg)
        except Exception:
            meta_lines = _cfg_fallback(project_name_for_cfg)
    else:
        meta_lines = _cfg_fallback(project_name_for_cfg)

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
    Shows which project is currently active, its path, and last modified date.

    In Flame 2026+ uses sw_listProjects (Stone+Wire DB) — authoritative source
    that includes projects on all volumes (internal and external mounts).
    Falls back to scanning /opt/Autodesk/project for older Flame versions.
    """
    # Primary: Stone+Wire database (Flame 2026+)
    sw_projects = _sw_list_projects()
    if sw_projects:
        current_result = _call_flame(
            "print(str(flame.projects.current_project.name))"
        )
        current = current_result.get('output', '').strip()
        lines = [
            f"Active project: {current}",
            f"All projects ({len(sw_projects)}) — sorted by last modified:",
        ]
        for p in sw_projects:
            marker = "  ◀ active" if p['name'] == current else ""
            date   = p['modified'][:10]
            lines.append(f"  {p['name']:<30}  {p['path']}  [{date}]{marker}")
        _stats['tokens_out'] += _tok('\n'.join(lines))
        _track_dedicated()
        return '\n'.join(lines)

    # Fallback: scan /opt/Autodesk/project (Flame < 2026)
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
    _track_call()
    try:
        from flame_mcp.rag.search import search

        # A12 — Return cached result for identical queries within this session
        cache_key = hash(query)
        if cache_key in _search_cache:
            cached_result, cached_score = _search_cache[cache_key]
            _last_rag_score = cached_score
            _stats['rag_calls'] += 1   # OBS-009: count cache hits too
            _rag_called_this_session = True
            return cached_result + "\n📎 (cached result — same query this session)"

        _t0_rag = time.monotonic()
        result, max_score = search(query, n_results=5)
        _rag_ms = round((time.monotonic() - _t0_rag) * 1000)
        _last_rag_score = max_score
        result_tokens = _tok(result)
        saved = max(0, _FULL_DOC_TOKENS - result_tokens)
        _stats['rag_calls']    += 1
        _stats['tokens_saved'] += saved
        _rag_called_this_session = True
        _track_timing({'op': 'rag', 'rag_ms': _rag_ms, 'score': max_score})

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
            f" · {_rag_ms}ms"
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
            "  cd <flame-mcp repo root>\n"
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
    build_script = _SERVER_DIR / "src" / "flame_mcp" / "rag" / "build_index.py"

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
    _lock_file = _SERVER_DIR / "src" / "flame_mcp" / "rag" / ".rebuilding"
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
        + _timings_summary()
    )


@mcp.tool(annotations=_RO)
def reset_session_stats() -> str:
    """
    Zero the session stats counters immediately.

    Use at the start of a new Claude session (or a fresh debugging run) when
    the idle-based auto-reset has not fired — for example when two sessions
    happen back-to-back. Returns a confirmation line with the new reset
    timestamp.
    """
    global _stats_reset_at
    now = datetime.datetime.now()
    _stats_reset_at = _reset_stats_helper(_stats, now)
    return f"📊 Session stats reset at {now.strftime('%H:%M:%S')}"


def _timings_summary() -> str:
    """REC-001: format last 10 call timings for get_session_stats output."""
    entries = _stats['timings']
    if not entries:
        return ""
    lines = [f"\n{'─'*32}\n⏱  Recent call timings (last {len(entries)})"]
    for e in entries[-10:]:
        op = e.get('op', '?')
        if op == 'exec':
            lines.append(f"   exec     bridge={e.get('bridge_ms', '?')}ms  total={e.get('total_ms', '?')}ms")
        elif op == 'rag':
            lines.append(f"   rag      search={e.get('rag_ms', '?')}ms  score={e.get('score', '?')}%")
        else:
            lines.append(f"   {op}  {e}")
    return "\n".join(lines)


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


# ─── Architecture 3.1: resolve_concept ────────────────────────────────────────

@mcp.tool(annotations=_RO)
def resolve_concept(query: str) -> str:
    """
    Fast static lookup: map a user concept to the correct API path and tool.

    Use this BEFORE search_flame_docs when you have a clear operation in mind
    (e.g., "list libraries", "get clip metadata", "render batch").  Returns
    the recommended tool, API layer, code pattern, and gotchas — no RAG search
    needed, no tokens spent.

    Returns None-match if the concept is not in the map; fall back to
    search_flame_docs in that case.

    Args:
        query: Natural-language description of the operation, e.g.
               "list all libraries", "delete a clip", "browse wiretap tree"
    """
    from flame_mcp.concept_map import resolve_concept as _resolve, CRITICAL_BEHAVIORS
    _track_dedicated()
    match = _resolve(query)
    if match is None:
        return (
            f"No concept match for: {query!r}\n"
            f"Fall back to search_flame_docs('{query}') for RAG-based search."
        )
    lines = [
        f"✅ Concept: {match['concept']}",
        f"   API layer : {match['api_layer']}",
    ]
    if match.get('entity_type'):
        lines.append(f"   Entity    : {match['entity_type']}")
    lines.extend([
        f"   Tool      : {match['tool']}",
        f"   API path  : {match['api_path']}",
    ])
    if match.get('notes'):
        lines.append(f"   Notes     : {match['notes']}")

    # Surface critical API behaviors relevant to this entity type
    entity_type = match.get('entity_type')
    if entity_type:
        relevant = [b for b in CRITICAL_BEHAVIORS if entity_type in b['applies_to']]
        if relevant:
            lines.append("\n⚠️  Critical API behaviors:")
            for b in relevant:
                lines.append(f"   - {b['summary']}")
                lines.append(f"     Example: {b['example']}")

    return '\n'.join(lines)


# ─── Architecture 3.5: dedicated tools for common multi-step operations ──────

@mcp.tool(annotations=_RO)
def get_source_path(
    library_name: str,
    reel_name: str = "",
    clip_name: str = "",
) -> str:
    """
    Get the filesystem source path of a clip, reel, or library.

    Returns the on-disk path (from Wiretap node or clip metadata) without
    requiring execute_python.  Useful for publish workflows, media collection,
    and path validation.

    Args:
        library_name: Name of the library.
        reel_name:    Name of the reel (optional — returns library path if omitted).
        clip_name:    Name of the clip (optional — returns reel path if omitted).
    """
    _track_dedicated()
    # Build the inspection code targeting the deepest specified level
    if clip_name and reel_name:
        code = (
            f"import flame\n"
            f"ws = flame.projects.current_project.current_workspace\n"
            f"lib = next((l for l in ws.libraries if str(l.name) == {library_name!r}), None)\n"
            f"if not lib: print('ERROR: library not found: {library_name}')\n"
            f"else:\n"
            f"  reel = next((r for r in lib.reels if str(r.name) == {reel_name!r}), None)\n"
            f"  if not reel: print('ERROR: reel not found: {reel_name}')\n"
            f"  else:\n"
            f"    clip = next((c for c in reel.clips if str(c.name) == {clip_name!r}), None)\n"
            f"    if not clip: print('ERROR: clip not found: {clip_name}')\n"
            f"    else:\n"
            f"      versions = clip.versions\n"
            f"      if versions:\n"
            f"        v = versions[0]\n"
            f"        tracks = v.tracks\n"
            f"        if tracks:\n"
            f"          segs = tracks[0].segments\n"
            f"          if segs: print(str(segs[0].file_path))\n"
            f"          else: print('(no segments)')\n"
            f"        else: print('(no tracks)')\n"
            f"      else: print('(no versions)')\n"
        )
    elif reel_name:
        code = (
            f"import flame\n"
            f"ws = flame.projects.current_project.current_workspace\n"
            f"lib = next((l for l in ws.libraries if str(l.name) == {library_name!r}), None)\n"
            f"if not lib: print('ERROR: library not found: {library_name}')\n"
            f"else:\n"
            f"  reel = next((r for r in lib.reels if str(r.name) == {reel_name!r}), None)\n"
            f"  if not reel: print('ERROR: reel not found: {reel_name}')\n"
            f"  else: print('Reel: ' + str(reel.name) + ' — clips: ' + str(len(reel.clips)))\n"
        )
    else:
        code = (
            f"import flame\n"
            f"ws = flame.projects.current_project.current_workspace\n"
            f"lib = next((l for l in ws.libraries if str(l.name) == {library_name!r}), None)\n"
            f"if not lib: print('ERROR: library not found: {library_name}')\n"
            f"else: print('Library: ' + str(lib.name) + ' — reels: ' + str(len(lib.reels)))\n"
        )
    result = _call_flame(code, timeout=15, dedicated_tool=True)
    return _fmt(result)


@mcp.tool(annotations=_DST)
def rename_segments(
    library_name: str,
    reel_name: str,
    clip_name: str,
    new_name: str,
) -> str:
    """
    Rename a clip (all its segments) in a Flame library/reel.

    This is a destructive operation — the clip name changes in-place.

    Args:
        library_name: Library containing the clip.
        reel_name:    Reel containing the clip.
        clip_name:    Current clip name.
        new_name:     New name to assign.
    """
    _track_dedicated()
    code = (
        f"import flame\n"
        f"ws = flame.projects.current_project.current_workspace\n"
        f"lib = next((l for l in ws.libraries if str(l.name) == {library_name!r}), None)\n"
        f"if not lib: print('ERROR: library not found')\n"
        f"else:\n"
        f"  reel = next((r for r in lib.reels if str(r.name) == {reel_name!r}), None)\n"
        f"  if not reel: print('ERROR: reel not found')\n"
        f"  else:\n"
        f"    clip = next((c for c in reel.clips if str(c.name) == {clip_name!r}), None)\n"
        f"    if not clip: print('ERROR: clip not found: {clip_name}')\n"
        f"    else:\n"
        f"      clip.name = {new_name!r}\n"
        f"      print('Renamed: {clip_name} → {new_name}')\n"
    )
    result = _call_flame(code, timeout=15, dedicated_tool=True)
    return _fmt(result)


@mcp.tool(annotations=_DST)
def create_sequence(
    library_name: str,
    reel_name: str,
    sequence_name: str,
) -> str:
    """
    Create a new empty sequence in a Flame library/reel.

    Args:
        library_name: Target library.
        reel_name:    Target reel within the library.
        sequence_name: Name for the new sequence.
    """
    _track_dedicated()
    code = (
        f"import flame\n"
        f"ws = flame.projects.current_project.current_workspace\n"
        f"lib = next((l for l in ws.libraries if str(l.name) == {library_name!r}), None)\n"
        f"if not lib: print('ERROR: library not found')\n"
        f"else:\n"
        f"  reel = next((r for r in lib.reels if str(r.name) == {reel_name!r}), None)\n"
        f"  if not reel: print('ERROR: reel not found')\n"
        f"  else:\n"
        f"    seq = flame.media_panel.create_sequence(name={sequence_name!r})\n"
        f"    print('Created sequence: ' + str(seq.name))\n"
    )
    result = _call_flame(code, timeout=15, dedicated_tool=True)
    return _fmt(result)


@mcp.tool(annotations=_RO)
def get_write_node_settings() -> str:
    """
    Get the Write File node settings from the current Batch setup.

    Returns render resolution, file format, codec, destination path,
    and frame range. Useful before rendering to verify output settings.
    """
    _track_dedicated()
    code = (
        "import flame\n"
        "nodes = [n for n in flame.batch.nodes if n.type == 'Write File']\n"
        "if not nodes: print('No Write File nodes in current Batch')\n"
        "else:\n"
        "  for wf in nodes:\n"
        "    print(f'Write File: {wf.name}')\n"
        "    try: print(f'  Format: {wf.format}')\n"
        "    except: pass\n"
        "    try: print(f'  Destination: {wf.destination}')\n"
        "    except: pass\n"
        "    try: print(f'  Range: {wf.range_start} - {wf.range_end}')\n"
        "    except: pass\n"
    )
    result = _call_flame(code, timeout=15, dedicated_tool=True)
    return _fmt(result)


@mcp.tool(annotations=_RO)
def collect_media_paths(
    library_name: str,
    reel_name: str = "",
) -> str:
    """
    Collect filesystem paths for all clips in a library or reel.

    Returns a list of source file paths, useful for media management,
    archival, and external processing workflows.

    Args:
        library_name: Library to scan.
        reel_name:    Optional reel filter. If omitted, scans all reels.
    """
    _track_dedicated()
    reel_filter = f"if str(r.name) == {reel_name!r}" if reel_name else ""
    code = (
        f"import flame\n"
        f"ws = flame.projects.current_project.current_workspace\n"
        f"lib = next((l for l in ws.libraries if str(l.name) == {library_name!r}), None)\n"
        f"if not lib: print('ERROR: library not found')\n"
        f"else:\n"
        f"  paths = []\n"
        f"  for r in lib.reels:\n"
        f"    {reel_filter}\n" if reel_name else ""
        f"    for c in r.clips:\n"
        f"      try:\n"
        f"        v = c.versions[0]\n"
        f"        t = v.tracks[0]\n"
        f"        s = t.segments[0]\n"
        f"        paths.append(str(c.name) + ': ' + str(s.file_path))\n"
        f"      except: paths.append(str(c.name) + ': (no path)')\n"
        f"  print(chr(10).join(paths) if paths else '(no clips found)')\n"
    )
    result = _call_flame(code, timeout=30, dedicated_tool=True)
    return _fmt(result)


# ─── Architecture 3.6: operation journaling + undo ────────────��──────────────

# Singleton journal instance — lives for the server process lifetime
from flame_mcp.journal import Journal as _Journal, UndoCodeGenerator as _UndoGen
_journal = _Journal()


@mcp.tool(annotations=_RO)
def operation_history(
    count: Annotated[int, Field(ge=1, le=50, description="Number of recent operations to show")] = 10,
) -> str:
    """
    Show the last N execute_python operations recorded this session.

    Each entry shows: timestamp, operation ID, code snippet, result summary,
    and whether the operation is undoable.

    Args:
        count: Number of operations to show (default 10, max 50).
    """
    _track_dedicated()
    if len(_journal) == 0:
        return "No operations recorded this session."
    return _journal.history(count)


@mcp.tool(annotations=_DST)
def undo_last_operation() -> str:
    """
    Undo the last undoable execute_python operation.

    Only works for operations that have auto-generated undo code (create,
    rename, move). Delete operations are NOT undoable.

    Returns the undo code that will be executed and its result.
    """
    undo_code = _journal.get_undo_code()
    if undo_code is None:
        last = _journal.last_operation()
        if last is None:
            return "❌ No operations to undo — journal is empty."
        return (
            f"❌ Last operation is not undoable.\n"
            f"   Operation: {last['code'][:100]}...\n"
            f"   Reason: no auto-generated undo code for this pattern."
        )

    result = _call_flame(undo_code, timeout=15, dedicated_tool=True)
    output = _fmt(result)
    _journal.record(f"[UNDO] {undo_code}", output)
    return f"↩️  Undo executed:\n   Code: {undo_code[:200]}\n   Result: {output}"


# ─── Startup: auto-sync tool permissions ─────────────────────────────────────

def _sync_tool_permissions() -> None:
    """
    On every server start, ensure all @mcp.tool functions are listed in
    .claude/settings.local.json.  This prevents OBS-006 from recurring:
    any new tool added to src/flame_mcp/server.py is auto-approved the next
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
