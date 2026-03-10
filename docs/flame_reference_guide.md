# flame-mcp Reference Guide — Key Patterns

> Extracted from the flame-mcp Reference Guide (Version 2026.1, March 2026).
> Contains: MCP workflow rules, dangerous crash patterns, common Flame code recipes.

---

## MCP Tool Workflow Rules (Mandatory)

These rules are embedded in the MCP server instructions. Every Claude context (Code, Desktop, Cowork)
receives them automatically — no per-client configuration needed.

```
Rule 1: ALWAYS call search_flame_docs BEFORE execute_python.
        Use a short query: "delete reel", "import clip", "create batch group".
        Skip only for trivially simple calls (e.g. print project name).

Rule 2: Use the correct object hierarchy:
        ws = flame.projects.current_project.current_workspace   ← CORRECT
        ws.libraries                                            ← CORRECT
        flame.projects.current_project.libraries                ← WRONG (returns None)

Rule 3: Never call flame.batch.render() directly — it crashes Flame.
        Use: flame.schedule_idle_event(render_fn)

Rule 4: Always end execute_python code with print().
        Results are only visible through stdout capture.

Rule 5: Keep code minimal — long loops can block Flame's main thread.

Rule 6: On failure, do NOT retry the same approach. Try a different method.

Rule 7: ALWAYS call session_stats as the LAST tool call of every response.

Rule 8: SELF-IMPROVEMENT — if search_flame_docs returned max score < 60%
        AND execute_python succeeded:
        → call learn_pattern(description, code) BEFORE session_stats.
```

---

## Object Hierarchy — Always Start Here

The correct traversal path from project root to media objects:

```python
import flame

p    = flame.projects.current_project       # PyProject
ws   = p.current_workspace                  # PyWorkspace
desk = ws.desktop                           # PyDesktop

# Libraries are on workspace, NOT on project
libs = ws.libraries                         # list[PyLibrary]

# Reels, clips, folders inside a library
lib     = libs[0]
reels   = lib.reels                         # list[PyReel]
clips   = lib.clips                         # list[PyClip]  (direct clips)
folders = lib.folders                       # list[PyFolder]
```

IMPORTANT: `flame.projects.current_project.libraries` returns `None` — always use `ws.libraries`.

---

## flame.delete() — Universal Delete Function

`flame.delete()` works on any Media Panel object: clips, reels, folders, libraries, sequences, batch groups.
Always wrap in a list for multiple objects.

```python
import flame
ws = flame.projects.current_project.current_workspace

# Delete a reel by name
lib  = next(l for l in ws.libraries if l.name == "Default Library")
reel = next(r for r in lib.reels if r.name == "OLD_REEL")
flame.delete(reel)

# Delete multiple reels at once
targets = {"TEST", "TEST2", "DESKTOP_TEST"}
to_del  = [r for r in lib.reels if r.name in targets]
flame.delete(to_del)
print(f"Deleted: {[r.name for r in to_del]}")

# Delete a folder by name
folder = next(f for f in lib.folders if f.name == "OLD_FOLDER")
flame.delete(folder)

# Delete a library
old_lib = next(l for l in ws.libraries if l.name == "TEMP_LIB")
flame.delete(old_lib)

# Delete all clips inside a reel
reel = next(r for r in lib.reels if r.name == "DAILIES")
flame.delete(list(reel.clips))
print(f"Cleared {len(reel.clips)} clips")
```

Key: always use `next((x for x in col if x.name == 'NAME'), None)` and check for None before calling `flame.delete()`.

---

## Create Library and Reel

```python
import flame
ws   = flame.projects.current_project.current_workspace
lib  = ws.create_library("Incoming")
reel = lib.create_reel("Raw")
print(f"Created: {lib.name} / {reel.name}")
```

---

## List Libraries and Reels

```python
import flame
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    print(f"{lib.name}   {len(lib.reels)} reels, {len(lib.clips)} clips")
    for reel in lib.reels:
        print(f"  Reel: {reel.name}  ({len(reel.clips)} clips)")
    for folder in lib.folders:
        print(f"  Folder: {folder.name}")
```

---

## Import Media

```python
import flame
ws   = flame.projects.current_project.current_workspace
lib  = next(l for l in ws.libraries if l.name == "Default Library")
reel = next(r for r in lib.reels if r.name == "Incoming")
clips = flame.import_clips("/path/to/file.mov", reel)
print(f"Imported: {[c.name for c in clips]}")
```

Note: `flame.import_clips(path, reel)` — first arg is a file path string, second is a PyReel target.

---

## List All Flame Projects

```python
import os, flame

# List all projects from filesystem (no API, no crash)
base     = "/opt/Autodesk/project"
projects = sorted(d for d in os.listdir(base)
                  if os.path.isdir(os.path.join(base, d)) and d != "project.db")
for p in projects:
    print(p)

# Currently open project
print(f"Active: {flame.projects.current_project.name}")
```

---

## Render via Background Reactor (Non-blocking)

NEVER call `flame.batch.render()` directly — it blocks and can crash Flame's UI.
Always use `flame.schedule_idle_event()`:

