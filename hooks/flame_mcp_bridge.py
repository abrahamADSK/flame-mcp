"""
flame_mcp_bridge.py
===================
Hook de Python para Autodesk Flame que abre un servidor TCP socket.
Permite ejecutar código Python dentro de Flame desde el exterior.

Instalación:
    sudo cp flame_mcp_bridge.py /opt/Autodesk/shared/python/

Después reinicia Flame. El bridge se activa automáticamente al iniciar.

Puerto por defecto: 4444 (localhost únicamente)
"""

import threading
import socket
import json
import traceback
import sys
import io

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 4444


def app_initialized(project_name):
    """
    Hook de Flame: llamado automáticamente cuando la aplicación termina
    de inicializarse. Arranca el servidor socket en un hilo de fondo.
    """
    t = threading.Thread(target=_run_server, daemon=True, name="FlameMCPBridge")
    t.start()


def _run_server():
    """Bucle principal del servidor TCP. Acepta conexiones entrantes."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((BRIDGE_HOST, BRIDGE_PORT))
    except OSError as e:
        print(f"[FlameMCPBridge] ERROR al abrir puerto {BRIDGE_PORT}: {e}", file=sys.stderr)
        return

    server.listen(5)
    print(f"[FlameMCPBridge] Activo en {BRIDGE_HOST}:{BRIDGE_PORT}")

    while True:
        try:
            conn, addr = server.accept()
            t = threading.Thread(target=_handle_connection, args=(conn,), daemon=True)
            t.start()
        except Exception:
            pass


def _handle_connection(conn):
    """
    Maneja una conexión entrante:
    1. Lee el payload JSON con el código Python a ejecutar.
    2. Ejecuta el código con acceso al módulo flame.
    3. Devuelve resultado o error en JSON.
    """
    import flame  # importado aquí para garantizar acceso al módulo ya cargado

    try:
        # Leer datos hasta encontrar el delimitador de línea
        raw = b""
        while not raw.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk

        payload = json.loads(raw.decode('utf-8').strip())
        code = payload.get('code', '')

        # Capturar stdout durante la ejecución
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf

        local_ns = {'flame': flame}
        result = {}

        try:
            exec(compile(code, '<flame_mcp>', 'exec'), local_ns)
            result['status'] = 'ok'
            result['output'] = buf.getvalue()
            # Si el código asignó _result, lo incluimos como valor de retorno
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
