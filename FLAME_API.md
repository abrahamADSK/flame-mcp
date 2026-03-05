# Flame 2026 Python API — Cheatsheet for Claude

> Compact reference. Read this before writing any execute_python code.
> Full docs: https://help.autodesk.com/view/FLAME/2026/ENU/?guid=Flame_API_Flame_Python_API_html

---

## Object Hierarchy

```
flame.projects.current_project          → PyProject
  .current_workspace                    → PyWorkspace
    .libraries                          → [PyLibrary]
    .desktop                            → PyDesktop
      .reel_groups                      → [PyReelGroup]
        .reels                          → [PyReel]
          .clips                        → [PyClip / PySequence]
      .batch_groups                     → [PyBatch]
flame.media_panel.selected_entries      → [PyArchiveEntry]
flame.batch                             → PyBatch  (current open batch)
flame.timeline                          → PyTimeline
flame.messages                          → PyMessages
```

---

## Navigation / Access

```python
# Current project and workspace
proj = flame.projects.current_project
ws   = proj.current_workspace
desk = ws.desktop

# Find a library by name
lib = next((l for l in ws.libraries if l.name == "MyLib"), None)

# Find a reel inside a library
reel = next((r for r in lib.reels if r.name == "MyReel"), None)

# Selected items in Media Panel
selected = flame.media_panel.selected_entries        # list
clip     = flame.media_panel.selected_entries[0]     # first item

# Find object by name anywhere in Media Panel
results = flame.find_by_name("clip_name")

# Current Flame version
flame.get_version()   # e.g. "2026.0.0.0"
```

---

## Import Media

```python
# ── TOP-LEVEL (simplest, recommended for Media Panel) ──────────────────────
# destination can be: PyReel, PyLibrary, PyFolder, PyDesktop
clips = flame.import_clips("/path/to/file.mov", destination_reel)
clips = flame.import_clips(["/path/a.mov", "/path/b.mov"], destination_reel)

# Image sequence (two equivalent syntaxes):
clips = flame.import_clips("/dir/clip.[1001-1100].exr", destination_reel)
clips = flame.import_clips("/dir/{name}.{frame}.{extension}", destination_reel)

# ── INTO BATCH (creates a Clip node in the Batch schematic) ────────────────
clip  = flame.batch.import_clip("/path/file.mov", "Reel 1")
clips = flame.batch.import_clips(["/path/a.mov"], "Reel 1")

# ── VIA MEDIAHUB (if you need import options like resize/bit depth) ─────────
tab = flame.mediahub.files
tab.set_path("/path/to/folder")
# Then use flame.import_clips with MediaHub selection
```

---

## Libraries & Reels

```python
# Create library in current workspace
lib = ws.create_library("VFX Shots")

# Create reel inside library
reel = lib.create_reel("Dailies")

# Create reel group inside library
rg = lib.create_reel_group("Review")

# Create folder inside library
folder = lib.create_folder("SubFolder")

# List clips
for clip in reel.clips:
    print(clip.name)

# Move/copy clips in Media Panel
flame.media_panel.copy(source_entries, destination)
flame.media_panel.move(source_entries, destination)

# Commit changes to disk
lib.commit()
reel.commit()
```

---

## Clip Operations

```python
clip = flame.media_panel.selected_entries[0]

# Basic properties
clip.name           # read/write via .name = "new_name"
clip.duration       # PyTime
clip.frame_rate     # str, e.g. "25 fps"
clip.width          # int
clip.height         # int
clip.bit_depth      # int
clip.start_frame    # int

# Tags (Flame 2025+)
clip.tags = ["approved", "vfx"]
all_tags = clip.tags.get_value()
all_tags.append("delivered")
clip.tags = all_tags

# Colour label
clip.colour_label = "Approved"
clip.clear_colour()

# Render
clip.render(render_option="Foreground")  # or "Background Reactor"
clip.is_rendered()   # bool

# Cache
clip.cache_media()
clip.flush_cache_media()

# Create marker
marker = clip.create_marker(frame_number)
marker.colour_label = "To Review"

# Reformat
clip.reformat(width=1920, height=1080, frame_rate="25 fps", resize_mode="Letterbox")

# Wiretap bridge (for low-level access)
node_id    = clip.get_wiretap_node_id()
storage_id = clip.get_wiretap_storage_id()
```

---

## Batch

