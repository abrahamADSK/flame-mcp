# Sequential Test Suite — flame-mcp

> **Instructions**: Run each test **in order** from Claude (Claude Desktop, Claude Code, or Cowork).
> Each level depends on what was created in the previous level. Do not skip tests.
> After each test, verify the expected result before continuing.

---

## Level 0 — Connection & Diagnostics

Tests that do not modify anything in Flame. They only verify the bridge is working.

### T0.1 · Ping the bridge
```
Is Flame connected? Ping it.
```
**Expected result**: "connected" + Flame version string.
**MCP tool**: `ping`

### T0.2 · Flame version
```
What version of Flame is currently running?
```
**Expected result**: Version string like "2026.0.1" or similar.
**MCP tool**: `get_flame_version`

### T0.3 · Active project info
```
Give me the active project information: name, resolution, frame rate, and bit depth.
```
**Expected result**: Project name, resolution (e.g. 1920x1080), fps (e.g. 23.976), bit depth (e.g. 16fp).
**MCP tool**: `get_project_info`

### T0.4 · List all projects
```
What Flame projects are available on this workstation?
```
**Expected result**: List of projects with an indicator showing which one is active.
**MCP tool**: `list_all_projects`

### T0.5 · RAG session statistics
```
Show me the current session statistics.
```
**Expected result**: Call counter, tokens consumed, tokens saved.
**MCP tool**: `session_stats`

---

## Level 1 — Current State Reading (Inspection Only)

Read-only tests that examine existing content in Flame.

### T1.1 · List libraries
```
What libraries exist in the current project?
```
**Expected result**: List of libraries with reel and folder counts.
**MCP tool**: `list_libraries`

### T1.2 · List reels from a library
```
Show me the reels in the first library you found.
```
**Expected result**: Reel names within the library.
**MCP tool**: `list_reels`

### T1.3 · List clips
```
What clips are in that library? Show me the first 20.
```
**Expected result**: List of clips with names.
**MCP tool**: `list_clips`

### T1.4 · Full desktop structure
```
Show me the full desktop structure: reel groups, reels, and clips.
```
**Expected result**: Complete hierarchical tree of the desktop.
**MCP tool**: `list_desktop_reels`

### T1.5 · List batch groups
```
Are there batch groups on the desktop? List them with their node and reel counts.
```
**Expected result**: List of batch groups (or "No batch groups found").
**MCP tool**: `list_batch_groups`

### T1.6 · Clip metadata (requires T1.3)
```
From the first clip you found earlier, give me its full metadata: resolution, frame rate, duration, timecode, bit depth.
```
**Expected result**: Technical detail of the clip (width, height, duration, frame_rate, etc.).
**MCP tool**: `get_clip_metadata`

### T1.7 · Currently selected clips in Flame
```
What clips do I have selected right now in Flame?
```
**Note**: Manually select something in Flame before running this test.
**Expected result**: Name and type of the selected items.
**MCP tool**: `get_selected_clips`

### T1.8 · Explore Wiretap tree
```
Explore the Wiretap tree at the root /projects.
```
**Expected result**: List of IFFFS nodes (project UUIDs).
**MCP tool**: `flame_wiretap_tree`

---

## Level 2 — RAG System & Documentation

Tests for the knowledge search system.

### T2.1 · Basic docs search
```
Search the documentation for how to access a project's libraries.
```
**Expected result**: Corpus fragments explaining `ws.libraries` (NOT `project.libraries`).
**MCP tool**: `search_flame_docs`

### T2.2 · Dangerous pattern search
```
Search the documentation for how to render in batch.
```
**Expected result**: Must mention `schedule_idle_event` and warn against direct `flame.batch.render()`.
**MCP tool**: `search_flame_docs`

### T2.3 · Advanced operation search
```
Search for how to create nodes in a batch group and connect them together.
```
**Expected result**: Patterns with `create_node`, `connect_nodes`, available node types.
**MCP tool**: `search_flame_docs`

### T2.4 · Export search
```
Search for how to export a clip using PyExporter.
```
**Expected result**: Pattern with `schedule_idle_event` + `PyExporter`, never a direct call.
**MCP tool**: `search_flame_docs`

