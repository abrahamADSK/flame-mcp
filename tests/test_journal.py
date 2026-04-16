"""
test_journal.py
===============
Tests for the operation journal module (architecture item 3.6).

Covers:
  - Journal: record, last_operation, history, ring buffer, get_undo_code, clear
  - UndoCodeGenerator: create→delete, rename→rename back, delete→None
"""

import pytest

from flame_mcp.journal import Journal, UndoCodeGenerator, MAX_ENTRIES


# ─── Journal class tests ────────────────────────────────────────────────────


class TestJournalRecordAndLastOperation:
    """record() + last_operation() round-trip."""

    def test_record_returns_entry_with_all_fields(self):
        j = Journal()
        result = {"status": "success", "output": "ok"}
        entry = j.record("print('hello')", result)

        assert "timestamp" in entry
        assert "operation_id" in entry
        assert entry["code"] == "print('hello')"
        assert entry["result"] == result
        assert entry["undoable"] is False
        assert entry["undo_code"] is None

    def test_last_operation_returns_most_recent(self):
        j = Journal()
        j.record("print(1)", {"status": "success", "output": "1"})
        j.record("print(2)", {"status": "success", "output": "2"})
        last = j.last_operation()

        assert last is not None
        assert last["code"] == "print(2)"
        assert last["result"]["output"] == "2"

    def test_last_operation_returns_none_when_empty(self):
        j = Journal()
        assert j.last_operation() is None

    def test_record_with_undo_code_marks_undoable(self):
        j = Journal()
        entry = j.record(
            "ws.create_library('Test')",
            {"status": "success", "output": "Created: Test"},
            undo_code="flame.delete(lib)",
        )
        assert entry["undoable"] is True
        assert entry["undo_code"] == "flame.delete(lib)"

    def test_operation_ids_are_unique(self):
        j = Journal()
        e1 = j.record("a", {"status": "success", "output": ""})
        e2 = j.record("b", {"status": "success", "output": ""})
        assert e1["operation_id"] != e2["operation_id"]


class TestJournalHistory:
    """history() returns correct count and format."""

    def test_history_returns_correct_count(self):
        j = Journal()
        for i in range(20):
            j.record(f"op_{i}", {"status": "success", "output": f"out_{i}"})

        # Default n=10 — should have exactly 10 blocks
        h = j.history()
        assert h.count("[") == 10  # 10 numbered entries

    def test_history_custom_count(self):
        j = Journal()
        for i in range(5):
            j.record(f"op_{i}", {"status": "success", "output": f"out_{i}"})

        h = j.history(n=3)
        # Should only show last 3
        assert "op_2" in h
        assert "op_3" in h
        assert "op_4" in h
        assert "op_0" not in h
        assert "op_1" not in h

    def test_history_empty_journal(self):
        j = Journal()
        assert j.history() == "No operations recorded."

    def test_history_shows_undoable_marker(self):
        j = Journal()
        j.record("code", {"status": "success", "output": ""}, undo_code="undo")
        h = j.history()
        assert "[undoable]" in h


class TestJournalRingBuffer:
    """Ring buffer drops oldest at MAX_ENTRIES."""

    def test_ring_buffer_caps_at_max(self):
        j = Journal()
        for i in range(MAX_ENTRIES + 20):
            j.record(f"op_{i}", {"status": "success", "output": ""})

        assert len(j) == MAX_ENTRIES

    def test_ring_buffer_drops_oldest(self):
        j = Journal()
        for i in range(MAX_ENTRIES + 5):
            j.record(f"op_{i}", {"status": "success", "output": ""})

        # The oldest should be op_5 (first 5 were dropped)
        first = j._entries[0]
        assert first["code"] == "op_5"

        # The newest should be the last one recorded
        last = j.last_operation()
        assert last["code"] == f"op_{MAX_ENTRIES + 4}"

    def test_exact_capacity_no_drop(self):
        j = Journal()
        for i in range(MAX_ENTRIES):
            j.record(f"op_{i}", {"status": "success", "output": ""})

        assert len(j) == MAX_ENTRIES
        assert j._entries[0]["code"] == "op_0"


