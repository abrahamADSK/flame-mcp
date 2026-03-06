# Flame 2026 — Segment, Timeline, Clip & Batch API

Source: Autodesk Flame 2026 Python API — official flame module reference.
Covers PySegment, PyClip, PySequence, PyBatch, PyDesktop in detail.

---

## PySegment — Timeline Segment Methods

Operators say: *"trim the shot"*, *"slip the clip"*, *"add handles"*,
*"ripple delete"*, *"close the gap"*, *"add a TL FX"*, *"create a marker"*

### All Methods

```python
# Change start frame of the segment's source
seg.change_start_frame(start_frame, use_segment_connections=True)

# Clear segment colour (reset to default)
seg.clear_colour()

# Return connected segments (segments sharing the same source)
segs = seg.connected_segments(scoping='all reels')
# scoping options: 'all reels', 'sequences reels', 'current reel', 'current sequence'

# Copy this segment's media out to the media panel
clip = seg.copy_to_media_panel(destination, duplicate_action='add')

# Create a sync connection to another segment
seg.create_connection(other_segment)

# Add a Timeline FX to this segment
# effect_type: 'Blur', 'Colour Management', 'Colour Warper', 'Sapphire BlurMoCurves', etc.
# after_effect_type: insert AFTER a specific existing effect type (optional)
fx = seg.create_effect(effect_type, after_effect_type='')

# Create a marker at a specific location on this segment
marker = seg.create_marker(location)

# Create an unlinked (offline/synthetic) segment
seg.create_unlinked_segment(source_name='', tape_name='', start_time=0,
                             source_duration=0, head=0, file_path='')

# Ensure this segment's source is not shared (detach from shared source)
seg.duplicate_source()

# Return the colour space at a given time (uses record_in if no time given)
cs = seg.get_colour_space(time=None)

# Return whether the segment is fully rendered
rendered = seg.is_rendered(render_quality='Full Resolution')

# Match segment media out to a destination (for conform / re-link)
clip = seg.match(destination, preserve_handle=False, use_sequence_info=True,
                 include_nested_content=False, include_timeline_fx=False)

# Remove a sync connection
seg.remove_connection(other_segment)

# Set gap bar display style
seg.set_gap_bars(style)

# Set gap fill colour
seg.set_gap_colour(colour)

# Set the matte channel
seg.set_matte_channel(channel_name)

# Set the RGB channel
seg.set_rgb_channel(channel_name)

# Set which version UID this segment uses
seg.set_version_uid(uid)

# Return all segments sharing the same source
shared = seg.shared_source_segments()

# Slide keyframes relative offset
seg.slide_keyframes(offset, sync=False)

# Slip the media within the same record duration
# offset: number of frames to slip (positive = slip forward in source)
success = seg.slip(offset, sync=False, keyframes_move_mode='Shift')
# Operators say: "slip it back 10 frames", "slip the clip"

# Smart replace — replace source with best match from a reel
seg.smart_replace(source_reel)
seg.smart_replace_media(source_reel)

# Sync connected segments
seg.sync_connected_segments()

# Trim the head (start) of the segment
# offset: positive = add frames (extend head), negative = remove frames
# ripple: True = prevent gaps from opening up
success = seg.trim_head(offset, ripple=False, sync=False, keyframes_move_mode='Shift')
# Operators say: "add 8 frames of head", "trim the head"

# Trim the tail (end) of the segment
success = seg.trim_tail(offset, ripple=False, sync=False, keyframes_move_mode='Shift')
# Operators say: "trim the tail", "extend the tail by 10 frames"
```

### Read-Only Properties

```python
seg.container_clip      # PyClip — the container clip (matte mode)
seg.effect_types        # list[str] — available effect types for this segment
seg.effects             # list[PyTimelineFX] — all TL FX on this segment
seg.file_path           # str — file path of the segment's source
seg.groups              # list[PySequenceGroup] — groups containing this segment
seg.head                # int — number of head frames available
seg.markers             # list[PyMarker] — markers on this segment
seg.matte_channel       # str — current matte channel name
seg.matte_channels      # list[str] — all available matte channels
seg.matte_mode          # str — current matte mode
seg.record_duration     # PyTime — duration of the segment on the timeline
seg.record_in           # PyTime — record in point (timeline position)
seg.record_out          # PyTime — record out point (timeline position)
seg.rgb_channel         # str — current RGB channel name
seg.rgb_channels        # list[str] — all available RGB channels
seg.source_audio_track  # int — source audio track number
seg.source_bit_depth    # int — clip bit depth
seg.source_cached       # bool — whether source is cached
seg.source_duration     # PyTime — duration of source
seg.source_essence_uid  # str — essence UID of the source
seg.source_frame_rate   # str — source frame rate
seg.source_has_history  # bool — source has versions
seg.source_height       # int — source height in pixels
seg.source_in           # PyTime — source in point
seg.source_name         # str — name of the source clip
seg.source_out          # PyTime — source out point
seg.source_ratio        # float — source pixel ratio
seg.source_scan_mode    # str — source scan mode
seg.source_uid          # str — source UID
seg.source_unlinked     # bool — source is offline/unlinked
seg.source_width        # int — source width in pixels
seg.type                # str — segment type: "Segment", "Gap", "Container"
```

