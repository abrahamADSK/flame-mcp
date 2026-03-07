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

# Find a library by name (user-visible only — exclude system libraries)
# System/hidden libraries: "Timeline FX", "Grabbed References"
# These appear in ws.libraries but are NOT shown in the Flame interface.
HIDDEN_LIBS = {"Timeline FX", "Grabbed References"}
visible_libs = [l for l in ws.libraries if str(l.name) not in HIDDEN_LIBS]
lib = next((l for l in visible_libs if str(l.name) == "MyLib"), None)

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
flame.execute_shortcut("Undo")        # undo last action (call N times for N undos)
flame.execute_shortcut("Redo")        # redo
flame.schedule_idle_event(fn, delay=1) # run fn when Flame is idle (non-blocking)

# Run system command via Flame daemon (preferred over subprocess)
flame.execute_command("/usr/bin/cmd arg1 arg2", blocking=True, capture_stdout=True)
```

> **Undo from the chat widget:** type `/undo` or `/undo 3` directly in the chat
> input — it triggers Flame's undo stack N times immediately, without going
> through Claude. No confirmation needed.

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

## Save / Copy Desktop Content to Library

"Save desktop to library" means copying a reel group (or its reels/clips) from
the **Desktop** into a **Library** using `flame.media_panel.copy()`.

```python
# ── Pattern: copy entire desktop reel group to library ─────────────────────
import flame
ws   = flame.projects.current_project.current_workspace
desk = ws.desktop
lib  = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
if lib is None:
    print("Library not found"); raise SystemExit

# Copy the first reel group (use index or name to pick the right one)
rg     = desk.reel_groups[0]
result = flame.media_panel.copy([rg], lib)
print(f"Copied '{rg.name}' to library '{lib.name}': {result}")

# ── Pattern: copy a specific reel from desktop to library ───────────────────
import flame
ws   = flame.projects.current_project.current_workspace
desk = ws.desktop
lib  = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)

src_reel = next(
    (r for rg in desk.reel_groups for r in rg.reels if str(r.name) == "Sequences"),
    None)
if src_reel is None:
    print("Source reel not found"); raise SystemExit

result = flame.media_panel.copy([src_reel], lib)
print(f"Copied reel '{src_reel.name}' to '{lib.name}': {result}")

# ── Pattern: move (not copy) reel group from desktop to library ─────────────
import flame
ws   = flame.projects.current_project.current_workspace
desk = ws.desktop
lib  = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
rg   = desk.reel_groups[0]
flame.media_panel.move([rg], lib)
print(f"Moved '{rg.name}' to library '{lib.name}'")
```

> **Note:** After `copy()` or `move()`, the library gains a `reel_groups` attribute
> with the copied content. Check with `lib.reel_groups` (not `lib.reels`).

---

## Folder Operations in Libraries

```python
# ── Inspect: list all folders in a library ─────────────────────────────────
# ⚠️ CRASH RISK: lib.folders can raise a C++ exception on some libraries —
# always wrap in try/except, NEVER call bare `lib.folders or []`
import flame
ws  = flame.projects.current_project.current_workspace
lib = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)

try:
    folders = list(lib.folders or [])
except Exception:
    folders = []
print(f"Folders in '{str(lib.name)}': {[str(f.name) for f in folders]}")

# ── Create folder in library ────────────────────────────────────────────────
folder = lib.create_folder("MyFolder")
print(f"Created folder: {folder.name}")

# ── Delete folder from library ─────────────────────────────────────────────
import flame
ws     = flame.projects.current_project.current_workspace
lib    = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
try:
    folders = list(lib.folders or [])
except Exception:
    folders = []
folder  = next((f for f in folders if str(f.name) == "OLD_FOLDER"), None)
if folder is None:
    print("Folder not found — available:", [str(f.name) for f in folders])
else:
    flame.delete(folder)
    print(f"Deleted folder: OLD_FOLDER")

# ── Import clips INTO a folder (not a reel) ─────────────────────────────────
import flame
ws     = flame.projects.current_project.current_workspace
lib    = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
try:
    all_folders = list(lib.folders or [])
except Exception:
    all_folders = []
folder = next((f for f in all_folders if str(f.name) == "source"), None)
if folder is None:
    folder = lib.create_folder("source")   # create if missing
