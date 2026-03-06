# Flame 2026 Advanced Python API Reference
# Action, Color Management, Conform, Timeline FX, Export

Source: Autodesk Flame 2026 Python API — help.autodesk.com/view/FLAME/2026/ENU/
Compiled from the official flame module reference page.

---

## Module-Level Data Attributes

These are the top-level singletons exposed by the `flame` module:

| Attribute | Type | Description |
|---|---|---|
| `flame.batch` | `PyBatch` | Current batch group |
| `flame.browser` | `PyBrowser` | Flame browser panel |
| `flame.media_panel` | `PyMediaPanel` | Media panel (library view) |
| `flame.mediahub` | `PyMediaHub` | MediaHub panel |
| `flame.messages` | `PyMessages` | Message console |
| `flame.project` | `PyProjectSelector` | Project selector |
| `flame.projects` | `PyProjectSelector` | Alias for project |
| `flame.search` | `PySearch` | Search panel |
| `flame.timeline` | `PyTimeline` | Current timeline |
| `flame.users` | `PyUsers` | User management |

---

## Module-Level Functions

```python
flame.delete(obj)
# Delete any Flame object (clip, reel, segment, etc.)
# Operators say: "nuke it", "trash it", "delete that clip"

flame.duplicate(obj)
# Duplicate a single object — returns the new object

flame.duplicate_many(objs)
# Duplicate a list of objects — returns list of new objects

flame.execute_command(command_name)
# Execute a Flame menu command by name

flame.execute_shortcut(shortcut_name)
# Execute a keyboard shortcut by name

flame.get_current_tab()
# Returns the name of the currently active tab (str)
# e.g. "Timeline", "Batch", "MediaHub"

flame.set_current_tab(tab_name)
# Switch to a tab by name
# Operators say: "switch to timeline tab", "go to batch"
# tab_name: "Timeline", "Batch", "MediaHub", "Conform", etc.

flame.import_clips(path, destination)
# Import media into a reel or batch
# path: string or list of strings (supports frame ranges: "shot.[1001-1100].exr")
# destination: PyReel or batch reel name (str)

flame.schedule_idle_event(callable)
# Schedule a function to run on the next Flame idle event
# CRITICAL: Use this for batch.render() — never call render() directly
# Operators say: "kick off a BG render", "schedule the render"
```

---

## PyNode (Base Class for All Nodes)

All batch nodes inherit from `PyNode`. Available on every node type.

```python
# Properties
node.name              # str — node label in the schematic
node.pos_x             # float — X position in schematic
node.pos_y             # float — Y position in schematic
node.colour            # tuple(r, g, b) — schematic colour 0.0–1.0
node.bypass            # bool — bypass the node

# Methods
node.cache_range()
# Returns the cached frame range

node.clear_schematic_colour()
# Reset schematic colour to default

node.delete()
# Delete this node from the batch

node.duplicate()
# Duplicate this node — returns the new node

node.load_node_setup(filename)
# Load a saved node setup (.nst file)
# Operators say: "load a setup", "import node preset"

node.save_node_setup(filename)
# Save node setup to a .nst file
# Operators say: "save the setup", "export node preset"

node.set_context(index, socket_name)
# Set the context output for multi-output nodes
```

---

## Action Node (PyActionNode / PyActionFamilyNode)

Operators say: *"go to Action"*, *"add media to Action"*, *"add a camera"*,
*"import an FBX"*, *"enable the Comp output"*, *"add a GMask"*,
*"set up a 3D comp"*, *"Action schematic"*

`PyActionNode` extends `PyActionFamilyNode` extends `PyNode`.
`PyActionFamilyNode` is also the base for `PyGMaskTracerNode`.

### PyActionFamilyNode — Shared Methods

```python
action.clear_schematic()
# Clear all nodes from the Action schematic

action.connect_nodes(parent, child, link_type)
# Connect two nodes in the Action schematic
# link_type: e.g. "Front", "Matte", "Result", "Camera"
# Operators say: "wire up", "connect the media to the comp"

action.create_node(type, file_path="", is_udim=False, tile_resolution=None)
# Create a node inside Action
# type: "Media", "Camera", "Light", "Axis", "Comp", "GMask", "Matchbox", etc.
# file_path: for Media nodes — path to the clip/image
# Returns the new node
# Operators say: "add media", "drop in a camera", "add an axis"
```

### PyActionNode — Action-Specific

