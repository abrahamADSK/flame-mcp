# FLAME-MCP TEST PLAN — QUICK REFERENCE

## A. MCP TOOLS SUMMARY TABLE

| Tool Name | Type | Params | Returns | Safe | Read/Write |
|-----------|------|--------|---------|------|------------|
| execute_python | CORE | code, timeout | output+error | ✓ (checked) | W |
| get_project_info | INFO | — | name, fps, res, bit | ✓ | R |
| list_libraries | INFO | — | lib names + counts | ✓ | R |
| list_reels | INFO | lib_name | reel names + clips | ✓ | R |
| list_clips | INFO | lib, reel, limit | clip names + duration | ✓ | R |
| list_desktop_reels | INFO | — | reel_groups > reels > clips | ✓ | R |
| list_batch_groups | INFO | — | batch names + reels/nodes | ✓ | R |
| list_all_projects | INFO | — | project names + active | ✓ | R |
| get_clip_metadata | INFO | lib, reel, clip | full clip metadata | ✓ | R |
| get_selected_clips | INFO | — | current selection | ✓ | R |
| flame_wiretap_tree | NAVG | path | IFFFS tree nodes | ✓ | R |
| get_flame_version | INFO | — | version string | ✓ | R |
| ping | DIAG | — | connected/error | ✓ | R |
| search_flame_docs | RAG | query | top-5 chunks + score | ✓ | R |
| learn_pattern | SELF | desc, code | pattern added/staged | ✓ | R+W |
| session_stats | DIAG | — | usage summary | ✓ | R |
| list_flame_logs | INFO | — | log files + size | ✓ | R |
| read_flame_log | INFO | name, lines, grep | log content (tail) | ✓ | R |

**Legend**: 
- Type: CORE=execution, INFO=inspection, NAVG=navigation, RAG=knowledge, DIAG=diagnostics, SELF=self-improvement
- R=read-only, W=write-only, R+W=read-write
- Safe: ✓ (checked/safe), ✓ (checked) means pattern detection applied

---

## B. DANGEROUS PATTERNS CHECKLIST (18 PATTERNS)

| # | Pattern | Symptom | Fix |
|---|---------|---------|-----|
| 1 | `len(flame.projects)` | Crash: not a list | Use `flame.projects.current_project` |
| 2 | `for x in flame.projects` | Crash: not iterable | Use `os.listdir('/opt/Autodesk/project')` |
| 3 | `flame.projects[0]` | Crash: not subscriptable | Use `flame.projects.current_project` |
| 4 | `flame.projects.current_project.libraries` | Returns None | Use `ws = ...current_workspace; ws.libraries` |
| 5 | `flame.batch.render()` | Blocks main thread | Use `schedule_idle_event(lambda: render(...))` |
| 6 | `import wiretap` | Crash: unsafe module | Use standard flame API |
| 7 | `WireTapServerHandle` | Crash: C-bindings unsafe | Use standard flame API |
| 8 | `.createNode(), .getNumChildren()` | Crash: WireTap unsafe | Use standard flame API |
| 9 | `ws.replace_desktop()` | Crash: corrupts state | Use `ws.desktop` + reel_groups |
| 10 | `dir(flame)` | Speculative/crashing | Use `search_flame_docs()` |
| 11 | `.clear()` on objects | Crash: raw C destructor | Use `flame.delete(item)` on each |
| 12 | `flame.clear_desktop()` | Doesn't exist | Use `flame.delete(reel)` loop |
| 13 | `for reel in reels: flame.delete(reel)` | Crash: zero reels | Keep ≥1 reel: `delete(list(reels)[:-1])` |
| 14 | `flame.delete(list(rg.reels))` | Crash: zero reels | Use `delete(list(reels)[:-1])` |
| 15 | `.name == "string"` | Silent fail: .name is PyAttribute | Use `str(reel.name) == "string"` |
| 16 | `.name.startswith()` | AttributeError | Use `str(clip.name).startswith('VFX_')` |
| 17 | `next(x for x in reels if ...)` | StopIteration crash | Use `next((x for x in reels if ...), None)` |
| 18 | `seg.delete(), track.remove_gap()` | Don't exist (Flame 2026) | Rebuild sequence (gap close pattern) |

---

## C. CORPUS SOURCES (668 CHUNKS)