clips  = flame.import_clips("/path/to/file.mov", folder)
print(f"Imported {len(clips)} clip(s) into folder '{folder.name}'")
```

> **Gotcha — CRASH RISK:** `lib.folders` can raise a Flame C++ exception on some
> library types (caused a confirmed Flame crash in testing). **Always wrap in
> `try/except Exception: folders = []`** — never use bare `lib.folders or []`.

---

## Delete / Remove Objects

```python
# ── flame.delete() — remove any Media Panel object ────────────────────────
# Works on: clips, reels, folders, LIBRARIES, sequences, batch groups
# flame.delete(lib) IS supported — libraries CAN be deleted via the API.
# Always wrap in a list, even for a single object.
flame.delete(obj)          # delete one object
flame.delete([obj1, obj2]) # delete multiple at once

# ── Pattern: delete a reel by name ────────────────────────────────────────
# NOTE: .name is PyAttribute — use str() and next(..., None) to avoid StopIteration
ws   = flame.projects.current_project.current_workspace
lib  = next(l for l in ws.libraries if str(l.name) == "Default Library")
reel = next((r for r in lib.reels if str(r.name) == "OLD_REEL"), None)
if reel is None:
    print("Reel not found")
else:
    flame.delete(reel)
    print("Deleted reel")

# ── Pattern: delete multiple reels by name list ────────────────────────────
# NOTE: reel.name is PyAttribute — ALWAYS use str() for comparisons
ws      = flame.projects.current_project.current_workspace
lib     = next(l for l in ws.libraries if l.name == "Default Library")
targets = {"TEST", "TEST2", "DESKTOP_TEST"}
to_del  = [r for r in lib.reels if str(r.name) in targets]
names   = [str(r.name) for r in to_del]   # collect BEFORE deleting
flame.delete(to_del)
print(f"Deleted: {names}")

# ── Pattern: delete a library by name ─────────────────────────────────────
# NOTE: flame.delete(lib) DOES work on user libraries — confirmed.
# CRITICAL: l.name is PyAttribute — MUST use str() or comparison always fails.
# CRITICAL: always provide a None default to next() to avoid StopIteration.
ws  = flame.projects.current_project.current_workspace
HIDDEN = {"Timeline FX", "Grabbed References"}
lib = next((l for l in ws.libraries
            if str(l.name) == "OLD_LIB" and str(l.name) not in HIDDEN), None)
if lib is None:
    available = [str(l.name) for l in ws.libraries if str(l.name) not in HIDDEN]
    print(f"Library not found. Available: {available}")
else:
    flame.delete(lib)
    print(f"Deleted library: OLD_LIB")

# ── Pattern: delete a folder inside a library ─────────────────────────────
# ⚠️ CRASH RISK: lib.folders raises C++ exception on some libs — use try/except
ws     = flame.projects.current_project.current_workspace
lib    = next((l for l in ws.libraries if str(l.name) == "Default Library"), None)
try:
    folders = list(lib.folders or [])
except Exception:
    folders = []
folder  = next((f for f in folders if str(f.name) == "OLD_FOLDER"), None)
if folder is None:
    print("Folder not found. Available:", [str(f.name) for f in folders])
else:
    flame.delete(folder)
    print("Deleted folder: OLD_FOLDER")

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

> 🚨 **CRITICAL: A desktop reel group MUST always have at least one reel.**
> Deleting ALL reels from a desktop reel group crashes Flame immediately.
> Always keep the last reel — rename it instead of deleting it if you want a clean slate.

```python
import flame

ws   = flame.projects.current_project.current_workspace
desk = ws.desktop

# ── Delete most reels — ALWAYS keep the last one (Flame requires ≥1 reel per group) ──
for rg in desk.reel_groups:
    reels = list(rg.reels)          # snapshot before modifying
    to_delete = reels[:-1]          # keep the LAST reel — never delete all
    for reel in to_delete:
        flame.delete(reel)
    # Optionally rename the surviving reel to something clean
    if rg.reels:
        rg.reels[0].name = "Reel 1"
print("Desktop cleared (one reel kept per group).")

# ── Delete specific reels by name from one reel group ────────────────────────
import flame

ws      = flame.projects.current_project.current_workspace
desk    = ws.desktop
rg_name = "Reels"
keep    = {"Sequences"}   # names to NEVER delete — adjust as needed

for rg in desk.reel_groups:
    if str(rg.name) == rg_name:
        reels     = list(rg.reels)
        to_delete = [r for r in reels if str(r.name) not in keep]
        # Safety: never delete all — keep at least one if all would be removed
        if len(to_delete) == len(reels):
            to_delete = to_delete[:-1]
        for reel in to_delete:
            flame.delete(reel)
        print(f"Deleted {len(to_delete)} reels from '{rg_name}'")
        break
```

