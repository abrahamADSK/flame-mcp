# flame-mcp — Claude Agent Instructions

## What this project is
An MCP server that lets Claude control Autodesk Flame 2026 via natural language.
Use the `execute_python` MCP tool to run Python inside Flame.
Do NOT communicate with the bridge socket directly — the MCP tool handles that internally.

---

## Rules — read before every task

1. **MANDATORY: Use dedicated tools — execute_python is the last resort.**
   For every question or task, go through this checklist IN ORDER before
   reaching for `execute_python`:

   | Question type | Dedicated tool |
   |---|---|
   | Project name, resolution, fps, bit depth | `get_project_info()` |
   | What libraries exist? | `list_libraries()` |
   | What reels are in library X? | `list_reels(library_name)` |
   | What clips are in library/reel X? | `list_clips(library_name, reel_name)` |
   | Desktop structure (reel groups, reels, clips) | `list_desktop_reels()` |
   | Batch groups on desktop | `list_batch_groups()` |
   | All Flame projects on this workstation | `list_all_projects()` |
   | Clip technical metadata | `get_clip_metadata(library, reel, clip)` |
   | Currently selected items in Flame | `get_selected_clips()` |
   | IFFFS/Wiretap node tree | `flame_wiretap_tree(path)` |
   | Log files | `list_flame_logs()` / `read_flame_log()` |
   | Bridge status | `ping()` |
   | Flame version | `get_flame_version()` |

   Only call `execute_python` when **none** of the above tools cover the operation.
   Do NOT use `execute_python` to answer a question that a dedicated tool handles —
   even if writing the code feels faster. The dedicated tools are validated,
   handle edge cases, and avoid API guessing.

   ❌ Wrong: `execute_python("print(flame.projects.current_project.name)")`
   ✅ Right: `get_project_info()`

   ❌ Wrong: `execute_python("for l in ws.libraries: print(l.name)")`
   ✅ Right: `list_libraries()`

2. **MANDATORY: Call `search_flame_docs` before every `execute_python`.**
   Before writing any `execute_python` code, call `search_flame_docs` with a short
   description (e.g. `"import clip to reel"`, `"list libraries"`). It returns the
   relevant API section (~200 tokens vs 1500 for the full file). Only fall back to
   reading `FLAME_API.md` directly if the search returns nothing useful.

   DO NOT skip this step even if you think you know the API. Common API traps:
   - `flame.selection` → does NOT exist. Use `flame.media_panel.selected_entries`
   - `project.libraries` → returns None. Use `ws.libraries` via `current_workspace`
   - `flame.batch.render()` → crashes Flame. Use `schedule_idle_event`

3. **Use low-relevance RAG results — do NOT discard them.**
   If `search_flame_docs` returns results below 60% relevance, still read and use
   the best match. Low relevance means the terminology differs, not that the API
   doesn't cover it. Try 2–3 alternate queries before concluding a pattern is
   undocumented:
   - "save desktop to library" → also try "copy reel group", "media panel copy"
   - "delete folder" → also try "remove folder", "library folders"
   - "ripple delete" → also try "close gap", "remove segment", "timeline gap"
   If all searches return < 30%, proceed with the best match and call `learn_pattern`
   after success.

4. **Exclude hidden system libraries.**
   `ws.libraries` includes two internal libraries NOT visible to the user:
   `"Timeline FX"` and `"Grabbed References"`. Always filter them out:
   ```python
   HIDDEN = {"Timeline FX", "Grabbed References"}
   visible = [l for l in ws.libraries if str(l.name) not in HIDDEN]
   ```
   Never list, modify, or delete these libraries unless the user explicitly names them.

5. **Dry-run before EVERY delete — no exceptions.**
   Never call `flame.delete()` without first doing a separate `execute_python`
   inspection that prints exactly what WOULD be deleted (names, types, counts).
   Then present that list to the user and say "Confirma para proceder / Confirm to
   proceed." Do NOT execute the actual delete until the user replies "confirm",
   "sí", "yes", "ok" or equivalent. This rule applies even when the user's request
   sounds unambiguous.

   Example flow:
   ```
   User: "delete all empty reels"
   Claude: [execute_python] → prints list of candidate reels
   Claude: "I would delete: Reel 2 (0 clips), Reel 4 (0 clips). Confirm?"
   User: "confirm"
   Claude: [execute_python] → actually deletes
   ```