### Read-Write Properties (set via `__setattr__`)

```python
seg.name         # str — segment label
seg.colour       # tuple(r,g,b) — colour 0.0–1.0; operators say "colour the shot red"
seg.shot_name    # str — shot name (used in batch group creation)
```

### PySegment Usage Patterns

```python
import flame

# Iterate all segments in a sequence and print info
seq = flame.timeline.clip  # PySequence from current timeline
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type == "Gap":
                print(f"  GAP: {seg.record_in}–{seg.record_out}")
            else:
                print(f"  {seg.shot_name or seg.name}: "
                      f"in={seg.record_in} out={seg.record_out} "
                      f"src_in={seg.source_in} src_out={seg.source_out}")

# Trim all VFX shots to add 8 frames of head and tail
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type != "Gap" and "VFX" in (seg.shot_name or ""):
                seg.trim_head(8, ripple=True)
                seg.trim_tail(8, ripple=True)

# Colour-code segments by type
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type == "Gap":
                continue
            if "VFX" in (seg.shot_name or ""):
                seg.colour = (0.0, 0.5, 1.0)   # blue
            elif "GFX" in (seg.shot_name or ""):
                seg.colour = (1.0, 0.5, 0.0)   # orange
            else:
                seg.colour = (0.5, 0.5, 0.5)   # grey

# Add Colour Management TL FX to all segments
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type != "Gap":
                fx = seg.create_effect("Colour Management")
                fx.bypass = False
```

---

## PyClip — Clip Methods

Operators say: *"render the clip"*, *"set in/out"*, *"open as sequence"*,
*"cache the clip"*, *"flush the renders"*, *"reformat"*

### render() — Full Signature

```python
clip.render(
    render_mode='All',                  # 'All' or 'Selected'
    render_option='Foreground',         # 'Foreground' or 'Background'
    render_quality='Full Resolution',   # 'Full Resolution' or 'Proxy Resolution'
    effect_type='',                     # filter to a specific effect type
    effect_caching_mode='Current',      # 'Current' or 'All Iterations'
    include_handles=False               # include handles in render range
)
# Returns: bool (True if render succeeded)

# Operators say: "render the clip FG", "BG render"
clip.render(render_option='Background')

# Operators say: "render proxy"
clip.render(render_quality='Proxy Resolution')

# Check if fully rendered before export
if not clip.is_rendered():
    clip.render()
```

### Other Methods

```python
# Cache media to disk
clip.cache_media(mode='current')   # mode: 'Current', 'All Versions'

# Change field dominance metadata
clip.change_dominance(scan_mode)   # scan_mode: 'P', 'F1', 'F2'

# Change source start frame
clip.change_start_frame(start_frame, use_segment_connections=True)

# Flush cached media (free storage)
clip.flush_cache_media()

# Flush rendered TL FX (unrender / invalidate)
clip.flush_renders()
# Operators say: "flush the renders", "unrender the clip"

# Return colour space of the clip at a given time
cs = clip.get_colour_space(time=None)

# Check if all TL FX are rendered
rendered = clip.is_rendered()

# Open a clip as an editable sequence
seq = clip.open_as_sequence()
# Operators say: "open as sequence", "step inside the clip"

# Reformat the clip
clip.reformat(width=1920, height=1080, ratio=1.778)

# Save the clip to its defined save destination
clip.save()
```

### Read-Only Properties

```python
clip.audio_tracks       # list[PyAudioTrack]
clip.bit_depth          # int
clip.cached             # bool
clip.duration           # PyTime
clip.frame_rate         # str
clip.height             # int
clip.markers            # list[PyMarker]
clip.ratio              # float
clip.scan_mode          # str
clip.start_frame        # int
clip.subtitles          # list
clip.width              # int
```

### Read-Write Properties

