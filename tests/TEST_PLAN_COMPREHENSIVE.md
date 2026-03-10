# FLAME-MCP COMPREHENSIVE TEST PLAN
## Analysis of RAG Corpus, MCP Tools, and Flame Python API

---

## 1. MCP TOOLS INVENTORY

### A. Core Execution Tools (with safety annotations)

#### 1.1 execute_python (DESTRUCTIVE)
- **Annotation**: `_DST` (destructive=True)
- **Parameters**: 
  - `code: str` - Python code to execute inside Flame
  - `timeout: int` (1-300, default=15) - TCP socket timeout in seconds
- **Description**: Execute arbitrary Python code inside Autodesk Flame with full access to flame module and Python API
- **Key Rules from Docstring**:
  - Libraries: use `ws = flame.projects.current_project.current_workspace` then `ws.libraries` (NOT `project.libraries`)
  - Renders: never call `flame.batch.render()` directly, use `schedule_idle_event`
  - Always end with `print()` for visible results

### B. Read-Only Inspection Tools (safe)

#### 1.2 get_project_info() → string
- **Annotation**: `_RO` (read-only)
- **Returns**: Project name, frame rate, resolution, bit depth, description, workspace count
- **Backend**: Uses wiretap_get_metadata (XML) for frame rate/resolution

#### 1.3 list_libraries() → string
- **Annotation**: `_RO`
- **Returns**: All user-visible libraries with reel/folder/reel_group counts
- **Excludes**: "Timeline FX", "Grabbed References" (hidden system libraries)

#### 1.4 list_reels(library_name: str = "") → string
- **Annotation**: `_RO`
- **Parameters**: 
  - `library_name: str` (optional) - Filter to specific library
- **Returns**: Reels in library with clip counts
- **Default behavior**: All reels across all visible libraries

#### 1.5 list_clips(library_name: str = "", reel_name: str = "", limit: int = 50) → string
- **Annotation**: `_RO`
- **Parameters**:
  - `library_name: str` (optional) - Filter to library
  - `reel_name: str` (optional) - Filter to specific reel
  - `limit: int` (0-5000, default=50) - Max clips per reel (0=unlimited)
- **Returns**: Clips with durations, with pagination if limit exceeded
- **Excludes**: Hidden system libraries

#### 1.6 list_desktop_reels() → string
- **Annotation**: `_RO`
- **Returns**: Full desktop structure: reel_groups > reels > clips (hierarchical)
- **Includes**: All clip names in one call (no follow-ups needed)

#### 1.7 list_batch_groups() → string
- **Annotation**: `_RO`
- **Returns**: All batch groups in active desktop with reel and node counts
- **Note**: Batch groups live on desktop alongside regular reel groups

#### 1.8 list_all_projects() → string
- **Annotation**: `_RO`
- **Returns**: All projects on workstation with active project marked
- **Backend**: Scans /opt/Autodesk/project directory (no project switching)

#### 1.9 get_clip_metadata(library_name: str, reel_name: str, clip_name: str) → string
- **Annotation**: `_RO`
- **Parameters**: All three required (no defaults)
- **Returns**: Detailed clip metadata (resolution, frame rate, duration, timecode, bit depth, tape name, source_timecode, ratio, scan_format)
- **Validation**: Requires frame_rate, width, duration to pass

#### 1.10 get_selected_clips() → string
- **Annotation**: `_RO`
- **Returns**: Current selection from media panel or desktop (name + type for each)
- **Use case**: Contextual operations on selected items

#### 1.11 flame_wiretap_tree(path: str = "/") → string
- **Annotation**: `_RO`
- **Parameters**:
  - `path: str` (default="/") - IFFFS node path to inspect
  - Examples: "/projects", "/projects/<uuid>", "/projects/<uuid>/workspace"
- **Returns**: Raw Wiretap IFFFS tree structure
- **Backend**: Runs wiretap_print_tree CLI tool (not inside Flame)
- **Use cases**: Explore inactive projects, find UUIDs, inspect raw node structure

#### 1.12 get_flame_version() → string
- **Annotation**: `_RO`
- **Returns**: Running Flame version string via flame.get_version()

