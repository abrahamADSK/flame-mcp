# flame-mcp OpenClip Patterns

> Patterns from husky.py (Autodesk 2015, JF Bouchard & M. Sansregret)
> and the OpenClip XML specification as used in Flame watch-folder workflows.
> Source: `docs/code_samples/autodesk_zips/python_script01/husky.py`

---

## OpenClip Watch Folder — Core Architecture

A watch-folder script for Flame works outside Flame (runs in a terminal or
as a daemon). It monitors a directory for new version subdirectories and
creates/updates `.clip` OpenClip XML files automatically.

```
Watch Folder Structure:
  /projects/vfx_shot1/
    v001/              ← version subfolders (auto-detected)
      frame.0001.dpx
      frame.0002.dpx
    v002/
      frame.0001.dpx
    vfx_shot1.clip     ← OpenClip XML (created + updated by script)
```

The script flow:
1. Ask the user for the folder path to watch
2. Poll the folder every N seconds (`os.walk()` diff)
3. When a new subdirectory appears, wait for it to stop growing (`get_size()` diff)
4. Call `dl_get_media_info` to generate initial `.clip` XML, or splice a new version into the existing `.clip`
5. Notify the OS (Linux: `notify-send`, macOS: `pync.Notifier`)

---

## dl_get_media_info — Create Initial OpenClip XML

The Flame CLI tool `dl_get_media_info` scans a media directory and outputs
OpenClip-compatible XML. This is the standard way to create a `.clip` file
from a folder of image sequences.

```python
import os
import xml.dom.minidom as minidom

def create_initial_clip(media_dir, clip_file_path):
    """Create a new .clip OpenClip file from a media directory."""
    get_media_script = "/usr/discreet/mio/current/dl_get_media_info"

    if not os.path.isfile(get_media_script):
        raise RuntimeError(f"dl_get_media_info not found: {get_media_script}")

    # Run dl_get_media_info recursively on the version folder
    result = os.popen4(f"{get_media_script} -r {os.path.abspath(media_dir)}")
    xml_lines = result[1].readlines()

    with open(clip_file_path, "w") as f:
        f.writelines(xml_lines)
```

Notes:
- `dl_get_media_info` is part of the Autodesk Flame/Lustre MIO toolkit.
- Path: `/usr/discreet/mio/current/dl_get_media_info`
- `-r` flag: scan recursively.
- Output is OpenClip XML that Flame can import directly via MediaHub or drag-drop.
- The `.clip` file must be in the same directory tree as the media it references.

---

## OpenClip XML — Splice New Version into Existing Clip

When a new version folder appears, parse the existing `.clip` XML and add
a new `<feed>` element to the existing `<track>`. This is the core of
multi-version OpenClip management.

```python
import xml.dom.minidom as minidom
import os, re, shutil, time

def splice_new_version(master_clip_path, new_version_dir, version_label):
    """
    Add a new version to an existing .clip OpenClip XML file.

    master_clip_path: path to the existing .clip file
    new_version_dir:  path to the new version folder (e.g. /shot/v002/)
    version_label:    relative path label shown in Flame (e.g. "v002/shot_001")
    """
    get_media_script = "/usr/discreet/mio/current/dl_get_media_info"
    tmp_path = "/tmp/openclip_tmp.clip"

    # Generate XML for the new version into a temp file
    result = os.popen4(f"{get_media_script} -r {os.path.abspath(new_version_dir)}")
    with open(tmp_path, "w") as f:
        f.writelines(result[1].readlines())

    # Parse both files
    master_xml = minidom.parse(master_clip_path)
    new_xml    = minidom.parse(tmp_path)

    # For each track in the new version, add its feed to the master
    new_version_id = ""
    for track in new_xml.getElementsByTagName("track"):
        track_uid = track.attributes["uid"].value
        feed = track.getElementsByTagName("feed")[0]

        # Find matching track in master by uid
        for master_track in master_xml.getElementsByTagName("track"):
            if master_track.attributes["uid"].value == track_uid:
                # Auto-increment version uid (v001 → v002, 001 → 002, etc.)
                existing_feeds = master_track.getElementsByTagName("feed")
                last_uid = existing_feeds[-1].attributes["uid"].value if existing_feeds else "v000"
                match = re.search(r"(\d+)$", last_uid)
                if match:
                    new_version_id = f"{int(match.group(1)) + 1:03d}"
                else:
                    new_version_id = "001"

                feed.attributes["vuid"].value = new_version_id
                feed.attributes["uid"].value  = new_version_id
                master_track.getElementsByTagName("feeds")[0].appendChild(feed)

    # Add a <version> metadata entry
    doc = minidom.Document()
    versions_node = master_xml.getElementsByTagName("versions")[0]
    version_elem = versions_node.appendChild(doc.createElement("version"))
    version_elem.setAttribute("type", "version")
    version_elem.setAttribute("uid", new_version_id)

    name_elem = doc.createElement("name")
    name_elem.appendChild(doc.createTextNode(version_label))
    version_elem.appendChild(name_elem)

    date_elem = doc.createElement("creationDate")
    date_elem.appendChild(doc.createTextNode(time.strftime("%c")))
    version_elem.appendChild(date_elem)

    # Backup original, write updated XML
    backup_path = master_clip_path + ".bak"
    shutil.copy2(master_clip_path, backup_path)

    with open(master_clip_path, "w") as f:
        f.write(master_xml.toxml())
```

