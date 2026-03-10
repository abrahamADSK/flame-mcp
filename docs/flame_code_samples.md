# Flame Python API — Real Code Samples

> Extracted from official Autodesk ZIP downloads and open-source Flame tools.
> Sources: FLC video descriptions, Logik Live sessions, LOGIK-PROJEKT GitHub repo.
> All code is real, tested Python used in production Flame pipelines.

---

## Hook Registration — Modern API (Flame 2020+)

Flame loads Python scripts from `/opt/Autodesk/shared/python/` at startup (or on Rescan).
Each hook module defines one or more entry-point functions that Flame calls to discover custom actions.

### get_media_panel_custom_ui_actions

Used to add right-click menu items in the Media Panel (libraries, reels, desktops, clips).

```python
def get_media_panel_custom_ui_actions():
    def scope_reel(selection):
        import flame
        for item in selection:
            if isinstance(item, flame.PyReelGroup):
                return True
        return False

    def create_reel(selection):
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
                    "execute": create_reel
                }
            ]
        }
    ]
```

Key points:
- `isVisible` callback receives `selection` list, returns bool (show/hide menu item)
- `isEnabled` callback (alternative) controls greyed-out vs active state
- `execute` callback receives same `selection` list
- Return value is a list of menu group dicts, each with `"name"` and `"actions"` keys
- Import `flame` inside each function, not at module level

### get_batch_custom_ui_actions

Used to add right-click menu items inside the Batch schematic.

```python
def get_batch_custom_ui_actions():
    def scope_back(selection):
        return len(selection) == 0   # True when nothing is selected

    def add_render(selection):
        import flame
        flame.batch.create_node("Render")

    return [
        {
            "name": "PYTHON: BATCH",
            "actions": [
                {
                    "name": "Add Render Node",
                    "isEnabled": scope_back,
                    "execute": add_render
                }
            ]
        }
    ]
```

### get_timeline_custom_ui_actions

Used to add right-click menu items in the Timeline editor.

```python
def get_timeline_custom_ui_actions():
    def scope_segment(selection):
        import flame
        for item in selection:
            if isinstance(item, flame.PySegment):
                return True
            return False

    def create_marker(selection):
        import flame
        for item in selection:
            # Walk up to find the parent PyClip
            parent = item.parent
            while not isinstance(parent, flame.PyClip) and parent:
                parent = parent.parent
            duration = item.record_duration
            marker = parent.create_marker(item.record_in)
            marker.duration = duration

    def create_seg_marker(selection):
        import flame
        for item in selection:
            duration = item.record_duration
            marker = item.create_marker(item.record_in)
            marker.duration = duration

    return [
        {
            "name": "PYTHON: SEGMENT",
            "actions": [
                {
                    "name": "Create Marker Based on Segment Duration",
                    "isVisible": scope_segment,
                    "execute": create_marker
                },
                {
                    "name": "Create Segment Marker Based on Segment Duration",
                    "isVisible": scope_segment,
                    "execute": create_seg_marker
                },
            ]
        }
    ]
```

---

## Scope Functions — Type Checking Patterns

Scope functions receive `selection` (a list of Flame Python objects) and return `True`/`False`.
Use `isinstance()` with the appropriate `flame.Py*` class.

```python
# Check for reel group selection
def scope_reel_group(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PyReelGroup):
            return True
    return False

# Check for library selection
def scope_library(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PyLibrary):
            return True
    return False

# Check for desktop selection
def scope_desktop(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PyDesktop):
            return True
    return False

# Check for segment in timeline
def scope_segment(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PySegment):
            return True
    return False

# Check for marker attached to a segment
def scope_segment_marker(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PyMarker):
            if isinstance(item.parent, flame.PySegment):
                return True
    return False

# Check for a batch Clip node (by type string)
def scope_clip_node(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PyNode):
            if item.type == "Clip":
                return True
    return False

# Check for any batch node
def scope_any_node(selection):
    import flame
    for item in selection:
        if isinstance(item, flame.PyNode):
            return True
    return False

# Empty selection (nothing selected in batch)
def scope_empty(selection):
    return len(selection) == 0
```

---

## Batch Operations

### Creating Nodes

