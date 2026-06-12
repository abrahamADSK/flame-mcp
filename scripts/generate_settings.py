#!/usr/bin/env python3
"""
generate_settings.py
====================
Auto-generates .claude/settings.local.json by introspecting
src/flame_mcp/server.py for all @mcp.tool decorated functions.

Run once after a fresh clone, or after adding new tools to the server:

    python scripts/generate_settings.py

The generated file is gitignored by design — it contains workstation-specific
settings. This script ensures every install starts with all tools allowed.
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
SERVER = ROOT / "src" / "flame_mcp" / "server.py"
SETTINGS = ROOT / ".claude" / "settings.local.json"

# --- Extract tool names from server -----------------------------------------

source = SERVER.read_text()


def _is_destructive(dec: ast.Call) -> bool:
    """True if an @mcp.tool(...) decorator carries annotations=_DST."""
    return any(
        kw.arg == "annotations"
        and isinstance(kw.value, ast.Name)
        and kw.value.id == "_DST"
        for kw in getattr(dec, "keywords", [])
    )


# AST walk over every @mcp.tool function (sync OR async — the old regex matched
# only `def`, silently missing async tools). Destructive (_DST) tools are
# EXCLUDED from auto-approval: they must require an explicit operator
# confirmation (Claude Code permission prompt), so a single LLM hallucination
# cannot delete client media unattended. Mirrors
# server.py::discover_mcp_tools(include_destructive=False) and install.sh step 8.
_tree = ast.parse(source)
_names: set[str] = set()
for _node in ast.walk(_tree):
    if isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for _dec in _node.decorator_list:
            if (isinstance(_dec, ast.Call)
                    and isinstance(_dec.func, ast.Attribute)
                    and _dec.func.attr == "tool"):
                if _is_destructive(_dec):
                    continue
                _names.add(f"mcp__flame__{_node.name}")
tool_names = sorted(_names)

print(f"Found {len(tool_names)} MCP tools:")
for t in tool_names:
    print(f"  {t}")

# --- Preserve existing Bash / Read / other non-mcp entries ------------------

existing_allow = []
if SETTINGS.exists():
    try:
        existing = json.loads(SETTINGS.read_text())
        existing_allow = existing.get("permissions", {}).get("allow", [])
    except Exception:
        pass

non_mcp = [e for e in existing_allow if not e.startswith("mcp__flame__")]

# --- Write settings ----------------------------------------------------------

SETTINGS.parent.mkdir(exist_ok=True)
settings = {
    "permissions": {
        "allow": tool_names + non_mcp
    }
}

SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
print(f"\n✅  Written: {SETTINGS.relative_to(ROOT)}")
print(f"   {len(tool_names)} MCP tools  +  {len(non_mcp)} other entries")
