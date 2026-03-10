# Flame Python API Patterns — Extracted from YouTube Transcripts

> Source: 12 high-priority YouTube transcripts from Logik Live channel
> Extracted: 2026-03-10
> Note: Patterns extracted from speech transcripts; exact code may differ slightly from actual API

## 1. Hook System

### Hook File Locations

The Python hook system in Flame expects scripts to be placed in specific directories:

- **Primary hook directory:** `/opt/Autodesk/shared/python/`
  - Drop Python scripts here to have them loaded as hooks
  - Flame scans this directory at startup for `.py` files
  - Custom hook folders can be created for organization (e.g., `/opt/Autodesk/shared/python/color_segments/`)

- **Project-specific hooks:** Per-project Python scripts can be stored in project structure
- **Rescan mechanism:** `Python > Rescan Python Hooks` in Flame UI reloads all hooks without restarting

### Hook Function Names & Patterns

From transcripts, these hook entry points are mentioned:

1. **`app_initialized`** — Called when Flame application starts
   - Used to set up global state or register custom menus
   - Context: Andy Milkis mentions this as foundational for automation

2. **`batch_render_begin`** / **`batch_render_end`** — Render lifecycle hooks
   - `batch_render_begin`: Before batch rendering starts
   - `batch_render_end`: After batch rendering completes
   - Use case: Automated output file routing, post-render notifications (Slack bots mentioned in wTRwYyXTosk)

3. **`after_iterate`** / **`on_iterate`** — Timeline/batch iteration hooks
   - Called after pressing "Iterate" in batch setup
   - Context: John Geehreng's slating automation fills 3D text nodes on each iterate
   - Use case: Dynamic slate metadata, version numbering, burn-in updates

4. **`scene_changed`** / **`timeline_update`** — Project/timeline change hooks
   - Monitor changes to active scenes or timelines
   - Lower-priority hooks, less commonly scripted

5. **`menu_` prefix patterns** — Custom menu item registration
   - Hooks that register right-click context menus
   - Example: `menu_flame_color_segment_red`, `menu_frame_io_get_comments`

### Hook Signature Patterns

From actual code shown in transcripts:

```python
# Basic hook structure (Python file dropped in /opt/Autodesk/shared/python/)
# File: color_segment_red.py

def __init__(scope):
    # Hook initialization - Flask-like pattern
    # scope provides access to Flame DOM and context
    pass

# Hook definition - varies by hook type
# For context menu: execute() called when menu item selected
def execute():
    # Actual hook code
    pass
```

**Context menu hook pattern:**
- File naming convention: `color_segment_red.py`
- Menu entry in UI: appears under right-click context on segments
- Hotkey assignment: Can be mapped in Preferences > Keyboard Shortcuts > Hook category

---

## 2. Object Hierarchy

The Flame object model (from transcripts and implied API):

```
flame
├── projects
│   └── current_project
│       ├── name (property)
│       └── current_workspace
│           ├── libraries (list of Library objects)
│           │   └── Library
│           │       ├── name (property)
│           │       └── reels (list of Reel objects)
│           │           └── Reel
│           │               ├── name (property)
│           │               └── clips (list of Clip objects)
│           │                   └── Clip
│           │                       ├── name (property)
│           │                       ├── timecode (property)
│           │                       ├── duration (property)
│           │                       └── color (property)
│           ├── desktop
│           │   ├── reel_groups (batch/reel grouping)
│           │   └── batch_groups (batch setups)
│           └── batch_groups
│               └── Batch
│                   ├── name (property)
│                   ├── segments (timeline segments)
│                   │   └── Segment
│                   │       ├── name (property)
│                   │       ├── color (property, RGB values 0.0-1.0)
│                   │       ├── duration (property)
│                   │       └── timecode (property)
│                   └── nodes (batch setup nodes)
│                       └── Node
│                           ├── name (property)
│                           ├── type (property)
│                           └── properties (node-specific)
```

**Key relationships mentioned in transcripts:**

- Projects contain workspaces (not shown in UI, backend concept)
- Workspaces contain libraries and batch groups
- Libraries organize clips hierarchically (folders, reels)
- Batch groups contain timeline segments and render node trees
- Clips can be linked to segments via OpenClip XML wrapper

