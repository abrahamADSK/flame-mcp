"""
journal.py
==========
Operation journaling system for Flame MCP execute_python calls.

Records every execute_python invocation and its result, enabling:
  - Full operation history (last N entries)
  - Undo support for reversible operations

Architecture item 3.6 — operation journal with undo code generation.

Classes:
  - Journal: ring-buffer of operation entries (max 100)
  - UndoCodeGenerator: pattern-based undo code synthesis for common Flame ops
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Callable


# ─── Ring-buffer operation journal ───────────────────────────────────────────

MAX_ENTRIES = 100


class Journal:
    """In-memory ring-buffer journal of execute_python operations.

    Each entry is a dict with:
      - timestamp (str): ISO-8601 UTC timestamp
      - operation_id (str): unique UUID4 identifier
      - code (str): the Python code that was executed
      - result (dict): {"status": "success"|"error", "output": str}
      - undoable (bool): whether undo_code is available
      - undo_code (str | None): Python code to reverse the operation
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []

    # ── Public API ───────────────────────────────────────────────────────

    def record(self, code: str, result: dict, undo_code: str | None = None) -> dict:
        """Record an operation and return the created entry.

        Args:
            code: Python source that was executed in Flame.
            result: Dict with at least 'status' and 'output' keys.
            undo_code: Optional Python source that reverses the operation.

        Returns:
            The journal entry dict that was stored.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation_id": str(uuid.uuid4()),
            "code": code,
            "result": result,
            "undoable": undo_code is not None,
            "undo_code": undo_code,
        }
        self._entries.append(entry)

        # Ring-buffer: drop the oldest entry when over capacity
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]

        return entry

    def last_operation(self) -> dict | None:
        """Return the most recent journal entry, or None if empty."""
        if not self._entries:
            return None
        return self._entries[-1]

    def get_undo_code(self) -> str | None:
        """Return the undo_code of the last undoable operation, or None.

        Scans backwards from the most recent entry to find the latest
        operation that is marked undoable. Returns None if no undoable
        operations exist in the journal.
        """
        for entry in reversed(self._entries):
            if entry["undoable"]:
                return entry["undo_code"]
        return None

    def history(self, n: int = 10) -> str:
        """Return the last N entries as a human-readable formatted string.

        Args:
            n: Maximum number of entries to include (default 10).

        Returns:
            Multi-line string with one entry per block, newest last.
            Returns "No operations recorded." if the journal is empty.
        """
        if not self._entries:
            return "No operations recorded."

        recent = self._entries[-n:]
        lines: list[str] = []
        for i, entry in enumerate(recent, 1):
            status = entry["result"].get("status", "unknown")
            output = entry["result"].get("output", "")
            undo_marker = " [undoable]" if entry["undoable"] else ""
            lines.append(
                f"[{i}] {entry['timestamp']} ({entry['operation_id'][:8]}...){undo_marker}\n"
                f"    Status: {status}\n"
                f"    Code: {entry['code'][:80]}{'...' if len(entry['code']) > 80 else ''}\n"
                f"    Output: {output[:120]}{'...' if len(output) > 120 else ''}"
            )
        return "\n\n".join(lines)

    def clear(self) -> None:
        """Reset the journal, removing all entries."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


# ─── Undo code generation ────────────────────────────────────────────────────

# Patterns are tried in order.  Each is a tuple of:
#   (compiled_regex, generator_function)
# The generator receives the regex match and the result string,
# and returns undo code (str) or None if it cannot produce safe undo code.

# Result file written by the scheduled structural delete (read it in a separate
# step to confirm completion, exactly like render/export).
_UNDO_RESULT_FILE = "~/flame_undo_result.txt"


