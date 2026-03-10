# flame-mcp — Informe de Auditoría Completa
**Fecha:** 2026-03-10
**Alcance:** Código fuente, documentación, corpus RAG, privacidad, derechos de autor, portabilidad, seguridad.

---

## Resumen Ejecutivo

El proyecto está en buen estado funcional para uso personal en un entorno Autodesk Flame local. Sin embargo, antes de publicarlo como repositorio público o distribuirlo a otros usuarios, hay **4 problemas críticos** y **8 mejoras importantes** que deben resolverse. Los principales vectores de riesgo son: una API key real en un archivo de configuración rastreado parcialmente, un conflicto arquitectural que corrompe el corpus RAG en cada rebuild, archivos residuales que no deberían estar en git, y una incompatibilidad de licencias con el material de Autodesk.

---

## 1. Seguridad y Datos Sensibles

### 🔴 CRÍTICO — `config.json` contiene credenciales reales

El archivo `config.json` contiene:
```json
{
  "ollama_url": "http://[internal-hostname]:11434",
  "ollama_cloud_key": "[REDACTED]"
}
```

- `[internal-hostname]` es el hostname de un servidor privado de red local — información de infraestructura interna.
- `ollama_cloud_key` es una API key real de ollama.com activa.

**Estado actual:** `config.json` está en `.gitignore` — **NO se sube a git**. El riesgo es nulo en este momento.
**Acción requerida:** Ninguna inmediata. Sin embargo, se recomienda rotar la API key si `config.json` fue expuesto accidentalmente en algún momento.
**Verificar:** `git log --all -- config.json` para confirmar que nunca fue commiteado.

---

### 🔴 CRÍTICO — `logs/flame_import_result.txt` rastreado en git

Este archivo contiene nombres reales de clips del proyecto Flame del usuario:
```
OK: ["'1476204_People_3840x2160'", "'COL_NOISE_25fps'", "'Meridian_UHD4k5994_HDR_P3PQ'", "'cine_negro_tono.mov'", ...]
```

Está **rastreado en git** (`git ls-files logs/flame_import_result.txt` devuelve el archivo). Es un artefacto de runtime que expone nombres de proyectos y media del entorno de trabajo.

**Acción requerida:**
```bash
git rm --cached logs/flame_import_result.txt
echo "logs/*.txt" >> .gitignore  # añadir a gitignore
git commit -m "fix(privacy): remove runtime log artifact from git tracking"
```

---

### 🟡 IMPORTANTE — `.claude/settings.local.json` contiene paths personales

Contiene `/Users/abraham/...` con comandos bash específicos del sistema. Está en `.gitignore` (`.claude/` excluido). Sin riesgo actual, pero confirmar que nunca fue commiteado: `git log --all -- .claude/`.

---

### 🟡 IMPORTANTE — `install.sh` y `README.md` exponen el username de GitHub

```bash
git clone https://github.com/abrahamADSK/flame-mcp.git
```

Esto es intencional si el repo es público bajo ese username. Si se transfiere o se hace fork, el script de instalación deja de funcionar. Considerar usar una URL genérica o una variable.

---

## 2. Derechos de Autor y Licencias

### 🔴 CRÍTICO — Conflicto de licencias: MIT vs CC BY-NC-SA 3.0

El proyecto tiene licencia **MIT** (`LICENSE`), pero `docs/code_samples/autodesk_zips/` contiene código de Autodesk bajo **Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported** (hay tres archivos `cc_by_nc_sa_3_0_unported.txt` que lo especifican).

Las licencias son **incompatibles** para distribución pública:
- CC BY-NC-SA 3.0 prohíbe uso comercial y exige que las obras derivadas se publiquen bajo la misma licencia.
- MIT permite uso comercial sin restricciones de share-alike.

Archivos afectados:
- `docs/code_samples/autodesk_zips/husky.py`
- `docs/code_samples/autodesk_zips/naming_conventions.py`
- `docs/code_samples/autodesk_zips/custom_menu_actions/*.py`
- `docs/code_samples/autodesk_zips/logik_python_code.txt`

