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
# ── Pattern: import file to first reel of current desktop ──────────────────
proj  = flame.projects.current_project
ws    = proj.current_workspace
desk  = ws.desktop
rg    = desk.reel_groups[0]
reel  = rg.reels[0]
clips = flame.import_clips("/path/file.mov", reel)
print(f"Imported: {[c.name for c in clips]}")

# ── Pattern: create library + reel + import ────────────────────────────────
lib   = ws.create_library("Incoming")
reel  = lib.create_reel("Raw")
clips = flame.import_clips("/path/file.mov", reel)

# ── Pattern: list all libraries and their reels ────────────────────────────
for lib in ws.libraries:
    print(f"Library: {lib.name}")
    for reel in lib.reels:
        print(f"  Reel: {reel.name} ({len(reel.clips)} clips)")

# ── Pattern: get selected clip and print info ──────────────────────────────
clip = flame.media_panel.selected_entries[0]
print(f"{clip.name} | {clip.duration} | {clip.frame_rate} | {clip.width}x{clip.height}")

# ── Pattern: create batch group from selected clips ────────────────────────
clips = flame.media_panel.selected_entries
bg    = desk.create_batch_group("New_Shot", duration=len(clips[0].duration) if clips else 100)
bg.open()
for i, clip in enumerate(clips):
    flame.batch.import_clip(clip, "Reel 1")
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

## Notes & Gotchas

- `flame.projects` and `flame.project` are the same object (`PyProjectSelector`)
- `commit()` must be called to persist changes to disk (clips, reels, libraries)
- `open()` must be called on a Library before accessing its contents if it was closed
- `PyTime` objects support arithmetic: `t1 + t2`, `t + 10` (frames)
- All Media Panel objects inherit `get_wiretap_node_id()` from `PyArchiveEntry`
- `flame.execute_command()` is preferred over `subprocess` inside Flame hooks
- Node names in Batch are unique — use `get_node("name")` to retrieve them
- `flame.batch` refers to the **currently open** batch group
- Rendering can block Flame UI — prefer `render_option="Background Reactor"` for long renders
