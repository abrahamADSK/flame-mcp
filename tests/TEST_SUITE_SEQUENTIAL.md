# Test Suite Secuencial — flame-mcp

> **Instrucciones**: Ejecuta cada prueba **en orden** desde Claude (Claude Desktop, Claude Code, o Cowork).
> Cada nivel depende de lo creado en el nivel anterior. No saltes pruebas.
> Al final de cada prueba, verifica el resultado esperado antes de continuar.

---

## Nivel 0 — Conexión y Diagnóstico

Pruebas que no modifican nada en Flame. Solo verifican que el bridge funciona.

### T0.1 · Ping al bridge
```
¿Está Flame conectado? Haz un ping.
```
**Resultado esperado**: "connected" + versión de Flame.
**Herramienta MCP**: `ping`

### T0.2 · Versión de Flame
```
¿Qué versión de Flame está corriendo?
```
**Resultado esperado**: String tipo "2026.0.1" o similar.
**Herramienta MCP**: `get_flame_version`

### T0.3 · Información del proyecto activo
```
Dame la información del proyecto activo: nombre, resolución, frame rate y bit depth.
```
**Resultado esperado**: Nombre del proyecto, resolución (ej. 1920x1080), fps (ej. 23.976), bit depth (ej. 16fp).
**Herramienta MCP**: `get_project_info`

### T0.4 · Listar todos los proyectos
```
¿Qué proyectos de Flame hay disponibles en esta estación?
```
**Resultado esperado**: Lista de proyectos con indicador de cuál está activo.
**Herramienta MCP**: `list_all_projects`

### T0.5 · Estadísticas de sesión RAG
```
Muéstrame las estadísticas de la sesión actual.
```
**Resultado esperado**: Contador de llamadas, tokens consumidos, tokens ahorrados.
**Herramienta MCP**: `session_stats`

---

## Nivel 1 — Lectura del Estado Actual (Solo Inspección)

Pruebas de solo lectura que examinan el contenido existente en Flame.

### T1.1 · Listar bibliotecas
```
¿Qué bibliotecas existen en el proyecto actual?
```
**Resultado esperado**: Lista de bibliotecas con conteo de reels y folders.
**Herramienta MCP**: `list_libraries`

### T1.2 · Listar reels de una biblioteca
```
Muéstrame los reels de la primera biblioteca que encontraste.
```
**Resultado esperado**: Nombres de reels dentro de la biblioteca.
**Herramienta MCP**: `list_reels`

### T1.3 · Listar clips
```
¿Qué clips hay en esa biblioteca? Muéstrame los primeros 20.
```
**Resultado esperado**: Lista de clips con nombres.
**Herramienta MCP**: `list_clips`

### T1.4 · Estructura completa del desktop
```
Muéstrame toda la estructura del desktop: reel groups, reels y clips.
```
**Resultado esperado**: Árbol jerárquico completo del desktop.
**Herramienta MCP**: `list_desktop_reels`

### T1.5 · Listar batch groups
```
¿Hay batch groups en el desktop? Lístalos con su número de nodos y reels.
```
**Resultado esperado**: Lista de batch groups (o "No batch groups found").
**Herramienta MCP**: `list_batch_groups`

### T1.6 · Metadata de un clip (requiere T1.3)
```
Del primer clip que encontraste antes, dame sus metadatos completos: resolución, frame rate, duración, timecode, bit depth.
```
**Resultado esperado**: Detalle técnico del clip (width, height, duration, frame_rate, etc.).
**Herramienta MCP**: `get_clip_metadata`

### T1.7 · Clips seleccionados en Flame
```
¿Qué clips tengo seleccionados ahora mismo en Flame?
```
**Nota**: Selecciona algo manualmente en Flame antes de lanzar esta prueba.
**Resultado esperado**: Nombre y tipo de los items seleccionados.
**Herramienta MCP**: `get_selected_clips`

### T1.8 · Explorar árbol Wiretap
```
Explora el árbol Wiretap en la raíz /projects.
```
**Resultado esperado**: Lista de nodos IFFFS (UUIDs de proyectos).
**Herramienta MCP**: `flame_wiretap_tree`