**Acción requerida:**
1. Añadir un apartado `THIRD-PARTY LICENSES` en el `README.md` o crear `NOTICE.md` que declare que el contenido de `docs/code_samples/autodesk_zips/` está bajo CC BY-NC-SA 3.0 de Autodesk, con atribución correcta.
2. Aclarar que la licencia MIT del proyecto **no se aplica** a esos archivos.
3. Si el proyecto pretende uso comercial, evaluar si los archivos de Autodesk deben excluirse del repo o sólo referenciarse.

---

### 🟡 IMPORTANTE — `docs/flame-mcp-reference.pdf` (40 KB) sin origen documentado

Este PDF está rastreado en git pero no tiene atribución de fuente ni licencia visible en ningún README. Si es de Autodesk u otra empresa, podría constituir redistribución no autorizada.

**Acción requerida:** Documentar el origen del PDF en el README, o eliminarlo del repo si no tiene licencia de distribución.

---

### 🟡 IMPORTANTE — `docs/flame_youtube_patterns.md` menciona presentadores por nombre

El archivo menciona nombres de personas (Bryan Bayley, Andy Milkis, Fred Warren, John Geehreng, etc.) en el contexto de atribución de patrones de código derivados de sus tutoriales en Logik Live. Esto es técnicamente uso justo educativo, pero:

- Todos los patrones están identificados como "extraídos de transcripciones de voz" — la nota de advertencia es apropiada.
- Los nombres se usan en contexto técnico, no como testimonios o endorsements.
- No se reproducen fragmentos largos de transcripciones verbatim.

**Estado:** Aceptable para uso público con la advertencia ya presente. Considerar añadir "Todos los derechos de los videos originales pertenecen a Logik Live y sus presentadores" en el encabezado del archivo.

---

### ✅ Transcripciones de YouTube correctamente excluidas

`docs/transcripts/` está en `.gitignore` y no se rastrea en git. Los 44 archivos `.txt` están sólo localmente. Esto es correcto: las transcripciones completas podrían violar los términos de servicio de YouTube y los derechos de los creadores de contenido.

---

## 3. Portabilidad y Agnóstico del Sistema

### 🔴 CRÍTICO — Arquitectura RAG conflictiva: corpus.json es fuente Y artefacto

Este es el problema más grave para la reproducibilidad del proyecto.

**El problema:**
- `rag/build_index.py` **genera `rag/corpus.json`** leyendo todos los archivos `.md` de `docs/` y aplicando su propio algoritmo de chunking básico (split en headers `##`).
- Las sesiones anteriores editaron `corpus.json` **directamente** (re-chunking de FLAME_API.md de 73→301 chunks, eliminación de `flame_api_full.md`).
- Cada vez que alguien ejecuta `python rag/build_index.py`, **se sobreescriben todos los cambios manuales** del corpus.

**Estado actual del corpus (en disco):** 525 chunks, generado por build_index.py en Mac.
**Estado del corpus en HEAD de git:** 678 chunks con schema mixto (`{id,text,metadata}` + `{source,content}`) — **archivo corrupto que no puede ser leído correctamente por search.py**.

**Impacto:** El re-chunking mejorado (73→301 chunks para FLAME_API.md) se pierde en cada rebuild. `flame_api_full.md` (71 chunks duplicados) sigue siendo indexado.

**Solución requerida:** La mejora del chunking debe implementarse en `rag/build_index.py`, no en `corpus.json`. El corpus debe ser 100% reproducible desde los archivos `.md` fuente.

Cambios concretos en `build_index.py`:
1. Implementar chunking por grupos de métodos (4 métodos por chunk) para secciones de API.
2. Excluir `docs/flame_api_full.md` de los archivos indexados (es 100% duplicado de `FLAME_API.md`).
3. Añadir flag `--force` para rebuild limpio.

---

### 🟡 IMPORTANTE — `docs/flame_api_full.md` duplicado sigue en el repo e indexado