```python
clip.name               # str
clip.colour             # tuple(r,g,b)
clip.in_mark            # PyTime — in mark (player in point)
clip.out_mark           # PyTime — out mark (player out point)
```

---

## PyBatch — Batch Group Creation

Operators say: *"create a batch group"*, *"make a new batch"*,
*"set up a comp"*, *"create batch from the timeline"*

### create_batch_group()

```python
# Creates a new batch group in the Desktop catalogue
batch_group = flame.batch.create_batch_group(
    name,                    # str — name of the batch group
    nb_reels=4,              # int — number of reels (overridden by reels=[])
    nb_shelf_reels=1,        # int — number of shelf reels (first is "Batch Renders")
    reels=[],                # list[str] — explicit reel names (overrides nb_reels)
    shelf_reels=[],          # list[str] — explicit shelf reel names
    start_frame=1,           # int — start frame (frame value only, not timecode)
    duration=None            # int — duration in frames
)

# Typical post-conform usage:
# Create a batch group per shot from timeline segments
for version in seq.versions:
    if version.tracks is None:
        continue
    for track in version.tracks:
        for seg in track.segments:
            if seg.type == "Gap":
                continue
            shot = seg.shot_name or seg.name
            dur = int(str(seg.record_duration).split('+')[0])  # frames
            bg = flame.batch.create_batch_group(
                name=shot,
                reels=["CMP", "REF", "PLATES"],
                shelf_reels=["Batch Renders"],
                start_frame=1001,
                duration=dur
            )
```

### create_batch_group() on PyDesktop

```python
# Also available on the desktop object:
ws = flame.projects.current_project.current_workspace
desktop = ws.desktop
bg = desktop.create_batch_group(
    name="SHOT_0010",
    reels=["CMP", "REF"],
    start_frame=1001,
    duration=64
)
```

### Other PyBatch Methods

```python
flame.batch.go_to()                          # Switch to the Batch tab
flame.batch.close()                          # Close the current batch group
flame.batch.open(batch_group)                # Open a batch group

flame.batch.save()                           # Save current iteration
flame.batch.iterate()                        # Create new iteration (increment version)
flame.batch.iterate(5)                       # Jump to iteration 5
flame.batch.save_current_iteration()         # Save without iterating

flame.batch.load_setup(filename)             # Load a .batch setup file
flame.batch.save_setup(filename)             # Save current batch to .batch file
flame.batch.clear_setup()                    # Clear all nodes

flame.batch.create_node(type, ...)           # Create a new node
flame.batch.connect_nodes(src, socket_src, dst, socket_dst)
flame.batch.disconnect_node(node, socket)
flame.batch.organize()                       # Auto-layout nodes in schematic
flame.batch.frame_all()                      # Zoom to fit all nodes
flame.batch.frame_selected()                 # Zoom to fit selected nodes
flame.batch.get_node(name)                   # Get node by name

flame.batch.import_clip(path, reel_name)     # Import a clip into a batch reel
flame.batch.import_clips(path_list, reel_name)

flame.batch.render()                         # Render (use schedule_idle_event!)
flame.batch.open_as_batch_group()            # Open batch iteration as batch group

flame.batch.append_setup(filename)           # Append nodes from a .batch file
flame.batch.append_to_batch(batch_group)     # Append existing batch content
flame.batch.replace_setup(filename)          # Replace with .batch file

flame.batch.mimic_link(src_node, dst_node)   # Create a Mimic link
flame.batch.select_nodes(nodes)              # Select specific nodes
flame.batch.encompass_nodes(nodes)           # Group nodes in a container
flame.batch.set_viewport_layout(layout)      # Set viewport layout (1-up, 2-up, etc.)
```

### PyBatch Read-Only Properties

```python
flame.batch.name              # str — current batch group name
flame.batch.nodes             # list[PyNode] — all nodes in current batch
flame.batch.reels             # list[PyReel] — reels in current batch
flame.batch.shelf_reels       # list[PyReel] — shelf reels
flame.batch.current_iteration # int — current iteration number
flame.batch.batch_iterations  # list[PyBatchIteration] — all saved iterations
```

---

## PySequence — Methods

Operators say: *"open the sequence"*, *"create a version"*, *"add an audio track"*,
*"create a container"*, *"insert clip"*, *"overwrite clip"*

