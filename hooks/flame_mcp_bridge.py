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

# Global bridge state
_bridge_active = False
_server_socket = None
_server_thread = None


# ── Flame initialisation hook ─────────────────────────────────────────────────

def app_initialized(project_name):
    """Called automatically by Flame when the application finishes loading."""
    _start_bridge()


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
            exec(compile(code, '<flame_mcp>', 'exec'), local_ns)
            result['status'] = 'ok'
            result['output'] = buf.getvalue()
            if '_result' in local_ns:
                result['return_value'] = str(local_ns['_result'])
            _log(f"  → ok  output: {buf.getvalue()[:80].strip()!r}")
        except Exception:
            result['status'] = 'error'
            result['error'] = traceback.format_exc()
            result['output'] = buf.getvalue()
            _log(f"  → ERROR: {traceback.format_exc().splitlines()[-1][:120]}")
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
        self._ui_queue = []          # written by bg thread, drained by QTimer
        self._busy = False
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

        self._chat = Qt.QTextEdit()
        self._chat.setReadOnly(True)
        self._chat.setStyleSheet(
            "QTextEdit{background:#111;color:#e0e0e0;font-size:13px;"
            "border:1px solid #333;border-radius:6px;padding:10px;}")
        layout.addWidget(self._chat, stretch=1)

        self._status = Qt.QLabel("Ready  ·  Ctrl+Return to send")
        self._status.setStyleSheet("color:#555;font-size:11px;")
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

        # QTimer drains the UI queue from the background thread
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
        self._ui_queue.append(
            lambda: self._status.setText("Ready  ·  Ctrl+Return to send"))

    # ── Agent loop (background thread) ───────────────────────────────────────

    def _agent_loop(self):
        """
        Calls 'claude -p <prompt>' as a subprocess.
        Claude Code handles all MCP tool calls (search_flame_docs, execute_python,
        learn_pattern, session_stats, etc.) internally — identical to terminal usage.
        Uses the user's existing Claude Code session (Pro/Max) — no API key needed.
        """
        try:
            self._ui_queue.append(lambda: self._status.setText("Thinking…"))

            claude_path, env = self._find_claude()
            if not claude_path:
                raise RuntimeError(
                    "claude not found.\n"
                    "Install Claude Code: npm install -g @anthropic-ai/claude-code\n"
                    "Then log in: claude login"
                )

            prompt = self._build_prompt()
            cwd = os.path.expanduser('~/Projects/flame-mcp')

            proc = subprocess.Popen(
                [claude_path, '-p', prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd if os.path.isdir(cwd) else None,
            )

            try:
                stdout, stderr = proc.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError("Claude timed out (180s). Try a simpler request.")

            response = self._strip_ansi(stdout.strip())
            if not response:
                err = self._strip_ansi(stderr.strip())
                raise RuntimeError(err or f"Claude exited with code {proc.returncode}")

            self._messages.append({"role": "assistant", "content": response})
            self._ui_queue.append(
                lambda r=response: self._append_bubble("assistant", r))

        except Exception as e:
            err = str(e)
            self._ui_queue.append(lambda e=err: self._append_bubble("error", e))
        finally:
            self._ui_queue.append(lambda: self._set_busy(False))

    # ── Claude Code subprocess helpers ────────────────────────────────────────

    @staticmethod
    def _find_claude():
        """
        Locate the 'claude' CLI executable and build a suitable environment.
        Flame's process may not inherit the user's full PATH, so we search
        common npm global install locations explicitly.
        """
        import shutil
        extra = [
            '/usr/local/bin',
            '/usr/bin',
            os.path.expanduser('~/.npm-global/bin'),
            os.path.expanduser('~/Library/pnpm'),
            os.path.expanduser('~/.volta/bin'),
        ]
        # Also pick up any nvm-managed node versions
        nvm_base = os.path.expanduser('~/.nvm/versions/node')
        if os.path.isdir(nvm_base):
            for ver in sorted(os.listdir(nvm_base), reverse=True):
                extra.append(os.path.join(nvm_base, ver, 'bin'))

        env = dict(os.environ)
        env['PATH'] = ':'.join(extra + [env.get('PATH', '')])
        found = shutil.which('claude', path=env['PATH'])
        return found, env

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

    # ── Thread-safe UI helpers ────────────────────────────────────────────────

    def _flush_ui_queue(self):
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

    def _set_busy(self, busy):
        self._busy = busy
        self._send_btn.setEnabled(not busy)
        if not busy:
            self._status.setText("Ready  ·  Ctrl+Return to send")


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
                    "name": "View log...",
                    "execute": _action_view_log,
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
        # Make sure file exists
        open(LOG_FILE, 'a').close()
        subprocess.Popen(['open', '-a', 'TextEdit', LOG_FILE])
        _log("View log: opened in TextEdit")
    except Exception as e:
        _log(f"View log error: {e}")