El análisis previo confirmó que `docs/flame_api_full.md` es **100% idéntico** a `FLAME_API.md` en contenido. Ocupa 71 chunks del corpus (14% del total) sin aportar nueva información. Degrada la diversidad del corpus y aumenta el ruido de recuperación.

**Acción requerida:**
```bash
git rm docs/flame_api_full.md
# Y añadir exclusión en build_index.py
git commit -m "fix(rag): remove duplicate flame_api_full.md"
```

---

### 🟡 IMPORTANTE — `FLAME_API.bak.md` es un artefacto rastreado en git

Está commiteado pero tiene un checksum diferente a `FLAME_API.md` — es una versión anterior. No tiene propósito en el repo público.

**Acción requerida:**
```bash
git rm FLAME_API.bak.md
echo "*.bak.md" >> .gitignore
git commit -m "fix(cleanup): remove FLAME_API.bak.md artifact"
```

---

### 🟡 IMPORTANTE — Artefactos macOS `__MACOSX/` rastreados en git

Tres archivos `._*` de metadatos macOS están en git bajo `docs/code_samples/autodesk_zips/__MACOSX/`. Son artefactos del sistema de archivos HFS+ que no tienen contenido útil y no deben distribuirse.

**Acción requerida:**
```bash
git rm -r "docs/code_samples/autodesk_zips/__MACOSX/"
echo "__MACOSX" >> .gitignore
git commit -m "fix(cleanup): remove macOS HFS+ artifacts from git"
```

---

### 🟢 OK — `config.json` correctamente gitignoreado

El archivo de configuración con datos sensibles está excluido correctamente. Existe `config.example.json` con valores placeholder para que los usuarios puedan configurar su entorno. Arquitectura correcta.

---

### 🟢 OK — `docs/transcripts/` correctamente gitignoreado

Las transcripciones de YouTube (44 archivos, potencialmente miles de líneas cada uno) no se incluyen en el repositorio. Correcto desde el punto de vista legal y de tamaño del repo.

---

## 4. Estado del Corpus RAG

### Corpus actual (525 chunks, generado por build_index.py en Mac)

| Fuente | Chunks | Calidad |
|--------|--------|---------|
| `docs/flame_advanced_api.md` | 78 | Alta — API avanzada con ejemplos |
| `FLAME_API.md` | 75 | Media — chunks demasiado grandes (avg ~1861 chars) |
| `docs/flame_api_full.md` | 71 | Nula — 100% duplicado de FLAME_API.md |
| `docs/flame_segment_timeline_api.md` | 61 | Alta — timeline muy detallado |
| `docs/flame_youtube_patterns.md` | 60 | Alta — patrones reales de uso |
| `docs/flame_code_samples.md` | 46 | Alta — code samples verificados |
| `docs/flame_reference_guide.md` | 30 | Media |
| `docs/flame_community_workflows.md` | 23 | Media |
| `docs/flame_ocr_patterns_v2.md` | 23 | Alta — batch hooks, create_node |
| `docs/flame_cookbook_official.md` | 22 | Alta |
| `docs/flame_ocr_patterns.md` | 15 | Alta — patrones OCR round 1 |
| `docs/flame_openclip_patterns.md` | 8 | Alta — OpenClip/husky.py |
| `docs/flame_vocabulary.md` | 8 | Media |
| `docs/ARCHITECTURE.md` | 5 | Baja — descripción del proyecto |

**Cobertura temática:**
- ✅ API básica (clips, reels, bibliotecas, proyectos, workspace)
- ✅ Batch/compositing (create_node, connect_nodes, render hooks)
- ✅ Timeline y segmentos
- ✅ Custom menus / hooks del sistema
- ✅ OpenClip y watch-folder workflows
- ✅ Naming conventions y hooks de nomenclatura
- ⚠️ Wiretap/IFFFS (cobertura mínima — intencionado por seguridad)
- ⚠️ Flame Effects (FX) — sin cobertura
- ⚠️ Media Panel UI avanzado — cobertura parcial

### Eficiencia del chunking

