# flame-mcp — Claude Agent Instructions

## What this project is
An MCP server that lets Claude control Autodesk Flame 2026 via natural language.
Claude runs as an external agent; the `execute_python` tool sends Python code into
a TCP bridge (127.0.0.1:4444) that executes it live inside Flame.

---

## Rules — read before every task

1. **Check Learned Patterns first.** Before attempting any Flame task, read the
   `## Learned Patterns` section. If a matching pattern exists, use it directly.
   Do not improvise if a known-good solution is documented.

2. **Self-update on success.** When a Flame task completes successfully, immediately
   append the working code to `## Learned Patterns` with a short description and date.
   Use the format defined in that section.

3. **Mark failures.** If a pattern causes a timeout, crash, or wrong result, add a ❌
   note next to it explaining why, so it is not retried.

4. **Research before guessing.** When tackling an unfamiliar Flame operation, research
   it using the sources listed in `## API References` before attempting trial-and-error.

5. **Keep code minimal.** Flame's Python environment is sensitive. Prefer short, direct
   API calls. Avoid long loops or anything that could block Flame's main thread.

6. **Always return output.** Every `execute_python` call should end with a `print()` or
   return value so Claude can confirm success or failure.

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

When researching how to perform a Flame operation, consult these sources in order:

### 1. Flame Python API (primary)
- **Official docs:** https://help.autodesk.com/view/FLAME/2026/ENU/?guid=Flame_API_Flame_Python_API_html
- Covers: projects, libraries, reels, clips, sequences, batch, timeline, import/export
- The `flame` module mirrors the Flame object hierarchy exactly
- Key objects: `flame.projects`, `flame.project.current_project`,
  `flame.project.current_project.current_workspace`,
  `flame.project.current_project.current_workspace.desktop`

### 2. Wiretap Python API (for library and media manipulation)
- Wiretap is Autodesk's lower-level SDK for accessing Flame's media library
- Python bindings are available inside Flame at `import wiretap` (may require
  the Wiretap SDK to be installed separately)
- Wiretap gives access to: projects, libraries, clips, and metadata at a lower
  level than the `flame` module — useful when the high-level API is missing a feature
- Wiretap documentation and SDK:
  https://help.autodesk.com/view/FLAME/2026/ENU/?guid=Flame_API_Wiretap_SDK_html
- Key Wiretap concepts: server (`WireTapServer`), node paths (`/projects/...`),
  clip handles, metadata XML
- Wiretap server address inside Flame is typically `localhost`
- Example pattern:
  ```python
  import libwiretap
  server = libwiretap.WireTapServer('localhost', libwiretap.WireTapClientAPI())
  ```

### 3. Community references
- Logik Forum: https://forum.logik.tv — search for specific operations
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

