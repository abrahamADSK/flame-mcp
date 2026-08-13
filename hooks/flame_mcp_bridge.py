"""
flame_mcp_bridge.py
===================
Python hook for Autodesk Flame that opens a TCP socket server.
Allows executing Python code inside Flame from the outside (via MCP server
or directly from the Quick Console dialog).

Installation:
    sudo cp flame_mcp_bridge.py /opt/Autodesk/shared/python/

Restart Flame after installing. The bridge activates automatically on startup.

Default port: 4444 (localhost only)

Flame menu  (MCP Bridge in main menu bar):
    Status indicator  — shows Active / Inactive
    Start / Stop / Restart bridge
    Quick Console     — run Python directly inside Flame
    Connection test   — verify the bridge is reachable
"""

import os
import threading
import socket
import json
import traceback
import sys
import io
import time
import subprocess
import datetime

# ── Shared helper import bootstrap ────────────────────────────────────────────
# The bridge runs inside Flame's embedded Python (installed at
# /opt/Autodesk/shared/python/flame_mcp_bridge.py) where the `flame_mcp`
# package is NOT on sys.path by default. Inject `<project_root>/src` onto
# sys.path so we can import shared helpers that live in the package.
# _PROJECT_ROOT is resolved further down, but we already know how to derive
# it from this file's location (see the dynamic project root detection block
# below for the authoritative logic — this mini-bootstrap just mirrors it).
# realpath (NOT abspath) is required here: the dev-mode install symlinks this
# file from /opt/Autodesk/shared/python/, and abspath keeps the symlink path,
# so the repo src/ is never found and the flame_mcp.* imports silently degrade
# to the fail-soft stubs (losing MCP scoping, usage logging and suggestion
# capture). The dynamic block below intentionally keeps abspath so installed-
# mode runtime paths (bridge socket, config.json) stay where they are today.
_BOOT_THIS_FILE = os.path.realpath(__file__)
_BOOT_HOOKS_DIR = os.path.dirname(_BOOT_THIS_FILE)
_BOOT_AUTO_ROOT = os.path.dirname(_BOOT_HOOKS_DIR)
if (os.path.basename(_BOOT_HOOKS_DIR) == 'hooks' and
        os.path.isfile(os.path.join(_BOOT_AUTO_ROOT, 'src', 'flame_mcp', 'server.py'))):
    _BOOT_PROJECT_ROOT = _BOOT_AUTO_ROOT
else:
    _BOOT_PROJECT_ROOT = os.environ.get(
        'FLAME_MCP_ROOT',
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    )
_BOOT_SRC = os.path.join(_BOOT_PROJECT_ROOT, 'src')
if os.path.isdir(_BOOT_SRC) and _BOOT_SRC not in sys.path:
    sys.path.insert(0, _BOOT_SRC)

try:
    from flame_mcp._config import (
        load_model_config as _shared_load_model_config,
        resolve_keep_alive as _shared_resolve_keep_alive,
    )
except Exception:
    # Fail-soft: if the helper cannot be imported (e.g. Flame host running
    # without the repo on disk), fall back to the inline legacy implementation
    # below. The bridge must never crash on import; losing the helper only
    # means losing the dedup, not the functionality.
    _shared_load_model_config = None
    _shared_resolve_keep_alive = None

try:
    from flame_mcp._readonly import (
        DISALLOWED_TOOLS,
        build_scoped_mcp_config,
        capture_suggestions,
        log_usage,
    )
except Exception:
    # Fail-soft, but the deny-list is a SECURITY property: keep it hardcoded so
    # the read-only lockdown holds even if the package import fails. Capture +
    # MCP scoping + usage logging degrade to no-ops (subprocess then uses default
    # discovery).
    DISALLOWED_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"]

    def capture_suggestions(text, dest):
        return text, 0

    def build_scoped_mcp_config(mcp_json_path, keep_servers):
        return None

    def log_usage(usage, console, dest=None):
        pass

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = int(os.environ.get('FLAME_BRIDGE_PORT', 4444))  # A8: override via env

# ── Dynamic project root detection ────────────────────────────────────────────
# Note: _BRIDGE_SOCKET_PATH is set after _PROJECT_ROOT is known (see below)
# When the bridge is in hooks/ (development), derive root from __file__.
# When installed to /opt/Autodesk/shared/python/, set FLAME_MCP_ROOT in the env.
_THIS_FILE    = os.path.abspath(__file__)
_HOOKS_DIR    = os.path.dirname(_THIS_FILE)
_AUTO_ROOT    = os.path.dirname(_HOOKS_DIR)
if (os.path.basename(_HOOKS_DIR) == 'hooks' and
        os.path.isfile(os.path.join(_AUTO_ROOT, 'src', 'flame_mcp', 'server.py'))):
    _PROJECT_ROOT = _AUTO_ROOT
