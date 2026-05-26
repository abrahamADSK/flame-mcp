"""
safety.py
=========
Known-crasher pattern detection for Autodesk Flame execute_python.

Extracted from src/flame_mcp/server.py to keep the safety module independent
and reusable.  Contains:

  - _DANGEROUS_PATTERNS: regex + explanation tuples for crash-prone code
  - _check_dangerous(): regex + AST scanner returning formatted error or None
  - _REDIRECT_PATTERNS: code patterns that should use a dedicated MCP tool
  - _SOFT_REDIRECT_PATTERNS: subset suppressed when creation intent detected
  - _CREATION_INTENT_RE: regex detecting create/modify intent in code
"""

import re


# ─── Safety: known-crasher patterns ──────────────────────────────────────────
# Each entry: (regex, explanation, safe_alternative)
_DANGEROUS_PATTERNS = [
    (
        r'len\s*\(\s*flame\.projects\s*\)',
        "flame.projects has no len() — PyProjectSelector is not a list.",
        "Use flame.projects.current_project.name for the active project, "
        "or read /opt/Autodesk/project directory to list all projects."
    ),
    (
        r'for\s+\w+\s+in\s+flame\.projects\b',
        "flame.projects is not iterable — iterating it crashes Flame.",
        "Use flame.projects.current_project for the active project, "
        "or os.listdir('/opt/Autodesk/project') to enumerate all projects."
    ),
    (
        r'flame\.projects\s*\[\s*\d',
        "flame.projects is not subscriptable — indexing it crashes Flame.",
        "Use flame.projects.current_project to access the current project."
    ),
    (
        r'flame\.projects\.current_project\.libraries\b',
        "project.libraries returns None — libraries live on the workspace.",
        "Use: ws = flame.projects.current_project.current_workspace; ws.libraries"
    ),
    (
        r'flame\.batch\.render\s*\(\s*\)',
        "flame.batch.render() blocks Flame's main thread and can freeze or crash it.",
        "Use: flame.schedule_idle_event(lambda: flame.batch.render(render_option='Background Reactor'))"
    ),
    (
        r'\bimport\s+wiretap\b',
        "The wiretap module is crash-prone for general scripting tasks.",
        "Use the standard flame module API. Call search_flame_docs for the correct pattern."
    ),
    (
        r'WireTapServerHandle|WireTapClientHandle|libwiretap|wiretapPythonClient',
        "Direct access to WireTap C-bindings crashes or destabilises Flame. "
        "WireTap is already loaded in Flame's process — accessing it directly is unsafe.",
        "Use the standard flame module API only. Call search_flame_docs for the correct pattern."
    ),
    (
        r'\.createNode\s*\(|\.getNumChildren\s*\(|\.getNodeInfo\s*\(',
        "WireTap tree-traversal methods (createNode, getNumChildren, getNodeInfo) "
        "are unreliable from Python hooks and can crash Flame.",
        "Use the standard flame module API. Call search_flame_docs for the correct pattern."
    ),
    (
        r'\.replace_desktop\s*\(',
        "ws.replace_desktop() is an internal Flame method that can corrupt the workspace "
        "state and crash Flame when called from a Python hook.",
        "To work with desktops use ws.desktop and its reel_groups/reels attributes. "
        "Call search_flame_docs('desktop reel group') for the correct pattern."
    ),
    (
        r'\bdir\s*\(\s*flame\b',
        "Using dir() to discover the Flame API is unsafe and causes speculative/crashing code.",
        "Call search_flame_docs(query) instead — it returns verified, working patterns."
    ),
    (
        r'\.\s*clear\s*\(\s*\)',
        "Calling .clear() on Flame objects (PyReelGroup, PyLibrary, PyReel, etc.) "
        "crashes Flame — it is a raw C-level destructor, not a public API.",
        "To empty a container, iterate its children and call flame.delete(item) on each one. "
        "See FLAME_API.md §Delete / Remove Objects for the correct pattern."
    ),
    (
        r'flame\s*\.\s*clear_desktop\s*\(',
        "flame.clear_desktop() does not exist in the public Flame Python API.",
        "To clear the desktop, delete individual reels/items using flame.delete(). "
        "See search_flame_docs('clear all reels from reel group') for the correct pattern."
    ),
    (
        r'for\s+\w+\s+in\s+list\s*\(\s*\w*\s*\.reels\s*\)\s*:\s*\n\s*flame\s*\.\s*delete',
        "This loop deletes ALL reels from the reel group — Flame crashes when a "
        "desktop reel group has zero reels.",
        "Always keep at least one reel: use reels[:-1] to delete all but the last, "
        "or filter by name with a 'keep' set. "
        "See FLAME_API.md 'Clear Desktop' for the confirmed safe pattern."
    ),
    (
        r'flame\s*\.\s*delete\s*\(\s*list\s*\(\s*\w*\s*\.reels\s*\)\s*\)',
        "flame.delete(list(rg.reels)) deletes ALL reels at once — "
        "Flame crashes when a desktop reel group has zero reels.",
        "Always keep at least one reel: flame.delete(list(rg.reels)[:-1]) "
        "or filter by name. See FLAME_API.md 'Clear Desktop' for the safe pattern."
    ),
    (
        r'if\s+\w+\.name\s*[=!]=\s*["\']|\.name\s+in\s+\{|\.name\s+not\s+in\s+\{',
        "Flame .name attributes return PyAttribute objects, not strings. "
        "Direct comparison with == or 'in' always fails silently (returns []).",
        "Always wrap with str(): str(reel.name) == 'Reel 1', "
        "or str(reel.name) in {'Reel 1', 'Reel 2'}. "
        "See FLAME_API.md 'PyAttribute' section."
    ),
    (
        r'\.name\s*\.\s*(?:startswith|endswith|lower|upper|split|strip|replace|find|contains)\s*\(',
        "Flame .name returns a PyAttribute object, not a string. "
        "String methods like .startswith(), .lower(), .split() crash with AttributeError.",
        "Always wrap with str() first: str(clip.name).startswith('VFX_')"
    ),
    (
        r'next\s*\(\s*\w+\s+for\s+\w+\s+in\s+\w+\.(?:reels|clips|libraries|reel_groups|folders)\b(?!\s*,)',
        "next() without a default raises StopIteration if no item matches, "
        "leaving Flame in an incomplete state.",
        "Always provide a default: next((r for r in rg.reels if ...), None) "
        "and check for None before using the result."
    ),
    (
        # TAREA 7: accept the common existence-guard forms, not just
        # `if x is [not] None`. `if not x:` and `if x:` are valid None checks.
        r'=\s*next\s*\(.*\bNone\b.*\)'
        r'(?![\s\S]{0,200}(?:'
        r'if\s+\w+\s+is\s+(?:not\s+)?None'   # if x is None / if x is not None
        r'|if\s+not\s+\w+'                    # if not x
        r'|if\s+\w+\s*:'                      # if x:
        r'|if\s+\w+\s+and\b'                  # if x and ...
        r'))',
        "Result of next(..., None) is used without a None check. "
        "Accessing attributes on None causes AttributeError.",
        "Always check: result = next(..., None); if result is None: print('not found'); else: use result"
    ),
    (
        r'seg\.delete\s*\(|\.remove_gap\s*\(|\.ripple\s*\(|flame\.timeline\.',
        "These timeline edit methods do not exist in Flame 2026 and crash Flame: "
        "seg.delete(), track.remove_gap(), track.ripple(), flame.timeline.*",
        "To close gaps / ripple delete: rebuild the sequence by iterating "
        "non-gap segments and overwriting them back-to-back into a new sequence. "
        "See FLAME_API.md 'Timeline / Sequence Editing — Close Gap' for the working pattern."
    ),
]


