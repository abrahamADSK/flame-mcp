"""
generate_flame_api.py
=====================
Generates a comprehensive Flame Python API reference by introspecting the
live `flame` module via the TCP bridge running inside Flame.

The output is saved as docs/flame_api_full.md and automatically picked up
by build_index.py when rebuilding the RAG index.

Usage (with Flame open and bridge running):
    cd ~/Projects/flame-mcp
    source .venv/bin/activate
    python rag/generate_flame_api.py

Then rebuild the RAG index:
    python rag/build_index.py
"""

import socket
import json
import os
import sys
import textwrap

BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 4444
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(ROOT, 'docs', 'flame_api_full.md')


# ── Bridge helper ─────────────────────────────────────────────────────────────

def _send(code: str, timeout: int = 60) -> dict:
    """Send Python code to the Flame bridge and return the parsed result."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((BRIDGE_HOST, BRIDGE_PORT))
        s.sendall((json.dumps({'code': code}) + '\n').encode('utf-8'))
        data = b''
        while not data.endswith(b'\n'):
            chunk = s.recv(8192)
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode('utf-8').strip())
    finally:
        s.close()


def run(code: str, timeout: int = 60) -> str:
    """Run code in Flame and return stdout output, or raise on error."""
    r = _send(code, timeout)
    if r.get('status') == 'error':
        raise RuntimeError(r.get('error', 'unknown error'))
    return r.get('output', '').strip()


# ── Introspection code (runs inside Flame) ────────────────────────────────────

_INTROSPECT_OVERVIEW = """
import flame, inspect, json

classes   = sorted([n for n,o in inspect.getmembers(flame, inspect.isclass)])
functions = sorted([n for n,o in inspect.getmembers(flame, inspect.isfunction)])
constants = sorted([n for n in dir(flame)
                    if not n.startswith('_')
                    and not inspect.isclass(getattr(flame, n, None))
                    and not inspect.isfunction(getattr(flame, n, None))
                    and not inspect.ismodule(getattr(flame, n, None))])

print(json.dumps({
    'classes':   classes,
    'functions': functions,
    'constants': constants,
}))
"""

_INTROSPECT_CLASS = """
import flame, inspect, json

cls_name = {cls_name!r}
cls = getattr(flame, cls_name, None)
if cls is None:
    print(json.dumps({{'error': 'not found'}}))
else:
    methods = []
    for name, obj in sorted(inspect.getmembers(cls)):
        if name.startswith('_'):
            continue
        try:
            sig = str(inspect.signature(obj))
        except (ValueError, TypeError):
            sig = '(...)'
        doc = (inspect.getdoc(obj) or '').strip()
        # Keep first 2 lines of docstring to save space
        short_doc = '\\n'.join(doc.splitlines()[:2]) if doc else ''
        methods.append({{'name': name, 'sig': sig, 'doc': short_doc}})

    cls_doc = (inspect.getdoc(cls) or '').strip()
    short_cls_doc = '\\n'.join(cls_doc.splitlines()[:4]) if cls_doc else ''

    # Get class-level attributes (non-callable, non-private)
    attrs = []
    for name in sorted(dir(cls)):
        if name.startswith('_'):
            continue
        val = getattr(cls, name, None)
        if callable(val):
            continue
        attrs.append(name)

    print(json.dumps({{
        'name':    cls_name,
        'doc':     short_cls_doc,
        'methods': methods,
        'attrs':   attrs,
    }}))
"""

_INTROSPECT_FUNCTIONS = """
import flame, inspect, json

functions = []
for name, obj in sorted(inspect.getmembers(flame, inspect.isfunction)):
    try:
        sig = str(inspect.signature(obj))
    except (ValueError, TypeError):
        sig = '(...)'
    doc = (inspect.getdoc(obj) or '').strip()
    short_doc = '\\n'.join(doc.splitlines()[:3]) if doc else ''
    functions.append({'name': name, 'sig': sig, 'doc': short_doc})

