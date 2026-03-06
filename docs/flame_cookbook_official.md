# Flame Python API — Official Cookbook (Autodesk 2026)

Source: https://help.autodesk.com/view/FLAME/2026/ENU/
Autodesk Flame Family 2026 Help — Python API Code Samples & Examples

These are official "recipes" from Autodesk. `<PyClip>`, `<PyReel>`, etc. are
shorthand for objects created from the `flame` module.

---

## Clip Import

Import a clip into a library:
```python
flame.import_clips("/usr/tmp/clip.mov", PyLibrary)
```

---

## Clip Reformat — change resolution

Changing the resolution of a clip:
```python
<PyClip>.reformat(width=1920, height=1080, ratio=1.778)
```

---

## Rendering a Clip

Render all Timeline FX in a clip in proxy resolution using Burn:
```python
<PyClip>.render(render_mode="All", render_option="Burn", render_quality="Proxy Resolution")
```

Render all Batch FX on a clip:
```python
<PyClip>.render(effect_type="Batch FX")
```

Get the render state of a clip:
```python
print(<PyClip>.is_rendered())
```

---

## Switching Views

Switch the top view to Desktop Reels without changing the visible item:
```python
<PyDesktop>.set_desktop_reels()
```

Set a PyBatch as the visible item in the Desktop Reels view:
```python
<PyDesktop>.set_desktop_reels(<PyBatch>)
```

Switch the top view to Freeform without changing the visible item:
```python
<PyWorkspace>.set_freeform()
```

Set a PyLibrary as the visible item in the Freeform view:
```python
<PyWorkspace>.set_freeform(<PyLibrary>)
```

Go to the Timeline Tab:
```python
flame.set_current_tab("Timeline")
```

Print the tab currently selected in the software:
```python
print(flame.get_current_tab())
```

---

## Select Segments on the Timeline

Select all segments on the bottom video track of a clip:
```python
for seg in <PyVersion>.tracks[0].segments:
    seg.selected = True
```

Select all segments that are unrendered on a track:
```python
for seg in <PyVersion>.tracks[0].segments:
    if seg.is_rendered() == False:
        seg.selected = True
```

Change the comment of all selected markers on a timeline segment:
```python
for marker in <PySegment>.selected_markers:
    marker.comment = "Need MasterGrade Work"
```

---

## Working with Markers

Print the name of all markers on a clip:
```python
for marker in <PyClip>.markers:
    print(marker.name)
```

Create a marker on the 10th frame of a clip:
```python
<PyClip>.create_marker(10)
```

Change the location of a marker on a clip:
```python
marker = <PyClip>.markers[0]
marker.location = 20
```

Move a marker to the middle of a timeline segment:
```python
marker.location = <PySegment>.record_in + (<PySegment>.record_duration.frame / 2)
```

Change the name of a marker on a timeline segment to the name of that segment:
```python
tlname = <PySegment>.name
marker = <PySegment>.markers[0]
marker.name = tlname
```

Change the comment on a clip marker using tokens:
```python
marker = <PyClip>.markers[0]
marker.comment = "<user>_<date>"
```

---

## Using PyTime

Set a PyTime in timecode:
```python
tc = flame.PyTime("10:00:01:05", "23.976 fps")
```

Set a PyTime in relative frame:
```python
frm = flame.PyTime(10)
```

Set a PyTime in absolute frame:
```python
frm = flame.PyTime(864000, "23.976 fps")
```

Get the current time of a clip in frame:
```python
print(<PyClip>.current_time.frame)
```

Get the current time of a clip in relative frame:
```python
print(<PyClip>.current_time.relative_frame)
```

Get the current time of a clip in timecode:
```python
print(<PyClip>.current_time.timecode)
```

Set the current time on a clip based on timecode:
```python
<PyClip>.current_time = "10:00:00:20"
```

---

## Clip Operations — in/out marks, duration

Print a list of clips in a reel:
```python
print(<PyReel>.clips)
```

Store a clip in a variable:
```python
clip = <PyReel>.clips[0]
```

Set an in mark on a clip based on relative frame:
```python
<PyClip>.in_mark = 20
```

Set an in mark on a clip based on a PyTime timecode:
```python
tc = flame.PyTime("10:00:00:20", "23.976 fps")
<PyClip>.in_mark = tc
```

Get the in mark value in frame:
```python
print(<PyClip>.in_mark.get_value().frame)
```

Set an out mark on a clip based on relative frame:
```python
<PyClip>.out_mark = 30
```

Get the out mark value in frame:
```python
print(<PyClip>.out_mark.get_value().frame)
```

