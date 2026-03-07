# flame-mcp — Claude Agent Instructions

## What this project is
An MCP server that lets Claude control Autodesk Flame 2026 via natural language.
Claude runs as an external agent; the `execute_python` tool sends Python code into
a TCP bridge (127.0.0.1:4444) that executes it live inside Flame.

---

## Rules — read before every task

1. **Call `search_flame_docs` first.** Before writing any `execute_python` code,
   call the `search_flame_docs` MCP tool with a short description of what you need
   (e.g. `"import clip to reel"`, `"list libraries"`). It returns the relevant API
   section from the local index (~200 tokens vs 1500 for the full file). Only fall
   back to reading `FLAME_API.md` directly if the search returns nothing useful.

2. **Use low-relevance RAG results — do NOT discard them.** If `search_flame_docs`
   returns results below 60% relevance, still read and use the best match. Low
   relevance means the terminology differs, not that the API doesn't cover it.
   Try 2–3 alternate queries before concluding a pattern is undocumented:
   - "save desktop to library" → also try "copy reel group", "media panel copy"
   - "delete folder" → also try "remove folder", "library folders"
   - "ripple delete" → also try "close gap", "remove segment", "timeline gap"
   If all searches return < 30%, proceed with the best match and call `learn_pattern`
   after success.

3. **Exclude hidden system libraries.** `ws.libraries` includes two internal
   libraries that are NOT visible to the user in the Flame interface:
   `"Timeline FX"` and `"Grabbed References"`. Always filter them out:
   ```python
   HIDDEN = {"Timeline FX", "Grabbed References"}
   visible = [l for l in ws.libraries if str(l.name) not in HIDDEN]
   ```
   Never list, modify, or delete these libraries unless the user explicitly names them.

4. **Dry-run before EVERY delete — no exceptions.** Never call `flame.delete()`
   without first doing a separate `execute_python` inspection that prints exactly
   what WOULD be deleted (names, types, counts). Then present that list to the user
   and say "Confirma para proceder / Confirm to proceed." Do NOT execute the actual
   delete until the user replies "confirm", "sí", "yes", "ok" or equivalent.
   This rule applies even when the user's request sounds unambiguous.

   Example flow:
   ```
   User: "delete all empty reels"
   Claude: [execute_python] → prints list of candidate reels
   Claude: "I would delete: Reel 2 (0 clips), Reel 4 (0 clips). Confirm?"
   User: "confirm"
   Claude: [execute_python] → actually deletes
   ```

4. **Inspect before acting.** Before any destructive or structural operation
   (delete, move, copy, rename), run one `execute_python` inspection first to
   confirm the hierarchy: list libraries, reel groups, folders, or clips.
   Confirm the target object EXISTS before trying to delete or modify it.
   Example inspection:
   ```python
   import flame
   ws = flame.projects.current_project.current_workspace
   lib = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
   if lib:
       print("folders:", [str(f.name) for f in (lib.folders or [])])
       print("reels:", [str(r.name) for r in lib.reels])
   ```

4. **Check Learned Patterns second.** After reading the API reference, check
   `## Learned Patterns` below. If a matching pattern exists, use it directly.
   Do not improvise if a known-good solution is documented.

5. **STOP after 2 failures — do not keep trying.** If the same sub-task fails
   twice (two `execute_python` calls return errors for the same goal), STOP
   immediately. Do NOT generate a third variation. Instead, report to the user:
   - What was attempted (code + error)
   - What is unclear or missing
   - What information would help proceed
   Never make more than 3 `execute_python` calls for the same sub-task.
   Repeated silent retries with variations waste the user's time and risk
   destabilising Flame.

6. **Self-update on success.** When a Flame task completes successfully, immediately
   append the working code to `## Learned Patterns` with a short description and date.
   Use the format defined in that section. Also call `learn_pattern()` when RAG
   coverage was low (< 60%) so the index is updated for future sessions.