#### 1.13 ping() → string
- **Annotation**: `_RO`
- **Returns**: "🟢 Bridge connected — Flame X.X" or "🔴 Bridge not connected"
- **Safety**: No state modification, safe to call anytime

### C. RAG & Knowledge Tools (read-only + write for learned patterns)

#### 1.14 search_flame_docs(query: str) → string
- **Annotation**: `_RO`
- **Parameters**: `query: str` - Semantic search query (e.g., "how to import media into a reel")
- **Returns**: 
  - Top 5 most relevant chunks from RAG corpus
  - Max relevance score (0-100%)
  - Estimated tokens saved vs full doc
  - Coverage warnings if score < threshold
- **Caching**: Identical queries cached within session
- **Key rule**: MUST call this BEFORE every execute_python call

#### 1.15 learn_pattern(description: str, code: str) → string
- **Annotation**: `_RW` (read-write, non-destructive)
- **Parameters**:
  - `description: str` - Short English label (e.g., "delete folder by name from library")
  - `code: str` - Working Python code that just executed successfully
- **Behavior**:
  - Trusted models (Sonnet/Opus): Add pattern directly to FLAME_API.md, rebuild RAG index in background
  - Read-only models (Haiku): Stage pattern to rag/candidates.json for human review
- **Deduplication**: Checks if similar description already documented
- **Traceability**: Adds model + date metadata to learned patterns

### D. Monitoring & Diagnostics Tools (read-only)

#### 1.16 session_stats() → string
- **Annotation**: `_RO`
- **Returns**: Session summary:
  - execute_python calls count
  - search_flame_docs calls count
  - Dedicated tool calls count
  - Patterns learned / staged / failed
  - Token usage (sent/received/total)
  - Tokens saved (RAG + tools)
  - Efficiency rating (warns if execute_python called without prior search)

#### 1.17 list_flame_logs() → string
- **Annotation**: `_RO`
- **Returns**: All log files in /opt/Autodesk/logs with size, last-modified time
- **Log types**: flame*.log, wiretap*.log, IFFFS*.log, backburner*.log, python*.log

#### 1.18 read_flame_log(log_name: str, lines: int = 100, grep: str = "") → string
- **Annotation**: `_RO`
- **Parameters**:
  - `log_name: str` (required, no path separators) - filename only
  - `lines: int` (0-50000, default=100) - lines from end (0=all)
  - `grep: str` (optional) - regex filter (case-insensitive)
- **Examples**:
  - `read_flame_log("flame.log", lines=50)` - last 50 lines
  - `read_flame_log("flame.log", grep="ERROR")` - all error lines
  - `read_flame_log("wiretap.log", grep="IFFFS")` - IFFFS operations
- **Backend**: Reverse-chunk tail algorithm (avoids loading gigabyte files into RAM)
- **Safety**: Path traversal guard (blocks ".." and leading ".")

---

## 2. DANGEROUS PATTERNS & SAFETY BLOCKS

### Crash-Level Patterns (18 categories)

1. **flame.projects iteration/indexing** → CRASH
   - `len(flame.projects)` - not a list
   - `for x in flame.projects` - not iterable
   - `flame.projects[0]` - not subscriptable
   - Fix: Use `flame.projects.current_project` or `os.listdir('/opt/Autodesk/project')`

2. **project.libraries** → Returns None
   - Fix: `ws = flame.projects.current_project.current_workspace; ws.libraries`

3. **flame.batch.render()** → Blocks main thread, freezes/crashes Flame
   - Fix: `flame.schedule_idle_event(lambda: flame.batch.render(...))`

4. **import wiretap** → Crash-prone module
   - Also blocks: Direct WireTap C-bindings (WireTapServerHandle, libwiretap, etc.)
   - Fix: Use standard flame API only

5. **WireTap tree-traversal methods** → Crash from Python hooks
   - `.createNode()`, `.getNumChildren()`, `.getNodeInfo()`
   - Fix: Use standard flame API

6. **ws.replace_desktop()** → Corrupts workspace state, crashes Flame
   - Fix: Use `ws.desktop` and its reel_groups/reels attributes

7. **dir(flame)** → Unsafe, causes speculative/crashing code
   - Fix: Use `search_flame_docs()` for verified patterns

8. **Calling .clear()** on Flame objects → Crash (raw C-level destructor)
   - Affected: PyReelGroup, PyLibrary, PyReel, etc.
   - Fix: Iterate children and call `flame.delete(item)` on each