```python
import flame

# Create a Render node
flame.batch.create_node("Render")

# Create an Action node
action = flame.batch.create_node("Action")

# Create a Mux node and position it relative to current node
current = flame.batch.current_node.get_value()
mux = flame.batch.create_node("Mux")
mux.pos_x = current.pos_x + 200
mux.pos_y = current.pos_y
mux.set_context(1, "Result")

# Connect two nodes
flame.batch.connect_nodes(current, "Default", mux, "Default")
```

### Add Mux to Selected Node — Full Script

```python
def get_batch_custom_ui_actions():
    def scope_node(selection):
        import flame
        for item in selection:
            if isinstance(item, flame.PyNode):
                return True
        return False

    def add_mux_to_node(selection):
        import flame
        current = flame.batch.current_node.get_value()
        mux = flame.batch.create_node("Mux")
        mux.pos_x = current.pos_x + 200
        mux.pos_y = current.pos_y
        mux.set_context(1, "Result")
        flame.batch.connect_nodes(current, "Default", mux, "Default")

    return [
        {
            "name": "PYTHON: NODES",
            "actions": [
                {
                    "name": "Add Mux Node to Current Node",
                    "isVisible": scope_node,
                    "execute": add_mux_to_node
                }
            ]
        }
    ]
```

### Action Node with Media and Motion Vectors

```python
def create_motion(selection):
    import flame
    for item in selection:
        clip = flame.batch.current_node.get_value()
        action = flame.batch.create_node("Action")

        # Position action to the right of clip
        pos_x = clip.pos_x
        pos_y = clip.pos_y
        action.pos_x = pos_x + 400
        action.pos_y = pos_y

        # Add a media node inside Action
        media = action.add_media()
        media.pos_x = pos_x + 200
        media.pos_y = pos_y

        # Connect clip → media
        flame.batch.connect_nodes(clip, "Default", media, "Default")

        # Create Motion Vectors Map node inside Action
        motion_map = action.create_node("Motion Vectors Map")

        # Cache the motion vectors over the clip duration
        start = flame.batch.start_frame.get_value()
        end = start + clip.duration.get_value()
        motion_map.cache_range(start, end)
```

### Creating Batch Groups and Importing Clips

```python
import flame

# Create a new batch group
bg = flame.batch.create_batch_group("MyNewBatch")

# Import a clip from disk into a schematic reel
clip = bg.import_clip(filename.encode("utf-8"), "Schematic Reel 1")

# Sync batch group duration to clip, rename it
bg.duration = clip.duration
bg.name = clip.name
bg.expanded = False
```

### Full Batch + Motion Cache from Desktop Selection

```python
def get_media_panel_custom_ui_actions():
    def scope_desktop(selection):
        import flame
        for item in selection:
            if isinstance(item, flame.PyDesktop):
                return True
        return False

    def create_batch_motion(selection):
        import flame, os
        from PySide2 import QtWidgets

        for item in selection:
            flame.go_to("Batch")

            # Open file picker
            actWindow = QtWidgets.QApplication.instance().activeWindow()
            filenames, filter = QtWidgets.QFileDialog.getOpenFileNames(
                actWindow,
                "Select one or more files to load",
                "/",
                "All files (*)",
                None,
                QtWidgets.QFileDialog.DontUseNativeDialog
            )

            for filename in filenames:
                bg = flame.batch.create_batch_group("MyNewBatch")
                clip = bg.import_clip(filename.encode("utf-8"), "Schematic Reel 1")
                bg.duration = clip.duration
                bg.name = clip.name
                bg.expanded = False

                action = flame.batch.create_node("Action")
                pos_x = clip.pos_x
                pos_y = clip.pos_y
                action.pos_x = pos_x + 400
                action.pos_y = pos_y
                media = action.add_media()
                media.pos_x = pos_x + 200
                media.pos_y = pos_y
                flame.batch.connect_nodes(clip, "Default", media, "Default")

                motion_map = action.create_node("Motion Vectors Map")
                start = flame.batch.start_frame.get_value()
                end = start + clip.duration.get_value()
                motion_map.cache_range(start, end)

    return [
        {
            "name": "PYTHON: DESKTOP",
            "actions": [
                {
                    "name": "Create Batch and Cache Motion Vectors Map",
                    "isVisible": scope_desktop,
                    "execute": create_batch_motion
                }
            ]
        }
    ]
```