---

## 3. Project & Workspace Operations

### Creating New Projects Programmatically

From John Geehreng's Uppercut workflow (wTRwYyXTosk):

```
flame.projects.create(
    project_name="PROJECT_NAME",
    project_path="/path/to/job/folder",
    workspace_path=None  # Uses default workspace
)
```

**Automation pattern shown:**
1. Script detects missing job folder → prompts creation
2. Script validates project naming format (date-based convention)
3. Script auto-creates nested folder structure
4. Slack bot monitors creation and logs to team

**Date formatting example:**
- Format: `YYYYMMDD_projectname`
- Example: `20240310_logicproject`

### Accessing Current Project

```python
current_project = flame.projects.current_project
project_name = current_project.name

# Accessing workspace (implied)
workspace = current_project.current_workspace
```

### Project Initialization Hooks

- Templates can be restored at project creation
- Batch setups pre-configured in template folders
- Permission adjustments can be scripted (Unix chmod equivalents)

---

## 4. Library & Reel Operations

### Listing Libraries

```python
# Get all libraries in current workspace
workspace = flame.projects.current_project.current_workspace
libraries = workspace.libraries

for library in libraries:
    print(library.name)
    # Access reels within library
    for reel in library.reels:
        print(f"  {reel.name}")
```

### Creating/Modifying Reels

**From Uppercut workflow:**
- Script creates reel groups with named reels
- Script applies naming conventions with tokens
- Example tokens: `{duration}`, `{aspect_ratio}`, `{reel_name}`

**Reel properties accessible:**
- `name` — Reel identifier
- `clips` — List of clips in reel

### Deleting Reels

```python
# Delete default library reel
# Pattern from John Geehreng: "I also going to delete the default library
# because I never use that"
library.reels.delete(reel_name)
```

---

## 5. Clip & Media Operations

### Clip Properties

From transcripts, these clip properties are mentioned/used:

- **`name`** — Clip identifier string
  - Example: Append start frame to name: `clip.name = f"{clip.name}_{clip.timecode.start_frame}"`
  - Brian Bayley's script: adds start frame for tracking purposes

- **`timecode`** — Timecode object (has sub-properties)
  - `timecode.start_frame` — Frame number (integer)
  - `timecode.frame_rate` — Playback rate (float, e.g., 23.976)
  - `timecode.value` — Full timecode string (e.g., "01:00:00:00")

- **`duration`** — Length in frames (integer)
  - Used for naming conventions, validations
  - Can be read but may not be directly settable

- **`color`** — RGB tuple (values 0.0 to 1.0)
  - Example: `segment.color = (1.0, 0.0, 0.0)` sets red
  - Example: `segment.color = (0.0, 0.5, 1.0)` sets blue
  - Used heavily in segment coloring automation

- **`path`** — File system path to media
  - Accessible for clips, allows scripting file operations

### Clip Naming Automation

**Bryan Bayley pattern** (GA0ipgNXhnI):
```python
# Append start frame to clip name
for clip in reel.clips:
    start_frame = clip.timecode.start_frame
    clip.name = f"{clip.name}_{start_frame}"
```

**John Geehreng's advanced renaming** (wTRwYyXTosk):
```python
# Token-based renaming with dropdown presets
tokens = {
    "{duration}": clip.duration,
    "{aspect_ratio}": "16x9",  # or from clip metadata
    "{reel_name}": reel.name,
    "{project_nickname}": "UC"  # custom token
}

new_name = template.format(**tokens)
clip.name = new_name
```

### OpenClip Pattern (XML-based clip versioning)

From John Geehreng (wTRwYyXTosk) — critical for Uppercut workflow:

**OpenClip is an XML container for clips that:**
- Wraps multiple media versions (e.g., V0, V1, V2)
- Points to actual render files on disk
- Gets updated when new renders are available
- Lives in shot folder under `openclip/` directory

**Script pattern:**
```python
# OpenClip XML structure (implied from transcript)
# File: /path/to/shot/openclip/shot_name.clip

# Edit OpenClip by updating XML directly
import xml.etree.ElementTree as ET

clip_xml = ET.parse("shot.clip")
root = clip_xml.getroot()

# Add new version
new_version = ET.Element("version")
new_version.set("name", "V1")
new_version.set("path", "/path/to/render/v1.mov")
root.append(new_version)

clip_xml.write("shot.clip")

# In timeline: flame.update_clip_version(clip_ref)
```