def _check_dangerous(code: str):
    """
    Scan code for patterns known to crash Flame (regex + AST).
    Returns a formatted error string if any are found, else None.
    """
    hits = []
    for pattern, reason, alternative in _DANGEROUS_PATTERNS:
        if re.search(pattern, code):
            hits.append(f"  \u2022 {reason}\n    \u2705 Instead: {alternative}")

    # A2 — AST analysis catches obfuscated calls that bypass regex
    # e.g. getattr(flame, 'batch').render()  or  __import__('wiretap')
    try:
        import ast as _ast
        tree = _ast.parse(code)
        for node in _ast.walk(tree):
            # Catch:  import wiretap  /  __import__('wiretap')
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                for alias in getattr(node, 'names', []):
                    if getattr(alias, 'name', '').startswith('wiretap'):
                        hits.append(
                            "  \u2022 [AST] import wiretap \u2014 crash-prone module.\n"
                            "    \u2705 Instead: use the standard flame module API."
                        )
            # Catch:  flame.batch.render()  via any attribute access chain
            if isinstance(node, _ast.Call):
                func = node.func
                if isinstance(func, _ast.Attribute) and func.attr == 'render':
                    owner = func.value
                    if isinstance(owner, _ast.Attribute) and owner.attr == 'batch':
                        hits.append(
                            "  \u2022 [AST] flame.batch.render() \u2014 blocks Flame main thread.\n"
                            "    \u2705 Instead: use schedule_idle_event(render_fn)."
                        )
    except SyntaxError:
        pass  # syntax errors will be caught later by exec()
    except Exception:
        pass  # AST check is best-effort — never block on parse failure

    # A2-EXT — PyExporter.export() called outside schedule_idle_event hangs Flame
    # even with foreground=False, because the Qt event loop cannot process the export
    # while the Python hook thread is still blocked waiting to return.
    if re.search(r'\bPyExporter\s*\(', code) and not re.search(r'schedule_idle_event', code):
        hits.append(
            "  \u2022 PyExporter().export() called without schedule_idle_event \u2014 "
            "this hangs Flame's main thread even with foreground=False.\n"
            "    \u2705 Instead:\n"
            "       def _do_export():\n"
            "           exporter = flame.PyExporter()\n"
            "           exporter.foreground = False\n"
            "           exporter.export([seq], preset_path, output_dir)\n"
            "       flame.schedule_idle_event(_do_export)"
        )

    if not hits:
        return None
    return (
        "\U0001f6d1 Blocked \u2014 contains pattern(s) known to crash Flame:\n\n"
        + "\n\n".join(hits)
        + "\n\nRevise the code and try again. "
        "If unsure of the correct approach, call search_flame_docs first."
    )


