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

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 4444

# Crash recovery: written before each exec, cleared after success.
# If Flame crashes mid-exec, this file will contain the offending code
# on the next Flame startup so the chat widget can show a warning.
CRASH_RECOVERY_FILE = os.path.expanduser(
    '~/Projects/flame-mcp/logs/crash_recovery.json')

# Model config — persists the selected model across widget sessions.
MODEL_CONFIG_FILE = os.path.expanduser(
    '~/Projects/flame-mcp/config.json')

# Available models shown in the chat widget dropdown.
# Each entry: (display_label, model_id, backend)
#   backend = "anthropic"    → Anthropic cloud (api.anthropic.com)
#   backend = "ollama"       → Self-hosted Ollama server (local LAN or remote Linux box)
#                              URL configured in config.json → ollama_url
#                              e.g. "http://192.168.1.50:11434"  (Linux workstation)
#   backend = "ollama_cloud" → Ollama.com cloud API (free tier, needs ollama_cloud_key)
# Add new entries here; install.sh configures ollama_url during setup.
AVAILABLE_MODELS = [
    # ── Anthropic cloud ───────────────────────────────────────────────────────
    ("Sonnet 4.5",          "claude-sonnet-4-5-20250929",  "anthropic"),
    ("Haiku 4.5",           "claude-haiku-4-5-20251001",   "anthropic"),
    # ── Self-hosted Ollama  (Linux workstation, NAS, any server on the LAN) ───
    ("qwen3-coder 30B",     "qwen3-coder:30b",              "ollama"),
    ("qwen2.5-coder 14B",   "qwen2.5-coder:14b",           "ollama"),
    # ── Ollama cloud  (free tier · needs ollama_cloud_key in config.json) ─────
    ("qwen3-coder 480B ☁",  "qwen3-coder:480b",            "ollama_cloud"),
    # ── Custom ────────────────────────────────────────────────────────────────
    ("Custom",              "",                             "anthropic"),
]
DEFAULT_MODEL    = "claude-sonnet-4-5-20250929"
DEFAULT_BACKEND  = "anthropic"
DEFAULT_OLLAMA_URL = "http://localhost:11434"   # overridden by config.json → ollama_url

# Ollama cloud endpoint (Anthropic Messages API compatible since Ollama v0.14)
OLLAMA_CLOUD_URL = "https://api.ollama.com"

