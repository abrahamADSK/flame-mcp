# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.21.0] — 2026-08-16

### Fixed
- **`fix_comp_writefile` signed off a 2-frame render as aligned** (Chat 101,
  measured on SEQ003_SH002). Two defects in the same read-back block:
  the range correction was gated on `_rs != _sf`, so a Write File whose
  `range_start` already matched the batch start skipped it entirely and
  `range_end` was never touched; and the `ALIGNMENT:` verdict compared only
  the START (`_bs == _sf and _rs == _sf`), never the end. The node sat at
  `<Range Start="1001" End="1002" Span="100"/>`, the op printed `-> OK`, the
  recipe rendered on that verdict, and the shot delivered **2 frames of 100**.
  The range is now pulled whenever EITHER end disagrees, the verdict checks
  both ends and NAMES the mismatch, and both frame counts appear on the line.
- **`render_batch` claimed it did not wait — in Foreground it does.**
  `flame.batch.render()` BLOCKS the main thread in Foreground, so the outcome
  file is written when the render ENDS; the tool nonetheless returned "this
  call does not wait for completion" and wrote `OK: render started` either
  way. The agent concluded it had no completion signal and handed the wheel
  back to the operator, abandoning the rest of the delivery cycle on every
  run. Foreground now reports the blocking semantics, writes
  `OK: render finished`, and instructs the caller to poll disk itself. The
  result file is also DELETED before scheduling, so its reappearance — not
  its mere existence — is the signal (a stale file was byte-identical to a
  fresh one).

### Changed
- **Comp delivery recipe (`resolve_concept` → STEP 8)**: 8a now requires the
  `ALIGNMENT:` line to be relayed VERBATIM with both frame counts (it was
  summarised as "aligned, 100 frames" while the node was set to 1001-1002);
  8b gains the concrete WAIT mechanism — poll the version folder on disk for
  the expected frame count, stable across two reads, plus the outcome file —
  and forbids handing the wheel back to the operator, which is what left
  steps (e) and (f) unrun in Chats 100 and 101.
- **Recipe step 8e** now passes `steps=['LGT']` (the Step **short_name**), not
  `['Light']`: the selector matches either, but the string passed becomes the
  uid prefix uppercased, so `'Light'` silently relabels the light layer
  `LIGHT_v003` where the conformed clip carries `LGT_v003`. The rationale for
  `extra_publish_types` is corrected too — it is required because of the
  publish TYPE (`Flame Render` vs the selector's `Rendered Image`), NOT
  because the native publish lacks a Task, which Chat 100 measured to be
  false.

### Tests
- The alignment verdict is now EXECUTED against a stubbed `flame` module
  rather than string-matched against the template, and the three new cases
  were confirmed to FAIL against the pre-fix code. String-matching the
  generated template is what let this defect ship.

### Validated in-vivo
Both fixes were exercised end to end on SEQ003_SH002 (Flame 2027.0.1) after
the code landed:
- `fix_comp_writefile` printed `write file range pulled to 1001-1100` — the
  correction the old guard skipped — and the verdict read
  `write file range 1001-1100 (100 frames) | source 1001-1100 (100 frames)
  -> OK`. The render produced 100/100 EXR, zero zero-byte.
- The console ran the whole delivery cycle (8a→8g) without once asking the
  operator whether the render had finished, and closed with all six
  conformed segments reading `source_in 00:00:40:01` — the anchor survived,
  including the light layer's uid changing from a bare `v003` to `LGT_v003`
  when the clip was regenerated with `steps=['LGT']`.
- `sg_uploaded_movie` was populated by the recipe, not by hand — the open
  question from Chat 100.

## [1.20.1] — 2026-08-16
- **The comp delivery must render in FOREGROUND** (Chat 99, measured
  in-vivo — and it overrides the engine's usual "always use Background
  Reactor" rule): Flame fires `batchExportEnd` when a background job is
  **SENT**, not when it finishes, so tk-flame's native publish chain runs
  against frames that do not exist yet. Timeline of the failure: job sent at
  16:27:21, the hook warned "does not exist" at 16:27:25, the Reactor
  finished frame 1100 at 16:28:08, and the quicktime transcode died at
  16:28:13 with *"cannot be imported to be transcoded"*. The `.batch` and
  render publishes and the Version all still land — **only the movie is
  lost** — which makes the failure easy to miss entirely. Every earlier
  validation passed only because the render option was passed explicitly as
  Foreground; the console followed rule 13 and broke. Recipe step 8b and
  `CLAUDE.md` rule 13 now both carry the exception.


## [1.20.0] — 2026-08-16
- **A brand-new shot is born native** (Chat 99, operator question: "would
  this setup be correct for a fresh conform, the first of the series?" — it
  would not have been). `setup_comp_batch` still built the OLD shape, so a
  new shot would have satisfied none of tk-flame's three gates and published
  nothing until someone ran a repair op over it. Both ops now emit the SAME
  contract, byte for byte: node named after the bare STEP (the Toolkit
  template builds the media folder from it — a node called `<Shot>_CMP`
  would produce `SEQ003_SH001_CMP_v001/` where `CMP_v001/` is expected),
  `shot_name` populated so the filename gets the shot through `<shot name>`,
  the setup redirected to `../batch/<shot name>.v<version>`, and
  `create_clip` ON pointing at the node's own clip. Writing the tests
  surfaced that `fix_comp_writefile` would have RENAMED the node back and
  silently undone the template match — setup and fix must agree or repairing
  a batch breaks it.
- **The conform builds clips the way the cycle regenerates them**: it used
  the singular `step=` (uid `v003`) while the comp delivery regenerates with
  `steps=` (uid `LIGHT_v003`), so the version uid CHANGED under an
  already-conformed segment on the first delivery. The recipe now mandates
  the list form from the start.
- **The rendered clip is renamed after the open clip is regenerated**
  (Chat 99, operator request): 'Add to Workspace' drops the render into the
  batch's *Batch Renders* shelf reel named after the NODE, and the Toolkit
  template forces that node to be the bare step (`CMP`) because
  `{segment_name}` is what builds the media folder — so on screen it reads
  as an anonymous `CMP`. Step 8f renames the CLIP to
  `<Shot>_<step>_v<version>` and says explicitly not to touch the node name,
  which is the very thing the native hook's template match depends on.
- **Both delivery gaps closed** (Chat 99, operator: "no admito huecos"). The
  review movie is now native: with `batch_quicktime_template` configured
  (`flame_shot_comp_mov`, added to the pipeline config) tk-flame writes a
  PERMANENT quicktime beside the light one
  (`{Shot}/CMP/review/{Shot}_CMP_v001.mov`, mirroring
  `{Shot}/LGT/review/…`), publishes it as *Flame Quicktime* and its
  backburner hook fills `sg_path_to_movie` itself — no `sg_update`
  workaround. Previously the quicktime was generated in a temp dir, uploaded
  and deleted, leaving the field empty. The Task link is the one thing the
  native path genuinely cannot do — the context is resolved from the `.batch`
  path and `flame_shot_batch` carries no `{Step}` token — so step 8d is now
  a MANDATORY step (`sg_find` the Task by Step short_name, `sg_update` the
  Version and both PublishedFiles) with "do not report DONE without it": an
  unlinked publish is invisible to every Task-based query in production.

- **The comp delivery is handed to Flame's own tk-flame integration** (Chat
  99, validated in-vivo end to end). Our hand-rolled publish and review steps
  are DELETED: once the Write File's output matches the Toolkit templates,
  Flame's `pre_batch_render_checks` / `post_batch_render_sg_process` hooks
  publish the `.batch` (**Flame Batch File**) and the render (**Flame
  Render**), create the Version with `sg_path_to_frames` and the frame range,
  generate the quicktime and upload it — after the operator accepts Flame's
  own *Send to Review* dialog, which is deliberately part of the on-camera
  flow. Getting there took three gates: the render path had to match
  `flame_shot_comp_exr` (the node is named after the Step so `{segment_name}`
  resolves, with `<shot name>` supplying the shot), the setup path had to
  match `flame_shot_batch` (`include_setup_path` redirected to
  `../batch/<shot name>.v<version>`), and `create_clip` had to be ON —
  without it Flame 2027 omits `versionNumber` from the hook payload and
  tk-flame dies with `KeyError`. `create_clip_path` points at the node's OWN
  clip, never at the conformed one (Chat 98).
- **Step 8 now ends with a mandatory ANCHOR VERIFICATION** and states how to
  repair: every segment's `source_in` must equal the source's first frame as
  timecode, the failure is silent, and *Update Sources* cannot undo it — a
  damaged segment is re-laid with `PySequence.overwrite(clip,
  PyTime(record_in.frame + 1))`. The version **flip stays MANUAL** by
  operator requirement: showing both versions available and choosing one on
  camera is the point of the demo.
- **Known gaps are written down rather than papered over**: the native
  Version and both publishes carry no Task (the batch template has no `Step`
  token), and `sg_path_to_movie` stays empty because the quicktime is
  generated in a temp dir, uploaded and deleted — a persistent movie needs
  `batch_quicktime_template` in the pipeline config, which is empty today.
- **The release-tag invariant only counts release tags**: `git describe
  --tags` picked up a snapshot marker and blocked every commit with a
  nonsense version. Now `--match 'v[0-9]*'` (same one-line fix applied to
  fpt-mcp and maya-mcp).

- **The comp batch reads the LIGHT render, never the conformed clip** (Chat
  99, in-vivo — the cause behind two earlier symptoms): `setup_comp_batch`
  imported the multi-version `.clip` as the batch's source, which is a
  FEEDBACK LOOP. The clip aggregates Light+Comp, so the moment a COMP
  version became current the source node resolved to the comp's OWN output:
  the comp composited over itself and rendered visually identical to the
  light pass (reported by the operator and unexplained at the time). Then,
  after the comp media was rolled back, Flame span forever on
  `Resize : Cannot access frame 35 … _CMP_v001.1035.exr`, saturating the
  main thread until the bridge stopped answering. Nothing has needed the
  aggregate as input since the Write File stopped creating clips (Chat 98):
  the clip AGGREGATES for the timeline flip, the batch READS the light
  render — different files, different jobs. `_derive_source_media` pulls the
  light publish's `[first-last]` pattern out of the clip (skipping COMP
  feeds) and the op imports that; an underivable source still falls back to
  the clip but says so loudly. `fix_comp_writefile` gains a `SOURCE LOOP`
  guard that flags batches created before this rule. +7 tests.

- **The "restart Flame" warning now fires on a bridge detection, never on
  text** (Chat 99, in-vivo false alarm mid-render): the console told the
  operator that Flame had thrown an internal C++ exception and the
  interface might be corrupted — while the render was completing normally
  (100 frames, correct embedded timecode) and neither the app log nor the
  shell log carried any exception. The warning was inferred from tool TEXT:
  it fired when a result contained (`possibly_corrupted` OR
  `unordered_map::at`) AND `ERROR:`, and a single `search_flame_docs`
  response concatenates several chunks — `docs/flame_vocabulary.md` carries
  an "Error messages" table listing `unordered_map::at` while other chunks
  carry `print('ERROR: ...')` samples. Chat 98 had already narrowed this
  heuristic once and it still misfired, because free-text scanning is the
  wrong mechanism, not the wrong threshold. `_fmt` now prefixes a sentinel
  (`CPP_CORRUPTION_SENTINEL`) when — and only when — the bridge set
  `flame_state='possibly_corrupted'`, and the console matches that literal
  and nothing else. Documentation is free to DESCRIBE the crash again. A
  concept-registry entry pins the literal byte-identical in both files and
  forbids the old substring scan from coming back. +8 tests.

- **The comp cycle now creates the review Version in Flow Production
  Tracking** (Chat 99, operator request): the delivery published an EXR
  sequence and stopped, so the comp never appeared as reviewable media —
  while the Light pipeline has been creating Versions with frames path,
  movie path and uploaded streaming media all along. Step 8 of the comp
  recipe gains a REVIEW VERSION phase that mirrors that convention exactly:
  resolve the movie path from the `movie_shot_publish` template
  (`tk_resolve_path`, never composed by hand), export the rendered version
  folder with Flame's own `shotgun/movie_file/Submit for review.xml` preset
  (QuickTime H.264 — the preset the native ShotGrid integration uses; its
  root is resolved from `get_flame_version`, never hardcoded), WAIT for the
  asynchronous export to stop growing, then `sg_create` a Version
  (`code`, `entity`, `sg_task`, `sg_path_to_frames`, `sg_path_to_movie`,
  `sg_first_frame`/`sg_last_frame`, `sg_status_list='rev'`,
  `published_files`) and `sg_upload` the movie into `sg_uploaded_movie` —
  the streaming media, without which the Version has no thumbnail and
  cannot be played. Recipe-only: no new tools, the decorator count is
  untouched. +6 tests.