9. **flame.clear_desktop()** → Doesn't exist in public API
   - Fix: Delete individual reels using `flame.delete()`

10. **Deleting ALL reels** → Crash (reel groups need ≥1 reel)
    - Pattern 1: `for reel in list(rg.reels): flame.delete(reel)` ❌
    - Pattern 2: `flame.delete(list(rg.reels))` ❌
    - Fix: `flame.delete(list(rg.reels)[:-1])` or filter by name

11. **PyAttribute comparison** → Silent failure (returns [])
    - `.name == "string"` - wrong type (PyAttribute)
    - `.name in {'Reel 1', 'Reel 2'}` - wrong type
    - Fix: `str(reel.name) == 'Reel 1'` or `str(reel.name) in {'Reel 1', 'Reel 2'}`

12. **Calling string methods on .name** → AttributeError
    - `.name.startswith()`, `.name.lower()`, `.name.split()`, etc.
    - Fix: `str(clip.name).startswith('VFX_')`

13. **next() without default** → StopIteration, incomplete state
    - `next(r for r in rg.reels if ...)` ❌
    - Fix: `next((r for r in rg.reels if ...), None)` and check for None

14. **Using next() result without None check** → AttributeError
    - `reel = next(..., None); reel.name` if reel is None ❌
    - Fix: Check `if reel is not None` before use

15. **Timeline edit methods** (Flame 2026) → Don't exist, crash
    - `seg.delete()`, `track.remove_gap()`, `track.ripple()`, `flame.timeline.*`
    - Fix: Rebuild sequence by iterating non-gap segments

16. **PyExporter() without schedule_idle_event** → Hangs Flame
    - Qt event loop blocked while Python thread waits
    - Fix: `flame.schedule_idle_event(lambda: PyExporter().export(...))`

17. **Obfuscated dangerous calls** (AST-detected)
    - `getattr(flame, 'batch').render()` - bypasses regex
    - `__import__('wiretap')` - dynamic import
    - Fixed by: AST analysis in _check_dangerous()

18. **Large media imports on main thread** → Hangs/crashes
    - Also requires `schedule_idle_event` for long operations

---

## 3. RAG CORPUS INVENTORY

### Corpus Statistics
- **Total chunks**: 668
- **Indexed by**: Chroma VectorDB (semantic + metadata)
- **Refresh**: Automatic when new patterns learned

### Source Documents (12 sources)

1. **FLAME_API.md** (294 chunks) - Full Python API reference
   - 68 classes (PyProject, PyClip, PySequence, PyBatch, PyNode, etc.)
   - Module-level functions: batch, browser, delete, duplicate, execute_command, etc.
   - Object hierarchy, attributes, methods for each class

2. **flame_advanced_api.md** (78 chunks) - Autodesk official reference
   - Action, Color Management, Conform, Timeline FX, Export
   - Module-level data attributes
   - Operator terminology ("nuke it", "trash it", "delete that clip")

3. **flame_code_samples.md** (46 chunks) - Real production code from Autodesk
   - Hook registration (modern API, Flame 2020+)
   - Media panel custom UI actions
   - Batch custom UI actions
   - Real-world examples

4. **flame_community_workflows.md** (23 chunks) - Logik Forums & operator language
   - Starting new projects / desktop setup
   - Clearing desktop and creating reels with color
   - Renaming/creating fresh reels
   - How artists actually talk about work

5. **flame_cookbook_official.md** (22 chunks) - Official Autodesk recipes
   - Clip import: `flame.import_clips(path, PyLibrary)`
   - Clip reformat: `<PyClip>.reformat(width, height, ratio)`
   - Rendering: `<PyClip>.render(render_mode, render_option, render_quality)`

6. **flame_ocr_patterns.md** (15 chunks) - YouTube OCR extractions (Round 1)
   - Basic workspace traversal
   - Accessing current workspace
   - List libraries pattern
   - Key point: `ws.libraries` (NOT `flame.projects.current_project.libraries`)

7. **flame_ocr_patterns_v2.md** (23 chunks) - YouTube OCR extractions (Round 2)
   - Batch naming hooks: `batchDefaultIterationName()`, `batchDefaultRenderNodeName()`
   - Python hook path: `/var/tmp/adsk_python/` or custom via `DL_PYTHON_HOOK_PATH`
   - Hook registration patterns