---

## Media Panel Operations

### Creating Reels

```python
import flame

# Create a reel in a reel group, inherit colour from parent
for item in selection:
    reel = item.create_reel("New Reel")
    reel.colour = reel.parent.colour
```

### Shared Libraries

```python
import flame
from PySide2 import QtWidgets

# Get artist name via dialog
dlg = QtWidgets.QInputDialog()
dlg.setLabelText("Enter the artist name")
if dlg.exec_():
    name = str(dlg.textValue())

# Create shared library, acquire exclusive access, add folders
shared = flame.project.current_project.create_shared_library(name)
shared.acquire_exclusive_access()
shared.create_folder("from_" + name)
shared.create_folder("to_" + name)
shared.release_exclusive_access()
```

Full hook script for shared library creation:

```python
def get_media_panel_custom_ui_actions():
    def scope_libraries(selection):
        import flame
        for item in selection:
            if isinstance(item, flame.PyLibrary):
                return True
        return False

    def create_shared_library(selection):
        import flame
        from PySide2 import QtWidgets

        dlg = QtWidgets.QInputDialog()
        dlg.setLabelText("Enter the artist name")
        if dlg.exec_():
            name = str(dlg.textValue())

        shared = flame.project.current_project.create_shared_library(name)
        shared.acquire_exclusive_access()
        shared.create_folder("from_" + name)
        shared.create_folder("to_" + name)
        shared.release_exclusive_access()

    return [
        {
            "name": "PYTHON: Libraries",
            "actions": [
                {
                    "name": "Create Shared Library",
                    "isVisible": scope_libraries,
                    "execute": create_shared_library
                }
            ]
        }
    ]
```

---

## Timeline Operations — Markers

### Create Clip Marker Matching Segment Duration

```python
def create_marker(selection):
    import flame
    for item in selection:
        # Walk up the parent chain to find the PyClip
        parent = item.parent
        while not isinstance(parent, flame.PyClip) and parent:
            parent = parent.parent

        duration = item.record_duration
        marker = parent.create_marker(item.record_in)
        marker.duration = duration
```

### Create Segment-Level Marker

```python
def create_seg_marker(selection):
    import flame
    for item in selection:
        duration = item.record_duration
        marker = item.create_marker(item.record_in)
        marker.duration = duration
```

### Set Segment Markers to Segment Duration

Adjusts an existing marker (attached to a segment) to span the full segment duration:

```python
def get_timeline_custom_ui_actions():
    def scope_markers(selection):
        import flame
        for item in selection:
            if isinstance(item, flame.PyMarker):
                if isinstance(item.parent, flame.PySegment):
                    return True
        return False

    def markers_length(selection):
        import flame
        for item in selection:
            parent = item.parent
            item.location = parent.record_in
            item.duration = parent.record_duration

    return [
        {
            "name": "PYTHON: MARKERS",
            "actions": [
                {
                    "name": "Set Segment Markers to Segment Duration",
                    "isVisible": scope_markers,
                    "execute": markers_length
                }
            ]
        }
    ]
```

Key marker attributes: `marker.location`, `marker.duration`, `marker.colour`, `marker.comment`

---

## Naming Convention Hooks

Flame calls these hooks to get default names for new batch iterations and render nodes.
The `project` argument is the project name string.

```python
# Batch iteration naming hook
def batchDefaultIterationName(project):
    pattern = project + "_<batch name>_<date>_<time>_<iteration##>_FPLC"
    return pattern

# Render node naming hook
def batchDefaultRenderNodeName(project):
    pattern = "<batch name>_<date>_<time>_" + project
    return pattern
```

Available token substitutions in naming patterns:
- `<batch name>` — name of the batch group
- `<date>` — current date
- `<time>` — current time
- `<iteration##>` — auto-incrementing iteration number (zero-padded)
- `<workstation>` — workstation hostname
- `<user nickname>` — logged-in Flame user's nickname

Source: `python_naming_conventions.zip` (FLC video `ZDHntCBBRXM`)

---

## PySide2 UI Dialogs in Hooks

