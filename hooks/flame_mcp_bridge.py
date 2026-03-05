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
                    "name": "Launch Claude...",
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
