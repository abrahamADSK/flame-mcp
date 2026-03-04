"""
flame_mcp_bridge.py
===================
Hook de Python para Autodesk Flame que abre un servidor TCP socket.
Permite ejecutar código Python dentro de Flame desde el exterior.

Instalación:
    sudo cp flame_mcp_bridge.py /opt/Autodesk/shared/python/

Después reinicia Flame. El bridge se activa automáticamente al iniciar.

Puerto por defecto: 4444 (localhost únicamente)

Menú Flame:
    Se añade un submenú "MCP Bridge" en el menú principal de Flame con
    opciones para ver el estado, activar, desactivar y reiniciar el bridge.
"""

import threading
import socket
import json
import traceback
import sys
import io

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 4444

# Estado global del bridge
_bridge_active = False
_server_socket = None
_server_thread = None


# ── Flame hook de inicialización ──────────────────────────────────────────────

def app_initialized(project_name):
    """
    Hook de Flame: llamado automáticamente cuando la aplicación termina
    de inicializarse. Arranca el servidor socket en un hilo de fondo.
    """
    _start_bridge()


# ── Control del bridge ────────────────────────────────────────────────────────

def _start_bridge():
    """Arranca el servidor TCP en un hilo de fondo."""
    global _server_thread, _bridge_active

    if _bridge_active:
        print("[FlameMCPBridge] Ya está activo.")
        return

    _server_thread = threading.Thread(target=_run_server, daemon=True, name="FlameMCPBridge")
    _server_thread.start()


def _stop_bridge():
    """Detiene el servidor TCP cerrando el socket."""
    global _server_socket, _bridge_active

    if not _bridge_active:
        print("[FlameMCPBridge] Ya está inactivo.")
        return

    if _server_socket:
        try:
            _server_socket.close()
        except Exception:
            pass

    _bridge_active = False
    print(f"[FlameMCPBridge] Detenido.")


def _run_server():
    """Bucle principal del servidor TCP. Acepta conexiones entrantes."""
    global _server_socket, _bridge_active

    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        _server_socket.bind((BRIDGE_HOST, BRIDGE_PORT))
    except OSError as e:
        print(f"[FlameMCPBridge] ERROR al abrir puerto {BRIDGE_PORT}: {e}", file=sys.stderr)
        return

    _server_socket.listen(5)
    _bridge_active = True
    print(f"[FlameMCPBridge] Activo en {BRIDGE_HOST}:{BRIDGE_PORT}")

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
    Maneja una conexión entrante:
    1. Lee el payload JSON con el código Python a ejecutar.
    2. Ejecuta el código con acceso al módulo flame.
    3. Devuelve resultado o error en JSON.
    """
    import flame  # importado aquí para garantizar acceso al módulo ya cargado

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
            error_response = json.dumps({'status': 'error', 'error': str(e)}) + "\n"
            conn.sendall(error_response.encode('utf-8'))
        except Exception:
            pass
    finally:
        conn.close()


# ── Menú principal de Flame ───────────────────────────────────────────────────

def get_main_menu_custom_ui_actions():
    """
    Registra un submenú 'MCP Bridge' en el menú principal de Flame.
    Muestra el estado actual del bridge y permite activarlo, desactivarlo
    y reiniciarlo sin salir de Flame.
    """
    status = "● Activo" if _bridge_active else "○ Inactivo"

    return [
        {
            "name": f"MCP Bridge  [{status}]",
            "actions": [
                {
                    "name": f"Estado: {status} — puerto {BRIDGE_PORT}",
                    "execute": _action_status,
                },
                {
                    "name": "Activar bridge",
                    "execute": _action_start,
                },
                {
                    "name": "Desactivar bridge",
                    "execute": _action_stop,
                },
                {
                    "name": "Reiniciar bridge",
                    "execute": _action_restart,
                },
            ],
        }
    ]


# ── Acciones del menú ─────────────────────────────────────────────────────────

def _action_status(selection):
    status = "ACTIVO" if _bridge_active else "INACTIVO"
    print(f"[FlameMCPBridge] Estado: {status} — {BRIDGE_HOST}:{BRIDGE_PORT}")


def _action_start(selection):
    _start_bridge()


def _action_stop(selection):
    _stop_bridge()


def _action_restart(selection):
    _stop_bridge()
    import time
    time.sleep(0.5)
    _start_bridge()
