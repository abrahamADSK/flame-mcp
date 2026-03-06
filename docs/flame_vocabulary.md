# Flame Editorial Vocabulary → Python API Mapping

This document bridges the gap between how Flame operators, editors, and
artists describe operations in natural language (from forums, tutorials,
manuals) and the corresponding Python API calls.

The RAG system uses this to connect user intent queries to the right code.

---

## Timeline / Sequence Operations

| Editorial term | What it means | Python API approach |
|---|---|---|
| close gap | remove a gap between clips, shift following clips left | rebuild sequence skipping gap segments |
| ripple delete | delete clip and close gap | rebuild sequence without that segment |
| lift | remove clip leaving gap (no ripple) | not supported directly |
| overwrite | place clip at position, replace what's there | `seq.overwrite(clip, PyTime(frame))` |
| insert | push following clips right, insert clip | not supported directly |
| slip | change in/out of clip without moving position | not supported directly |
| slide | move clip position keeping in/out | not supported directly |
| trim | adjust edit point between two clips | not supported directly |
| extend / shorten | change clip duration at edit point | not supported directly |
| record in / record out | position in the timeline (sequence time) | `seg.record_in`, `seg.record_out` (PyTime) |
| source in / source out | position in the original clip (source time) | `seg.source_in`, `seg.source_out` (PyTime) |
| duration | length of a clip or sequence in frames | `seg.record_duration.frame`, `seq.duration.frame` |
| gap / filler | empty space between clips in timeline | `seg.type == "Gap"` |
| segment | a clip placed on a timeline track | `PySegment` object in `track.segments` |
| track | video or audio lane in a sequence | `PyTrack` in `ver.tracks` |
| version | one edit version of a sequence | `PyVersion` in `seq.versions` |

### Close Gap — working pattern

```python
# "close gap", "ripple delete", "remove gap", "fill gap"
# Rebuild sequence omitting gap segments
import flame
from flame import PyTime

ws   = flame.projects.current_project.current_workspace
desk = ws.desktop
reel = next((r for rg in desk.reel_groups for r in rg.reels
             if str(r.name) == "Sequences"), None)
seq  = reel.sequences[0]

non_gap = []
for ver in seq.versions:
    if ver.tracks is None: continue
    for track in ver.tracks:
        for seg in track.segments:
            if seg.type != "Gap":
                non_gap.append(seg)
    break

new_seq = reel.create_sequence(str(seq.name) + "_NOGAP")
cursor  = PyTime(0)
for seg in non_gap:
    if seg.clip is not None:
        new_seq.overwrite(seg.clip, cursor)
        cursor = PyTime(cursor.frame + seg.record_duration.frame)
print(f"Done: {len(non_gap)} segs, {cursor.frame} frames")
```

---

## Media / Clip Operations

| Editorial term | What it means | Python API |
|---|---|---|
| bin / library | container for clips and sequences | `PyLibrary` via `ws.libraries` |
| reel | container within a library or desktop | `PyReel` via `lib.reels` or `rg.reels` |
| reel group | group of reels on the desktop | `PyReelGroup` via `desk.reel_groups` |
| desktop | main workspace area with reel groups | `ws.desktop` → `PyDesktop` |
| media panel | the panel showing library content | `flame.media_panel` |
| source clip / master clip | original media clip | `PyClip` |
| sequence / timeline | an edited sequence of clips | `PySequence` |
| batch group | a node-based compositing group | `PyBatch` |
| import media | bring files into Flame | `flame.import_clips(paths, reel)` |
| export / render | write frames to disk | `flame.export(clip, preset, path)` |
| move clip to reel | relocate a clip | `flame.media_panel.move(clip, target_reel)` |
| duplicate | make a copy | `flame.duplicate(obj)` |
| delete clip / remove clip | remove from container | `flame.delete(clip)` |
| wipe / clear reel | empty a reel of all clips | iterate clips → `flame.delete(each)` |

---

## Project / Workspace Operations

| Editorial term | What it means | Python API |
|---|---|---|
| project | a Flame project | `flame.projects.current_project` |
| workspace | the user's workspace | `flame.projects.current_project.current_workspace` |
| stone / wire | network shared storage (IFFFS) | not scriptable — use local paths |
| conform | match EDL/XML to media | no public Python API |
| archive | save project to archive | no public Python API |
| colour management | ACES, LUT, colour space | `PyClip.colour_space`, limited API |
| frame rate / fps | project frame rate | `flame.projects.current_project.frame_rate` |
| resolution | project pixel dimensions | `flame.projects.current_project.width/height` |

---

## Batch / Compositing Operations

| Editorial term | What it means | Python API |
|---|---|---|
| batch | node-based compositing workspace | `flame.batch` (current open batch) |
| render batch | execute a batch render | `flame.schedule_idle_event(lambda: flame.batch.render(...))` |
| batch group | a saved batch setup on desktop | `PyBatch` via `desk.batch_groups` |
| create batch group | make a new batch from clips | `flame.batch.create_batch_group(name, reels=[...], clips=[...])` |
| node | a processing element in batch | PyNode objects (limited public API) |

---

## Error messages and what they mean

| Error | Cause | Fix |
|---|---|---|
| `unordered_map::at: key not found` | C++ Flame internal crash — object no longer valid | restart Flame |
| `'NoneType' object has no attribute X` | Flame returned None for a property | check if property exists before use |
| `PyAttribute` in str() output | .name is a PyAttribute, not str | wrap with `str()` |
| `StopIteration` | `next()` without default, no match found | use `next(gen, None)` |
| `Clip is locked` | clip has a lock (version/permission) | unlock via UI or skip |
| `The destination is invalid` | target reel/library doesn't accept this type | check container type |
| `Failed to have the number of children for ':IFFFS:'` | Stone/Wire network storage unreachable | use local filesystem paths |

---

## Synonyms used in forums and tutorials

These are common ways Flame users describe things. All map to the patterns above.

- "nuke the desktop" → delete all reels except one (keep ≥1 per reel group)
- "strip the sequence" → iterate and delete clips in a reel
- "bounce to tape / export" → `flame.export()`
- "cut" in timeline → segment boundary (rec_in/rec_out of adjacent segments)
- "handles" → extra frames before/after a cut point
- "LUT" → colour transform applied to clip
- "EDL" → Edit Decision List — no direct Python import, use Flame UI
- "XML" → timeline exchange format — no direct Python import, use Flame UI
- "AAF" → Advanced Authoring Format — no direct Python import, use Flame UI
- "render farm / background reactor" → `flame.batch.render(render_option='Background Reactor')`
- "SAN" → Storage Area Network, same as Stone/Wire
- "versioning" → `seq.versions` list