> ⚠️  **NEVER call `.clear()` on any Flame object** (PyReelGroup, PyLibrary,
> PyReel, PyDesktop …).  It is a raw C-level destructor that crashes Flame
> immediately.  Always use `flame.delete(item)` on individual items instead.

---

## PyAttribute — reel.name, clip.name, rg.name are NOT strings

> 🚨 **Critical gotcha**: All `.name` attributes in Flame return a `PyAttribute`
> object, NOT a Python `str`. Direct comparison with `==` always fails silently.
> **Always wrap with `str()`** before any comparison or concatenation.

```python
# ❌ WRONG — comparison always False, deletion silently deletes nothing
to_del = [r for r in rg.reels if r.name == "Reel 1"]   # Deleted: []

# ✅ CORRECT — always use str()
to_del = [r for r in rg.reels if str(r.name) == "Reel 1"]

# ✅ ALSO CORRECT for sets / membership tests
keep = {"Sequences", "Reel 1"}
to_del = [r for r in rg.reels if str(r.name) not in keep]

# ✅ CORRECT for next() — always provide a default to avoid StopIteration crash
reel = next((r for r in rg.reels if str(r.name) == "Reel 1"), None)
if reel is None:
    print("Reel not found")
else:
    flame.delete(reel)
```

> ⚠️ **After `flame.delete(reel)`**, do NOT access `reel.name` or any attribute
> of the deleted object — it is invalidated. Collect names BEFORE deleting:
> ```python
> names = [str(r.name) for r in to_del]   # collect first
> for r in to_del: flame.delete(r)          # then delete
> print(f"Deleted: {names}")               # use pre-collected names
> ```

---

## Timeline / Sequence Editing — Segment Delete, Ripple, Gap Close

> **Keywords:** ripple delete, remove segment, delete segment from timeline,
> close gap, remove gap, trim segment, gap fill, sequence gap, timeline edit

> ⚠️ Flame 2026 has NO direct segment-manipulation methods (delete, ripple, trim).
> BUT gaps can be closed by **rebuilding the sequence** placing only non-gap
> segments back-to-back — this IS supported and has worked in practice.

### What you CAN read (inspection is safe)

```python
import flame
ws   = flame.projects.current_project.current_workspace
desk = ws.desktop

# Navigate to sequence
seq = None
for rg in desk.reel_groups:
    for reel in rg.reels:
        if reel.sequences:
            seq = reel.sequences[0]
            break

# Inspect version → tracks → segments
for ver in seq.versions:
    for track in ver.tracks:
        print(f"Track: {str(track.name)}, segments: {len(track.segments)}")
        for seg in track.segments:
            print(f"  type={seg.type} rec_in={seg.record_in} rec_out={seg.record_out}")
```

> **Note:** `ver.tracks` may return `None` in some Flame 2026 contexts.
> Always check: `if ver.tracks is not None:`

### Close Gap / Ripple Delete — rebuild approach

Gap removal works by creating a new sequence containing only the non-gap
segments placed back-to-back. Never call `seg.delete()` or `track.remove_gap()`.

```python
import flame
from flame import PyTime

ws   = flame.projects.current_project.current_workspace
desk = ws.desktop

# Find target reel and sequence
target_reel = next(
    (r for rg in desk.reel_groups for r in rg.reels
     if str(r.name) == "Sequences"), None)
if target_reel is None:
    print("Sequences reel not found"); raise SystemExit

old_seq = next((s for s in target_reel.sequences
                if str(s.name) == "SEQ_MASTER"), None)
if old_seq is None:
    print("Sequence not found"); raise SystemExit

# Collect non-gap segments from first video track
non_gap_segs = []
for ver in old_seq.versions:
    if ver.tracks is None:
        continue
    for track in ver.tracks:
        for seg in track.segments:
            if seg.type != "Gap":   # skip gaps
                non_gap_segs.append(seg)
    break  # first version only

# Create new sequence and overwrite clips back-to-back
new_seq = target_reel.create_sequence(str(old_seq.name) + "_NOGAP")
cursor = PyTime(0)
for seg in non_gap_segs:
    clip = seg.clip          # source clip
    if clip is not None:
        new_seq.overwrite(clip, cursor)
        cursor = PyTime(cursor.frame + seg.record_duration.frame)

print(f"Done: {len(non_gap_segs)} segments, new duration {cursor.frame} frames")
```