7. **Mark failures.** If a pattern causes a timeout, crash, or wrong result, add a ❌
   note next to it explaining why, so it is not retried.

8. **Keep code minimal.** Flame's Python environment is sensitive. Prefer short, direct
   API calls. Avoid long loops or anything that could block Flame's main thread.

9. **Always return output.** Every `execute_python` call should end with a `print()` or
   return value so Claude can confirm success or failure.

10. **Use Background Reactor for renders.** Long renders block Flame's UI. Always use
    `render_option="Background Reactor"` unless the user explicitly requests Foreground.

11. **Always call `session_stats` last.** After every response that uses any Flame tool,
    call `session_stats` as the final tool call to display token usage and RAG savings.

---

## Flame Environment

- **Application:** Autodesk Flame 2026, macOS
- **Bridge:** TCP socket on `127.0.0.1:4444` — JSON payload `{"code": "..."}`,
  returns `{"result": "..."}` or `{"error": "..."}`
- **Entry point:** the `flame` module is always available inside the bridge
- **Qt:** Flame 2026 uses PySide6 (not PySide2)
- **Python:** the Flame-embedded Python interpreter (not system Python)
- **Hook path:** `/opt/Autodesk/shared/python/flame_mcp_bridge.py`

---

## API References

### Primary — embedded cheatsheet (read this, do not fetch URLs)
- **`FLAME_API.md`** in this project — full cheatsheet with patterns, gotchas,
  and common code snippets for Flame 2026. Always read this file first.

### Fallback — fetch only if FLAME_API.md doesn't cover the operation
- Official Python API: https://help.autodesk.com/view/FLAME/2026/ENU/?guid=Flame_API_Flame_Python_API_html
- Wiretap SDK: https://help.autodesk.com/view/FLAME/2026/ENU/?guid=Flame_API_Wiretap_SDK_html

### Wiretap — when to use it
The Python `flame` module covers most operations. Use Wiretap only when:
- The Python API doesn't expose what you need (e.g. raw metadata XML)
- You need bulk library operations via CLI tools without Python
- You need to access the Flame storage filesystem structure directly
- Bridge from Python to Wiretap: `obj.get_wiretap_node_id()` and
  `flame.find_by_wiretap_node_id(node_id)`
- Wiretap server runs at `localhost` inside Flame

### Community
- Logik Forum: https://forum.logik.tv
- Autodesk Community: https://forums.autodesk.com/t5/flame/ct-p/area_flame

---

## Learned Patterns

> Format for new entries:
> ```
> ### [Short description] — YYYY-MM-DD
> **Task:** what was requested
> **Works:** ✅ or ❌ (reason)
> ```python
> # working code here
> ```
> ```

<!-- Claude appends new entries below this line -->

### Render batch via schedule_idle_event — 2026-03-05
**Task:** Renderizar un batch group (ej. Substance Noise) desde el bridge
**Works:** ✅ (llamada directa a `flame.batch.render()` crashea Flame ❌)

```python
import flame, os

result_file = os.path.expanduser("~/Projects/flame-mcp/logs/flame_render_result.txt")

def do_render():
    try:
        flame.batch.render(render_option="Background Reactor")
        msg = "OK: render lanzado"
    except Exception as e:
        msg = f"ERROR: {e}"
    with open(result_file, 'w') as f:
        f.write(msg)

# Asegurarse de que el batch correcto está abierto antes de llamar esto
flame.schedule_idle_event(do_render)
print("Render programado via idle event.")
```

Luego leer `~/Projects/flame-mcp/logs/flame_render_result.txt` con una llamada separada para confirmar.

### Substance Noise crashea Flame — 2026-03-05
**Task:** Crear clip de ruido coloreado con nodo Substance Noise en Batch
**Works:** ❌ — El nodo Substance Noise conectado a Render crashea Flame al hacer render (incluso via schedule_idle_event). El archivo de resultado nunca se crea.
**Alternativa pendiente:** usar `Colour Source` + `Gradient` o generar frames externos e importarlos.