---

## Nivel 2 — Sistema RAG y Documentación

Pruebas del sistema de búsqueda de conocimiento.

### T2.1 · Búsqueda básica en docs
```
Busca en la documentación cómo acceder a las bibliotecas de un proyecto.
```
**Resultado esperado**: Fragmentos del corpus explicando `ws.libraries` (NO `project.libraries`).
**Herramienta MCP**: `search_flame_docs`

### T2.2 · Búsqueda de patrón peligroso
```
Busca en la documentación cómo hacer un render en batch.
```
**Resultado esperado**: Debe mencionar `schedule_idle_event` y advertir contra `flame.batch.render()` directo.
**Herramienta MCP**: `search_flame_docs`

### T2.3 · Búsqueda de operación avanzada
```
Busca cómo crear nodos en un batch group y conectarlos entre sí.
```
**Resultado esperado**: Patrones con `create_node`, `connect_nodes`, tipos de nodos disponibles.
**Herramienta MCP**: `search_flame_docs`

### T2.4 · Búsqueda de export
```
Busca cómo exportar un clip con PyExporter.
```
**Resultado esperado**: Patrón con `schedule_idle_event` + `PyExporter`, nunca llamada directa.
**Herramienta MCP**: `search_flame_docs`

### T2.5 · Búsqueda de timeline/segmentos
```
¿Cómo puedo acceder a los segmentos de una secuencia en el timeline?
```
**Resultado esperado**: Información sobre `PySequence`, `PySegment`, `versions`.
**Herramienta MCP**: `search_flame_docs`

---

## Nivel 3 — Logs y Diagnóstico del Sistema

### T3.1 · Listar logs disponibles
```
¿Qué archivos de log tiene Flame disponibles?
```
**Resultado esperado**: Lista de archivos en /opt/Autodesk/logs con tamaño y fecha.
**Herramienta MCP**: `list_flame_logs`

### T3.2 · Leer últimas líneas del log principal
```
Muéstrame las últimas 30 líneas del log principal de Flame.
```
**Resultado esperado**: Líneas recientes del log de Flame.
**Herramienta MCP**: `read_flame_log`

### T3.3 · Filtrar errores en log
```
Busca errores recientes en el log de Flame (las últimas 200 líneas, filtrando por "ERROR" o "Traceback").
```
**Resultado esperado**: Solo líneas que contengan errores, o "no matches" si no hay.
**Herramienta MCP**: `read_flame_log` con parámetro `grep`

---

## Nivel 4 — Ejecución de Código Simple (Solo Lectura)

Primera vez que se usa `execute_python`. Solo operaciones de lectura.

### T4.1 · Nombre del proyecto vía Python
```
Ejecuta código Python dentro de Flame para imprimir el nombre del proyecto actual.
```
**Resultado esperado**: `flame.projects.current_project.name` impreso correctamente.
**Herramienta MCP**: `execute_python`
**Validación RAG**: Debe llamar a `search_flame_docs` antes.

### T4.2 · Contar clips en todas las bibliotecas
```
Con Python en Flame, cuenta cuántos clips totales hay en cada biblioteca del workspace.
```
**Código esperado (aproximado)**:
```python
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    count = sum(len(list(r.clips)) for r in lib.reels)
    print(f"{str(lib.name)}: {count} clips")
```

### T4.3 · Inspeccionar atributos de un clip
```
Con Python, encuentra el primer clip de la primera biblioteca y muéstrame todos sus atributos disponibles (usa dir() filtrado).
```
**Validación**: No debe intentar acceder a `project.libraries` (patrón peligroso bloqueado).

### T4.4 · Listar reel groups del desktop con Python
```
Con Python, lista todos los reel groups del desktop mostrando cuántos reels tiene cada uno.
```
**Código esperado**: Acceso via `ws.desktop.reel_groups`.

---

## Nivel 5 — Creación de Estructuras Organizativas

Aquí empezamos a modificar cosas en Flame. Todo lo creado en este nivel será necesario después.