```python
# Create a new Batch Group on the Desktop
bg = desk.create_batch_group(
    "Shot_010",
    nb_reels=2,
    nb_shelf_reels=1,
    start_frame=1001,
    duration=100
)

# Open a batch group
bg.open()

# Create nodes (node_type must be in flame.batch.node_types)
blur   = flame.batch.create_node("Blur")
render = flame.batch.create_node("Render")
wf     = flame.batch.create_node("Write File")
action = flame.batch.create_node("Action")

# Connect nodes
flame.batch.connect_nodes(source_node, "Default", dest_node, "Default")

# Get existing node by name
node = flame.batch.get_node("Blur1")

# Render current batch
flame.batch.render()
flame.batch.render(render_option="Background Reactor")

# Save setup
flame.batch.save_setup("/path/to/setup.batch")
flame.batch.load_setup("/path/to/setup.batch")

# Iterate (create a new iteration)
flame.batch.iterate()

# Node colours (Flame 2025+)
node.schematic_colour = (0.6, 0.0, 0.0)   # RGB tuple 0.0–1.0
node.schematic_colour_label = "In Progress"
node.clear_schematic_colour()
```

---

## Export

```python
exporter = flame.PyExporter()

# Export clip with a preset
exporter.export(
    sources=clip,                              # PyClip, or list, or container
    preset_path="/path/to/preset.xml",
    output_directory="/output/dir/"
)

# Export options (set before calling export)
exporter.foreground = True
exporter.use_top_video_track = True

# Get preset directories
shared_presets = flame.PyExporter.get_presets_dir(
    flame.PyExporter.Shared,
    flame.PyExporter.Movie
)
```

---

## Messages & UI

```python
# Message bar (non-blocking)
flame.messages.show_in_console("Import done!", "info", 5)   # info/warning/error
flame.messages.show_in_console("Error!", "error")
flame.messages.clear_console()

# Dialog (blocking, returns button string)
result = flame.messages.show_in_dialog(
    title="Confirm",
    message="Delete clip?",
    type="question",          # info / question / warning / error
    buttons=["Yes", "No"],
    cancel_button="No"
)
# result == "Yes" or "No"
```

---

## Project

```python
proj = flame.projects.current_project

# Properties
proj.name
proj.nickname
proj.current_workspace
proj.shared_libraries     # list of PyLibrary

# Colour spaces (Flame 2025.1+)
proj.working_colour_space = "ACES - ACEScct"
available = proj.get_available_colour_spaces()

# Create shared library
shared_lib = proj.create_shared_library("Shared Assets")
proj.refresh_shared_libraries()
```

---

## Sequence / Timeline

```python
# Create sequence in a reel
seq = reel.create_sequence(
    name="Edit_v01",
    video_tracks=1,
    width=1920,
    height=1080,
    frame_rate="25 fps",
    start_at="01:00:00:00",
    duration=250
)

# Open sequence in Timeline
seq.open()

# Timeline access
tl = flame.timeline
current_seg = tl.current_segment
current_clip = tl.clip

# Segment operations
seg = tl.current_segment
seg.trim_head(5)
seg.trim_tail(-5, ripple=True)
seg.slip(10)
seg.create_effect("Blur")

# Copy segment to Media Panel
new_clip = seg.copy_to_media_panel(destination_reel)
```

---

## Wiretap Bridge (Python API side)

```python
# Every Media Panel object has these:
node_id    = obj.get_wiretap_node_id()     # e.g. "/library/0000000100000080"
storage_id = obj.get_wiretap_storage_id()  # e.g. "stonefs"

# Find Python object from Wiretap node ID
obj = flame.find_by_wiretap_node_id(node_id)
```

The Wiretap node ID format is `/projects/<project>/desktops/<desktop>/...`
Use `find_by_wiretap_node_id()` to go from a Wiretap path back to a Python object.

---

## Utility Functions

```python
flame.get_version()                    # "2026.0.0.0"
flame.get_home_directory()             # "/opt/Autodesk/flame_2026/"
flame.get_current_tab()               # "Batch", "MediaHub", "Timeline", etc.
flame.set_current_tab("Batch")        # switch to tab
flame.find_by_name("clip_name")       # search Media Panel
flame.find_by_uid("uid_string")       # find by UID
flame.execute_shortcut("Save")        # trigger Flame shortcut by description
flame.schedule_idle_event(fn, delay=1) # run fn when Flame is idle (non-blocking)

# Run system command via Flame daemon (preferred over subprocess)
flame.execute_command("/usr/bin/cmd arg1 arg2", blocking=True, capture_stdout=True)
```

---

## Common Patterns