Notes:
- OpenClip XML uses `<track>` → `<feeds>` → `<feed>` hierarchy per channel/track.
- Each `<feed>` has a `uid` and `vuid` attribute identifying the version.
- Version UIDs are typically zero-padded integers: `"001"`, `"002"`, etc.
- `<versions>` → `<version>` entries are the labels shown in the Flame UI timeline.
- Always backup the original `.clip` before writing (data safety).

---

## Watch Folder — Directory Polling with Size Stability Check

```python
import os, time

POLL_INTERVAL = 2  # seconds between scans

def watch_for_new_directory(watch_folder, clip_file_path):
    """
    Block until a new subdirectory appears in watch_folder,
    then wait for it to stop growing before processing.
    """
    known_dirs = set(d for d, _, _ in os.walk(watch_folder))

    while True:
        print(f"Watching {watch_folder} — polling every {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)

        current_dirs = set(d for d, _, _ in os.walk(watch_folder))
        new_dirs = current_dirs - known_dirs

        if new_dirs:
            new_dir = new_dirs.pop()
            print(f"New directory detected: {new_dir}")
            wait_for_stable_size(new_dir)
            # Now process: create or update the OpenClip
            rel_path = os.path.relpath(new_dir, watch_folder)
            create_initial_clip(new_dir, clip_file_path)  # or splice_new_version()
            notify_os(clip_file_path)
            # Reset and continue watching
            known_dirs = current_dirs
        else:
            known_dirs = current_dirs

def wait_for_stable_size(directory, interval=2):
    """Wait until the directory stops growing (render/copy is complete)."""
    def get_dir_size(path):
        total = 0
        for dirpath, _, files in os.walk(path):
            for f in files:
                total += os.path.getsize(os.path.join(dirpath, f))
        return total

    size1 = get_dir_size(directory)
    while True:
        time.sleep(interval)
        size2 = get_dir_size(directory)
        if size2 > 0 and size2 == size1:
            break
        size1 = size2
        print(f"Still writing... size={size2}")
```

---

## OS Notification After Clip Update

```python
import os

def notify_os(clip_label):
    """Send a desktop notification when the OpenClip is updated."""
    if os.uname()[0] == "Linux":
        os.environ["DISPLAY"] = "0:0"
        os.system(f"xhost + > /dev/null")
        os.system(f"notify-send '{clip_label} updated' 2>/dev/null")
    elif os.uname()[0] == "Darwin":
        # macOS: requires `pip install pync`
        from pync import Notifier
        Notifier.notify("updated", title=clip_label)
```

---

## OpenClip Integration with Flame — Import and Version Switch

Once a `.clip` file is created or updated, Flame detects the new version
automatically if the clip is already loaded in the timeline.

```python
import flame

def import_openclip_to_reel(clip_path, library_name="Default Library", reel_name="Incoming"):
    """Import a .clip OpenClip file into a Flame reel."""
    ws = flame.projects.current_project.current_workspace
    lib = next((l for l in ws.libraries if l.name == library_name), None)
    if lib is None:
        raise ValueError(f"Library not found: {library_name}")
    reel = next((r for r in lib.reels if r.name == reel_name), None)
    if reel is None:
        raise ValueError(f"Reel not found: {reel_name}")
    flame.import_clips(clip_path, reel)

# To switch to the latest version of a clip already in the timeline:
# (done via context menu in Flame UI — no Python API for version switch)
```

Notes:
- `.clip` files import into Flame like any other media via `flame.import_clips()`.
- Once imported, Flame tracks new versions added to the `.clip` file automatically.
- The user selects a segment in the timeline → right-click → "Update to latest version".
- There is no Python API to programmatically switch clip versions in the timeline.
