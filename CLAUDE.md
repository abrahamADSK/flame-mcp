# flame-mcp — Claude Agent Instructions

## What this project is
An MCP server that lets Claude control Autodesk Flame 2026 via natural language.
Claude runs as an external agent; the `execute_python` tool sends Python code into
a TCP bridge (127.0.0.1:4444) that executes it live inside Flame.

---

## Rules — read before every task

1. **Read FLAME_API.md first.** Before writing any `execute_python` code, read
   `FLAME_API.md` in this project. It contains the complete API cheatsheet for
   Flame 2026. Use it as the primary reference — do not guess method names.

2. **Check Learned Patterns second.** After reading the API reference, check
   `## Learned Patterns` below. If a matching pattern exists, use it directly.
   Do not improvise if a known-good solution is documented.

3. **Self-update on success.** When a Flame task completes successfully, immediately
   append the working code to `## Learned Patterns` with a short description and date.
   Use the format defined in that section.

4. **Mark failures.** If a pattern causes a timeout, crash, or wrong result, add a ❌
   note next to it explaining why, so it is not retried.

5. **Keep code minimal.** Flame's Python environment is sensitive. Prefer short, direct
   API calls. Avoid long loops or anything that could block Flame's main thread.

6. **Always return output.** Every `execute_python` call should end with a `print()` or
   return value so Claude can confirm success or failure.

7. **Use Background Reactor for renders.** Long renders block Flame's UI. Always use
   `render_option="Background Reactor"` unless the user explicitly requests Foreground.

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
import flame

result_file = "/tmp/flame_render_result.txt"

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

Luego leer `/tmp/flame_render_result.txt` con una llamada separada para confirmar.