print(json.dumps(functions))
"""


# ── Markdown generation ───────────────────────────────────────────────────────

def _md_class(cls_info: dict) -> str:
    lines = []
    name = cls_info['name']
    lines.append(f"\n## {name}\n")
    if cls_info.get('doc'):
        lines.append(f"{cls_info['doc']}\n")

    attrs = cls_info.get('attrs', [])
    if attrs:
        lines.append(f"**Attributes:** `{'`, `'.join(attrs)}`\n")

    methods = cls_info.get('methods', [])
    if methods:
        lines.append("**Methods:**\n")
        for m in methods:
            sig_line = f"- `{m['name']}{m['sig']}`"
            if m.get('doc'):
                # Indent continuation lines
                doc_lines = m['doc'].splitlines()
                sig_line += f"  \n  {doc_lines[0]}"
                for dl in doc_lines[1:]:
                    sig_line += f"  \n  {dl}"
            lines.append(sig_line)
        lines.append("")

    return '\n'.join(lines)


def _md_functions(functions: list) -> str:
    if not functions:
        return ""
    lines = ["\n## Module-level Functions\n"]
    for f in functions:
        line = f"- `flame.{f['name']}{f['sig']}`"
        if f.get('doc'):
            doc_lines = f['doc'].splitlines()
            line += f"  \n  {doc_lines[0]}"
        lines.append(line)
    lines.append("")
    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"flame-mcp · Flame API documentation generator")
    print(f"Bridge: {BRIDGE_HOST}:{BRIDGE_PORT}")
    print()

    # ── Step 1: overview ──────────────────────────────────────────────────────
    print("Step 1/3  Getting module overview…")
    try:
        raw = run(_INTROSPECT_OVERVIEW)
    except ConnectionRefusedError:
        print(f"\n❌  Cannot connect to bridge on {BRIDGE_HOST}:{BRIDGE_PORT}")
        print("    Make sure Flame is open and the MCP Bridge is active.")
        print("    In Flame: MCP Bridge → Start bridge")
        sys.exit(1)

    overview = json.loads(raw)
    classes   = overview['classes']
    functions = overview.get('functions', [])
    constants = overview.get('constants', [])

    print(f"   Classes  : {len(classes)}")
    print(f"   Functions: {len(functions)}")
    print(f"   Constants: {len(constants)}")

    # ── Step 2: introspect each class ─────────────────────────────────────────
    print(f"\nStep 2/3  Introspecting {len(classes)} classes…")
    class_docs = []
    failed     = []

    for i, cls_name in enumerate(classes):
        pct = int((i + 1) / len(classes) * 100)
        print(f"\r   [{pct:3d}%] {cls_name:<40}", end='', flush=True)

        code = _INTROSPECT_CLASS.format(cls_name=cls_name)
        try:
            raw = run(code, timeout=15)
            info = json.loads(raw)
            if 'error' not in info:
                class_docs.append(info)
            else:
                failed.append(cls_name)
        except Exception as e:
            failed.append(cls_name)

    print(f"\r   Done. {len(class_docs)} classes documented, {len(failed)} failed.")
    if failed:
        print(f"   Failed: {', '.join(failed[:10])}" +
              (' …' if len(failed) > 10 else ''))

    # ── Step 3: introspect module functions ───────────────────────────────────
    print("\nStep 3/3  Introspecting module-level functions…")
    fn_docs = []
    if functions:
        try:
            raw = run(_INTROSPECT_FUNCTIONS, timeout=30)
            fn_docs = json.loads(raw)
            print(f"   {len(fn_docs)} functions documented.")
        except Exception as e:
            print(f"   Warning: {e}")

    # ── Assemble markdown ─────────────────────────────────────────────────────
    print(f"\nWriting {OUTPUT_PATH} …")

    # Detect Flame version
    try:
        version = run("import flame; print(flame.get_version_info())", timeout=10)
    except Exception:
        version = "2026"

    lines = [
        f"# Flame Python API — Full Reference",
        f"",
        f"> Auto-generated by `rag/generate_flame_api.py` from the live `flame` module.",
        f"> Flame version: {version}",
        f"> Classes: {len(class_docs)}  ·  Functions: {len(fn_docs)}",
        f"",
        f"This document is indexed by the RAG system and searched automatically.",
        f"It supplements FLAME_API.md with the complete class and method reference.",
        f"",
        f"---",
        f"",
        f"## Object Hierarchy (quick reference)",
        f"",
        f"```",
        f"flame.projects.current_project          → PyProject",
        f"  .current_workspace                    → PyWorkspace",
        f"    .libraries                          → [PyLibrary]",
        f"    .desktop                            → PyDesktop",
        f"      .reel_groups                      → [PyReelGroup]",
        f"        .reels                          → [PyReel]",
        f"          .clips                        → [PyClip / PySequence]",
        f"```",
        f"",
        f"---",
        f"",
    ]

    # Constants / top-level attributes
    if constants:
        lines += [
            "## Module-level Attributes",
            "",
            f"`{'`, `'.join(constants)}`",
            "",
            "---",
            "",
        ]

    # Module functions
    if fn_docs:
        lines.append(_md_functions(fn_docs))
        lines += ["", "---", ""]

    # Classes (alphabetical, already sorted)
    lines.append("# Classes\n")
    for cls_info in class_docs:
        lines.append(_md_class(cls_info))
        lines.append("\n---\n")

    content = '\n'.join(lines)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"✅  Written: {OUTPUT_PATH}  ({size_kb:.0f} KB)")
    print()
    print("Next step — rebuild the RAG index:")
    print("  python rag/build_index.py")


if __name__ == '__main__':
    main()