| Source | Chunks | Focus | Key Content |
|--------|--------|-------|------------|
| FLAME_API.md | 294 | Full API reference | 68 classes, module functions, hierarchy |
| flame_advanced_api.md | 78 | Action/Color/Timeline FX | Advanced node types, export workflows |
| flame_code_samples.md | 46 | Production examples | Hook registration, UI actions, real code |
| flame_community_workflows.md | 23 | Operator workflows | Desktop setup, reel creation, naming |
| flame_cookbook_official.md | 22 | Official recipes | Import, reformat, render examples |
| flame_ocr_patterns.md | 15 | Basic traversal | Workspace access, library listing |
| flame_ocr_patterns_v2.md | 23 | Batch hooks | Naming hooks, Python hook path |
| flame_openclip_patterns.md | 8 | Watch-folder/XML | Multi-version clips, OpenClip format |
| flame_reference_guide.md | 30 | Method signatures | API reference-level documentation |
| flame_segment_timeline_api.md | 61 | Timeline editing | PySegment, gap closure, ripple delete |
| flame_vocabulary.md | 8 | Terminology | Operator language → API mapping |
| flame_youtube_patterns.md | 60 | Advanced workflows | Logik Live sessions, real patterns |

---

## D. CORE OBJECT HIERARCHY

```
flame.projects.current_project (PyProject)
  └─ current_workspace (PyWorkspace)
      ├─ libraries (PyLibrary[])
      │   ├─ reels (PyReel[])
      │   │   └─ clips (PyClip/PySequence[])
      │   │       └─ segments (PySegment[]) [for PySequence only]
      │   ├─ folders (PyFolder[])
      │   └─ reel_groups (PyReelGroup[])
      └─ desktop (PyDesktop)
          ├─ reel_groups (PyReelGroup[])
          │   └─ reels (PyReel[])
          └─ batch_groups (PyBatch[])
              ├─ reels (PyReel[])
              └─ nodes (PyNode variants)
```

**Critical access pattern**: `ws = flame.projects.current_project.current_workspace`
- ❌ `flame.projects.current_project.libraries` → WRONG (returns None)
- ✓ `flame.projects.current_project.current_workspace.libraries` → CORRECT

---

## E. SAFETY ANNOTATIONS

```python
_RO  = ToolAnnotations(readOnlyHint=True,  destructiveHint=False)  # 15 tools
_RW  = ToolAnnotations(readOnlyHint=False, destructiveHint=False)  # 2 tools (learn_pattern, session_stats)
_DST = ToolAnnotations(readOnlyHint=False, destructiveHint=True)   # 1 tool (execute_python)
```

---

## F. CRITICAL CONSTRAINTS

### Object Hierarchy Access
- **Valid**: `ws.libraries`, `rg.reels`, `reel.clips`
- **Invalid**: `project.libraries` (returns None)
- **Safe wrap**: Always `str(obj.name)` before string operations

### Reel Group Deletion
- **MUST keep ≥1 reel in desktop reel groups**
- ❌ `flame.delete(list(rg.reels))` - Crashes if reel group is on desktop
- ✓ `flame.delete(list(rg.reels)[:-1])` - Keep last reel
- ✓ `flame.delete([r for r in rg.reels if r.name != 'KEEP_ME'])` - Filter

### Long Operations
- **MUST use** `schedule_idle_event()` for:
  - `flame.batch.render()`
  - `PyExporter().export()`
  - Large media imports
  - Timeline rebuilds

### Timeline Editing (Flame 2026)
- ❌ `seg.delete()` - Doesn't exist
- ❌ `track.remove_gap()` - Doesn't exist
- ❌ `track.ripple()` - Doesn't exist
- ✓ **Rebuild algorithm**: Iterate non-gap segments, overwrite back-to-back

### PyAttribute Gotchas
- `.name` returns `PyAttribute` object, NOT a string
- ❌ `if reel.name == "Reel 1"` - Silent fail (always False)
- ✓ `if str(reel.name) == "Reel 1"` - Works
- ❌ `if reel.name.startswith("VFX_")` - AttributeError
- ✓ `if str(reel.name).startswith("VFX_")` - Works

### Next Pattern (Generator Pitfall)
- ❌ `reel = next(r for r in rg.reels if r.name == "OFFLINE")` - StopIteration crash if not found
- ✓ `reel = next((r for r in rg.reels if r.name == "OFFLINE"), None)` - Safe, returns None if not found
- ✓ Then check: `if reel is not None: reel.do_something()`