6. **Inspect before acting.**
   Before any destructive or structural operation (delete, move, copy, rename),
   run one `execute_python` inspection first to confirm the hierarchy. Confirm
   the target object EXISTS before trying to delete or modify it.
   ```python
   ws = flame.projects.current_project.current_workspace
   lib = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
   if lib:
       print("folders:", [str(f.name) for f in (lib.folders or [])])
       print("reels:", [str(r.name) for r in lib.reels])
   ```

7. **Check Learned Patterns second.**
   After reading the API reference, check `## Learned Patterns` below. If a
   matching pattern exists, use it directly. Do not improvise if a known-good
   solution is documented.

8. **STOP after 2 failures — do not keep trying.**
   If the same sub-task fails twice (two `execute_python` calls return errors for
   the same goal), STOP immediately. Do NOT generate a third variation. Instead,
   report to the user:
   - What was attempted (code + error)
   - What is unclear or missing
   - What information would help proceed
   Never make more than 3 `execute_python` calls for the same sub-task.

9. **Self-update on success.**
   When a Flame task completes successfully, immediately append the working code
   to `## Learned Patterns` with a short description and date. Also call
   `learn_pattern()` when RAG coverage was low (< 60%) so the index is updated
   for future sessions.

10. **Mark failures.**
    If a pattern causes a timeout, crash, or wrong result, add a ❌ note next to
    it explaining why, so it is not retried.

11. **Keep code minimal.**
    Flame's Python environment is sensitive. Prefer short, direct API calls.
    Avoid long loops or anything that could block Flame's main thread.

12. **Always return output.**
    Every `execute_python` call should end with a `print()` or return value so
    Claude can confirm success or failure.

13. **Use Background Reactor for renders.**
    Long renders block Flame's UI. Always use `render_option="Background Reactor"`
    unless the user explicitly requests Foreground.

14. **Debug via logs when execute_python errors.**
    When a tool returns an unexpected error or Flame crashes, call
    `read_flame_log("flame.log", lines=50, grep="Error|Traceback|Python")` to
    get the actual crash trace before retrying. Also check wiretap.log for IFFFS
    errors. Call `session_stats()` when the user asks about efficiency or after
    long multi-step tasks.

---

## Flame Environment

- **Application:** Autodesk Flame 2026, macOS
- **Bridge:** Internal — use the `execute_python` MCP tool. Do NOT write Bash/shell
  commands to talk to the bridge socket; that bypasses tool-selection enforcement.
- **Entry point:** the `flame` module is always available inside the bridge
- **Qt:** Flame 2026 uses PySide6 (not PySide2)
- **Python:** the Flame-embedded Python interpreter (not system Python)
- **Hook path:** `/opt/Autodesk/shared/python/flame_mcp_bridge.py`

---

## LLM Backend & Model Selection

flame-mcp supports multiple LLM backends via the model selector widget in the Flame panel.

### Recommended local model: Qwen3.5 9B (`qwen3.5-mcp`)
- **Tool calling**: 97.5% accuracy (1st of 13 models, eval J.D. Hodges)
- **Context window**: 262K tokens
- **Memory**: 6.6 GB (Q4_K_M)
- **Multimodal**: vision-capable
- **Modelfile**: `qwen3.5-mcp` is a custom Modelfile derived from `qwen3.5:9b` with
  `num_ctx 8192`, `temperature 0.7`, `top_p 0.8`, `top_k 20`.
  Available on glorfindel and Mac M5 Pro.
- **Mac 24GB fallback**: `qwen3.5:4b` (direct, no custom Modelfile)
- **Ollama API note**: requires `"think": false` in each request to disable thinking mode.

### Available backends
| Backend | Label in combo | URL | Notes |
|---|---|---|---|
| `anthropic` | Claude Sonnet/Opus | Anthropic API | Default, needs internet + API key |
| `ollama` | 🖥 models | `config.json → ollama_url` | glorfindel RTX 3090, LAN |
| `ollama_mac` | 🍎 models | `config.json → ollama_mac_url` | Mac-local, offline |

