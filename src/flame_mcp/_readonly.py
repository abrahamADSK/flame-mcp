"""Read-only console support: deny-list + improvement-suggestion capture.

The in-Flame bridge spawns a ``claude`` subprocess with every file-mutation
tool denied (``DISALLOWED_TOOLS``), so the agent CANNOT edit the repo (a console
agent once rewrote a server's own source mid-session). The self-improving RAG
is unaffected: ``learn_pattern`` is an MCP tool, so its writes happen in the MCP
server process, not via the agent's file tools.

Instead of editing code, the agent is instructed to surface code-improvement
ideas as ``@@SUGGESTION@@ <text>`` lines. ``capture_suggestions`` — the ONLY
writer of the backlog file — pulls those lines out of the reply, appends them
(timestamped, with a one-time header) for a later dev session / PR, and strips
the markers from what the user sees.

Pure stdlib (no Flame deps) so it is unit-testable outside the host app.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

# Every file-write / shell vector the agent could use to modify the repo.
DISALLOWED_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"]

_SUGGESTION_RE = re.compile(r"(?m)^.*@@SUGGESTION@@[ \t]*(.+?)[ \t]*$")


def capture_suggestions(text, dest):
    """Pull ``@@SUGGESTION@@`` lines from *text*, append them to *dest*, and
    return ``(text_without_those_lines, count)``.

    *dest* is a path (str or Path) to the backlog file. Best-effort: any write
    failure is swallowed (returns the cleaned text, count 0) and never breaks
    the reply.
    """
    matches = [m.group(1).strip() for m in _SUGGESTION_RE.finditer(text or "")]
    matches = [s for s in matches if s]
    clean = re.sub(r"\n{3,}", "\n\n", _SUGGESTION_RE.sub("", text or "")).strip()
    if not matches:
        return clean, 0
    try:
        dest = Path(dest)
        new_file = not dest.exists()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with dest.open("a", encoding="utf-8") as fh:
            if new_file:
                fh.write(
                    "# Console improvement backlog\n\n"
                    "Auto-captured suggestions from the **read-only** in-Flame "
                    "console subprocess. The console agent cannot edit code; it "
                    "logs ideas here to pick up in a dev session or PR.\n"
                )
            for s in matches:
                fh.write(f"\n- [{stamp}] {s}")
            fh.write("\n")
    except OSError:
        return clean, 0
    return clean, len(matches)


def build_scoped_mcp_config(mcp_json_path, keep_servers):
    """Return a ``--mcp-config`` JSON string with only *keep_servers*, read from
    *mcp_json_path* (the repo's ``.mcp.json``).

    Used with ``--strict-mcp-config`` so the in-Flame console loads ONLY the MCP
    servers it needs — Flame + ShotGrid (`fpt-mcp`), NOT Maya's ~15 tool schemas.
    Returns None on any failure (missing file, no matching servers, parse error)
    so the caller can fall back to default MCP discovery.
    """
    try:
        data = json.loads(Path(mcp_json_path).read_text(encoding="utf-8"))
        servers = {
            k: v
            for k, v in (data.get("mcpServers") or {}).items()
            if k in keep_servers
        }
        if not servers:
            return None
        return json.dumps({"mcpServers": servers})
    except Exception:
        return None