### File Picker Dialog

```python
from PySide2 import QtWidgets

def get_paths():
    actWindow = QtWidgets.QApplication.instance().activeWindow()
    filenames, filter = QtWidgets.QFileDialog.getOpenFileNames(
        actWindow,
        "Select one or more files to load",
        "/",
        "All files (*)",
        None,
        QtWidgets.QFileDialog.DontUseNativeDialog
    )
    return filenames
```

### Text Input Dialog

```python
from PySide2 import QtWidgets

dlg = QtWidgets.QInputDialog()
dlg.setLabelText("Enter the artist name")
if dlg.exec_():
    name = str(dlg.textValue())
```

Note: Always use `DontUseNativeDialog` flag with Flame to avoid conflicts with Flame's own native dialogs.

---

## Old Hook API (pre-Flame 2020)

Before the dict-based hook API, Flame used a different pattern with `getCustomUIActions()` and `customUIAction()`.
This is legacy code — still useful for understanding older scripts.

```python
def getCustomUIActions():
    getLogikShaders = {
        'name': 'getLogikShaders',
        'caption': "Download Latest Logik Shaders"
    }
    webgroup = {
        'name': "Web Utilities",
        'actions': (getLogikShaders,)
    }
    return (webgroup,)

def customUIAction(info, userdata):
    action = info['name']
    if action == 'getLogikShaders':
        import commands, os
        print(commands.getstatusoutput(
            'curl "http://logik-matchbook.org/shaders/logik_shaders_installer.sh" -o /tmp/logik_shaders_installer.sh'
        ))
        print(commands.getstatusoutput(
            'chmod 755 /tmp/logik_shaders_installer.sh && /tmp/logik_shaders_installer.sh'
        ))
```

Differences from modern API:
- Entry points: `getCustomUIActions()` / `customUIAction(info, userdata)`
- Dict keys use `'caption'` instead of `'name'` for display text
- Uses `'name'` as the action identifier for dispatch in `customUIAction`
- `info` dict contains `'name'` key identifying which action was triggered
- No `isVisible`/`isEnabled` callbacks — visibility controlled differently
- Uses Python 2 `commands` module (replaced by `subprocess` in Python 3)

Source: `python_logik_shaders.zip` (FLC video `C5Ez4nlRvTk`)

---

## Wiretap CLI — Project Creation

Flame projects can be created from the command line using the Wiretap tools.
The `wiretap_create_node` binary creates IFFFS nodes directly.

```python
import subprocess

def create_flame_wiretap_node(flame_projekt_name, projekt_xml_path):
    bash_command = f"""
    umask 0
    /opt/Autodesk/wiretap/tools/current/wiretap_create_node \\
        -h 127.0.0.1:IFFFS \\
        -n /projects \\
        -t PROJECT \\
        -d "{flame_projekt_name}" \\
        -s XML \\
        -f "{projekt_xml_path}"
    """
    process = subprocess.Popen(
        bash_command,
        shell=True,
        executable='/bin/bash',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr
```

Wiretap CLI flags:
- `-h 127.0.0.1:IFFFS` — connect to local Flame IFFFS server
- `-n /projects` — parent node path in IFFFS tree
- `-t PROJECT` — node type to create
- `-d <name>` — display name of the new project
- `-s XML` — metadata format
- `-f <path>` — path to XML file with project settings

Source: LOGIK-PROJEKT GitHub (`flamelogik/LOGIK-PROJEKT`)

---

## Flame Installation Detection

Scan `/opt/Autodesk/` for installed Flame versions:

```python
import os
import re

def detect_flame_versions():
    autodesk_path = "/opt/Autodesk"
    flame_prefixes = ("flame", "flare", "flame_assist")
    versions = []

    for entry in os.listdir(autodesk_path):
        full_path = os.path.join(autodesk_path, entry)
        if os.path.isdir(full_path):
            if entry.startswith(flame_prefixes):
                versions.append(entry)

    # Sort by version number extracted from directory name
    def version_key(name):
        match = re.search(r'(\d+)[\._](\d+)', name)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (0, 0)

    versions.sort(key=version_key)
    return versions
```

Python scripts directory for shared hooks: `/opt/Autodesk/shared/python/`

