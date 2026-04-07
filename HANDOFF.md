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

### Planes de test (documentación)
5 documentos en `tests/` (planes .md, no scripts ejecutables):
- `TEST_PLAN_COMPREHENSIVE.md` (31 KB) — 40+ test cases
- `TEST_SUITE_SEQUENTIAL.md` + `_EN.md` (17 KB c/u)
- `TEST_PLAN_QUICK_REFERENCE.md` (11 KB)
- `TEST_PLAN_INDEX.md` (7.8 KB)
- `TEST_PLAN_ANALYSIS_SUMMARY.txt` (14 KB)

### Tests automatizados (pytest) — ✅ NUEVO 2026-04-07
**62 tests, 62 pasando, 0 fallos.** Ejecutar con:
```bash
ulimit -n 4096 && python -m pytest tests/ -v --tb=short -p no:cacheprovider
```

Requiere: `pip install chromadb rank-bm25 pytest --break-system-packages`

| Archivo | Tests | Descripción |
|---|---|---|
| `tests/conftest.py` | — | Path setup, MCP stubs, mock_bridge fixtures, mini Flame corpus (12 chunks), ChromaDB determinístico |
| `tests/test_safety.py` | 10 | `_check_dangerous()`: 18 regex + AST patterns, multi-hit, safe code |
| `tests/test_redirect.py` | 8 | `execute_python` redirect system: 5 hard redirects, 3 soft redirect supresión |
| `tests/test_tools.py` | 24 | Tools dedicadas: ping, get_project_info, list_libraries, list_reels, list_clips, execute_python, get_flame_version, list_desktop_reels, list_batch_groups, get_clip_metadata, get_selected_clips, flame_wiretap_tree, list_flame_logs, read_flame_log |
| `tests/test_rag_search.py` | 20 | RAG híbrido: BM25, RRF fusion, ChromaDB, cache, índice vacío, índice ausente |

---

## Dependencias

**requirements.txt**: mcp>=1.26.0, chromadb>=0.6.0, sentence-transformers>=2.7.0, rank-bm25>=0.2, pydantic>=2.0

**install.sh** (265 líneas): Python 3.11+, Claude Code v2+, Node.js 22+, crea .venv, copia hook a `/opt/Autodesk/shared/python/`, registra MCP, construye RAG index, auto-aprueba 18 tools.

**setup_linux.sh** (8.9 KB): Setup de Ollama GPU server en Linux.

---

## Bugs conocidos

- Ningún bug identificado en el código. NO VERIFICADO en ejecución real.
- Widget embebido requiere que el repo esté en una de las rutas candidatas (ver abajo).

---

## Rutas hardcodeadas

### En código ejecutable (.py)

| Archivo | Ruta | Uso | Impacto |
|---|---|---|---|
| `src/flame_mcp/server.py` | `~/Claude_projects/flame-mcp` | Base path para .env, config.json, socket, logs | **ALTO** — server no arranca si el repo no está ahí |
| `src/flame_mcp/server.py` | `~/flame-mcp` | Fallback search | Medio |
| `src/flame_mcp/server.py` | `/opt/Autodesk/project` | List Flame projects | Bajo (path estándar de Flame) |
| `src/flame_mcp/server.py` | `/opt/Autodesk/cfg/.*/sysconfig.cfg` | Project config lookup | Bajo (path estándar) |
| `src/flame_mcp/server.py` | `/opt/Autodesk/wiretap/tools/current` | Wiretap tools | Bajo (path estándar) |
| `src/flame_mcp/server.py` | `/opt/Autodesk/logs` | Log directory | Bajo (path estándar) |
| `src/flame_mcp/server.py` | `/var/opt/Autodesk/flame/projects/{name}` | Project storage (2026+) | Bajo (path estándar) |
| `hooks/flame_mcp_bridge.py` | `~/Claude_projects/flame-mcp` | config.json, .env, socket | ✅ Refactorizado (Chat 12) |
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
| `README.md` | `~/flame-mcp/`, `/opt/Autodesk/shared/python/`, `~/Library/Application Support/Claude/` |
| `CLAUDE.md` | `~/Claude_projects/flame-mcp/`, `/opt/Autodesk/shared/python/` |

