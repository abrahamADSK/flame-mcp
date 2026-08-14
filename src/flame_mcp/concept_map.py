"""
concept_map.py
==============
Static lookup table mapping common Flame operation concepts to their
correct API paths and recommended MCP tools.

Provides `resolve_concept(query)` — a fast fuzzy matcher that returns the
best matching concept entry (or None) WITHOUT requiring RAG search.

This is architecture item 3.1: a zero-latency concept resolver that helps
the LLM pick the right tool and API path on the first try.

No external dependencies — uses only keyword-based matching against the
concept map entries.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Concept map — each entry describes one Flame operation concept
# ---------------------------------------------------------------------------
# Fields:
#   concept   — user-facing concept name (lowercase, descriptive)
#   api_layer — which API layer handles it:
#               "python_api", "wiretap_cli", "wiretap_sdk", "dedicated_tool"
#   tool      — the recommended MCP tool to call
#   api_path  — the actual API call, code pattern, or CLI command
#   notes     — gotchas, tips, or common mistakes to avoid
# ---------------------------------------------------------------------------

CONCEPT_MAP: list[dict[str, str]] = [
    # ── Project / Workspace operations ───────────────────────────────────────
    {
        "concept": "get project info",
        "api_layer": "dedicated_tool",
        "tool": "get_project_info",
        "api_path": "flame.projects.current_project → Wiretap XML for frame_rate/resolution",
        "notes": (
            "frame_rate, width, height, bit_depth are NOT available via Python API — "
            "they return None. The dedicated tool reads them from Wiretap XML metadata."
        ),
    },
    {
        "concept": "get flame version",
        "api_layer": "dedicated_tool",
        "tool": "get_flame_version",
        "api_path": "flame.get_version()",
        "notes": "Returns version string like '2026.2.2'. No bridge state is modified.",
    },
    {
        "concept": "check bridge connection",
        "api_layer": "dedicated_tool",
        "tool": "ping",
        "api_path": "flame.get_version() via bridge socket",
        "notes": "Use ping() to check if Flame is running and the bridge is reachable.",
    },
    {
        "concept": "list all projects",
        "api_layer": "dedicated_tool",
        "tool": "list_all_projects",
        "api_path": "sw_listProjects (Stone+Wire DB) or /opt/Autodesk/project scan",
        "notes": (
            "Shows all projects on the workstation, not just the active one. "
            "Flame 2026+ uses Stone+Wire DB as authoritative source."
        ),
    },
    {
        "concept": "get current workspace",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.projects.current_project.current_workspace",
        "notes": (
            "Returns a PyWorkspace object. NEVER use flame.projects.current_project.libraries — "
            "it returns None. Always go through current_workspace."
        ),
    },

    # ── Library operations ───────────────────────────────────────────────────
    {
        "concept": "list libraries",
        "api_layer": "dedicated_tool",
        "tool": "list_libraries",
        "api_path": "ws.libraries (filtered)",
        "notes": (
            "Excludes hidden system libraries 'Timeline FX' and 'Grabbed References'. "
            "Do NOT use execute_python for this."
        ),
    },
    {
        "concept": "create library",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "ws.create_library('name')",
        "notes": "Library names must be unique within the workspace.",
    },
    {
        "concept": "delete library",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.delete(lib)",
        "notes": (
            "MANDATORY: dry-run first to show what will be deleted, then wait for "
            "user confirmation. Never call .clear() — it crashes Flame."
        ),
    },
    {
        "concept": "create folder in library",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "lib.create_folder('name')",
        "notes": "Creates a PyFolder inside a PyLibrary.",
    },
    {
        "concept": "create reel in library",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "lib.create_reel('name')",
        "notes": "Creates a PyReel inside a PyLibrary.",
    },

    # ── Reel / Clip operations ───────────────────────────────────────────────
    {
        "concept": "list reels",
        "api_layer": "dedicated_tool",
        "tool": "list_reels",
        "api_path": "lib.reels",
        "notes": "Can filter by library name. Shows clip count per reel.",
    },
    {
        "concept": "list clips",
        "api_layer": "dedicated_tool",
        "tool": "list_clips",
        "api_path": "reel.clips",
        "notes": (
            "Can filter by library and/or reel. Default limit 50 clips per reel. "
            "Use limit=0 to see all."
        ),
    },
    {
        "concept": "get clip metadata",
        "api_layer": "dedicated_tool",
        "tool": "get_clip_metadata",
        "api_path": "clip.duration, clip.frame_rate, clip.width, clip.height, ...",
        "notes": "Requires library_name, reel_name, and clip_name as arguments.",
    },
    {
        "concept": "get selected clips",
        "api_layer": "dedicated_tool",
        "tool": "get_selected_clips",
        "api_path": "flame.media_panel.selected_entries",
        "notes": (
            "CRITICAL: flame.selection does NOT exist and raises AttributeError. "
            "Always use flame.media_panel.selected_entries via this dedicated tool."
        ),
    },
    {
        "concept": "import clips",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.import_clips('/path/to/clip.mov', reel)",
        "notes": (
            "Accepts file paths, wildcards, and lists. Always call search_flame_docs "
            "before writing import code."
        ),
    },
    {
        "concept": "delete clip",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.delete(clip)",
        "notes": (
            "MANDATORY: dry-run inspection first, then user confirmation. "
            "Never call .clear() on containers."
        ),
    },
    {
        "concept": "rename clip",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "clip.name = 'NewName'",
        "notes": (
            "PyAttribute objects require str() wrapping for comparison. "
            "Assignment works directly: clip.name = 'NewName'."
        ),
    },
    {
        "concept": "create sequence",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "reel.create_sequence(name='SH010', nb_tracks=1, start_frame=1001)",
        "notes": "Creates a PySequence (timeline-based clip). Available on reel, library, or folder.",
    },

    # ── Desktop operations ───────────────────────────────────────────────────
    {
        "concept": "list desktop reels",
        "api_layer": "dedicated_tool",
        "tool": "list_desktop_reels",
        "api_path": "ws.desktop.reel_groups → reels → clips",
        "notes": "Returns full desktop structure: reel groups, reels, and clip names in one call.",
    },
    {
        "concept": "list batch groups",
        "api_layer": "dedicated_tool",
        "tool": "list_batch_groups",
        "api_path": "ws.desktop.batch_groups",
        "notes": "Batch groups live alongside reel groups on the desktop.",
    },
    {
        "concept": "create batch group",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "desktop.create_batch_group('name', reels=['Input', 'Output'])",
        "notes": "Creates a new batch group on the desktop with specified reels.",
    },
    {
        "concept": "create reel group on desktop",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "desktop.create_reel_group('name')",
        "notes": "Reel groups are containers for reels on the desktop.",
    },
    {
        "concept": "save desktop",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "ws.desktop.save()",
        "notes": "Saves the desktop to the location defined by its destination attribute.",
    },

    # ── Batch / Rendering operations ─────────────────────────────────────────
    {
        "concept": "render batch",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.schedule_idle_event(lambda: flame.batch.render(render_option='Background Reactor'))",
        "notes": (
            "NEVER call flame.batch.render() directly — it blocks/crashes Flame. "
            "ALWAYS wrap in schedule_idle_event. Use 'Background Reactor' by default."
        ),
    },
    {
        "concept": "render clip timeline",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "clip.render(render_option='Background Reactor')",
        "notes": (
            "Renders timeline FX on a clip. Wrap in schedule_idle_event for safety. "
            "render_mode can be 'All', render_quality 'Full Resolution'."
        ),
    },
    {
        "concept": "export clip",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.schedule_idle_event(lambda: PyExporter().export(sources, preset, output_dir))",
        "notes": (
            "NEVER call PyExporter().export() directly — blocks main thread. "
            "ALWAYS wrap in schedule_idle_event. STOP after 'Export scheduled' — "
            "do NOT poll or re-export."
        ),
    },

    # ── Timeline operations ──────────────────────────────────────────────────
    {
        "concept": "open sequence in timeline",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "seq.open()",
        "notes": "Opens a PySequence in the timeline editor.",
    },
    {
        "concept": "get current timeline segment",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.timeline.current_segment",
        "notes": "Returns the PySegment currently focused on the timeline.",
    },
    {
        "concept": "add timeline fx to segment",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "segment.create_effect('effect_type')",
        "notes": (
            "Use segment.effect_types() to list available FX types. "
            "Returns a PyTimelineFX object."
        ),
    },
    {
        "concept": "cut clip at timecode",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "clip.cut(PyTime)",
        "notes": "Cuts all tracks at the specified PyTime position.",
    },
    {
        "concept": "insert clip into sequence",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "seq.insert(source_clip, insert_time=PyTime, destination_track=track)",
        "notes": "Inserts a source clip into the sequence at the given time/track.",
    },
    {
        "concept": "overwrite clip in sequence",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "seq.overwrite(source_clip, overwrite_time=PyTime, destination_track=track)",
        "notes": "Overwrites content in the sequence timeline at the given position.",
    },
    {
        "concept": "trim segment head or tail",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "segment.trim_head(offset, ripple=False) / segment.trim_tail(offset, ripple=False)",
        "notes": "offset is in frames. Set ripple=True to close the gap.",
    },

    # ── Wiretap operations ───────────────────────────────────────────────────
    {
        "concept": "browse wiretap tree",
        "api_layer": "dedicated_tool",
        "tool": "flame_wiretap_tree",
        "api_path": "wiretap_print_tree -h localhost:IFFFS -n <path>",
        "notes": (
            "Runs CLI tool via subprocess — no Flame bridge needed. "
            "Useful for exploring raw IFFFS node hierarchy."
        ),
    },
    {
        "concept": "get wiretap node id",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "obj.get_wiretap_node_id()",
        "notes": (
            "Only works on objects in the Media Panel (PyArchiveEntry subclasses). "
            "Use flame.find_by_wiretap_node_id(id) for the reverse lookup."
        ),
    },
    {
        "concept": "get wiretap metadata xml",
        "api_layer": "wiretap_cli",
        "tool": "execute_python",
        "api_path": "wiretap_get_metadata -h localhost:IFFFS -n <node_id> -s XML",
        "notes": (
            "Retrieves raw XML metadata from Wiretap for a given node. "
            "Run via subprocess inside execute_python. Used for frame_rate, resolution, etc."
        ),
    },

    # ── Log / Debug operations ───────────────────────────────────────────────
    {
        "concept": "list flame logs",
        "api_layer": "dedicated_tool",
        "tool": "list_flame_logs",
        "api_path": "/opt/Autodesk/logs directory listing",
        "notes": "Shows log files with size and modification time. No bridge needed.",
    },
    {
        "concept": "read flame log",
        "api_layer": "dedicated_tool",
        "tool": "read_flame_log",
        "api_path": "tail + optional grep on /opt/Autodesk/logs/<name>",
        "notes": (
            "Reads last N lines with optional regex filter. Works even when Flame "
            "is crashed. Use for debugging errors and crashes."
        ),
    },
    {
        "concept": "search flame documentation",
        "api_layer": "dedicated_tool",
        "tool": "search_flame_docs",
        "api_path": "RAG vector search over FLAME_API.md index",
        "notes": (
            "MANDATORY before every execute_python call. Returns relevant API "
            "sections with relevance scores."
        ),
    },
    {
        "concept": "learn new api pattern",
        "api_layer": "dedicated_tool",
        "tool": "learn_pattern",
        "api_path": "Appends to FLAME_API.md + rebuilds RAG index",
        "notes": (
            "Call after successful execute_python when RAG score was < 60%. "
            "Only trusted models (Sonnet/Opus) can write to FLAME_API.md."
        ),
    },
    {
        "concept": "session statistics",
        "api_layer": "dedicated_tool",
        "tool": "session_stats",
        "api_path": "Internal token tracking counters",
        "notes": "Shows exec calls, RAG calls, tokens used/saved. No side effects.",
    },

    # ── Flame Object Model — entity hierarchy ──────────────────────────────
    # These entries describe Flame's Python API entity types, their access
    # paths from the hierarchy, and key methods/behaviors.  They complement
    # the operation entries above: operations say "what to do", entity entries
    # say "what things are and how to reach them."
    {
        "concept": "flame entity: Project",
        "api_layer": "python_api",
        "entity_type": "Project",
        "tool": "get_project_info",
        "api_path": "flame.projects.current_project",
        "notes": (
            "Properties: .name, .nickname, .current_workspace. "
            "flame.projects is NOT iterable and NOT subscriptable — "
            "only .current_project is accessible."
        ),
    },
    {
        "concept": "flame entity: Workspace",
        "api_layer": "python_api",
        "entity_type": "Workspace",
        "tool": "execute_python",
        "api_path": "project.current_workspace",
        "notes": (
            "Properties: .libraries, .desktop. "
            "The workspace is the entry point to all media and desktop structures. "
            "NEVER access libraries via project.libraries (returns None)."
        ),
    },
    {
        "concept": "flame entity: Library",
        "api_layer": "python_api",
        "entity_type": "Library",
        "tool": "list_libraries",
        "api_path": "workspace.libraries[i]",
        "notes": (
            "Properties: .name (PyAttribute — use str()), .reels. "
            "NOT name-subscriptable — use index access or iterate. "
            "Filter out hidden system libraries: 'Timeline FX', 'Grabbed References'."
        ),
    },
    {
        "concept": "flame entity: Reel",
        "api_layer": "python_api",
        "entity_type": "Reel",
        "tool": "list_reels",
        "api_path": "library.reels[i]",
        "notes": (
            "Properties: .name (PyAttribute — use str()), .clips. "
            "NOT name-subscriptable — iterate and filter by str(name)."
        ),
    },
    {
        "concept": "flame entity: Clip",
        "api_layer": "python_api",
        "entity_type": "Clip",
        "tool": "list_clips",
        "api_path": "reel.clips[i]",
        "notes": (
            "Properties: .name (PyAttribute — use str()), .duration, .width, .height, "
            ".versions. Name returns PyAttribute object, NOT a plain string — "
            "clip.name == 'shot_01' is ALWAYS False. Use str(clip.name) == 'shot_01'."
        ),
    },
    {
        "concept": "flame entity: Desktop",
        "api_layer": "python_api",
        "entity_type": "Desktop",
        "tool": "list_desktop_reels",
        "api_path": "workspace.desktop",
        "notes": (
            "Properties: .reel_groups, .width, .height. "
            "The desktop is the visual workspace area in Flame. "
            "Contains reel groups (which contain reels) and batch groups."
        ),
    },
    {
        "concept": "flame entity: ReelGroup",
        "api_layer": "python_api",
        "entity_type": "ReelGroup",
        "tool": "list_desktop_reels",
        "api_path": "desktop.reel_groups[i]",
        "notes": (
            "Properties: .name, .reels. "
            "A ReelGroup is a visual container on the Desktop that holds Reels."
        ),
    },
    {
        "concept": "flame entity: BatchGroup",
        "api_layer": "python_api",
        "entity_type": "BatchGroup",
        "tool": "list_batch_groups",
        "api_path": "desktop.batch_groups[i]",
        "notes": (
            "Properties: .name, .nodes, .reels. "
            "Contains Batch nodes (compositing graph). "
            "Rendering MUST use flame.schedule_idle_event() — never call "
            "flame.batch.render() directly."
        ),
    },
    {
        "concept": "flame entity: Node",
        "api_layer": "python_api",
        "entity_type": "Node",
        "tool": "execute_python",
        "api_path": "batch_group.nodes[i]",
        "notes": (
            "Properties: .name (PyAttribute — use str()), .type, .attributes, "
            ".sockets, .input_sockets, .output_sockets. "
            "Common node types: 'Write File', 'Read File', 'Action', 'Resize'."
        ),
    },
    {
        "concept": "flame entity: Sequence",
        "api_layer": "python_api",
        "entity_type": "Sequence",
        "tool": "execute_python",
        "api_path": "clip (via timeline) or reel.sequences[i]",
        "notes": (
            "Properties: .versions, .current_version. "
            "A Sequence contains Versions, each with Tracks and Segments. "
            "Export/render MUST use flame.schedule_idle_event()."
        ),
    },
    {
        "concept": "flame entity: Segment",
        "api_layer": "python_api",
        "entity_type": "Segment",
        "tool": "execute_python",
        "api_path": "sequence.versions[v].tracks[t].segments[s]",
        "notes": (
            "Properties: .name, .record_in, .record_out, .record_duration, "
            ".source_in, .source_out, .file_path. "
            "Deep in the hierarchy: Sequence → Version → Track → Segment."
        ),
    },
    {
        "concept": "flame entity: Selected items",
        "api_layer": "dedicated_tool",
        "entity_type": "Selection",
        "tool": "get_selected_clips",
        "api_path": "flame.media_panel.selected_entries",
        "notes": (
            "Returns a list of mixed types (clips, sequences, reels). "
            "CRITICAL: flame.selection does NOT exist — raises AttributeError. "
            "Always use flame.media_panel.selected_entries or the dedicated tool."
        ),
    },

    # ── Common mistakes / gotchas ────────────────────────────────────────────
    {
        "concept": "flame.selection does not exist",
        "api_layer": "dedicated_tool",
        "tool": "get_selected_clips",
        "api_path": "flame.media_panel.selected_entries",
        "notes": (
            "flame.selection is a HALLUCINATION — it does not exist and raises "
            "AttributeError. Use flame.media_panel.selected_entries instead, "
            "or better yet, use the get_selected_clips dedicated tool."
        ),
    },
    {
        "concept": "project.libraries returns none",
        "api_layer": "dedicated_tool",
        "tool": "list_libraries",
        "api_path": "ws.libraries (via current_workspace)",
        "notes": (
            "flame.projects.current_project.libraries returns None. "
            "ALWAYS use flame.projects.current_project.current_workspace.libraries."
        ),
    },
    {
        "concept": "flame.batch.render crashes flame",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "flame.schedule_idle_event(render_fn)",
        "notes": (
            "Direct flame.batch.render() blocks the main thread and freezes Flame. "
            "ALWAYS wrap in schedule_idle_event. Same applies to PyExporter.export()."
        ),
    },
    {
        "concept": "pyattribute string comparison",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "str(obj.name) == 'value'",
        "notes": (
            "Flame attributes return PyAttribute objects, NOT plain strings. "
            "reel.name == 'Reel 1' is ALWAYS False. Use str(reel.name) == 'Reel 1'."
        ),
    },
    {
        "concept": "hidden system libraries",
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": "HIDDEN = {'Timeline FX', 'Grabbed References'}; [l for l in ws.libraries if str(l.name) not in HIDDEN]",
        "notes": (
            "ws.libraries includes two internal libraries NOT visible in the UI: "
            "'Timeline FX' and 'Grabbed References'. Always filter them out."
        ),
    },
    {
        "concept": "iterate flame projects crashes",
        "api_layer": "dedicated_tool",
        "tool": "list_all_projects",
        "api_path": "sw_listProjects or os.listdir('/opt/Autodesk/project')",
        "notes": (
            "len(flame.projects) and for x in flame.projects both crash — "
            "PyProjectSelector is NOT iterable. Use the list_all_projects dedicated tool."
        ),
    },
    # ── Pipeline workflows (span flame-mcp AND fpt-mcp) ──────────────────────
    #
    # These two entries carry a multi-step ``recipe``. That field is
    # DELIBERATELY not scored (see _score_entry): a long procedure mentions
    # many tool names, and scoring it would let a workflow entry outrank the
    # single-operation concepts those names belong to. Keep concept/tool/
    # api_path/notes short and distinctive here; put the procedure in recipe.
    {
        "concept": "fpt link",
        "api_layer": "dedicated_tool",
        "tool": "fpt_link",
        "api_path": "fpt_link(action='get')",
        "notes": (
            "Resolve this BEFORE any ShotGrid query. Never fall back to a "
            "configured default."
        ),
        "recipe": (
            "This console launches with NO ShotGrid project scope, on purpose "
            "(zero silent defaults), so ShotGrid queries span the whole site "
            "until you supply a project filter yourself.\n"
            "1) fpt_link(action='get') returns the linked FPT project NAME "
            "(read from the loaded Flame project; '' means not linked).\n"
            "2) Resolve that name to an id: sg_find on 'Project' filtered by "
            "name, with add_project_filter=false.\n"
            "3) Put that project explicitly in EVERY later ShotGrid query.\n"
            "The Flame and FPT project names are routinely DIFFERENT — that is "
            "not a mismatch, the native link is what pairs them. Never report "
            "one as a problem."
        ),
    },
    {
        "concept": "build comp expand multilayer compose shadow light layers",
        "api_layer": "python_api",
        "tool": "execute_python via schedule_idle_event (batch wiring recipe)",
        "api_path": "see recipe",
        "notes": (
            "Batch state is UI-backed: EVERY batch operation — creation, "
            "wiring, and node-list READS — runs on Flame's main thread via "
            "schedule_idle_event with a file-polled result. A worker-thread "
            "node drill killed Flame in-vivo (Chat 98)."
        ),
        "recipe": (
            "Comp build for a relit shot. Operator commands this recipe "
            "answers: 'expand multilayer node' and 'compose shadow and light "
            "layers'. Work ONE shot at a time — the demo records a single "
            "shot; the rest are for testing.\n"
            "THREADING (non-negotiable): every batch call — create_node, "
            "connect_nodes, import_clip, and even reading node lists or "
            "sockets — executes INSIDE a function passed to "
            "flame.schedule_idle_event, writing its result to a /tmp file "
            "the caller polls (~15 s budget). Follow the KB render/delete "
            "pattern. Never touch flame.batch from the exec thread directly.\n"
            "0) The shot's batch group already holds its source Clip node "
            "(the shot's open clip). Resolve it with flame.batch.get_node or "
            "by iterating batch.nodes — inside the idle event.\n"
            "1) EXPAND MULTILAYER: read the source Clip node's "
            "output_sockets (idle event) and report them. The multichannel "
            "EXR presents one output socket per layer. Identify:\n"
            "   - 'Beauty' (or the first/default socket) — the comp base;\n"
            "   - the SHADOW layer: socket named like 'shadow_mult' "
            "(operator may say shadow_multi);\n"
            "   - the MATTE: 'charmatte' — used INVERTED as the shadow "
            "comp's matte (remember it includes props, not only "
            "characters);\n"
            "   - the LIGHT layers: every socket whose name contains 'Light' "
            "or 'light' (each shot names its lights differently), PLUS the "
            "club discs: sockets containing 'disco' — note 'disco' and "
            "'disco y beam' are DISTINCT layers, take both;\n"
            "   - ignore 'rest' and anything unmatched, and LIST what was "
            "ignored so the operator can veto.\n"
            "2) SHADOW FIRST: create a Comp node (node_type must come from "
            "flame.batch.node_types), blend mode MULTIPLY. Wire beauty -> "
            "back input, shadow layer -> front, charmatte -> matte input, "
            "INVERTED. Read the Comp node's attributes to find the blend-"
            "mode and matte-invert attribute names — set invert on the node "
            "if it exists, otherwise route charmatte through a Negative/"
            "Invert node (check node_types for the exact name) before the "
            "matte input.\n"
            "3) LIGHTS IN CASCADE: one Comp node per light/disco layer, "
            "blend mode SCREEN, chained — previous result -> back, the "
            "light layer -> front. Order: lights first, club beams LAST "
            "(the review-mov formula: beauty x shadow, then lights, beams "
            "after).\n"
            "4) connect_nodes signature (verified on the 2027 graph): "
            "flame.batch.connect_nodes(output_node, output_socket_name, "
            "input_node, input_socket_name). Socket names come from step 1 "
            "— never guess them.\n"
            "5) STOP after wiring: show the operator the graph summary "
            "(nodes + connections) and let HIM hook the Write File node — "
            "its 'Create Open Clip' check is demo material, not automation. "
            "Do not create or configure the Write File."
        ),
    },
    {
        "concept": "conform cut",
        "api_layer": "dedicated_tool",
        "tool": "conform recipe (spans fpt-mcp and flame-mcp)",
        "api_path": "see recipe",
        "notes": (
            "Present the whole plan and wait for confirmation before building "
            "anything in Flame."
        ),
        "recipe": (
            "ASK THE USER AT MOST ONCE. Everything below is already decided; "
            "the only legitimate question is an ambiguity the DATA raises (a "
            "shot with several candidate Tasks, a missing publish). Gather all "
            "of those, ask them in ONE message, then execute to the end. Do not "
            "re-confirm decisions the recipe already makes.\n"
            "0) Resolve the FPT project first — see the 'fpt link' concept.\n"
            "1) Find the Cut with the highest revision_number, and its CutItems "
            "ordered by cut_order, each carrying its shot and edit_in.\n"
            "2) One open clip per shot with openclip_create.\n"
            "   2a) Call it WITHOUT task_id/step FIRST, on one shot. It returns "
            "choice_required with the shot's candidate Tasks AND a 'suggested' "
            "one derived from the Task graph (upstream_tasks). If a suggestion "
            "comes back, propose THAT and ask for a single yes — never open with "
            "'which step do you want?', the pipeline already knows.\n"
            "   2b) Output path: try the Toolkit template 'flame_shot_clip'. If "
            "the project has no PipelineConfiguration the template cannot "
            "resolve — do NOT invent a directory and do NOT drop the clip beside "
            "the media (the Open Clip docs forbid it). Build the path the "
            "template itself defines, under the project root the publishes "
            "already reveal: <root>/sequences/<Sequence>/<Shot>/finishing/clip/"
            "<Shot>.clip\n"
            "   2c) GATE — every .clip must EXIST on disk before anything is "
            "created in Flame. Check each openclip_create result for its "
            "clip_path and treat a missing or failed clip as a full stop: "
            "report it and end the turn. Building libraries first and clips "
            "later (or around a failure) leaves empty structure that has to be "
            "deleted BY HAND — structural deletes from the console deadlock "
            "Flame 2027.\n"
            "3) Organise by Sequence: a library per Sequence, each with ONE "
            "reel named 'sources' — never name the reel after its library, "
            "that reads as a duplicated hierarchy. Import each shot's .clip "
            "into its sequence's 'sources' reel, and rename the clip to its "
            "shot name BEFORE it enters any timeline (renaming only works on a "
            "clip inside a reel).\n"
            "4) ONE master sequence for the whole Cut — not one per Sequence. "
            "The per-Sequence libraries of step 3 are staging; the timeline is a "
            "single sequence at the Cut's full duration, assembled from all of "
            "them. Create it in a library named 'Conform' with a reel named "
            "'master'; the SEQUENCE carries the Cut's name. Then place each "
            "shot at its CutItem position. The sequence frame is ONE-based while "
            "CutItem edit_in is ZERO-based: pass edit_in + 1. Mixing them cost "
            "one frame in-vivo.\n"
            "   4a) A library-stored sequence is read-only for timeline edits. "
            "Pass to_desktop=true on the FIRST edit: that is the decided "
            "behaviour for a conform, not a question. Later edits find the "
            "sequence on the desktop by themselves.\n"
            "GOTCHAS: no tool imports an EDL into Flame — never plan a native "
            "EDL conform, and never ask whether to produce one; cut_to_edl makes "
            "an EDL as a separate deliverable, on explicit request only."
        ),
    },
]

# ---------------------------------------------------------------------------
# Critical API behaviors — structured reference block
# ---------------------------------------------------------------------------
# These are the most common traps in Flame's Python API.  The resolve_concept
# tool appends relevant behaviors when the matched entry has an entity_type
# that appears in a behavior's applies_to list.

CRITICAL_BEHAVIORS: list[dict] = [
    {
        "id": "str_wrap",
        "summary": "Name attributes are NOT strings — wrap with str()",
        "applies_to": ["Clip", "Reel", "Library", "Node"],
        "example": "name = str(clip.name)  # NOT clip.name directly",
    },
    {
        "id": "projects_not_iterable",
        "summary": "flame.projects is NOT iterable, NOT subscriptable",
        "applies_to": ["Project"],
        "example": "project = flame.projects.current_project  # NOT flame.projects[0]",
    },
    {
        "id": "no_name_subscript",
        "summary": "Collections are index-accessible but NOT name-subscriptable",
        "applies_to": ["Library", "Reel"],
        "example": "lib = workspace.libraries[0]  # NOT workspace.libraries['MyLib']",
    },
    {
        "id": "schedule_idle_event",
        "summary": "All export/render MUST use flame.schedule_idle_event()",
        "applies_to": ["Clip", "Sequence", "BatchGroup"],
        "example": "flame.schedule_idle_event(do_export)  # NOT do_export() directly",
    },
]


# Required keys for validation
_REQUIRED_KEYS = frozenset({"concept", "api_layer", "tool", "api_path", "notes"})

# Pre-compiled word tokenizer (splits on non-alphanumeric)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from a string."""
    return set(_WORD_RE.findall(text.lower()))