El chunking actual (split básico por headers `##`) produce chunks variables con tamaños problemáticos:
- `FLAME_API.md`: avg ~1861 chars/chunk, max ~8697 chars — demasiado grande para recuperación precisa
- `docs/flame_advanced_api.md`: avg ~900 chars — más manejable
- Las secciones más largas entierran nombres de métodos específicos en ruido semántico

**Impacto en retrieval:** Las queries sobre métodos específicos (ej. `flame.batch.create_node`) tienen menor precisión porque el chunk que los contiene incluye docenas de otros métodos no relacionados.

---

## 5. Código Fuente — Evaluación

### `flame_mcp_server.py` (1577 líneas) — ✅ Buena calidad

- Arquitectura MCP correcta con FastMCP.
- Safety system robusto: 18 patrones de código peligroso con regex + alternativas seguras.
- Lectura de config desde `config.json` sin hardcodear credenciales.
- Compatibilidad con múltiples modelos (claude-opus-4-5, claude-sonnet-4-6, etc.).
- Manejo de errores defensivo con try/except en puntos críticos.
- Los parámetros de entorno (`FLAME_BRIDGE_PORT`, `FLAME_BRIDGE_SOCKET`) son configurables via variables de entorno — buena portabilidad.

**Mejoras menores:**
- La lista `WRITE_ALLOWED_MODELS` hardcodea model strings que pueden quedar obsoletos.
- No hay validación de input para code injection antes de enviar al bridge.

### `hooks/flame_mcp_bridge.py` — ✅ Buena calidad

- Integración Qt (PyFlame) correcta para Flame.
- Soporte multi-backend: anthropic, ollama (LAN), ollama_cloud, ollama_mac.
- Gestión de timeouts diferenciados por backend.
- UI de configuración bien construida.
- Los textos de UI en español sugieren uso personal — considerar inglés para distribución.

### `rag/search.py` — ✅ Buena calidad

- Hybrid BM25 + ChromaDB con RRF fusion — arquitectura state-of-the-art.
- HyDE (Hypothetical Document Embedding) para mejorar queries cortas.
- Lazy loading de singletons para rendimiento.

### `rag/build_index.py` — ⚠️ Funcional pero con problema arquitectural

- Chunking básico por headers funciona pero produce chunks demasiado grandes.
- No excluye archivos duplicados (`flame_api_full.md`).
- Sobreescribe `corpus.json` sin opción de merge con ediciones manuales.
- El comentario en `.gitignore` dice "commit the index" pero no hay instrucción en el build script para hacerlo automáticamente.

### `install.sh` — ⚠️ Username hardcoded

- URL de clone con username específico `abrahamADSK` — rompe si el repo se transfiere.
- Buen flujo de instalación de .venv y dependencias.

---

## 6. Documentación

### `README.md` — ✅ Completo

Cubre instalación, configuración, uso y arquitectura. El username en la URL de clone es el único issue.

### `CLAUDE.md` — ✅ Apropiado

Instrucciones para Claude Code sobre el contexto del proyecto. Sin información sensible.

### `docs/ARCHITECTURE.md` — ✅ OK

Descripción técnica de la arquitectura del sistema.

### `docs/EXTRACTION_REPORT.txt` — 🟡 Path interno expuesto

Contiene la referencia:
```
Output: /sessions/magical-fervent-ride/mnt/Projects/flame-mcp/docs/...
```
Es un path de la VM de sesión de Claude — información de infraestructura interna que no aporta valor. Debería limpiarse o eliminarse del repo.

---

## 7. Plan de Acción Priorizado

### Inmediato (antes de cualquier push público)

| Prioridad | Acción | Comando |
|-----------|--------|---------|
| 🔴 1 | Desrastrear `logs/flame_import_result.txt` | `git rm --cached logs/flame_import_result.txt` |
| 🔴 2 | Eliminar `docs/flame_api_full.md` (duplicado) | `git rm docs/flame_api_full.md` |
| 🔴 3 | Eliminar artefactos macOS `__MACOSX/` | `git rm -r "docs/code_samples/autodesk_zips/__MACOSX/"` |
| 🔴 4 | Eliminar `FLAME_API.bak.md` | `git rm FLAME_API.bak.md` |
| 🔴 5 | Añadir `logs/*.txt`, `__MACOSX`, `*.bak.md` a `.gitignore` | Editar `.gitignore` |
| 🔴 6 | Corregir `corpus.json` corrupto en git (reemplazar con versión de Mac) | Ver abajo |