```python
# ── Pattern: create reel in existing library (no import) ───────────────────
import flame
ws   = flame.projects.current_project.current_workspace
lib  = next(l for l in ws.libraries if l.name == "Default Library")
reel = lib.create_reel("MY_REEL")
print(f"Created reel: {reel.name} in {lib.name}")

# ── Pattern: create new library and reel ────────────────────────────────────
import flame
ws   = flame.projects.current_project.current_workspace
lib  = ws.create_library("Incoming")
reel = lib.create_reel("Raw")
print(f"Created: {lib.name} / {reel.name}")

# ── Pattern: create library + reel + import file ────────────────────────────
import flame
ws    = flame.projects.current_project.current_workspace
lib   = ws.create_library("Incoming")
reel  = lib.create_reel("Raw")
clips = flame.import_clips("/path/file.mov", reel)
print(f"Imported: {[c.name for c in clips]}")

# ── Pattern: list all libraries and their reels ────────────────────────────
import flame
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    print(f"Library: {lib.name}")
    for reel in lib.reels:
        print(f"  Reel: {reel.name} ({len(reel.clips)} clips)")

# ── Pattern: import file to first reel of current desktop ──────────────────
import flame
proj  = flame.projects.current_project
ws    = proj.current_workspace
desk  = ws.desktop
rg    = desk.reel_groups[0]
reel  = rg.reels[0]
clips = flame.import_clips("/path/file.mov", reel)
print(f"Imported: {[c.name for c in clips]}")

# ── Pattern: get selected clip and print info ──────────────────────────────
import flame
clip = flame.media_panel.selected_entries[0]
print(f"{clip.name} | {clip.duration} | {clip.frame_rate} | {clip.width}x{clip.height}")

# ── Pattern: create batch group from selected clips ────────────────────────
import flame
ws    = flame.projects.current_project.current_workspace
desk  = ws.desktop
clips = flame.media_panel.selected_entries
bg    = desk.create_batch_group("New_Shot", duration=100)
bg.open()
for clip in clips:
    flame.batch.import_clip(clip, "Reel 1")
print(f"Batch group created: {bg.name}")
```

---

## Delete / Remove Objects

```python
# ── flame.delete() — remove any Media Panel object ────────────────────────
# Works on: clips, reels, folders, libraries, sequences, batch groups
# Always wrap in a list, even for a single object
flame.delete(obj)          # delete one object
flame.delete([obj1, obj2]) # delete multiple at once

# ── Pattern: delete a reel by name ────────────────────────────────────────
ws  = flame.projects.current_project.current_workspace
lib = next(l for l in ws.libraries if l.name == "Default Library")
reel = next(r for r in lib.reels if r.name == "OLD_REEL")
flame.delete(reel)
print("Deleted reel")

# ── Pattern: delete multiple reels by name list ────────────────────────────
ws      = flame.projects.current_project.current_workspace
lib     = next(l for l in ws.libraries if l.name == "Default Library")
targets = {"TEST", "TEST2", "DESKTOP_TEST"}
to_del  = [r for r in lib.reels if r.name in targets]
flame.delete(to_del)
print(f"Deleted: {[r.name for r in to_del]}")

# ── Pattern: delete a library by name ─────────────────────────────────────
ws  = flame.projects.current_project.current_workspace
lib = next(l for l in ws.libraries if l.name == "OLD_LIB")
flame.delete(lib)
print("Deleted library")

# ── Pattern: delete a folder inside a library ─────────────────────────────
ws     = flame.projects.current_project.current_workspace
lib    = next(l for l in ws.libraries if l.name == "Default Library")
folder = next(f for f in lib.folders if f.name == "OLD_FOLDER")
flame.delete(folder)
print("Deleted folder")

# ── Pattern: delete all clips in a reel ───────────────────────────────────
ws   = flame.projects.current_project.current_workspace
lib  = next(l for l in ws.libraries if l.name == "Default Library")
reel = next(r for r in lib.reels if r.name == "REEL_NAME")
flame.delete(list(reel.clips))
print(f"Cleared {reel.name}")
```

---


# ── Auto-learned: list all projects via filesystem (flame.projects is not iterable) 
```python
import os
# flame.projects only exposes current_project; no API to list all.
# Read project dirs from filesystem instead:
base = "/opt/Autodesk/project"
projects = [d for d in os.listdir(base) if d != "project.db"]
for p in sorted(projects):
    print(p)
# The currently open project (not stored there) can be found via:
import flame
print(f"Current (active): {flame.projects.current_project.name}")
```

## Projects — list all / switch project