Get the duration of a clip between in and out marks in frame:
```python
print(<PyClip>.duration.frame)
```

---

## Segment Operations — timeline inspection

Get the name of a timeline segment:
```python
print(<PyTrack>.segments[0].name)
```

Get the name of all segments in a timeline (full traversal):
```python
for version in flame.timeline.clip.versions:
    for track in version.tracks:
        for segment in track.segments:
            print(segment.name)
```

Get the name of all selected segments in a timeline:
```python
for version in flame.timeline.clip.versions:
    for track in version.tracks:
        for segment in track.selected_segments.get_value():
            print(segment.name)
```

Get the name of the currently selected timeline segment:
```python
print(flame.timeline.current_segment.name)
```

Set the shot name of a timeline segment:
```python
<PySegment>.shot_name = "sh010"
```

Set the comment of a timeline segment:
```python
<PySegment>.comment = "sh010"
```

Get the source file path of a timeline segment:
```python
print(<PySegment>.file_path)
```

Get hidden / colour / source information:
```python
print(<PyTrack>.segments[0].hidden)
print(<PyTrack>.segments[0].colour)
print(<PyTrack>.segments[0].source_name)
print(<PyTrack>.segments[0].source_in)
print(<PyTrack>.segments[0].source_out)
print(<PyTrack>.segments[0].source_duration)
print(<PyTrack>.segments[0].tape_name)
print(<PyTrack>.segments[0].record_in)
print(<PyTrack>.segments[0].record_out)
print(<PyTrack>.segments[0].record_duration)
```

Hide a timeline segment:
```python
<PyTrack>.segments[0].hidden = True
```

Set the colour of a timeline segment to blue:
```python
tl_seg = <PyTrack>.segments[0]
tl_seg.colour = (0.0, 0.0, 1.0)
```

---

## Timeline FX (TLFX)

Add a Blur Timeline FX to a timeline segment:
```python
<PySegment>.create_effect("Blur")
```

Add a Blur Timeline FX after an existing Image TL FX:
```python
<PySegment>.create_effect("Blur", "Image")
```

Print the TL FX types that can be added on a segment:
```python
print(<PySegment>.effect_types)
```

Print existing PyTimelineFX of a segment:
```python
print(<PySegment>.effects)
```

Bypass a Timeline FX:
```python
<PyTimelineFX>.bypass = True
```

Get the bypass status of a Timeline FX:
```python
print(<PyTimelineFX>.bypass)
```

Print names of all TL FX on a segment:
```python
for tlfx in <PySegment>.effects:
    print(tlfx.type)
```

Bypass all Image Timeline FX in a sequence:
```python
for segment in <PyTrack>.segments:
    for effect in segment.effects:
        if effect.type == "Image":
            effect.bypass = True
```

Save a Timeline FX setup:
```python
<PySegment>.effects[0].save_setup("/usr/tmp/my_timelinefx_setup")
```

Save a specific TL FX setup by type:
```python
for tlfx in <PySegment>.effects:
    if tlfx.type == "Blur":
        tlfx.save_setup("/usr/tmp/my_timelinefx_setup")
```

Load a Timeline FX setup on a segment:
```python
<PySegment>.create_effect("Blur")
for tlfx in <PySegment>.effects:
    if tlfx.type == "Blur":
        tlfx.load_setup("/usr/tmp/my_timelinefx_setup")
```

Load a setup on all selected timeline segments:
```python
for version in flame.timeline.clip.versions:
    for track in version.tracks:
        for segment in track.selected_segments.get_value():
            openfx = segment.create_effect("OpenFX")
            openfx.load_setup("/usr/tmp/my_openfx_setup")
```

---

## Track Operations

Set a Track to be the Primary Track:
```python
seq = <PySequence>
track = seq.versions[0].tracks[0]
seq.primary_track = track
```

Get the name of the Primary Track:
```python
seq = <PySequence>
print(seq.primary_track.get_value().name)
```

Collapse a timeline video version:
```python
version = <PySequence>.versions[0]
version.expanded = False
```

Lock a track:
```python
version = <PySequence>.versions[0]
version.locked = True
```

Hide a track:
```python
version = <PySequence>.versions[0]
version.hidden = True
```

Disable stereo link on a video track:
```python
track = <PyVersion>.tracks[0]
track.stereo_linked = False
```

Print names of all segments on a track:
```python
for segment in <PyVersion>.tracks[0]:
    print(segment.name)
```

Collapse an audio track:
```python
atrack = <PySequence>.audio_tracks[0]
atrack.expanded = False
```

---

## Media Panel Operations — Batch Groups, Reels