```python
import flame

def do_render():
    flame.batch.render(render_option="Background Reactor")
    print("Render queued")

flame.schedule_idle_event(do_render)
print("Render scheduled")
```

---

## Safety — Known Crash Patterns

`execute_python` automatically scans code for these patterns before sending to Flame.
If detected, the code is **never executed** — a blocked message is returned with the correct alternative.

### len(flame.projects) — TypeError
```python
# WRONG — PyProjectSelector has no len(). Raises TypeError.
len(flame.projects)

# CORRECT
flame.projects.current_project.name  # active project name
```

### for p in flame.projects — TypeError
```python
# WRONG — PyProjectSelector is not iterable.
for p in flame.projects:
    print(p)

# CORRECT — enumerate from filesystem
import os
projects = sorted(d for d in os.listdir('/opt/Autodesk/project')
                  if os.path.isdir(os.path.join('/opt/Autodesk/project', d)))
for p in projects:
    print(p)
```

### flame.PyClipSelector — not subscriptable
```python
# WRONG — PyClipSelector is not subscriptable.
flame.PyClipSelector[0]

# CORRECT
flame.projects.current_project  # use directly
```

### flame.projects.current_project.libraries — returns None
```python
# WRONG — AttributeError / returns None
flame.projects.current_project.libraries

# CORRECT
ws = flame.projects.current_project.current_workspace
ws.libraries  # this works
```

### flame.batch.render() — freezes UI
```python
# WRONG — blocks Flame's main thread. Freezes or crashes UI.
flame.batch.render()

# CORRECT — schedule via idle event with Background Reactor
def do_render():
    flame.batch.render(render_option="Background Reactor")
flame.schedule_idle_event(do_render)
```

### import wiretap — crash-prone
```python
# WRONG — wiretap module is crash-prone for general scripting.
import wiretap

# CORRECT — use the standard flame module
import flame
# Call search_flame_docs for patterns.
```

### dir(flame) — speculative API discovery
```python
# WRONG — speculative API discovery leads to untested code.
dir(flame)

# CORRECT — call search_flame_docs(query) to get verified patterns only.
```

---

## RAG Relevance Score Reference

| Score range | Meaning | Action |
|---|---|---|
| ≥ 70% | Pattern well-documented. High confidence. | Use directly. No learn_pattern needed. |
| 60–69% | Partial match. Pattern may be incomplete. | Proceed cautiously. Consider learn_pattern if code differs. |
| < 60% | Pattern NOT documented. Low confidence. | Warn user inline. Call learn_pattern after successful execute_python. |
| < 45% | No relevant documentation found. | Reason from first principles. learn_pattern critical after success. |

---

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Claude can't connect to Flame | Bridge not running, or hook not installed | Open Flame > MCP Bridge > Status. Verify hook is in /opt/Autodesk/shared/python/. Run: `lsof -i :4444` |
| Low RAG scores (< 60%) on common operations | Pattern not documented in FLAME_API.md | flame-mcp auto-learns after a successful run. Or manually: `python rag/build_index.py` after editing FLAME_API.md |
| Claude Chat doesn't open | ANTHROPIC_API_KEY missing | Check logs/flame_mcp_bridge.log. Set ANTHROPIC_API_KEY in environment or .env file. |
| Hook changes not taking effect | Flame still running old version of hook | Copy hook: `sudo cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/`. Then: MCP Bridge → Reload hook (no Flame restart needed). |
| Port 4444 in use | Another process is using port 4444 | Change BRIDGE_PORT in both flame_mcp_bridge.py and flame_mcp_server.py. Values must match. |
| StopIteration in bridge log | next() call on empty iterator | Add fallback: `next((x for x in col if x.name == 'NAME'), None)` and check for None before flame.delete(). |
| RAG index not found error | Index hasn't been built | `cd flame-mcp && source .venv/bin/activate && python rag/build_index.py` |

---

## Flame Hook Search Paths

Flame loads Python hooks in this order:
1. `$DL_PYTHON_HOOK_PATH`
2. `/opt/Autodesk/shared/python/`
3. `/opt/Autodesk//python/`
4. `/opt/Autodesk/user//python/`

Installing to `shared/python/` ensures compatibility across all Flame versions.

---

## Compatibility Matrix

| Flame version | Internal Python | Qt binding | Chat widget |
|---|---|---|---|
| 2023 | 3.9.7 | PySide2 | ✓ |
| 2024 | 3.9.x | PySide2 | ✓ |
| 2025 | 3.11.x | PySide2 | ✓ |
| 2026 | 3.11.5 | PySide6 | ✓ (fully tested) |
| 2027 preview | 3.13.3 | PySide6 | ✓ |

The embedded chat widget detects PySide2 vs PySide6 at runtime and imports accordingly.
The event filter class is built at runtime as a proper QObject subclass — PySide6 strictly requires this.

---

## Flame Hook Search Paths

Flame hook search paths (loaded in this order): `$DL_PYTHON_HOOK_PATH` → `/opt/Autodesk/shared/python/` → `/opt/Autodesk//python/` → `/opt/Autodesk/user//python/`. This project installs to `shared/python/` so it works across all Flame versions.