---

## Fixes aplicados — 2026-04-05 (sesión Mac install)

### Widget embebido no detectaba tools MCP
- **Causa raíz**: `_agent_loop` usaba `cwd = _PROJECT_ROOT` para lanzar `claude -p`. Cuando el hook está instalado en `/opt/Autodesk/shared/python/`, `_PROJECT_ROOT` resuelve a `/opt/Autodesk/shared/` → Claude Code no encuentra `.mcp.json` → no ve las tools de flame-mcp.
- **Fix**: Buscar el repo en candidates que contengan `.mcp.json`: `_PROJECT_ROOT` → `~/Claude_projects/flame-mcp` → `~/flame-mcp` → `~/Documents/flame-mcp`.
- **Archivos**: `hooks/flame_mcp_bridge.py` (`_agent_loop` línea ~940 y `_action_launch_claude` línea ~1900)

### Socket path resolution
- **Causa raíz**: Bridge y server asumían que `run/flame_mcp.sock` estaba dentro del repo. Hook instalado fuera del repo no encontraba el socket.
- **Fix**: Bridge detecta si corre desde `hooks/` (dev) o instalado, y usa `/tmp/flame_mcp.sock` como default en modo instalado. Server usa fallback: `repo/run/` → `/tmp/` → TCP.
- **Archivos**: `hooks/flame_mcp_bridge.py` (líneas 50-56), `src/flame_mcp/server.py` (líneas 489-496)

### rank-bm25 version
- **Bug**: `requirements.txt` pedía `rank-bm25>=0.7.2` — esa versión no existe en PyPI (última es 0.2.2).
- **Fix**: Cambiado a `rank-bm25>=0.2`.

### install.sh — Python version discovery
- **Bug**: Usaba `python3` sin versionar. En macOS, `python3` del Xcode CLT puede ser 3.9.
- **Fix**: Busca `python3.13` → `python3.12` → `python3.11` en Homebrew paths y PATH antes de caer a `python3` genérico. Todos los usos de `python3` en el script reemplazados por `$PYTHON_BIN`.

### Decisiones tomadas
- Los archivos RAG (`rag/index/`) son regenerables y se excluyeron del commit.
- Los candidates del widget usan `.mcp.json` como criterio (no solo `isdir`) para garantizar que Claude Code descubra la config del server.
- `install.sh` no cambia los candidates — la búsqueda de Python es independiente.

---

## Bugs encontrados y corregidos — 2026-04-07 (sesión tests automatizados)

### Caracteres de control en `_REDIRECT_PATTERNS` (src/flame_mcp/safety.py)
- **Bug**: 4 patrones en `_REDIRECT_PATTERNS` contenían caracteres `\x08` (backspace, 0x08) embebidos en lugar de `\b` (word boundary). Esto hacía que los redirects no dispararan para `flame.selection`, `\.reels`, `\.clips` y `current_project`.
- **Causa raíz**: Los raw strings `r'...\b...'` habían sido editados con un editor que sustituyó `\b` por el carácter de control backspace literal.
- **Impacto**: execute_python no redirigía correctamente cuando el código usaba `flame.selection`, `lib.reels`, `ws.libraries[].clips`, o `current_project.name`. Las soft redirects para `\.reels` y `\.clips` tampoco funcionaban porque el string no coincidía con `_SOFT_REDIRECT_PATTERNS`.
- **Fix**: Reemplazados los 4 `\x08` → `\b` (o eliminados donde el pattern ya funciona sin word boundary) usando operación binaria en el archivo.
- **Archivo**: `src/flame_mcp/safety.py` (extraído de `flame_mcp_server.py` en refactor 2026-04-07)