Create a new Reel named "MyReel" inside a batch group:
```python
batch = <PyDesktop>.batch_groups[0]
batch.create_reel("MyReel")
```

Create a new Shelf Reel:
```python
batch = <PyDesktop>.batch_groups[0]
batch.create_shelf_reel("MyShelfReel")
```

Create a Batch Iteration:
```python
batch = <PyDesktop>.batch_groups[0]
batch.iterate()
```

Create Batch Iteration number 5:
```python
batch = <PyDesktop>.batch_groups[0]
batch.iterate(5)
```

Save a Batch Group from the Desktop to a Library:
```python
desk = <PyDesktop>
batch = <PyDesktop>.batch_groups[0]
lib = <PyLibrary>
desk.destination = lib
batch.save()
```

Save the current Batch Iteration to a Library:
```python
desk = <PyDesktop>
batch = <PyDesktop>.batch_groups[0]
lib = <PyLibrary>
desk.destination = lib
batch.save_current_iteration()
```

Print names of Batch Groups in a Library:
```python
for batch in <PyLibrary>.batch_groups:
    print(batch.name)
```

Print names of Batch Groups in a Folder:
```python
for batch in <PyFolder>.batch_groups:
    print(batch.name)
```

Open a Batch Group from a Folder in the Desktop:
```python
<PyFolder>.batch_groups[0].open_as_batch_group()
```

Open a Batch Iteration from a Library in the Desktop:
```python
<PyLibrary>.batch_iterations[0].open_as_batch_group()
```

Overwrite a clip in the current Sequence via shortcut:
```python
flame.execute_shortcut("Overwrite Edit")
```

Select the Desktop in the Workspace:
```python
desk = <PyWorkspace>.desktop
desk.selected = True
```

Move all clips from a Library Folder to a Desktop Reel:
```python
clips = <PyLibrary>.folders[0].clips
reel = <PyDesktop>.reel_groups[0].reels[0]
flame.media_panel.move(clips, reel)
```

Copy all clips from a Library Folder to a Desktop Reel:
```python
clips = <PyLibrary>.folders[0].clips
reel = <PyDesktop>.reel_groups[0].reels[0]
flame.media_panel.copy(clips, reel)
```

Select multiple entries at once in the Media Panel:
```python
flame.media_panel.selected_entries = <PyReel>.clips
```

Print the list of selected entries in the Media Panel:
```python
print(flame.media_panel.selected_entries)
```

Hide / show the Media Panel:
```python
flame.media_panel.visible = False
flame.media_panel.full_width = True
flame.media_panel.full_height = True
flame.media_panel.dual = True
```

---

## Using the parent Property in Hooks

Get the name of the Sequence hosting a Marker (in a Python Hook):
```python
def action_1(selection):
    import flame
    for marker in selection:
        print(marker.parent.name)
```

Put a Segment Marker in the middle of a segment (custom action hook):
```python
def action_1(selection):
    import flame
    for marker in selection:
        parent = marker.parent
        marker.location = parent.record_in + (parent.record_duration.frame / 2)
```

---

## Batch — Nodes and Connections

Create a Batch Group with specific reels:
```python
schematic_reels = ['direct_passes', 'indirect_passes', 'reflection', 'Utility_Passes']
shelf_reels = ['Extra_Data']
flame.batch.create_batch_group(
    'MyBatchGroup',
    start_frame=1001,
    duration=5,
    reels=schematic_reels,
    shelf_reels=shelf_reels
)
flame.batch.go_to()  # switch to batch tab
```

Import a clip into a batch reel:
```python
clip = flame.batch.import_clip("/var/tmp/robot_diffuse.[025-029].exr", "direct_passes")
clip.name = "Direct_Diffuse"
```

Create nodes in Batch:
```python
comp = flame.batch.create_node("Comp")
comp.name = "Diffuse"
comp.flame_blend_mode = "Add"

write_file = flame.batch.create_node("Write File")
write_file.name = "MyOutput"
```

Connect two nodes:
```python
flame.batch.connect_nodes(clip1, "BGR", comp1, "Front")
flame.batch.connect_nodes(clip2, "BGR", comp1, "Back")
flame.batch.connect_nodes(comp1, "Result", write_file, "Front")
```

Organise all nodes automatically (avoid overlap):
```python
flame.batch.organize()
```

Create a Matchbox node with a specific shader:
```python
flame.batch.create_node("Matchbox", "Blur.mx")
```

Create a Pybox node with a handler:
```python
flame.batch.create_node("Pybox", "sendmail.py")
```

Print the name of the current Matchbox shader:
```python
mx = flame.batch.get_node("Matchbox100")
print(mx.shader_name)
```