Source: LOGIK-PROJEKT GitHub (`flamelogik/LOGIK-PROJEKT`, `flame_software_utils.py`)

---

## Deployment — Copying Python Scripts to Projects

Script that rsyncs Flame hook scripts into a project-specific directory and patches the base path:

```python
import subprocess
from pathlib import Path

def copy_flame_python_scripts(source_dir, project_dir):
    dest_dir = project_dir / "setups" / "python"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Rsync scripts
    subprocess.run(
        ["rsync", "-av", str(source_dir) + "/", str(dest_dir) + "/"],
        check=True
    )

    # Patch base_python_path in copied scripts
    shared_path = Path('/opt/Autodesk/shared/python')
    for py_file in dest_dir.rglob("*.py"):
        content = py_file.read_text()
        if "base_python_path" in content:
            patched = content.replace(
                str(shared_path),
                str(dest_dir)
            )
            py_file.write_text(patched)
```

Source: LOGIK-PROJEKT GitHub (`flamelogik/LOGIK-PROJEKT`, `copy_flame_python_scripts.py`)

---

## OpenClip Watch Folder — husky.py

A watchdog script (Autodesk, 2015) that monitors a directory for new subdirectories,
then creates `.clip` OpenClip XML files for each new media folder found.

Key patterns:

```python
import xml.dom.minidom as minidom
import os, time, re

# Poll a directory every N seconds
sleepy = 2  # seconds between checks

def watch_directory(target_dir):
    known = set(os.listdir(target_dir))
    while True:
        current = set(os.listdir(target_dir))
        new_entries = current - known
        for entry in new_entries:
            full_path = os.path.join(target_dir, entry)
            if os.path.isdir(full_path):
                create_clip_file(full_path, entry)
        known = current
        time.sleep(sleepy)

# Create OpenClip XML using dl_get_media_info output
def create_clip_file(media_dir, clip_name):
    # Run dl_get_media_info to get media metadata
    import subprocess
    result = subprocess.run(
        ["dl_get_media_info", media_dir],
        capture_output=True, text=True
    )
    # Parse XML output and create .clip file
    doc = minidom.parseString(result.stdout)
    clip_path = os.path.join(media_dir, clip_name + ".clip")
    with open(clip_path, 'w') as f:
        f.write(doc.toprettyxml())
```

The `dl_get_media_info` command is part of the Autodesk Flame/Lustre toolkit and returns
OpenClip-compatible XML describing the media found in a directory.

Source: `python_script01.zip` (FLC video `hPa1OVEY_78`)
Author: Jean-Francois Bouchard & Mathieu Sansregret (Autodesk, 2015)

---

## Common Object Attributes

### PySegment (timeline segment)
```python
segment.record_in        # record in timecode
segment.record_out       # record out timecode
segment.record_duration  # duration in frames
segment.parent           # parent track or clip
```

### PyMarker
```python
marker.location          # position in timeline (timecode)
marker.duration          # duration in frames
marker.colour            # marker colour (tuple)
marker.comment           # text comment
marker.parent            # parent segment or clip
```

### PyNode (batch node)
```python
node.pos_x               # X position in schematic
node.pos_y               # Y position in schematic
node.type                # node type string (e.g. "Clip", "Action", "Render")
node.name                # node name
```

### PyReelGroup
```python
reel_group.create_reel("Reel Name")  # creates and returns a new PyReel
reel_group.colour                     # colour tuple
```

### PyReel
```python
reel.colour              # reel colour tuple
reel.parent              # parent PyReelGroup
```

### flame.batch
```python
flame.batch.create_node("NodeType")              # create a new node
flame.batch.connect_nodes(src, "Default", dst, "Default")  # connect two nodes
flame.batch.current_node.get_value()             # get the currently selected node
flame.batch.start_frame.get_value()              # get batch start frame (int)
flame.batch.create_batch_group("Name")           # create a new batch group
```

### flame.project.current_project
```python
flame.project.current_project.name
flame.project.current_project.create_shared_library("name")
```

---

## Navigation

```python
import flame

# Jump to the Batch environment
flame.go_to("Batch")

# Jump to other areas
flame.go_to("MediaHub")
flame.go_to("Timeline")
```