8. **flame_openclip_patterns.md** (8 chunks) - OpenClip XML & watch-folder workflows
   - Watch-folder core architecture
   - `dl_get_media_info` CLI tool for OpenClip XML creation
   - Splicing new versions into existing clips (XML manipulation)

9. **flame_reference_guide.md** (30 chunks) - API method signatures & behavior
   - Reference-level documentation of public API
   - Method signatures and return types

10. **flame_segment_timeline_api.md** (61 chunks) - Timeline / sequence editing
    - PySegment, PyAudioTrack, timeline editing
    - Gap closure patterns
    - Ripple delete algorithms

11. **flame_vocabulary.md** (8 chunks) - Operator terminology glossary
    - Maps Flame artist language to API concepts
    - "Online", "Offline", "DCP", "Conform", etc.

12. **flame_youtube_patterns.md** (60 chunks) - Multi-video OCR extractions
    - Patterns from Logik Live sessions
    - Real-world scripting patterns
    - Advanced workflows

---

## 4. DOCUMENTED FLAME PYTHON API CLASSES

### Project & Workspace (4 classes)
- **PyProject**: Current project reference
- **PyProjectSelector**: Not iterable (common crash source)
- **PyWorkspace**: Current workspace, holds libraries & desktop
- **PyDesktop**: Holds reel_groups & batch_groups

### Library Structure (5 classes)
- **PyLibrary**: Container for reels & folders
- **PyReel**: Container for clips
- **PyReelGroup**: Container for reels (on desktop)
- **PyFolder**: Organizational container within library
- **PyClip / PySequence**: Media items (clips or sequences)

### Batch & Rendering (4 classes)
- **PyBatch**: Current batch group
- **PyBatchIteration**: Iteration within batch
- **PyExporter**: For export operations (requires schedule_idle_event)
- **PyRenderNode**: Batch render node

### Node Types (12 classes, extending PyNode)
- **PyActionNode**: Action/effect node
- **PyActionFamilyNode**: Container for action nodes
- **PyImageNode**: Image processing node
- **PyMorphNode**: Morphing node
- **PyGMaskTracerNode**: Mask tracer node
- **PyClipNode**: Clip input node
- **PyRenderNode**: Render output node
- **PyOFXNode**: OpenFX plugin node
- **PyPaintNode**: Paint/drawing node
- **PyHDRNode**: HDR processing node
- **PyLensDistortionNode**: Lens correction node
- **PyClrMgmtNode**: Color management node
- **PyCompassNode**: Compass organization node
- **PyCoCompass**: Cooperative compass

### Timeline & Sequences (3 classes)
- **PySequence**: Sequence object (type of PyClip)
- **PySegment**: Timeline segment within sequence
- **PyAudioTrack**: Audio track in sequence

### Utilities (4 classes)
- **PyAttribute**: Represents object attributes (NOT strings - must wrap with str())
- **PyFlameObject**: Base class for all Flame objects
- **PyMarker**: Timeline markers
- **PyResolution**: Resolution specification object

### Module-Level Functions
- **flame.delete(obj)**: Delete single object
- **flame.duplicate(obj)**: Duplicate single object
- **flame.duplicate_many(objs)**: Duplicate multiple objects
- **flame.import_clips(path, library)**: Import media files
- **flame.schedule_idle_event(fn)**: Execute function on idle (safe for long ops)
- **flame.execute_command(cmd)**: Execute Flame command
- **flame.execute_shortcut(shortcut)**: Run keyboard shortcut
- **flame.set_render_option(option)**: Configure render
- **flame.find_by_name(name)**: Find object by name
- **flame.find_by_uid(uid)**: Find object by UID
- **flame.find_by_wiretap_node_id(id)**: Find via WireTap ID
- **flame.go_to(obj)**: Navigate to object in UI
- **flame.set_current_tab(tab)**: Switch UI tab
- **flame.get_current_tab()**: Get active tab
- **flame.exit()**: Close Flame
- **flame.get_version()**: Version string
- **flame.get_version_major()**, **get_version_minor()**, **get_version_patch()**: Version components
- **flame.get_home_directory()**: User home path
- **flame.get_init_cfg_path()**: Flame config directory
- **flame.flush_graphics_memory()**: Clear GPU memory