### `_SOFT_REDIRECT_PATTERNS` desincronizado
- **Causa raíz**: Misma causa que arriba — los strings con `\x08` en `_REDIRECT_PATTERNS` no coincidían con los strings en `_SOFT_REDIRECT_PATTERNS` (que NO tenían `\x08`).
- **Fix**: El fix de arriba alinea ambos sets automáticamente.

---

## Refactor: Migración a src/flame_mcp/ — 2026-04-07

### Qué se hizo
- Creado `src/flame_mcp/` con estructura de paquete Python instalable
- Movido `flame_mcp_server.py` → `src/flame_mcp/server.py` (1760 líneas, -247 de safety extraído)
- Extraído `src/flame_mcp/safety.py` con: `_DANGEROUS_PATTERNS`, `_check_dangerous()`, `_REDIRECT_PATTERNS`, `_SOFT_REDIRECT_PATTERNS`, `_CREATION_INTENT_RE`
- Movido `rag/*.py` → `src/flame_mcp/rag/` (search.py, config.py, build_index.py, validate_index.py, generate_flame_api.py)
- Creado `pyproject.toml` con entry point `flame-mcp = flame_mcp.server:main`
- Creado `src/flame_mcp/__init__.py`
- Actualizados TODOS los imports: `from flame_mcp_server import` → `from flame_mcp.server import`, `from rag.` → `from flame_mcp.rag.`
- Eliminados todos los `sys.path.insert` hacks en server.py, search.py, build_index.py, validate_index.py, conftest.py
- Actualizado `.mcp.json`: `args: ["-m", "flame_mcp.server"]`
- Actualizado `_SERVER_DIR` a `Path(__file__).resolve().parent.parent.parent` (repo root)
- Actualizados paths de `_CANDIDATES_PATH`, `_FAILED_PATH`, `build_script`, `_lock_file`
- 62/62 tests pasando

### Decisiones tomadas
- `hooks/` y `scripts/` NO se movieron — ejecutan fuera del paquete MCP
- `rag/corpus.json` e `index/` no se copiaron (generados, deben regenerarse)
- `pyproject.toml` usa `requires-python = ">=3.10"` (sandbox usa 3.10; en producción será 3.11+)
- `flame_mcp_server.py` original y `rag/*.py` originales necesitan ser borrados localmente (el sandbox no puede hacer `rm` en el mount)

### Qué queda pendiente post-refactor
- **Borrar archivos originales** en tu máquina local: `rm flame_mcp_server.py` y `rm rag/__init__.py rag/config.py rag/search.py rag/build_index.py rag/validate_index.py rag/generate_flame_api.py`
- **Copiar** `rag/corpus.json` e `index/` a `src/flame_mcp/rag/` si quieres preservar el corpus (o regenerar con `python -m flame_mcp.rag.build_index`)
- **Reinstalar** en tu máquina: `cd flame-mcp && pip install -e .`
- **Commit** sugerido: `refactor: migrate flame-mcp to src/flame_mcp/ package layout + extract safety.py`

---

## Pendiente

- ✅ Refactorizar paths hardcodeados (legacy) → completado (Chat 12)
- ✅ Convertir test plans .md a tests automatizados → completado (2026-04-07): 62 tests, 100% pass
- ✅ Migración a src/flame_mcp/ package layout → completado (2026-04-07): 62 tests, 100% pass
- Borrar archivos originales del root (flame_mcp_server.py, rag/*.py) — debe hacerse localmente
- Evaluar si candidates.json necesita mecanismo de review/aprobación
- Verificar compatibilidad con Flame 2027 preview
- Verificar widget embebido en Flame real después de los fixes (requiere máquina con Flame)
- Considerar añadir `rag/index/` a `.gitignore` si se determina que siempre debe regenerarse

---

## Última actualización: 2026-04-07 — Migración a src/flame_mcp/, extract safety.py, 62/62 tests OK