- **The comp media now carries the timecode anchor it declares** (Chat 99 —
  the actual root cause behind four partial fixes): Maya/Arnold EXRs carry
  NO `timeCode` attribute, so the two consumers invent different values.
  `dl_get_media_info` (which writes the `.clip`) falls back to the FRAME
  NUMBER and declares TC 1001; Flame's batch gets nothing — the source Clip
  node's `source_timecode` reads `None`, measured in-vivo — and the Write
  File stamps an EXPLICIT `00:00:00:00` into the comp EXRs. The clip then
  says 1001 and the media says 0 for the same frames, and whichever Flame
  re-reads wins: the declaration lines up and the version flip works, then
  any operation that re-reads the media finds the explicit zero and
  RE-ANCHORS the conformed segment to `00:00:00:00` — at which point BOTH
  versions go 'no media' (measured on the live timeline: five segments at
  `00:00:40:01`, the comped one at `00:00:00:00`). An ABSENT timecode falls
  back to the clip while an EXPLICIT zero overrides it, which is why
  LGT-only conforms stayed stable for months and only the comped shot
  broke. `fix_comp_writefile` now sets `basic_metadata='Custom Values'`
  (Flame refuses the write otherwise: *"Basic metadata values cannot be set
  when the Basic Metadata mode is not set to Custom Values"*) and stamps
  `source_timecode`/`record_timecode` from the derived start frame at the
  node's own `frame_rate` — frame 1001 @ 25 fps = `00:00:40:01`, exactly
  the `source_in` the healthy segments carry. Read back and reported; a
  failure says so instead of being swallowed.
- **`frame_padding` is derived from the source, not left at its default**
  (Chat 99, in-vivo): a fresh Write File pads to 6, so the first comp
  rendered `.001001.exr` against a source of `.1001.exr` — a wasted render
  plus a second, correct one. `_derive_source_frame_range` now also returns
  the padding read from the clip's `[1001-1100]` bracket, and BOTH ops set
  it (falling back to 4 only when the clip is unreadable). +9 tests.


## [1.19.0] — 2026-08-16
- **The comp Write File is named `{Shot}_{Step}`, never `writefile`** (Chat
  99, operator-caught): the media pattern `<name>_v<version>` expands the
  node NAME, and `setup_comp_batch` named it `<shot>_writefile` — the
  literal leaked into the folder, the frames and the PublishedFile code
  (`SEQ003_SH001_writefile_v001.%04d.exr`) instead of the pipeline
  convention the LGT publishes follow (`SEQ003_SH001_LGT_v003`). Both ops
  now take a REQUIRED `step` (the compositing Step's `short_name` read from
  ShotGrid — `Comp -> CMP` on this site — validated as a token, never a
  default): `setup_comp_batch` names the node `<shot>_<step>` and
  `fix_comp_writefile` RENAMES the active batch's Write File to
  `<Shot>_<step>` (Shot = the clip filename stem) and reports
  `name: old -> new`, so the six existing batches are repaired by the same
  idempotent op. Recipe step 0 and 8a instruct the console to `sg_find` the
  Step short_name. +4 tests.
- **Frame alignment is derived and PROVEN, never delegated to the console**
  (Chat 99, in-vivo 'no media' on the COMP flip): the console ran
  `fix_comp_writefile` without `start_frame`, the op left the batch at 1
  and answered OK, the comp rendered `0001-0100` against a `1001-1100`
  source and the conformed segment showed 'no media' on COMP. The recipe
  had asked the model to read the value from the source filenames — it
  skipped it. Guards must not bill the operator, so `setup_comp_batch` and
  `fix_comp_writefile` now DERIVE `start_frame` (default `0`) from the
  conformed clip they already receive (`_derive_source_frame_range`:
  `<startFrame>` / `[first-last]` of the first non-COMP feed), apply it,
  READ BACK the batch start and the Write File range (pulling the range
  onto the source when it did not follow — the WF range is what numbers
  the files: `batchExportBegin` reported `firstFrame=1`), and print one
  `ALIGNMENT: … -> OK | MISALIGNED — do not render` verdict the recipe
  gates the render on, plus an `OVERWRITE WARNING` when Follow Iteration
  would overwrite an existing version and a diagnostic dump of the source
  Clip node's timing (answers in-vivo whether the imported source shifts
  with the batch start). Recipe step 8c adds a NUMBERING CHECK: the first
  rendered filename must carry the source's first frame or the cycle
  STOPS before publishing. +10 tests (the old `zero leaves the batch
  untouched` test enshrined the failure and is gone).
- **Comp renders number from the SOURCE's first frame** (Chat 98, in-vivo
  'no media' on the LIGHT flip): the batch was created with
  `start_frame=1`, the comp rendered frames 1-100 against a source
  spanning 1001-1100, and after update sources the segment anchored to
  COMP — flipping to LIGHT asked for frames outside its span. The spliced
  clip document itself was verified byte-identical on the LIGHT feed; the
  misalignment was pure frame numbering. `setup_comp_batch` takes
  `start_frame` at creation and `fix_comp_writefile` can realign an
  existing batch (`flame.batch.start_frame`); the recipe reads the value
  from the source publish filenames — never assumed. +4 tests.
- **`version_mode` is the real attribute** (Chat 98, console-discovered and
  read-back verified): `versioning` does not exist on this Flame 2027
  build, and the `version_mode` enum silently ignores invalid strings — no
  exception, value unchanged — which is how the `<version>` token once
  rendered as a literal folder name. Both ops now set
  `version_mode='Follow Iteration'` + `version_padding=3`, and the
  render-deliver cycle ITERATES the batch before a re-render — without it,
  Follow Iteration overwrites the same version. +2 tests.
- **'Render the comp' is ONE command** (Chat 98, operator workflow): the
  post-render cycle stopped being two manual steps. Step 8 of the comp
  recipe now runs fix-write-file → render (Background Reactor) → WAIT for
  the full frame count via Glob polling (never publish a partial
  sequence) → tk_publish to the Comp Task → regenerate the conformed clip
  (steps Light+Comp) — leaving the operator exactly one manual gesture:
  update sources on the timeline. A thin pointer concept ('render deliver
  comp') routes the render phrasings to that step with the 'comp' token
  isolated to its name — spread across four fields it out-scored the main
  concept and stole 'create the comp batches' (caught while tuning;
  anti-theft pinned). +4 tests.
- **Write File demoted to media-only; the pipeline owns the clip** (Chat
  98, architecture closed in-vivo and operator-approved): pointing the
  Write File's Create Open Clip at the pipeline's conformed clip made
  Flame OVERWRITE the file wholesale (43 KB multichannel → 2.4 KB, LGT
  versions gone, timeline with no media) — Flame owns any clip its Write
  File creates, there is no co-ownership. Both batch ops now set
  `create_clip=False`, and `versioning=True` + `version_padding=3` — the
  archived setup revealed `<Versioning>False</Versioning>`, the reason the
  `<version>` token stayed LITERAL in rendered paths. The comp reaches the
  timeline through the pipeline instead: publish the render to the Comp
  Task, regenerate the conformed clip with fpt-mcp's
  `openclip_create steps=['Light','Comp']` (multi-step aggregation, fpt
  PR #47), update sources, native flip. The recipe carries the full
  post-render cycle. +3 tests reworked.
- **The comp version must land in the CONFORMED clip** (Chat 98, first
  render in-vivo): Flame appends its own `.clip` extension to
  `create_clip_path`, so passing the full path sent the comp version into
  `<Shot>.clip.clip` — a duplicate the timeline never looks at — while the
  conformed clip stayed at v003. And with no `media_path_pattern` the
  frames landed flat and unversioned (`…_writefile000100.exr`).
  `setup_comp_batch` now strips the extension and sets the versioned
  pattern (`<name>_v<version>/<name>_v<version>.<frame>`), and a new
  plan-native op `fix_comp_writefile` repairs the Write File of the ACTIVE
  batch in place — the active batch cannot be switched from Python, and
  the wired comp graph must not be destroyed to fix two attributes. +4
  tests.
- **The active batch group cannot be switched from Python** (Chat 98,
  falsified in-vivo): `bg.open()` is a SILENT no-op on Flame 2027 when
  another batch is current — three idle-event attempts, `open()+go_to()`
  included, left the current batch unchanged with no error logged,
  falsifying the KB's auto-learned pattern for this case. The recipe now
  verifies the active batch's name FIRST, asks the operator for the one
  UI double-click when it differs, forbids open() retry loops, and guards
  every mutating idle event on the batch-group name so a wrong active
  batch is never touched. +1 test.
- **Comp wiring semantics corrected by the operator** (Chat 98, first
  in-vivo graph): the recipe wired backwards — beauty entered the Back and
  the cascade accumulated on Back. Corrected to the operator's semantics:
  beauty (rgba) enters the shadow Comp's FRONT; each Comp's Result feeds
  the NEXT Comp's FRONT; layers arrive on Back; charmatte gates via the
  SECOND matte input (real socket names read from the node), inverted ON
  the node if a full attribute dump reveals the option — the first pass
  only fuzzy-searched 'invert', which is not a dump — else through a
  Negative into that second matte. The chain now CLOSES: last Result ->
  Write File Front (manual stays the Create Open Clip check and the
  render, never the connection). And the graph lays out as a top-left to
  bottom-right diagonal via node position attributes — batch.organize() is
  explicitly not trusted, the operator reads this graph on camera. +3
  tests reworked.
- **Comp-batch phrasings route to the recipe directly** (Chat 98, logged
  by the console itself): every 'comp batch' phrasing fuzzy-matched the
  generic 'list batch groups' concept — the matcher does no stemming, so
  'batches' never hit 'batch' — and the recipe was only reachable via
  'conform', at three failed queries per session. The concept name now
  carries the routing vocabulary (create/setup/comp/batches); the batch
  read/render concepts keep their queries (anti-theft pinned). +4 tests.
- **Visual node expansion is UI-only** (Chat 98): the schematic
  expand/collapse of a node (showing every layer connection) has no Python
  API — the 2027 graph exposes nothing for it; it is the 'Expand/Collapse
  Current Node' hotkey. The recipe now says so: 'expand multilayer' means
  reading and classifying the output sockets, and the operator presses the
  hotkey for the on-screen expansion.
- **Comp batches must target the CONFORMED clip** (Chat 98, in-vivo): the
  console asked ShotGrid whether the shots' open clips existed, concluded
  they did not (clips are never published to SG), generated a SECOND set at
  `finishing/<Shot>.clip` and wired all six Write Files to it — comp
  versions would land in a clip the conform timeline never looks at,
  silently breaking the version flip. The recipe now pins clip_path to the
  conformed clip at `finishing/clip/<Shot>.clip`, verified ON DISK, and
  forbids generating a clip at any other path.
- **The C++ corruption warning needs a real error** (Chat 98): the chat
  scanned every tool result for the `unordered_map::at` substring — which
  now lives in our own comments and CHANGELOG describing last night's
  crash — and told the operator Flame was corrupted while it was perfectly
  healthy. The warning now also requires an `ERROR:` marker in the same
  result. +2 tests. The hook part requires **MCP Bridge → Reload hook**.
- **`setup_comp_batch`: the comp batch build is ONE deterministic call**
  (Chat 98, operator order 'de una atacada'): a new PLAN-NATIVE op in the
  execute_plan registry — no dedicated MCP tool, so the AU-deck tool
  inventory stays untouched. Per shot it creates `<shot>_comp` with a
  `sources` reel, imports the source open clip, and wires it to a Write
  File whose open-clip target is the SOURCE's `.clip` (operator decision:
  comp versions land in the conformed clip, so the timeline flips natively
  via Source Versions). One plan carries all six shots. Runs on the main
  thread via the idle harness; Write File attributes are set DEFENSIVELY
  and reported set/skipped — the node's attribute surface is dynamic, so
  the first in-vivo run reports the real names instead of crashing on a
  guessed flag. The `every_op_is_a_tool` invariant evolved: ops are either
  tool-backed or plan-native (`tool: execute_plan`), each pinned. The
  `build comp` recipe now leads with the op; the verbatim template remains
  as fallback. +4 tests.
- **Guards must not bill the operator** (Chat 98): a 'create a batch group
  per shot' order burned the operator's remaining session tokens — every
  guard objection (a redirect, next() without default, an unrecognised
  None-check form) cost a full model round-trip. Two fixes: the safety
  layer now accepts the TERNARY guard form (`y if x else z`) alongside the
  existing ones (the unguarded case is still flagged, pinned by test); and
  the `build comp` recipe carries a VERBATIM batch-group-per-shot template
  (idle event + file result + `import_clip` for the source node) that
  passes the safety layer, the AST validator and the redirect suppression
  on first submission — with CI tests that run the template through the
  REAL guard layers, so a future guard change that would reject it fails
  CI instead of billing the operator. +7 tests.
- **Batch territory is main-thread — reads included** (Chat 98, in-vivo):
  the comp phase crashed Flame inside `getNodeList` while `list_batch_groups`
  drilled freshly built batch groups from the worker thread — the shell log
  ends mid-drill. Batch state is UI-backed, so even READS of it interleave
  with main-thread redraws. `list_batch_groups` now runs its drill as an
  idle event with a file-polled result, like the timeline edits. (The batch
  builds themselves survived: the console applied the KB idle-event pattern
  on its own and created 6 batch groups cleanly.)
- **`build comp` recipe in `resolve_concept`** (Chat 98, operator-specified):
  answers 'build comp', 'expand multilayer node' and 'compose shadow and
  light layers'. One shot at a time (the demo records a single shot). Layer
  rules: `shadow_mult` composited FIRST in MULTIPLY with `charmatte`
  INVERTED as matte (charmatte includes props); every layer whose name
  contains 'Light'/'light' plus the club discs — 'disco' and 'disco y beam'
  are DISTINCT layers — cascaded in SCREEN, club beams last (the Chat 92
  review-mov formula). Wiring uses the 2027-graph-verified
  `flame.batch.connect_nodes(output_node, output_socket_name, input_node,
  input_socket_name)` with socket names read from the clip node, never
  guessed; every batch call — reads included — goes through
  `schedule_idle_event`. The recipe stops after wiring: the Write File (and
  its 'Create Open Clip' check) stays in the operator's hands, it is demo
  material. +8 tests.

## [1.18.0] — 2026-08-14
- **Timeline edits run on Flame's MAIN thread** (Chat 98 — CER-backed root
  cause): two SIGSEGVs killed the sixth overwrite of a conform, and the CER
  crash backtrace shows Flame dying on its MAIN thread redrawing the
  editdesk UI (`MenuDoDrawItem` → `lxUploadBufferToTexture` → null) right
  after an `AUTOSAVE`, while the edit ran on the bridge worker thread. A
  worker-thread mutation of the desktop sequence lets the UI redraw
  interleave with invalidated state; a human never crashes this because the
  UI serialises everything on the main thread. `timeline_insert`/`
  timeline_overwrite` now wrap the whole resolve+move+edit in
  `flame.schedule_idle_event` — the documented-safe pattern already
  validated for `render_batch` and structural deletes — with the result
  returned through a file the worker polls (bounded well inside the
  bridge's exec guard; a poll timeout says the edit may still land instead
  of inviting a doubled retry). A cheap read-only probe precedes the
  schedule per the Chat 63 invariant.
