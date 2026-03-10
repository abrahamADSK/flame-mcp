# flame-mcp OCR Patterns v2 — Extracted from YouTube Videos (Round 2)

> Patterns extracted via frame OCR from 4 additional HIGH-priority videos.
> Sources: Autodesk Flame Learning Channel (flame_learning_channel)
> Videos: ZDHntCBBRXM, lMRidruJDqA, VJFgxnCqrE0
> (hPa1OVEY_78 contained no readable code frames — workflow demo only)

---

## Batch Naming Hooks — batchDefaultIterationName and batchDefaultRenderNodeName

From ZDHntCBBRXM ("Python Scripting - Batch Iteration and Render Naming").
These two hooks are defined in any Python file in the Flame hook path.
Flame calls them at startup and on project switch to set global naming defaults.

```python
# naming_conventions.py
# Place in: /var/tmp/adsk_python/  (or any directory set via DL_PYTHON_HOOK_PATH)

# Hook: define default batch iteration name
# Called at app start and project switch
# project: str — name of current project
def batchDefaultIterationName(project):
    pattern = project + "_<batch name>_<date>_<time>_<iteration##>_FPLC"
    return pattern

# Hook: define default batch render node name
# Called at app start and project switch
def batchDefaultRenderNodeName(project):
    pattern = "<batch name>_<date>_<time>_" + project
    return pattern

# Hook: define default batch write file node name (optional)
def batchDefaultWriteNodeName(project):
    pattern = "<batch name>_<date>_<time>_write_" + project
    return pattern
```

### Mandatory naming tokens

The tokens `<batch name>` and `<iteration>` are **mandatory** in
`batchDefaultIterationName`. All other tokens are optional.

