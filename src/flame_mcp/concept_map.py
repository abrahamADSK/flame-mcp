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