def _schedule_idle_delete(finder_code: str, label: str) -> str:
    """Build undo code that deletes a *structural* Flame object safely.

    Direct ``flame.delete()`` on a PyLibrary / PyReel / PyFolder / PyBatchGroup
    DEADLOCKS Flame 2027's main thread (ecosystem invariant — the bridge times
    out at ~15 s with the UI frozen and a force-quit required). The only
    validated-safe form is ``flame.schedule_idle_event`` + a result file, the
    same pattern render_batch / export_clip use. The delete therefore runs
    ASYNCHRONOUSLY: ``undo_last_operation`` returns as soon as it is scheduled,
    and the operator reads ``~/flame_undo_result.txt`` to confirm.

    Names captured from the create-call regex cannot contain quotes (the
    patterns use ``[^'\"]+``), so direct interpolation into the generated
    string literals is safe.

    Args:
        finder_code: Python that locates the object and binds it to ``target``
                     (or ``target = None`` when not found). May span several
                     lines; ``ws`` is already defined when it runs.
        label:       Human-readable description for the messages, e.g.
                     ``"library VFX_Shots"``.
    """
    return (
        "import flame, os\n"
        f"result_file = os.path.expanduser({_UNDO_RESULT_FILE!r})\n"
        "ws = flame.projects.current_project.current_workspace\n"
        f"{finder_code}\n"
        "if target is None:\n"
        f"    print('Undo target not found: {label}')\n"
        "elif not hasattr(flame, 'schedule_idle_event'):\n"
        "    print('ERROR: Flame idle-event API unavailable — bring Flame to the "
        "foreground (active app) and retry.')\n"
        "else:\n"
        "    def _do_delete():\n"
        "        try:\n"
        "            flame.delete(target)\n"
        f"            msg = 'OK: deleted {label}'\n"
        "        except Exception as e:\n"
        "            msg = 'ERROR: ' + str(e)\n"
        "        with open(result_file, 'w') as f:\n"
        "            f.write(msg)\n"
        "    flame.schedule_idle_event(_do_delete)\n"
        f"    print('Undo (delete {label}) scheduled via idle event.')\n"
    )


def _undo_create_library(match: re.Match, result: str) -> str | None:
    """Undo ws.create_library('Name') → scheduled flame.delete(lib).

    Structural delete: wrapped in schedule_idle_event (see _schedule_idle_delete).
    """
    lib_name = match.group("name")
    finder = (
        f"target = next((l for l in ws.libraries if str(l.name) == {lib_name!r}), None)"
    )
    return _schedule_idle_delete(finder, f"library {lib_name}")


def _undo_create_reel(match: re.Match, result: str) -> str | None:
    """Undo create_reel('Name') → scheduled flame.delete(reel).

    Structural delete: wrapped in schedule_idle_event (see _schedule_idle_delete).
    """
    reel_name = match.group("name")
    finder = (
        "HIDDEN = {'Timeline FX', 'Grabbed References'}\n"
        "target = None\n"
        "for lib in ws.libraries:\n"
        "    if str(lib.name) in HIDDEN:\n"
        "        continue\n"
        "    for reel in lib.reels:\n"
        f"        if str(reel.name) == {reel_name!r}:\n"
        "            target = reel\n"
        "            break\n"
        "    if target is not None:\n"
        "        break"
    )
    return _schedule_idle_delete(finder, f"reel {reel_name}")


def _undo_create_batch_group(match: re.Match, result: str) -> str | None:
    """Undo create_batch_group('Name') → scheduled flame.delete(bg).

    Structural delete: wrapped in schedule_idle_event (see _schedule_idle_delete).
    """
    bg_name = match.group("name")
    finder = (
        "desktop = ws.desktop\n"
        f"target = next((b for b in desktop.batch_groups if str(b.name) == {bg_name!r}), None)"
    )
    return _schedule_idle_delete(finder, f"batch group {bg_name}")