### T5.1 · Crear un reel group en el desktop
```
Crea un reel group en el desktop llamado "MCP_Test_Group".
```
**Código esperado**: `ws.desktop.create_reel_group("MCP_Test_Group")`
**Verificación**: Después pide `list_desktop_reels` para confirmar que aparece.

### T5.2 · Crear reels dentro del reel group (requiere T5.1)
```
Dentro del reel group "MCP_Test_Group", crea 3 reels: "Sources", "Comps" y "Renders".
```
**Código esperado**: `rg.create_reel("Sources")` (x3)
**Verificación**: `list_desktop_reels` debe mostrar los 3 reels.

### T5.3 · Crear una carpeta en una biblioteca
```
En la primera biblioteca, crea una carpeta llamada "MCP_Tests".
```
**Código esperado**: `lib.create_folder("MCP_Tests")`
**Verificación**: `list_libraries` o `list_reels` para confirmar.

### T5.4 · Crear un reel dentro de la carpeta (requiere T5.3)
```
Dentro de la carpeta "MCP_Tests" que acabamos de crear, crea un reel llamado "Test_Reel_01".
```
**Verificación**: Confirmar que el reel existe dentro de la carpeta.

---

## Nivel 6 — Creación de Batch Groups y Nodos

### T6.1 · Crear un batch group (requiere T5.1)
```
Crea un batch group llamado "MCP_Batch_Test" con 2 reels de schematic.
```
**Código esperado**:
```python
ws = flame.projects.current_project.current_workspace
bg = ws.desktop.create_batch_group("MCP_Batch_Test", nb_reels=2)
print(f"Batch group creado: {str(bg.name)}")
```
**Verificación**: `list_batch_groups` debe mostrar "MCP_Batch_Test".

### T6.2 · Abrir el batch group y entrar (requiere T6.1)
```
Abre el batch group "MCP_Batch_Test" y entra en él con go_to.
```
**Código esperado**:
```python
bg.open()
flame.batch.go_to(bg)
```
**Nota crítica**: El corpus documenta que `go_to()` requiere `open()` previo.

### T6.3 · Crear nodos en el batch (requiere T6.2)
```
En el batch group abierto, crea un nodo Write File y un nodo Resize.
```
**Código esperado**: `flame.batch.create_node("Write File")`, `flame.batch.create_node("Resize")`
**Verificación**: Pedir `list_batch_groups` — debe mostrar nodos.

### T6.4 · Conectar nodos (requiere T6.3)
```
Conecta el nodo Resize al nodo Write File en el batch group activo.
```
**Código esperado**: `flame.batch.connect_nodes(resize_node, write_node)`
**Verificación**: Confirmar visualmente en Flame o con query Python.

### T6.5 · Listar todos los nodos del batch (requiere T6.2)
```
Muéstrame todos los nodos que hay ahora en el batch group "MCP_Batch_Test", con sus tipos.
```
**Código esperado**: Iteración sobre `flame.batch.nodes` imprimiendo `name` y `type`.

---

## Nivel 7 — Operaciones con Clips y Secuencias

### T7.1 · Crear una secuencia vacía (requiere T5.2)
```
Crea una secuencia vacía llamada "MCP_Sequence_Test" en el reel "Comps" del reel group "MCP_Test_Group".
```
**Código esperado**: `reel.create_sequence("MCP_Sequence_Test")`

### T7.2 · Inspeccionar la secuencia creada (requiere T7.1)
```
Muéstrame las propiedades de la secuencia "MCP_Sequence_Test": duración, frame rate, resolución, número de versiones.
```
**Validación**: Debe usar `search_flame_docs` para encontrar atributos de PySequence.

### T7.3 · Duplicar un clip existente
```
Si hay clips en alguna biblioteca, duplica el primero y ponle el nombre "MCP_Clip_Copy".
```
**Código esperado**: `flame.duplicate(clip)` + renombrar con `new_clip.name = "MCP_Clip_Copy"`.
**Nota**: Si no hay clips, esta prueba se salta (el sistema debe detectarlo).