### PySegment — read segment properties from timeline

```python
# ── Inspect all segments in a sequence ─────────────────────────────────────
import flame
ws   = flame.projects.current_project.current_workspace
desk = ws.desktop

# Find sequence
seq = None
for rg in desk.reel_groups:
    for reel in rg.reels:
        for s in reel.sequences:
            seq = s
            break

# Read segment data — iterate versions → tracks → segments
for ver in (seq.versions or []):
    if ver.tracks is None:
        continue
    for track in ver.tracks:
        print(f"Track: {track.name}")
        for seg in track.segments:
            print(f"  seg.type={seg.type} "
                  f"rec_in={seg.record_in} rec_out={seg.record_out} "
                  f"src_in={seg.source_in} src_out={seg.source_out} "
                  f"duration={seg.record_duration}")
```

> **Segment types:** `"Gap"` (empty space), `"Clip"` (media), `"Effect"`.
> Check `seg.type != "Gap"` to skip empty slots.
>
> **To delete a segment / close a gap:** Use the rebuild approach below.
> There is NO `seg.delete()` method — it does not exist.

### ❌ Methods that DO NOT EXIST / crash Flame

```python
seg.delete()              # AttributeError → crash
track.remove_gap()        # does not exist
track.ripple()            # does not exist
flame.timeline.delete_gap()  # does not exist
```

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

# ❌ CRASH: importing the Wiretap Python SDK inside Flame's execute_python
import libwiretapPythonClientAPI  # NOT safe inside Flame hooks — use CLI tools via subprocess instead
# ✅ Safe alternative: call wiretap CLI tools via subprocess (see "Wiretap SDK" section)

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


# ── Auto-learned: delete all clips directly in a library (not in reels) ─
```python
import flame

ws = flame.projects.current_project.current_workspace
lib = next(l for l in ws.libraries if l.name == "Default Library")

clips = list(lib.clips)
names = [str(c.name) for c in clips]
for clip in clips:
    flame.delete(clip, confirm=False)
print(f"Deleted {len(names)} clips: {names}")
# NOTE: flame.delete() does NOT accept a list — must delete one at a time
# NOTE: clips can live directly on lib.clips (not inside lib.reels)
```


# ── Auto-learned: access desktop reel groups and reels, delete a reel by name 
```python
import flame

ws = flame.projects.current_project.current_workspace
desktop = ws.desktop

# Desktop has reel_groups, not reels directly
# Each reel_group contains reels
for rg in desktop.reel_groups:
    for reel in rg.reels:
        print(f"{rg.name} -> {reel.name}")

# Delete a specific reel
rg = next(g for g in desktop.reel_groups if g.name == "Reels")
reel = next(r for r in rg.reels if r.name == "REEL_NAME")
flame.delete(reel, confirm=False)
```


# ── Auto-learned: rename reel by setting .name property ─────────────────
```python
import flame
ws = flame.projects.current_project.current_workspace
desk = ws.desktop
rg = desk.reel_groups[0]
reel = next(r for r in rg.reels if r.name == "Reel 1")
reel.name = "SOURCE_CLIPS"
print(f"Renamed to: {reel.name}")
```


# ── Auto-learned: create folder in library and import clips into it ─────
```python
import flame, os

IMPORT_DIR = "/path/to/files"
paths = sorted([
    os.path.join(IMPORT_DIR, f)
    for f in os.listdir(IMPORT_DIR)
    if not f.startswith('.')
])

ws = flame.projects.current_project.current_workspace
lib = next(l for l in ws.libraries if l.name == "Default Library")

# Create folder (or find existing one)
folder = lib.create_folder("source")
# If folder already exists, use (with crash-safe guard):
#   try: all_f = list(lib.folders or [])
#   except Exception: all_f = []
#   folder = next((f for f in all_f if str(f.name) == "source"), None)

result_file = "/tmp/flame_import_result.txt"

def do_import():
    try:
        clips = flame.import_clips(paths, folder)
        msg = f"OK: {[c.name for c in clips]}"
    except Exception as e:
        msg = f"ERROR: {e}"
    with open(result_file, 'w') as f:
        f.write(msg)

flame.schedule_idle_event(do_import)
print(f"Importing {len(paths)} files into folder — scheduled.")
# Then read /tmp/flame_import_result.txt with a separate bridge call to confirm
```