# Global bridge state
_bridge_active = False
_server_socket = None
_server_thread = None
_last_crash_info = None   # set at startup if a crash was detected


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
    """
    global _last_crash_info
    try:
        if not os.path.exists(CRASH_RECOVERY_FILE):
            return
        with open(CRASH_RECOVERY_FILE) as f:
            data = json.load(f)
        if data.get('status') == 'running':
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
    """Stop the TCP server by closing the socket."""
    global _server_socket, _bridge_active

    if not _bridge_active:
        print("[FlameMCPBridge] Already inactive.")
        return

    if _server_socket:
        try:
            _server_socket.close()
        except Exception:
            pass

    _bridge_active = False
    print("[FlameMCPBridge] Stopped.")


def _run_server():
    """Main TCP server loop. Accepts incoming connections."""
    global _server_socket, _bridge_active

    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        _server_socket.bind((BRIDGE_HOST, BRIDGE_PORT))
    except OSError as e:
        print(f"[FlameMCPBridge] ERROR opening port {BRIDGE_PORT}: {e}", file=sys.stderr)
        return

    _server_socket.listen(5)
    _bridge_active = True
    print(f"[FlameMCPBridge] Active on {BRIDGE_HOST}:{BRIDGE_PORT}")

    while _bridge_active:
        try:
            _server_socket.settimeout(1.0)
            conn, addr = _server_socket.accept()
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

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf

        local_ns = {'flame': flame}
        result = {}

        try:
            _write_crash_recovery(code)   # record before exec — cleared on success
            exec(compile(code, '<flame_mcp>', 'exec'), local_ns)
            _clear_crash_recovery()       # exec completed — no crash
            result['status'] = 'ok'
            result['output'] = buf.getvalue()
            if '_result' in local_ns:
                result['return_value'] = str(local_ns['_result'])
            _log(f"  → ok  output: {buf.getvalue()[:80].strip()!r}")
        except Exception:
            tb = traceback.format_exc()
            result['status'] = 'error'
            result['error'] = tb
            result['output'] = buf.getvalue()
            _log(f"  → ERROR: {tb.splitlines()[-1][:120]}")
            # ── Flame C++ corruption warning ──────────────────────────────────
            # 'unordered_map::at: key not found' means a C++ exception escaped
            # through the Python binding. Flame's internal state may be corrupted
            # even though Python caught the exception. Flag it clearly.
            _CPP_CRASH_MARKERS = (
                'unordered_map::at',
                'out_of_range',
                'bad_weak_ptr',
                'PyFlame',
            )
            if any(m in tb for m in _CPP_CRASH_MARKERS):
                result['flame_state'] = 'possibly_corrupted'
                _log("  ⚠️  Flame C++ exception detected — UI may be corrupted. "
                     "Consider restarting Flame if behaviour seems wrong.")
        finally:
            sys.stdout = old_stdout

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

LOG_FILE = os.path.expanduser('~/Projects/flame-mcp/logs/flame_mcp_bridge.log')


def _log(msg):
    """Write a timestamped line to the log file and to stdout."""
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
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
    - All 8 MCP tools available: execute_python, search_flame_docs,
      learn_pattern, session_stats, list_libraries, list_reels, etc.
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
        self._model, self._backend, self._ollama_url, self._ollama_cloud_key = self._load_model_config()
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
        title.setStyleSheet("color:#f59e0b;font-size:14px;font-weight:bold;padding:4px 0;")
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
            "QLineEdit:focus{border:1px solid #f59e0b;}")
        self._ollama_input.editingFinished.connect(self._on_ollama_url_changed)
        ollama_row.addWidget(self._ollama_input, stretch=1)

        layout.addWidget(self._ollama_url_widget)
        # Show only when the current backend is "ollama" (self-hosted)
        self._ollama_url_widget.setVisible(self._backend == "ollama")
        # ─────────────────────────────────────────────────────────────────────

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
            "QPushButton{background:#d97706;color:white;border:none;"
            "border-radius:5px;font-weight:bold;font-size:13px;}"
            "QPushButton:hover{background:#f59e0b;}"
            "QPushButton:disabled{background:#4a3500;color:#7a6030;}")
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

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_send(self):
        if self._busy:
            return
        text = self._input.toPlainText().strip()
        if not text:
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
        """
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
                    "Then paste the full path into ~/Projects/flame-mcp/.env:\n"
                    "  CLAUDE_PATH=/usr/local/bin/claude"
                )

            # Apply Ollama env overrides when using a self-hosted or cloud Ollama model.
            # Ollama implements the Anthropic Messages API natively (v0.14+):
            # Claude Code on macOS → HTTP → Ollama server (LAN Linux box or cloud)
            # No proxy required.
            if self._backend == "ollama":
                if not self._check_ollama():
                    raise RuntimeError(
                        f"Ollama server not reachable at {self._ollama_url}\n\n"
                        "Check that Ollama is running on the Linux machine:\n"
                        "  OLLAMA_HOST=0.0.0.0 ollama serve\n\n"
                        "And that ollama_url in config.json points to it:\n"
                        f"  {self._ollama_url}\n\n"
                        "Or switch to an Anthropic model until it's available."
                    )
                env = self._get_ollama_env(env)
            elif self._backend == "ollama_cloud":
                env = self._get_ollama_env(env)

            prompt = self._build_prompt()
            cwd = os.path.expanduser('~/Projects/flame-mcp')

            cmd = [claude_path, '-p', '--verbose', '--output-format', 'stream-json']
            if self._model:
                cmd.extend(['--model', self._model])
            cmd.append(prompt)

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd if os.path.isdir(cwd) else None,
                bufsize=1,
            )

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

            # Watchdog — kill process after 180 s
            _timed_out = [False]
            def _kill():
                _timed_out[0] = True
                try:
                    proc.kill()
                except Exception:
                    pass
            watchdog = threading.Timer(180, _kill)
            watchdog.start()

            assistant_parts = []    # text blocks from assistant messages
            tool_summaries  = []    # extracted stats footers from tool results

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

            if _timed_out[0]:
                raise RuntimeError("Claude timed out (180 s). Try a simpler request.")

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
                raise RuntimeError(err or f"Claude exited with code {proc.returncode}")

            # ── Display main assistant response ──────────────────────────────
            response = self._strip_ansi('\n\n'.join(assistant_parts).strip())
            if response:
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

        except Exception as e:
            err = str(e)
            self._ui_queue.append(lambda e=err: self._append_bubble("error", e))
        finally:
            self._ui_queue.append(lambda: self._set_busy(False))

    def _handle_stream_event(self, event, assistant_parts, tool_summaries):
        """
        Process one parsed JSON event from 'claude -p --output-format stream-json'.

        Event types we care about:
          assistant  → content blocks: text (response) or tool_use (show status)
          user       → tool_result blocks: extract stats footers
          result     → fallback: use result.result if no assistant text collected
        """
        etype = event.get('type', '')

        if etype == 'assistant':
            for block in event.get('message', {}).get('content', []):
                btype = block.get('type', '')
                if btype == 'text':
                    text = block.get('text', '').strip()
                    if text:
                        assistant_parts.append(text)
                elif btype == 'tool_use':
                    # Live status update while tool executes
                    name = block.get('name', '')
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
                    full_text = str(tc)
                # ── Flame C++ corruption warning ──────────────────────────────
                if 'possibly_corrupted' in full_text or 'unordered_map::at' in full_text:
                    warn = ("⚠️  Excepción C++ interna de Flame detectada.\n"
                            "La interfaz puede estar corrupta.\n"
                            "Si ves paneles rotos o líneas curvadas → reinicia Flame.")
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

        config.json keys:
          model            – model_id string
          backend          – "anthropic" | "ollama" | "ollama_cloud"
                             ("ollama_local" accepted for backward compat → treated as "ollama")
          ollama_url       – base URL of the Ollama server, e.g. "http://192.168.1.50:11434"
                             Set this to the IP of your Linux workstation running Ollama.
          ollama_cloud_key – API key from ollama.com (only needed for ollama_cloud backend)
        """
        try:
            with open(MODEL_CONFIG_FILE) as f:
                cfg = json.load(f)
            model      = cfg.get('model',            DEFAULT_MODEL)
            backend    = cfg.get('backend',          DEFAULT_BACKEND)
            # Backward compat: old configs may have "ollama_local"
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
                with open(MODEL_CONFIG_FILE) as f:
                    cfg = json.load(f)
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

    def _on_model_changed(self, index: int) -> None:
        """Called when the user picks a different model in the combo."""
        label, model_id, backend = AVAILABLE_MODELS[index]
        self._model   = model_id
        self._backend = backend
        self._save_model_config(model_id, backend)
        # Show the Ollama URL field only when a self-hosted Ollama model is selected
        self._ollama_url_widget.setVisible(backend == "ollama")
        if backend == "ollama":
            suffix = f" 🖥 {self._ollama_url}"
        elif backend == "ollama_cloud":
            suffix = " ☁ ollama.com"
        else:
            suffix = ""
        display = f"{label}{suffix}" if model_id else f"{label} (set model in config.json)"
        self._ui_queue.append(
            lambda d=display: self._append_bubble("tool", f"⚙️  Model → {d}"))
        _log(f"Model changed to: {model_id or 'default'} (backend={backend})")

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
        # Persist to config.json
        try:
            cfg = {}
            if os.path.exists(MODEL_CONFIG_FILE):
                with open(MODEL_CONFIG_FILE) as f:
                    cfg = json.load(f)
            cfg['ollama_url'] = url
            os.makedirs(os.path.dirname(MODEL_CONFIG_FILE), exist_ok=True)
            with open(MODEL_CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            _log(f"Ollama URL save error: {e}")
        self._ui_queue.append(
            lambda u=url: self._append_bubble("tool", f"⚙️  Ollama server → {u}"))
        _log(f"Ollama URL set to: {url}")

    # ── Ollama helpers ────────────────────────────────────────────────────────

    def _check_ollama(self) -> bool:
        """
        Return True if the configured Ollama server is reachable.
        Pings self._ollama_url (set in config.json → ollama_url).
        Works whether Ollama runs on localhost, a LAN Linux box, etc.
        """
        try:
            import urllib.request
            urllib.request.urlopen(f"{self._ollama_url}/api/version", timeout=2)
            return True
        except Exception:
            return False

    def _get_ollama_env(self, base_env: dict) -> dict:
        """
        Return a copy of base_env with Anthropic API vars pointed at Ollama.

        Ollama implements the Anthropic Messages API natively (v0.14+), so
        Claude Code on macOS can talk directly to any Ollama server on the LAN —
        no proxy required.

        Self-hosted:  ANTHROPIC_BASE_URL = config.json → ollama_url
                      ANTHROPIC_API_KEY  = "ollama"  (arbitrary, Ollama ignores it)
        Cloud:        ANTHROPIC_BASE_URL = https://api.ollama.com
                      ANTHROPIC_API_KEY  = config.json → ollama_cloud_key
                      (get a free key at ollama.com → account settings → API keys)
        """
        env = base_env.copy()
        if self._backend == "ollama":
            env['ANTHROPIC_BASE_URL']   = self._ollama_url
            env['ANTHROPIC_API_KEY']    = 'ollama'
            env['ANTHROPIC_AUTH_TOKEN'] = 'ollama'
            _log(f"Ollama backend: {self._ollama_url} / model={self._model}")
        elif self._backend == "ollama_cloud":
            env['ANTHROPIC_BASE_URL'] = OLLAMA_CLOUD_URL
            key = self._ollama_cloud_key
            if key:
                env['ANTHROPIC_API_KEY']    = key
                env['ANTHROPIC_AUTH_TOKEN'] = key
            else:
                _log("WARNING: ollama_cloud_key not set in config.json. "
                     "Add it to use Ollama cloud models (ollama.com → API keys).")
            _log(f"Ollama cloud backend: {OLLAMA_CLOUD_URL} / model={self._model}")
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
            for candidate in ['~/Projects/flame-mcp/.env', '~/flame-mcp/.env']:
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
        Build the prompt for 'claude -p', injecting recent conversation history
        so Claude Code has context for follow-up requests.
        """
        history = self._messages[:-1]   # everything except the latest user message
        user_msg = self._messages[-1]['content']

        if not history:
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
            "user":      ("#60a5fa", "You"),
            "assistant": ("#34d399", "Claude"),
            "tool":      ("#a78bfa", ""),
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
    _STYLE_BUSY   = ("color:#f59e0b;font-size:13px;font-weight:bold;"
                     "padding:2px 4px;")
    _STYLE_WARN   = "color:#f59e0b;font-size:12px;padding:2px 4px;"
    _STYLE_DANGER = ("color:#ef4444;font-size:12px;font-weight:bold;"
                     "padding:2px 4px;")

    def _idle_status_text(self):
        """Return the status bar text (and style) for the idle state."""
        if self._rate_limited:
            return (self._STYLE_DANGER,
                    "⏱️ Rate limit alcanzado — espera antes del siguiente envío")
        tok = self._session_tokens
        if tok >= self._TOKEN_DANGER:
            return (self._STYLE_DANGER,
                    f"🔴 {tok // 1000}k tokens esta sesión — considera reiniciar chat")
        if tok >= self._TOKEN_WARN:
            return (self._STYLE_WARN,
                    f"⚠️ {tok // 1000}k tokens esta sesión · Ctrl+Return to send")
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
                "💥 Flame crasheó en la sesión anterior\n"
                f"Hora del crash: {ts}\n\n"
                "Último código ejecutado antes del crash:\n"
                "─────────────────────────────────────\n"
                f"{code_preview}\n"
                "─────────────────────────────────────\n"
                "Puedes preguntar: '¿Por qué crasheó este código y cómo lo arreglo?'"
            )
            _chat_instance._ui_queue.append(
                lambda m=msg: _chat_instance._append_bubble("error", m))
    except Exception as e:
        _log(f"Chat widget error: {e}\n{traceback.format_exc()}")
        _osascript_alert("MCP Bridge — Chat Error", str(e))


def _action_launch_claude(selection):
    """Open a Terminal window running Claude Code with the flame MCP server."""
    import stat

    # Locate the flame-mcp project directory
    candidates = [
        os.path.expanduser('~/Projects/flame-mcp'),
        os.path.expanduser('~/flame-mcp'),
        os.path.expanduser('~/Documents/flame-mcp'),
    ]
    project_dir = next((p for p in candidates if os.path.isdir(p)), None)

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


RAG_LOG_FILE = os.path.expanduser('~/Projects/flame-mcp/logs/flame_rag.log')


def _action_view_rag_log(selection):
    """Open the RAG search log file in TextEdit."""
    try:
        open(RAG_LOG_FILE, 'a').close()
        subprocess.Popen(['open', '-a', 'TextEdit', RAG_LOG_FILE])
        _log("View RAG log: opened in TextEdit")
    except Exception as e:
        _log(f"View RAG log error: {e}")