```python
# ── flame.projects is NOT iterable and has NO len() — do NOT do this ───────
# WRONG:  len(flame.projects)           → TypeError: PyProjectSelector has no len()
# WRONG:  for p in flame.projects:      → TypeError: not iterable
# WRONG:  flame.projects[0]             → TypeError: not subscriptable

# ── Correct: current project only ───────────────────────────────────────────
import flame
print(flame.projects.current_project.name)   # active project

# ── Correct: list ALL projects via filesystem ────────────────────────────────
import os
base     = "/opt/Autodesk/project"
projects = sorted(d for d in os.listdir(base)
                  if os.path.isdir(os.path.join(base, d)) and d != "project.db")
for p in projects:
    print(p)
import flame
print(f"Currently open: {flame.projects.current_project.name}")

# ── Switch to a different project ────────────────────────────────────────────
import flame
flame.projects.open_project("MY_PROJECT_NAME")
print(f"Switched to: {flame.projects.current_project.name}")
```

---

## Clear Desktop / Empty All Reels from Reel Group

"Clear desktop" is NOT a Flame API method. To empty a reel group, delete each
reel individually using `flame.delete()`.

```python
import flame

ws   = flame.projects.current_project.current_workspace
desk = ws.desktop

# ── Delete ALL reels from ALL reel groups on the desktop ─────────────────────
for rg in desk.reel_groups:
    for reel in list(rg.reels):   # list() copy — modifying while iterating is unsafe
        flame.delete(reel)
print("Desktop cleared.")

# ── Delete all reels from ONE specific reel group ────────────────────────────
rg_name = "Reels"
for rg in desk.reel_groups:
    if str(rg.name) == rg_name:
        for reel in list(rg.reels):
            flame.delete(reel)
        print(f"Cleared reel group '{rg_name}'")
        break
```

> ⚠️  **NEVER call `.clear()` on any Flame object** (PyReelGroup, PyLibrary,
> PyReel, PyDesktop …).  It is a raw C-level destructor that crashes Flame
> immediately.  Always use `flame.delete(item)` on individual items instead.

---

## Known Crashers — NEVER use these

These patterns are **confirmed to crash or corrupt** Flame. The execute_python
tool will block them automatically.

```python
# ❌ CRASH: PyProjectSelector is not iterable
len(flame.projects)             # TypeError → do NOT use
for p in flame.projects: ...    # TypeError → do NOT use
flame.projects[0]               # TypeError → do NOT use

# ❌ CRASH: project.libraries returns None (use ws.libraries instead)
flame.projects.current_project.libraries      # None → AttributeError on iteration

# ❌ CRASH: flame.batch.render() blocks Flame's main thread
flame.batch.render()            # hangs / crashes → use schedule_idle_event

# ❌ CRASH: .clear() on any Flame object — raw C-level destructor
reel_group.clear()              # crashes Flame immediately
library.clear()                 # crashes Flame immediately
desk.clear()                    # crashes Flame immediately
# ✅ Instead: iterate and flame.delete(item) each child individually

# ❌ CRASH: WireTap C-bindings — destabilise Flame process
import wiretap                  # crash-prone, never use
WireTapServerHandle(...)        # direct C-binding, crashes unpredictably
obj.createNode(...)             # WireTap tree method, unreliable from hooks
obj.getNumChildren(...)         # WireTap tree method, unreliable from hooks
# ✅ Instead: use flame module API only

# ❌ CRASH: ws.replace_desktop() — corrupts workspace state
ws.replace_desktop(new_desktop) # internal method, not safe from Python hooks
# ✅ Instead: use ws.desktop and its reel_groups / reels attributes directly

# ❌ CRASH: flame.clear_desktop() does not exist
flame.clear_desktop()           # AttributeError / crash
# ✅ Instead: see "Clear Desktop" pattern above

# ❌ CRASH: Wiretap bridge is not safe for general scripting
import wiretap                  # complex, crash-prone, not needed for normal ops

# ❌ BAD PRACTICE: do NOT use dir() to discover the API
dir(flame.projects)             # never do this — use search_flame_docs instead
```

**Safe alternatives:**
- List projects → read `/opt/Autodesk/project` directory (see pattern above)
- Libraries → `ws = current_workspace; ws.libraries`
- Renders → `flame.schedule_idle_event(render_fn)`
- Clear desktop → see "Clear Desktop / Empty All Reels" pattern above

---


# ── Auto-learned: delete reels from desktop reel group by name (keep one) 
```python
import flame

ws = flame.projects.current_project.current_workspace
desk = ws.desktop

deleted = []
for rg in desk.reel_groups:
    for reel in list(rg.reels):
        if reel.name != "Sequences":  # nombre a conservar
            flame.delete(reel)
            deleted.append(str(reel.name))

print(f"Reels borrados: {deleted}")
```