---

## 5. DOCUMENTED OPERATIONS BY CATEGORY

### Import & Media Operations
- `flame.import_clips(file_path, library)` - Import clips to library
- `dl_get_media_info` - CLI tool for OpenClip XML
- Watch-folder monitoring for auto-imports
- Multiple version management (OpenClip)

### Create Operations
- Create libraries (via workspace API)
- Create reels (within library)
- Create reel groups (on desktop)
- Create clips/sequences
- Create batch groups
- Create nodes in batch (Action, Image, etc.)

### Modify Operations
- **Rename**: Set `.name` property
- **Reformat clip**: `clip.reformat(width, height, ratio)`
- **Color reel**: Set `.colour = (R, G, B)` tuple
- **Node connections**: `connect_nodes()`, `disconnect_nodes()`
- **Batch configuration**: Set render options, iteration names
- **Timeline editing**: Close gaps, ripple delete (rebuild algorithm)
- **Attributes**: Get/set via property access

### Delete Operations
- `flame.delete(obj)` - Delete single item
- `flame.delete(list_of_objs)` - Delete multiple items
- **Safety constraint**: Always keep ≥1 reel in reel groups
- Proper pattern: `flame.delete(list(rg.reels)[:-1])`

### Export & Render Operations
- `clip.render(render_mode, render_option, render_quality)` - Render clip
- `PyExporter().export(...)` - Export setup (requires schedule_idle_event)
- `export_fbx(...)` - Export to FBX format
- Batch rendering via PyRenderNode
- Custom render presets via `set_render_option()`

### Search & Find Operations
- `flame.find_by_name(name)` - Find by name
- `flame.find_by_uid(uid)` - Find by unique ID
- `flame.find_by_wiretap_node_id(id)` - Find via WireTap ID
- RAG-based search via `search_flame_docs()`

### Timeline/Sequence Operations
- Access segments: `sequence.segments`
- Get segment properties: `segment.source, segment.start, segment.duration`
- **Gaps**: Not deletable directly - rebuild sequence algorithm
- **Ripple delete**: Rebuild by iterating non-gap segments
- Timeline FX: Apply to clips/sequences

### Batch & Node Operations
- Access batch nodes: `flame.batch.nodes`
- Create nodes: `batch.create_node(type, file_path)`
- Connect nodes: `action_node.connect_nodes(parent, child)`
- Load/save node setups: `node.load_node_setup()`, `save_node_setup()`
- Set node context: `node.set_context(index, socket_name)`

### Hook Operations (Flame Startup)
- `get_media_panel_custom_ui_actions()` - Media panel context menu
- `get_batch_custom_ui_actions()` - Batch schematic context menu
- `batchDefaultIterationName(project)` - Batch iteration naming
- `batchDefaultRenderNodeName(...)` - Render node naming
- Hook path: `/opt/Autodesk/shared/python/` or `$DL_PYTHON_HOOK_PATH`

### Import Formats (from corpus)
- Movie files: .mov, .mp4, .mxf
- Image sequences: .exr, .dpx, .tiff
- FBX files for 3D objects
- ABC (Alembic) for geometry
- PSD files for layered assets
- OpenClip XML for multi-version clips

---

## 6. OBJECT HIERARCHY REFERENCE

```
flame (module root)
├── projects
│   └── current_project (PyProject)
│       ├── name, description, workspaces_count
│       └── current_workspace (PyWorkspace)
│           ├── libraries (list of PyLibrary)
│           │   ├── reels (list of PyReel)
│           │   │   ├── clips (list of PyClip/PySequence)
│           │   │   │   ├── segments (for PySequence)
│           │   │   │   ├── duration, frame_rate, width, height
│           │   │   │   └── [attributes...]
│           │   │   ├── name, colour
│           │   │   └── [properties...]
│           │   ├── folders (list of PyFolder)
│           │   ├── reel_groups (list of PyReelGroup)
│           │   └── [properties...]
│           └── desktop (PyDesktop)
│               ├── reel_groups (list of PyReelGroup)
│               │   └── reels (list of PyReel)
│               └── batch_groups (list of PyBatch)
│                   ├── reels (list of PyReel)
│                   ├── nodes (list of PyNode variants)
│                   └── [batch configuration...]
├── batch (PyBatch) - Current batch (via flame.batch)
├── selection - Current selection (list of items)
├── browser (PyBrowser) - File browser panel
├── media_panel (PyMediaPanel) - Media panel reference
├── timeline (PySequence) - Current sequence in Timeline
├── mediahub (PyMediaHub) - MediaHub panel
├── messages (PyMessages) - Message logging
└── [module functions...]
```