# ── Auto-learned: delete reels by name using PyAttribute get_value() for name comparison 
```python
import flame

ws = flame.projects.current_project.current_workspace
desk = ws.desktop

to_delete = {"Reel 1", "Reel 2", "Reel 3"}
deleted = []

for rg in desk.reel_groups:
    for reel in list(rg.reels):
        name = reel.name.get_value()  # reel.name is PyAttribute, must call .get_value()
        if name in to_delete:
            flame.delete(reel, confirm=False)
            deleted.append(name)

print(f"Deleted: {deleted}")
```


# ── Auto-learned: create sequence from clips in reel using overwrite with PyTime cursor 
```python
import flame

ws = flame.projects.current_project.current_workspace
desktop = ws.desktop

# Find source reel and sequence reel
src_reel = None
seq_reel = None
for rg in desktop.reel_groups:
    for r in rg.reels:
        name = str(r.name).strip("'\"")
        if name == "SOURCE_MEDIA":
            src_reel = r
        elif name == "Sequences":
            seq_reel = r

all_clips = list(src_reel.clips)
total_frames = sum(c.duration.frame for c in all_clips)

# Create sequence
seq = seq_reel.create_sequence(
    name="SEQ_MASTER",
    width=3840,
    height=2160,
    frame_rate="25 fps",
    start_at="01:00:00:00",
    duration=total_frames
)

# Place each clip back-to-back using PyTime cursor
cursor = 0
for c in all_clips:
    seq.overwrite(c, flame.PyTime(cursor))
    cursor += c.duration.frame

print(f"Done: {len(all_clips)} clips placed, {cursor} total frames")
```


# ── Auto-learned: copy desktop reel group to library using flame.media_panel.copy 
```python
import flame
ws = flame.projects.current_project.current_workspace
desk = ws.desktop
lib = next((l for l in ws.libraries if str(l.name).strip("'") == "Default Library"), None)

rg = list(desk.reel_groups)[0]
result = flame.media_panel.copy([rg], lib)
print(f"Result: {result}")
# Verifying: lib now has reel_groups with the copied content
# lib.reel_groups → copied reel group with reels
# Sequences reel: use r.sequences (not r.clips) to access sequences
```


# ── Auto-learned: create folder in library by creating reel ─────────────
```python
import flame
ws = flame.projects.current_project.current_workspace
default_lib = ws.libraries[0]  # Default Library
new_reel = default_lib.create_reel("KK")
```

---

## Wiretap SDK — IFFFS Server Access
<!-- Keywords: wiretap ifffs project create metadata cross-project node hierarchy cli tools subprocess -->

Wiretap is Autodesk's content-management server that underlies every Flame installation.
It exposes the full project/library/clip database as a navigable node tree.

**Two usage modes:**
- **CLI tools** (`/opt/Autodesk/wiretap/tools/current/`) — call via `subprocess` from
  inside Flame Python. Safe, no import required.
- **Python SDK** (`libwiretapPythonClientAPI`) — for EXTERNAL scripts that run *outside*
  Flame. Do NOT import inside Flame's `execute_python` — crashes Flame.

---

### IFFFS Node Hierarchy

The complete tree structure exposed by `localhost:IFFFS`:

```
/projects                        ← PROJECTS (root)
  /<project-uuid>                ← PROJECT  (one per project)
    /<workspace-uuid>            ← WORKSPACE
      /...                       ← DESKTOP
        /...                     ← REEL_GROUP  (≥1, user reel groups on Desktop)
          /...                   ← REEL  → CLIP*
        /...                     ← BATCH_CONTAINER  (one per batch group)
          /...                   ← SAVED_BATCH
          /...                   ← REEL_LIST  (shelf reels)
          /...                   ← SAVED_BATCH_LIST  (saved iterations)
      /Libraries                 ← LIBRARY_LIST (workspace-specific)
        /...                     ← LIBRARY
          /...                   ← REEL → CLIP*
          /...                   ← FOLDER
          /...                   ← CLIP  (directly in lib, no reel)
    /Shared Libraries            ← LIBRARY_LIST (shared across all workspaces)
      /...                       ← LIBRARY → REEL / FOLDER / CLIP
    /setups/...                  ← NODE → SETUP (per VFX module: Paint, CC, Keyer…)
```

