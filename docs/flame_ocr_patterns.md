# flame-mcp OCR Patterns — Extracted from YouTube Videos

> Patterns extracted via frame OCR from 6 high-priority Flame Python tutorial videos.
> Sources: Logik.tv and Autodesk YouTube channels (March 2026).
> Videos: jfxJYUnWIjY, wTRwYyXTosk, GA0ipgNXhnI, 0SpDr3tMdPI, e2ob2gNoea8, ewKoYXkqEXA

---

## Python Console — Basic Workspace Traversal

From the Flame Python Console. The simplest way to inspect the current workspace and libraries interactively.

```python
import flame

# Access current workspace
ws = flame.projects.current_project.current_workspace
print(ws)

# List libraries
for lib in ws.libraries:
    print(lib.name)
```

Key point: always use `current_workspace` to reach libraries. `flame.projects.current_project.libraries` returns `None`.

---

## Watch Folder — Auto-Import with schedule_idle_event

Pattern from jfxJYUnWIjY (Logik.tv, "Python Scripting in Flame"). Demonstrates a watch-folder that polls a directory and imports new media into a reel on a timed schedule.

```python
import flame
import os

WATCH_DIR = "/path/to/watch/folder"
TARGET_LIBRARY = "Default Library"
TARGET_REEL = "Incoming"

def do_watch_folder():
    ws = flame.projects.current_project.current_workspace
    lib = next((l for l in ws.libraries if l.name == TARGET_LIBRARY), None)
    if lib is None:
        return
    reel = next((r for r in lib.reels if r.name == TARGET_REEL), None)
    if reel is None:
        return

    for fname in os.listdir(WATCH_DIR):
        fpath = os.path.join(WATCH_DIR, fname)
        if os.path.isfile(fpath):
            flame.import_clips(fpath, reel)

    # Re-schedule: poll every 10 seconds
    flame.schedule_idle_event(do_watch_folder, delay=10)

def app_initialized(project_name):
    """Hook called when Flame starts or a project is loaded."""
    flame.schedule_idle_event(do_watch_folder, delay=5)
```

Notes:
- `flame.schedule_idle_event(fn, delay=N)` schedules `fn` to run after `N` seconds on Flame's idle loop.
- `app_initialized(project_name)` is a standard Flame hook — Flame calls it automatically on startup.
- Never call `flame.import_clips` from a timer callback directly without `schedule_idle_event`.

---

## Custom Media Panel Action — Export / Publish Script

Pattern from GA0ipgNXhnI. A fully-structured `get_media_panel_custom_ui_actions()` hook with export logic, using `flame.PyClip`, `scope_clip`, and `flame.go_to`.

```python
import flame
import os

def export_clips(selection):
    """Export selected clips to a publish path."""
    for clip in selection:
        # Build export path from clip metadata
        clip_name = clip.name.get_value()
        new_export_path = os.path.join("/jobs/publish", clip_name)
        os.makedirs(new_export_path, exist_ok=True)

        # Export using MediaHub
        flame.go_to("MediaHub")
        # (additional export logic with exporter preset here)

def scope_clip(selection):
    """Return True only when at least one PyClip is selected."""
    for item in selection:
        if isinstance(item, flame.PyClip):
            return True
    return False

def get_media_panel_custom_ui_actions():
    return [
        {
            "name": "Export",
            "actions": [
                {
                    "name": "Publish Clip",
                    "isVisible": scope_clip,
                    "execute": export_clips,
                }
            ]
        }
    ]
```

Notes:
- `get_media_panel_custom_ui_actions()` is the hook Flame calls to populate right-click menus in the Media Panel.
- `scope_clip` controls visibility: the menu item only appears when a `flame.PyClip` is selected.
- `flame.go_to("MediaHub")` navigates Flame's UI to the MediaHub tab programmatically.
- `clip.name.get_value()` — clip name is a `PyAttribute`, call `.get_value()` to get the string.

---

## Timeline Markers — Create Marker with Dialog

Pattern from e2ob2gNoea8 (Logik.tv Python Browsing & Messaging tutorial). Creates a timeline marker on either the current segment or the parent clip, with a user dialog to choose scope.

```python
import flame

segment = flame.timeline.current_segment

dialog = flame.messages.show_in_dialog(
    title="Create Marker",
    message="Do you want to create the Marker on the Segment or the Clip?",
    type="question",
    buttons=["Segment", "Clip"],
    cancel_button="Cancel",
)

if dialog == "Segment":
    duration = segment.record_duration
    marker = segment.create_marker(segment.record_in)
    marker.duration = duration

if dialog == "Clip":
    # Walk up the object tree until we find a PyClip
    parent = segment.parent
    while (isinstance(parent, flame.PyClip) != True) and parent:
        parent = parent.parent
    duration = segment.record_duration
    marker = parent.create_marker(segment.record_in)
    marker.duration = duration
```

Notes:
- `flame.timeline.current_segment` — the segment currently selected in the timeline.
- `flame.messages.show_in_dialog(...)` — shows a blocking dialog; returns the label of the clicked button, or `cancel_button` value if dismissed.
- `segment.record_in`, `segment.record_duration` — timeline record-side timecode attributes.
- `segment.create_marker(timecode)` — creates a marker at the given timecode on the segment.
- `parent.create_marker(timecode)` — same, but on the parent PyClip.
- Walk pattern: `while (isinstance(parent, flame.PyClip) != True) and parent: parent = parent.parent`

