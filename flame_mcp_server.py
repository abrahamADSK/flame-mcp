"""
flame_mcp_server.py
===================
Servidor MCP que expone herramientas para controlar Autodesk Flame.
Se comunica con el bridge socket (flame_mcp_bridge.py) que corre dentro de Flame.

Uso:
    Registrar en Claude Code con:
        claude mcp add flame -- /ruta/al/.venv/bin/python /ruta/al/flame_mcp_server.py

    O añadir manualmente a ~/.claude/mcp_settings.json

Requisitos:
    pip install mcp --no-user

Puerto del bridge: 4444 (debe coincidir con flame_mcp_bridge.py)
"""

import socket
import json
from mcp.server.fastmcp import FastMCP

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 4444

mcp = FastMCP("flame")


# ─── Comunicación con el bridge ──────────────────────────────────────────────

def _call_flame(code: str) -> dict:
    """
    Envía código Python al bridge de Flame via socket TCP.
    Devuelve el resultado como diccionario.
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
                'No se puede conectar a Flame en el puerto 4444.\n'
                'Verifica que:\n'
                '  1. Flame esté abierto\n'
                '  2. flame_mcp_bridge.py esté en /opt/Autodesk/shared/python/\n'
                '  3. Flame se haya reiniciado después de instalar el bridge'
            )
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def _fmt(result: dict) -> str:
    """Formatea la respuesta del bridge para presentarla a Claude."""
    if result.get('status') == 'error':
        return f"ERROR:\n{result.get('error', 'Error desconocido')}"

    parts = []
    output = result.get('output', '').strip()
    return_value = result.get('return_value', '')

    if output:
        parts.append(output)
    if return_value:
        parts.append(f"Valor: {return_value}")

    return '\n'.join(parts) if parts else '(ejecutado correctamente, sin salida)'


# ─── Herramientas MCP ────────────────────────────────────────────────────────

@mcp.tool()
def run_python(code: str) -> str:
    """
    Ejecuta código Python arbitrario dentro de Autodesk Flame.
    Tiene acceso completo al módulo flame y a toda su API Python.
    Útil para inspeccionar o modificar proyectos, reels, clips, secuencias, etc.

    Ejemplo de uso:
        run_python("print(flame.project.current_project.name)")
    """
    return _fmt(_call_flame(code))


@mcp.tool()
def get_project_info() -> str:
    """
    Devuelve información básica del proyecto activo en Flame:
    nombre, frame rate, resolución y profundidad de bits.
    """
    code = """
p = flame.project.current_project
print(f"Nombre: {p.name}")
print(f"Frame rate: {p.frame_rate}")
print(f"Resolución: {p.width}x{p.height}")
print(f"Profundidad de bits: {p.bit_depth}")
"""
    return _fmt(_call_flame(code))


@mcp.tool()
def list_libraries() -> str:
    """
    Lista todas las librerías del proyecto activo en Flame,
    con el número de reels que contiene cada una.
    """
    code = """
p = flame.project.current_project
for lib in p.libraries:
    print(f"  {lib.name}  ({len(lib.reels)} reels)")
"""
    return _fmt(_call_flame(code))


@mcp.tool()
def list_reels(library_name: str = "") -> str:
    """
    Lista los reels de una librería. Si no se especifica nombre,
    muestra los reels de todas las librerías del proyecto.
    """
    if library_name:
        code = f"""
p = flame.project.current_project
lib = next((l for l in p.libraries if l.name == "{library_name}"), None)
if lib is None:
    print(f"Librería '{library_name}' no encontrada.")
else:
    for reel in lib.reels:
        print(f"  {reel.name}  ({len(reel.clips)} clips)")
"""
    else:
        code = """
p = flame.project.current_project
for lib in p.libraries:
    print(f"[{lib.name}]")
    for reel in lib.reels:
        print(f"  {reel.name}  ({len(reel.clips)} clips)")
"""
    return _fmt(_call_flame(code))


@mcp.tool()
def get_flame_version() -> str:
    """Devuelve la versión de Flame en ejecución."""
    code = "print(flame.get_version())"
    return _fmt(_call_flame(code))


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport='stdio')