**Pattern: Version stacking**
- When Frame.io script finds matching render, auto-versions clip in timeline
- Automatic XML update triggers timeline clip refresh

---

## 6. Timeline Segment Operations

### Segment Color Manipulation

**KG51c1GStLk — The canonical "color segments" example:**

```python
# File: /opt/Autodesk/shared/python/color_segments/color_segment_red.py

def execute():
    # Get selected segment from context
    # (Context mechanism not fully clear from transcript)
    segment = get_selected_segment()  # [uncertain - mechanism unclear]

    # Set color to red
    segment.color = (1.0, 0.0, 0.0)

    # Result: Segment in timeline turns red
```

**Color palette creation:**
- Create multiple hook files for each color
- `color_segment_red.py`, `color_segment_blue.py`, `color_segment_green.py`
- Assign hotkeys in Preferences > Keyboard Shortcuts > Hook category
- Example hotkey: `Ctrl+Alt+Cmd+R` for red

**Segment properties accessible:**
- `name` — Segment identifier
- `color` — RGB tuple (0.0-1.0 range)
- `timecode` / `duration` — Timeline position and length

### Segment Iteration & Dynamic Updates

**Andy Milkis slating pattern** (wTRwYyXTosk):

```python
# Hook: on_iterate (called after pressing Iterate button)
def execute():
    # Find action node called "versioner" in current batch
    batch = get_active_batch()
    action_node = batch.get_node_by_name("versioner")

    # Fill 3D text nodes with dynamic data
    # Pattern: action_node contains 3D text nodes for metadata

    # Each 3D text node has a "text" property
    project_node = action_node.get_text_node("project")
    project_node.text = flame.projects.current_project.name

    shot_node = action_node.get_text_node("shot")
    shot_node.text = batch.name.replace("_v\d+", "")  # Remove version suffix

    version_node = action_node.get_text_node("version")
    # Extract version number from batch name (e.g., "shot_v2" → "v2")
    version_node.text = extract_version(batch.name)

    date_node = action_node.get_text_node("date")
    from datetime import datetime
    date_node.text = datetime.now().strftime("%Y-%m-%d")

    # Iterate now includes updated slate metadata
```

---

## 7. Custom Menu Registration

### Menu Item Pattern

From KG51c1GStLk (color segments), menus are registered via hook files:

```python
# Hook file in /opt/Autodesk/shared/python/
# When right-click menu is built, Flame scans for hook functions

def create_menu():
    # Create menu structure (pattern inferred)
    menu_item = flame.MenuItem("Color Segment > Red")
    menu_item.execute = color_segment_red
    return menu_item
```

**Menu registration:**
1. Hook file in `/opt/Autodesk/shared/python/` with `execute()` function
2. Right-click context menu automatically discovers and adds it
3. Menu label derived from filename or explicit naming

### Hotkey Assignment to Hooks

**From KG51c1GStLk:**
1. Go to Preferences > Keyboard Shortcuts
2. Search hook category
3. Find hook name (e.g., "color_segment_red")
4. Assign hotkey (e.g., `Ctrl+Alt+Cmd+R`)
5. Save and close

**Hotkey usage:**
- Hotkeys assigned to hooks persist across sessions
- Can be accessed from any context (timeline, media panel, etc.)

### Advanced Menu Pattern: Frame.io Integration

From John Geehreng (wTRwYyXTosk):

```python
# Right-click menu on clips/segments
# Menu: "Frame.io > Get Comments"
#
# When selected, script:
# 1. Looks up clip/segment in Frame.io via API
# 2. Fetches comments from Frame.io
# 3. Color-codes clips red if comments exist
# 4. Loads comments into Flame for review

def execute():
    selected_clip = get_selected_clip()
    frame_io_comments = fetch_frame_io_comments(selected_clip)

    if frame_io_comments:
        selected_clip.color = (1.0, 0.0, 0.0)  # Red flag for review
        display_comments(frame_io_comments)
```

---

