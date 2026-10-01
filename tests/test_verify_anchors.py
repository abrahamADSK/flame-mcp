"""verify_anchors — READ-ONLY anchor report for a conformed sequence (Chat 108).

Covers the plan schema, the registry, the verdict formatter and the bridge
payload parsing. The in-Flame code itself is only checked statically here
(it compiles, runs on the main thread, writes nothing); it is exercised
in-vivo against a live Flame.
"""

import json
import re
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import flame_mcp.server as srv
from flame_mcp import _plan_schema as plan


def _seg(src, source_in, start, rec=0, tc="00:00:40:01", media_first=1001):
    return {"version": 0, "track": 0, "source": src, "record_in": rec,
            "file_path": f"/proj/{src}/CMP_v001/{src}_CMP_v001.{media_first}.exr",
            "source_in": source_in, "source_in_tc": tc, "start_frame": start}


DATA_OK = {"sequence": "Master v1", "location": "desktop Desktop / Reel 1",
           "segments": [_seg("SEQ003_SH001", 1001, 1001), _seg("SEQ003_SH002", 1001, 1001, rec=100)]}


class TestSchemaAndRegistry:

    def test_registered_as_read_only_plan_op(self):
        assert "verify_anchors" in plan.op_names()
        assert plan.op_tool("verify_anchors") == "execute_plan"
        assert "READ-ONLY" in plan._OP_REGISTRY["verify_anchors"]["description"]

    def test_valid_plan(self):
        ops = plan.validate_plan({"ops": [{"op": "verify_anchors",
                                           "args": {"sequence_name": "Master v1"}}]})
        assert ops[0][0] == "verify_anchors"

    @pytest.mark.parametrize("args", [{}, {"sequence_name": ""},
                                      {"sequence_name": "x", "fix": True}])
    def test_invalid_args_rejected(self, args):
        with pytest.raises(plan.PlanValidationError):
            plan.validate_plan({"ops": [{"op": "verify_anchors", "args": args}]})

    def test_args_model_forbids_extras(self):
        with pytest.raises(ValidationError):
            plan.VerifyAnchorsArgs(sequence_name="x", repair=True)


class TestVerdict:

    def test_all_anchored(self):
        out = srv._format_anchor_report(DATA_OK)
        head = out.splitlines()[0]
        assert head.startswith("ANCHORS:") and "2 OK" in head and head.endswith("-> OK")
        assert "re-lay" not in out

    def test_zero_anchor_is_damaged_and_names_the_repair(self):
        data = dict(DATA_OK, segments=[_seg("SH001", 1001, 1001), _seg("SH002", 0, 1001, tc="00:00:00:00")])
        out = srv._format_anchor_report(data)
        assert "1 DAMAGED" in out.splitlines()[0] and out.splitlines()[0].endswith("-> DAMAGED")
        assert "SH002: source_in 0 (00:00:00:00) vs media first frame 1001 -> DAMAGED" in out
        assert "PySequence.overwrite" in out

    def test_other_offset_is_a_mismatch(self):
        data = dict(DATA_OK, segments=[_seg("SH001", 1009, 1001)])
        out = srv._format_anchor_report(data)
        assert "1 MISMATCH" in out and out.splitlines()[0].endswith("-> DAMAGED")

    def test_anchor_is_judged_against_the_media_not_start_frame(self):
        """In-vivo Chat 108: SEQ003_SH002 had source_in 1001 and media from
        frame 1001, but start_frame 2002 (it follows the current version).
        That segment is anchored — the odd start_frame is a WARNING."""
        data = dict(DATA_OK, segments=[_seg("SEQ003_SH002", 1001, 2002)])
        out = srv._format_anchor_report(data)
        head = out.splitlines()[0]
        assert "1 OK" in head and "-> OK" in head and "1 WARNING" in head
        assert "start_frame 2002" in out and "re-lay" not in out

    def test_falls_back_to_start_frame_without_a_frame_number(self):
        seg = dict(_seg("SH001", 1001, 1001), file_path="/proj/SH001/movie.mov")
        assert "-> OK" in srv._format_anchor_report(dict(DATA_OK, segments=[seg])).splitlines()[0]

    def test_not_found_and_ambiguous(self):
        assert srv._format_anchor_report({"error": "sequence not found: X"}).startswith("ERROR:")
        out = srv._format_anchor_report({"error": "sequence name is ambiguous: X",
                                         "locations": ["library A / R", "desktop D / R"]})
        assert "library A / R; desktop D / R" in out

    def test_no_segments(self):
        out = srv._format_anchor_report({"sequence": "S", "location": "L", "segments": []})
        assert "NOTHING TO CHECK" in out


class TestBridgeRoundTrip:

    def test_parses_marker_payload(self):
        fake = {"status": "ok", "output": "ANCHORS_JSON " + json.dumps(DATA_OK) + "\n"}
        with patch.object(srv, "_call_flame", return_value=fake) as call:
            out = srv._verify_anchors_impl("Master v1")
        assert out.startswith("ANCHORS:")
        _, kwargs = call.call_args
        assert kwargs["dedicated_tool"] is True  # skips the desktop redirect

    def test_name_is_injected_as_a_literal(self):
        with patch.object(srv, "_call_flame", return_value={"status": "ok", "output": "x"}) as call:
            srv._verify_anchors_impl("Master \"v1\"")
        code = call.call_args[0][0]
        assert "SEQ_NAME = 'Master \"v1\"'" in code

    def test_bridge_error_passes_through(self):
        with patch.object(srv, "_call_flame", return_value={"status": "error", "error": "boom"}):
            assert srv._verify_anchors_impl("S").startswith("ERROR:")


class TestBridgeCodeIsReadOnly:

    CODE = srv._VERIFY_ANCHORS_CODE.replace("__SEQ_NAME__", repr("S"))

    def test_compiles(self):
        compile(self.CODE, "verify_anchors", "exec")

    def test_runs_on_the_main_thread(self):
        assert "flame.schedule_idle_event(_do_read)" in self.CODE

    def test_writes_nothing_to_flame(self):
        forbidden = r"\.(overwrite|insert|delete|save|set_value|update_sources|move|create_|change_start_frame|slip)\b|flame\.delete"
        assert not re.search(forbidden, self.CODE), re.search(forbidden, self.CODE)