else:
    _PROJECT_ROOT = os.environ.get('FLAME_MCP_ROOT',
                                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A13 — Unix domain socket path (derived from project root; no new deps required)
# Installed hook (/opt/Autodesk/shared/python/) -> /tmp/flame_mcp.sock
# Development (hooks/ inside repo) -> <repo>/run/flame_mcp.sock
_DEFAULT_SOCK = (os.path.join(_PROJECT_ROOT, 'run', 'flame_mcp.sock')
                 if os.path.basename(_HOOKS_DIR) == 'hooks'
                 else '/tmp/flame_mcp.sock')
_BRIDGE_SOCKET_PATH = os.environ.get('FLAME_BRIDGE_SOCKET', _DEFAULT_SOCK)

# Crash recovery: written before each exec, cleared after success.
# If Flame crashes mid-exec, this file will contain the offending code
# on the next Flame startup so the chat widget can show a warning.
CRASH_RECOVERY_FILE = os.path.join(_PROJECT_ROOT, 'logs', 'crash_recovery.json')

# Model config — persists the selected model across widget sessions.
MODEL_CONFIG_FILE   = os.path.join(_PROJECT_ROOT, 'config.json')

# Available models shown in the chat widget dropdown.
# Each entry: (display_label, model_id, backend)
#   backend = "anthropic"    → Anthropic cloud (api.anthropic.com)
#   backend = "ollama"       → Self-hosted Ollama server (local LAN or remote Linux box)
#                              URL configured in config.json → ollama_url
#                              e.g. "http://192.168.1.50:11434"  (Linux workstation)
#   backend = "ollama_cloud" → Ollama.com cloud API (free tier, needs ollama_cloud_key)
# Add new entries here; install.sh configures ollama_url during setup.
AVAILABLE_MODELS = [
    # ── Anthropic cloud (default — needs internet + API key) ─────────
    ("Claude Opus 4.8",       "claude-opus-4-8",           "anthropic"),
    ("Claude Fable 5",        "claude-fable-5",            "anthropic"),
    ("Claude Sonnet 4.6",     "claude-sonnet-4-6",         "anthropic"),
    # ── Self-hosted Ollama (LAN GPU host, RTX 3090) ──────────────────
    ("Qwen3.5 9B 🖥",         "qwen3.5-mcp",               "ollama"),
    ("GLM-4.7 Flash 🖥",      "glm-4.7-flash",             "ollama"),
    # ── Mac-local Ollama (offline, no LAN) ───────────────────────────
    ("Qwen3.5 9B 🍎",         "qwen3.5-mcp",               "ollama_mac"),
    ("Qwen3.5 4B 🍎",         "qwen3.5:4b",                "ollama_mac"),
]
DEFAULT_MODEL    = "claude-opus-4-8"
DEFAULT_BACKEND  = "anthropic"

# Each entry: (display_label, effort_value). "auto" re-enables adaptive
# thinking (both hardening env vars cleared); fixed levels force that effort
# with adaptive thinking off. Persisted to config.json like model/backend.
AVAILABLE_EFFORTS = [
    ("Auto", "auto"),
    ("Low", "low"),
    ("Medium", "medium"),
    ("High", "high"),
    ("Max", "max"),
]
DEFAULT_EFFORT = "auto"

DEFAULT_OLLAMA_URL = "http://localhost:11434"   # overridden by config.json → ollama_url

# URL for backends that use the Mac's own Ollama daemon (cloud proxy + offline models).
# ollama_cloud:  localhost Ollama forwards the :cloud model to ollama.com servers.
# ollama_mac:    localhost Ollama runs the model directly (offline, no GPU needed).
# Neither requires gpu-server — Ollama must be installed on the Mac (brew install ollama).
OLLAMA_MAC_URL = "http://localhost:11434"

# Context window forced when pre-loading a self-hosted Ollama model.
# Ollama's /v1/messages (Anthropic-compat) endpoint ignores the model's
# Modelfile num_ctx at inference time and falls back to 4096.  We fix this by
# sending a pre-flight POST to /api/generate (native API) with
# options.num_ctx before running the claude CLI subprocess.  Ollama reuses
# the already-loaded runner, so the subsequent Anthropic-API call gets the
# correct 16 K context window.
OLLAMA_NUM_CTX = 24576   # 24 K: ~18.5 GB (model) + ~2.6 GB (KV cache) ≈ 21 GB < 24 GB VRAM
                         # 32 K pushed total to ~21.5 GB + CUDA overhead → OOM → full CPU fallback

# Mac-local Ollama: smaller default because models are 4B/9B on unified memory,
# not a 24 GB dGPU. Ollama's Anthropic-compat endpoint still ignores Modelfile
# num_ctx without an explicit preflight, so ollama_mac needs its own call.
OLLAMA_MAC_NUM_CTX = 8192

# Global bridge state
_bridge_active = False
_server_socket = None
_server_thread = None
_last_crash_info = None   # set at startup if a crash was detected

# A3 — exec() timeout guard (seconds). Protects against Flame API calls that
# hang indefinitely (e.g. UI blocking operations called from a non-main thread).
# The hung thread continues in the background; the client gets an error response
# so the MCP server is not left waiting for a reply that will never arrive.
_EXEC_TIMEOUT = 30

# OBS-025: Bridge-level redirect enforcement.
# execute_python in the MCP server can be bypassed when claude -p uses Bash to
# send JSON directly to this socket (documented protocol enabled the bypass).
# Adding the same redirect table HERE catches ALL execution attempts regardless
# of how they arrive — MCP tool call OR raw socket payload.
import re as _re_bridge
_BRIDGE_REDIRECT_PATTERNS = [
    (r'get_project_info|current_project.*\.(name|description|workspaces)',
     "Use get_project_info() MCP tool — accesses resolution/fps/bit_depth via Wiretap."),
    (r'ws\.libraries|current_workspace\.libraries|getLibraries',
     "Use list_libraries() MCP tool — filters hidden system libraries automatically."),
    (r'\.reels\b|getReels\(',
     "Use list_reels(library_name) MCP tool."),
    (r'getEntries\(|\.clips\b|getClips\(',
     "Use list_clips(library_name, reel_name) MCP tool."),
    (r'reel_groups|getReelGroups|desktop.*reel',
     "Use list_desktop_reels() MCP tool."),
    (r'batch_groups|getBatchGroups|\.batch_group',
     "Use list_batch_groups() MCP tool."),
    (r'flame\.selection\b',
     "flame.selection does not exist — use get_selected_clips() MCP tool."),
    (r'media_panel\.selected_entries',
     "Use get_selected_clips() MCP tool."),
    (r'get_version\(\)|flame\.version\b',
     "Use get_flame_version() MCP tool."),
    (r'wiretap_print_tree|wiretap_get_children',
     "Use flame_wiretap_tree(path) MCP tool."),
    (r'os\.listdir.*log|/opt/Autodesk/logs',
     "Use list_flame_logs() / read_flame_log() MCP tools."),
]

# Structural bridge patterns suppressed when creation intent is detected.
_BRIDGE_SOFT_REDIRECTS = {
    r'ws\.libraries|current_workspace\.libraries|getLibraries',
    r'\.reels\b|getReels\(',
    r'getEntries\(|\.clips\b|getClips\(',
    r'reel_groups|getReelGroups|desktop.*reel',
    r'batch_groups|getBatchGroups|\.batch_group',
}

_BRIDGE_CREATION_INTENT_RE = _re_bridge.compile(
    r'create_sequence\s*\('
    r'|\.overwrite\s*\('
    r'|import_clips\s*\('
    r'|flame\.delete\s*\('
    r'|schedule_idle_event'
    r'|create_reel\s*\('
    r'|create_library\s*\('
    r'|create_batch_group\s*\('
    r'|create_clip\s*\('
)


# ── Flame initialisation hook ─────────────────────────────────────────────────

def app_initialized(project_name):
    """Called automatically by Flame when the application finishes loading."""
    _check_crash_recovery()
    _start_bridge()


# ── Crash recovery ────────────────────────────────────────────────────────────

def _check_crash_recovery():
    """
    Called at Flame startup. If crash_recovery.json exists with status='running',
    Flame crashed during the previous session while executing Python code.
    Save the info so the chat widget can display it.
    A11 — Entries older than 24 h are silently expired; stale crashes are not actionable.
    """
    global _last_crash_info
    try:
        if not os.path.exists(CRASH_RECOVERY_FILE):
            return
        with open(CRASH_RECOVERY_FILE) as f:
            data = json.load(f)
        if data.get('status') == 'running':
            # A11 — Ignore crashes older than 1 day
            try:
                import datetime as _dt
                crash_ts = _dt.datetime.fromisoformat(data.get('timestamp', ''))
                age_s = (_dt.datetime.now() - crash_ts).total_seconds()
                if age_s > 86400:
                    _log("⚠️  CRASH RECOVERY: stale entry (>24 h) — clearing automatically.")
                    _clear_crash_recovery()
                    return
            except Exception:
                pass  # unparseable timestamp → keep the warning
            _last_crash_info = data
            _log("⚠️  CRASH RECOVERY: Flame crashed during previous session.")
            _log(f"   Last code executed: {data.get('code','')[:200].strip()}")
    except Exception as e:
        _log(f"Crash recovery check failed: {e}")


def _write_crash_recovery(code):
    """Write code to crash recovery file before execution."""
    try:
        os.makedirs(os.path.dirname(CRASH_RECOVERY_FILE), exist_ok=True)
        with open(CRASH_RECOVERY_FILE, 'w') as f:
            json.dump({
                'status':    'running',
                'timestamp': datetime.datetime.now().isoformat(),
                'code':      code,
            }, f)
    except Exception:
        pass


def _clear_crash_recovery():
    """Mark last exec as successful — no crash occurred."""
    try:
        with open(CRASH_RECOVERY_FILE, 'w') as f:
            json.dump({'status': 'ok'}, f)
    except Exception:
        pass


# ── Bridge control ────────────────────────────────────────────────────────────

def _start_bridge():
    """Start the TCP server in a background thread."""
    global _server_thread, _bridge_active

    if _bridge_active:
        print("[FlameMCPBridge] Already active.")
        return

    _server_thread = threading.Thread(target=_run_server, daemon=True, name="FlameMCPBridge")
    _server_thread.start()


def _stop_bridge():
    """Stop the server by closing the socket (Unix or TCP) and cleaning up."""
    global _server_socket, _bridge_active

    if not _bridge_active:
        print("[FlameMCPBridge] Already inactive.")
        return

    if _server_socket:
        try:
            _server_socket.close()
        except Exception:
            pass
        # A13 — remove Unix socket file if it was created by this run
        if hasattr(socket, 'AF_UNIX') and os.path.exists(_BRIDGE_SOCKET_PATH):
            try:
                os.unlink(_BRIDGE_SOCKET_PATH)
            except Exception:
                pass

    _bridge_active = False
    print("[FlameMCPBridge] Stopped.")


def _run_server():
    """
    Main server loop. Accepts incoming connections.
    A13 — Uses a Unix domain socket by default (owner-only file permissions replace
    TCP network authentication). Falls back to TCP if AF_UNIX is unavailable.
    """
    global _server_socket, _bridge_active

    # A13 — prefer Unix socket; Python 3.9+ on macOS/Linux always has AF_UNIX
    _use_unix = hasattr(socket, 'AF_UNIX')
    _bound_ok = False

    if _use_unix:
        run_dir = os.path.dirname(_BRIDGE_SOCKET_PATH)
        try:
            os.makedirs(run_dir, exist_ok=True)
            os.chmod(run_dir, 0o700)
        except Exception:
            pass
        # Remove stale socket file left over from a previous Flame session
        if os.path.exists(_BRIDGE_SOCKET_PATH):
            try:
                os.unlink(_BRIDGE_SOCKET_PATH)
            except Exception:
                pass
        _server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            _server_socket.bind(_BRIDGE_SOCKET_PATH)
            try:
                os.chmod(_BRIDGE_SOCKET_PATH, 0o600)  # owner-only access
            except Exception:
                pass
            _bound_ok = True
        except OSError as e:
            print(f"[FlameMCPBridge] Unix socket bind failed: {e} — falling back to TCP",
                  file=sys.stderr)
            try:
                _server_socket.close()
            except Exception:
                pass
            _use_unix = False

    if not _use_unix:
        _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            _server_socket.bind((BRIDGE_HOST, BRIDGE_PORT))
            _bound_ok = True
        except OSError as e:
            print(f"[FlameMCPBridge] ERROR opening port {BRIDGE_PORT}: {e}", file=sys.stderr)

    if not _bound_ok:
        return

    _server_socket.listen(5)
    _bridge_active = True

    if _use_unix:
        print(f"[FlameMCPBridge] Active on {_BRIDGE_SOCKET_PATH} (Unix socket)")
    else:
        print(f"[FlameMCPBridge] Active on {BRIDGE_HOST}:{BRIDGE_PORT} (TCP fallback)")

    while _bridge_active:
        try:
            _server_socket.settimeout(1.0)
            conn, _addr = _server_socket.accept()
            t = threading.Thread(target=_handle_connection, args=(conn,), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break

    _bridge_active = False


def _handle_connection(conn):
    """
    Handle an incoming connection:
    1. Read JSON payload containing Python code to execute.
    2. Execute the code with access to the flame module.
    3. Return result or error as JSON.
    """
    import flame

    try:
        raw = b""
        while not raw.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk

        payload = json.loads(raw.decode('utf-8').strip())
        code = payload.get('code', '')

        # Log first line of code so we can see what's being executed
        first_line = code.strip().splitlines()[0] if code.strip() else '(empty)'
        _log(f"EXEC: {first_line[:120]}")

        # OBS-025: Bridge-level redirect enforcement — BRIDGE ONLY, no server trust.
        # Marker is '# DT\n' at the START of the code string, added by _call_flame
        # in the MCP server for every dedicated tool call (list_libraries, etc.).
        # execute_python does NOT add the prefix → always goes through redirect check.
        # Old/cached server never adds '# DT\n' → all its code goes through check.
        # This is fully independent of server reload / pkill cycles.
        _is_dt = code.startswith('# DT\n')
        if _is_dt:
            code = code[len('# DT\n'):]   # strip marker before execution
        _log(f"PAYLOAD keys={list(payload.keys())}  _dt={_is_dt}")
        if not _is_dt:
            _has_creation = bool(_BRIDGE_CREATION_INTENT_RE.search(code))
            try:
                with open("/tmp/flame_mcp_redirect.log", "a") as _rf:
                    _rf.write(
                        f"CHECK: code={code[:80]!r} "
                        f"patterns={len(_BRIDGE_REDIRECT_PATTERNS)} "
                        f"creation={_has_creation}\n"
                    )
            except Exception:
                pass
            for _pat, _msg in _BRIDGE_REDIRECT_PATTERNS:
                if _re_bridge.search(_pat, code):
                    if _has_creation and _pat in _BRIDGE_SOFT_REDIRECTS:
                        _log(f"  ℹ️  REDIRECT suppressed (creation intent): {_pat[:60]}")
                        continue
                    _log(f"  🚫 REDIRECT matched: {_pat[:60]}")
                    conn.sendall((json.dumps({
                        'status': 'redirect',
                        'error': (
                            f"\U0001f6ab REDIRECT \u2014 a dedicated MCP tool handles this query.\n"
                            f"   {_msg}\n"
                            f"   Call the MCP tool instead of sending code to the bridge."
                        ),
                        'output': '',
                    }) + "\n").encode('utf-8'))
                    conn.close()
                    return

        local_ns = {'flame': flame}
        result   = {}
        done     = threading.Event()

        # A3 — run exec in a watched thread so we can enforce _EXEC_TIMEOUT.
        # The thread captures its own stdout to avoid races with the main bridge.
        def _exec_target():
            buf        = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buf
            try:
                _write_crash_recovery(code)
                exec(compile(code, '<flame_mcp>', 'exec'), local_ns)
                _clear_crash_recovery()
                sys.stdout = old_stdout
                result['status'] = 'ok'
                result['output'] = buf.getvalue()
                if '_result' in local_ns:
                    result['return_value'] = str(local_ns['_result'])
                _log(f"  → ok  output: {buf.getvalue()[:80].strip()!r}")
            except Exception:
                sys.stdout = old_stdout
                tb = traceback.format_exc()
                result['status'] = 'error'
                result['error']  = tb
                result['output'] = buf.getvalue()
                _log(f"  → ERROR: {tb.splitlines()[-1][:120]}")
                # Flame C++ corruption warning ─────────────────────────────────
                # 'unordered_map::at' means a C++ exception escaped the binding.
                # Flame's internal state may be corrupted even though Python caught it.
                _CPP_CRASH_MARKERS = (
                    'unordered_map::at', 'out_of_range', 'bad_weak_ptr', 'PyFlame',
                )
                if any(m in tb for m in _CPP_CRASH_MARKERS):
                    result['flame_state'] = 'possibly_corrupted'
                    _log("  ⚠️  Flame C++ exception detected — UI may be corrupted. "
                         "Consider restarting Flame if behaviour seems wrong.")
                else:
                    # Normal Python exception (AttributeError, NameError, etc.) —
                    # NOT a Flame crash.  Clear crash recovery so the next Flame
                    # startup does not show a false "previous session crashed" warning.
                    _clear_crash_recovery()
            finally:
                done.set()

        exec_thread = threading.Thread(target=_exec_target, daemon=True,
                                       name="flame_exec")
        exec_thread.start()
        exec_thread.join(_EXEC_TIMEOUT)

        if not done.is_set():
            # Thread is still alive — exec() hung (e.g. blocking UI call)
            result['status'] = 'error'
            result['error']  = (
                f"⏱ Execution timed out after {_EXEC_TIMEOUT}s. "
                "The Flame operation may still be running in the background. "
                "If Flame appears frozen, restart the bridge via the menu."
            )
            if not result.get('output'):
                result['output'] = ''
            _log(f"  ⏱ TIMEOUT after {_EXEC_TIMEOUT}s — exec thread still alive")

        conn.sendall((json.dumps(result) + "\n").encode('utf-8'))

    except Exception as e:
        _log(f"CONNECTION ERROR: {e}")
        try:
            conn.sendall((json.dumps({'status': 'error', 'error': str(e)}) + "\n").encode('utf-8'))
        except Exception:
            pass
    finally:
        conn.close()


# ── Logging ───────────────────────────────────────────────────────────────────

LOG_FILE = os.path.join(_PROJECT_ROOT, 'logs', 'flame_mcp_bridge.log')
_LOG_MAX_BYTES = 5 * 1024 * 1024  # rotate at 5 MB so the log cannot grow unbounded


def _log(msg):
    """Write a timestamped line to the log file and to stdout.

    Size-rotates ``LOG_FILE`` at ``_LOG_MAX_BYTES`` (keeps a single ``.1``
    backup) so a long-running Flame session cannot grow the bridge log
    without bound, and restricts the file to owner-rw / group-r (0o640)
    instead of leaving it at the umask default. All file I/O stays wrapped
    so logging can never raise into the bridge's request path.
    """
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) >= _LOG_MAX_BYTES:
            try:
                os.replace(LOG_FILE, LOG_FILE + '.1')
            except Exception:
                pass
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
        try:
            os.chmod(LOG_FILE, 0o640)
        except Exception:
            pass
    except Exception:
        pass


# ── Qt import helper ──────────────────────────────────────────────────────────

def _import_qt():
    """
    Try to import Qt widgets from PySide2 or PySide6.
    Flame bundles PySide2 but may not add it to sys.path automatically.
    Searches /opt/Autodesk/ for the correct site-packages if needed.
    Returns (QtWidgets, QtCore, QtGui) or (None, None, None).
    """
    import glob

    def _try_pyside2():
        from PySide2 import QtWidgets, QtCore, QtGui
        return QtWidgets, QtCore, QtGui

    def _try_pyside6():
        from PySide6 import QtWidgets, QtCore, QtGui
        return QtWidgets, QtCore, QtGui

    # 1. Standard import (works if Flame already added site-packages to sys.path)
    for fn in (_try_pyside2, _try_pyside6):
        try:
            return fn()
        except ImportError:
            pass

    # 2. Search Flame's own Python site-packages under /opt/Autodesk/
    candidates = sorted(
        glob.glob('/opt/Autodesk/*/python/lib/python*/site-packages') +
        glob.glob('/opt/Autodesk/*/lib/python*/site-packages') +
        glob.glob('/opt/autodesk/*/python/lib/python*/site-packages'),
        reverse=True  # newest version first
    )
    _log(f"Qt search: found {len(candidates)} candidate site-packages paths")
    for path in candidates:
        if path not in sys.path:
            sys.path.insert(0, path)
            _log(f"Qt search: added {path}")

    for fn in (_try_pyside2, _try_pyside6):
        try:
            result = fn()
            _log(f"Qt search: import succeeded after path search")
            return result
        except ImportError:
            pass

    _log("Qt search: PySide2 and PySide6 both unavailable")
    return None, None, None


# Keep references alive so the GC does not destroy open dialogs
_open_dialogs = []


# ── Flame Chat Widget ──────────────────────────────────────────────────────────

_chat_instance = None  # singleton — keeps widget alive


def _make_enter_catcher(callback, QtCore):
    """
    Factory that returns a QObject-based event filter for Ctrl+Return.
    The class is built at runtime so it inherits from the correct QtCore.QObject
    (PySide2 vs PySide6 both require QObject as base for installEventFilter).
    """
    class _EnterCatcher(QtCore.QObject):
        def __init__(self):
            super().__init__()
            self._cb = callback

        def eventFilter(self, obj, event):
            # PySide2: QEvent.KeyPress  /  PySide6: QEvent.Type.KeyPress
            key_press = getattr(QtCore.QEvent, 'Type', QtCore.QEvent).KeyPress
            # PySide2: Qt.Key_Return / Qt.ControlModifier at QtCore.Qt
            # PySide6: same path, still works
            if (event.type() == key_press and
                    event.key() == QtCore.Qt.Key_Return and
                    bool(event.modifiers() & QtCore.Qt.ControlModifier)):
                self._cb()
                return True
            return False

    return _EnterCatcher()


class _FlameChat:
    """
    Qt chat widget that lets you talk to Claude from inside Flame.
    - No terminal / no shell — pure GUI
    - Uses 'claude -p' subprocess (Claude Code) — no API key needed,
      works with your existing Claude Pro / Max subscription
    - All 18 MCP tools available: execute_python, search_flame_docs,
      list_libraries, list_reels, list_clips, list_desktop_reels,
      list_batch_groups, list_all_projects, get_clip_metadata,
      get_selected_clips, flame_wiretap_tree, list_flame_logs,
      read_flame_log, learn_pattern, session_stats, and more.
    - Token tracking and self-improving RAG work identically to the terminal
    """

    def __init__(self):
        QtWidgets, QtCore, _ = _import_qt()
        if QtWidgets is None:
            raise RuntimeError("Qt unavailable in this Flame installation")
        self._Qt = QtWidgets
        self._Core = QtCore
        self._messages = []          # list of {"role": str, "content": str}
        self._ui_queue = []          # written by bg thread, drained by QTimer in main thread
        self._busy = False
        self._session_tokens = 0     # cumulative tokens this widget session
        self._rate_limited = False   # True if last call hit a rate limit
        self._last_exec_count = 0    # execute_python calls in last agent turn
        # Session continuity (Chat 98). Every turn spawns a fresh `claude -p`,
        # so without this the CLI starts from zero each time and only sees the
        # 4-message digest _build_prompt used to inject — measured in-vivo on a
        # conform: the model re-discovered the FPT link, the project id, the
        # Cut and its CutItems FIVE times, and re-fetched the workflow recipe
        # on every turn because it fell outside the digest. Capturing the
        # CLI's session_id and passing --resume keeps one real conversation.
        self._session_id = None
        self._model, self._backend, self._ollama_url, self._ollama_cloud_key = self._load_model_config()
        self._effort = self._load_effort_config()
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        Qt, Core = self._Qt, self._Core

        self._window = Qt.QWidget()
        self._window.setWindowTitle("Claude — Flame Assistant")
        self._window.setWindowFlags(Core.Qt.Window | Core.Qt.WindowStaysOnTopHint)
        self._window.resize(700, 880)
        self._window.setStyleSheet("background-color:#1c1c1c;")

        layout = Qt.QVBoxLayout(self._window)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        title = Qt.QLabel("🔥  Claude — Flame Assistant")
        title.setStyleSheet("color:#ffff00;font-size:14px;font-weight:bold;padding:4px 0;")
        layout.addWidget(title)

        # ── Model selector ────────────────────────────────────────────────────
        model_row = Qt.QHBoxLayout()
        model_row.setSpacing(6)

        model_lbl = Qt.QLabel("Model:")
        model_lbl.setStyleSheet("color:#888;font-size:11px;min-width:42px;")
        model_row.addWidget(model_lbl)

        self._model_combo = Qt.QComboBox()
        for label, _, _ in AVAILABLE_MODELS:
            self._model_combo.addItem(label)
        # Restore persisted selection
        ids = [m[1] for m in AVAILABLE_MODELS]
        idx = ids.index(self._model) if self._model in ids else 0
        self._model_combo.setCurrentIndex(idx)
        self._model_combo.setStyleSheet(
            "QComboBox{background:#2a2a2a;color:#e0e0e0;border:1px solid #444;"
            "border-radius:4px;padding:2px 8px;font-size:11px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#2a2a2a;color:#e0e0e0;"
            "selection-background-color:#444;}")
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        model_row.addWidget(self._model_combo)
        model_row.addStretch()
        layout.addLayout(model_row)

        # ── Effort selector ───────────────────────────────────────────────
        effort_row = Qt.QHBoxLayout()
        effort_row.setSpacing(6)
        effort_lbl = Qt.QLabel("Effort:")
        effort_lbl.setStyleSheet("color:#888;font-size:11px;min-width:42px;")
        effort_row.addWidget(effort_lbl)
        self._effort_combo = Qt.QComboBox()
        for label, _ in AVAILABLE_EFFORTS:
            self._effort_combo.addItem(label)
        eff_ids = [e[1] for e in AVAILABLE_EFFORTS]
        eff_idx = eff_ids.index(self._effort) if self._effort in eff_ids else 0
        self._effort_combo.setCurrentIndex(eff_idx)
        self._effort_combo.setStyleSheet(
            "QComboBox{background:#2a2a2a;color:#e0e0e0;border:1px solid #444;"
            "border-radius:4px;padding:2px 8px;font-size:11px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#2a2a2a;color:#e0e0e0;"
            "selection-background-color:#444;}")
        self._effort_combo.currentIndexChanged.connect(self._on_effort_changed)
        effort_row.addWidget(self._effort_combo)
        effort_row.addStretch()
        layout.addLayout(effort_row)

        # ── Ollama server URL row (visible only when an Ollama model is selected) ──
        # Wrapped in a QWidget so we can show/hide the whole row cleanly.
        self._ollama_url_widget = Qt.QWidget()
        ollama_row = Qt.QHBoxLayout(self._ollama_url_widget)
        ollama_row.setContentsMargins(0, 0, 0, 0)
        ollama_row.setSpacing(6)

        ollama_lbl = Qt.QLabel("Ollama server:")
        ollama_lbl.setStyleSheet("color:#888;font-size:11px;min-width:90px;")
        ollama_row.addWidget(ollama_lbl)

        self._ollama_input = Qt.QLineEdit()
        self._ollama_input.setText(self._ollama_url)
        self._ollama_input.setPlaceholderText("http://192.168.1.50:11434")
        self._ollama_input.setToolTip(
            "IP address and port of the Linux machine running Ollama.\n"
            "Example: http://192.168.1.50:11434\n"
            "Press Enter to save.")
        self._ollama_input.setStyleSheet(
            "QLineEdit{background:#2a2a2a;color:#e0e0e0;border:1px solid #555;"
            "border-radius:4px;padding:2px 8px;font-size:11px;}"
            "QLineEdit:focus{border:1px solid #ffff00;}")
        self._ollama_input.editingFinished.connect(self._on_ollama_url_changed)
        ollama_row.addWidget(self._ollama_input, stretch=1)

        layout.addWidget(self._ollama_url_widget)
        # Show only when the current backend is "ollama" (self-hosted)
        self._ollama_url_widget.setVisible(self._backend == "ollama")

        # ── Ollama cloud API key row (visible only when ollama_cloud is selected) ──
        self._ollama_cloud_key_widget = Qt.QWidget()
        cloud_key_row = Qt.QHBoxLayout(self._ollama_cloud_key_widget)
        cloud_key_row.setContentsMargins(0, 0, 0, 0)
        cloud_key_row.setSpacing(6)

        cloud_key_lbl = Qt.QLabel("Ollama API key:")
        cloud_key_lbl.setStyleSheet("color:#888;font-size:11px;min-width:90px;")
        cloud_key_row.addWidget(cloud_key_lbl)

        self._ollama_cloud_key_input = Qt.QLineEdit()
        self._ollama_cloud_key_input.setText(self._ollama_cloud_key)
        self._ollama_cloud_key_input.setPlaceholderText("ollama_…  (get it at ollama.com → API keys)")
        self._ollama_cloud_key_input.setEchoMode(Qt.QLineEdit.Password)
        self._ollama_cloud_key_input.setToolTip(
            "API key from ollama.com (free tier available).\n"
            "Go to ollama.com → account → API keys → Create key.\n"
            "Press Enter to save.")
        self._ollama_cloud_key_input.setStyleSheet(
            "QLineEdit{background:#2a2a2a;color:#e0e0e0;border:1px solid #555;"
            "border-radius:4px;padding:2px 8px;font-size:11px;}"
            "QLineEdit:focus{border:1px solid #cccccc;}")
        self._ollama_cloud_key_input.editingFinished.connect(self._on_ollama_cloud_key_changed)
        cloud_key_row.addWidget(self._ollama_cloud_key_input, stretch=1)

        layout.addWidget(self._ollama_cloud_key_widget)
        # Cloud key no longer used — auth handled by Mac Ollama daemon internally
        self._ollama_cloud_key_widget.setVisible(False)
        # ─────────────────────────────────────────────────────────────────────

        # Populate combo labels with currently-configured server / key info
        self._update_combo_labels()

        self._chat = Qt.QTextEdit()
        self._chat.setReadOnly(True)
        self._chat.setStyleSheet(
            "QTextEdit{background:#111;color:#e0e0e0;font-size:13px;"
            "border:1px solid #333;border-radius:6px;padding:10px;}")
        layout.addWidget(self._chat, stretch=1)

        self._status = Qt.QLabel("Ready  ·  Ctrl+Return to send")
        self._status.setStyleSheet(
            "color:#555;font-size:12px;padding:2px 4px;")
        layout.addWidget(self._status)

        row = Qt.QHBoxLayout()
        row.setSpacing(8)

        self._input = Qt.QTextEdit()
        self._input.setMaximumHeight(90)
        self._input.setMinimumHeight(60)
        self._input.setPlaceholderText("Ask Claude to do something in Flame…  (uses Claude Code — no API key needed)")
        self._input.setStyleSheet(
            "QTextEdit{background:#252525;color:#e8e8e8;font-size:13px;"
            "border:1px solid #444;border-radius:6px;padding:8px;}")
        # Install Ctrl+Return event filter
        self._enter_catcher = _make_enter_catcher(self._on_send, Core)
        self._input.installEventFilter(self._enter_catcher)
        row.addWidget(self._input, stretch=1)

        btns = Qt.QVBoxLayout()
        btns.setSpacing(4)

        self._send_btn = Qt.QPushButton("Send")
        self._send_btn.setFixedSize(72, 40)
        self._send_btn.clicked.connect(self._on_send)
        self._send_btn.setStyleSheet(
            "QPushButton{background:#ffff00;color:#1c1c1c;border:none;"
            "border-radius:5px;font-weight:bold;font-size:13px;}"
            "QPushButton:hover{background:#cccc00;}"
            "QPushButton:disabled{background:#3a3a00;color:#6a6320;}")
        btns.addWidget(self._send_btn)

        clear_btn = Qt.QPushButton("Clear")
        clear_btn.setFixedSize(72, 28)
        clear_btn.clicked.connect(self._on_clear)
        clear_btn.setStyleSheet(
            "QPushButton{background:#333;color:#aaa;border:none;"
            "border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#444;color:#ccc;}")
        btns.addWidget(clear_btn)
        btns.addStretch()

        row.addLayout(btns)
        layout.addLayout(row)

        # QTimer drains the UI queue — runs in the main thread every 40 ms.
        # QTimer.singleShot from background threads does NOT work in PySide2
        # (background threads have no event loop), so we use this polling approach.
        self._timer = Core.QTimer()
        self._timer.timeout.connect(self._flush_ui_queue)
        self._timer.start(40)

        _open_dialogs.append(self._window)

    def show(self):
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._input.setFocus()
        # Warn immediately if the persisted backend is ollama_mac
        if self._backend == "ollama_mac":
            self._append_bubble(
                "warn",
                "⚠️  Modelo offline (7B): capacidad de tool use limitada.\n"
                "Puede imprimir JSON en lugar de ejecutar herramientas.\n"
                "Recomendado solo para consultas de texto. Usa anthropic u ollama para controlar Flame.")

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_send(self):
        if self._busy:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return

        # ── /undo [N] — undo last N Flame actions without going through Claude ──
        import re as _re
        m = _re.match(r'^/?undo\s*(\d*)$', text, _re.IGNORECASE)
        if m:
            self._input.clear()
            n = int(m.group(1)) if m.group(1) else 1
            self._append_bubble("user", text)
            try:
                import flame as _flame
                for _ in range(n):
                    _flame.execute_shortcut("Undo")
                label = "action" if n == 1 else "actions"
                msg = f"↩ {n} {label} undone."
            except Exception as e:
                msg = f"⚠️ Undo failed: {e}"
            self._append_bubble("assistant", msg)
            return

        # ── /wrong [reason] — feedback: the last response was incorrect ──
        import re as _re2
        m2 = _re2.match(r'^/?wrong\s*(.*)', text, _re2.IGNORECASE | _re2.DOTALL)
        if m2:
            self._input.clear()
            detail = m2.group(1).strip()
            correction = (
                "⚠️ USER FEEDBACK: Your last response was INCORRECT. "
                + (f"Reason: {detail}. " if detail else "")
                + "Do not learn the previous code as a correct pattern (do not call learn_pattern). "
                "Analyze what went wrong and try again correctly."
            )
            self._append_bubble("user", f"⚠️ /wrong{(' — ' + detail) if detail else ''}")
            self._messages.append({"role": "user", "content": correction})
            self._set_busy(True)
            import threading as _threading2
            _threading2.Thread(target=self._agent_loop, daemon=True).start()
            return

        self._input.clear()
        self._messages.append({"role": "user", "content": text})
        self._append_bubble("user", text)
        self._set_busy(True)
        import threading
        threading.Thread(target=self._agent_loop, daemon=True).start()

    def _on_clear(self):
        self._messages.clear()
        self._chat.clear()
        self._session_tokens = 0
        self._rate_limited = False
        # Drop the CLI session too — Clear must mean a genuinely fresh start,
        # not a cleared transcript in front of a conversation that remembers.
        self._session_id = None
        self._ui_queue.append(lambda: self._set_busy(False))

    # ── Agent loop (background thread) ───────────────────────────────────────

    def _agent_loop(self):
        """
        Calls 'claude -p --output-format stream-json <prompt>' as a subprocess.

        Parses the newline-delimited JSON stream to display:
          - assistant text blocks  → main green chat bubble
          - tool_use events        → live status bar update (e.g. "⚡ Executing in Flame…")
          - tool_result stats      → purple "tool" bubble with RAG / token summary
          - learn_pattern confirm  → purple bubble with 🧠 message

        Uses the user's existing Claude Code session (Pro/Max) — no API key needed.

        F0 baseline: every invocation appends one record to logs/turns.jsonl
        whether it succeeded, errored, or timed out. The record is written
        from the outer finally so it is never skipped — pre-flight variables
        are initialised to sane defaults so an early exception still produces
        a usable row.
        """
        # F0: turn-record fields, initialised here so the finally clause can
        # always read them. Updated incrementally as the subprocess progresses.
        _t0_turn        = time.monotonic()
        _turn_prompt    = ""
        _turn_watchdog  = 0
        _turn_exit_code = None
        _turn_timed_out = False
        _turn_stderr_lines: list[str] = []
        _turn_error_msg = None

        try:
            self._ui_queue.append(lambda: (
                self._status.setStyleSheet(self._STYLE_BUSY),
                self._status.setText("Thinking…"),
            ))

            claude_path, env = self._find_claude()
            if not claude_path:
                _log("Chat: claude not found. Searched: " + env.get('PATH', ''))
                raise RuntimeError(
                    "claude CLI not found in PATH.\n\n"
                    "Check the bridge log (MCP Bridge → View log) for searched paths.\n\n"
                    "Quick fix — run in Terminal:\n"
                    "  which claude\n"
                    f"Then paste the full path into {_PROJECT_ROOT}/.env:\n"
                    "  CLAUDE_PATH=/usr/local/bin/claude"
                )

            # Reasoning effort for every claude subprocess spawned from the
            # Flame panel, controlled by the Effort selector (default "auto").
            # A fixed level (low/medium/high/max) disables adaptive thinking
            # and forces that effort, preventing Anthropic's adaptive-thinking
            # feature from allocating zero reasoning tokens on turns it judges
            # as simple — which produces hallucinated API calls when
            # execute_python needs fresh code paths. "auto" clears both vars so
            # the CLI's adaptive-thinking default applies. Ollama ignores the
            # vars. The user controls their own top-level claude session via
            # /effort; these overrides affect the MCP-spawned subprocess only.
            if self._effort and self._effort != "auto":
                env["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] = "1"
                env["CLAUDE_CODE_EFFORT_LEVEL"] = self._effort
            else:
                # "auto": the child uses the CLI's adaptive-thinking default;
                # pop both so an inherited os.environ value cannot force them.
                env.pop("CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", None)
                env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)

            # The Flame bridge has NO ShotGrid project context (no tk engine in
            # the bridge). If the spawned claude reaches fpt-mcp (it loads the
            # ecosystem MCP servers from ~/.claude.json), inject "0" ("no
            # project") so a project-scoped sg_create FAILS loudly instead of
            # silently writing to fpt-mcp's stale .env default — fpt-mcp's gate
            # then asks the user. Zero silent defaults across all consoles
            # (Chat 69). The bridge itself does no ShotGrid; this is a safety net.
            env["SHOTGRID_PROJECT_ID"] = "0"
            # Defer MCP tool schemas: only tool NAMES load upfront and the model
            # fetches a schema on demand via ToolSearch, so the request isn't
            # bloated by every loaded server's full tool definitions.
            env["ENABLE_TOOL_SEARCH"] = "true"

            # ── Ollama backend routing ────────────────────────────────────────
            # Four backends, two physical paths:
            #
            #  anthropic    → api.anthropic.com  (default, no extra setup)
            #  ollama       → gpu-server:11434   (LAN GPU server, big models)
            #  ollama_cloud → localhost:11434    (Mac Ollama daemon → ollama.com cloud)
            #  ollama_mac   → localhost:11434    (Mac Ollama daemon, local model, offline)
            #
            # ollama_cloud and ollama_mac both require Ollama installed on this Mac:
            #   brew install ollama && ollama serve
            if self._backend == "ollama":
                if not self._check_ollama(self._ollama_url):
                    raise RuntimeError(
                        f"Ollama LAN server not reachable at {self._ollama_url}\n\n"
                        "Check that Ollama is running on the Linux machine:\n"
                        "  OLLAMA_HOST=0.0.0.0 ollama serve\n\n"
                        "And that ollama_url in config.json points to it:\n"
                        f"  {self._ollama_url}\n\n"
                        "Or switch to an Anthropic model until it's available."
                    )
                # Force-load with correct context window (Anthropic endpoint ignores Modelfile num_ctx)
                self._preload_ollama_model()
                env = self._get_ollama_env(env)
            elif self._backend in ("ollama_cloud", "ollama_mac"):
                if not self._check_ollama(OLLAMA_MAC_URL):
                    raise RuntimeError(
                        f"Ollama not found on this Mac ({OLLAMA_MAC_URL}).\n\n"
                        "Install and start Ollama:\n"
                        "  brew install ollama\n"
                        "  ollama serve\n\n"
                        + (
                            "Then the cloud model will be downloaded on first use.\n"
                            "No GPU required — inference runs on ollama.com."
                            if self._backend == "ollama_cloud" else
                            f"Then pull the model:\n  ollama pull {self._model}\n\n"
                            "Works offline once downloaded (~4 GB)."
                        )
                    )
                # ollama_mac needs its own num_ctx preflight — Anthropic-compat
                # endpoint ignores Modelfile settings, same as LAN. ollama_cloud
                # is deliberately skipped: the cloud runners manage context.
                if self._backend == "ollama_mac":
                    self._preload_ollama_model(url=OLLAMA_MAC_URL, num_ctx=OLLAMA_MAC_NUM_CTX)
                env = self._get_ollama_env(env)

            prompt = self._build_prompt()
            _turn_prompt = prompt  # F0: snapshot for turn-record
            if not prompt.strip():
                # UI queue consumes callables, not tuples.
                self._ui_queue.append(lambda: self._append_bubble(
                    "assistant", "Mensaje vacío — escribe algo antes de enviar."))
                self._ui_queue.append(lambda: self._set_busy(False))
                return

            # Resolve cwd to the repo directory that contains .mcp.json so
            # that 'claude -p' discovers the flame MCP server definition.
            # When the hook runs from hooks/ inside the repo, _PROJECT_ROOT
            # already points there.  When installed to /opt/Autodesk/shared/
            # python/, _PROJECT_ROOT is wrong — search known locations.
            _repo_candidates = [
                _PROJECT_ROOT,
                os.path.expanduser('~/Projects/flame-mcp'),
                os.path.expanduser('~/Claude_projects/flame-mcp'),
                os.path.expanduser('~/flame-mcp'),
                os.path.expanduser('~/Documents/flame-mcp'),
            ]
            cwd = next(
                (p for p in _repo_candidates
                 if os.path.isfile(os.path.join(p, '.mcp.json'))),
                _PROJECT_ROOT,  # last resort fallback
            )

            cmd = [claude_path, '-p', '--verbose', '--output-format', 'stream-json']
            # Continue the same CLI conversation across turns (Chat 98). The id
            # is captured from the stream events of the previous turn; a stale
            # one (transcript pruned, cleanup window elapsed) makes the CLI
            # abort, so the retry below drops it and starts fresh once.
            if self._session_id:
                cmd.extend(['--resume', self._session_id])
            if self._model:
                cmd.extend(['--model', self._model])
            # Cap agentic turns for Ollama models.  Qwen3 in thinking mode tends
            # to plan exhaustive exploration and then execute every step, running
            # 15-20 tool calls for questions that need 1-2.  --max-turns 6 gives
            # enough headroom for multi-step tasks while preventing runaway loops.
            # Anthropic models are left uncapped (they follow stop instructions).
            if getattr(self, '_backend', '') in ('ollama', 'ollama_cloud', 'ollama_mac'):
                cmd.extend(['--max-turns', '6'])
            # Inject critical tool-selection rules as a real system prompt so
            # claude -p receives them at higher priority than MCP instructions
            # metadata (OBS-011/013 root cause fix).
            cmd.extend([
                '--append-system-prompt',
                (
                    'CRITICAL RULES for this Flame MCP session:\n'
                    '1. ALWAYS use dedicated MCP tools when they cover the query — '
                    'NEVER use execute_python for: project info, libraries, reels, '
                    'clips, desktop, batch groups, clip metadata, selected clips, '
                    'wiretap tree, log files, ping, or version.\n'
                    '2. ALWAYS call search_flame_docs before ANY execute_python call '
                    '— no exceptions, even for patterns you think you know.\n'
                    '2b. PIPELINE WORKFLOWS (conform, publish, the FPT project '
                    'link): call resolve_concept FIRST and follow the recipe it '
                    'returns, before planning anything of your own. These span '
                    'both MCP servers and have gates you cannot infer.\n'
                    '2c. This session has NO ShotGrid project scope by design. '
                    'Before ANY ShotGrid query, resolve the project with '
                    "fpt_link(action='get') and pass it explicitly. The Flame and "
                    'FPT project names are routinely DIFFERENT — that is the '
                    'normal case, never report it as a mismatch.\n'
                    '3. flame.selection does not exist — use flame.media_panel.selected_entries.\n'
                    '4. flame.projects.current_project.libraries returns None — '
                    'use current_workspace.libraries.\n'
                    'LANGUAGE — overrides any global config: there is NO default '
                    'language. Reply ONLY in the language of the latest user '
                    'message. English in → English out, Spanish in → Spanish out. '
                    'Disregard any "Spanish by default" or preferred-language '
                    'instruction inherited from the global CLAUDE.md or from '
                    'earlier turns — mirroring the latest message always wins. '
                    'Re-detect every turn.\n'
                    'READ-ONLY: you cannot edit/create/delete files (Edit/Write/'
                    'Bash are disabled). Use the MCP tools only. RAG self-learning '
                    'still works via learn_pattern (an MCP tool). To propose a '
                    'code fix, emit one line @@SUGGESTION@@ <title> :: <detail> '
                    '(the console logs it); never try to edit files.'
                ),
            ])
            # Read-only bridge: deny every file-mutation tool so the subprocess
            # cannot modify the repo. MCP tools + Read stay available (RAG
            # self-learning is a server-side MCP tool). Improvement ideas are
            # captured via capture_suggestions, not by editing files.
            cmd.extend(['--disallowedTools', *DISALLOWED_TOOLS])
            # Per-console MCP scoping: the in-Flame console only needs Flame +
            # ShotGrid (fpt), not Maya's tool schemas. Load only those via strict
            # config so Maya's tools never enter the request.
            _scoped_mcp = build_scoped_mcp_config(
                os.path.join(cwd, '.mcp.json'), {'flame', 'fpt-mcp'})
            if _scoped_mcp:
                cmd.extend(['--strict-mcp-config', '--mcp-config', _scoped_mcp])
            # The prompt goes through STDIN, never argv (Chat 91): --mcp-config
            # is VARIADIC, so a positional prompt right after it is swallowed as
            # another config path and the CLI aborts with "Input must be
            # provided either through stdin or as a prompt argument when using
            # --print". stdin is also immune to dash-prefixed messages.

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd if os.path.isdir(cwd) else None,
                bufsize=1,
            )

            # Feed the prompt and close stdin so the CLI knows input is done.
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except Exception:
                pass

            # Drain stderr in background thread to prevent pipe deadlock
            stderr_lines = []
            def _read_stderr():
                try:
                    for line in proc.stderr:
                        stderr_lines.append(line)
                except Exception:
                    pass
            stderr_t = threading.Thread(target=_read_stderr, daemon=True)
            stderr_t.start()

            # Watchdog — kill process after timeout.
            # ollama       (LAN GPU): 600 s — first load of a 30B model can take minutes
            # ollama_cloud (Mac→☁):   300 s — 480B inference on ollama.com
            # ollama_mac   (Mac CPU): 240 s — small 7B model, slower without GPU
            # anthropic:              180 s
            if self._backend == "ollama":
                _watchdog_secs = 600
            elif self._backend == "ollama_cloud":
                _watchdog_secs = 300
            elif self._backend == "ollama_mac":
                _watchdog_secs = 240
            else:
                _watchdog_secs = 180
            _turn_watchdog = _watchdog_secs  # F0: snapshot for turn-record
            _timed_out = [False]
            def _kill():
                _timed_out[0] = True
                try:
                    proc.kill()
                except Exception:
                    pass
            watchdog = threading.Timer(_watchdog_secs, _kill)
            watchdog.start()

            assistant_parts = []    # text blocks from assistant messages
            tool_summaries  = []    # extracted stats footers from tool results
            self._last_exec_count = 0  # reset counter for this turn

            try:
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    self._handle_stream_event(event, assistant_parts, tool_summaries)
            finally:
                watchdog.cancel()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()
                stderr_t.join(timeout=5)
                # F0: snapshot fields for the turn-record now that the
                # subprocess has fully drained and stderr is complete.
                _turn_exit_code = proc.returncode
                _turn_timed_out = _timed_out[0]
                _turn_stderr_lines = list(stderr_lines)

            if _timed_out[0]:
                raise RuntimeError(
                    f"Request timed out ({_watchdog_secs} s). "
                    "Try a simpler request, or check that the Ollama server "
                    "is not overloaded (nvidia-smi on the Linux machine)."
                )

            # ── Rate-limit detection ──────────────────────────────────────────
            # Look for 429 / "rate limit" / "quota" in stderr output
            _RL_KW = ('rate limit', 'rate_limit', '429',
                      'too many requests', 'quota exceeded', 'overloaded')
            stderr_text = ''.join(stderr_lines).lower()
            if any(k in stderr_text for k in _RL_KW):
                self._rate_limited = True
            else:
                self._rate_limited = False

            if not assistant_parts and proc.returncode != 0:
                err = self._strip_ansi(''.join(stderr_lines).strip())
                # A --resume against a session the CLI can no longer find (its
                # transcript was pruned, or Flame outlived the retention
                # window) aborts before producing anything. Drop the id so the
                # NEXT send starts a fresh conversation instead of failing
                # forever, and say so — silently losing the thread mid-conform
                # would be worse than the error.
                if self._session_id and 'session' in err.lower():
                    _log(f"Chat: resume failed for session {self._session_id} — starting fresh")
                    self._session_id = None
                    raise RuntimeError(
                        "The previous conversation could no longer be resumed, "
                        "so it has been dropped. Send your message again — it "
                        "will start a new conversation, and this one keeps "
                        "its context from here on.\n\n" + err
                    )
                raise RuntimeError(err or f"Claude exited with code {proc.returncode}")

            # ── Display main assistant response ──────────────────────────────
            response = self._strip_ansi('\n\n'.join(assistant_parts).strip())
            # Read-only bridge: log any @@SUGGESTION@@ lines to the backlog and
            # strip the markers from what the user sees.
            response, _ = capture_suggestions(
                response, os.path.join(_PROJECT_ROOT, 'CONSOLE_IMPROVEMENTS.md'))
            if response:
                # REC-002: log first 200 chars of assistant response for QA audit
                _log(f"RESPONSE: {response[:200].replace(chr(10), ' ')!r}")
                self._messages.append({"role": "assistant", "content": response})
                self._ui_queue.append(
                    lambda r=response: self._append_bubble("assistant", r))
            elif not tool_summaries:
                err = self._strip_ansi(''.join(stderr_lines).strip())
                if err:
                    raise RuntimeError(err)

            # ── Display tool stats / learn_pattern confirmations ─────────────
            learn_msgs    = [s for s in tool_summaries if '✅ Pattern' in s or
                             ('🧠' in s and '📊' not in s)]
            stats_footers = [s for s in tool_summaries if s not in learn_msgs]

            for raw in learn_msgs:
                clean = self._strip_ansi(raw.strip())
                if clean:
                    self._ui_queue.append(
                        lambda s=clean: self._append_bubble("tool", s))

            if stats_footers:
                last = self._strip_ansi(stats_footers[-1].strip())
                if last:
                    self._ui_queue.append(
                        lambda s=last: self._append_bubble("tool", s))

            # ── Undo hint — show how many Flame actions were made ─────────────
            n = self._last_exec_count
            if n > 0:
                hint = f"↩  {n} action{'s' if n > 1 else ''} in Flame · type /undo {n} to revert"
                self._ui_queue.append(
                    lambda h=hint: self._append_bubble("tool", h))

        except Exception as e:
            err = str(e)
            _turn_error_msg = err
            self._ui_queue.append(lambda e=err: self._append_bubble("error", e))
        finally:
            self._ui_queue.append(lambda: self._set_busy(False))
            # F0: best-effort turn-record. Written from the outer finally so
            # the row is produced even on early-exception paths (claude not
            # found, ollama unreachable, build_prompt failure). All I/O
            # errors are swallowed — telemetry must never crash the panel.
            try:
                _turn_path = os.path.join(_PROJECT_ROOT, 'logs', 'turns.jsonl')
                os.makedirs(os.path.dirname(_turn_path), exist_ok=True)
                # Size-cap rotation (~5 MB ≈ 10k typical entries).
                try:
                    if os.path.getsize(_turn_path) >= 5 * 1024 * 1024:
                        _rot = _turn_path + ".1"
                        if os.path.exists(_rot):
                            os.unlink(_rot)
                        os.rename(_turn_path, _rot)
                except FileNotFoundError:
                    pass
                _record = {
                    "ts":             datetime.datetime.now().isoformat(timespec='seconds'),
                    "model":          getattr(self, '_model', 'unknown'),
                    "backend":        getattr(self, '_backend', 'unknown'),
                    "watchdog_secs":  _turn_watchdog,
                    "exit_code":      _turn_exit_code,
                    "timed_out":      _turn_timed_out,
                    "prompt_chars":   len(_turn_prompt),
                    "stderr_lines":   len(_turn_stderr_lines),
                    "duration_ms":    round((time.monotonic() - _t0_turn) * 1000),
                    "error":          bool(_turn_error_msg),
                    "error_msg":      (_turn_error_msg or '')[:200],
                }
                with open(_turn_path, 'a', encoding='utf-8') as _fh:
                    _fh.write(json.dumps(_record, ensure_ascii=False, default=str) + "\n")
            except (OSError, TypeError, ValueError):
                pass

    def _handle_stream_event(self, event, assistant_parts, tool_summaries):
        """
        Process one parsed JSON event from 'claude -p --output-format stream-json'.

        Event types we care about:
          assistant  → content blocks: text (response) or tool_use (show status)
          user       → tool_result blocks: extract stats footers
          result     → fallback: use result.result if no assistant text collected

        Every event carries the CLI's session_id at the top level; capturing it
        is what lets the NEXT turn pass --resume and continue the same
        conversation instead of starting from zero (Chat 98).
        """
        sid = event.get('session_id')
        if sid and sid != self._session_id:
            self._session_id = sid

        etype = event.get('type', '')

        if etype == 'assistant':
            for block in event.get('message', {}).get('content', []):
                btype = block.get('type', '')
                if btype == 'text':
                    text = block.get('text', '').strip()
                    # Strip thinking blocks emitted by reasoning models (Qwen3,
                    # DeepSeek-R1, etc.).  These often contain raw <function=…>
                    # syntax that must NOT be shown as plain chat text.
                    # We remove both complete blocks and any unclosed opening
                    # tags so the user never sees internal reasoning output.
                    import re as _re
                    text = _re.sub(r'<think>.*?</think>', '', text,
                                   flags=_re.DOTALL).strip()
                    # Catch any unclosed <think> at end of partial stream chunks
                    text = _re.sub(r'<think>.*$', '', text,
                                   flags=_re.DOTALL).strip()
                    if text:
                        assistant_parts.append(text)
                elif btype == 'tool_use':
                    # Live status update while tool executes
                    name = block.get('name', '')
                    if name == 'execute_python':
                        self._last_exec_count += 1
                    _TOOL_STATUS = {
                        'search_flame_docs': "🔍  Searching docs…",
                        'execute_python':    "⚡  Executing in Flame…",
                        'learn_pattern':     "🧠  Learning pattern…",
                        'session_stats':     "📊  Getting session stats…",
                        'list_libraries':    "📚  Listing libraries…",
                        'list_reels':        "🎞️   Listing reels…",
                        'get_project_info':  "🎬  Getting project info…",
                        'get_flame_version': "🔥  Getting Flame version…",
                    }
                    status = _TOOL_STATUS.get(name, f"⚙️   Running {name}…")
                    self._ui_queue.append(lambda s=status: (
                        self._status.setStyleSheet(self._STYLE_BUSY),
                        self._status.setText(s),
                    ))

        elif etype == 'user':
            for block in event.get('message', {}).get('content', []):
                if block.get('type') != 'tool_result':
                    continue
                tc = block.get('content', '')
                if isinstance(tc, list):
                    full_text = '\n'.join(
                        item.get('text', '') for item in tc
                        if isinstance(item, dict) and item.get('type') == 'text'
                    )
                else:
                    # Some Claude Code versions deliver tool_result content as a
                    # JSON-encoded string still inside its JSON envelope, e.g.:
                    #   "actual text\"}"   ← closing quote+brace leak from stream
                    # Try to decode it; fall back to raw string if not valid JSON.
                    raw = str(tc)
                    try:
                        parsed = json.loads(raw)
                        full_text = parsed if isinstance(parsed, str) else raw
                    except (json.JSONDecodeError, ValueError):
                        full_text = raw
                # ── Flame C++ corruption warning ──────────────────────────────
                if 'possibly_corrupted' in full_text or 'unordered_map::at' in full_text:
                    warn = ("⚠️  Internal Flame C++ exception detected.\n"
                            "The interface may be corrupted.\n"
                            "If you see broken panels or curved lines → restart Flame.")
                    self._ui_queue.append(lambda w=warn: self._append_bubble("error", w))

                footer = self._extract_stats_footer(full_text)
                if footer:
                    tool_summaries.append(footer)

        elif etype == 'result':
            # ── Token accounting ──────────────────────────────────────────────
            # The result event carries usage counts (may be top-level or nested
            # under a 'usage' key depending on Claude Code version).
            usage   = event.get('usage') or {}
            in_tok  = usage.get('input_tokens',  event.get('input_tokens',  0)) or 0
            out_tok = usage.get('output_tokens', event.get('output_tokens', 0)) or 0
            if in_tok or out_tok:
                self._session_tokens += in_tok + out_tok
            # Per-call usage to the shared cross-console log for objective
            # monitoring (best-effort; no-op if usage is empty).
            log_usage(usage, 'flame')

            # ── Rate-limit detection in result event ──────────────────────────
            if event.get('is_error') or event.get('subtype') == 'error_during_execution':
                err_text = (event.get('error', '') or event.get('result', '')).lower()
                _RL_KW = ('rate limit', 'rate_limit', '429',
                          'too many requests', 'quota exceeded')
                if any(k in err_text for k in _RL_KW):
                    self._rate_limited = True

            # ── Fallback: if Claude produced no text blocks, use result summary
            if not assistant_parts:
                r = event.get('result', '').strip()
                if r:
                    assistant_parts.append(r)

    @staticmethod
    def _extract_stats_footer(text):
        """
        Extract the ─────… stats block from a tool result string.
        The MCP server appends this footer to every tool response.

        Some MCP / Claude Code versions deliver tool_result content with
        literal '\\n' (two chars) instead of real newlines — unescape first.

        Returns the footer string, or '' if none found.
        """
        # Unescape literal \\n that some pipeline stages leave in the text
        text = text.replace('\\n', '\n')
        # Strip trailing JSON envelope leak: closing quote+brace from stream parser
        # e.g. '...search_flame_docs"}' → '...search_flame_docs'
        # None of our tool outputs legitimately end with "}
        while text.endswith('"}'):
            text = text[:-2].rstrip()

        STATS_MARKERS = ('🔍', '📊', '🧠', '✅ Pattern', '─────')
        if not any(m in text for m in STATS_MARKERS):
            return ''
        sep = '─' * 5
        if sep in text:
            idx = text.index(sep)
            return text[idx:].strip()
        # No separator — return whole thing if it contains stats emoji
        return text.strip()

    # ── Model config ──────────────────────────────────────────────────────────

    def _load_model_config(self) -> tuple:
        """
        Load persisted model, backend, Ollama server URL, and cloud key.

        Delegates to `flame_mcp._config.load_model_config` when the shared
        helper is importable (repo on disk / src/ reachable). Falls back
        to an inline implementation if the helper is unavailable — keeps
        the bridge functional on Flame hosts that were deployed without
        the repo (e.g. a bare `cp` of this file to
        `/opt/Autodesk/shared/python/` without FLAME_MCP_ROOT set).

        config.json keys:
          model            – model_id string
          backend          – "anthropic" | "ollama" | "ollama_cloud"
                             ("ollama_local" accepted for backward compat → treated as "ollama")
          ollama_url       – base URL of the Ollama server, e.g. "http://192.168.1.50:11434"
                             Set this to the IP of your Linux workstation running Ollama.
          ollama_cloud_key – API key from ollama.com (only needed for ollama_cloud backend)
        """
        if _shared_load_model_config is not None:
            return _shared_load_model_config(
                MODEL_CONFIG_FILE,
                default_model=DEFAULT_MODEL,
                default_backend=DEFAULT_BACKEND,
                default_ollama_url=DEFAULT_OLLAMA_URL,
            )
        # Fallback: inline logic (kept in lock-step with _config.py).
        try:
            with open(MODEL_CONFIG_FILE) as f:
                cfg = json.load(f)
            model      = cfg.get('model',            DEFAULT_MODEL)
            backend    = cfg.get('backend',          DEFAULT_BACKEND)
            if backend == 'ollama_local':
                backend = 'ollama'
            ollama_url = cfg.get('ollama_url',       DEFAULT_OLLAMA_URL)
            cloud_key  = cfg.get('ollama_cloud_key', '')
            return model, backend, ollama_url, cloud_key
        except Exception:
            return DEFAULT_MODEL, DEFAULT_BACKEND, DEFAULT_OLLAMA_URL, ''

    def _save_model_config(self, model_id: str, backend: str) -> None:
        """Persist model + backend to config.json, preserving all other keys."""
        try:
            cfg = {}
            if os.path.exists(MODEL_CONFIG_FILE):
                try:
                    with open(MODEL_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    _log("Model config: malformed config.json — starting fresh")
                    cfg = {}   # don't propagate parse errors; write a clean file
            cfg['model']   = model_id
            cfg['backend'] = backend
            # Ensure ollama_url exists in config even if not yet set
            if 'ollama_url' not in cfg:
                cfg['ollama_url'] = DEFAULT_OLLAMA_URL
            os.makedirs(os.path.dirname(MODEL_CONFIG_FILE), exist_ok=True)
            with open(MODEL_CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            _log(f"Model config save error: {e}")

    def _load_effort_config(self) -> str:
        """Read the persisted effort level from config.json (default auto)."""
        try:
            if os.path.exists(MODEL_CONFIG_FILE):
                with open(MODEL_CONFIG_FILE) as f:
                    cfg = json.load(f)
                val = cfg.get("effort", DEFAULT_EFFORT)
                if any(val == e[1] for e in AVAILABLE_EFFORTS):
                    return val
        except Exception as e:
            _log(f"Effort config load error: {e}")
        return DEFAULT_EFFORT

    def _save_effort_config(self, effort: str) -> None:
        """Persist effort to config.json, preserving all other keys."""
        try:
            cfg = {}
            if os.path.exists(MODEL_CONFIG_FILE):
                try:
                    with open(MODEL_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    cfg = {}
            cfg["effort"] = effort
            os.makedirs(os.path.dirname(MODEL_CONFIG_FILE), exist_ok=True)
            with open(MODEL_CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            _log(f"Effort config save error: {e}")

    def _on_model_changed(self, index: int) -> None:
        """Called when the user picks a different model in the combo."""
        label, model_id, backend = AVAILABLE_MODELS[index]
        self._model   = model_id
        self._backend = backend
        self._save_model_config(model_id, backend)
        # URL widget only needed for LAN Ollama (gpu-server) — cloud/mac use localhost
        self._ollama_url_widget.setVisible(backend == "ollama")
        # Cloud key widget hidden — Ollama Mac daemon handles cloud auth internally
        self._ollama_cloud_key_widget.setVisible(False)
        if backend == "ollama":
            suffix = f" · {self._ollama_url}"
        elif backend == "ollama_cloud":
            suffix = " · localhost → ☁ ollama.com"
        elif backend == "ollama_mac":
            suffix = " · localhost (offline)"
        else:
            suffix = ""
        display = f"{label}{suffix}" if model_id else f"{label} (set model in config.json)"
        self._ui_queue.append(
            lambda d=display: self._append_bubble("tool", f"⚙️  Model → {d}"))
        if backend == "ollama_mac":
            self._ui_queue.append(lambda: self._append_bubble(
                "warn",
                "⚠️  Modelo offline (7B): capacidad de tool use limitada.\n"
                "Puede imprimir JSON en lugar de ejecutar herramientas.\n"
                "Recomendado solo para consultas de texto. Usa anthropic u ollama para controlar Flame."))
        _log(f"Model changed to: {model_id or 'default'} (backend={backend})")

    def _on_effort_changed(self, index: int) -> None:
        """Called when the user picks a different effort level."""
        _, effort_value = AVAILABLE_EFFORTS[index]
        self._effort = effort_value
        self._save_effort_config(effort_value)
        _log(f"Effort changed to: {effort_value}")

    def _on_ollama_url_changed(self) -> None:
        """Called when the user edits the Ollama server URL field and presses Enter."""
        url = self._ollama_input.text().strip().rstrip('/')
        if not url:
            return
        # Normalise: add http:// if missing
        if not url.startswith('http'):
            url = 'http://' + url
        self._ollama_url = url
        self._ollama_input.setText(url)
        # Persist to config.json (fail-safe read)
        try:
            cfg = {}
            if os.path.exists(MODEL_CONFIG_FILE):
                try:
                    with open(MODEL_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    cfg = {}
            cfg['ollama_url'] = url
            os.makedirs(os.path.dirname(MODEL_CONFIG_FILE), exist_ok=True)
            with open(MODEL_CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            _log(f"Ollama URL save error: {e}")
        self._update_combo_labels()
        self._ui_queue.append(
            lambda u=url: self._append_bubble("tool", f"⚙️  Ollama server → {u}"))
        _log(f"Ollama URL set to: {url}")

    def _on_ollama_cloud_key_changed(self) -> None:
        """Called when the user edits the Ollama cloud API key field and presses Enter."""
        key = self._ollama_cloud_key_input.text().strip()
        if not key:
            return
        self._ollama_cloud_key = key
        # Persist to config.json (fail-safe read)
        try:
            cfg = {}
            if os.path.exists(MODEL_CONFIG_FILE):
                try:
                    with open(MODEL_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    cfg = {}
            cfg['ollama_cloud_key'] = key
            os.makedirs(os.path.dirname(MODEL_CONFIG_FILE), exist_ok=True)
            with open(MODEL_CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            _log(f"Ollama cloud key save error: {e}")
        self._update_combo_labels()
        self._ui_queue.append(
            lambda: self._append_bubble("tool", "⚙️  Ollama cloud key saved ✓"))
        _log("Ollama cloud key updated")

    def _update_combo_labels(self) -> None:
        """
        Update combo box item text to show the currently-configured
        server hostname (ollama backend) or masked API key (ollama_cloud).

        Examples:
          "qwen3-coder 30B"       → "qwen3-coder 30B  · gpu-server"
          "qwen3-coder 480B ☁"   → "qwen3-coder 480B ☁  · ollama_ab…"
        Called at startup and whenever the URL or cloud key changes.
        """
        try:
            from urllib.parse import urlparse as _urlparse
            parsed = _urlparse(self._ollama_url)
            host = parsed.hostname or self._ollama_url
        except Exception:
            host = self._ollama_url

        key = self._ollama_cloud_key
        if key:
            masked = key[:8] + "…" if len(key) > 8 else key[:4] + "…"
        else:
            masked = None

        for i, (label, _model_id, backend) in enumerate(AVAILABLE_MODELS):
            if backend == "ollama":
                new_label = f"{label}  · {host}"
            elif backend == "ollama_cloud":
                new_label = f"{label}  · localhost → ☁"
            elif backend == "ollama_mac":
                new_label = f"{label}  · localhost"
            else:
                new_label = label
            self._model_combo.setItemText(i, new_label)

    # ── Ollama helpers ────────────────────────────────────────────────────────

    def _check_ollama(self, url: str = None) -> bool:
        """
        Return True if an Ollama server is reachable at the given URL.
        Defaults to self._ollama_url (LAN server).
        Pass OLLAMA_MAC_URL to check the Mac-local daemon.
        """
        target = url or self._ollama_url
        try:
            import urllib.request
            urllib.request.urlopen(f"{target}/api/version", timeout=2)
            return True
        except Exception:
            return False

    def _preload_ollama_model(self, url: str = None, num_ctx: int = None) -> None:
        """
        Pre-load the Ollama model with the correct num_ctx via the native API.

        Ollama's Anthropic-compatible endpoint (/v1/messages) does not honour
        the num_ctx set in a model's Modelfile — it always falls back to the
        global default of 4096 tokens.  The native /api/generate endpoint DOES
        respect options.num_ctx.  By making an empty-prompt request there first,
        we load (or reload) the model's runner with num_ctx tokens.
        Ollama will then reuse that runner for the subsequent Anthropic-API call
        made by the claude CLI subprocess.

        Parameters default to LAN-server values (`self._ollama_url`, OLLAMA_NUM_CTX).
        Called with OLLAMA_MAC_URL + OLLAMA_MAC_NUM_CTX from the ollama_mac branch.

        Safe to call even if the model is already loaded — Ollama is a no-op
        if num_ctx matches the current runner.

        F1b: keep_alive defaults to 30m (was 10m). 10m unloads the runner
        when the user spends >10 min reading a long response or thinking
        about the next prompt, forcing a full cold-load on the next turn
        (5–30 s of latency the user blames on "the model is slow"). 30 m
        covers normal-paced conversations end-to-end with one preflight
        per turn refreshing the timer. Override via
        `config.json -> ollama_keep_alive` (Ollama parses durations like
        "30m", "1h", "24h", or pass an int for seconds).
        """
        import urllib.request as _urllib_req
        import json as _json

        target_url = url or self._ollama_url
        target_ctx = num_ctx if num_ctx is not None else OLLAMA_NUM_CTX
        # F1b: keep_alive defaults to 30 m. Override via
        # `config.json -> ollama_keep_alive`. Reading is delegated to
        # flame_mcp._config.resolve_keep_alive when available (single
        # source of truth, unit-tested) with an inline fallback for
        # bridges installed without the repo on disk.
        if _shared_resolve_keep_alive is not None:
            keep_alive_cfg = _shared_resolve_keep_alive(MODEL_CONFIG_FILE)
        else:
            keep_alive_cfg = "30m"
            try:
                with open(MODEL_CONFIG_FILE, "r") as _cfg_fh:
                    _cfg = _json.loads(_cfg_fh.read() or "{}")
                _ka = _cfg.get("ollama_keep_alive", "30m")
                if isinstance(_ka, (str, int)) and not isinstance(_ka, bool):
                    keep_alive_cfg = _ka
            except (FileNotFoundError, OSError, ValueError):
                pass

        payload = _json.dumps({
            "model":      self._model,
            "prompt":     "",          # empty — we only want to load the runner
            "options":    {"num_ctx": target_ctx, "temperature": 0},  # C1: deterministic code gen
            "keep_alive": keep_alive_cfg,
            "stream":     False,
        }).encode()

        api_url = f"{target_url}/api/generate"
        req = _urllib_req.Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with _urllib_req.urlopen(req, timeout=120) as resp:
                resp.read()
            _log(f"Ollama pre-load OK: {self._model} num_ctx={target_ctx} url={target_url}")
        except Exception as exc:
            # Non-fatal — log and continue; the main call may still work
            _log(f"Ollama pre-load warning (non-fatal): {exc}")

    def _get_ollama_env(self, base_env: dict) -> dict:
        """
        Return a copy of base_env with Anthropic API vars pointed at Ollama.

        Ollama implements the Anthropic Messages API natively (v0.14+), so
        Claude Code on macOS can talk directly to any Ollama server on the LAN —
        no proxy required.

        Self-hosted:  ANTHROPIC_BASE_URL = config.json → ollama_url  (e.g. gpu-server)
                      ANTHROPIC_API_KEY  = "ollama"  (arbitrary, Ollama ignores it)
        Cloud ☁:      ANTHROPIC_BASE_URL = http://localhost:11434  (Mac Ollama daemon)
                      Model tag = qwen3-coder:480b-cloud  (daemon proxies to ollama.com)
                      Requires: brew install ollama && ollama serve on the Mac
        Mac offline:  ANTHROPIC_BASE_URL = http://localhost:11434  (Mac Ollama daemon)
                      Model = small local model, no internet needed
        """
        env = base_env.copy()
        if self._backend == "ollama":
            env['ANTHROPIC_BASE_URL']   = self._ollama_url
            env['ANTHROPIC_API_KEY']    = 'ollama'
            env['ANTHROPIC_AUTH_TOKEN'] = 'ollama'
            _log(f"Ollama LAN backend: {self._ollama_url} / model={self._model}")
        elif self._backend in ("ollama_cloud", "ollama_mac"):
            # Both cloud-proxy and mac-local models run through the Mac's own
            # Ollama daemon at localhost:11434.
            # ollama_cloud: model tag ends in -cloud → daemon forwards to ollama.com
            # ollama_mac:   model is stored locally on the Mac → works offline
            env['ANTHROPIC_BASE_URL']   = OLLAMA_MAC_URL
            env['ANTHROPIC_API_KEY']    = 'ollama'
            env['ANTHROPIC_AUTH_TOKEN'] = 'ollama'
            _log(f"Ollama Mac backend ({self._backend}): {OLLAMA_MAC_URL} / model={self._model}")
        return env

    # ── Claude Code subprocess helpers ────────────────────────────────────────

    @staticmethod
    def _find_claude():
        """
        Locate the 'claude' CLI and return (path, env).

        Strategy:
        1. Search common npm/nvm/volta install paths directly.
        2. If not found, ask the user's login shell ('which claude') — this
           sources ~/.zprofile / ~/.bash_profile so nvm, fnm, volta etc. are
           resolved correctly even when Flame's process has a stripped PATH.
        """
        import shutil

        # ── 0. Explicit override via CLAUDE_PATH env var or .env ─────────
        explicit = os.environ.get('CLAUDE_PATH', '')
        if not explicit:
            for candidate in [os.path.join(_PROJECT_ROOT, '.env'), '~/flame-mcp/.env']:
                p = os.path.expanduser(candidate)
                if os.path.exists(p):
                    with open(p) as f:
                        for line in f:
                            if line.startswith('CLAUDE_PATH='):
                                explicit = line.split('=', 1)[1].strip().strip('"\'')
        if explicit and os.path.isfile(explicit):
            _log(f"Chat: using CLAUDE_PATH override: {explicit}")
            return explicit, dict(os.environ)

        # ── 1. Candidate paths ────────────────────────────────────────────
        extra = [
            '/usr/local/bin',
            '/usr/bin',
            '/opt/homebrew/bin',
            os.path.expanduser('~/.npm-global/bin'),
            os.path.expanduser('~/Library/pnpm'),
            os.path.expanduser('~/.volta/bin'),
            os.path.expanduser('~/.fnm/aliases/default/bin'),
        ]
        nvm_base = os.path.expanduser('~/.nvm/versions/node')
        if os.path.isdir(nvm_base):
            for ver in sorted(os.listdir(nvm_base), reverse=True):
                extra.append(os.path.join(nvm_base, ver, 'bin'))

        env = dict(os.environ)
        env['PATH'] = ':'.join(extra + [env.get('PATH', '')])
        found = shutil.which('claude', path=env['PATH'])
        if found:
            return found, env

        # ── 2. Ask the login shell ────────────────────────────────────────
        # Uses '-l' (login) so it sources ~/.zprofile / ~/.bash_profile
        # WITHOUT '-i' (interactive) to avoid oh-my-zsh update prompts.
        shell = os.environ.get('SHELL', '/bin/zsh')
        try:
            result = subprocess.run(
                [shell, '-l', '-c', 'which claude'],
                capture_output=True, text=True, timeout=10
            )
            path = result.stdout.strip()
            if path and os.path.isfile(path):
                _log(f"Chat: found claude via login shell at {path}")
                return path, env
        except Exception as e:
            _log(f"Chat: login-shell which failed: {e}")

        # ── 3. Ask npm directly ────────────────────────────────────────────
        try:
            result = subprocess.run(
                [shell, '-l', '-c', 'npm config get prefix'],
                capture_output=True, text=True, timeout=10
            )
            prefix = result.stdout.strip()
            candidate = os.path.join(prefix, 'bin', 'claude')
            if prefix and os.path.isfile(candidate):
                _log(f"Chat: found claude via npm prefix at {candidate}")
                return candidate, env
        except Exception as e:
            _log(f"Chat: npm prefix lookup failed: {e}")

        return None, env

    def _build_prompt(self):
        """
        Build the prompt for 'claude -p'.

        With a live CLI session (--resume, Chat 98) the conversation is already
        in the child's context, so the message goes through alone: re-injecting
        the digest would duplicate it, and a truncated copy of what the model
        already remembers is worse than nothing.

        The digest below is the FALLBACK for the first turn of a session and
        for any turn after a resume failure. It carries the last 4 messages
        truncated to 500 chars — enough for a follow-up question, never enough
        for a multi-step workflow (that gap is what --resume fixes).
        """
        history = self._messages[:-1]   # everything except the latest user message
        user_msg = self._messages[-1]['content']

        if self._session_id or not history:
            return user_msg

        # Include last 4 messages (2 exchanges) as context
        context_lines = ["<recent_conversation>"]
        for msg in history[-4:]:
            role = "User" if msg['role'] == 'user' else "Assistant"
            content = msg['content']
            if len(content) > 500:
                content = content[:500] + "…"
            context_lines.append(f"{role}: {content}")
        context_lines.append("</recent_conversation>")
        context_lines.append(f"\n{user_msg}")
        return "\n".join(context_lines)

    @staticmethod
    def _strip_ansi(text):
        """Remove ANSI escape codes from Claude Code terminal output."""
        import re
        return re.sub(r'\x1b\[[0-9;]*[mGKHF]|\x1b\][^\x07]*(\x07|\x1b\\)', '', text)

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _flush_ui_queue(self):
        """Drain UI callbacks queued by background threads. Called by QTimer (main thread)."""
        while self._ui_queue:
            try:
                self._ui_queue.pop(0)()
            except Exception:
                pass

    def _append_bubble(self, role, content):
        colors = {
            "user":      ("#cccccc", "You"),
            "assistant": ("#34d399", "Claude"),
            "tool":      ("#cccccc", ""),
            "warn":      ("#ffff00", ""),
            "error":     ("#f87171", "Error"),
        }
        color, label = colors.get(role, ("#aaa", ""))
        escaped = (content
                   .replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('\n', '<br>'))
        if label:
            html = (f'<p><b style="color:{color};">{label}:</b> '
                    f'<span style="color:#ddd;">{escaped}</span></p>')
        else:
            html = f'<p style="color:{color};margin-left:12px;">{escaped}</p>'
        self._chat.append(html)
        sb = self._chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Token warning thresholds ──────────────────────────────────────────────
    _TOKEN_WARN   = 100_000   # 🟡 caution — approach rate-limit territory
    _TOKEN_DANGER = 200_000   # 🔴 high — risk of hitting daily/minute limits

    # ── Status-bar styles ─────────────────────────────────────────────────────
    _STYLE_IDLE   = "color:#555;font-size:12px;padding:2px 4px;"
    _STYLE_BUSY   = ("color:#ffff00;font-size:13px;font-weight:bold;"
                     "padding:2px 4px;")
    _STYLE_WARN   = "color:#ffff00;font-size:12px;padding:2px 4px;"
    _STYLE_DANGER = ("color:#ef4444;font-size:12px;font-weight:bold;"
                     "padding:2px 4px;")

    def _idle_status_text(self):
        """Return the status bar text (and style) for the idle state."""
        if self._rate_limited:
            return (self._STYLE_DANGER,
                    "⏱️ Rate limit alcanzado — espera antes del siguiente envío")
        tok = self._session_tokens
        # Token warnings only make sense for Anthropic (rate limits / cost).
        # For self-hosted or cloud Ollama there is no per-token cost or strict
        # rate limit, so we skip the danger/warn levels entirely.
        if self._backend == "anthropic":
            if tok >= self._TOKEN_DANGER:
                return (self._STYLE_DANGER,
                        f"🔴 {tok // 1000}k tokens this session — consider restarting the chat")
            if tok >= self._TOKEN_WARN:
                return (self._STYLE_WARN,
                        f"⚠️ {tok // 1000}k tokens this session · Ctrl+Return to send")
        if tok >= 1000:
            return (self._STYLE_IDLE,
                    f"Ready · {tok // 1000}k tokens  ·  Ctrl+Return to send")
        return (self._STYLE_IDLE, "Ready  ·  Ctrl+Return to send")

    def _set_busy(self, busy):
        self._busy = busy
        self._send_btn.setEnabled(not busy)
        if busy:
            self._status.setStyleSheet(self._STYLE_BUSY)
        else:
            style, text = self._idle_status_text()
            self._status.setStyleSheet(style)
            self._status.setText(text)


def _show_connection_test(selection):
    """Test the bridge connection and show result — Qt with macOS fallback."""
    status_str = "ACTIVE" if _bridge_active else "INACTIVE"
    _log(f"Connection test: bridge is {status_str}")

    if _bridge_active:
        title = "MCP Bridge — Connected"
        msg = (f"Bridge is ACTIVE\n"
               f"Listening on {BRIDGE_HOST}:{BRIDGE_PORT}\n\n"
               f"Ready to receive commands from Claude.")
    else:
        title = "MCP Bridge — Not Connected"
        msg = ("Bridge is INACTIVE\n\n"
               "Use 'Start bridge' to activate it,\n"
               "or restart Flame to load it automatically.")

    # Try Qt first
    try:
        QtWidgets, QtCore, _ = _import_qt()
        if QtWidgets is None:
            raise ImportError("Qt not available")
        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication.instance() is None")

        box = QtWidgets.QMessageBox()
        box.setWindowTitle(title)
        box.setText(msg)
        box.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.WindowStaysOnTopHint)
        box.setIcon(
            QtWidgets.QMessageBox.Information if _bridge_active
            else QtWidgets.QMessageBox.Warning
        )
        _open_dialogs.append(box)
        box.finished.connect(lambda: _open_dialogs.remove(box) if box in _open_dialogs else None)
        box.show()
        box.raise_()
        box.activateWindow()
        _log("Connection test: Qt dialog shown")

    except Exception as e:
        # Fallback: native macOS alert (always works regardless of Qt)
        _log(f"Connection test: Qt failed ({e}), using osascript fallback")
        _osascript_alert(title, msg)


def _osascript_alert(title, message):
    """Show a native macOS alert dialog via osascript (no Qt required)."""
    try:
        safe_msg = message.replace('"', '\\"').replace('\n', '\\n')
        safe_title = title.replace('"', '\\"')
        subprocess.Popen([
            'osascript', '-e',
            f'display dialog "{safe_msg}" with title "{safe_title}" buttons {{"OK"}} default button "OK"'
        ])
    except Exception as e:
        _log(f"osascript fallback also failed: {e}")


# ── Flame main menu ───────────────────────────────────────────────────────────

def get_main_menu_custom_ui_actions():
    """
    Registers an 'MCP Bridge' submenu in Flame's main menu bar.
    Shows bridge status and provides controls + Quick Console.
    """
    status = "● Active" if _bridge_active else "○ Inactive"

    return [
        {
            "name": f"MCP Bridge  [{status}]",
            "actions": [
                {
                    "name": f"Status: {status} — port {BRIDGE_PORT}",
                    "execute": _action_status,
                },
                {
                    "name": "Start bridge",
                    "execute": _action_start,
                },
                {
                    "name": "Stop bridge",
                    "execute": _action_stop,
                },
                {
                    "name": "Restart bridge",
                    "execute": _action_restart,
                },
                {
                    "name": "Claude Chat  (embedded)",
                    "execute": _action_open_chat,
                },
                {
                    "name": "Launch Claude (terminal)...",
                    "execute": _action_launch_claude,
                },
                {
                    "name": "Reload hook",
                    "execute": _action_reload_hook,
                },
                {
                    "name": "Connection test",
                    "execute": _show_connection_test,
                },
                {
                    "name": "View bridge log...",
                    "execute": _action_view_log,
                },
                {
                    "name": "View RAG log...",
                    "execute": _action_view_rag_log,
                },
            ],
        }
    ]


# ── Menu actions ──────────────────────────────────────────────────────────────

def _action_status(selection):
    status = "ACTIVE" if _bridge_active else "INACTIVE"
    print(f"[FlameMCPBridge] Status: {status} — {BRIDGE_HOST}:{BRIDGE_PORT}")


def _action_start(selection):
    _start_bridge()


def _action_stop(selection):
    _stop_bridge()


def _action_restart(selection):
    _stop_bridge()
    time.sleep(0.5)
    _start_bridge()


def _action_reload_hook(selection):
    """Reload this module without restarting Flame."""
    import importlib

    module_name = None
    for name, mod in sys.modules.items():
        try:
            if hasattr(mod, '__file__') and mod.__file__ and 'flame_mcp_bridge' in mod.__file__:
                module_name = name
                break
        except Exception:
            pass

    if module_name is None:
        _log("Reload: module not found in sys.modules")
        _osascript_alert("MCP Bridge — Reload", "Module not found in sys.modules.\nSee log for details.")
        return

    try:
        _log(f"Reload: reloading '{module_name}'")
        _stop_bridge()
        importlib.reload(sys.modules[module_name])
        # start_bridge is called by the reloaded module's globals,
        # but since we're in the old frame we call it explicitly
        sys.modules[module_name]._start_bridge()
        _log("Reload: done — open the menu again to see changes")
        _osascript_alert("MCP Bridge — Reload", "Hook reloaded successfully.\nOpen the menu again to see any changes.")
    except Exception as e:
        _log(f"Reload error: {e}\n{traceback.format_exc()}")
        _osascript_alert("MCP Bridge — Reload Error", f"{e}\n\nSee log: {LOG_FILE}")


def _action_open_chat(selection):
    """Open the embedded Claude chat widget."""
    global _chat_instance
    try:
        if _chat_instance is None:
            _chat_instance = _FlameChat()
        _chat_instance.show()
        _log("Chat widget opened")
        # If a crash was detected at startup, show recovery info in chat
        if _last_crash_info:
            code_preview = _last_crash_info.get('code', '').strip()[:600]
            ts = _last_crash_info.get('timestamp', 'unknown time')
            msg = (
                "💥 Flame crashed in the previous session\n"
                f"Crash time: {ts}\n\n"
                "Last code executed before the crash:\n"
                "─────────────────────────────────────\n"
                f"{code_preview}\n"
                "─────────────────────────────────────\n"
                "You can ask: 'Why did this code crash and how do I fix it?'"
            )
            _chat_instance._ui_queue.append(
                lambda m=msg: _chat_instance._append_bubble("error", m))
    except Exception as e:
        _log(f"Chat widget error: {e}\n{traceback.format_exc()}")
        _osascript_alert("MCP Bridge — Chat Error", str(e))


def _action_launch_claude(selection):
    """Open a Terminal window running Claude Code with the flame MCP server."""
    import stat

    # Locate the flame-mcp project directory (must contain .mcp.json so
    # Claude Code discovers the flame MCP server definition).
    candidates = [
        _PROJECT_ROOT,
        os.path.expanduser('~/Claude_projects/flame-mcp'),
        os.path.expanduser('~/flame-mcp'),
        os.path.expanduser('~/Documents/flame-mcp'),
    ]
    project_dir = next(
        (p for p in candidates
         if os.path.isfile(os.path.join(p, '.mcp.json'))),
        next((p for p in candidates if os.path.isdir(p)), None),
    )

    if project_dir:
        venv_activate = os.path.join(project_dir, '.venv', 'bin', 'activate')
        if os.path.isfile(venv_activate):
            launch_cmd = f'cd "{project_dir}" && source .venv/bin/activate && claude'
        else:
            launch_cmd = f'cd "{project_dir}" && claude'
    else:
        launch_cmd = 'claude'

    # Use a .command file — macOS Terminal opens these directly via the shebang
    # (bash --login), bypassing the user's interactive shell session and any
    # shell plugin prompts (oh-my-zsh update, thefuck init, etc.).
    # 'open launch_claude.command' is equivalent to double-clicking the file.
    cache_dir = os.path.expanduser('~/Library/Caches/flame-mcp')
    os.makedirs(cache_dir, exist_ok=True)
    script_path = os.path.join(cache_dir, 'launch_claude.command')
    try:
        with open(script_path, 'w') as f:
            f.write('#!/bin/bash --login\n')
            f.write(f'{launch_cmd}\n')
        os.chmod(script_path, stat.S_IRWXU)
    except Exception as e:
        _log(f"Launch Claude: could not write script — {e}")
        _osascript_alert("MCP Bridge — Launch Claude", f"Could not write launch script.\n\n{e}")
        return

    _log(f"Launch Claude: script written — {launch_cmd}")

    try:
        subprocess.Popen(['open', script_path])
        _log("Launch Claude: terminal opened via .command file")
    except Exception as e:
        _log(f"Launch Claude error: {e}")
        _osascript_alert("MCP Bridge — Launch Claude",
                         f"Could not open terminal.\n\nRun manually:\n{launch_cmd}\n\nError: {e}")


def _action_view_log(selection):
    """Open the bridge log file in TextEdit."""
    try:
        open(LOG_FILE, 'a').close()
        subprocess.Popen(['open', '-a', 'TextEdit', LOG_FILE])
        _log("View log: opened in TextEdit")
    except Exception as e:
        _log(f"View log error: {e}")


RAG_LOG_FILE = os.path.join(_PROJECT_ROOT, 'logs', 'flame_rag.log')


def _action_view_rag_log(selection):
    """Open the RAG search log file in TextEdit."""
    try:
        open(RAG_LOG_FILE, 'a').close()
        subprocess.Popen(['open', '-a', 'TextEdit', RAG_LOG_FILE])
        _log("View RAG log: opened in TextEdit")
    except Exception as e:
        _log(f"View RAG log error: {e}")
