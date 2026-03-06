# Flame Community Workflows & Operator Terminology

Source: Logik Forums (forum.logik.tv), community discussions, operator language.
This document maps how Flame artists actually talk about their work to API concepts.

---

## How Operators Describe Common Tasks

### Starting a New Project / Setting Up the Desktop
Operators say: *"nuke the desktop"*, *"clear everything and start fresh"*,
*"set up my reels"*, *"create my online reels"*, *"colour-code my reels"*

Real-world script (from Logik Live #131, Bryan B):
```python
# Clear the Desktop and create 3 Reels with Green colour
import flame
ws = flame.projects.current_project.current_workspace
desktop = ws.desktop
rg = desktop.reel_groups[0]

# Keep at least 1 reel — delete all but the last, then rename/create fresh ones
existing = list(rg.reels)
for reel in existing[:-1]:
    flame.delete(reel)

reel = rg.reels[0]
reel.name = "ONLINE"
reel.colour = (0.0, 0.8, 0.0)   # green

rg.create_reel("VFX")
rg.reels[-1].colour = (0.0, 0.8, 0.0)

rg.create_reel("AUDIO")
rg.reels[-1].colour = (0.0, 0.8, 0.0)
```

---

### Conforming / Online Conform
Operators say: *"conform from an AAF"*, *"load the EDL"*, *"bring in the offline"*,
*"merge offline with the online"*, *"the conform didn't link up"*,
*"shots aren't tracking"*, *"relink the media"*

Key concepts:
- **Offline edit** = low-res reference video from editorial (Avid/Premiere AAF or XML)
- **Online/conform** = process of relinking offline to high-res camera original media
- **AAF/EDL/XML** = edit decision list formats from editorial
- `flame.import_clips()` handles media; conform is done via MediaHub or Wiretap
- After conform: *"create batch groups from timeline"* = `sequence.create_batch_groups()`

---

### Batch Compositing
Operators say: *"go to batch"*, *"open the batch"*, *"set up a comp"*,
*"wire up the nodes"*, *"connect the passes"*, *"throw it in a comp node"*,
*"add a Sapphire"*, *"drop in a Matchbox"*, *"patch the output"*

```python
flame.batch.go_to()  # "go to batch tab"

# "wire up" = connect_nodes
flame.batch.connect_nodes(clip, "BGR", comp, "Front")

# "drop in a Matchbox" = create_node
flame.batch.create_node("Matchbox", "Blur.mx")

# "loop by node type" = iterate flame.batch.nodes
for node in flame.batch.nodes:
    if node.type == "Comp":
        node.flame_blend_mode = "Add"
```

---

### Rendering
Operators say: *"kick off a render"*, *"render to the library"*,
*"background render"*, *"BG render"*, *"foreground render"*, *"FG render"*,
*"render list"*, *"write file node"*, *"render passes"*,
*"cache the timeline"*, *"hard commit"*

```python
# Background render via schedule_idle_event (safe — doesn't block UI)
import flame
def do_render():
    flame.batch.render()
flame.schedule_idle_event(do_render)

# Render Timeline FX on a clip
clip.render(render_mode="All", render_option="Burn", render_quality="Proxy Resolution")

# "hard commit" a timeline segment = render and bake the TL FX
# (done via render then check is_rendered())
print(clip.is_rendered())
```

Operators also say:
- *"No render or write file node enabled in the Render List"* = no Write File node is active in batch
- *"Batch empty after render"* = a known Flame bug; switch view (1-up/2-up) to refresh
- *"In and out in the render node"* = set render range in the Write File node
- *"keep TLFX renders after background export"* = a Flame setting in the export dialog

---

### Timeline Editing
Operators say: *"edit on the timeline"*, *"trim a shot"*, *"slip the clip"*,
*"close the gap"*, *"ripple delete"*, *"add handles"*, *"pad the head/tail"*,
*"insert black at the head"*, *"black head and tail"*

Key terminology:
- **Gap** = empty space between segments on a timeline track (type = "Gap" in PySegment)
- **Handles** = extra frames before/after the cut point (source_in/source_out beyond record marks)
- **Slip** = move the source media within the same record duration (doesn't change edit length)
- **Ripple delete** = remove a segment and pull everything downstream to fill the hole
- **Close gap** = remove a gap segment and pull downstream (see rebuild pattern in FLAME_API.md)

```python
# "add black heads and tails" (from Logik Live #131 script):
# Creates a black clip and adds it as the first segment of selected sequences
# The Black segment goes wherever track patching is set

# Inspect timeline:
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            print(f"{seg.name}: type={seg.type}, in={seg.record_in}, out={seg.record_out}")
```

---

### Export / Delivery
Operators say: *"export a QuickTime"*, *"export with alpha"*, *"export EXRs"*,
*"export for approval"*, *"export the master"*, *"export with metadata overlay"*,
*"FG export"* (foreground), *"BG export"* (background),
*"export with handles"*, *"export subfolders"*

Common issues operators encounter:
- *"Cannot access frame X: Unrendered frame"* = timeline has unrendered TL FX; must render first
- *"Cannot Complete the Export"* = often a media permissions or storage issue
- *"Flame wants to render first before FG export"* = Flame forces a render pass for unrendered FX
- *"Export 1-1-1"* = requesting ProRes tagged as 1-1-1 (full-range) instead of default 1-2-1

---

### Python Hooks
Operators say: *"write a hook"*, *"add a custom action"*, *"right-click menu item"*,
*"run a script from the menu"*, *"refresh python hooks"*, *"reload scripts"*

Hook development notes (from Logik forum):
```bash
# Set hook path before launching Flame:
export DL_PYTHON_HOOK_PATH=/path/to/your/scripts
```

Hook function format:
```python
def get_media_panel_custom_ui_actions():
    return [
        {
            "name": "My Tools",
            "actions": [
                {
                    "name": "My Action",
                    "execute": my_function,
                    "isVisible": True,
                }
            ]
        }
    ]
```

- `get_<context>_custom_ui_actions` where context = `media_panel`, `timeline`, `batch`, etc.
- After editing a hook: *"Refresh Python Hooks"* from Flame menu (no restart needed)
- Third-party module imports at the top are NOT refreshed by Refresh Python Hooks (restart required)

---

### Archive / Storage Workflows
Operators say: *"archive the job"*, *"send to LTO"*, *"pull from tape"*,
*"archive to Facilis"*, *"delete old renders to save space"*,
*"nuke the renders"* (delete cached renders, not the project),
*"clean up the batches"*, *"collect media"* (copy unmanaged clips into the project)

Key concepts:
- **Archive** = Flame's proprietary backup format (not just a folder copy)
- **Managed media** = media stored inside Flame's framestore
- **Unmanaged media** = clips pointing to files outside the framestore
- **Collect media** = copy unmanaged media into the managed framestore (like AE's Collect Files)
- **Facilis** = shared storage system common in post facilities

---

### Flame Quirks Operators Know About
From the forum thread *"Superstition-based Flame workflow rituals"*:

- *"Batch empty after render"* → switch 2-up view to 1-up and back to refresh
- *"Values stuck to zero"* → save iteration, quit Flame, reboot
- *"Conform not making shots track"* → check AAF has no nested sequences, still frames, or graphics layers that confuse the linker
- *"Action Outputs blank"* → known bug since 2024.0.2 in large batch setups with many logo layers
- *"Rendering timeline view instead of batch view"* → batch was created in the timeline; check view context before render
- *"The ratio bug"* → when conforming XML with footage at different resolution than offline: add Source Color Management TL FX then immediately remove it

---

### Scripts from Community (Logik Live #131 — Bryan B)

**Append Start Frame to Name**: Select clips in Media Panel → adds Source Timecode (in frames) to clip name. Useful for deliveries to avoid name collisions.

**Delete Empty Tracks**: Selected sequences have all empty video and audio tracks removed.

**Merge Offline**: Takes a reference video (offline edit) and merges it into an AAF/EDL/XML import. Requirements: same start frame (1:00:00:00), reference video named `[aaf_name]_ref`.

**Open in Photoshop**: Opens any PSD segment/clip/batch input using Photoshop (Mac only).

**Ratio Bug Fixer**: Adds a Source Color Management TL FX and immediately removes it to fix resolution mismatches after conform.

**Import EXR sequence to Library Reel without slate**:
```python
# Import starting at frame 1001 of a sequence that starts at 1000
# (frame 1000 is often a slate/black)
import flame
ws = flame.projects.current_project.current_workspace
lib = ws.libraries[0]
reel = lib.reels[0]
flame.import_clips("/path/to/shot.[1001-1100].exr", reel)
```

**Folder-based Reel creation** (creates a reel on Desktop using tokens to mirror server folder structure).

---

## Common Operator Questions → API Answers

| What operator says | What it means in the API |
|---|---|
| "go to batch" | `flame.batch.go_to()` |
| "create a batch group" | `flame.batch.create_batch_group(name, ...)` |
| "iterate the batch" | `batch.iterate()` or `batch.iterate(5)` |
| "save batch to library" | `desk.destination = lib; batch.save()` |
| "open batch from library" | `lib.batch_iterations[0].open_as_batch_group()` |
| "import passes into batch" | `flame.batch.import_clip(path, reel_name)` |
| "wire up / connect nodes" | `flame.batch.connect_nodes(src, socket, dst, socket)` |
| "tidy / organise the schematic" | `flame.batch.organize()` |
| "drop in a Matchbox" | `flame.batch.create_node("Matchbox", "shader.mx")` |
| "kick off a BG render" | `flame.schedule_idle_event(lambda: flame.batch.render())` |
| "move clips to reel" | `flame.media_panel.move(clips, reel)` |
| "copy clips to reel" | `flame.media_panel.copy(clips, reel)` |
| "select clips in media panel" | `flame.media_panel.selected_entries = clips` |
| "switch to timeline tab" | `flame.set_current_tab("Timeline")` |
| "what tab am I on?" | `flame.get_current_tab()` |
| "add a TL FX / timeline effect" | `segment.create_effect("Blur")` |
| "bypass a node / effect" | `node.bypass = True` or `effect.bypass = True` |
| "create a marker at frame X" | `clip.create_marker(X)` |
| "set in/out on a clip" | `clip.in_mark = 20; clip.out_mark = 60` |
| "reformat a clip" | `clip.reformat(width=1920, height=1080, ratio=1.778)` |
| "render the clip proxy" | `clip.render(render_option="Burn", render_quality="Proxy Resolution")` |
| "is the clip rendered?" | `clip.is_rendered()` |
| "current user" | `flame.users.current_user.name` |
| "get the shot name" | `segment.shot_name` |
| "colour the segment red" | `segment.colour = (1.0, 0.0, 0.0)` |
| "lock the track" | `version.locked = True` |
| "hide the track" | `version.hidden = True` |
| "collapse the version" | `version.expanded = False` |