# ── Auto-learned: create reel in desktop reel group ─────────────────────
```python
import flame

ws = flame.projects.current_project.current_workspace
desk = ws.desktop

rg = desk.reel_groups[0]
new_reel = rg.create_reel("CLIP sources")
print(f"Reel creado: {new_reel.name}")
```


# ── Auto-learned: get clip duration in frames using PyTime.frame, move clips between reels 
```python
# PyTime duration in frames: clip.duration.frame (not int(clip.duration))
clips_info = [(clip.duration.frame, clip) for clip in source_reel.clips]
clips_info.sort(key=lambda x: x[0], reverse=True)

# Move clip to another reel
flame.media_panel.move(clip, destination_reel)
```


# ── Auto-learned: create sequence from all desktop clips using PyTime and overwrite 
```python
import flame

ws = flame.projects.current_project.current_workspace
desk = ws.desktop

# Collect all clips from all reel groups
all_clips = []
for rg in desk.reel_groups:
    for reel in rg.reels:
        for c in reel.clips:
            all_clips.append(c)

# Find target reel (e.g. "Sequences")
seq_reel = None
for rg in desk.reel_groups:
    for reel in rg.reels:
        if reel.name == 'Sequences':
            seq_reel = reel
            break

total_frames = sum(c.duration.frame for c in all_clips)

seq = seq_reel.create_sequence(
    name="ALL_CLIPS_EDIT",
    video_tracks=1,
    width=1920,
    height=1080,
    frame_rate="25 fps",
    start_at="01:00:00:00",
    duration=total_frames
)

# PyTime(frame_number) is required — passing int directly raises ArgumentError
cursor = 0
for c in all_clips:
    seq.overwrite(c, flame.PyTime(cursor))
    cursor += c.duration.frame

print(f"Done: {len(all_clips)} clips, {cursor} frames")
```


# ── Auto-learned: create sequence from clips without gaps using seq.duration.frame as insert position 
```python
import flame

ws = flame.projects.current_project.current_workspace
desktop = ws.desktop

# Collect clips from reels
all_clips = []
for rg in desktop.reel_groups:
    for reel in rg.reels:
        if "CLIP sources" in str(reel.name) or "SELECTION" in str(reel.name):
            all_clips.extend(reel.clips)

# Get target reel
seq_reel = None
for rg in desktop.reel_groups:
    for reel in rg.reels:
        if "Sequences" in str(reel.name):
            seq_reel = reel
            break

# Create sequence
seq = seq_reel.create_sequence(
    name="Edit_v01",
    width=1920, height=1080,
    frame_rate="25 fps",
    start_at="00:00:00:00",
    duration=1
)

# Insert clips sequentially without gaps
# Key: use seq.duration.frame after each overwrite as next insert point
# Works with mixed fps clips — Flame handles conversion automatically
current_pos = 0
for clip in all_clips:
    seq.overwrite(clip, flame.PyTime(current_pos))
    current_pos = seq.duration.frame

print(f"Done. {len(all_clips)} clips, duration: {seq.duration}")
```


# ── Auto-learned: delete PySequence from desktop reel ───────────────────
```python
import flame

ws = flame.projects.current_project.current_workspace
desk = ws.desktop

for rg in desk.reel_groups:
    for reel in rg.reels:
        if "Sequences" in str(reel.name):
            for s in list(reel.sequences):
                flame.delete(s)  # works for PySequence despite unordered_map error on first attempt
                print(f"Deleted sequence: {s.name}")
```

## Notes & Gotchas

- `flame.projects` and `flame.project` are the same object (`PyProjectSelector`) — NOT iterable
- Libraries live on the **workspace**, not the project: `ws.libraries` not `project.libraries`
- `commit()` must be called to persist changes to disk (clips, reels, libraries)
- `open()` must be called on a Library before accessing its contents if it was closed
- `PyTime` objects support arithmetic: `t1 + t2`, `t + 10` (frames)
- `flame.execute_command()` is preferred over `subprocess` inside Flame hooks
- Node names in Batch are unique — use `get_node("name")` to retrieve them
- `flame.batch` refers to the **currently open** batch group
- Rendering can block Flame UI — prefer `render_option="Background Reactor"` for long renders
- When using `next()` on a list, always provide a default to avoid StopIteration crashes:
  `next((l for l in ws.libraries if l.name == "X"), None)` — then check for None