---

## 7. TEST PLAN STRUCTURE

### 7.1 MCP Tool Category Tests

#### Category: Read-Only Inspection (9 tools)
**Tools**: list_libraries, list_reels, list_clips, list_desktop_reels, list_batch_groups, list_all_projects, get_clip_metadata, get_selected_clips, get_project_info

**Test Areas**:
- ✓ Tool invocation with and without parameters
- ✓ Expected output format validation
- ✓ Pagination (limit parameter)
- ✓ Empty results handling
- ✓ Hidden library exclusion ("Timeline FX", "Grabbed References")
- ✓ Token efficiency (dedicated tools vs execute_python)
- ✓ Filter parameter validation

#### Category: Knowledge & Documentation (2 tools)
**Tools**: search_flame_docs, learn_pattern

**Test Areas**:
- ✓ Semantic search accuracy (5 results + score)
- ✓ Cache mechanism (identical queries)
- ✓ Low-coverage warnings (< threshold)
- ✓ Pattern deduplication
- ✓ Model-specific behavior (trusted vs read-only)
- ✓ Candidate staging (rag/candidates.json)
- ✓ RAG index rebuild trigger
- ✓ Traceability metadata (model + date)

#### Category: Execution (1 tool)
**Tools**: execute_python

**Test Areas**:
- ✓ 18 dangerous pattern blocks
- ✓ AST analysis for obfuscated calls
- ✓ Regex pattern matching
- ✓ Error message quality
- ✓ Safe alternatives in error text
- ✓ Timeout handling (1-300 seconds)
- ✓ Output capture (stdout + stderr)
- ✓ Token tracking

#### Category: Diagnostics (4 tools)
**Tools**: ping, get_flame_version, list_flame_logs, read_flame_log

**Test Areas**:
- ✓ Bridge connectivity check
- ✓ Version retrieval
- ✓ Log file enumeration
- ✓ Log tailing (reverse-chunk algorithm)
- ✓ Grep filtering (regex + case-insensitive)
- ✓ Path traversal defense
- ✓ Large file handling (no full load)
- ✓ Malformed grep pattern handling

#### Category: Wiretap Navigation (1 tool)
**Tools**: flame_wiretap_tree

**Test Areas**:
- ✓ IFFFS node exploration
- ✓ Path validity
- ✓ UUID discovery
- ✓ Timeout handling
- ✓ Cross-project inspection (no switching)

#### Category: Monitoring (1 tool)
**Tools**: session_stats

**Test Areas**:
- ✓ Call counters (execute_python, search_flame_docs, dedicated)
- ✓ Token accounting
- ✓ Efficiency rating
- ✓ Pattern learning/staging tracking
- ✓ RAG savings calculation

---

### 7.2 Flame Python API Coverage Tests

#### CRUD Operations
- **Create**: Libraries, reels, reel groups, clips, batch groups, nodes
- **Read**: All object hierarchies, attributes, metadata
- **Update**: Rename, reformat, color, node connections, properties
- **Delete**: Single & multiple items, with safety constraints

#### Object Hierarchy Traversal
- **Valid paths**: All documented paths in 6. Object Hierarchy Reference
- **Invalid paths**: Each dangerous pattern from section 2 (18 tests)
- **Error handling**: AttributeError, None checks, type validation

#### Safe Execution Context
- **schedule_idle_event**: Required for long operations
- **PyExporter**: Must use schedule_idle_event
- **flame.batch.render()**: Must use schedule_idle_event
- **Media imports**: Safe on main thread vs long operations

#### PyAttribute Handling
- **String wrapping**: All .name comparisons must use str()
- **String methods**: All .name.method() must wrap with str()
- **Set membership**: All `in {set}` checks must use str()