| Token | Expands to |
|---|---|
| `<batch name>` | Name of the batch group |
| `<iteration##>` | Iteration number (## = zero-padded digits) |
| `<date>` | Current date (YYYY_MM_DD) |
| `<time>` | Current time (HHhMMmSS) |
| `<project>` | Current project name |

Notes:
- These hooks fire on **app startup** and on **project switch**, not per-iteration.
- To force a refresh without relaunching: `Ctrl+Shift+P+H` rescans all Python hooks.
- The `project` argument is the string name of the current Flame project.
- Returning `""` (empty string) leaves the naming at Flame's built-in default.

---

## Standard Flame Python Hook Files Location

From ZDHntCBBRXM — listing of `/usr/discreet/flame_2016.2/python/`:

```
_handle.so
archiveHook.py      # hooks for archive operations
autodesk_ifffs.py   # Wiretap/IFFFS integration
batchHook.py        # batch iteration, render, write node naming hooks
exportHook.py       # export hooks
hook.py             # base hook definitions
```

The `batchHook.py` file ships with Flame and documents all available batch
hooks with examples. To view it:
```bash
cat /usr/discreet/<flame_version>/python/batchHook.py
```

---

## DL_PYTHON_HOOK_PATH — Setting a Custom Python Hook Directory

From ZDHntCBBRXM. Set this environment variable before launching Flame to
point to a custom directory containing Python hook files. This is how
facility-wide naming conventions are deployed across multiple workstations.

### Method 1: Set in the startApplication launch script (permanent)

```bash
# Edit /usr/discreet/<flame_version>/bin/startApplication
# Add before the Flame launch command:

# Defining custom python hook path
os.environ['DL_PYTHON_HOOK_PATH'] = '/var/tmp/adsk_python'
```

### Method 2: Set in shell before launching (temporary)

```bash
export DL_PYTHON_HOOK_PATH=/var/tmp/adsk_python
./startApplication
```

### Method 3: Set programmatically in a startup script

```python
import os
os.environ['DL_PYTHON_HOOK_PATH'] = '/mnt/shared/facility_python_hooks'
```

Notes:
- The path can be on any accessible volume (local or NFS/shared storage).
- Multiple workstations can point to the same shared location for facility-wide hooks.
- Python files can have any name — Flame scans all `.py` files in the directory.
- After changing `DL_PYTHON_HOOK_PATH`, relaunch Flame or press `Ctrl+Shift+P+H`.

---

## Python Hook Install Paths — All 4 Scoping Options

From lMRidruJDqA ("Adding Custom Menu Actions", Flame 2020).
Flame scans these directories for Python hook files (`.py`). The path
controls which projects and users the hooks are available to.

| Path | Scope |
|---|---|
| `/opt/Autodesk/shared/python` | All Flame versions, all projects, all users |
| `/opt/Autodesk/<version>/python` | Specific Flame version only |
| `/opt/Autodesk/project/<project>/python` | Specific project only |
| `/opt/Autodesk/user/<user>/python` | Specific user only |

Additionally, set `DL_PYTHON_HOOK_PATH` to a custom directory path to add
a fifth location (useful for centralising hooks on shared storage).

To activate newly copied scripts without restarting Flame:
```
Ctrl + Shift + P + H   →  rescan Python hooks
```

---

## get_media_panel_custom_ui_actions — Create Reel in Reel Group

From lMRidruJDqA. Complete working example of a media panel custom action
that creates a new reel inside a selected reel group, inheriting its colour.

```python
def get_media_panel_custom_ui_actions():

    def scope_reel(selection):
        """Show menu item only when a PyRealGroup is selected."""
        import flame
        for item in selection:
            if isinstance(item, (flame.PyRealGroup,)):
                return True
        return False

    def create_reel(selection):
        """Create a new reel in each selected reel group, copying its colour."""
        import flame
        for item in selection:
            reel = item.create_reel("New Reel")
            reel.colour = reel.parent.colour

    return [
        {
            "name": "PYTHON: REEL GROUP",
            "actions": [
                {
                    "name": "Create Reel",
                    "isVisible": scope_reel,
                    "execute": create_reel,
                }
            ],
        }
    ]
```

Notes:
- `flame.PyRealGroup` — the class for a reel group (the coloured folder in the media panel).
- `item.create_reel("New Reel")` — creates a new reel inside the reel group; returns the reel object.
- `reel.colour = reel.parent.colour` — copies the parent reel group colour to the new reel.
- `isinstance(item, (flame.PyRealGroup,))` — note the trailing comma: single-element tuple.
- `import flame` can be placed at module level or inside each function; both work.
- The menu item label in the context menu is `"PYTHON: REEL GROUP"` → `"Create Reel"`.

---

## flame.batch.create_node — Build Batch Flow Graph Programmatically

From VJFgxnCqrE0 ("Working with Python Scripting", Flame 2018.2).
Creates nodes in the current batch group and connects them to build a
compositing flow graph from Python. Source file: `flc_comp.py`.

```python
import flame

# Create Comp nodes for each light pass
comp1 = flame.batch.create_node("Comp")
comp1.name = "Diffuse"
comp1.flame_blend_mode = "Add"

comp2 = flame.batch.create_node("Comp")
comp2.name = "Direct_Specular"
comp2.flame_blend_mode = "Add"

comp3 = flame.batch.create_node("Comp")
comp3.name = "Indirect_Specular"
comp3.flame_blend_mode = "Add"

comp4 = flame.batch.create_node("Comp")
comp4.name = "Reflection"
comp4.flame_blend_mode = "Screen"

# Create a Write File node for output
writeFile = flame.batch.create_node("Write File")
writeFile.name = "MyComp"

# Connect nodes: connect_nodes(source_node, output_connector, dest_node, input_connector)
flame.batch.connect_nodes(clip1, "BGR", comp1, "Front")
flame.batch.connect_nodes(clip1, "Result", comp1, "Back")

flame.batch.connect_nodes(clip1, "BGR", comp2, "Front")
flame.batch.connect_nodes(clip1, "Result", comp2, "Back")

flame.batch.connect_nodes(clip2, "BGR", comp3, "Front")
flame.batch.connect_nodes(clip2, "Result", comp3, "Back")

flame.batch.connect_nodes(comp1, "Result", writeFile, "Front")
```

Notes:
- `flame.batch.create_node(type_string)` — creates a node of the given type in the current batch.
  Common type strings: `"Comp"`, `"Write File"`, `"Read File"`, `"Render"`, `"Action"`, `"Reformat"`.
- `node.name` — set the display name of the node.
- `node.flame_blend_mode` — blend mode attribute on Comp nodes.
  Common values: `"Add"`, `"Screen"`, `"Normal"`, `"Multiply"`.
- `flame.batch.connect_nodes(src, src_output, dst, dst_input)` — connects two nodes.
  - `src_output` and `dst_input` are connector name strings (e.g. `"BGR"`, `"Front"`, `"Back"`, `"Result"`).
- Nodes are created at a default position; use `node.pos_x` / `node.pos_y` to set position.
- This pattern is the Python equivalent of manually dragging nodes onto the batch schematic.

---

## Common Batch Node Type Strings

From ZDHntCBBRXM and VJFgxnCqrE0. Node types usable with `flame.batch.create_node()`:

```python
import flame

# Compositing
comp   = flame.batch.create_node("Comp")
action = flame.batch.create_node("Action")

# I/O
reader = flame.batch.create_node("Read File")
writer = flame.batch.create_node("Write File")
render = flame.batch.create_node("Render")

# Colour / Transform
reformat  = flame.batch.create_node("Reformat")
colourwarp = flame.batch.create_node("Colour Warper")

# Timing
timewarp = flame.batch.create_node("TimeWarp")
mux      = flame.batch.create_node("MUX")
```

Notes:
- Type strings are case-sensitive and must match Flame's internal node names exactly.
- Use `node.type` (read-only attribute) to inspect the type of an existing node.
- `batch_group.nodes` returns all nodes in the batch; iterate to find nodes by type or name.