### T2.5 · Timeline/segments search
```
How can I access the segments of a sequence in the timeline?
```
**Expected result**: Information about `PySequence`, `PySegment`, `versions`.
**MCP tool**: `search_flame_docs`

---

## Level 3 — Logs & System Diagnostics

### T3.1 · List available logs
```
What log files does Flame have available?
```
**Expected result**: File list from /opt/Autodesk/logs with size and date.
**MCP tool**: `list_flame_logs`

### T3.2 · Read last lines of main log
```
Show me the last 30 lines of the main Flame log.
```
**Expected result**: Recent lines from the Flame log.
**MCP tool**: `read_flame_log`

### T3.3 · Filter errors in log
```
Search for recent errors in the Flame log (last 200 lines, filtering for "ERROR" or "Traceback").
```
**Expected result**: Only lines containing errors, or "no matches" if there are none.
**MCP tool**: `read_flame_log` with `grep` parameter

---

## Level 4 — Simple Code Execution (Read-Only)

First time using `execute_python`. Read-only operations only.

### T4.1 · Project name via Python
```
Execute Python code inside Flame to print the current project name.
```
**Expected result**: `flame.projects.current_project.name` printed correctly.
**MCP tool**: `execute_python`
**RAG validation**: Must call `search_flame_docs` first.

### T4.2 · Count clips across all libraries
```
Using Python in Flame, count how many total clips are in each library of the workspace.
```
**Expected code (approximate)**:
```python
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    count = sum(len(list(r.clips)) for r in lib.reels)
    print(f"{str(lib.name)}: {count} clips")
```

### T4.3 · Inspect clip attributes
```
Using Python, find the first clip in the first library and show me all its available attributes (use filtered dir()).
```
**Validation**: Must not attempt to access `project.libraries` (blocked dangerous pattern).

### T4.4 · List desktop reel groups with Python
```
Using Python, list all desktop reel groups showing how many reels each one has.
```
**Expected code**: Access via `ws.desktop.reel_groups`.

---

## Level 5 — Creating Organizational Structures

Here we start modifying things in Flame. Everything created at this level will be needed later.

### T5.1 · Create a reel group on the desktop
```
Create a reel group on the desktop called "MCP_Test_Group".
```
**Expected code**: `ws.desktop.create_reel_group("MCP_Test_Group")`
**Verification**: Then ask `list_desktop_reels` to confirm it appears.

### T5.2 · Create reels inside the reel group (requires T5.1)
```
Inside the reel group "MCP_Test_Group", create 3 reels: "Sources", "Comps", and "Renders".
```
**Expected code**: `rg.create_reel("Sources")` (x3)
**Verification**: `list_desktop_reels` should show all 3 reels.

### T5.3 · Create a folder in a library
```
In the first library, create a folder called "MCP_Tests".
```
**Expected code**: `lib.create_folder("MCP_Tests")`
**Verification**: `list_libraries` or `list_reels` to confirm.

### T5.4 · Create a reel inside the folder (requires T5.3)
```
Inside the "MCP_Tests" folder we just created, create a reel called "Test_Reel_01".
```
**Verification**: Confirm the reel exists inside the folder.

---

## Level 6 — Batch Group & Node Creation

### T6.1 · Create a batch group (requires T5.1)
```
Create a batch group called "MCP_Batch_Test" with 2 schematic reels.
```
**Expected code**:
```python
ws = flame.projects.current_project.current_workspace
bg = ws.desktop.create_batch_group("MCP_Batch_Test", nb_reels=2)
print(f"Batch group created: {str(bg.name)}")
```
**Verification**: `list_batch_groups` should show "MCP_Batch_Test".

### T6.2 · Open and enter the batch group (requires T6.1)
```
Open the batch group "MCP_Batch_Test" and enter it with go_to.
```
**Expected code**:
```python
bg.open()
flame.batch.go_to(bg)
```
**Critical note**: The corpus documents that `go_to()` requires a prior `open()`.

### T6.3 · Create nodes in batch (requires T6.2)
```
In the currently open batch group, create a Write File node and a Resize node.
```
**Expected code**: `flame.batch.create_node("Write File")`, `flame.batch.create_node("Resize")`
**Verification**: Ask `list_batch_groups` — should show nodes.