```python
# Properties
action.media_nodes         # list — all Media nodes in the Action
action.output_types        # list of str — currently enabled outputs

# Methods
action.add_media()
# Add a Media node to the Action schematic
# Returns PyActionMediaNode

action.disable_output(output_type)
# Disable a render output
# Operators say: "turn off the Matte pass", "disable AO output"

action.enable_output(output_type)
# Enable a render output
# Operators say: "turn on Comp output", "enable motion vectors"

action.import_fbx(file_path, frame_offset=0, scale=1.0,
                  import_cameras=True, import_lights=True,
                  import_geometry=True, import_animation=True)
# Import an FBX file into Action
# Operators say: "bring in the FBX", "import the 3D scene"
```

### Action Output Types

Standard output names used with `enable_output()` / `disable_output()`:

- `"Comp"` — main composite output (always present)
- `"Matte"` — combined matte
- `"3D Motion"` — motion vectors in 3D
- `"Albedo"` — material albedo
- `"AO"` — ambient occlusion
- `"Background"` — background layer
- `"Emissive"` — emissive pass
- `"GMask"` — GMask output
- `"Lens Flare"` — lens flare render
- `"Motion Vectors"` — 2D motion vectors
- `"Normals"` — surface normals
- `"Object ID"` — per-object ID matte
- `"Z Depth"` — depth pass

### Action Usage Examples

```python
import flame

# Get Action node from batch
action = None
for node in flame.batch.nodes:
    if node.type == "Action":
        action = node
        break

# Enable multiple render outputs
action.enable_output("Comp")
action.enable_output("Z Depth")
action.enable_output("Matte")

# Import FBX and add media
action.import_fbx("/path/to/scene.fbx", import_cameras=True)
media = action.add_media()

# Connect media to comp node
comp = action.create_node("Comp")
action.connect_nodes(media, comp, "Front")
```

---

## GMask Tracer (PyGMaskTracerNode)

Operators say: *"add a GMask"*, *"mask it off"*, *"roto the shot"*,
*"paint a matte"*, *"GMask Tracer node"*

`PyGMaskTracerNode` extends `PyActionFamilyNode`.
Uses the same `clear_schematic()`, `connect_nodes()`, `create_node()` as Action.

---

## Color Management (PyClrMgmtNode / PyClrMgmtTimelineFX)

Operators say: *"add a colour management node"*, *"add an ACES transform"*,
*"apply a LUT"*, *"import a CDL"*, *"set up colour space"*,
*"source colour management"*, *"display colour management"*

### PyClrMgmtNode (Batch node)

```python
# Methods
clr.get_context_variables()
# Returns dict of current context variables (e.g. scene_linear, display)
# Operators say: "what colour space is this set to?"

clr.import_transform(file_path)
# Import a colour transform file into the node
# Supports: CDL (.cdl, .cc), CTF (.ctf), LUT (.cube), 3D LUT (.3dl)
# Operators say: "load the LUT", "import the CDL grade", "apply the transform"

clr.reset_context_variables()
# Reset all context variables to defaults

clr.set_context_variable(name, value)
# Set a specific context variable
# Operators say: "set input colour space to scene_linear"
# Common names: "src_colourspace", "dst_colourspace", "display", "view"
```

### PyClrMgmtTimelineFX (Timeline FX version)

Same methods as `PyClrMgmtNode` plus all inherited `PyTimelineFX` methods.

```python
# Typical pattern: add colour management TL FX to a segment
effect = segment.create_effect("Colour Management")
effect.import_transform("/path/to/shot.cdl")
effect.set_context_variable("src_colourspace", "scene_linear")
effect.set_context_variable("dst_colourspace", "rec709")

# The "ratio bug fixer" pattern from community scripts:
# Add Source Color Management TL FX then immediately remove it
fix_fx = segment.create_effect("Source Colour Management")
fix_fx.delete()  # Flame rebuilds the colour pipeline on delete
```

### Color Management Usage Examples

```python
import flame

# Add a LUT to a clip in batch
clr_node = flame.batch.create_node("Colour Management")
clr_node.import_transform("/path/to/lut.cube")

# Apply CDL grade
clr_node.import_transform("/path/to/grade.cdl")

# Set ACES context
clr_node.set_context_variable("src_colourspace", "ACEScg")
clr_node.set_context_variable("dst_colourspace", "Rec.709")

# Check current variables
vars = clr_node.get_context_variables()
print(vars)
```

---

## Exporter (PyExporter)