### Prerequisites for local models
```bash
# Install Ollama (macOS)
brew install ollama
brew services start ollama

# Pull the model
ollama pull qwen3.5:9b
# On Mac 24GB (fallback):
ollama pull qwen3.5:4b
```

---

## Deploy workflow — after every code change

### One-time setup: symlink `flame_mcp_bridge.py` (recommended)

Flame loads the bridge hook from the hardcoded path
`/opt/Autodesk/shared/python/flame_mcp_bridge.py`. On a fresh workstation,
symlink that path to the working tree so every `git pull` deploys the
latest bridge instantly — no per-change `cp` required:

```bash
sudo ln -sf ~/Projects/flame-mcp/hooks/flame_mcp_bridge.py \
           /opt/Autodesk/shared/python/flame_mcp_bridge.py
```

Verify:
```bash
ls -la /opt/Autodesk/shared/python/flame_mcp_bridge.py
# Should show: ... -> /Users/<you>/Projects/flame-mcp/hooks/flame_mcp_bridge.py
```

The M4 Pro workstation has this symlink in place since 2026-03-09. You
still need **MCP Bridge → Reload hook** in Flame after each bridge
change, because the Flame Python process caches the compiled bytecode
of the hook module in memory — the symlink serves the source file, not
the bytecode. Reload forces `importlib.reload` inside Flame.

### `src/flame_mcp/server.py` only:
```bash
git push && pkill -f flame_mcp.server
```
Claude Desktop respawns the server automatically with the new code.

### `hooks/flame_mcp_bridge.py` only:

**With symlink in place** (recommended — current M4 Pro setup):
```bash
git push
```
Then in Flame: **MCP Bridge → Reload hook**

**Without symlink** (fresh machine, pre-setup fallback):
```bash
git push && cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/flame_mcp_bridge.py
```
Then in Flame: **MCP Bridge → Reload hook**

The `cp` is idempotent — running it on a host that already has the
symlink reports "identical" and does nothing, so you can script either
workflow without branching.

### Both files:

**With symlink**:
```bash
git push && pkill -f flame_mcp.server
```

**Without symlink**:
```bash
git push && pkill -f flame_mcp.server && cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/flame_mcp_bridge.py
```

Then in Flame: **MCP Bridge → Reload hook**

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
**Task:** Render a batch group (e.g. Substance Noise) from the bridge
**Works:** ✅ (calling `flame.batch.render()` directly crashes Flame ❌)

```python
import flame, os

result_file = os.path.expanduser("~/flame_render_result.txt")

def do_render():
    try:
        flame.batch.render(render_option="Background Reactor")
        msg = "OK: render started"
    except Exception as e:
        msg = f"ERROR: {e}"
    with open(result_file, 'w') as f:
        f.write(msg)

# Make sure the correct batch is open before calling this
flame.schedule_idle_event(do_render)
print("Render scheduled via idle event.")
```

Then read `~/flame_render_result.txt` in a separate call to confirm.

### Substance Noise crashes Flame — 2026-03-05
**Task:** Create a coloured noise clip with a Substance Noise node in Batch
**Works:** ❌ — A Substance Noise node connected to Render crashes Flame when rendering (even via schedule_idle_event). The result file is never created.
**Pending alternative:** use `Colour Source` + `Gradient` or generate frames externally and import them.

---

## MANDATORY: Tool pre-approval stays in sync automatically

flame-mcp's `install.sh` (Step 8) extracts tool names dynamically from `src/flame_mcp/server.py` via `ast.parse`. New `@mcp.tool()` functions are picked up automatically on next install.

**RULE — NON-NEGOTIABLE:**
- Every `@mcp.tool()` function MUST follow the standard decorator pattern so ast.parse detects it
- If you rename a tool function, the old name becomes orphaned in users' settings.json — note this in the commit message
- After adding/removing tools, run `bash -n install.sh` to verify syntax
- Run the install.sh Python snippet standalone to verify detection: `grep -c "mcp__flame__" ~/.claude/settings.json`

This ensures users never get permission prompts on first use of new tools.
