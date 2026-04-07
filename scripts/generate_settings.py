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
import re
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
SERVER = ROOT / "src" / "flame_mcp" / "server.py"
SETTINGS = ROOT / ".claude" / "settings.local.json"

# --- Extract tool names from server -----------------------------------------

source = SERVER.read_text()

# Match every function decorated with @mcp.tool(...) immediately above def <name>
pattern = re.compile(
    r'@mcp\.tool\([^)]*\)\s*\ndef (\w+)\(',
    re.MULTILINE
)
tool_names = sorted(
    f"mcp__flame__{m.group(1)}"
    for m in pattern.finditer(source)
)

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