**Node type rules:**
- `DESKTOP` → save to library or restore from library via Wiretap copy/duplicate
- `LIBRARY` can only be destroyed when empty (delete clips/reels first)
- `PROJECT` can be destroyed even with libraries present (libraries are deleted too)
- Moving a `REEL_LIST` out of a `BATCH_CONTAINER` converts it to `REEL_GROUP`
- Only one `DESKTOP` and one `LIBRARY_LIST` node per `WORKSPACE`

---

### Wiretap CLI Tools — Reference
<!-- Keywords: wiretap_print_tree wiretap_create_node wiretap_destroy_node wiretap_get_children wiretap_duplicate_node -->

All tools live in `/opt/Autodesk/wiretap/tools/current/`.
Call from inside Flame Python using `subprocess`.

```python
import subprocess, json

WTAP = "/opt/Autodesk/wiretap/tools/current"

def _wt(*args):
    """Run a wiretap CLI tool, return stdout as string."""
    result = subprocess.run([f"{WTAP}/{args[0]}"] + list(args[1:]),
                            capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"wiretap error: {result.stderr.strip()}")
    return result.stdout.strip()

# ── List all projects (names) ────────────────────────────────────────────────
output = _wt("wiretap_get_children", "-h", "localhost:IFFFS", "-n", "/projects", "-N")
print(output)
# MyProject
# MyOtherProject

# ── Print full node tree (depth 3) from /projects ───────────────────────────
output = _wt("wiretap_print_tree", "-h", "localhost:IFFFS", "-n", "/projects", "-d", "3", "-k")
print(output)

# ── Get node ID for a project by display name ────────────────────────────────
# wiretap_get_children without -N returns node IDs
children = _wt("wiretap_get_children", "-h", "localhost:IFFFS", "-n", "/projects")
# Returns lines of: <node_id>  <display_name>
# Parse to find UUID for "MyProject"

# ── Get project XML metadata ─────────────────────────────────────────────────
project_uuid = "080f2228-89cb-47c6-ac10-5c434df570da"  # from wiretap_get_children
xml = _wt("wiretap_get_metadata",
          "-h", "localhost:IFFFS",
          "-n", f"/projects/{project_uuid}",
          "-s", "XML")
print(xml)   # full <Project>…</Project> XML

# ── Get clip SourceData metadata (MIO XML, similar to Open Clip) ─────────────
clip_node_id = "/projects/uuid/workspace-uuid/library-uuid/reel-uuid/clip-uuid"
mio_xml = _wt("wiretap_get_metadata",
              "-h", "localhost:IFFFS",
              "-n", clip_node_id,
              "-s", "SourceData")

# ── Create a new workspace under an existing project ─────────────────────────
new_node = _wt("wiretap_create_node",
               "-h", "localhost:IFFFS",
               "-n", f"/projects/{project_uuid}",
               "-t", "WORKSPACE",
               "-d", "NewWorkspace")
print(f"Created: {new_node}")

# ── Create a library under a workspace Libraries list ────────────────────────
# First find the Libraries node ID (child of workspace named "Libraries")
lib_list_id = "0036dc7f_67deac7c_000c5228"  # from wiretap_print_tree
_wt("wiretap_create_node",
    "-h", "localhost:IFFFS",
    "-n", f"/projects/{project_uuid}/{lib_list_id}",
    "-t", "LIBRARY",
    "-d", "MyNewLib")

# ── Duplicate a node (copy clip/reel to another location) ────────────────────
_wt("wiretap_duplicate_node",
    "-h", "localhost:IFFFS",
    "-s", source_clip_node_id,
    "-n", dest_library_node_id,
    "-d", "CopiedClip")

# ── Destroy (delete) a node ───────────────────────────────────────────────────
_wt("wiretap_destroy_node",
    "-h", "localhost:IFFFS",
    "-n", node_id_to_delete)

# ── Rename a node ─────────────────────────────────────────────────────────────
_wt("wiretap_rename_node",
    "-h", "localhost:IFFFS",
    "-n", node_id,
    "-d", "NewDisplayName")

# ── Check node type ───────────────────────────────────────────────────────────
node_type = _wt("wiretap_get_node_type", "-h", "localhost:IFFFS", "-n", node_id)
# Returns: PROJECT / WORKSPACE / LIBRARY / REEL / CLIP / DESKTOP / …

# ── Ping Wiretap server (health check) ───────────────────────────────────────
_wt("wiretap_ping", "-h", "localhost:IFFFS")
```

> **Note (Autodesk):** CLI tools are for testing/prototyping. For mission-critical
> automation use the Python SDK (`libwiretapPythonClientAPI`) in external scripts.

