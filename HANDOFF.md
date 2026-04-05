# HANDOFF — flame-mcp

**Nivel de completitud: Alto (~90%)**. Repo más maduro del ecosistema (202+ commits, 4 stars).

---

## Estado actual

**Funciona**:
- 18 MCP tools (14 read-only, 1 read-write, 1 destructive con safety checks)
- RAG híbrido (ChromaDB + BM25 + HyDE + RRF) con ~340 chunks indexados
- Self-improving patterns: trusted models (Sonnet/Opus) auto-aprenden en FLAME_API.md; modelos read-only (Qwen/Llama) staged en candidates.json
- Qt chat widget embebido en Flame con selector de modelo y multi-backend
- Unix domain socket bridge (A13) con fallback TCP
- Crash recovery (A11) con expiración automática a 24h
- Flame hook con menú integrado (Start/Stop/Restart bridge, Chat, Log viewer)
- Token tracking con estimación de tokens ahorrados por RAG
- Hot-reload del hook sin reiniciar Flame
- 18+ regex patterns + AST analysis para bloquear crashers conocidos en execute_python
- Compatibilidad Flame 2023–2027 preview (PySide2/PySide6)
- Ollama pre-flight context-window fix (fuerza num_ctx via /api/generate)
- Logs estructurados (bridge, RAG queries, crash recovery, render results)
- Multi-backend (Anthropic + Ollama LAN + Ollama cloud + Ollama Mac offline)

**Limitaciones**:
- NO VERIFICADO — requiere ejecutar en máquina con Flame instalado
- El repo está recién clonado, no instalado en esta máquina

---

## Tests existentes

5 documentos de test en `tests/` (todos son planes .md, no scripts ejecutables):
- `TEST_PLAN_COMPREHENSIVE.md` (31 KB) — 40+ test cases
- `TEST_SUITE_SEQUENTIAL.md` + `_EN.md` (17 KB c/u)
- `TEST_PLAN_QUICK_REFERENCE.md` (11 KB)
- `TEST_PLAN_INDEX.md` (7.8 KB)
- `TEST_PLAN_ANALYSIS_SUMMARY.txt` (14 KB)

**NO hay tests automatizados** (ni pytest, ni unittest).

---

## Dependencias

**requirements.txt**: mcp>=1.26.0, chromadb>=0.6.0, sentence-transformers>=2.7.0, rank-bm25>=0.7.2, pydantic>=2.0

**install.sh** (265 líneas): Python 3.11+, Claude Code v2+, Node.js 22+, crea .venv, copia hook a `/opt/Autodesk/shared/python/`, registra MCP, construye RAG index, auto-aprueba 18 tools.

**setup_linux.sh** (8.9 KB): Setup de Ollama GPU server en Linux.

---

## Bugs conocidos

- Ningún bug identificado en el código. NO VERIFICADO en ejecución real.

---

## Rutas hardcodeadas

### En código ejecutable (.py)

| Archivo | Ruta | Uso | Impacto |
|---|---|---|---|
| `flame_mcp_server.py` | `~/Projects/flame-mcp` | Base path para .env, config.json, socket, logs | **ALTO** — server no arranca si el repo no está ahí |
| `flame_mcp_server.py` | `~/flame-mcp` | Fallback search | Medio |
| `flame_mcp_server.py` | `/opt/Autodesk/project` | List Flame projects | Bajo (path estándar de Flame) |
| `flame_mcp_server.py` | `/opt/Autodesk/cfg/.*/sysconfig.cfg` | Project config lookup | Bajo (path estándar) |
| `flame_mcp_server.py` | `/opt/Autodesk/wiretap/tools/current` | Wiretap tools | Bajo (path estándar) |
| `flame_mcp_server.py` | `/opt/Autodesk/logs` | Log directory | Bajo (path estándar) |
| `flame_mcp_server.py` | `/var/opt/Autodesk/flame/projects/{name}` | Project storage (2026+) | Bajo (path estándar) |
| `hooks/flame_mcp_bridge.py` | `~/Projects/flame-mcp` | config.json, .env, socket | **ALTO** |
| `hooks/flame_mcp_bridge.py` | `~/flame-mcp`, `~/Documents/flame-mcp` | Fallback search locations | Medio |
| `hooks/flame_mcp_bridge.py` | `~/.nvm/...`, `~/.npm-global/...`, `~/.volta/...`, `~/.fnm/...`, `~/Library/pnpm` | Node.js version manager discovery | Bajo (búsqueda, no dependencia) |

**Env vars que mitigan**: `FLAME_MCP_ROOT`, `FLAME_BRIDGE_SOCKET`, `FLAME_BRIDGE_PORT`

### En scripts (.sh)

| Archivo | Ruta | Uso |
|---|---|---|
| `install.sh` | `/opt/Autodesk/shared/python/` | Copy hook destination (Flame estándar) |

### En configuración (.json)

| Archivo | Ruta | Uso |
|---|---|---|
| `claude_desktop_config.json` | `/Users/YOUR_USERNAME/Projects/flame-mcp/` | Template con placeholder |
| `.mcp.json` | (relativo) | ✅ Usa paths relativos |

### En documentación (.md)

| Archivo | Rutas mencionadas |
|---|---|
| `README.md` | `~/Projects/flame-mcp/`, `/opt/Autodesk/shared/python/`, `~/Library/Application Support/Claude/` |
| `CLAUDE.md` | `~/Projects/flame-mcp/`, `/opt/Autodesk/shared/python/` |

---

## Pendiente

- Refactorizar paths hardcodeados a `~/Projects/flame-mcp/` → derivar de `FLAME_MCP_ROOT` + `Path(__file__)` (después de validar funcionalidad base)
- Convertir test plans .md a tests automatizados (pytest con mocks del bridge)
- Evaluar si candidates.json necesita mecanismo de review/aprobación
- Verificar compatibilidad con Flame 2027 preview

---

## Última actualización: 2026-04-05 — Reestructuración de HANDOFF: separado del monolítico a HANDOFF por repo