---

## Timeline Markers — Set Marker Colour

Continuation of the markers script above. After creating the marker, prompt the user to choose a colour.

```python
import flame

# (marker already created as `marker` from previous step)

dialog2 = flame.messages.show_in_dialog(
    title="Marker Colour",
    message="Select a Colour for the new Marker",
    type="question",
    buttons=["Red", "Green", "Blue"],
    cancel_button="Yellow",
)

if dialog2 == "Red":
    marker.colour = (0.75, 0.0, 0.0)
if dialog2 == "Green":
    marker.colour = (0.0, 0.75, 0.0)
if dialog2 == "Blue":
    marker.colour = (0.0, 0.0, 0.75)
if dialog2 == "Yellow":
    marker.colour = (0.75, 0.75, 0.0)
```

Notes:
- `marker.colour` accepts an RGB tuple of floats in the range 0.0–1.0.
- Standard Flame colours: Red `(0.75, 0.0, 0.0)`, Green `(0.0, 0.75, 0.0)`, Blue `(0.0, 0.0, 0.75)`, Yellow `(0.75, 0.75, 0.0)`.
- `cancel_button` in `show_in_dialog` can be any string — it's returned when the user dismisses the dialog without clicking a main button.

---

## Batch Group Duration — Sync to Clip Duration

Pattern from e2ob2gNoea8 (BatchDuration.py tab). Finds the first Clip node in the current batch group and sets the batch duration to match it. Shows an error dialog if no clip is found.

```python
import flame

batch_group = flame.batch
clip = None

for node in batch_group.nodes:
    if node.type == "Clip":
        clip = node
        break

if clip:
    batch_group.duration = clip.duration
else:
    dialog = flame.messages.show_in_dialog(
        title="No Clip Found",
        message="The Batch Group duration can't be set because there is no Clip node in the batch.",
        type="error",
        buttons=["Close"],
    )
    if dialog == "Close":
        pass
```

Notes:
- `flame.batch` — the currently open batch group object.
- `batch_group.nodes` — iterable of all nodes in the batch; each node has a `.type` string attribute.
- `node.type == "Clip"` — identifies Clip (media) nodes; other types include `"Render"`, `"TimeWarp"`, `"Comp"`, etc.
- `batch_group.duration = clip.duration` — sets batch duration to match a clip node's duration.
- `flame.messages.show_in_dialog(..., type="error")` — shows an error-style dialog (red icon).

---

## flame.messages.show_in_dialog — Reference

All `show_in_dialog` parameter options, compiled from multiple tutorial examples:

```python
import flame

result = flame.messages.show_in_dialog(
    title="Dialog Title",           # str — window title
    message="Body text here.",      # str — message content
    type="question",                # str — "question" | "info" | "warning" | "error"
    buttons=["OK", "Cancel"],       # list[str] — main action buttons (left to right)
    cancel_button="Cancel",         # str — button or label for ESC/close action
)

# result is a str matching the label of the button clicked
if result == "OK":
    pass
```

Dialog types and their icons:
- `"question"` — question mark icon (blue)
- `"info"` — information icon
- `"warning"` — warning triangle (yellow)
- `"error"` — error icon (red)

---

## PyBrowser — Browse Media with Python

Pattern from e2ob2gNoea8 (PyBrowser.py tab). Opens Flame's built-in media browser from Python to let the user pick a file path.

```python
import flame

# Open the PyBrowser for the user to select a media file
browser = flame.PyBrowser(
    title="Select Media File",
    mode="Open",
    filter=["*.mov", "*.mxf", "*.exr"],
)

if browser.path:
    selected_path = browser.path
    # Import the selected file
    ws = flame.projects.current_project.current_workspace
    lib = next((l for l in ws.libraries if l.name == "Default Library"), None)
    reel = next((r for r in lib.reels if r.name == "Incoming"), None)
    flame.import_clips(selected_path, reel)
```

Notes:
- `flame.PyBrowser` opens Flame's native file browser dialog.
- `browser.path` returns the selected path string, or `None` if cancelled.
- Combine with `flame.import_clips(path, reel)` to import the selected file.

---

## get_batch_custom_ui_actions — Batch Right-Click Menu Hook

Parallel to `get_media_panel_custom_ui_actions`, this hook adds items to the batch schematic right-click menu.

```python
import flame

def my_batch_action(selection):
    for node in selection:
        print(f"Selected node: {node.name} type={node.type}")

def get_batch_custom_ui_actions():
    return [
        {
            "name": "My Tools",
            "actions": [
                {
                    "name": "Print Selected Nodes",
                    "execute": my_batch_action,
                }
            ]
        }
    ]
```

Notes:
- `selection` in batch context is a list of batch node objects.
- Each node has `.name`, `.type`, `.pos_x`, `.pos_y` attributes.
- To also appear in timeline right-click menus use `get_timeline_custom_ui_actions()` with the same structure.