#### Timeline Editing Safety
- **Gap operations**: Only via rebuild algorithm (no seg.delete)
- **Ripple delete**: Only via rebuild algorithm
- **Sequence mutation**: Non-destructive iteration patterns

#### Reel Group Constraints
- **Minimum 1 reel**: Never delete all reels from desktop reel groups
- **Safe deletion patterns**: Always keep last reel or use filter

#### Corpus-Documented Patterns (from section 5)
- **Import operations**: Test each documented import format
- **Render operations**: All documented render modes and options
- **Node operations**: All documented node types and connections
- **Hook registration**: All documented hook functions

---

### 7.3 RAG Corpus Completeness Tests

#### Source Coverage (12 sources)
- ✓ FLAME_API.md: All 68 classes have methods/attributes
- ✓ flame_advanced_api.md: Action, Color Management, Conform, Timeline FX, Export documented
- ✓ flame_code_samples.md: Real production patterns
- ✓ flame_community_workflows.md: Operator workflows
- ✓ flame_cookbook_official.md: Official recipes
- ✓ flame_ocr_patterns.md: Basic traversal
- ✓ flame_ocr_patterns_v2.md: Batch hooks, naming
- ✓ flame_openclip_patterns.md: Watch-folder, XML
- ✓ flame_reference_guide.md: Reference-level docs
- ✓ flame_segment_timeline_api.md: Timeline/sequence
- ✓ flame_vocabulary.md: Terminology mapping
- ✓ flame_youtube_patterns.md: Advanced workflows

#### Chunk Distribution
- 668 total chunks indexed
- Even distribution across 12 sources
- Semantic search effectiveness on representative queries

#### Gap Analysis
- Coverage of every PyClass (68 classes)
- Coverage of every module function
- Coverage of dangerous patterns & safe alternatives
- Coverage of edge cases (None checks, empty results, etc.)

---

### 7.4 Safety & Security Tests

#### Pattern Detection (18 categories)
1. ✓ flame.projects iteration/indexing detection
2. ✓ project.libraries → None detection
3. ✓ flame.batch.render() blocking detection
4. ✓ import wiretap detection
5. ✓ WireTap C-bindings detection
6. ✓ WireTap tree-traversal detection
7. ✓ ws.replace_desktop() detection
8. ✓ dir(flame) detection
9. ✓ .clear() on objects detection
10. ✓ flame.clear_desktop() detection
11. ✓ Delete all reels detection (2 patterns)
12. ✓ PyAttribute comparison detection
13. ✓ String methods on .name detection
14. ✓ next() without default detection
15. ✓ next() result without None check detection
16. ✓ Timeline methods detection
17. ✓ PyExporter without schedule_idle_event detection
18. ✓ Media import on main thread (soft warning)

#### AST Analysis
- ✓ Obfuscated calls: `getattr(flame, 'batch').render()`
- ✓ Dynamic imports: `__import__('wiretap')`
- ✓ Attribute chaining detection

#### Error Message Quality
- ✓ Clear problem statement
- ✓ Safe alternative provided
- ✓ Example code in alternative
- ✓ Link to documentation section

#### Bridge Security
- ✓ TCP localhost-only binding (127.0.0.1:4444)
- ✓ Port override via environment variable (FLAME_BRIDGE_PORT)
- ✓ Connection validation
- ✓ Socket cleanup on disconnect

---

### 7.5 Integration Tests

#### Tool Orchestration
- ✓ search_flame_docs → execute_python workflow
- ✓ learn_pattern after successful execute_python
- ✓ get_selected_clips → operate on selection
- ✓ list_* tools for preconditions before mutations

#### State Consistency
- ✓ Operations maintain workspace state
- ✓ Reel constraints enforced (min 1 reel)
- ✓ Attribute updates reflected
- ✓ Selection changes tracked

#### Multi-Step Workflows
- ✓ Import → organize → render
- ✓ Clear desktop → create reels → configure
- ✓ Create batch → add nodes → connect → render
- ✓ Find → select → modify

---

### 7.6 Performance & Efficiency Tests

#### Token Usage
- ✓ Dedicated tools save tokens vs execute_python
- ✓ RAG search saves tokens vs full FLAME_API.md
- ✓ Session stats accurately track usage
- ✓ Savings calculation validation