- **Flame's own saves arm the settle clock** (Chat 98): the `projectSaved`
  Python hook fires after EVERY save, autosave included — and the autosave
  is a massive structural write the settle clock could not see. A timeline
  edit landing six seconds after `AUTOSAVE ( completed )` looked fully
  settled to the throttle and segfaulted. Any save now counts as the last
  structural write. +9 tests across both changes. The hook part requires
  **MCP Bridge → Reload hook**.
- **Timeline edits join the 10 s settle tier** (Chat 98, in-vivo SIGSEGV):
  five overwrites placed cleanly at 3-5 s spacing and the SIXTH segfaulted
  at address 0x0 inside `PySequence.overwrite` — the same delayed-burst
  profile the imports showed, and timeline edits only had the 2 s gap. The
  settle pattern now covers `import_clips`, `.overwrite(` and `.insert(`;
  `.insert(` also joins the creation-intent pattern, where its absence
  meant ripple-inserts were never write-throttled at all. The 10 s figure
  is measured for imports and extrapolated for edits: if an edit still
  dies at this spacing the next step is a Flame bug report (rapid API
  overwrites on a desktop sequence → SEGV), not more throttling. Creates
  stay at 2 s — eight-in-a-row committed cleanly twice at that gap.
  Requires **MCP Bridge → Reload hook**.
- **Crash-recovery warning shows once, not forever** (Chat 98): the warning
  stayed armed in a module global with the file still saying `running`, so
  every console open for the rest of the Flame session reopened with last
  night's crash. It is now consumed on display — global reset + file
  cleared. An old crash is information the first time and noise every time
  after. +1 test. Requires **MCP Bridge → Reload hook**.
- **Timeline to_desktop: a landed edit can no longer be reported as a
  failure** (Chat 98, in-vivo): moving the sequence to the desktop makes
  Flame resync the workspace, which can invalidate the Python wrappers the
  generated code still holds. Reading `dreel.name` AFTER the move raised a
  C++ `unordered_map::at: key not found` exception — the overwrite had
  already landed (clip placed, sequence on the desktop, verified by the
  panel listings) but the tool returned an error, the console stopped the
  conform at 1 of 6 shots, and the operator was told the UI might be
  corrupted. The reel name is now captured BEFORE the move, and the
  post-edit reporting is guarded so a stale-wrapper hiccup degrades the
  message, never the result. +2 tests.
- **Import settle: media imports wait for Flame's database writes** (Chat
  98, measured in-vivo BOTH ways the same night): the Python API returns
  from `create_library`/`create_reel` before Flame finishes writing its
  project database (the app log shows `Committing history…`/`Syncing…`
  continuing after the call). Six imports on an IDLE Flame succeeded
  back-to-back through this same bridge — and the SAME six `.clip` files
  imported perfectly by hand through the UI — while one import arriving 2 s
  after eight spaced creates killed Flame inside `importClips` at the
  Wiretap gateway, with the gateway logging its client vanishing one second
  after connect. `import_clips` now requires 10 s of quiet since the last
  structural write of any kind (imports included — they write framestore
  metadata too); other structural writes keep the validated 2 s gap. Same
  handler-thread wait as the burst guard: Flame's main thread is never
  touched. +4 tests.
- **Burst guard: the bridge spaces structural writes** (Chat 98 — CRASH):
  the hardened conform recipe fired eight structural creates (4 libraries +
  4 reels) in 1.5 s; Flame raised its error report one second after the
  burst and crashed violently. The same tools, humanly paced across
  conversation turns, completed the Chat 92 conform without incident — a
  burst of chained writes is a crash mode known since Chat 55, where
  'space them out' became the manual rule. The bridge now enforces a 2 s
  minimum gap between operations matching the creation-intent pattern, for
  EVERY caller — the `# DT` marker skips the redirect check only, and it was
  precisely the dedicated `create_*` tools that produced the burst. The wait
  runs on the connection-handler thread, never Flame's main thread (Chat 63
  invariant untouched).
- **Conform recipe: clips gate + explicit naming** (Chat 98): the crashed
  run had built 4 libraries with ZERO `.clip` files on disk — structure that
  must be deleted by hand, since structural deletes from the console
  deadlock Flame 2027. The recipe now treats a missing/failed `.clip` as a
  FULL STOP before anything is created in Flame. It also names the
  containers: reel `sources` in each sequence library (naming the reel after
  its library read as a duplicated hierarchy — user report), master timeline
  in library `Conform`, reel `master`, the sequence carrying the Cut's name.
  +7 tests.
- **Chat watchdog measures silence, not duration** (Chat 98): it capped total
  wall-clock, which was fine while every turn was a question-and-answer
  exchange. Once the conform recipe stopped asking needless questions the
  whole workflow became ONE long turn — around 30 tool calls — and died at
  180 s mid-run while streaming events perfectly: the fix for the questions
  walked straight into the timeout. What signals a hang is a MUTE process, so
  every line of output now refreshes the deadline (before the JSON parse, or a
  burst of malformed lines would read as silence). A healthy 10-minute conform
  survives; a subprocess that stops emitting still dies. An absolute 30-minute
  ceiling remains so a pathological loop cannot run forever, and it reports
  differently — hitting the ceiling is not a hang. The timeout hint no longer
  blames the Ollama server when the backend is Anthropic. +10 tests.
- **The chat panel renders the assistant's markdown** (Chat 98): answers came
  out literal — `## Conform plan`, `**confirm**`, and table rows spelled as
  `|---|---|` — because the panel escaped the text and only converted
  newlines. On a recorded demo that reads as a tool that cannot format its
  own output. `_md_to_html` now renders headings, bold, italics, inline code,
  fenced blocks, bullet/numbered lists (nesting by indent), blockquotes,
  rules, links and tables, into the HTML/CSS subset Qt's rich-text engine
  accepts. Hand-rolled rather than `QTextDocument.setMarkdown()`, whose
  output carries Qt's own font stack and colours and would fight the panel
  palette. Only the assistant role is rendered: the operator's text stays
  literal (a prompt containing `**` is not formatting), content is escaped
  before any tag is added, code spans are extracted first so `**` inside
  backticks survives, and an unrecognised construct degrades to plain text
  instead of vanishing. +24 tests. Requires **MCP Bridge → Reload hook**.
- **Operator prompts render in Autodesk yellow** (Chat 98): the in-Flame
  console painted only the small `You:` label and left every message body at
  a fixed `#ddd`, so the operator's input was indistinguishable from the
  assistant's output. The bubble palette now carries a per-role body colour
  and the user role uses `#ffff00` — the same accent the FPT console applies
  to its user bubbles. Assistant, tool, warn and error rows are unchanged.
  +3 tests. Requires **MCP Bridge → Reload hook**.
- **The in-Flame console keeps ONE conversation across turns** (Chat 98):
  every turn spawns a fresh `claude -p`, and until now the child started from
  zero each time — all it saw was a digest of the last 4 messages truncated to
  500 characters. Measured in-vivo on a conform: the model re-discovered the
  FPT link, the project id, the Cut and its CutItems **five times**, and
  re-fetched the workflow recipe on every turn because it fell outside the
  digest (once resolving the wrong concept in the process). The console now
  captures the CLI's `session_id` from the stream events and passes `--resume`
  on the next turn; with a live session the message is sent alone (re-injecting
  the digest would duplicate, in truncated form, what the child already
  remembers). **Clear** drops the session too, and a `--resume` against a
  session the CLI can no longer find drops the id and says so instead of
  wedging the console. +8 tests. Requires **MCP Bridge → Reload hook**.
- **Conform recipe hardened against needless questions** (Chat 98, same
  in-vivo run): ask at most ONCE, batching every genuine data ambiguity into a
  single message. Specifically — probe `openclip_create` WITHOUT a selector
  first and propose the Task its `upstream_tasks` suggestion returns instead of
  opening with "which step?"; `to_desktop=true` on the first timeline edit is
  the decided behaviour, not a question; ONE master sequence for the Cut (the
  per-Sequence libraries are staging — the console read them as one timeline
  each and asked); and when the project has no PipelineConfiguration and the
  `flame_shot_clip` template cannot resolve, build the path the template itself
  defines (`…/finishing/clip/<Shot>.clip`) rather than inventing a directory or
  stalling. +5 tests, one per question removed.
- **Pipeline recipes in `resolve_concept`** (Chat 98): two new concepts —
  `conform cut` and `fpt link` — carry a step-by-step `recipe` spanning both
  MCP servers, so the procedure lives in data instead of in whatever the
  caller remembers to type. In-vivo, "Conform the main cut" produced a plan
  built on importing an EDL into Flame (no tool does that) and reported the
  Flame and FPT project names as a "mismatch" (they are linked; different
  names are the normal case). The recipes state the real order, the gates
  (`choice_required` on the Task selector, `to_desktop` on library
  sequences) and the traps (one-based sequence frame vs zero-based
  `edit_in`; no EDL import). The `recipe` field is deliberately NOT scored by
  the matcher: a procedure names many tools, and scoring it let the conform
  entry steal "import clips into a reel" from its own concept. +6 tests.
- **Console rules: workflows resolve their recipe first** (Chat 98): the
  in-Flame system prompt now requires `resolve_concept` before planning a
  conform/publish/link, and states that this session has no ShotGrid project
  scope by design — the project is resolved with `fpt_link(action='get')` and
  passed explicitly, and differing Flame/FPT project names are never reported
  as a mismatch. Requires **MCP Bridge → Reload hook** in Flame to take
  effect.
- **New tool `fpt_link`** (Chat 93, narrowed to READ-ONLY in Chat 98): reports
  the NATIVE Flame↔FPT project link — the `shotgun_project_name` ProjectEntry
  attribute, the same one Flame's shipped FPT plugin
  (`presets/<ver>/shotgun`) reads and writes (mechanism reverse-engineered
  from the shipped plugin + session logs; the attribute persists in the
  project's framestore metadata and is only reachable with the project
  loaded). `get` is the only action; the tool is annotated read-only and
  auto-approved.
- **`fpt_link` set/break REMOVED before ever shipping** (Chat 98, in-vivo):
  both write attempts ended with Flame raising its error report, from the
  native Toolkit dialog and from this tool alike. Root difference found in
  the code: writing the attribute is not an assignment — Flame saves the
  WHOLE project through it (the app log shows `Saving Project ... DONE`,
  `Connected to DLmpd`, a 2 GB metadata streaming buffer, all *inside*
  `setShotgunProjectName`) — and the bridge executes tool code on a worker
  thread (`flame_exec`, `hooks/flame_mcp_bridge.py`), never on Flame's main
  thread, whereas the native plugin performs the same write from the MAIN
  thread (`tk_flame_basic/bootstrap.py`). Neither validation layer covers
  that axis: they check symbols and patterns, not the executing thread, and
  dedicated tools bypass the bridge-side check via the `# DT` marker.
  Creating and breaking links is now done only from Flame's own FPT menu;
  the removed actions fail loudly and never reach Flame. Doing it safely
  would require `schedule_idle_event` (main thread) plus an asynchronous
  result contract — deliberately not attempted here.
- CI hardening against environment drift: `ruff` pinned (0.15.11) and the
  `mcp` dependency bounded `<2` (mcp 2.x removes `mcp.server.fastmcp`).
- Flame chat: repo discovery now includes `~/Projects/flame-mcp` — without it the spawned CLI ran without the project `.mcp.json`, losing the Flame MCP server (session claimed only ShotGrid/Maya tools).
- Hook import bootstrap resolves the `/opt/Autodesk/shared/python/` symlink via `os.path.realpath` — with `abspath` the repo `src/` was never found, so the `flame_mcp._config`/`_readonly` imports silently degraded to the fail-soft stubs and the chat subprocess lost per-console MCP scoping (`build_scoped_mcp_config` → `None`), usage logging and suggestion capture. Runtime paths (bridge socket, `config.json`) intentionally unchanged.
- execute_python redirect guard: batch-group content traversal (`flame.batch.reels`, `bg.shelf_reels`, `reel.clips`) is no longer redirected to the library-scoped read tools — no dedicated tool can read inside a batch group, so the `.reels`/`.clips` soft redirects dead-ended the model (in-vivo false positive: "list clips in current batch group"). Soft redirects are now suppressed when batch context AND content drill co-occur (`_BATCH_CONTEXT_RE`/`_BATCH_DRILL_RE` in `safety.py`); pure batch listings still redirect to `list_batch_groups()`. +4 tests (`TestBatchDrillSuppression`).
- **Timeline ops resolve the sequence from the desktop too** (in-vivo Chat 92): after a `to_desktop` move the sequence is no longer in any library, so events 2..N of a multi-event conform could not resolve it ("sequence not found") and had to fall back to raw `execute_python`. The generated template now also searches the desktop reels' sequences and edits there directly (desktop sequences carry no library lock). +1 test.
- **`record_frame` documented as ONE-based** (measured in-vivo: `PyTime(1)` = first sequence frame, while `segment.record_in.frame` reads back zero-based — mixing the two cost one overwritten frame during the Chat 92 conform).
- **Wiretap tools dir resolved dynamically** (`_wiretap_tools_dir`: `$FLAME_WIRETAP_TOOLS` → `tools/current` → newest versioned dir): macOS installs ship no `current` symlink, so `get_project_info`'s authoritative wiretap route always failed silently and the `.cfg` fallback misreported a 25 fps project as 23.976 (the cfg `Framerate` key is a creation-time default, not the live setting). Same resolver now feeds `flame_wiretap_tree`.
- **Flame log dir resolved dynamically** (`_logs_dir()`: `$FLAME_LOG_DIR` → `/opt/Autodesk/logs` → `/opt/Autodesk/log`): this Mac ships the singular name, so `list_flame_logs`/`read_flame_log` always failed with "directory not found".
- **`import_clips` warns on 0-clip imports** — a zero-length result is a silent Flame rejection (e.g. a malformed `.clip` XML dropped with no logged error), not a success.
- **`list_desktop_reels` now lists desktop sequences** (tagged `[SEQ]` with frame duration) — they were invisible, which made the tool a dead-end target for the `desktop.*reel` redirect; the redirect guard also suppresses soft redirects for desktop content drills (same mechanism as batch, +2 tests).
- execute_python redirect guard: desktop content drills (`.sequences` et al. under a desktop context) suppress soft redirects — covered by `TestBatchDrillSuppression`.
- Flame chat (_FlameChat): prompt fed to the claude CLI via stdin — a positional prompt after the variadic `--mcp-config` was swallowed as a config path ("Input must be provided either through stdin..."), and dash-prefixed messages parsed as options; empty messages now get a friendly bubble.