Operators say: *"export a QuickTime"*, *"export with a preset"*,
*"background export"*, *"BG export"*, *"export EXRs"*,
*"export for approval"*, *"export the master"*, *"export with handles"*

```python
exporter = flame.PyExporter()

exporter.export(
    sources,                  # list of clips/segments/sequences to export
    preset_path,              # str — path to .xml export preset
    output_directory,         # str — destination folder
    background_job_settings=None,   # dict — BG export settings (optional)
    hooks=None                # dict — hook callbacks (optional)
)

# Background export example:
exporter.export(
    sources=[clip],
    preset_path="/opt/Autodesk/presets/2026/export/file/QuickTime.xml",
    output_directory="/deliveries/today/",
    background_job_settings={"enabled": True}
)
```

### Export Presets Location

```
/opt/Autodesk/presets/2026/export/
├── file/
│   ├── QuickTime.xml
│   ├── OpenEXR.xml
│   ├── DPX.xml
│   └── ...
└── sequence/
    └── ...
```

### Common Export Issues

- *"Cannot access frame X: Unrendered frame"* → timeline has unrendered TL FX; call `clip.render()` first
- *"Cannot Complete the Export"* → often a media permissions or storage issue
- *"Flame wants to render first before FG export"* → Flame forces render pass for unrendered FX
- *"Export 1-1-1"* → ProRes full-range: set video_range in preset to "FullRange"
- *"keep TLFX renders after background export"* → set in the export dialog, not via API

---

## MediaHub (PyMediaHub)

Operators say: *"go to MediaHub"*, *"import from MediaHub"*, *"browse the server"*,
*"MediaHub files"*, *"access archives"*

```python
hub = flame.mediahub

# Access file entries
hub.files          # PyMediaHubFilesEntry — the Files tab
hub.archives       # archive entries

# PyMediaHubFilesEntry
hub.files.path     # str — current directory path shown in MediaHub
hub.files.path = "/path/to/media"   # Navigate MediaHub to a directory

# Import via MediaHub — use flame.import_clips() for scripted imports
flame.import_clips("/path/to/media/shot.[1001-1100].exr", destination_reel)
```

---

## Sequence Group (PySequenceGroup)

Operators say: *"group those shots"*, *"create a sequence group"*,
*"add to the group"*, *"remove from the group"*

```python
# Properties
group.segments    # list of PySegment — segments in this group

# Methods
group.add(segments)
# Add a list of segments to the group

group.remove(segments)
# Remove a list of segments from the group

# Create a sequence group
seq_group = sequence.create_segment_group([seg1, seg2, seg3])
```

---

## Timeline (PyTimeline)

The `flame.timeline` object represents the currently open timeline.

```python
# Properties (read-only)
flame.timeline.clip             # PyClip — the sequence being edited
flame.timeline.current_effect   # PyTimelineFX — currently selected TL FX
flame.timeline.current_marker   # PyMarker — currently selected marker
flame.timeline.current_segment  # PySegment — currently selected segment
flame.timeline.current_transition  # PyTransition — selected transition
flame.timeline.type             # str — timeline type

# Switch to timeline tab
flame.set_current_tab("Timeline")

# Get current segment from timeline
seg = flame.timeline.current_segment
if seg:
    print(f"Current shot: {seg.shot_name}, in={seg.record_in}")
```

---

## Conform / EDL / AAF Workflow

Operators say: *"conform from an AAF"*, *"load the EDL"*, *"bring in the offline"*,
*"shots aren't tracking"*, *"relink the media"*, *"the conform didn't link up"*,
*"create batch groups from the timeline"*, *"open the conform tab"*

### Key Concepts

- **Offline edit** = low-res reference from editorial (AAF/XML from Avid/Premiere)
- **Online/conform** = relinking offline to high-res camera original media
- **AAF** = Advanced Authoring Format — Avid's native exchange format
- **EDL** = Edit Decision List — older, CMX3600 format
- **XML** = FCP X or Resolve XML interchange

### Conform API Patterns

