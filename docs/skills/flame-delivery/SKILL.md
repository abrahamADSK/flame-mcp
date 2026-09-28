---
name: flame-delivery
description: Take a shot or sequence out of Flame as delivered media — render, wait for the real frame count, export a master, create the review Version, regenerate the open clip. Fire on any render/export/deliver/master/review request: export deadlocks, a start frame that moves with the current version, presets that apply no colour. E.g. "renderiza y entrega", "saca el master", "exporta el mov de review", "por qué la versión no se actualiza", "deliver the comp".
---

# Delivering media out of Flame

Covers the path from a finished graph or timeline to media someone else can use:
render, export, versioning, review. Applies to **any** delivery, not one pipeline.

For *which* class or method to call, use `search_flame_docs`. For anything touching
`flame.batch` — including the idle-event contract and the render-wait rule — see
**`flame-batch-authoring`**; it is not repeated here.

The failures below are silent. Every one of them produces a file that exists, opens,
and is wrong.

---

## Flame truth — applies at any facility

### 1. Export blocks the main thread, and "scheduled" is not "done"

`PyExporter().export()` freezes Flame even with `foreground = False`. It must run
inside `flame.schedule_idle_event` (same shape as the batch skill's probe).

Once the call confirms **"Export scheduled"** or prints an output path, **stop**.
The export runs asynchronously after your call returns. A second call to check on
it deadlocks Flame. Do not poll Flame; poll the filesystem.

### 2. In Background, the "finished" signal fires when the job is SENT

Flame raises `batchExportEnd` at **submission**, not completion. Anything chained to
that event runs against frames that do not exist yet.

Measured in-vivo: job sent 16:27:21 → hook reported "does not exist" 16:27:25 →
the renderer actually finished 16:28:08 → the transcode died at 16:28:13 with
"cannot be imported to be transcoded".

**The trap is that it half-succeeds.** Stills and metadata land; only the movie is
lost. Nothing errors loudly.

Consequences:
- For a delivery whose downstream steps depend on real frames, render in
  **Foreground**, even where house convention says otherwise.
- In Foreground `flame.batch.render()` blocks, so an outcome file appears when the
  render **ends** — that reappearance is your signal.
- Background submission also raises modal dialogs that no automated caller can
  answer. Never queue main-thread work while a modal is open.

### 3. A clip's start frame is read from its CURRENT version

The same open clip reports `start_frame` **1001** with one version current and **0**
with another. Nothing about the file changed.

At 0, every *Update Sources* replace re-anchors the segment at `00:00:00:00` and its
cut is lost. Whenever a version is added to a clip already laid on a timeline,
preserve which version is current.

### 4. Open clips: silent rejection, and the feedback loop

- Flame **silently refuses** open clip XML that is not canonical — no error, no clip.
  Generate the XML with `dl_get_media_info` rather than by hand.
- An open clip **aggregates** every version published to it. A graph that reads the
  aggregate as its source will, the moment its own output becomes the current
  version, read **its own render** as input. Symptom: output visually identical to
  the previous pass, then Flame spinning forever on `Resize : Cannot access frame`.
  **Point graphs at a specific published render, never at the aggregate they feed.**
- A clip can only be renamed while it sits **in a reel** — rename before it enters
  any timeline.

### 5. Export presets apply no colour management

Neither `PyExporter` nor the presets shipped with Flame — the stock review preset
included — apply any colour transform. The export copies values through.

So a deliverable can be correct in codec, resolution, frame count and duration and
still be **scene-linear crushed into a display-referred container**. Highlights
flatten; the file looks plausible in a thumbnail.

Colour is not verifiable from metadata. Extract a frame and measure it. If a
delivery must carry a transform, it needs a preset built with
`ColorTransformBuilder` — guessing colour-space names to reconstruct one does not
work.

### 6. Write File settings are in-memory until the batch is saved

Attribute changes to a Write File node live in memory only. A Flame restart reverts
them **silently** — the node reads back the way it was. Save the batch as part of
configuring it, not afterwards.

### 7. A damaged timeline anchor cannot be repaired afterwards

Each segment's `source_in` must equal the source's first frame expressed as
timecode (frame 1001 at 25 fps = `00:00:40:01`).

*Update Sources* **cannot** fix a wrong anchor — verified across all three
`version_selection_mode` values. The only repair is re-laying the segment:
`PySequence.overwrite(clip, PyTime(record_in.frame + 1))`. Record positions are
one-based on input while `record_in` reads back **zero-based**; mixing them costs
exactly one frame.

Verify anchors and report the verdict in the same breath as the delivery.

### 8. Never build structure you might have to remove

Structural deletes from a console deadlock Flame 2027 — a library or reel created in
error has to be removed by hand in the UI. Gate creation on the media actually
existing on disk first, so a failure never leaves empty structure behind.

Related: a library-stored sequence is **read-only** for timeline edits; it must be
on the desktop before its first edit.

---

## With the tk-flame Toolkit engine

True wherever the Toolkit engine is installed — not specific to one facility.

- The engine does the publishing and creates the review Version itself. Do not
  hand-roll publishes or quicktimes alongside it; configure the Write File so its
  output matches the Toolkit templates and let the hook fire.
- Context is resolved **from the `.batch` file path**. If the batch template carries
  no `{Step}` token, Toolkit resolves a Shot and stops — the Version and publishes
  arrive with **no Task**. An unlinked publish is invisible to every Task-based
  query. Link it explicitly as part of the delivery.
- Review-movie generation depends on a configured quicktime template. If the movie
  path comes back empty, the template is missing from the config. Say so — never
  invent a path to a movie that was written to a temp dir and deleted.

---

## This facility only — do not generalise

Local configuration. A reader at another site should ignore all of it.

- The only colour-correct master preset here exists as a **single file saved in this
  framestore**. It is not in the repo and not reconstructible. Stock presets,
  including the one the review app uses, deliver flat (measured on our footage:
  ~48–50 against ~107 with the correct preset).
- Toolkit template and step names in use here: light `LGT`, comp `CMP`; conformed
  clips at `<root>/sequences/<Sequence>/<Shot>/finishing/clip/<Shot>.clip`.
- `prepare_comp_render` configures the Write File to match those templates and emits
  an `ALIGNMENT:` line carrying both ranges — relay it verbatim, render only on
  `-> OK`.
- `openclip_create` takes `steps=[...]` (list form — the singular drops the step
  prefix from the version uid), `extra_publish_types` when the publish type is not
  `Rendered Image`, and `keep_source_current=True` to preserve §3.
- Our server cannot import an EDL into Flame. `cut_to_edl` writes one as a separate
  deliverable, on explicit request.

---

## What this skill is not

- **Not batch graph authoring.** Node creation, wiring, the idle-event contract and
  the render-wait rule live in `flame-batch-authoring`.
- **Not the site's comp recipe.** For this facility's relit-shot cascade and its
  full delivery chain: `resolve_concept('expand multilayer')`.
- **Not an API reference.** Class and method lookup is `search_flame_docs`.
- **Not archiving.** Archive and restore have no validated procedure here yet.