class TestJournalGetUndoCode:
    """get_undo_code() finds the last undoable operation."""

    def test_returns_none_when_no_undoable_ops(self):
        j = Journal()
        j.record("print(1)", {"status": "success", "output": "1"})
        j.record("print(2)", {"status": "success", "output": "2"})
        assert j.get_undo_code() is None

    def test_returns_none_when_empty(self):
        j = Journal()
        assert j.get_undo_code() is None

    def test_returns_code_for_undoable_ops(self):
        j = Journal()
        j.record("create", {"status": "success", "output": ""}, undo_code="delete")
        assert j.get_undo_code() == "delete"

    def test_returns_most_recent_undoable(self):
        j = Journal()
        j.record("create_1", {"status": "success", "output": ""}, undo_code="delete_1")
        j.record("print(1)", {"status": "success", "output": "1"})  # not undoable
        j.record("create_2", {"status": "success", "output": ""}, undo_code="delete_2")
        j.record("print(2)", {"status": "success", "output": "2"})  # not undoable

        assert j.get_undo_code() == "delete_2"

    def test_skips_non_undoable_to_find_last_undoable(self):
        j = Journal()
        j.record("create", {"status": "success", "output": ""}, undo_code="delete")
        for _ in range(10):
            j.record("read", {"status": "success", "output": ""})

        assert j.get_undo_code() == "delete"


class TestJournalClear:
    """clear() resets the journal."""

    def test_clear_empties_journal(self):
        j = Journal()
        j.record("op", {"status": "success", "output": ""})
        j.record("op2", {"status": "success", "output": ""})
        assert len(j) == 2

        j.clear()
        assert len(j) == 0
        assert j.last_operation() is None
        assert j.get_undo_code() is None
        assert j.history() == "No operations recorded."


# ─── UndoCodeGenerator tests ────────────────────────────────────────────────


class TestUndoCodeGeneratorCreate:
    """Create operations produce delete undo code."""

    def test_create_library_generates_delete(self):
        code = "ws.create_library('VFX_Shots')"
        result = "Created: VFX_Shots"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is not None
        assert "flame.delete" in undo
        assert "VFX_Shots" in undo

    def test_create_reel_generates_delete(self):
        code = "lib.create_reel('Input')"
        result = "Created reel: Input"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is not None
        assert "flame.delete" in undo
        assert "Input" in undo

    def test_create_batch_group_generates_delete(self):
        code = "desktop.create_batch_group('Shot_010', reels=['Input', 'Output'])"
        result = "Created: Shot_010"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is not None
        assert "flame.delete" in undo
        assert "Shot_010" in undo


class TestUndoCodeGeneratorRename:
    """Rename operations produce rename-back undo code when old name is available."""

    def test_rename_with_old_name_in_result(self):
        code = "clip.name = 'NewClipName'"
        result = "Renamed OldClipName to NewClipName"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is not None
        assert "OldClipName" in undo
        assert ".name =" in undo

    def test_rename_without_old_name_returns_none(self):
        code = "clip.name = 'NewClipName'"
        result = "ok"  # No old name info — cannot safely undo
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None


class TestUndoCodeGeneratorNonReversible:
    """Delete and other destructive operations return None."""

    def test_flame_delete_returns_none(self):
        code = "flame.delete(lib)"
        result = "Deleted library: Test"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None

    def test_os_remove_returns_none(self):
        code = "os.remove('/path/to/file')"
        result = "ok"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None

    def test_shutil_rmtree_returns_none(self):
        code = "shutil.rmtree('/path/to/dir')"
        result = "ok"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None

    def test_unknown_code_returns_none(self):
        code = "some_unknown_function()"
        result = "ok"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None

    def test_read_only_code_returns_none(self):
        code = "print([str(l.name) for l in ws.libraries])"
        result = "['Default Library', 'VFX']"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None


class TestUndoCodeGeneratorMove:
    """Move operations produce move-back undo code when source/dest are captured."""

    def test_move_with_source_dest_in_result(self):
        code = "shutil.move('/src/file.exr', '/dst/file.exr')"
        result = "Moved from /src/file.exr to /dst/file.exr"
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is not None
        assert "/src/file.exr" in undo
        assert "/dst/file.exr" in undo
        assert "shutil.move" in undo

    def test_move_without_result_info_returns_none(self):
        code = "shutil.move('/src/file.exr', '/dst/file.exr')"
        result = "ok"  # No move confirmation — cannot determine original path
        undo = UndoCodeGenerator.generate_undo(code, result)

        assert undo is None