# ─── Redirect patterns ──────────────────────────────────────────────────────
# Bug 3 (OBS-013): module-level redirect table — maps code patterns to the
# dedicated tool that should be used instead of execute_python.
_REDIRECT_PATTERNS = [
    # (regex pattern in code,  redirect message)
    (r'get_project_info|current_project\b.*\.(name|description|workspaces)',
     "Use get_project_info() \u2014 it returns project name, resolution, fps, "
     "bit depth via Wiretap XML. execute_python cannot access those fields."),
    (r'ws\.libraries|current_workspace\.libraries|getLibraries',
     "Use list_libraries() \u2014 it filters hidden system libraries automatically."),
    (r'\.reels|getReels\(',
     "Use list_reels(library_name) \u2014 returns all reels for a library in one call."),
    (r'getEntries\(|\.clips|getClips\(',
     "Use list_clips(library_name, reel_name) \u2014 returns formatted clip list."),
    (r'reel_groups|getReelGroups|desktop.*reel',
     "Use list_desktop_reels() \u2014 returns the full desktop hierarchy with clip names."),
    (r'batch_groups|getBatchGroups|\.batch_group',
     "Use list_batch_groups() \u2014 returns batch groups with node and reel counts."),
    (r'flame\.selection',
     "flame.selection does not exist. "
     "Use get_selected_clips() \u2014 it uses flame.media_panel.selected_entries correctly."),
    (r'media_panel\.selected_entries',
     "Use get_selected_clips() \u2014 the dedicated tool handles this."),
    (r'get_version\(\)|flame\.version',
     "Use get_flame_version() \u2014 returns the version string directly."),
    (r'wiretap_print_tree|wiretap_get_children',
     "Use flame_wiretap_tree(path) \u2014 it handles host flags and error handling."),
    (r'os\.listdir.*log|/opt/Autodesk/logs',
     "Use list_flame_logs() / read_flame_log() \u2014 they list and filter log files."),
]

# Structural redirect patterns that are suppressed when creation/modification
# intent is detected. These match object-hierarchy traversal (libraries -> reels
# -> clips) that is legitimately required for operations like create_sequence /
# overwrite / import_clips. Hard patterns (wrong API, version, logs) always
# redirect regardless of intent.
_SOFT_REDIRECT_PATTERNS: set = {
    r'ws\.libraries|current_workspace\.libraries|getLibraries',
    r'\.reels|getReels\(',
    r'getEntries\(|\.clips|getClips\(',
    r'reel_groups|getReelGroups|desktop.*reel',
    r'batch_groups|getBatchGroups|\.batch_group',
}

# Regex that detects creation / modification intent in execute_python code.
# When matched, soft redirect patterns above are suppressed so the model can
# traverse the hierarchy (libraries -> reels -> clips) to operate on it.
# TAREA 7: copy / move / method-form delete / timeline insert are modification
# intents too — without them, a legitimate copy/move/delete that traverses
# .reels/.clips was redirected as if it were a read query, forcing the model to
# obfuscate the traversal with getattr() to dodge the redirect.
_CREATION_INTENT_RE = re.compile(
    r'create_sequence\s*\('
    r'|\.overwrite\s*\('
    r'|\.insert\s*\('                          # timeline insert (seq.insert)
    r'|import_clips\s*\('
    r'|\.delete\s*\('                          # flame.delete(...) AND method form clip.delete()
    r'|media_panel\s*\.\s*(?:copy|move)\s*\('  # media-panel copy / move
    r'|schedule_idle_event'
    r'|create_reel\s*\('
    r'|create_library\s*\('
    r'|create_batch_group\s*\('
    r'|create_clip\s*\('
)