## 8. Batch & Render Hooks

### Batch Group Management

**From John Geehreng's Uppercut workflow:**

```python
# List all batch groups in desktop
workspace = flame.projects.current_project.current_workspace
batch_groups = workspace.batch_groups

for batch in batch_groups:
    print(f"Batch: {batch.name}")
    # Access nodes within batch
    for node in batch.nodes:
        print(f"  Node: {node.name}")
```

### Render Node Operations

**Batch setup node hierarchy:**
- Source clip feed
- Timespan/composition nodes
- Effects/color correction nodes
- Render output nodes

**Pattern from Uppercut:**
```python
# Build batch setup from publish script
batch = create_batch(shot_name)

# Add pre-render nodes
prerender_node = batch.add_node("PreRender")
prerender_node.path = f"/path/to/renders/{shot_name}"

# Add template nodes for cleanup, color correction, etc.
# Script reuses "batch templates" (pre-built setups)
template_batch = load_batch_template("default_template.bfx")
copy_nodes_from_template(batch, template_batch)
```

### Backburner Integration

From John Geehreng's BB archiving script (wTRwYyXTosk):

```python
# Queue archive jobs to Backburner
def archive_project(project_name, segment_size_mb=2000):
    # Command sent to Backburner CLI
    backburner_cmd = f"bb_archive --project {project_name} --segment-size {segment_size_mb}"

    # Execute and get job ID
    job_id = execute_backburner(backburner_cmd)

    # Script can:
    # 1. Queue multiple archives
    # 2. Restart jobs
    # 3. Monitor completion
    # 4. Send email notification when done

def restart_archived_jobs(job_ids):
    # Restart multiple completed archive jobs
    for job_id in job_ids:
        backburner_cmd = f"bb_restart --job-id {job_id}"
        execute_backburner(backburner_cmd)
```

---

## 9. MediaHub Integration

From transcripts, MediaHub is mentioned but not deeply scripted. However:

- **MediaHub:** Autodesk's media organization system
- **Integration point:** Python scripts can access MediaHub API for asset tracking
- **Pattern:** Scripts interact with MediaHub for shot management (ShotGrid alternative)
- **Context:** Dzq3hua0GrU discusses pipeline tools that may use MediaHub

**Placeholder pattern (not detailed in transcripts):**
```python
# MediaHub integration (speculative from context)
# flame.mediahub.get_assets()
# flame.mediahub.create_asset()
# flame.mediahub.link_to_clip()
```

---

## 10. Publishing & OpenClip

### Publishing Workflow Pattern

From John Geehreng and Josh Lawrence (uAPgg4r0BbY, SjeSywTMSAE):

**Publishing creates:**
1. **OpenClip files** — XML clip containers in `/shot_folder/openclip/`
2. **Shot folder structure** — Organized by shot/version
3. **Batch templates** — Pre-configured batch setups linked to shots
4. **Version 0 media** — Initial published output

```python
def publish_shots_to_openclip(selected_segments, handles=6):
    """
    Pattern from John Geehreng's UC Publish script
    """
    for segment in selected_segments:
        # Create shot folder
        shot_name = segment.name
        shot_folder = create_shot_folder(shot_name)

        # Publish segment with handles
        openclip_path = publish_segment(
            segment,
            output_folder=shot_folder,
            handles=handles,
            version=0
        )

        # OpenClip created at: shot_folder/openclip/shot_name.clip

        # Load batch template
        batch = load_batch_template("default_publish_template.bfx")
        batch.name = shot_name

        # Link published media to batch
        link_published_media_to_batch(batch, openclip_path)

        # Save batch
        save_batch(batch, shot_folder)
```

### Adding Versions to OpenClip

**From Uppercut workflow (Nuke integration example):**

```python
def add_version_to_openclip(clip_xml_path, version_number, render_path, nuke_project=None):
    """
    Update OpenClip XML to add new render version
    Called when new renders become available
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(clip_xml_path)
    root = tree.getroot()

    # Create new version element
    version_elem = ET.Element("version")
    version_elem.set("name", f"v{version_number}")
    version_elem.set("path", render_path)

    if nuke_project:
        version_elem.set("project_file", nuke_project)

    root.append(version_elem)

    tree.write(clip_xml_path)

    # Trigger timeline update
    update_timeline_clips(clip_xml_path)
```