```python
import flame

# After a conform, create batch groups from timeline segments
# Operators say: "create batch groups from the timeline"
# NOTE: create_batch_groups() does NOT exist on PySequence in Flame 2026
# Use flame.batch.create_batch_group() instead — see flame_segment_timeline_api.md

seq = flame.timeline.clip  # get current sequence
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type == "Gap":
                continue
            flame.batch.create_batch_group(
                name=seg.shot_name or seg.name,
                reels=["CMP", "REF"],
                shelf_reels=["Batch Renders"],
                start_frame=1001,
                duration=int(seg.record_duration)
            )

# Navigate to Conform tab
flame.set_current_tab("Conform")

# Check current tab
print(flame.get_current_tab())  # "Conform"

# Iterate timeline to find unlinked/offline segments
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type == "Gap":
                print(f"Gap at {seg.record_in} – {seg.record_out}")
            elif not seg.clip:
                print(f"Unlinked segment: {seg.name}")
```

### Post-Conform Workflow Script

```python
import flame

def setup_after_conform(sequence):
    """
    Typical post-conform setup:
    1. Delete empty tracks
    2. Create batch groups for VFX shots
    3. Colour-code segments by type
    """
    ws = flame.projects.current_project.current_workspace

    # 1. Delete empty tracks
    for version in sequence.versions:
        if version.tracks is None:
            continue
        empty_tracks = []
        for track in version.tracks:
            all_gaps = all(seg.type == "Gap" for seg in track.segments)
            if all_gaps:
                empty_tracks.append(track)
        for track in empty_tracks:
            flame.delete(track)

    # 2. Create batch groups for all segments with "VFX" in the name
    vfx_segs = []
    for version in sequence.versions:
        if version.tracks is None:
            continue
        for track in version.tracks:
            for seg in track.segments:
                if seg.type != "Gap" and "VFX" in (seg.shot_name or ""):
                    vfx_segs.append(seg)

    if vfx_segs:
        sequence.create_batch_groups(
            segments=vfx_segs,
            copy_media_to_batch=True,
            reel_names=["CMP", "REF"],
            start_frame=1001
        )
```

### AAF Import Known Issues

- *"Conform not making shots track"* → check AAF has no nested sequences, still frames, or graphics layers
- *"The ratio bug"* → when conforming XML with footage at different resolution from offline:
  add Source Color Management TL FX then immediately remove it
- *"Reels created but media not linked"* → check frame rate of project matches the AAF's frame rate
- Avid AAF with embedded media: set "Import media" option in MediaHub conform settings

---

## Timeline FX (TL FX) and BFX

Operators say: *"add a TL FX"*, *"add a timeline effect"*, *"drop a blur on the timeline"*,
*"BFX"* (batch FX), *"add a Sapphire on the timeline"*, *"bypass the effect"*,
*"save the effect setup"*, *"load the effect setup"*, *"collapse to BFX"*

### Adding Timeline FX

```python
# Add a TL FX to a segment
effect = segment.create_effect("Blur")
effect = segment.create_effect("Colour Management")
effect = segment.create_effect("Colour Warper")
effect = segment.create_effect("Sapphire BlurMoCurves")  # third-party

# List TL FX on a segment
for fx in segment.effects:
    print(f"{fx.name}: bypass={fx.bypass}")
```

### PyTimelineFX Methods

```python
# Properties
fx.name          # str — effect name
fx.type          # str — effect type
fx.bypass        # bool — set to True to bypass
fx.start_frame   # int — effect start in timeline
fx.end_frame     # int — effect end in timeline

# Methods
fx.load_node_setup(filename)   # Load .nst setup file
fx.save_node_setup(filename)   # Save .nst setup file
fx.delete()                    # Remove the effect

# Bypass / un-bypass
fx.bypass = True    # Operators say: "bypass the TL FX"
fx.bypass = False   # "un-bypass it", "turn it back on"
```

### BFX (Batch FX) — Converting TL FX to Batch

```python
# Operators say: "collapse to BFX", "open the BFX", "go into the BFX"
# BFX is a special TL FX that contains a full batch setup

# Check if an effect is a BFX
for fx in segment.effects:
    if fx.type == "BFX":
        print(f"BFX found: {fx.name}")
        # Open the BFX as a batch group
        fx.open_as_batch_group()
```

### Rendering Timeline FX

```python
# Render all TL FX on a clip
# Operators say: "render the clip", "hard commit", "bake the TL FX"
clip.render(
    render_mode="All",                  # "All" or "Selected"
    render_option="Foreground",         # "Foreground" or "Background"
    render_quality="Full Resolution",   # "Full Resolution" or "Proxy Resolution"
    effect_type="",                     # filter by specific effect type (optional)
    effect_caching_mode="Current",      # "Current" or "All Iterations"
    include_handles=False
)

# Check if rendered
if clip.is_rendered():
    print("All TL FX are rendered")
else:
    print("Clip has unrendered TL FX — export will fail")
```