---

### Create a Project via Wiretap CLI

```python
import subprocess, textwrap, tempfile, os

WTAP = "/opt/Autodesk/wiretap/tools/current"

project_xml = textwrap.dedent("""\
    <Project>
      <Name>MyNewProject</Name>
      <FrameWidth>1920</FrameWidth>
      <FrameHeight>1080</FrameHeight>
      <FrameDepth>10-bit</FrameDepth>
      <AspectRatio>1.77778</AspectRatio>
      <FieldDominance>PROGRESSIVE</FieldDominance>
      <FrameRate>25 fps</FrameRate>
      <DefaultStartFrame>1001</DefaultStartFrame>
      <IntermediatesProfile>65796:596088</IntermediatesProfile>
    </Project>
""")

# Write XML to temp file
with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
    f.write(project_xml)
    xml_path = f.name

try:
    result = subprocess.run(
        [f"{WTAP}/wiretap_create_node", "-h", "localhost:IFFFS",
         "-n", "/projects", "-d", "MyNewProject",
         "-s", "XML", "-f", xml_path],
        capture_output=True, text=True, timeout=30
    )
    print(result.stdout)
finally:
    os.unlink(xml_path)
```

---

### Project XML — IntermediatesProfile Codec Codes
<!-- Keywords: intermediates profile codec prores dnxhr dnxhd openexr quicktime apple prores -->

The `<IntermediatesProfile>` element uses the format `<integer>:<integer>`.
First integer = container/codec, second integer = float pixel format.

**Common combinations:**

| Codec | `<IntermediatesProfile>` |
|---|---|
| Apple ProRes 4444 XQ + OpenEXR (PIZ) | `65541:596088` |
| Apple ProRes 4444 + OpenEXR (PIZ) | `65540:596088` |
| Apple ProRes 422 HQ + OpenEXR (PIZ) | `65539:596088` |
| Apple ProRes 422 + OpenEXR (PIZ) | `65538:596088` |
| Apple ProRes 4444 XQ Raw | `65797:596088` |
| Apple ProRes 4444 Raw | `65796:596088` |
| Apple ProRes 422 HQ Raw | `65795:596088` |
| Apple ProRes 422 Raw | `65794:596088` |
| DNxHR/DNxHD 444 Raw | `512:596088` |
| DNxHR/DNxHD HQ Raw | `513:596088` |
| DNxHR/DNxHD SQ Raw | `514:596088` |
| Uncompressed OpenEXR (PIZ) | `0:596088` |
| Uncompressed Raw | `2:596088` |

**Float pixel format second values (common):**

| Format | Second integer |
|---|---|
| OpenEXR (PIZ) | `596088` |
| OpenEXR (DWAA) | `1120376` |
| OpenEXR (uncompressed) | `6264` |
| Raw | `64704` |

**Project XML editable fields:**

| XML Element | Type | Editable | Description |
|---|---|---|---|
| `<Name>` | string | No (creation only) | Project name |
| `<Description>` | string | Yes | Free-form description |
| `<FrameWidth>` | integer 24–16384 | Yes | Default resolution width (multiple of 2) |
| `<FrameHeight>` | integer 24–16384 | Yes | Default resolution height |
| `<FrameDepth>` | string | Yes | `8-bit` / `10-bit` / `12-bit` / `16-bit fp` / `32-bit fp` |
| `<AspectRatio>` | decimal 0.001–100 | Yes | Pixel aspect ratio |
| `<FieldDominance>` | string | Yes | `PROGRESSIVE` / `FIELD_1` / `FIELD_2` |
| `<FrameRate>` | string | Yes | `23.976 fps` / `24 fps` / `25 fps` / `29.97 fps DF` / `29.97 fps NDF` / `30 fps` / `50 fps` / `59.94 fps DF` / `59.94 fps NDF` / `60 fps` |
| `<IntermediatesProfile>` | int:int | Yes | Codec (see table above) |
| `<ProxyWidth>` | integer | Yes | Proxy width (multiple of 4) |
| `<ProxyWidthHint>` | decimal 0–1 | Yes | Ratio proxy/full width |
| `<ProxyQuality>` | string | Yes | `lanczos` / `draft` / `bicubic` / `mitchell` / `gaussian` |
| `<OCIOConfigFile>` | string | Yes | Absolute path to OCIO config file |
| `<ColourPolicyName>` | string | Yes | Named OCIO policy (mutually exclusive with OCIOConfigFile) |
| `<DefaultStartFrame>` | integer ≥0 | Yes | Start frame (e.g. `1001`) |
| `<HdrMode>` | string | Yes | `Dolby Vision 2.9` / `Dolby Vision 4.0` |
| `<ProjectDir>` | string | Creation only | Path for project home dir (use `&lt;project name&gt;` token) |
| `<MediaDir>` | string | Creation only | Path for media cache |
| `<Template>` | string | Creation only | Project template name |