def _undo_rename(match: re.Match, result: str) -> str | None:
    """Undo obj.name = 'NewName' → obj.name = 'OldName'.

    Requires the result to contain the old name.  We look for patterns like:
      'Renamed <old> to <new>' or 'old_name: <old>'
    """
    new_name = match.group("new_name")

    # Try to extract old name from the result output
    old_match = re.search(
        r"(?:Renamed|renamed)\s+['\"]?(.+?)['\"]?\s+(?:to|->)\s+['\"]?" + re.escape(new_name),
        result,
    )
    if not old_match:
        # Also try: "old_name: X" or "was: X" patterns
        old_match = re.search(r"(?:old_name|was|previous):\s*['\"]?(.+?)['\"]?\s*$", result, re.MULTILINE)

    if not old_match:
        return None  # Cannot determine old name — not safe to undo

    old_name = old_match.group(1).strip()
    # Reconstruct: find the object reference and set name back
    obj_ref = match.group("obj")
    return f"{obj_ref}.name = {old_name!r}\nprint(f'Renamed back to: {old_name}')"


def _undo_move(match: re.Match, result: str) -> str | None:
    """Undo a move/copy operation by moving back.

    Only generates undo if the result confirms the source and destination.
    """
    # Extract source and destination from result
    # Use \S+ to capture paths (non-whitespace), stripping optional quotes
    move_back = re.search(
        r"(?:Moved|moved)\s+from\s+['\"]?(\S+?)['\"]?\s+to\s+['\"]?(\S+?)['\"]?\s*$",
        result,
    )
    if not move_back:
        return None  # Cannot determine original location

    source = move_back.group(1).strip()
    dest = move_back.group(2).strip()
    return (
        "import flame, shutil\n"
        f"# Move back from {dest} to {source}\n"
        f"shutil.move({dest!r}, {source!r})\n"
        f"print('Moved back from {dest} to {source}')"
    )


# ── Pattern table ────────────────────────────────────────────────────────────
# Order matters: more specific patterns first.

_UNDO_PATTERNS: list[tuple[re.Pattern, Callable]] = [
    # Create library
    (
        re.compile(r"\.create_library\s*\(\s*['\"](?P<name>[^'\"]+)['\"]\s*\)"),
        _undo_create_library,
    ),
    # Create reel
    (
        re.compile(r"\.create_reel\s*\(\s*['\"](?P<name>[^'\"]+)['\"]\s*\)"),
        _undo_create_reel,
    ),
    # Create batch group (may have extra kwargs after the name)
    (
        re.compile(r"\.create_batch_group\s*\(\s*['\"](?P<name>[^'\"]+)['\"]"),
        _undo_create_batch_group,
    ),
    # Rename: obj.name = 'NewName'
    (
        re.compile(r"(?P<obj>[\w.]+)\.name\s*=\s*['\"](?P<new_name>[^'\"]+)['\"]"),
        _undo_rename,
    ),
    # Move operations (shutil.move or similar)
    (
        re.compile(r"(?:shutil\.move|os\.rename)\s*\("),
        _undo_move,
    ),
]

# Patterns that are NEVER undoable — checked first to short-circuit.
_NON_UNDOABLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"flame\.delete\s*\("),
    re.compile(r"\.clear\s*\(\s*\)"),
    re.compile(r"shutil\.rmtree\s*\("),
    re.compile(r"os\.remove\s*\("),
    re.compile(r"os\.unlink\s*\("),
]


class UndoCodeGenerator:
    """Generate undo code for common Flame operations via pattern matching.

    Conservative approach: only produces undo code when confident the
    reversal is correct.  Returns None for anything ambiguous or
    destructive (deletes are never undoable).
    """

    @staticmethod
    def generate_undo(code: str, result: str) -> str | None:
        """Attempt to generate undo code for a given execute_python call.

        Args:
            code: The Python source that was executed.
            result: The string output returned by the execution.

        Returns:
            Python source string that reverses the operation, or None
            if the operation is not safely reversible.
        """
        # Short-circuit: destructive operations are never undoable
        for pattern in _NON_UNDOABLE_PATTERNS:
            if pattern.search(code):
                return None

        # Try each undo pattern in order
        for pattern, generator in _UNDO_PATTERNS:
            match = pattern.search(code)
            if match:
                undo = generator(match, result)
                if undo is not None:
                    return undo

        # No matching pattern — not safely reversible
        return None