### Arquitectura RAG (sesión de trabajo)

| Prioridad | Acción |
|-----------|--------|
| 🟡 1 | Mover lógica de re-chunking (4 métodos/chunk) a `rag/build_index.py` |
| 🟡 2 | Excluir `flame_api_full.md` en `collect_docs()` de `build_index.py` |
| 🟡 3 | Ejecutar `python rag/build_index.py` → commitar resultado limpio |

### Documentación legal

| Prioridad | Acción |
|-----------|--------|
| 🟡 1 | Crear `NOTICE.md` o añadir sección en `README.md` para CC BY-NC-SA de Autodesk |
| 🟡 2 | Documentar origen y licencia de `docs/flame-mcp-reference.pdf` |
| 🟡 3 | Rotar `ollama_cloud_key` en config.json local |

---

## 8. Comandos de Limpieza Completa

```bash
# === En Mac, dentro del directorio flame-mcp ===

# 1. Desrastrear archivos que no deben estar en git
git rm --cached logs/flame_import_result.txt
git rm docs/flame_api_full.md
git rm FLAME_API.bak.md
git rm -r "docs/code_samples/autodesk_zips/__MACOSX/"

# 2. Actualizar .gitignore
cat >> .gitignore << 'EOF'

# Runtime artifacts
logs/*.txt
logs/*.json

# Backup files
*.bak.md

# macOS HFS+ metadata
__MACOSX
._*
EOF

# 3. Corregir build_index.py para excluir flame_api_full.md
# (editar collect_docs() para filtrar ese archivo)

# 4. Rebuild el corpus desde los .md fuente
python rag/build_index.py

# 5. Commitar todo junto
git add -A
git commit -m "fix: cleanup git tracking, remove duplicates and personal artifacts

- Remove logs/flame_import_result.txt (runtime data, personal project names)
- Remove docs/flame_api_full.md (100% duplicate of FLAME_API.md, -71 chunks)
- Remove FLAME_API.bak.md (backup artifact)
- Remove __MACOSX/ HFS+ metadata artifacts
- Update .gitignore for logs/*.txt, *.bak.md, __MACOSX
- Rebuild corpus.json from source .md files (clean schema)
- corpus.json: 525 → ~455 chunks after deduplication
"

git push origin main
```

---

## 9. Estado General del Sistema

| Componente | Estado | Nota |
|------------|--------|------|
| MCP Server (`flame_mcp_server.py`) | ✅ Funcional | Buena calidad, safety system robusto |
| Bridge (`hooks/flame_mcp_bridge.py`) | ✅ Funcional | Requiere Flame en ejecución |
| RAG Search (`rag/search.py`) | ✅ Funcional | Hybrid BM25+semantic, HyDE |
| RAG Corpus (contenido) | ✅ Completo | 525 chunks, buena cobertura temática |
| RAG Corpus (schema en git) | 🔴 Corrupto | HEAD tiene mixed schema — sobreescribir con build limpio |
| RAG Index (ChromaDB) | ⚠️ Pendiente rebuild | Nuevos directorios sin commitar |
| Instalación (`install.sh`) | ⚠️ Username hardcoded | Funcional pero no portable |
| Privacidad | ⚠️ 1 archivo con datos | `logs/flame_import_result.txt` en git |
| Licencias | ⚠️ Sin NOTICE | CC BY-NC-SA no declarado explícitamente |
| Portabilidad | ✅ Buena | Config via `config.json`, env vars para ports |
| Documentación | ✅ Buena | README completo, CLAUDE.md apropiado |
| Seguridad en reposo | ✅ OK | `config.json` gitignoreado |

---

*Informe generado el 2026-03-10 — flame-mcp Phase D audit*