#### Caching
- ✓ Identical query results cached in session
- ✓ Cache invalidation on RAG rebuild
- ✓ Cache miss + hit paths

#### Scalability
- ✓ Large library enumeration (1000+ reels)
- ✓ Large clip lists (limit pagination)
- ✓ Large log file tailing (reverse-chunk algorithm)
- ✓ Deep object hierarchies (recursion safe)

#### Timeout Handling
- ✓ TCP timeout parameter (1-300 range)
- ✓ Timeout exceeded handling
- ✓ Graceful degradation

---

### 7.7 Error Handling Tests

#### Invalid Input
- ✓ Missing required parameters
- ✓ Out-of-range parameters (limit, timeout)
- ✓ Invalid regex patterns in grep
- ✓ Path traversal attempts ("..",".", "/etc/passwd")
- ✓ Non-existent log files, libraries, reels, clips

#### Bridge Not Connected
- ✓ Graceful error message when bridge unavailable
- ✓ Ping tool detects disconnection
- ✓ All execute_python calls fail cleanly

#### Malformed Code
- ✓ SyntaxError in code
- ✓ NameError during execution
- ✓ RuntimeError during execution
- ✓ Timeout during execution

#### Flame Crash Recovery
- ✓ Bridge detects Flame crash
- ✓ Crash recovery log written
- ✓ Recovery on Flame restart

---

## 8. TEST PREREQUISITES & FIXTURES

### 8.1 Flame Instance Requirements
- Flame 2026 running
- Bridge installed: `/opt/Autodesk/shared/python/flame_mcp_bridge.py`
- Bridge active on port 4444 (or `$FLAME_BRIDGE_PORT`)
- Default project loaded with:
  - ≥1 library with reels
  - ≥1 clip in reel for metadata testing
  - ≥1 batch group with nodes
  - Desktop with reel groups

### 8.2 MCP Server Setup
- Server running (stdio transport)
- RAG index built: `python rag/build_index.py`
- RAG corpus indexed: 668 chunks from 12 sources
- Config loaded: `.venv/bin/python flame_mcp_server.py`

### 8.3 Test Data Fixtures
- Test library: "test_lib" with 3 reels ("ONLINE", "OFFLINE", "DCP")
- Test clips: 1 in each reel with varied frame rates/resolutions
- Test batch: 1 batch group "test_batch" with Action node setup
- Test desktop: 1 reel group with 3 reels minimum

### 8.4 Environment
- Linux workstation with /opt/Autodesk/
- Python 3.10+ with mcp, chromadb, pydantic
- Logs directory: /opt/Autodesk/logs/
- Wiretap CLI: /opt/Autodesk/wiretap/tools/current/

---

## 9. EXPECTED OUTCOMES & COVERAGE MATRIX

| Category | Tool Count | Test Cases | Safety Checks | Pass Criteria |
|----------|-----------|-----------|---------------|---------------|
| Read-Only Inspection | 9 | 45 | 5 | 100% passing + output validation |
| Knowledge & Docs | 2 | 20 | 3 | RAG accuracy > 85%, pattern dedup works |
| Execution | 1 | 50 | 18 | All dangerous patterns blocked, AST works |
| Diagnostics | 4 | 16 | 2 | All tools accessible when bridge active |
| Wiretap | 1 | 12 | 1 | Cross-project exploration works |
| Monitoring | 1 | 8 | 1 | Token accounting accurate |
| **TOTAL** | **18** | **151** | **30** | **All tests pass + 100% API coverage** |

---

## 10. KNOWN LIMITATIONS & NOT-TESTED

### Intentionally Out of Scope
- Custom plugins/extensions (not in RAG corpus)
- Wiretap direct C-bindings (blocked for safety)
- flame.projects iteration (blocked for safety)
- Unresolved Flame bugs (documentation dependency)

### Prerequisites for Full Coverage
- Active Flame instance (cannot mock TCP bridge)
- /opt/Autodesk/ filesystem access
- Pre-configured test project with fixtures

### Model-Specific Behavior
- Trusted models (Sonnet/Opus): learn_pattern → FLAME_API.md
- Read-only models (Haiku): learn_pattern → rag/candidates.json
- Requires human promotion for read-only patterns

---

