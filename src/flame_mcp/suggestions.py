"""Per-tool chaining hints for flame-mcp (text-response variant).

Design note
-----------
fpt-mcp and maya-mcp emit hints by mutating a JSON-object response; their
tools return structured dicts. flame-mcp tools return **plain-text print
output** from Flame's embedded Python, so the JSON-mutate contract
doesn't apply. This module uses a different shape: hints are appended to
the text as a visible trailing block::

    <original tool output>

    ➡ Next you could also:
      • Inspect Reel 1 of 'Default Library' → list_reels(library_name='Default Library')

The LLM reads it in the same way: "surface 1–3 of these as an aside once
the user's explicit request is satisfied" (FastMCP instructions already
carry that policy for the ecosystem).

The registry mirrors fpt-mcp/maya-mcp layout (SUGGESTION_RULES dict,
kill-switch env var, cap of 3) so a future unifying wrapper can consume
both contracts.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, TypedDict


class Suggestion(TypedDict, total=False):
    tool: str
    reason: str
    params_hint: dict[str, Any]


_HIDDEN_LIBS = {"Timeline FX", "Grabbed References"}
# list_libraries produces lines of the form  `  <name>  (<summary>)`  with
# the library name terminated by two spaces before the parenthesised
# summary. The regex tolerates trailing whitespace but requires the
# two-space separator so line-wrapped diagnostics don't accidentally
# match (Flame occasionally prints headers/errors as plain text).
_LIB_LINE_RE = re.compile(r"^  (.+?)  \(.+\)\s*$", re.MULTILINE)
_LIB_HEADER_RE = re.compile(r"^\[(.+)\]$")
_REEL_LINE_RE = re.compile(r"^  (.+?)  \((\d+) clips?\)\s*$")
_CLIPS_HEADER_RE = re.compile(r"^\[(.+?)\] / \[(.+?)\] — (\d+) clip\(s\)$")


def _suggest_after_list_libraries(response_text: str) -> list[Suggestion]:
    """Pick the first visible library and suggest drilling into its reels."""
    if "No libraries found." in response_text:
        return []
    for match in _LIB_LINE_RE.finditer(response_text):
        name = match.group(1).strip()
        if name and name not in _HIDDEN_LIBS:
            return [{
                "tool": "list_reels",
                "reason": f"Inspect reels in '{name}'.",
                "params_hint": {"library_name": name},
            }]
    return []


def _suggest_after_list_reels(response_text: str) -> list[Suggestion]:
    """Pick the first populated reel and suggest listing its clips.

    Fires only when ``[Library]`` headers precede reel lines — the
    no-filter case. When the caller passed ``library_name=...``, flame-mcp
    omits the header, so the rule cannot populate ``library_name`` in the
    hint and stays silent (the user already narrowed scope manually).
    """
    current_lib = ""
    for line in response_text.splitlines():
        header = _LIB_HEADER_RE.match(line)
        if header:
            current_lib = header.group(1).strip()
            continue
        if not current_lib or current_lib in _HIDDEN_LIBS:
            continue
        reel = _REEL_LINE_RE.match(line)
        if not reel:
            continue
        reel_name = reel.group(1).strip()
        clip_count = int(reel.group(2))
        if clip_count <= 0:
            continue
        return [{
            "tool": "list_clips",
            "reason": f"List the {clip_count} clip(s) in reel '{reel_name}' of '{current_lib}'.",
            "params_hint": {
                "library_name": current_lib,
                "reel_name": reel_name,
            },
        }]
    return []


def _suggest_after_list_clips(response_text: str) -> list[Suggestion]:
    """Pick the first clip under the first reel header and suggest metadata.

    The list_clips output uses ``[Library] / [Reel] — N clip(s)`` as a
    section header followed by indented clip lines (optionally carrying a
    duration after two spaces). We extract the first clip under the first
    header to seed ``get_clip_metadata``'s three required params.

    Notes for ``get_selected_clips`` chain (intentionally NOT implemented):
    that tool's output lists items as ``  <name>  [<PyType>]`` without any
    library/reel parent context. ``get_clip_metadata`` needs all three
    names, so a follow-up hint would be misleading. The rule is deferred
    until get_selected_clips grows parent-trail output.
    """
    current_lib = ""
    current_reel = ""
    for line in response_text.splitlines():
        header = _CLIPS_HEADER_RE.match(line)
        if header:
            current_lib = header.group(1).strip()
            current_reel = header.group(2).strip()
            continue
        if not (current_lib and current_reel):
            continue
        if not line.startswith("  ") or line.lstrip().startswith("…"):
            continue
        clip_name = line[2:].split("  ", 1)[0].strip()
        if not clip_name:
            continue
        return [{
            "tool": "get_clip_metadata",
            "reason": f"Inspect detailed metadata for clip '{clip_name}'.",
            "params_hint": {
                "library_name": current_lib,
                "reel_name": current_reel,
                "clip_name": clip_name,
            },
        }]
    return []


_LOG_LINE_RE = re.compile(
    r"^  (\S[^\s]*\.log)\s",
    re.MULTILINE,
)


def _suggest_after_list_flame_logs(response_text: str) -> list[Suggestion]:
    """Pick the most recent log and suggest a filtered read.

    `list_flame_logs` prints a `📁 <dir> (N files)` header followed by
    indented rows sorted by mtime (newest first), shaped as
    ``  <name.log>     <size>   YYYY-MM-DD HH:MM``. The first matching
    row is the most recently modified log — the natural candidate for a
    follow-up read with the standard error-grep pattern used in
    diagnostic loops.
    """
    if "❌" in response_text or "No log files" in response_text:
        return []
    match = _LOG_LINE_RE.search(response_text)
    if not match:
        return []
    log_name = match.group(1)
    return [{
        "tool": "read_flame_log",
        "reason": f"Inspect the most recent log '{log_name}' for errors or tracebacks.",
        "params_hint": {
            "log_name": log_name,
            "lines": 200,
            "grep": "Error|Traceback|Exception|crash",
        },
    }]


# tool_name → callable(response_text) -> list[Suggestion]
#
# Rules mirror the fpt-mcp/maya-mcp contract. The navigation chain
# list_libraries → list_reels → list_clips → get_clip_metadata gives the
# LLM a breadcrumb for structural discovery when the user asks
# exploratory questions about the Flame project. A separate diagnostic
# chain handles the log-triage flow: list_flame_logs → read_flame_log.
SUGGESTION_RULES: dict[str, Callable[[str], list[Suggestion]]] = {
    "list_libraries": _suggest_after_list_libraries,
    "list_reels": _suggest_after_list_reels,
    "list_clips": _suggest_after_list_clips,
    "list_flame_logs": _suggest_after_list_flame_logs,
}


def _suggestions_disabled() -> bool:
    """Kill switch. Set FLAME_MCP_DISABLE_SUGGESTIONS=1 to bypass hints."""
    return os.environ.get("FLAME_MCP_DISABLE_SUGGESTIONS", "").strip() in ("1", "true", "yes")


def _format_block(suggestions: list[Suggestion]) -> str:
    """Render suggestions as a trailing text block.

    Format intentionally matches the ecosystem convention: visible to the
    user, separate from tool output, no structured markers beyond a
    leading arrow and bulleted items.
    """
    lines = ["", "", "➡ Next you could also:"]
    for s in suggestions[:3]:
        reason = s.get("reason") or ""
        tool = s.get("tool") or ""
        hint = s.get("params_hint") or {}
        hint_str = ""
        if hint:
            rendered = ", ".join(f"{k}={v!r}" for k, v in hint.items())
            hint_str = f"({rendered})"
        lines.append(f"  • {reason} → {tool}{hint_str}")
    return "\n".join(lines)


def maybe_annotate_with_suggestions(tool_name: str, response: str) -> str:
    """Return ``response`` with a trailing hint block when any rule fires.

    Idempotent: responses already containing the hint block (e.g. from a
    double-wrap) are returned verbatim. Rule errors are swallowed so a
    misbehaving rule never breaks a Flame tool call.
    """
    if _suggestions_disabled():
        return response
    rule = SUGGESTION_RULES.get(tool_name)
    if rule is None:
        return response
    if "➡ Next you could also:" in response:
        return response
    try:
        suggestions = rule(response) or []
    except Exception:
        return response
    if not suggestions:
        return response
    return response + _format_block(suggestions)