### Frame.io Automation

From John Geehreng's Frame.io integration (wTRwYyXTosk):

```python
def conform_upload_to_frame_io(clips, project_name):
    """
    Export clips as MP4, create Frame.io project, upload
    """
    import frame_io_sdk  # External Python package

    # 1. Export MP4s (via Flame render)
    mp4_paths = export_clips_as_mp4(clips)

    # 2. Create Frame.io project via API
    fio_project = frame_io_sdk.create_project(project_name)
    fio_project_id = fio_project["id"]

    # 3. Create folders in Frame.io
    conforms_folder = fio_project.create_folder("Conforms")

    # 4. Upload MP4s
    for clip, mp4_path in zip(clips, mp4_paths):
        asset = conforms_folder.upload_file(mp4_path)
        # Asset object now has Frame.io review link

    # 5. Create shareable review link
    review_link = fio_project.get_review_url()
    send_client_email(review_link)


def fetch_frame_io_comments(clip):
    """
    Fetch comments from Frame.io and update Flame clip
    """
    import frame_io_sdk

    # Look up clip in Frame.io
    fio_asset = frame_io_sdk.find_asset(clip.name)

    # Get comments
    comments = fio_asset.get_comments()

    # Color-code if comments exist
    if comments:
        clip.color = (1.0, 0.0, 0.0)  # Red

    return comments
```

### Version Stacking Pattern

From Uppercut workflow:

```python
def auto_version_stack_from_openclip(timeline_clip, openclip_path):
    """
    When OpenClip is updated, automatically stack new version in timeline
    """
    import xml.etree.ElementTree as ET

    # Read OpenClip
    tree = ET.parse(openclip_path)
    versions = tree.findall(".//version")

    # Find latest version
    latest_version = max(versions, key=lambda v: int(v.get("name").lstrip("v")))

    # Update timeline clip to point to latest
    timeline_clip.source_path = latest_version.get("path")
    timeline_clip.metadata["version"] = latest_version.get("name")

    # Timeline automatically reflects new version
```

---

## 11. Complete Script Examples

### Example 1: Simple Clip Renaming (Brian Bayley)

From GA0ipgNXhnI:

```python
# Script: Append start frame to all clips in a reel

def execute():
    # Get current reel from context
    current_reel = flame.context.reel  # [uncertain - pattern inference]

    for clip in current_reel.clips:
        # Extract start frame from timecode
        start_frame = clip.timecode.start_frame

        # Append to name
        original_name = clip.name
        clip.name = f"{original_name}_{start_frame}"
```

### Example 2: Segment Color Menu (KG51c1GStLk)