### T7.4 · Leer metadatos de segmentos de timeline (requiere clip existente)
```
Si hay alguna secuencia en el proyecto, muéstrame los segmentos de su timeline principal con sus shot names, duraciones y timecodes.
```
**Código esperado**: Acceso a `seq.versions[0].tracks[0].segments` iterando atributos.

---

## Nivel 8 — Operaciones sobre Atributos y Metadatos

### T8.1 · Renombrar un reel (requiere T5.2)
```
Renombra el reel "Sources" del reel group "MCP_Test_Group" a "Source_Material".
```
**Código esperado**: `reel.name = "Source_Material"`
**Verificación**: `list_desktop_reels` para confirmar.

### T8.2 · Cambiar el shot_name de un segmento (requiere secuencia existente)
```
Si hay una secuencia con segmentos, cambia el shot_name del primer segmento a "VFX_010".
```
**Código esperado**: `segment.shot_name = "VFX_010"`

### T8.3 · Leer y modificar el comment de un clip (requiere clip existente)
```
Lee el campo comment del primer clip que encuentres. Si está vacío, escribe "Tested via MCP".
```
**Código esperado**: `clip.comment = "Tested via MCP"` si estaba vacío.

### T8.4 · Consultar colour space de un clip
```
Del primer clip disponible, dime su colour space, scan format y aspect ratio.
```
**Validación**: Debe acceder a atributos como `colour_space`, `scan_format`, `ratio`.

---

## Nivel 9 — Operaciones Avanzadas y Batch Setup

### T9.1 · Guardar un batch setup (requiere T6.2)
```
Guarda el setup del batch group "MCP_Batch_Test" en /var/tmp/mcp_test_setup.batch.
```
**Código esperado**: `bg.save_setup("/var/tmp/mcp_test_setup.batch")`
**Verificación**: Confirmar que el archivo existe con `os.path.exists`.

### T9.2 · Crear un nuevo batch group y cargar el setup (requiere T9.1)
```
Crea un nuevo batch group llamado "MCP_Batch_Loaded", ábrelo, y carga el setup guardado en /var/tmp/mcp_test_setup.batch.
```
**Código esperado**:
```python
bg2 = ws.desktop.create_batch_group("MCP_Batch_Loaded")
bg2.open()
flame.batch.go_to(bg2)
bg2.load_setup("/var/tmp/mcp_test_setup.batch")
```

### T9.3 · Iterar un batch setup (requiere T9.2)
```
Crea una iteración del batch group "MCP_Batch_Loaded".
```
**Código esperado**: `bg.iterate()`

### T9.4 · Consultar contexts de un batch group
```
Muéstrame los contexts (vistas) registrados en "MCP_Batch_Test".
```
**Código esperado**: `bg.contexts()` — devuelve diccionario de Context IDs.

---

## Nivel 10 — Pruebas de Seguridad (Patrones Peligrosos)

Estas pruebas verifican que el sistema **bloquea** operaciones peligrosas.

### T10.1 · Intentar iterar flame.projects (DEBE FALLAR)
```
Ejecuta este código en Flame: for p in flame.projects: print(p.name)
```
**Resultado esperado**: BLOQUEADO con mensaje explicando que `flame.projects` no es iterable.

### T10.2 · Intentar flame.batch.render() directo (DEBE FALLAR)
```
Ejecuta: flame.batch.render()
```
**Resultado esperado**: BLOQUEADO con alternativa `schedule_idle_event`.

### T10.3 · Intentar import wiretap (DEBE FALLAR)
```
Ejecuta: import wiretap
```
**Resultado esperado**: BLOQUEADO por patrón peligroso.

### T10.4 · Intentar project.libraries (DEBE FALLAR)
```
Ejecuta: libs = flame.projects.current_project.libraries
```
**Resultado esperado**: BLOQUEADO con alternativa `ws.libraries`.

### T10.5 · Intentar flame.projects[0] (DEBE FALLAR)
```
Ejecuta: p = flame.projects[0]
```
**Resultado esperado**: BLOQUEADO — `flame.projects` no es subscriptable.