### T6.4 · Connect nodes (requires T6.3)
```
Connect the Resize node to the Write File node in the active batch group.
```
**Expected code**: `flame.batch.connect_nodes(resize_node, write_node)`
**Verification**: Confirm visually in Flame or with a Python query.

### T6.5 · List all nodes in the batch (requires T6.2)
```
Show me all the nodes currently in the "MCP_Batch_Test" batch group, with their types.
```
**Expected code**: Iteration over `flame.batch.nodes` printing `name` and `type`.

---

## Level 7 — Clip & Sequence Operations

### T7.1 · Create an empty sequence (requires T5.2)
```
Create an empty sequence called "MCP_Sequence_Test" in the "Comps" reel of the "MCP_Test_Group" reel group.
```
**Expected code**: `reel.create_sequence(name='MCP_Sequence_Test')` (with
`duration=flame.PyTime(N)` appended when a frame count is requested)

### T7.2 · Inspect the created sequence (requires T7.1)
```
Show me the properties of "MCP_Sequence_Test": duration, frame rate, resolution, number of versions.
```
**Validation**: Must use `search_flame_docs` to find PySequence attributes.

### T7.3 · Duplicate an existing clip
```
If there are clips in any library, duplicate the first one and name it "MCP_Clip_Copy".
```
**Expected code**: `flame.duplicate(clip)` + rename with `new_clip.name = "MCP_Clip_Copy"`.
**Note**: If no clips exist, this test is skipped (the system should detect this).

### T7.4 · Read timeline segment metadata (requires existing clip)
```
If there is any sequence in the project, show me the segments of its main timeline with their shot names, durations, and timecodes.
```
**Expected code**: Access `seq.versions[0].tracks[0].segments` iterating attributes.

---

## Level 8 — Attribute & Metadata Operations

### T8.1 · Rename a reel (requires T5.2)
```
Rename the "Sources" reel in the "MCP_Test_Group" reel group to "Source_Material".
```
**Expected code**: `reel.name = "Source_Material"`
**Verification**: `list_desktop_reels` to confirm.

### T8.2 · Change a segment's shot_name (requires existing sequence)
```
If there is a sequence with segments, change the first segment's shot_name to "VFX_010".
```
**Expected code**: `segment.shot_name = "VFX_010"`

### T8.3 · Read and modify a clip's comment (requires existing clip)
```
Read the comment field of the first clip you find. If it's empty, write "Tested via MCP".
```
**Expected code**: `clip.comment = "Tested via MCP"` if it was empty.

### T8.4 · Query clip colour space
```
From the first available clip, tell me its colour space, scan format, and aspect ratio.
```
**Validation**: Must access attributes like `colour_space`, `scan_format`, `ratio`.

---

## Level 9 — Advanced Operations & Batch Setup

### T9.1 · Save a batch setup (requires T6.2)
```
Save the "MCP_Batch_Test" batch group setup to /var/tmp/mcp_test_setup.batch.
```
**Expected code**: `bg.save_setup("/var/tmp/mcp_test_setup.batch")`
**Verification**: Confirm the file exists with `os.path.exists`.

### T9.2 · Create a new batch group and load the setup (requires T9.1)
```
Create a new batch group called "MCP_Batch_Loaded", open it, and load the setup saved at /var/tmp/mcp_test_setup.batch.
```
**Expected code**:
```python
bg2 = ws.desktop.create_batch_group("MCP_Batch_Loaded")
bg2.open()
flame.batch.go_to(bg2)
bg2.load_setup("/var/tmp/mcp_test_setup.batch")
```

### T9.3 · Iterate a batch setup (requires T9.2)
```
Create an iteration of the "MCP_Batch_Loaded" batch group.
```
**Expected code**: `bg.iterate()`

### T9.4 · Query batch group contexts
```
Show me the contexts (views) registered in "MCP_Batch_Test".
```
**Expected code**: `bg.contexts()` — returns dictionary of Context IDs.

---

## Level 10 — Security Tests (Dangerous Patterns)

These tests verify that the system **blocks** dangerous operations.

### T10.1 · Attempt to iterate flame.projects (MUST FAIL)
```
Execute this code in Flame: for p in flame.projects: print(p.name)
```
**Expected result**: BLOCKED with message explaining `flame.projects` is not iterable.