---

## G. BRIDGE EXECUTION MODEL

### TCP Bridge (flame_mcp_bridge.py)
- **Host**: 127.0.0.1 (localhost only)
- **Port**: 4444 (override via `$FLAME_BRIDGE_PORT`)
- **Transport**: JSON protocol over TCP socket
- **Request**: `{"code": "...", "timeout": 15}`
- **Response**: `{"status": "ok"|"error", "output": "...", "error": "..."}`

### Code Execution Inside Flame
- Runs in Python hook context (not main thread by default)
- Access to full `flame` module + all standard libraries
- Output capture: stdout + stderr concatenated
- Timeout: Default 15 seconds (customizable 1-300)

### Safety Checks
1. **Regex check** (18 dangerous patterns) — runs BEFORE TCP send
2. **AST check** (obfuscated calls) — runs BEFORE TCP send
3. **Pattern-specific validation** — runs inside Flame if needed
4. If any check fails → Error returned, code NOT executed

---

## H. RAG SYSTEM DETAILS

### Search Mechanism
- **Engine**: Chroma VectorDB (semantic + metadata filtering)
- **Query**: Natural language (e.g., "how to import media")
- **Results**: Top 5 chunks + max relevance score (0-100%)
- **Cache**: Within-session identical query cache (A12 pattern)

### Learned Patterns Flow
- **Trusted models** (Sonnet, Opus):
  - Call `learn_pattern(description, code)`
  - → Appends to FLAME_API.md
  - → Rebuilds RAG index in background thread
  - → Cleared on index rebuild
  
- **Read-only models** (Haiku):
  - Call `learn_pattern(description, code)`
  - → Stages to `rag/candidates.json`
  - → Human review required
  - → Trusted model must promote to FLAME_API.md

### Index Rebuild
- **Trigger**: learn_pattern() or manual `python rag/build_index.py`
- **Duration**: Background thread (non-blocking)
- **Lock file**: `rag/.rebuilding` (A4 pattern)
- **Cache invalidation**: Clears session cache during rebuild
- **Rebuild note**: "⏳ RAG index rebuilding — results may be stale"

### Coverage Notes
- **Low coverage** (score < 60%):
  - Trusted: "⚠️ Pattern may not be documented. Call learn_pattern(...) if code succeeds."
  - Read-only: "⚠️ Low coverage. Switch to Sonnet/Opus to save patterns."

---

## I. TEST MATRIX

```
18 Tools × 8-9 test cases each = ~150 test cases

Breakdown:
├─ Read-Only Tools (15 tools)
│  ├─ Parameter validation (3 tests each)
│  ├─ Output format (2 tests each)
│  └─ Edge cases (3 tests each)
│  └─ = ~135 tests
├─ Dangerous Pattern Detection (1 tool: execute_python)
│  ├─ Regex patterns (18 tests, 1 each)
│  ├─ AST detection (2 tests)
│  ├─ Error message quality (1 test)
│  └─ = ~21 tests
└─ Integration (2 tests)
   ├─ search_flame_docs → execute_python workflow
   └─ learn_pattern → RAG rebuild workflow
   └─ = ~2 tests

Coverage target: 100% of MCP tools × all parameter combinations × all error cases
```

---

## J. QUICK VALIDATION CHECKLIST

### Before Running Tests
- [ ] Flame 2026 running on workstation
- [ ] Bridge installed: `/opt/Autodesk/shared/python/flame_mcp_bridge.py`
- [ ] Bridge active (check Flame menu: MCP Bridge → Status = Active)
- [ ] MCP server running: `python flame_mcp_server.py`
- [ ] RAG index built: `python rag/build_index.py` (668 chunks indexed)
- [ ] Test project loaded with fixtures (see TEST_PLAN_COMPREHENSIVE.md section 8.3)
- [ ] /opt/Autodesk/logs/ directory exists with recent flame.log

### During Tests
- [ ] All 18 tools invoke successfully (ping first)
- [ ] No dangerous patterns execute (all blocked)
- [ ] RAG search returns top 5 results + score
- [ ] Error messages include safe alternatives
- [ ] Timeout parameter works (1-300 range)
- [ ] Token counting accurate (session_stats)

### After Tests
- [ ] All tests pass (0 failures)
- [ ] Coverage matrix 100% complete
- [ ] Documentation updated with findings
- [ ] New patterns (if any) added to FLAME_API.md

---

