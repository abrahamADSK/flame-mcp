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

import threading
import socket
import json
import traceback
import sys
import io
import time

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
        except Exception:
            result['status'] = 'error'
            result['error'] = traceback.format_exc()
            result['output'] = buf.getvalue()
        finally:
            sys.stdout = old_stdout

        conn.sendall((json.dumps(result) + "\n").encode('utf-8'))

    except Exception as e:
        try:
            conn.sendall((json.dumps({'status': 'error', 'error': str(e)}) + "\n").encode('utf-8'))
        except Exception:
            pass
    finally:
        conn.close()


# ── Quick Console — run Python directly inside Flame ─────────────────────────

# Keep references alive so the GC does not destroy open dialogs
_open_dialogs = []


def _execute_in_flame(code):
    """Execute Python code directly inside Flame and return (status, output)."""
    import flame

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    local_ns = {'flame': flame}
    error = None

    try:
        exec(compile(code, '<quick_console>', 'exec'), local_ns)
    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout

    output = buf.getvalue()
    if '_result' in local_ns:
        output += f"\n=> {local_ns['_result']}"

    return ('error' if error else 'ok'), (error or output or '(no output)')


def _show_quick_console(selection):
    """Open the Quick Console dialog — run Python directly inside Flame."""
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
    except ImportError:
        print("[FlameMCPBridge] PySide2 not available — cannot open Quick Console.")
        return

    try:
        class QuickConsole(QtWidgets.QWidget):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("MCP Bridge — Quick Console")
                self.setMinimumSize(700, 500)
                # Float above Flame, don't block its event loop
                self.setWindowFlags(
                    QtCore.Qt.Window |
                    QtCore.Qt.WindowStaysOnTopHint |
                    QtCore.Qt.WindowCloseButtonHint
                )
                self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
                self.setStyleSheet("""
                    QWidget         { background: #232323; color: #e0e0e0; }
                    QLabel          { color: #a0a0a0; font-size: 11px; }
                    QPlainTextEdit  { background: #1a1a1a; color: #e8e8e8;
                                      font-family: Courier, monospace; font-size: 12px;
                                      border: 1px solid #444; border-radius: 3px; }
                    QPushButton     { background: #3a3a3a; color: #e0e0e0;
                                      border: 1px solid #555; border-radius: 3px;
                                      padding: 5px 14px; font-size: 11px; }
                    QPushButton:hover   { background: #505050; }
                    QPushButton#run_btn { background: #1a5c8a; border-color: #2a7ab8; }
                    QPushButton#run_btn:hover { background: #2a7ab8; }
                """)

                layout = QtWidgets.QVBoxLayout(self)
                layout.setSpacing(8)
                layout.setContentsMargins(12, 12, 12, 12)

                header = QtWidgets.QLabel("Quick Console  —  Python runs directly inside Flame")
                header.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
                layout.addWidget(header)

                layout.addWidget(QtWidgets.QLabel("Python code:"))
                self.input = QtWidgets.QPlainTextEdit()
                self.input.setPlaceholderText(
                    "# Example:\n"
                    "p = flame.projects.current_project\n"
                    "print(p.name, p.frame_rate)"
                )
                self.input.setMinimumHeight(160)
                layout.addWidget(self.input)

                btn_row = QtWidgets.QHBoxLayout()
                self.run_btn = QtWidgets.QPushButton("▶  Run")
                self.run_btn.setObjectName("run_btn")
                self.run_btn.clicked.connect(self._execute)
                self.clear_btn = QtWidgets.QPushButton("Clear output")
                self.clear_btn.clicked.connect(self._clear_output)
                btn_row.addWidget(self.run_btn)
                btn_row.addWidget(self.clear_btn)
                btn_row.addStretch()
                layout.addLayout(btn_row)

                layout.addWidget(QtWidgets.QLabel("Output:"))
                self.output = QtWidgets.QPlainTextEdit()
                self.output.setReadOnly(True)
                self.output.setMinimumHeight(160)
                layout.addWidget(self.output)

                close_row = QtWidgets.QHBoxLayout()
                close_row.addStretch()
                close_btn = QtWidgets.QPushButton("Close")
                close_btn.clicked.connect(self.close)
                close_row.addWidget(close_btn)
                layout.addLayout(close_row)

                shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self)
                shortcut.activated.connect(self._execute)

            def _execute(self):
                code = self.input.toPlainText().strip()
                if not code:
                    return
                self.output.appendPlainText(f">>> {code[:60]}{'...' if len(code) > 60 else ''}")
                status, result = _execute_in_flame(code)
                prefix = "OK" if status == 'ok' else "ERROR"
                self.output.appendPlainText(f"[{prefix}]\n{result}\n{'-' * 40}")

            def _clear_output(self):
                self.output.clear()

        dlg = QuickConsole()
        _open_dialogs.append(dlg)
        dlg.destroyed.connect(lambda: _open_dialogs.remove(dlg) if dlg in _open_dialogs else None)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    except Exception as e:
        print(f"[FlameMCPBridge] Quick Console error: {e}")
        traceback.print_exc()


def _show_connection_test(selection):
    """Test the bridge connection and show result in a floating label."""
    try:
        from PySide2 import QtWidgets, QtCore
    except ImportError:
        status = "ACTIVE" if _bridge_active else "INACTIVE"
        print(f"[FlameMCPBridge] Connection test: {status} — {BRIDGE_HOST}:{BRIDGE_PORT}")
        return

    try:
        if _bridge_active:
            title = "MCP Bridge — Connected"
            msg = (f"Bridge is ACTIVE\n"
                   f"Listening on {BRIDGE_HOST}:{BRIDGE_PORT}\n\n"
                   f"Ready to receive commands from Claude.")
        else:
            title = "MCP Bridge — Not Connected"
            msg = ("Bridge is INACTIVE\n\n"
                   "Use  'Start bridge'  to activate it,\n"
                   "or restart Flame to load it automatically.")

        box = QtWidgets.QMessageBox()
        box.setWindowTitle(title)
        box.setText(msg)
        box.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.WindowStaysOnTopHint
        )
        box.setIcon(
            QtWidgets.QMessageBox.Information if _bridge_active
            else QtWidgets.QMessageBox.Warning
        )
        _open_dialogs.append(box)
        box.finished.connect(lambda: _open_dialogs.remove(box) if box in _open_dialogs else None)
        box.show()
        box.raise_()
        box.activateWindow()

    except Exception as e:
        print(f"[FlameMCPBridge] Connection test error: {e}")
        traceback.print_exc()


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
                    "name": "─────────────────",
                    "execute": lambda s: None,
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
                    "name": "─────────────────",
                    "execute": lambda s: None,
                },
                {
                    "name": "Quick Console...",
                    "execute": _show_quick_console,
                },
                {
                    "name": "Connection test",
                    "execute": _show_connection_test,
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
