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


# tool_name → callable(response_text) -> list[Suggestion]
#
# Rules start conservative. The design goal is the pattern parity with
# fpt-mcp/maya-mcp, not a specific rule set — more rules land once the
# contract is exercised in real Flame sessions.
SUGGESTION_RULES: dict[str, Callable[[str], list[Suggestion]]] = {
    "list_libraries": _suggest_after_list_libraries,
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