## [1.17.0] — 2026-08-05
- Release tooling: `commits_since_tag` now tolerates the release-in-progress
  commit via the `CUT_RELEASE_VERSION` anchor (same mechanism as
  `version_match`/`changelog_tag_sync`). Without it the check deadlocked the
  flow once `max_age_days` was exceeded (Chat 92). Engine propagated from
  `invariant_types_canonical.py`.

### Added
- **`record_frame` on `timeline_insert` / `timeline_overwrite`** (also in the
  `execute_plan` registry): optional explicit sequence frame for the edit
  point, dispatched as `flame.PyTime(record_frame)` (the API's
  `insert_time`/`overwrite_time` argument, previously unexposed — edits always
  landed at Flame's default position). Motivation: scripted conform — placing
  each ShotGrid CutItem at its `edit_in` position on a master sequence.
  Backward compatible: omitting it keeps the previous behavior. Needs in-vivo
  validation on Flame 2027 before release.

## [1.16.0] — 2026-06-24

### Added
- **Per-call token-usage to the shared cross-console log.** The bridge already
  parsed `usage` from the result event for its session counter; it now also
  appends a per-call line (input context + cache + reasoning output) to
  `~/Library/Logs/mcp-console-usage.log` via `flame_mcp._readonly.log_usage`, so
  request weight is objectively visible alongside the fpt/maya consoles. Covered
  by `tests/test_suggestion_capture.py`.

### Changed
- **In-Flame console request is much lighter — deferred tool loading + MCP
  scoping.** The bridge's `claude` subprocess now (1) runs with
  `ENABLE_TOOL_SEARCH=true`, so MCP tool schemas are deferred (only tool names
  load upfront; the model fetches a schema on demand via `ToolSearch`), and (2)
  is launched with `--strict-mcp-config --mcp-config` carrying only the servers
  the Flame console needs — Flame + ShotGrid (`fpt-mcp`), NOT Maya. Maya's tool
  schemas no longer bloat every request. `flame_mcp._readonly.build_scoped_mcp_config`
  builds the curated config (fail-soft no-op if it can't); covered by
  `tests/test_suggestion_capture.py`.
- **CI Python matrix realigned to the real runtimes.** The test matrix now runs
  `[3.13, 3.14]` (the MCP server runs on system Python — 3.13.9 on the dev box;
  Flame 2027 ships 3.13) instead of `[3.10, 3.11, 3.12, 3.13]`. `requires-python`
  raised to `>=3.13`; the ruff/mypy/verify_concepts jobs and the Codecov upload
  pin moved to 3.13; the README requirement was corrected.

## [1.15.0] — 2026-06-23

### Changed
- **In-Flame bridge runs read-only (recording-safe)** — the spawned `claude`
  subprocess is now launched with `--disallowedTools Edit Write MultiEdit
  NotebookEdit Bash`, so it can no longer modify the repository. MCP tools and
  Read stay available, so Flame work and RAG self-learning are unaffected
  (`learn_pattern` is a server-side MCP tool, not an agent file edit). The
  deny-list is hardcoded in a fail-soft fallback, so the lockdown holds even if
  `flame_mcp._readonly` cannot be imported. Code-improvement ideas are captured,
  not applied: the agent emits `@@SUGGESTION@@ <title> :: <detail>` lines that
  `flame_mcp._readonly.capture_suggestions` appends to the git-ignored
  `CONSOLE_IMPROVEMENTS.md` backlog (for a later dev session / PR) and strips
  from the reply. Rules 9/10 reworded: self-update goes through `learn_pattern()`,
  not by editing `## Learned Patterns`. Covered by
  `tests/test_suggestion_capture.py`.

### Fixed
- **In-Flame console mirrors the user's language per message** — the bridge's
  appended system prompt now carries an explicit LANGUAGE directive (previously
  absent) that overrides the global `CLAUDE.md` "Spanish by default" bias and
  re-detects the latest message's language every turn.

## [1.14.1] — 2026-06-22

### Changed
- **Bridge injects `SHOTGRID_PROJECT_ID=0` into the spawned `claude` env**
  (Chat 69, safety net). The Flame bridge does no ShotGrid itself, but the
  `claude` it spawns loads the ecosystem MCP servers (fpt-mcp included) from
  `~/.claude.json`, and the bridge has no ShotGrid project context (no tk engine).
  It now passes `"0"` ("no project") so a project-scoped `sg_create` via fpt-mcp
  **fails loudly instead of silently writing to fpt-mcp's stale `.env` default**
  — fpt-mcp's gate then asks the user. Zero silent defaults across all consoles.

## [1.14.0] — 2026-06-22

### Added
- **Reasoning-effort selector in the Flame panel** — combo
  (Auto / Low / Medium / High / Max, default **Auto**) controlling the spawned
  `claude` subprocess effort; persisted to `config.json → effort`. Affects only
  the MCP-spawned subprocess, never the operator's top-level session. (PR #35)

### Changed
- **Panel default model → Claude Opus 4.8** (Fable 5 kept as a selectable
  option); remaining panel UI strings translated to English. (PR #34)
- **Panel colour scheme → Autodesk palette** — the accent is unified to
  Autodesk yellow (`#ffff00`, dark `#1c1c1c` text on yellow buttons) and the
  residual purple/blue accents are retired in favour of the neutral grayscale
  base. Status colours unchanged.

## [1.13.0] — 2026-06-15

### Added
- **Shared OPSEC error sanitisation** (`error_scrub.py`) — exception text echoed
  to the model at the bridge boundary is now scrubbed of credential-shaped
  tokens and length-bounded (300 chars). `_call_flame`'s exception path uses
  `safe_error_message(e)` (scrub + truncate) and `_fmt`'s error branch scrubs the
  formatted message regardless of origin (bridge exception OR Flame-side error
  text); normal (non-error) output is untouched. The helper is byte-identical
  across the ecosystem (canonical `~/Projects/error_scrub_canonical.py`; same
  copy in fpt-mcp / maya-mcp) — completing the "port `sg_errors_to_json` as a
  shared helper" follow-up (the ShotGrid `Fault` *taxonomy* stays fpt-specific;
  flame raises no `Fault`s, so only the scrub+truncate primitive is shared).
  +8 tests (`tests/test_error_scrub.py`).

### CI / Docs
- **Code knowledge graph auto-publishes to GitHub Pages** on push to `src/**`
  (`.github/workflows/graphify-pages.yml` + `scripts/graphify/`), original
  force-directed layout + deterministic file-based community names (no LLM key);
  README links the live graph. `src/graphify-out/` is gitignored.

## [1.12.1] — 2026-06-15

### Changed
- CI: Python 3.13 added to the test matrix.

## [1.12.0] — 2026-06-15

### Changed
- **Bridge log is now size-rotated and mode-restricted** — `_log` in
  `hooks/flame_mcp_bridge.py` rotates `flame_mcp_bridge.log` at 5 MB (one
  `.1` backup) so a long Flame session can no longer grow it without bound,
  and chmods it to `0o640`. Completes the audit log-hardening item whose
  bridge half was deferred while Flame was open (the server-side
  `flame_rag.log` rotation already shipped). Also scrubs the `glorfindel`
  hostname from a bridge code comment (OPSEC parity with the docs).

### Added
- **Operation journal is now wired into the execution path** — `_journal_record`
  is invoked from `_execute_python_impl` and from every mutation tool
  (`rename_segments`, `create_sequence`, `_render_batch_impl`, `export_clip`,
  `create_library`, `create_reel`, `create_folder`, `create_reel_group`,
  `create_batch_group`, `_import_clips_impl`, timeline insert/overwrite), so
  `operation_history` and `undo_last_operation` finally return real data
  instead of the "no operations recorded" / "journal is empty" sentinels.
  Each entry carries an auto-generated undo snippet. (Previously dead code —
  there was no audit trail of what the LLM did to the project.)
- **A2-EXT PyExporter safety rule now has pytest coverage** —
  `tests/test_safety.py::TestPyExporterIdleEvent` asserts a bare
  `flame.PyExporter().export(...)` is blocked and the documented
  `schedule_idle_event` form passes, so a refactor can no longer silently
  drop the rule and reintroduce the Flame main-thread hang it prevents.
- **CI hardening** — Python 3.13 (the deployed interpreter and the one inside
  Flame 2027) added to the test matrix; the pytest step now
  `--ignore=tests/test_flame_live.py` as defense-in-depth so the live harness
  can never arm in CI even if a stray `FLAME_LIVE` leaks into the env.
- **`flame_rag.log` is now size-capped** — `search.py::_log` rotates the file
  to `flame_rag.log.1` at 5 MB (mirroring the `TELEMETRY_MAX_BYTES` pattern in
  `_session_stats.persist_timing`), replacing the previous unbounded append.
- **`cut-release.sh` maintains the CHANGELOG footer compare-links** — it now
  repoints `[Unreleased]` at the new tag and inserts the per-version compare
  link on every cut, so the footer can no longer rot (it had drifted to
  v1.2.1 while the code was at v1.11.1).

### Changed
- **`execute_plan` is now async** — it offloads `dispatch_plan` through
  `_to_thread_with_heartbeat`, so the blocking bridge socket (up to the 120 s
  import timeout for a covered op) no longer freezes the asyncio event loop;
  it now streams heartbeats and matches the existing
  `execute_python`/`import_clips`/`render_batch`/`export_clip` wrappers.
  Per-op registry handlers stay synchronous.
- **Installer deploys the Flame bridge as a symlink** — `install.sh` step 5
  now uses `sudo ln -sf` instead of `sudo cp`, eliminating the recurring
  stale-bridge drift class. `--doctor`'s bridge check additionally
  sha256-compares the deployed hook against `hooks/flame_mcp_bridge.py` and
  FAILs on a stale regular-file copy (WARN when it merely matches now).
- **Only non-destructive tools are pre-approved** — `install.sh` step 8,
  `scripts/generate_settings.py` and `_sync_tool_permissions` now exclude any
  `@mcp.tool` carrying `annotations=_DST` (AST-based, covering async tools the
  old regex missed). `execute_python`, `execute_plan`, the
  `create_*`/`timeline_*`/render/export/import writers and
  `undo_last_operation` fall through to the interactive permission prompt
  instead of being silently auto-allowed.
- **Documentation accuracy sweep** — write-trust corrected to **Opus/Fable**
  (Sonnet, the default cloud model, stages to `rag/candidates.json` for human
  review) across README, `docs/ARCHITECTURE.md` and the test-plan docs; README
  tool count `18`→`38` and the `--doctor` check labels corrected; the project
  structure tree now shows `src/flame_mcp/rag/{build_index,search}.py`; the
  offline-Mac model setup uses `qwen3.5:4b` (a real `AVAILABLE_MODELS` entry)
  instead of the non-existent `qwen2.5-coder:7b`; the FLAME_API export sample
  resolves the H.264 QuickTime preset via `glob` of
  `/opt/Autodesk/presets/*/…` instead of a hardcoded `2026.2.2` path that does
  not exist on Flame 2027 (RAG corpus rebuilt).
- **Live-Flame harness is now opt-in via `FLAME_LIVE=1`** — Chat 64
  incident: a routine `pytest tests/` run with Flame open armed
  `test_flame_live.py` (its gates probe the bridge at collection time) and
  queued render/export idle events on the main thread → Flame froze
  (second main-thread violation after Chat 63). Without the env var the
  module now skips at collection WITHOUT touching the bridge socket;
  firing at the real Flame is a user decision, never a suite side effect.
  Lock tests in `tests/test_live_optin.py`. Run a live pass with
  `FLAME_LIVE=1 pytest tests/test_flame_live.py`.

### Fixed
- **`collect_media_paths` generated un-parseable Python on every call** — the
  inline ternary `f"    {reel_filter}\n" if reel_name else ""` bound across
  implicit string concatenation, dropping the clips loop (or the import/outer
  setup) and raising `SyntaxError`/`IndentationError` on every invocation.
  Rebuilt with an explicit if/else that assembles the reel body via a
  `_clip_loop(indent)` helper, mirroring `_import_clips_impl`. Regression test
  `tests/test_collect_media_paths.py` compiles both branches.
- **Journal undo of a structural create no longer deadlocks Flame 2027** — the
  undo generators for `create_library`/`create_reel`/`create_batch_group` now
  route `flame.delete(target)` through `_schedule_idle_delete` (a `_do_delete`
  closure dispatched via `flame.schedule_idle_event` plus a result file)
  instead of a bare `flame.delete`, honoring the invariant that a bare
  `flame.delete` on a PyReel/PyLibrary deadlocks the Flame main thread.
- **`get_project_info` returned empty Resolution / Bit depth / Scan mode
  (+ SELF-HEAL) on every call** — Chat 64 gotcha, latent since the tool was
  authored (2026-03-07): the Wiretap XML parser used guessed tag names
  (`Width`/`Height`/`BitDepth`/`ScanMode`/`ColourSpace`) that do not exist
  in the PROJECT-node XML. Verified against a real Flame 2027 dump
  (`wiretap_get_metadata -m XML`): the project node exposes `FrameWidth`/
  `FrameHeight`/`FrameDepth`/`FieldDominance`/`ColourPolicyName` —
  `FrameRate` was the only correct guess, which is why frame rate populated
  while everything else dashed out. Also switched the stream selector to
  the documented `-m` flag (`-s` is tolerated by the binary but undocumented
  for this tool), and tightened the `.cfg` fallback guard: a PARTIAL wiretap
  answer missing a required field (Frame rate, Resolution) now falls back to
  `.cfg` instead of being displayed as authoritative. Regression tests feed
  the real captured XML through the parsing path (`tests/test_tools.py::
  TestGetProjectInfo`), closing the mock-only coverage gap that hid the bug.

### Security
- **Destructive Flame tools are no longer auto-approved** — combined with the
  now-live operation journal, an LLM hallucination can no longer delete a
  populated library of client media without an interactive permission prompt,
  and every mutation is recorded with an auto-generated undo.
- **`.gitignore` now covers the real `learn_pattern` staging paths** —
  `src/flame_mcp/rag/candidates.json` and `src/flame_mcp/rag/failed.json`
  (the actual `_CANDIDATES_PATH`/`_FAILED_PATH` targets) were outside the
  top-level `rag/` ignore rules, so a `git add -A` could have committed
  staged (possibly hallucinated) API patterns and internal asset/project
  names. Now ignored.
- **Internal hostname removed from published example/docs** —
  `config.example.json` and `CLAUDE.md` use a `gpu-host.lan` / "LAN GPU host"
  placeholder instead of the real hostname, and the retired "Mac M5 Pro"
  reference was dropped.

## [1.11.1] — 2026-06-11

### Fixed
- **`create_sequence` accepts a `duration` (frames)** — the tool had no
  duration parameter at all (Chat 63 gotcha: asking for a 50-frame sequence
  produced Flame's 1-frame default). A `duration > 0` is now forwarded to
  `PyReel.create_sequence` as `flame.PyTime(frames)`; the success message
  echoes the resulting `seq.duration.frame` so the created length is visible.
  Omitting it preserves the previous behaviour. Validated in-vivo against
  Flame 2027 (project `2027_test`: 50 requested → 50 created, confirmed
  independently via `list_clips`).
- **F4b AST validator falsely rejected `flame.<ClassName>` references** —
  the introspector records classes without the `flame.` prefix while every
  Flame class is also exposed as a module attribute, so official cookbook
  patterns like `flame.PyTime(50)` were blocked as "unresolved symbol"
  (found in-vivo when the validator rejected the create_sequence duration
  pattern). `_graph_symbols` now also registers `flame.{ClassName}`.

## [1.11.0] — 2026-06-11

### Added
- **`list_clips` now lists sequences with durations (TAREA 7 sub-5)** —
  `reel.sequences` were invisible to the tool, so "list sequences" / "how
  long is sequence X" requests redirected from `execute_python` into a dead
  end. Both branches (filtered and all-libraries) now print `[SEQ] <name>
  duration=<frames>` rows and clip durations; headers show clip AND sequence
  counts. Query lookup tables (server instructions, CLAUDE.md, README)
  updated. Validated in-vivo against Flame 2027 (project 2027_test).

### Changed
- **Live harness gates on a fully loaded project (TAREA 7 sub-6 hardening)** —
  `test_flame_live.py`'s render/export guards used to run whenever the bridge
  socket answered; with Flame at the project picker they queued idle events
  against a half-initialized main thread and froze Flame (Chat 63 incident,
  force quit required). The scheduling tests now skip unless a read-only
  probe confirms `flame.projects.current_project` answers. User-declared
  invariant: never queue main-thread work against a half-loaded Flame.
  Full harness validated in-vivo: 3/3 passed with a loaded project, the
  scheduled render executed and Flame stayed healthy.

## [1.10.0] — 2026-06-11

### Added
- **Visible-progress streaming (Chat 62 design, MCP-native)** — the five
  long-running tools (`execute_python`, `flame_wiretap_tree`, `render_batch`,
  `export_clip`, `import_clips`) now stream a `ctx.info` heartbeat every 10 s
  while the operation blocks inside Flame (`_to_thread_with_heartbeat`); fast
  operations emit nothing. Design adjusted from the original "convert tools to
  async" plan: the `execute_plan` op registry is synchronous, so each tool is
  split into a sync `_<name>_impl` body (called by the registry and the test
  suite) plus an async `@mcp.tool` wrapper that adds the heartbeat. 9 new
  tests (545 → 554); `pytest-asyncio` added to the CI test deps.

### Fixed
- **AST tool scanners missed `async def` tools** — both `install.sh` Step 8
  (pre-approved tools list) and the server's own settings sync block walked
  only `ast.FunctionDef`; the five tools converted to `async def` would have
  silently vanished from the pre-approved list (permission prompts on every
  use). Both scanners now match `(FunctionDef, AsyncFunctionDef)`; all 38
  tools verified detected.

## [1.9.3] — 2026-06-10

### Fixed

- **glm-4.7-flash doc-drift corrected** — `scripts/setup_ollama_linux.sh` had a
  wrong ~4 GB download estimate for `glm-4.7-flash` (real size ~19 GB at q4 quant)
  and wrongly recommended it for GPUs with 6 GB VRAM (impossible at ~19 GB). The
  6 GB / CPU tiers now recommend `qwen3.5:4b` (the ecosystem's validated small-GPU
  fallback, ~2.5 GB Q4_K_M). All three tier branches (`6 GB`, `CPU/RAM`, fallback)
  updated. Size estimate corrected: `~4 GB` → `~19 GB`.
- **glm-4.7-flash not-recommended notice added to all docs** — `glm-4.7-flash` was
  evaluated and rejected for the ecosystem (Ollama tool-calling bugs, upstream issues
  #13820/#13840, as of June 2026). README, `docs/ARCHITECTURE.md`, `install.sh` Ollama
  prompts, and `scripts/setup_ollama_linux.sh` model comment block all updated with
  clear "NOT recommended" notices. Historical mentions preserved; only active
  recommendations corrected.
- **Stale model example `qwen3-coder:30b-a3b` in `install.sh`** — the "skip Ollama"
  section showed an outdated model name as a config example. Replaced with the current
  canonical local model `qwen3.5-mcp`.
- **`wiretap_smoke.sh` SDK probe segfaulted on Flame 2027** — the script invoked
  `wiretap_sdk_smoke.py` with the system `python3`, but the Wiretap SDK `.so` is
  compiled against Flame's embedded Python ABI and segfaults under the system
  interpreter even at matching minor versions (3.13 vs 3.13). New `FLAME_PYTHON`
  env var (default `/opt/Autodesk/python/2027/bin/python3`, falls back to
  `python3` on non-Flame boxes); `wiretap_sdk_smoke.py` default `SDK_PATH`
  updated 2026.2.2 → 2027 (`…/python/2027/lib/python3.13/site-packages/adsk`).

### Validated
- **Wiretap smoke suite on Flame 2027 (build 2027.pr238)** — first run against
  2027, GUI not required (stone+wire / ifffsWiretapServer standalone): CLI
  32/32 non-destructive tools OK (5 destructive hard-skipped, 37 total), SDK
  probe 5/5 steps OK (22 symbols). `docs/wiretap_smoke_report.md` regenerated
  from this run. Closes the last "Flame 2027 Tested" gap.

## [1.9.2] — 2026-06-10

### Changed
- **Cloud model selector refreshed** — `AVAILABLE_MODELS` now offers Claude
  Fable 5 (`claude-fable-5`), Claude Opus 4.8 (`claude-opus-4-8`) and Claude
  Sonnet 4.6 (Opus 4.7 removed). Self-learning (`learn_pattern` write-trust) is
  now reserved for **Opus + Fable** — Sonnet and local models are read-only
  (`WRITE_ALLOWED_MODELS`, `rag/validate_index.py`, `config.example.json`,
  README + ARCHITECTURE.md updated in lockstep; concept registry green).

## [1.9.1] — 2026-05-26

### Fixed

- **execute_python redirect/safety false positives (TAREA 7)** — three
  legitimate-code patterns were wrongly blocked:
  - **copy / move / method-form delete / timeline insert were redirected.**
    `_CREATION_INTENT_RE` (which suppresses the soft `.libraries`/`.reels`/`.clips`
    redirect when the code is a modification, not a read query) only recognised
    `create_*` / `.overwrite(` / `import_clips(` / `flame.delete(`. A
    `flame.media_panel.copy(...)`, `.move(...)`, method-form `clip.delete()`, or
    `seq.insert(...)` that traversed the hierarchy was redirected as if it were a
    read — which forced the model to obfuscate the traversal with `getattr()` to
    dodge the redirect. The intent regex now also matches `media_panel.copy/move(`,
    any `.delete(` (not just `flame.delete(`), and `.insert(`.
  - **`if not x:` / `if x:` guards were flagged as unchecked.** The
    `next(..., None)` "result used without a None check" guard only accepted
    `if x is [not] None`; the equally valid `if not x:` and `if x:` truthy forms
    were treated as missing and the code blocked. The negative-lookahead now
    accepts those forms (a genuinely unchecked result is still flagged).
  - Confirmed the AST validator no longer false-positives on `flame.PyTime`
    (already present in `rag/api_graph.json`, Flame 2027).
  - Adds 8 regression tests (4 in `test_redirect.py`, 4 in `test_safety.py`).

- `create_sequence` raised `AttributeError: 'PyMediaPanel' object has no
  attribute 'create_sequence'` on Flame 2027 — it called
  `flame.media_panel.create_sequence(name=…)` (which does not exist) and
  ignored the resolved reel. Now calls `PyReel.create_sequence(name=…)`, so the
  sequence is created in the target library/reel — the API already canonical in
  the RAG docs, test fixtures and golden set. Confirmed in-vivo on Flame 2027
  (build 2027.pr238). Adds the previously-missing `test_create_sequence`
  regression guard (asserts `reel.create_sequence(`, rejects
  `media_panel.create_sequence`) plus a reel-not-found case. `create_sequence`
  is a pre-4C tool and was outside the Chat 53 "validated live" set, which is
  why the bug shipped uncaught.
- `timeline_insert` / `timeline_overwrite` surfaced a raw
  `RuntimeError: Clip is locked` on **library** sequences. Verified in-vivo on
  Flame 2027 that library sequences are read-only for timeline edits (fails on
  any library, fresh or persisted, 1-arg or 2-arg form, even after
  `acquire_exclusive_access()`); only desktop sequences are editable. The single-arg
  `seq.insert(src)` / `overwrite(src)` form was confirmed correct (works on the
  desktop, `ret=True`) — the lock, not the call shape, was the blocker. The tools
  now catch that lock and, when the sequence and source both resolved (so the lock
  is the only blocker), return a `LOCKED` message offering an opt-in `to_desktop`
  flag instead of crashing. With `to_desktop=True` — set only on explicit user
  confirmation — the sequence is moved to the first desktop reel via
  `flame.media_panel.move` and edited there; it is never moved automatically.

## [1.9.0] — 2026-05-21

### Added — 4C write tools + execute_plan ops (Chat 53)

- Ten dedicated write tools, each registered as a closed-schema
  `execute_plan` op and **validated live against Flame 2027**:
  - `render_batch` — Background Reactor render of the current Batch Group,
    scheduled via `flame.schedule_idle_event` (calling `flame.batch.render()`
    synchronously crashes Flame and the `execute_python` AST guard blocks it,
    so a dedicated `# DT` tool is required to run the documented-safe form).
  - `export_clip` — `PyExporter` export via idle event (same deadlock guard).
  - `import_clips` — import media from disk into a library/reel.
  - `create_library`, `create_reel`, `create_folder`, `create_reel_group`,
    `create_batch_group` — container creation.
  - `timeline_insert`, `timeline_overwrite` — `PySequence.insert` / `overwrite`.
- `execute_plan` annotation flipped read-only → destructive, since a plan can
  now trigger these write ops.
- MCP tool count 28 → 38; README table, CLAUDE.md rule 16 and the
  `execute_plan` docstring updated in lockstep under the concept registry.
- `render_batch` / `export_clip` detect when the GUI-thread APIs
  (`schedule_idle_event`, `PyExporter`) are unbound (Flame backgrounded) and
  return a clear "bring Flame to the foreground" message instead of a raw
  `AttributeError`.

### Fixed — docs Flame 2027 correctness (Chat 53)

- Wiretap SDK/CLI documentation paths updated 2026.2.2 → 2027
  (python3.11 → 3.13).
- Four PySegment/PySequence API-signature errors corrected against the 2027
  graph: `is_rendered` removed from PySegment (clip-level only);
  `create_version(stereo=…)` not `name=`; `create_connection` /
  `remove_connection` take no argument; `smart_replace*` take a `PyClip`,
  not a reel.

### Changed — Flame 2027 support (Chat 52)

- Migrated the supported Flame version 2026 → **2027**. Regenerated
  `rag/api_graph.json` from a live Flame 2027 box (`flame_version: 2027`;
  72 classes / 25 functions / 10 module attrs). The 2027 Python API is a
  strict **superset** of 2026 — 5 new classes (`PyMetadataNode`,
  `PyMetadataTimelineFX`, `PyMetadataValue`, `PyNodeMarker`,
  `PyReadFileNode`) and 2 new functions (`flame.clear_graphics_memory`,
  `flame.clear_unreferenced_cache`), **zero removals** — so F4b now
  accepts 2027 symbols and no existing pattern breaks.
- Updated version strings and Autodesk doc URLs (2026 → 2027) in
  `CLAUDE.md`, the `README.md` compatibility table (2027 row now
  3.13.3 / PySide6 / Tested), and the `FLAME_API.md` header. Flame 2027
  ships Python 3.13.
- Validation: 517 tests + 36/36 concept invariants green against the 2027
  graph; live `get_flame_version` → `2027` on the bridge. **Not yet
  re-validated on 2027:** Wiretap SDK/CLI paths (docs still cite 2026.2.2)
  and the full write-op tool round-trip. Installed build is `2027.pr238`.

### Fixed — Chat 52 in-vivo validation findings

- **Name comparisons failed against real Flame.** On Flame 2026,
  `str(obj.name)` returns a single-quote-wrapped string for
  libraries/reels/clips (`'Default Library'`, not `Default Library`).
  Every name comparison (`== name`, `in HIDDEN`) therefore mismatched
  against a live bridge: hidden system libraries (`Timeline FX`,
  `Grabbed References`) leaked into `list_libraries`, and name-based
  lookups in `list_reels`, `list_clips`, `get_clip_metadata` and
  `get_source_path` always returned "not found". Normalised every
  `str(x.name)` comparison with `.strip("'")` (the convention already
  used in `FLAME_API.md`). Mock-only tests masked this because the
  mocked bridge returns clean names.

- **Bridge socket resolution trapped by stale files.** `_BRIDGE_SOCKET`
  was resolved once at import time by file *existence*, so a leftover
  socket file (e.g. `<repo>/run/flame_mcp.sock` from a prior dev
  session) hijacked the resolver even when the live bridge listened on
  `/tmp/flame_mcp.sock` — every tool returned "Cannot connect to Flame".
  Replaced with probe-on-connect (`_connect_bridge`): try each candidate
  socket by actually connecting, first that accepts wins, TCP fallback
  last. A dead socket file is now harmless. Added
  `tests/test_bridge_connect.py` (real local sockets, runs in CI).

## [1.8.0] — 2026-05-19

### Added — F5b: Ruta A — structured plan output (Issue #12, AJUSTE 1)

The deepest reliability win of the chat 51 roadmap. The LLM can now
submit a structured JSON plan via the new `execute_plan` MCP tool
instead of writing raw Python. The plan is validated against a closed
schema (each op carries a typed pydantic args model with
`extra="forbid"`). Hallucinated symbols and wrong arg shapes are
rejected at the protocol level — they never reach Flame.

- New `src/flame_mcp/_plan_schema.py` module:
  - Schema shape v1: `{"ops": [{"op": "<name>", "args": {...}}, ...]}`.
  - 6 registered ops in v1: `list_libraries`, `list_reels`,
    `list_clips`, `get_project_info`, `get_clip_metadata`, `ping`.
  - Per-op pydantic models enforce `extra="forbid"` +
    `str_strip_whitespace=True`.
  - `validate_plan(plan)` returns parsed (op_name, args_instance)
    pairs or raises `PlanValidationError` with LLM-facing message.
  - `dispatch_plan(plan)` validates then dispatches op-by-op with
    per-op headers + final summary; short-circuits on handler
    failure with the exact index reported.
  - `register_op(name, handler)` wires server-side handlers at
    import time (server.py is the only caller); raises on unknown
    name to surface typos loudly.
- New `execute_plan` MCP tool in `src/flame_mcp/server.py`:
  - Wires handlers for the 6 ops above (each delegates to its
    existing dedicated tool — F5b is a protocol change, not a
    behaviour change).
  - On schema rejection: increments `_stats['plan_ops_rejected_by_schema']`
    and returns the rejection message without touching Flame.
  - On success: increments `_stats['plan_ops_executed']` by the op
    count.
- `execute_python` is NOT deprecated. F5b co-exists. Migration path:
  observe F0 telemetry, migrate frequent `execute_python` calls into
  new plan ops, only deprecate `execute_python` once the corresponding
  plan ops are stable.
- `tests/test_plan_schema.py` — 21 unit tests covering schema
  rejection (unknown op, extra keys, missing keys, wrong types, empty
  ops, non-dict plan), args model rejection (missing required, unknown
  arg), dispatch order preservation, short-circuit on handler failure
  (subsequent ops NOT invoked), `register_op` typo detection,
  `describe_registry` JSON-serialisability, sorted `op_names`.
- `README.md` — tool count `27 → 28`, `execute_plan` added to the
  tool table.
- `CLAUDE.md` — new rule 16 with 3 worked examples for `execute_plan`.
- `.concepts.yml` — new `structured_plan_output` concept with 3
  invariants: 2 × `file_exists` (module, tests) + `every_op_is_a_tool`
  subset (op keys in `_OP_REGISTRY` ⊂ `@mcp.tool` decorator names in
  server.py). Pre-commit verifier: 36/36 (was 33/33).

Tests: 512 passed, 113 skipped, 0 failed (was 491/113).

### Changed — F6a: trim CLAUDE.md (Issue #13, AJUSTE 3 — unblocked by F3b)

- `CLAUDE.md` reduced 359 → 290 lines (~19 %, ~69 lines / ~4.8 KB
  removed). Operator-only sections moved out so the LLM system prompt
  no longer carries content the LLM never acts on.
- New `docs/DEPLOY.md` — receives the relocated content:
  - "Prerequisites for local models" (Ollama install + alias setup).
  - "Deploy workflow — after every code change" section (symlink
    setup, `pkill` + `cp` recipes per file, **MCP Bridge → Reload
    hook** step). Two paths (with-symlink / fresh-machine fallback).
- `CLAUDE.md` retains a 2-line pointer to `docs/DEPLOY.md` so the
  operator can find the workflow when reading the prompt-facing file.
- `CLAUDE.md` also drops the "## Community" subsection (Logik Forum
  + Autodesk Community URLs) — not actionable for the LLM, and the
  URLs remain searchable when needed.
- `.concepts.yml` gains a `claude_md_trim` concept with 3 invariants:
  1 × `file_exists` (`docs/DEPLOY.md`) + 2 × `claim_verifies` that
  re-expansion of `CLAUDE.md` cannot re-introduce the deploy section
  heading or the embedded shell commands. Pre-commit verifier: 33/33
  (was 30/30 after F4b).

### AJUSTE 3 gate

The trim was blocked until F3b shipped ≥ 10 adversarial entries
(`scripts/check_adversarial_count.py`) so the LLM-facing API trap
warnings now have an executable defense via the golden routing
dataset. Current state: 16 adversarial ≥ 10 required ✓.

Token impact (rough): ~1200 fewer tokens per LLM turn that loads the
system prompt. Strictly Pareto — no LLM behavioural rule was modified,
only operator-facing text relocated.

Tests: 491 passed, 113 skipped, 0 failed (golden suite unchanged).

### Added — F4b: AST dry-run walker (Issue #11)

- New `src/flame_mcp/_ast_validate.py` module — static validator that
  walks the AST of any source about to be sent to `execute_python` and
  flags `flame.X.Y` references that do not exist in `rag/api_graph.json`
  (the introspected truth from F2-intro).
  - `validate_python(source, graph=None)` returns an `AstValidation`
    dataclass with `issues: list[UnresolvedSymbol]` and `graph_loaded`
    flag (False when the graph file is missing or empty → walker
    degrades to a no-op, never blocks legitimate code).
  - `UnresolvedSymbol` carries the dotted path, line/col, and an
    optional `suggestion` from `difflib.get_close_matches`.
  - `format_issues(validation)` returns a human-readable rejection
    message with each symbol's position, suggestion, and the
    `ast_dry_run: false` config escape hatch.
- `src/flame_mcp/server.py::execute_python` runs the walker as
  pre-flight when `config.json -> ast_dry_run` is true (default).
  On rejection, returns the formatted message + footer WITHOUT
  touching the bridge and increments `_stats['ast_dry_run_rejected']`.
- `tests/test_ast_validate.py` — 15 unit tests: missing-graph and
  malformed-JSON degradation, graph-symbols flatten, happy-path
  acceptance (including prefix-resolved chains so legitimate
  `flame.batch.render` calls inside `schedule_idle_event` are NOT
  rejected), hallucinated-symbol rejection (`flame.selection`,
  `flame.foo_bar_baz`), close-match suggestion, multi-issue
  collection, syntax-error silence (let the bridge surface it),
  non-`flame.*` chain ignored, `format_issues` formatting.
- `.concepts.yml` gains an `ast_dry_run_validator` concept with 3
  invariants: 2 × `file_exists` (module, tests) + 1 × `subset` pinning
  the validator import in server.py. Pre-commit verifier: 30/30
  (was 27/27).

What F4b CAN and CANNOT catch (documented in module docstring):

- CAN catch: `flame.selection` (non-existent), `flame.foo_bar_baz`
  (invented), method typos on known classes.
- CANNOT catch: usage traps where the symbol IS valid but the call
  pattern is wrong (e.g. `flame.batch.render` without
  `schedule_idle_event`). Those are F3b's golden adversarial dataset's
  scope, enforced at the routing layer.

Tests: 491 passed, 113 skipped, 0 failed (was 476/113).

### Added — F4a: workspace snapshot with TTL 12s + write-invalidation (Issue #10, AJUSTE 2)

- New `src/flame_mcp/_workspace_snapshot.py` module — thread-safe,
  per-process cache for workspace read tools.
  - `get(key, ttl=12.0)` / `set_value(key, value)` — monotonic-clock
    TTL store. Lazy GC on stale entries.
  - `invalidate(prefix=None)` — drop by key prefix (or all). Returns
    count dropped.
  - `cache_workspace_read(ttl=12.0)` — decorator wrapper for MCP tool
    bodies. Caches keyed by `__name__` + positional args + sorted
    kwargs. Skips function body on hit (no socket round-trip, no
    `_stats` inflation). Exceptions are NOT cached.
- `src/flame_mcp/server.py` — 7 read tools now decorated with
  `@_cache_workspace_read()`: `get_project_info`, `list_libraries`,
  `list_reels`, `list_clips`, `list_desktop_reels`, `list_batch_groups`,
  `list_all_projects`. `execute_python` calls
  `_workspace_invalidate(_WORKSPACE_PREFIX)` after every exec
  (success or failure — partial mutations on error are still
  mutations). This is **AJUSTE 2** of the chat 51 v2 plan: TTL alone
  was insufficient because a post-delete read within TTL would have
  served the pre-delete view.
- `tests/test_workspace_snapshot.py` — 14 unit tests: get/set, TTL
  expiry (monotonic-clock injected via monkeypatch — no `time.sleep`,
  suite stays < 100 ms), invalidate prefix vs all, decorator caches
  by arg tuple, decorator does not cache exceptions, decorator
  respects custom TTL, decorator invalidation forces refresh, 2-thread
  concurrent-read smoke test.
- `.concepts.yml` gains a `workspace_snapshot_cache` concept with 3
  invariants: 2 × `file_exists` (module, tests) + 1 × `subset` pinning
  the `_workspace_invalidate(_WORKSPACE_PREFIX)` call in server.py
  against the `def invalidate` declaration. Pre-commit verifier:
  27/27 (was 24/24).

Tests: 476 passed, 113 skipped, 0 failed (was 462/113).

### Added — F3a: concept_map bypass via api_graph.json (Issue #9)

- New `src/flame_mcp/routing.py` module with two functions:
  - `_route_from_graph(query, graph=None)` searches the introspected
    `rag/api_graph.json` (produced by F2-intro) for the best match,
    returning a concept-shaped dict with `_provenance="graph"`. **Safety
    filter**: any matched entry whose introspector-attached `notes` list
    is non-empty (trap hints like `schedule_idle_event`, `.clear()`
    crash) is refused — function returns `None` so the LLM falls
    through to RAG (which has the curated docs). A small
    `_FORBIDDEN_API_PATHS` allowlist also short-circuits known
    non-existent symbols (`flame.selection`,
    `flame.projects.current_project.libraries`).
  - `resolve_query(query, graph=None)` is the dual-source chain:
    `resolve_concept` (curated, low-latency) → `_route_from_graph`
    (introspected, broader). Every non-None result carries a
    `_provenance` field (`"concept_map"` | `"graph"`) for telemetry.
- `src/flame_mcp/server.py::resolve_concept` MCP tool now delegates to
  `routing.resolve_query` so the LLM-facing tool transparently benefits
  from graph fallback. Response surfaces `Source: <provenance>` line.
- `tests/test_routing.py` — 15 unit tests covering safe-symbol
  surfacing, trap-flagged refusal, missing-file degradation, malformed
  JSON, cache behaviour, and the `resolve_concept → _route_from_graph`
  chain with `_provenance` propagation.
- `tests/fixtures/api_graph_sample.json` — small hermetic graph
  fixture (3 functions, 2 classes with methods, trap notes on
  `PyBatch.render` and `PyClip.clear`) so the tests work in CI where
  the real graph is not generated.
- `tests/test_golden.py` switches its import from `resolve_concept`
  to `routing.resolve_query` (aliased) so the F3b adversarial suite now
  exercises the full chain. All 16 adversarial entries still fail
  `must_not_contain` (no regression). All 48 happy-path entries
  continue to resolve via `concept_map` (no expected_tool change).
- `.concepts.yml` gains a new `dual_source_routing` concept with 4
  invariants: 3 × `file_exists` (routing.py, fixture, tests) plus a
  `subset` invariant pinning the `from flame_mcp.routing import
  resolve_query` import in server.py against the `def resolve_query`
  declaration. Pre-commit verifier: 24/24 (was 20/20).

Tests: 462 passed, 113 skipped, 0 failed (was 447/113).

## [1.7.0] — 2026-05-18

### Added — Chat 51 performance + reliability plan (6 phases F0–F3b)

- **F0 — Baseline telemetry** (PR #3). New `_session_stats.py` helpers
  `persist_timing` / `persist_turn` write append-only JSONL to
  `logs/timings.jsonl` (per-call) and `logs/turns.jsonl` (per-turn) with
  ~5 MB size-cap rotation to `.1`. New counters `turns_total` and
  `failed_turns` enable `p_fallo = failed_turns / turns_total` as a
  cross-session reliability metric. Server-side `_track_timing` enriches
  each entry with `ts`, `model`, `backend`, `tool_name`, `score`,
  `error`. Bridge-side `_agent_loop` writes one turn row per invocation
  from the outer `finally` so timeouts and early-exits are still
  captured. `.gitignore` extended to cover `*.jsonl` and `*.jsonl.1`.
  Tests +9 (209/209). Concept verifier: 20/20.

- **F1a — `_stats_footer` modes** (PR #4, AJUSTE 4). `_stats_footer(mode)`
  accepts `none` / `minimal` / `full`, default `minimal` reads from
  `config.json -> stats_footer_mode`. `minimal` returns `""` (per-call
  timing already lives in the `execute_python` preamble), `full` restores
  the historical multi-line aggregate. Net reduction of ~80–150 tokens
  per LLM turn that uses `execute_python` or `search_flame_docs`. Tests
  +6 (27/27 in test_session_stats).

- **F1b — Ollama `keep_alive` config knob** (PR #5). New
  `src/flame_mcp/_config.py::resolve_keep_alive` helper reads
  `config.json -> ollama_keep_alive` as a duration string (`"30m"`) or
  int seconds; rejects dict/list/None/bool with default fallback.
  Default bumped 10 min → 30 min so reading-pauses between turns don't
  trigger Ollama cold-load (5–30 s penalty on 9B models). Bridge
  `_preload_ollama_model` delegates via helper with inline fallback
  (Chat 44 helper-extraction pattern). Tests +9 (19/19 in test_config).

- **F2-intro — Flame API introspector** (PR #6). New
  `scripts/introspect_flame_api.py` walks Flame's embedded `flame`
  Python module and emits structured JSON to `rag/api_graph.json` with
  module-level attributes, free functions, and classes (with methods +
  attrs). Becomes source-of-truth for downstream F3a (concept_map
  bypass), F4b (AST dry-run walker), F5b (structured plan schema).
  `--check` exits 2 with sentinel when run outside Flame. Cadence:
  regenerate per Flame major release (2026.x → 2027.x). Tests +3.

- **F2-wt — Wiretap smoke harness** (PR #7). New
  `scripts/wiretap_smoke.sh` iterates the 37 Wiretap CLI tools listed
  in `docs/wiretap_cli_reference.md`, default `--help`, hard skip for
  5 destructive tools, `timeout 5s` wrapper, captures exit + first 5
  lines stdout/stderr + ms. Emits Markdown table to
  `docs/wiretap_smoke_report.md`. Companion `scripts/wiretap_sdk_smoke.py`
  runs the SDK init→server→node→getNumChildren sequence and emits
  JSON to stdout. Both bash 3.2 / shellcheck / py_compile clean.

- **F3b — Golden routing dataset + adversarial gate** (PR #8). New
  `tests/golden/flame_queries.jsonl` with 83 curated queries (48
  happy-path, 16 adversarial, 14 Spanish fall-through) across 9
  categories. Schema: `{id, query, lang, expected_tool, expected_concept,
  must_contain[], must_not_contain[], tags[], category}`. Adversarial
  entries assert the router does NOT propose forbidden symbols
  (`flame.selection`, `flame.batch.render` without `schedule_idle_event`,
  `.clear()` on containers, etc.). Hermetic pytest runner
  `tests/test_golden.py` mocks `flame_mcp.rag.search.search` and uses
  `resolve_concept` directly. New pre-commit gate
  `scripts/check_adversarial_count.py` exits 0 iff ≥10 adversarial
  entries with non-empty `must_not_contain` — currently 16, **unblocks
  F6a** (CLAUDE.md trim).

### Added — Architecture documentation (PR #14)

- `docs/CHAT_51_PLAN.md` — 7-phase roadmap reconstructed from the six
  open PRs after the original `/ultraplan` v2 output was lost. Covers
  the expected-latency metric, the four v2 AJUSTES, and acceptance
  criteria for the five pending phases (F3a, F4a, F4b, F5b, F6a).
- `docs/ARCHITECTURE.md` extended with §§13–16: granular Mermaid
  request-flow diagrams (top-level orchestration, RAG internals,
  `execute_python` pipeline, LLM decision tree from CLAUDE.md rules);
  seven parallel self-learning loops with cross-loop properties;
  21-row pre-designed elements catalogue with origin chat per row;
  honest uniqueness analysis vs a stock MCP server. References
  renumbered §12 → §17.
- `docs/PHASE_TRACKER.md` — single-glance status table mirroring the
  six merged PRs and the five new pending-phase issues, with an
  update protocol.

### Pending — next-phase issues opened

- #9 F3a — concept_map bypass via `api_graph.json`.
- #10 F4a — workspace snapshot TTL 12 s + write-invalidation (AJUSTE 2).
- #11 F4b — AST dry-run walker.
- #12 F5b — Ruta A: structured plan output schema (AJUSTE 1).
- #13 F6a — trim CLAUDE.md (AJUSTE 3, unblocked by F3b).

## [1.6.0] — 2026-04-22

### Added
- `src/flame_mcp/suggestions.py` — `list_flame_logs → read_flame_log`
  rule. Parses the `📁 <dir> (N files)` header + indented log rows
  sorted by mtime, picks the first (most recent) log, and seeds a
  `read_flame_log` call with the standard diagnostic grep pattern
  `Error|Traceback|Exception|crash` and `lines=200`. Natural triage
  flow when the user runs `list_flame_logs` because something looked
  off. Short-circuits on "❌ Log directory not found", "❌ Error
  listing logs", and "No log files found" responses.
- `scripts/invariant_types.py` — `_write_subset` handler registered
  in WRITERS (Phase C + D, Chat 48). Covers `b_source.type:
  anchor_list` (without `item_pattern`) and `file_regex_matches`
  (with YAML opt-in `b_source.writer.line_template`). Enables
  `/propagate-change` Path A to auto-fix subset-drift without
  manual edits for the common cases.
- `.github/workflows/ci.yml` — Codecov coverage upload step
  (`codecov/codecov-action@v4`), gated to `matrix.python-version ==
  '3.12'`.

### Fixed
- `scripts/invariant_types.py` — `version_match` handler honors
  opt-in `tolerate_release_in_progress: true`. Applied to
  `.concepts.yml` on the `pyproject_matches_latest_tag` invariant to
  unblock `cut-release.sh` under strict mode.

## [1.5.0] — 2026-04-22

### Added
- `src/flame_mcp/suggestions.py` — next_suggested_actions pattern port
  (Chat 47). Text-contract variant of the fpt-mcp/maya-mcp rule engine:
  hints are appended to tool output as a visible `➡ Next you could also:`
  trailing block rather than mutating JSON. Ships with `list_libraries →
  list_reels` rule, `FLAME_MCP_DISABLE_SUGGESTIONS` kill switch, and a
  cap of 3 suggestions per response. Wired via
  `maybe_annotate_with_suggestions` in `server.py`.
- `.concepts.yml` — `next_suggested_actions_contract` concept with
  `every_rule_is_wired` invariant (ast_dict_keys `SUGGESTION_RULES` ⊂
  regex capture of `maybe_annotate_with_suggestions("<tool>", …)`
  call-sites). Pre-commit fails if a rule is registered without being
  wired at the tool level.
- `src/flame_mcp/suggestions.py` — two new chaining rules (Chat 48,
  this release): `list_reels → list_clips` (fires on no-filter responses
  with `[Library]` headers, skips hidden libs and empty reels) and
  `list_clips → get_clip_metadata` (parses `[Library] / [Reel] — N
  clip(s)` header, picks first visible clip, ignores `… and N more`
  summary lines). Completes the navigation breadcrumb
  `list_libraries → list_reels → list_clips → get_clip_metadata`. Tests
  grew from 183 to 197 (+14); invariant count 15 → 20.
- `.github/workflows/ci.yml` — GitHub Actions CI workflow. Four blocking
  jobs: pytest across Python 3.10/3.11/3.12 matrix, ruff lint, mypy,
  verify_concepts. Pytest coverage reported inline via `--cov=<pkg>
  --cov-report=term`.
- `.github/workflows/pr-review.yml` — automated Claude PR review
  (`anthropics/claude-code-action@v1`). Byte-identical across the 4
  ecosystem repos; canonical at `~/Projects/pr-review-canonical.yml`.
  Prompts Claude to audit concept-registry compliance first, then
  correctness, style, and ecosystem coherence. Uses
  `claude_code_oauth_token` (not API key) — ecosystem standard is
  Max/Pro subscription via OAuth. Requires GitHub App + workflow
  permission `id-token: write` + `--model claude-sonnet-4-6` pin so the
  OAuth token (Sonnet-scoped) works against the default-Opus action.
- `scripts/verify_concepts.py --write` — WRITER MODE (Chat 46). Requires
  the triple flag `--accept-current-as-truth --i-reviewed-diff --write`.
  Dispatches to per-type writers in `invariant_types.py::WRITERS`.
  Currently supports `tool_count` and `review_expiry`; other types
  report `WRITER UNSUPPORTED`. No auto-commit.
- `scripts/cut-release.sh` — ecosystem-shared release orchestrator.
  Validates clean tree + semver arg + non-empty `[Unreleased]`, edits
  CHANGELOG + `pyproject.toml`, commits with `CUT_RELEASE_VERSION=X.Y.Z`
  so the `changelog_tag_sync` invariant tolerates the transient
  pre-commit drift, then tags, pushes, and creates a GitHub release.
  Byte-identical across the 4 MCP-ecosystem repos.
- `scripts/invariant_types.py` — new `changelog_tag_sync` handler
  replaces the previous `subset`-based `changelog_tag_coherence`.
  Release-in-progress tolerance anchored to `CUT_RELEASE_VERSION` env
  OR `pyproject.toml`'s `version` field.
- `scripts/invariant_types.py` — `ast_dict_keys` canonical (Chat 47)
  now reads `ast.AnnAssign` in addition to `ast.Assign`, so typed-dict
  declarations like `SUGGESTION_RULES: dict[...] = {...}` resolve
  correctly. Synced byte-identical across 4 repos.
- `scripts/verify_concepts.py` — `ci_skip: true` flag on individual
  invariants + auto-skip of `review_expiry` under `GITHUB_ACTIONS`
  (Chat 47). Keeps dev-side invariants active via pre-commit while CI
  runs stay green without shipping `~/Projects/.external_versions.yml`
  or broad `gh` auth.

### Changed
- `.concepts.yml` — `strict: false → true`. The pre-commit hook now
  blocks commits on any unresolved invariant drift instead of only
  reporting it. Ecosystem-wide flip on 2026-04-20 (Chat 46), unblocked
  by the `changelog_tag_sync` release-in-progress tolerance.
- CI pipeline cleanup (Chat 47): ruff baseline cleared (all warnings
  fixed, job flipped to blocking), mypy baseline cleared (per-repo
  `[tool.mypy]` with `ignore_missing_imports=true` +
  `no_strict_optional=true`, job flipped to blocking). Both jobs now
  block merge rather than `continue-on-error: true`.

### Fixed
- `tests/test_rag_search.py` — `TestRagRealIndex` skipif guard now
  checks for `chroma.sqlite3` sentinel inside the index dir rather
  than `is_dir()` (Chat 47). A committed `.gitkeep` fooled the old
  guard in CI, causing real-index tests to attempt to run against an
  empty directory.
- `.github/workflows/pr-review.yml` — added `id-token: write` workflow
  permission (Chat 48). The action calls `getOidcToken()` during
  `setupGitHubToken`; without it the action errored with "Unable to
  get ACTIONS_ID_TOKEN_REQUEST_URL env variable" in 3 retries.
- `.github/workflows/pr-review.yml` — pinned `--model claude-sonnet-4-6`
  via `claude_args` (Chat 48). OAuth tokens from `claude setup-token`
  are scoped to Sonnet on Max/Pro; the action's default model (Opus
  after v1.0.100) returned `401 Invalid bearer token` against those
  credentials (see anthropics/claude-code-action#584).

### Documentation
- `README.md` — added a "Configuration precedence (env-var vs
  config.json)" subsection that surfaces the transport-vs-model
  asymmetry user-facing. Previously only in `docs/ARCHITECTURE.md
  §9/§11` (Chat 45 gotcha #4 closure).

## [1.4.3] - 2026-04-20

### Added
- `scripts/verify_concepts.py` — `--accept-current-as-truth` + `--i-reviewed-diff` double-flag escape hatch (REPORT MODE ONLY). When both flags are passed, the runner inspects every failing invariant and prints a human-readable "would update \<mirror\>" line describing what a hypothetical writer mode would change, then exits 0 without touching any file. Single-flag usage is rejected with exit code 2 by design — the double-flag requirement prevents accidental drift acceptance. Intended for repos that drifted while dormant and need a one-shot review before flipping `strict: true`. Writer mode is deferred to a future pass with explicit user sign-off. Chat 44 ultraplan Q5.

## [1.4.2] - 2026-04-20

### Added
- `.concepts.yml` — `github_release_per_tag` concept with the `every_v1plus_tag_has_github_release` invariant. Enforces that every `vX.Y.Z` tag (v1.0.0+) has a matching published GitHub Release; `gh release list` is the oracle. Pre-1.0 tags excluded (pre-release noise). Ecosystem-wide policy introduced in Chat 45 — now enforced per repo via the concept registry.

## [1.4.1] - 2026-04-20

### Fixed
- `hooks/flame_mcp_bridge.py` — `ollama_mac` backend now runs `_preload_ollama_model()` before spawning the claude subprocess. Without the preflight, Ollama's Anthropic-compat `/v1/messages` endpoint silently fell back to 4096 tokens on Mac-local inference even when the Modelfile declared a larger window. `_preload_ollama_model` gained optional `url` and `num_ctx` kwargs so the Mac branch can target `OLLAMA_MAC_URL` + `OLLAMA_MAC_NUM_CTX=8192`. Chat 45 / Agent D investigation.
- `.concepts.yml` — new `ollama_preflight_parity` concept with two `file_regex_matches` invariants guarding the two preflight call sites. `ollama_cloud` is deliberately excluded (cloud runners manage their own context window).

### Changed
- `scripts/invariant_types.py` + `scripts/verify_concepts.py` — synced to the ecosystem-canonical version (Chat 45 Agent F consolidation). Adds `ast_decorator_functions.name_kwarg`, `ast_enum_values`, and `ast_decorator_kwarg` (back-compat alias). Byte-identical with fpt-mcp, maya-mcp, vision3d.

## [1.4.0] - 2026-04-20

### Added
- `reset_session_stats` MCP tool (read-only) — zero the session stats counters on demand. Tool inventory 26 → 27.
- Idle-gap auto-reset: the first tool call after `stats_idle_reset_seconds` (default 30 min) of inactivity auto-zeros `_stats`. Overridable via `config.json → stats_idle_reset_seconds`.
- `.concepts.yml` invariant `stats_keys_schema_shared` locking `server.py::_stats` keys to `flame_mcp._session_stats.make_empty_stats()` so new counters cannot be added to only one side.

### Changed
- `src/flame_mcp/server.py` — `_stats` now initialised via `make_empty_stats()`; `_call_flame` and `search_flame_docs` invoke `_track_call()` on entry to drive the idle-gap reset. `_stats_reset_at` surfaced by `session_stats()` updates whenever either reset trigger fires.
- `docs/ARCHITECTURE.md` §1 — tool count 26 → 27.

## [1.3.1] - 2026-04-20

### Added
- `src/flame_mcp/_config.py` — shared `load_model_config()` helper. Canonical loader for the four widget-facing config.json keys (`model`, `backend`, `ollama_url`, `ollama_cloud_key`). Imported by the bridge via a `sys.path`-inserted bootstrap so it works even from `/opt/Autodesk/shared/python/`.
- `src/flame_mcp/_session_stats.py` — `make_empty_stats()`, `should_auto_reset()`, `apply_idle_reset()`, `reset_stats()`. Pure logic for the pending per-Claude-session `_stats` reset (server.py wiring proposed, not yet applied — see `docs/session_stats_reset.md`).
- `tests/test_config.py` (9 cases) and `tests/test_session_stats.py` (13 cases). Full suite 149 → 171.
- `docs/session_stats_reset.md` — design doc + unified-diff patch proposal for server.py and `.concepts.yml`. Follow-up `v1.4.0` will apply the patch and expose a new `reset_session_stats` MCP tool.

### Changed
- `hooks/flame_mcp_bridge.py::_load_model_config` now delegates to `flame_mcp._config.load_model_config()`. An inline fallback remains for Flame hosts deployed without the repo on disk.
- `docs/ARCHITECTURE.md` §11 — dead-code bullet retired (see *Removed*); `_load_model_config` and `_stats` bullets updated to reflect the helper landings and the pending server.py patch.

### Removed
- `src/flame_mcp/rag/generate_flame_api.py` — orphan generator. Not imported anywhere, produced an output file (`docs/flame_api_full.md`) that is absent from disk and from `rag/corpus.json`. Flagged for deletion in the Chat 44 audit (§11).
- README directory-tree illustration entry for `flame_api_full.md` (file never existed in the shipped tree).
- FLAME_API.md attribution header "Auto-generated by …" (stale — the file is curated by hand and extended at runtime by `learn_pattern`).

## [1.3.0] - 2026-04-17

### Added
- `.concepts.yml` cross-cutting concept registry with 13 machine-checkable invariants
- `scripts/verify_concepts.py` runner + `scripts/invariant_types.py` (7 invariant types, 6 source types, stdlib + PyYAML only)
- `.pre-commit-config.yaml` wiring `verify_concepts.py` to every commit via the pre-commit framework
- `docs/ARCHITECTURE.md` rewritten as ground truth from reverse-engineered source (replaces the stale 18-tools doc)
- `CLAUDE.md` rule 15 pointing future sessions at `.concepts.yml` before cross-cutting edits
- GLM-4.7 Flash documented in backend table (was implemented but undocumented)

### Changed
- README MCP-tools section updated from 18 to 26 tools (the 8 missing ones now listed: `collect_media_paths`, `create_sequence`, `get_source_path`, `get_write_node_settings`, `operation_history`, `rename_segments`, `resolve_concept`, `undo_last_operation`)
- README model selector table rewritten to match `AVAILABLE_MODELS` (removed non-existent `qwen3-coder`, `qwen2.5-coder`, Sonnet 4.5, Haiku 4.5; added GLM-4.7 Flash)
- README knowledge-base table: 7 → 14 documents, chunk counts aligned with actual `rag/corpus.json` (783)
- `hooks/flame_mcp_bridge.py`: Claude Opus 4.6 → 4.7 in `AVAILABLE_MODELS`
- `src/flame_mcp/server.py`: `WRITE_ALLOWED_MODELS` — dropped `claude-opus-4-5`, added `claude-opus-4-7`, kept forward-compatible prefixes
- `src/flame_mcp/server.py::_rating()` returns empty string for Ollama backends (token-cost warnings suppressed, matching README claim)
- `pyproject.toml` version bump 0.1.0 → 1.3.0 (catch-up release including all commits since v1.2.1)
- `install.sh` Ollama server prompts now reference `qwen3.5-mcp` and `glm-4.7-flash` instead of stale `qwen3-coder` / `qwen2.5-coder`
- `scripts/setup_ollama_linux.sh` (renamed from `setup_linux.sh`; moved to `scripts/`) VRAM tiering updated to current `AVAILABLE_MODELS`
- Modelfile setup simplified: `ollama cp qwen3.5:9b qwen3.5-mcp` instead of referencing a non-existent `Modelfile.qwen35mcp` file
- `CLAUDE.md`: retired unbacked `"think": false` claim; Modelfile section aligned with the runtime-preflight reality

### Removed
- Reference to `Modelfile.qwen35mcp` (file never existed in the repo; bridge handles `num_ctx` at runtime)

### Previously pending
- Stopped tracking `rag/index/` generated files; added `.gitkeep` placeholder
- Fixed stale `python rag/build_index.py` references to `python -m flame_mcp.rag.build_index`

## [1.2.1] - 2026-04-14

### Fixed
- Harden reasoning on Flame panel claude subprocess to prevent bridge crashes

## [1.2.0] - 2026-04-14

### Added
- Index Wiretap CLI (37 tools) and Wiretap SDK Python bindings (22 classes) in RAG

## [1.1.2] - 2026-04-14

### Fixed
- Align `INDEX_DIR` and `CORPUS_PATH` with real on-disk data layout
- Make `test_cli_not_found` deterministic by mocking `subprocess.run`

### Changed
- Rebuild RAG index after adding auto-learned sequence-from-reel pattern

## [1.1.1] - 2026-04-10

### Added
- Migrate tool pre-approval to user-level `~/.claude/settings.json` (auto-detected via `ast.parse`)

### Fixed
- Update maya-mcp entry from `core/server.py` to `-m maya_mcp.server`

### Changed
- Clean internal artifacts and translate Spanish content to English

## [1.1.0] - 2026-04-08

### Added
- In-session RAG cache (A12) consistent with maya-mcp and fpt-mcp

### Changed
- **Breaking:** Migrate to `src/flame_mcp/` package layout; extract `safety.py` as separate module
- Update all `flame_mcp_server.py` references to new `src/flame_mcp/` layout

## [1.0.0] - 2026-04-07

### Added
- Automated test suite with 62 tests covering safety, redirect, tools, and RAG
- `MODEL_STRATEGY.md` with Ollama setup, Modelfile, and `KEEP_ALIVE` config
- Ollama as optional prerequisite in README and `install.sh`

### Fixed
- Tighten redirect pattern regexes to avoid false positives

## [0.10.0] - 2026-04-07

### Added
- LLM Strategy v2: Qwen3.5-mcp as primary local model with updated `AVAILABLE_MODELS`
- `.env.example` for ecosystem consistency
- Ecosystem section with cross-repo links in README
- Timing profiling at each pipeline stage boundary (REC-001)
- Log first 200 chars of assistant response in bridge log (REC-002)
- `.mcp.json` so `claude -p` discovers MCP server (OBS-024)
- QA test plans from audit agent (Level 0-1 coverage)
- `NOTICE.md` for third-party license attributions
- Smart method-group chunking in `build_index.py`
- Phase D: YouTube transcript patterns, OCR frames, GitHub pattern fetcher

### Fixed
- Remove all legacy `~/Projects/flame-mcp` hardcoded paths from docs and bridge
- `install.sh` Python 3.11+ discovery on macOS
- Widget cwd resolution and socket path for installed hook
- Dynamic `_PROJECT_ROOT` resolution replacing 11 hardcoded paths
- Suppress structural redirects when creation intent is detected
- Three-level path resolution for project `.cfg` fallback (OBS-028)
- Root cause fixes for systemic tool-selection failure (OBS-011/013)
- Apply all Level 0 and Level 1 QA observations (OBS-002 to OBS-023)
- Remove `husky.py` (Autodesk proprietary)
- Bridge-only redirect via `# DT\n` code prefix (OBS-025)

### Changed
- Rewrite `ARCHITECTURE.md` for v0.9.0 current state
- Rebuild RAG index multiple times with improved chunking (668 chunks)

## [0.9.0] - 2026-03-09

### Added
- Hybrid BM25 + semantic search (C3)
- HyDE query expansion (C4)
- Three-level learning system (C5): trusted models auto-learn, read-only models stage for review
- Mandatory citation rule (C2)

### Changed
- Upgrade embedding model to `bge-large-en-v1.5` (C6)
- Rebuild FLAME_API.md from live Flame introspection (B7)

### Fixed
- Block `PyExporter.export()` deadlock and export hang post-mortem
- Remove personal paths and untrack `crash_recovery.json`

## [0.8.0] - 2026-03-09

### Added
- 18 MCP tools total: log reader (`list_flame_logs`, `read_flame_log`), pagination, timeout param
- `ollama_mac` backend for fully offline local inference
- `/undo` and `/undo N` chat commands for instant Flame undo
- `/wrong` and `/wrong <reason>` chat commands for correction feedback
- Warn bubble type (amber) for `ollama_mac` tool-use limitations
- Runtime config keys (B5) and RAG index validator (B6)
- Self-healing: dedicated tools warn on empty fields and prompt `learn_pattern`

### Fixed
- Model update to Sonnet 4.6 with A4/A9/A13/A14 bug fixes
- Ollama: cap agentic turns, replace `/no_think` prefix with think-block stream filtering
- Crash recovery and bridge connection rule for Ollama
- `config.json` fail-safe JSON reads in all save functions
- `get_project_info`: use `wiretap_get_metadata` XML for accurate frame rate/resolution
- Full audit: `sys` import, desktop clips, `openWorldHint`, Pydantic, `CLAUDE.md`
- Wiretap SDK section added to `FLAME_API.md`
- Crash on `lib.folders` access in `list_libraries`
- Library delete pattern: add `str()` cast and `None` default
- Filter hidden system libraries (`Timeline FX`, `Grabbed References`) from all list tools
- Strip JSON envelope leak from `tool_result` content
- `ollama_cloud`: route through local Ollama server with `:cloud` model tag

### Changed
- Recalibrate token rating thresholds (low<500, medium<2000, high>=2000)
- Suppress token warnings for Ollama backends

## [0.7.0] - 2026-03-06

### Added
- Ollama cloud API key field in the UI
- Editable Ollama server URL field in the chat widget
- Ollama local/cloud backend support in the bridge

### Fixed
- Reduce `num_ctx` 32K to 24K to keep inference on GPU
- Pre-load model via native API to force `num_ctx`
- Correct qwen3-coder model tag references
- Show server/key in combo labels; fix Ollama cloud URL; extend cloud watchdog

## [0.6.0] - 2026-03-06

### Added
- Model selector dropdown in Qt chat widget
- `ping()` tool for bridge connectivity checks
- `list_clips` and `list_desktop_reels` dedicated tools
- Auto-approve all MCP tools in `~/.claude/settings.json` via install.sh

### Fixed
- Track dedicated tool savings; fix `None` attrs; block `.startswith` on `PyAttribute`
- Enforce RAG call before every `execute_python`, no exceptions
- Remove 'when unsure' escape from `search_flame_docs` docstring

### Changed
- Simplify `ARCHITECTURE.md` Mermaid diagram for clean GitHub rendering

## [0.5.0] - 2026-03-06

### Added
- Pre-built RAG index shipped with repo (BAAI/bge-small-en-v1.5)
- Action, Color Management, Conform, Segment and Timeline API reference docs
- Official cookbook and community workflow docs for RAG enrichment
- Knowledge base documentation in README (~340 chunks)

### Fixed
- Add `ROOT` to `sys.path` so `rag.config` imports correctly when run directly

## [0.4.0] - 2026-03-06

### Changed
- Replace `all-MiniLM` with `BAAI/bge-small-en-v1.5` embedding model
- Add vocabulary doc and Ollama embeddings; fix timeline/crash patterns

## [0.1.0] - 2026-03-06

### Added
- Initial release: MCP server with `execute_python` and `search_flame_docs` tools
- Flame Python hook (`flame_mcp_bridge.py`) with Unix socket bridge
- Qt chat widget embedded in Flame
- RAG semantic search over FLAME_API.md
- Safety validator with crash-prevention patterns
- Complete reference documentation (README + PDF guide)

[Unreleased]: https://github.com/abrahamADSK/flame-mcp/compare/v1.11.1...HEAD
[1.11.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.9.3...v1.10.0
[1.9.3]: https://github.com/abrahamADSK/flame-mcp/compare/v1.9.2...v1.9.3
[1.9.2]: https://github.com/abrahamADSK/flame-mcp/compare/v1.9.1...v1.9.2
[1.9.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.4.3...v1.5.0
[1.4.3]: https://github.com/abrahamADSK/flame-mcp/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/abrahamADSK/flame-mcp/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/abrahamADSK/flame-mcp/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.10.0...v1.0.0
[0.10.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/abrahamADSK/flame-mcp/releases/tag/v0.1.0