def _score_entry(query_tokens: set[str], entry: dict) -> float:
    """
    Score a concept map entry against query tokens.

    Uses a weighted keyword overlap approach:
      - concept field:  weight 3.0 (primary match surface)
      - api_path field: weight 1.5
      - notes field:    weight 1.0
      - tool field:     weight 2.0

    The optional ``recipe`` field is NOT scored. A multi-step procedure names
    many tools, and scoring it would let a workflow entry outrank the
    single-operation concepts those names belong to (measured: the conform
    recipe stole "import clips" from its own entry).

    Includes a precision bonus for the concept field: when the query
    covers a higher fraction of the concept's tokens, the entry is
    considered a tighter match (e.g. "list reels" scores higher against
    "list reels" than against "list desktop reels").

    Returns a float score >= 0. Higher is better.
    """
    score = 0.0

    concept_tokens = _tokenize(entry["concept"])
    api_tokens = _tokenize(entry["api_path"])
    notes_tokens = _tokenize(entry["notes"])
    tool_tokens = _tokenize(entry["tool"])

    # Count matching tokens per field, weighted
    concept_hits = len(query_tokens & concept_tokens)
    api_hits = len(query_tokens & api_tokens)
    notes_hits = len(query_tokens & notes_tokens)
    tool_hits = len(query_tokens & tool_tokens)

    score += concept_hits * 3.0
    score += api_hits * 1.5
    score += notes_hits * 1.0
    score += tool_hits * 2.0

    # Precision bonus: reward entries whose concept field is well-covered
    # by the query. "list reels" (2/2 = 1.0) beats "list desktop reels"
    # (2/3 = 0.67) for query "list reels".
    if concept_tokens and concept_hits > 0:
        precision = concept_hits / len(concept_tokens)
        score += precision * 3.0

    # Bonus: if ALL query tokens are found somewhere in the entry, add a boost
    all_entry_tokens = concept_tokens | api_tokens | notes_tokens | tool_tokens
    if query_tokens and query_tokens.issubset(all_entry_tokens):
        score += 2.0

    return score


def resolve_concept(query: str) -> Optional[dict]:
    """
    Fuzzy-match a user query against the concept map.

    Uses keyword-based scoring to find the best matching entry.
    Returns the best match as a dict, or None if no meaningful match
    is found (score below threshold).

    Args:
        query: Natural language query describing the desired Flame operation.
               Examples: "list libraries", "how to render batch",
                         "flame.selection error", "get selected clips"

    Returns:
        The best matching concept map entry (dict with concept, api_layer,
        tool, api_path, notes), or None if no match scores above threshold.
    """
    if not query or not query.strip():
        return None

    query_tokens = _tokenize(query)
    if not query_tokens:
        return None

    best_entry = None
    best_score = 0.0

    for entry in CONCEPT_MAP:
        score = _score_entry(query_tokens, entry)
        if score > best_score:
            best_score = score
            best_entry = entry

    # Minimum score threshold: at least one meaningful keyword match
    # A single keyword hit on concept = 3.0, so threshold of 2.0 allows
    # partial matches but filters out noise
    if best_score < 2.0:
        return None

    return best_entry