---

### Force Save to Disk (Commit)

Changes made via Wiretap are auto-committed 2 seconds after the last operation.
To force immediate save:

```python
# Python SDK (external scripts only — NOT inside Flame execute_python)
import libwiretapPythonClientAPI as wiretap

server  = wiretap.WireTapServerHandle("localhost:IFFFS")
project_node = wiretap.WireTapNodeHandle(server, f"/projects/{project_uuid}")
project_node.setMetaData("COMMIT", "")   # forces flush to disk for project + all children

# Or commit at library level (affects that library's clips only)
lib_node = wiretap.WireTapNodeHandle(server, lib_node_id)
lib_node.setMetaData("COMMIT", "")
```

> Committing a clip node actually commits its parent library/workspace.
> Committing a project node commits everything.

---

### Cross-Project Copy via Wiretap CLI

The Flame Python API only operates on the active project. Wiretap can read/write
any project by node ID regardless of which project Flame has open.

```python
import subprocess

WTAP = "/opt/Autodesk/wiretap/tools/current"

# Copy a reel from ProjectA to a library in ProjectB (both can be inactive)
subprocess.run([
    f"{WTAP}/wiretap_duplicate_node",
    "-h", "localhost:IFFFS",
    "-s", "/projects/<projectA-uuid>/<ws-uuid>/<reel-uuid>",  # source
    "-n", "/projects/<projectB-uuid>/<ws-uuid>/<lib-list-uuid>/<lib-uuid>",  # dest
    "-d", "CopiedReel"
], check=True)
```

> **Limitation:** Wiretap requires exclusive access to modify a library or workspace.
> If Flame has that library open for read/write, the operation will fail with an error.
> Close the library in Flame first, or run the operation when Flame is idle.

---

### Wiretap Python SDK — External Scripts

For Python scripts that run **outside** Flame (e.g. from Terminal, render farm, CI):

```python
# Python interpreter with Wiretap bundled: /opt/Autodesk/python/<version>/bin/python
import libwiretapPythonClientAPI as wiretap

# Connect to IFFFS server on localhost
server = wiretap.WireTapServerHandle("localhost:IFFFS")

# Get root node
root   = wiretap.WireTapNodeHandle(server, "/projects")

# List children
num    = wiretap.WireTapInt()
root.getNumChildren(num)
for i in range(int(num)):
    child = wiretap.WireTapNodeHandle()
    root.getChild(i, child)
    node_id = wiretap.WireTapNodeId()
    child.getNodeId(node_id)
    print(node_id.id())

# Get project XML metadata
project_node = wiretap.WireTapNodeHandle(server, f"/projects/{project_uuid}")
metadata     = wiretap.WireTapStr()
project_node.getMetaData("XML", "", 1, metadata)
print(str(metadata))   # <Project>…</Project>

# Set project description
project_node.setMetaData("XML", wiretap.WireTapStr("<Project><Description>My desc</Description></Project>"))

# Create a LIBRARY under a LIBRARY_LIST node
lib_list_node = wiretap.WireTapNodeHandle(server, lib_list_node_id)
new_lib_node  = wiretap.WireTapNodeHandle()
lib_list_node.createNode("MyLib", "LIBRARY", new_lib_node)

# Duplicate a node (cross-reel copy)
dest_node = wiretap.WireTapNodeHandle()
source_node.duplicateNode(dest_parent_node, "ClipCopy", dest_node)

# Discover available metadata stream IDs on a node
n_streams = wiretap.WireTapInt()
project_node.getNumAvailableMetaDataStreams(n_streams)
for i in range(int(n_streams)):
    stream_id = wiretap.WireTapStr()
    project_node.getAvailableMetaDataStream(i, stream_id)
    print(str(stream_id))   # "XML", "COMMIT", "ProjectLocator", …
```

> **⚠️ Do NOT** `import libwiretapPythonClientAPI` inside Flame's `execute_python`.
> Use the CLI tools via `subprocess` instead (see section above).

---

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