Create an OpenFX node and load a plugin:
```python
ofx = flame.batch.create_node("OpenFX")
ofx.change_plugin("S_Distort")
```

Bypass a node:
```python
mux = flame.batch.current_node.get_value()
mux.bypass = True
```

Freeze the current frame in a MUX node:
```python
frame = flame.batch.current_frame
mux = flame.batch.current_node.get_value()
mux.range_active = True
mux.range_start = frame
mux.range_end = frame
mux.before_range = "Repeat First"
mux.after_range = "Repeat Last"
```

Loop through all nodes in a Batch and check type:
```python
for node in flame.batch.nodes:
    if node.type == "Comp":
        node.flame_blend_mode = "Add"
```

Find all Action Media nodes and reposition if below y=99:
```python
for node in flame.batch.nodes:
    if node.type == "Action Media" and node.pos_y < 99:
        node.pos_y -= 100
```

---

## Action — Compass Nodes

Set Compass colour, name, size:
```python
compass = action.create_node("Compass")
compass.colour = (50, 50, 50)
compass.name = "MyCompass"
compass.width = 250
compass.height = 250
```

Create a Compass around named nodes:
```python
action.encompass_nodes(["NodeName1", node3, "NodeName2"])
```

Get a list of nodes inside a Compass:
```python
compass = action.encompass_nodes(["NodeName1", node3, "NodeName2"])
print(compass.nodes)
```

---

## Working with Users

Store the name of the current user:
```python
user = flame.users.current_user.name
```

Print the nickname of the current user:
```python
print(flame.users.current_user.nickname)
```

---

## Exception Handling in Scripts

Catch exceptions from the Flame API:
```python
from flame import batch
try:
    batch.import_clip("bad_path", "bad_reel_name")
except Exception as e:
    print(str(e))
```

---

## Render Passes — Full Multi-Pass Batch Example

Automate a multi-pass render workflow (direct/indirect/reflection/utility passes):
```python
import flame

schematic_reels = ['direct_passes', 'indirect_passes', 'reflection', 'Utility_Passes']
shelf_reels = ['Extra_Data']

flame.batch.create_batch_group(
    'Learning_RenderPasses',
    start_frame=1001,
    duration=5,
    reels=schematic_reels,
    shelf_reels=shelf_reels
)
flame.batch.go_to()

# Import media
clip1 = flame.batch.import_clip("/var/tmp/robot/direct_diffuse/robot.[025-029].exr", "direct_passes")
clip1.name = "Direct_Diffuse"
clip2 = flame.batch.import_clip("/var/tmp/robot/indirect_diffuse/robot.[025-029].exr", "indirect_passes")
clip2.name = "Indirect_Diffuse"
clip3 = flame.batch.import_clip("/var/tmp/robot/direct_specular/robot.[025-029].exr", "direct_passes")
clip3.name = "Direct_Specular"
clip4 = flame.batch.import_clip("/var/tmp/robot/indirect_specular/robot.[025-029].exr", "indirect_passes")
clip4.name = "Indirect_Specular"
clip5 = flame.batch.import_clip("/var/tmp/robot/reflection/robot.[025-029].exr", "reflection")
clip5.name = "Reflection"

# Create Comp nodes
comp1 = flame.batch.create_node("Comp"); comp1.name = "Diffuse";         comp1.flame_blend_mode = "Add"
comp2 = flame.batch.create_node("Comp"); comp2.name = "Direct_Specular"; comp2.flame_blend_mode = "Add"
comp3 = flame.batch.create_node("Comp"); comp3.name = "Indirect_Specular"; comp3.flame_blend_mode = "Add"
comp4 = flame.batch.create_node("Comp"); comp4.name = "Reflection";      comp4.flame_blend_mode = "Screen"
write = flame.batch.create_node("Write File"); write.name = "MyComp"

# Connect the tree
flame.batch.connect_nodes(clip1, "BGR", comp1, "Front")
flame.batch.connect_nodes(clip2, "BGR", comp1, "Back")
flame.batch.connect_nodes(comp1, "Result", comp2, "Back")
flame.batch.connect_nodes(clip3, "BGR", comp2, "Front")
flame.batch.connect_nodes(comp2, "Result", comp3, "Back")
flame.batch.connect_nodes(clip4, "BGR", comp3, "Front")
flame.batch.connect_nodes(comp3, "Result", comp4, "Back")
flame.batch.connect_nodes(clip5, "BGR", comp4, "Front")
flame.batch.connect_nodes(comp4, "Result", write, "Front")

flame.batch.organize()
```