### T10.2 · Attempt direct flame.batch.render() (MUST FAIL)
```
Execute: flame.batch.render()
```
**Expected result**: BLOCKED with `schedule_idle_event` alternative.

### T10.3 · Attempt import wiretap (MUST FAIL)
```
Execute: import wiretap
```
**Expected result**: BLOCKED by dangerous pattern.

### T10.4 · Attempt project.libraries (MUST FAIL)
```
Execute: libs = flame.projects.current_project.libraries
```
**Expected result**: BLOCKED with `ws.libraries` alternative.

### T10.5 · Attempt flame.projects[0] (MUST FAIL)
```
Execute: p = flame.projects[0]
```
**Expected result**: BLOCKED — `flame.projects` is not subscriptable.

### T10.6 · Attempt replace_desktop (MUST FAIL)
```
Execute: ws.replace_desktop(ws.desktop)
```
**Expected result**: BLOCKED — internal method that can corrupt the workspace.

---

## Level 11 — Cleanup (Undo Everything Created)

> **IMPORTANT**: Run this level after finishing all tests to leave Flame clean.

### T11.1 · Delete test batch groups
```
Delete the "MCP_Batch_Test" and "MCP_Batch_Loaded" batch groups from the desktop.
```
**Expected code**: `flame.delete(bg)` for each batch group found.

### T11.2 · Delete the test reel group (requires T11.1)
```
Delete the "MCP_Test_Group" reel group from the desktop.
```
**Expected code**: `flame.delete(rg)`

### T11.3 · Delete the test folder from the library
```
Delete the "MCP_Tests" folder from the first library.
```
**Expected code**: `flame.delete(folder)`

### T11.4 · Delete the duplicated clip (if created in T7.3)
```
If the clip "MCP_Clip_Copy" exists, delete it.
```
**Expected code**: `flame.delete(clip)` with prior search.

### T11.5 · Clean up temporary files
```
Delete the file /var/tmp/mcp_test_setup.batch if it exists.
```
**Expected code**: `os.remove("/var/tmp/mcp_test_setup.batch")`

### T11.6 · Final verification
```
Show me the full desktop structure and libraries to confirm everything is clean.
```
**MCP tools**: `list_desktop_reels` + `list_libraries`

---

## Coverage Summary

| Level | Tests | MCP Tools Covered | Type |
|-------|-------|-------------------|------|
| 0 | 5 | ping, get_flame_version, get_project_info, list_all_projects, session_stats | Diagnostics |
| 1 | 8 | list_libraries, list_reels, list_clips, list_desktop_reels, list_batch_groups, get_clip_metadata, get_selected_clips, flame_wiretap_tree | Inspection |
| 2 | 5 | search_flame_docs (x5) | RAG |
| 3 | 3 | list_flame_logs, read_flame_log (x2) | Logs |
| 4 | 4 | execute_python (read-only, x4) | Code RO |
| 5 | 4 | execute_python (create structures, x4) | Creation |
| 6 | 5 | execute_python (batch/nodes, x5) | Batch |
| 7 | 4 | execute_python (clips/sequences, x4) | Timeline |
| 8 | 4 | execute_python (attributes, x4) | Metadata |
| 9 | 4 | execute_python (advanced setup, x4) | Advanced |
| 10 | 6 | execute_python (security blocks, x6) | Security |
| 11 | 6 | execute_python + dedicated tools (cleanup, x6) | Cleanup |
| **Total** | **58** | **18/18 tools** (100%) | |

## Level Dependencies

```
Level 0 ──→ Level 1 ──→ Level 2 (independent)
                │         Level 3 (independent)
                │
                └──→ Level 4 ──→ Level 5 ──→ Level 6 ──→ Level 9
                                    │           │
                                    └──→ Level 7 ┘──→ Level 8
                                                         │
                            Level 10 (independent) ──────┘
                                                         │
                                                    Level 11 (final)
```

## Execution Notes

1. **Before starting**: Make sure Flame is open with a project loaded.
2. **Levels 2, 3, 10**: Can be run at any time (they are independent).
3. **Levels 5-9**: Sequential and cumulative — do not skip.
4. **Level 11**: ALWAYS run at the end to clean up.
5. **If a test fails**: Note the exact error and continue with the next test in the same level if possible.
6. **Estimated time**: 30-45 minutes for the full suite.