### T10.6 · Intentar replace_desktop (DEBE FALLAR)
```
Ejecuta: ws.replace_desktop(ws.desktop)
```
**Resultado esperado**: BLOQUEADO — método interno que puede corromper el workspace.

---

## Nivel 11 — Limpieza (Deshacer Todo lo Creado)

> **IMPORTANTE**: Ejecuta este nivel al terminar todas las pruebas para dejar Flame limpio.

### T11.1 · Eliminar batch groups de test
```
Elimina los batch groups "MCP_Batch_Test" y "MCP_Batch_Loaded" del desktop.
```
**Código esperado**: `flame.delete(bg)` para cada batch group encontrado.

### T11.2 · Eliminar el reel group de test (requiere T11.1)
```
Elimina el reel group "MCP_Test_Group" del desktop.
```
**Código esperado**: `flame.delete(rg)`

### T11.3 · Eliminar la carpeta de test de la biblioteca
```
Elimina la carpeta "MCP_Tests" de la primera biblioteca.
```
**Código esperado**: `flame.delete(folder)`

### T11.4 · Eliminar el clip duplicado (si se creó en T7.3)
```
Si existe el clip "MCP_Clip_Copy", elimínalo.
```
**Código esperado**: `flame.delete(clip)` con búsqueda previa.

### T11.5 · Limpiar archivos temporales
```
Elimina el archivo /var/tmp/mcp_test_setup.batch si existe.
```
**Código esperado**: `os.remove("/var/tmp/mcp_test_setup.batch")`

### T11.6 · Verificación final
```
Muéstrame la estructura completa del desktop y las bibliotecas para confirmar que todo quedó limpio.
```
**Herramientas MCP**: `list_desktop_reels` + `list_libraries`

---

## Resumen de Cobertura

| Nivel | Pruebas | Herramientas MCP Cubiertas | Tipo |
|-------|---------|---------------------------|------|
| 0 | 5 | ping, get_flame_version, get_project_info, list_all_projects, session_stats | Diagnóstico |
| 1 | 8 | list_libraries, list_reels, list_clips, list_desktop_reels, list_batch_groups, get_clip_metadata, get_selected_clips, flame_wiretap_tree | Inspección |
| 2 | 5 | search_flame_docs (x5) | RAG |
| 3 | 3 | list_flame_logs, read_flame_log (x2) | Logs |
| 4 | 4 | execute_python (solo lectura, x4) | Código RO |
| 5 | 4 | execute_python (crear estructuras, x4) | Creación |
| 6 | 5 | execute_python (batch/nodos, x5) | Batch |
| 7 | 4 | execute_python (clips/secuencias, x4) | Timeline |
| 8 | 4 | execute_python (atributos, x4) | Metadatos |
| 9 | 4 | execute_python (setup avanzado, x4) | Avanzado |
| 10 | 6 | execute_python (bloqueos de seguridad, x6) | Seguridad |
| 11 | 6 | execute_python + herramientas dedicadas (limpieza, x6) | Limpieza |
| **Total** | **58** | **18/18 herramientas** (100%) | |

## Dependencias entre Niveles

```
Nivel 0 ──→ Nivel 1 ──→ Nivel 2 (independiente)
                │         Nivel 3 (independiente)
                │
                └──→ Nivel 4 ──→ Nivel 5 ──→ Nivel 6 ──→ Nivel 9
                                    │           │
                                    └──→ Nivel 7 ┘──→ Nivel 8
                                                         │
                            Nivel 10 (independiente) ─────┘
                                                         │
                                                    Nivel 11 (final)
```

## Notas de Ejecución

1. **Antes de empezar**: Asegúrate de que Flame está abierto con un proyecto cargado.
2. **Niveles 2, 3, 10**: Pueden ejecutarse en cualquier momento (son independientes).
3. **Niveles 5-9**: Son secuenciales y acumulativos — no saltar.
4. **Nivel 11**: SIEMPRE ejecutar al final para limpiar.
5. **Si una prueba falla**: Anota el error exacto y continúa con la siguiente del mismo nivel si es posible.
6. **Tiempo estimado**: 30-45 minutos para la suite completa.