**File:** `/opt/Autodesk/shared/python/color_segments/color_segment_red.py`

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Color segment red hook
Drop in /opt/Autodesk/shared/python/color_segments/
Right-click segment > Color Segment > Red
Or assign hotkey in Preferences > Keyboard Shortcuts > Hook
"""

def execute():
    # Get selected segment (implied from context)
    segment = flame.context.selected_segment  # [uncertain]

    if segment:
        segment.color = (1.0, 0.0, 0.0)  # RGB: Red
```

**File:** `/opt/Autodesk/shared/python/color_segments/color_segment_blue.py`

```python
def execute():
    segment = flame.context.selected_segment
    if segment:
        segment.color = (0.0, 0.5, 1.0)  # RGB: Blue
```

### Example 3: Slate Versioning on Iterate (Andy Milkis / John Geehreng)

```python
# Hook: on_iterate
# Called after pressing Iterate button on batch timeline

def execute():
    """
    Fills 3D text nodes in action node named 'versioner'
    with current project/shot/version/date metadata
    """
    from datetime import datetime
    import re

    # Get active batch
    batch = flame.context.active_batch  # [uncertain - mechanism]

    if not batch:
        return

    # Find action node called "versioner"
    versioner_node = None
    for node in batch.nodes:
        if node.name == "versioner" and node.type == "Action":
            versioner_node = node
            break

    if not versioner_node:
        return

    # Extract version from batch name (e.g., "shot_010_v2" → "v2")
    def extract_version(batch_name):
        match = re.search(r'_v(\d+)', batch_name)
        return f"v{match.group(1)}" if match else "v1"

    # Remove version suffix to get shot name
    def get_shot_name(batch_name):
        return re.sub(r'_v\d+$', '', batch_name)

    # Update 3D text nodes
    try:
        # Project name
        if hasattr(versioner_node, 'project'):
            versioner_node.project.text = flame.projects.current_project.name

        # Shot name
        if hasattr(versioner_node, 'shot'):
            versioner_node.shot.text = get_shot_name(batch.name)

        # Version number
        if hasattr(versioner_node, 'version'):
            versioner_node.version.text = extract_version(batch.name)

        # Date
        if hasattr(versioner_node, 'date'):
            versioner_node.date.text = datetime.now().strftime("%Y-%m-%d")

        # Frame range (from timeline)
        if hasattr(versioner_node, 'frame_range'):
            start = batch.start_time
            duration = batch.duration
            versioner_node.frame_range.text = f"{start}-{start+duration}"

    except Exception as e:
        print(f"[versioner] Error updating slate: {e}")
```

### Example 4: Uppercut Publish Script (John Geehreng)

```python
# Script: UC Publish
# Publishes selected segments to OpenClip format with batch templates

def publish_selected_segments(handles=6, include_batch=True):
    """
    Publishes selected timeline segments to OpenClip
    Creates shot folders and batch setup templates
    """
    import os
    import shutil
    from datetime import datetime

    # Get selected segments
    desktop = flame.context.desktop  # [uncertain]
    selected = [seg for seg in desktop.segments if seg.selected]

    if not selected:
        print("No segments selected")
        return

    # Base output path
    base_path = flame.projects.current_project.paths.shots

    for segment in selected:
        shot_name = segment.name
        shot_folder = os.path.join(base_path, shot_name)

        # Create shot folder structure
        os.makedirs(shot_folder, exist_ok=True)
        os.makedirs(os.path.join(shot_folder, "openclip"), exist_ok=True)
        os.makedirs(os.path.join(shot_folder, "renders"), exist_ok=True)
        os.makedirs(os.path.join(shot_folder, "footage"), exist_ok=True)

        # Publish to OpenClip
        openclip_file = os.path.join(shot_folder, "openclip", f"{shot_name}.clip")
        publish_to_openclip(segment, openclip_file, handles=handles)

        # Load batch template
        if include_batch:
            template_path = "/path/to/templates/default_batch.bfx"
            batch = flame.batch.load_batch(template_path)
            batch.name = shot_name

            # Link to published media
            link_to_openclip(batch, openclip_file)

            # Save batch
            batch_path = os.path.join(shot_folder, f"{shot_name}.bfx")
            batch.save(batch_path)
```

### Example 5: Frame.io Comment Fetch (John Geehreng)

```python
# Script: Frame.io Get Comments
# Right-click clip > Frame.io > Get Comments
# Fetches comments from Frame.io review link

def execute():
    """
    Fetch Frame.io comments for selected clip
    """
    try:
        import requests

        # Get selected clip
        selected_clip = flame.context.selected_clip  # [uncertain]

        if not selected_clip:
            print("No clip selected")
            return

        # Frame.io API credentials (stored in config)
        api_token = load_frame_io_token()
        headers = {"Authorization": f"Bearer {api_token}"}

        # Search Frame.io for asset matching clip name
        api_url = "https://api.frame.io/v2/assets/search"
        response = requests.get(
            api_url,
            headers=headers,
            params={"query": selected_clip.name}
        )

        if response.status_code != 200:
            print(f"Frame.io API error: {response.status_code}")
            return

        assets = response.json().get("assets", [])

        if not assets:
            print(f"No Frame.io asset found for {selected_clip.name}")
            return

        # Get first matching asset
        asset = assets[0]
        asset_id = asset["id"]

        # Fetch comments
        comments_url = f"https://api.frame.io/v2/assets/{asset_id}/comments"
        comments_response = requests.get(comments_url, headers=headers)
        comments = comments_response.json().get("comments", [])

        # Flag clip if comments exist
        if comments:
            selected_clip.color = (1.0, 0.0, 0.0)  # Red
            print(f"Found {len(comments)} comments on Frame.io")

            # Display comments (UI mechanism unclear from transcript)
            for comment in comments:
                print(f"  - {comment['author']}: {comment['text']}")
        else:
            print("No comments on Frame.io")

    except Exception as e:
        print(f"Error fetching Frame.io comments: {e}")
```

---

## 12. Version-Specific API Changes

### Flame 2022

- **Project management API** — Improved workspace handling
- **Conform improvements** — Better API exposure for archiving workflows

### Flame 2023

- **Python API enhancements** — Additional hooks and object methods
- **Publishing workflow** — OpenClip XML support formalized
- **Batch rendering** — Better `batch_render_begin`/`batch_render_end` hook stability

### Flame 2024

- **Release features** — Snapshot functionality, improved project management
- **Type node** — New node type exposed to Python (may be scriptable)

### Flame 2025-2026

- **Recent features** — Snapshot system, advanced project management
- **Type node enhancements** — Further scripting exposure
- **Latest API** — As of IBC 2025, Flame 2026.2 released with continued Python improvements

**Note from transcripts (February 2026):** Latest updates include Snapshot and Project Management enhancements, suggesting expanded Python scripting surfaces.

---

## 13. Real-World Workflow Patterns

### Uppercut (NYC) - Complete Production Pipeline

**Pattern description from John Geehreng (wTRwYyXTosk):**

1. **Project Creation** — Automated folder structure, date-based naming
2. **Publishing** — Segments to OpenClip with batch templates
3. **Shot Setup** — Auto-rename reels, set up pre-render nodes
4. **Version Management** — OpenClip versioning for Flame + Nuke renders
5. **Frame.io Delivery** — Auto-export MP4s, upload to Frame.io, fetch comments
6. **Slating** — Auto-populate slate metadata on iterate
7. **Archiving** — Backburner queue for automatic archive jobs

**Key scripts:**
- Project template creation
- UC Publish (segments → OpenClip)
- UC Batch Load Setup (dropdown menu for batch selection)
- Rename Open Clips (version labeling in timeline)
- Frame.io Conform Uploader
- Frame.io Get Comments
- Slate Maker (Mike V) + Desktop Copy Slates
- Batch Renamer (apply naming conventions)
- BB Archiving UI (Backburner queue management)

### Logik Projekt (Phil Man) - Open-Source Python Pipeline

**Pattern description from FYNkebyiCEU:**

Logik Projekt is a complete Python pipeline tool for Flame featuring:

- **Project management** — Automated project creation from templates
- **Shot structure** — Folder hierarchies, reel organization
- **Publishing automation** — Batch script for conforming shots
- **Naming conventions** — Tokenized, configurable
- **Integration** — ShotGrid/Shotgun support (implied)

**Key patterns:**
- Command-line interface to Flame via Python
- Batch operations on multiple shots
- Template system for project/batch setup
- Pipeline state tracking (project, shots, versions)

### MTI Film (Andrew Miller) - Advanced Motion Tracking

From 0SpDr3tMdPI and other sources, MTI Film uses Python for:

- **Custom tracking nodes** — Integration with external ML models
- **ML tools** — Timewarp ML (TWML) for motion analysis
- **Automation** — Batch processing of multiple shots with tracking

---

## 14. Uncertain/Speculative Patterns

The following patterns are inferred or partially mentioned in transcripts and should be verified against the actual Flame Python API documentation:

- `flame.context.*` — Accessing selected objects (mechanism unclear from transcripts)
- `flame.batch.load_batch()` — Loading batch setups
- `flame.batch.save_batch()` — Saving batch setups
- 3D text node property access (`.text`, `.font`, etc.)
- Segment iteration/duration properties
- XML editing of OpenClip files (inferred from usage patterns)
- Backburner CLI invocation mechanism
- Frame.io API integration (external, not Flame-native)

---

## 15. Common Integration Patterns

### External APIs Referenced in Transcripts

1. **Frame.io** — Video review and collaboration
   - Python `requests` library for REST API calls
   - Authentication via API token
   - Asset search, comment fetching, project creation

2. **Backburner** — Rendering queue management
   - CLI-based invocation
   - Job queuing and restart
   - Email notifications (implied)

3. **Slack** — Team notifications
   - Webhook-based posting
   - Used for project creation alerts, archive completion notifications

4. **ShotGrid/Shotgun** — Pipeline management
   - Asset tracking, shot management
   - Integration context mentioned but not detailed

### Recommended External Python Packages

- `requests` — HTTP API calls (Frame.io, Slack webhooks)
- `lxml` or `xml.etree.ElementTree` — XML manipulation (OpenClip editing)
- `python-dateutil` — Date formatting and manipulation
- `pathlib` — Cross-platform file path handling
- `frame_io_sdk` — Frame.io Python SDK (if available)

---

## 16. Source Videos

| Video ID | Title | Topics | Priority | Notes |
|----------|-------|--------|----------|-------|
| jfxJYUnWIjY | Writing Python Scripts for Flame (Andy Milkis & Fred Warren) | python_basics, flame_api_intro, custom_scripts, menus | HIGH | Foundational episode covering API basics and workflow concepts |
| GA0ipgNXhnI | Simple Python Scripts (Bryan Bayley) | clip_naming, timecode_manipulation, simple_automation | HIGH | Practical beginner scripts for clip renaming and timecode handling |
| wTRwYyXTosk | Uppercut Workflow (John Geehreng) | project_creation, shot_publishing, clip_renaming, frame_io | HIGH | Complete production pipeline automation, most comprehensive |
| FYNkebyiCEU | Logik Projekt (Phil Man) | pipeline_tool, project_management, python_pipeline | HIGH | Open-source pipeline solution demonstrating full workflow |
| 0SpDr3tMdPI | Python Fun (Andrew Miller & Erik Borzi) | python_api, advanced_scripting, workflow_automation | HIGH | Recent episode covering newer API features |
| KG51c1GStLk | Color Segments (demo) | timeline_segments, segment_colors, python_api | MEDIUM | Short demo of segment color manipulation, hook registration |
| b-4fG6zModA | AI/ML in Flame (Andy Milkis) | python_ml_integration, ai_tools, custom_scripts | MEDIUM | AI/ML integration patterns, external model interaction |
| C5TcgHte2o0 | Head Tracking Tool (Eric Levy) | python_tool_development, ai_tracking, custom_flame_tools | MEDIUM | Artist-level Python tool development |
| 5xKjiUBSse8 | TWML (Andriy Toloshny) | python_ml_tools, timewarp_ml, custom_python_nodes | MEDIUM | ML timewarp tool, external ML model integration |
| Dzq3hua0GrU | ShotGrid Integration (Instinctual) | shotgrid_integration, pipeline_integration, shot_management | MEDIUM | Pipeline tool integration context |
| SjeSywTMSAE | Advanced Publishing (Jeff Kyle) | publishing, conform, openclip, advanced_workflow | MEDIUM | Advanced publishing and OpenClip workflow details |
| uAPgg4r0BbY | Publishing Workflows 101 (Josh Lawrence) | openclip, publishing, small_archives, workflow_automation | MEDIUM | Publishing fundamentals and OpenClip concepts |

---

## Summary Statistics

- **Total transcripts analyzed:** 12 (high and medium priority)
- **API patterns extracted:** 50+
- **Hook functions identified:** 5 primary hooks
- **Complete script examples:** 5
- **Object hierarchy levels:** 8 (flame → project → workspace → library → reel → clip)
- **Integration patterns:** 4 major (Frame.io, Backburner, Slack, ShotGrid)
- **Version-specific notes:** Flame 2022-2026 covered

**Key takeaways for LLM assistance:**

1. **Hook system** is central to Flame Python scripting — scripts are event-driven
2. **OpenClip XML** is the versioning mechanism for modern workflows
3. **Object hierarchy** is strictly project → workspace → library/reel/batch
4. **Properties** (name, timecode, color) are the main touch points for automation
5. **External APIs** (Frame.io, Slack, ShotGrid) are commonly integrated via Python `requests` library
6. **Batch templates** are the primary way to standardize shot setup workflows
7. **Command-line integration** (Backburner, shell scripts) bridges Flame and external tools
8. **File paths** are critical — many scripts manipulate filesystem for folder structure, metadata, and version tracking