```python
# Open the sequence in the timeline
seq.open()

# Create a new version (track layer)
version = seq.create_version(name="V2")

# Create an audio track
audio_track = seq.create_audio(stereo=False)

# Create a container around selected segments or between in/out
container = seq.create_container()

# Create a subtitle track
seq.create_subtitle()

# Copy selected segments to media panel
clip = seq.copy_selection_to_media_panel(destination, duplicate_action='add')

# Extract (lift) selected segments to media panel
clip = seq.extract_selection_to_media_panel(destination)

# Lift selected segments to media panel (leaves gap)
clip = seq.lift_selection_to_media_panel(destination)

# Insert a clip at in mark
seq.insert(clip, track_index=0)

# Overwrite a clip at in mark
seq.overwrite(clip, track_index=0)

# Import subtitles
seq.import_subtitles_file(path)

# Render, cache, flush (inherited from PyClip)
seq.render()
seq.cache_media()
seq.flush_renders()
seq.flush_cache_media()
```

---

## Creating Batch Groups from Timeline — Correct Pattern

IMPORTANT: `create_batch_groups()` does NOT exist on PySequence in Flame 2026.
The correct API is `flame.batch.create_batch_group()` or `desktop.create_batch_group()`.

```python
import flame

def create_batch_groups_from_sequence(sequence, start_frame=1001):
    """
    Create one batch group per non-gap segment in a sequence.
    Operators say: 'create batch groups from the timeline'
    """
    ws = flame.projects.current_project.current_workspace
    created = []

    for version in sequence.versions:
        if version.tracks is None:
            continue
        for track in version.tracks:
            for seg in track.segments:
                if seg.type == "Gap":
                    continue

                shot_name = seg.shot_name or seg.name
                if not shot_name:
                    continue

                # Calculate duration
                # record_duration is a PyTime; convert to int frames
                try:
                    dur = int(seg.record_duration)
                except Exception:
                    dur = 100  # fallback

                bg = flame.batch.create_batch_group(
                    name=shot_name,
                    reels=["CMP", "REF"],
                    shelf_reels=["Batch Renders"],
                    start_frame=start_frame,
                    duration=dur
                )
                created.append(bg)
                print(f"Created batch group: {shot_name} ({dur} frames)")

    print(f"Total batch groups created: {len(created)}")
    return created
```

---

## PyTrack — Track Operations

Operators say: *"lock the track"*, *"hide the track"*, *"add a track"*,
*"delete the track"*, *"cut on the timeline"*

```python
# Track properties (read-write)
track.name       # str
track.locked     # bool — lock/unlock the track
track.hidden     # bool — hide/show the track

# Track properties (read-only)
track.segments   # list[PySegment] — all segments including gaps
track.type       # str — 'Video', 'Audio'

# Cut at a specific time
track.cut(cut_time, sync=False)
```

---

## PyVersion — Version (Track Layer) Operations

Operators say: *"collapse the version"*, *"hide the version"*, *"lock the version"*

```python
# Read-write properties
version.name       # str
version.locked     # bool — lock/unlock; operators say "lock the track"
version.hidden     # bool — hide/show; operators say "hide the track"
version.expanded   # bool — expand/collapse; operators say "collapse the version"
version.colour     # tuple(r,g,b)

# Read-only
version.tracks     # list[PyTrack] — None if version has no tracks
```

---

## Common Timeline Operations — Quick Reference

```python
import flame

# "What tab am I on?"
print(flame.get_current_tab())

# "Switch to timeline"
flame.set_current_tab("Timeline")

# "Switch to batch"
flame.set_current_tab("Batch")
flame.batch.go_to()

# "Get the current segment"
seg = flame.timeline.current_segment

# "Get current clip on timeline"
clip = flame.timeline.clip

# "Slip the current segment by 10 frames"
flame.timeline.current_segment.slip(10)

# "Trim the head of the current segment by 8 frames (ripple)"
flame.timeline.current_segment.trim_head(8, ripple=True)

# "Bypass all TL FX on the current segment"
for fx in flame.timeline.current_segment.effects:
    fx.bypass = True

# "Save a TL FX setup to disk"
fx = flame.timeline.current_segment.effects[0]
fx.save_setup("/jobs/SHOW/setups/grade_v01.nst")

# "Load a TL FX setup from disk"
new_fx = seg.create_effect("Colour Warper")
new_fx.load_setup("/jobs/SHOW/setups/grade_v01.nst")

# "Flush renders on all clips in a reel"
ws = flame.projects.current_project.current_workspace
for lib in ws.libraries:
    for reel in lib.reels:
        for clip in reel.clips:
            clip.flush_renders()

# "Is the clip rendered?"
print(clip.is_rendered())
```