### Save/Load Effect Setups

```python
# Save a TL FX setup for reuse across shots
# Operators say: "save the grade", "save the effect preset"
for fx in segment.effects:
    if fx.name == "Colour Warper":
        fx.save_node_setup("/jobs/SHOW/setups/grade_v01.nst")

# Load on another segment
new_fx = other_segment.create_effect("Colour Warper")
new_fx.load_node_setup("/jobs/SHOW/setups/grade_v01.nst")
```

---

## Batch — Additional Patterns

### Saving and Loading Batch Groups

```python
# "Save batch to library"
ws = flame.projects.current_project.current_workspace
lib = ws.libraries[0]
flame.batch.go_to()
# flame.batch.destination = lib  # set destination before saving
flame.batch.save()

# "Open batch from library"
batch_iter = lib.batch_iterations[0]
batch_iter.open_as_batch_group()
```

### Iterating Batch Versions

```python
# "Iterate the batch" — creates a new version
flame.batch.iterate()         # one iteration
flame.batch.iterate(5)        # jump to iteration 5
```

### Organising the Batch Schematic

```python
# "Tidy up the schematic", "auto-arrange nodes"
flame.batch.organize()
```

---

## Python Hooks Reference

Operators say: *"write a hook"*, *"add a right-click menu item"*,
*"custom action"*, *"run from the menu"*, *"refresh Python hooks"*

### Hook Contexts

| Context | Function name |
|---|---|
| Media Panel | `get_media_panel_custom_ui_actions()` |
| Timeline | `get_timeline_custom_ui_actions()` |
| Batch | `get_batch_custom_ui_actions()` |
| Main Menu | `get_main_menu_custom_ui_actions()` |

### Minimal Hook Template

```python
def get_media_panel_custom_ui_actions():
    return [
        {
            "name": "My Tools",      # submenu name
            "actions": [
                {
                    "name": "My Action",
                    "execute": my_function,
                    "isVisible": True,
                    # "isEnabled": lambda selection: len(selection) > 0,
                }
            ]
        }
    ]

def my_function(selection):
    import flame
    for item in selection:
        print(item.name)
```

### Hook Installation

```bash
# Set hook path before launching Flame:
export DL_PYTHON_HOOK_PATH=/path/to/your/scripts

# Or add to Flame preferences → Python → Hook paths
```

### Important Notes

- After editing a hook: use **Flame menu → Python → Refresh Python Hooks** (no restart needed)
- Third-party module imports at the top of hook files are NOT refreshed by Refresh Python Hooks (restart required)
- The `selection` argument to `execute` functions is a list of selected objects

---

## Quick Reference: Common Operator Phrases → API

| What operator says | API |
|---|---|
| "go to Action" | navigate to batch, find `node.type == "Action"` |
| "add media to Action" | `action.add_media()` |
| "import FBX" | `action.import_fbx(path)` |
| "enable Z Depth output" | `action.enable_output("Z Depth")` |
| "disable Matte output" | `action.disable_output("Matte")` |
| "add a LUT" | `clr.import_transform("/path/to.cube")` |
| "import a CDL" | `clr.import_transform("/path/to.cdl")` |
| "set colour space" | `clr.set_context_variable("src_colourspace", "ACEScg")` |
| "export with preset" | `PyExporter().export(sources, preset_path, output_dir)` |
| "BG export" | `exporter.export(..., background_job_settings={"enabled": True})` |
| "conform from AAF" | use MediaHub conform tab; then `seq.create_batch_groups()` |
| "create batch groups from timeline" | `sequence.create_batch_groups(...)` |
| "add a TL FX" | `segment.create_effect("effect_name")` |
| "bypass the TL FX" | `fx.bypass = True` |
| "save the effect setup" | `fx.save_node_setup("/path/preset.nst")` |
| "load the effect setup" | `fx.load_node_setup("/path/preset.nst")` |
| "hard commit" / "render TL FX" | `clip.render(render_option="Foreground")` |
| "collapse to BFX" | `fx.type == "BFX"` then `fx.open_as_batch_group()` |
| "kick off BG render" | `flame.schedule_idle_event(lambda: flame.batch.render())` |
| "save node setup" | `node.save_node_setup(filename)` |
| "load node setup" | `node.load_node_setup(filename)` |
| "refresh Python hooks" | Flame menu → Python → Refresh Python Hooks |
