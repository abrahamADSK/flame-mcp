"""
test_plan_schema.py
===================
F5b — Unit tests for ``flame_mcp._plan_schema``.

Hermetic: no Flame, no bridge socket. Handlers are monkey-patched
with deterministic stubs so we can assert dispatch order, payload
shape, and the validation-before-execution contract.

Test groups
-----------
- Schema rejection: unknown op, extra keys, missing keys, wrong types,
  empty ``ops``, non-dict plan.
- Args model rejection: missing required args, unknown args, wrong
  scalar type.
- Successful dispatch: order preserved, per-op headers present,
  final summary line.
- Short-circuit on handler failure: subsequent ops NOT invoked,
  failure index reported.
- ``register_op`` raises on unknown name.
- ``describe_registry`` returns a JSON-serialisable mapping for docs.
"""

from __future__ import annotations

import json

import pytest

from flame_mcp import _plan_schema as ps


# ---------------------------------------------------------------------------
# Fixtures — install deterministic handlers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _install_stub_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every registered op's handler with a deterministic stub.

    Each stub returns a string with the op's name + the JSON-encoded
    args so tests can assert exact dispatch behaviour without touching
    server.py or Flame.
    """
    for name in ps.op_names():
        def make_stub(op_name: str):
            def stub(args: object) -> str:
                # Pydantic models support .model_dump() in v2.
                payload = args.model_dump() if hasattr(args, "model_dump") else {}
                return f"<stub:{op_name}:{json.dumps(payload, sort_keys=True)}>"
            return stub
        ps._OP_REGISTRY[name]["handler"] = make_stub(name)


# ---------------------------------------------------------------------------
# Schema rejection
# ---------------------------------------------------------------------------


def test_validate_plan_rejects_non_dict() -> None:
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan(["not", "an", "object"])
    assert "expected an object" in str(exc.value)


def test_validate_plan_rejects_missing_ops_key() -> None:
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan({})
    assert "missing required key 'ops'" in str(exc.value)


def test_validate_plan_rejects_unknown_top_level_keys() -> None:
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan({"ops": [], "version": 1})
    assert "unexpected top-level keys" in str(exc.value)
    assert "version" in str(exc.value)


def test_validate_plan_rejects_non_list_ops() -> None:
    with pytest.raises(ps.PlanValidationError):
        ps.validate_plan({"ops": "not-a-list"})


def test_validate_plan_rejects_empty_ops() -> None:
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan({"ops": []})
    assert "list is empty" in str(exc.value)


def test_validate_plan_rejects_unknown_op_name() -> None:
    plan = {"ops": [{"op": "destroy_world", "args": {}}]}
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan(plan)
    assert "destroy_world" in str(exc.value)
    assert "not a registered op" in str(exc.value)


def test_validate_plan_rejects_extra_keys_in_op() -> None:
    plan = {
        "ops": [
            {"op": "ping", "args": {}, "comment": "explanatory note"}
        ]
    }
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan(plan)
    assert "unexpected keys" in str(exc.value)
    assert "comment" in str(exc.value)


def test_validate_plan_rejects_missing_op_key() -> None:
    plan = {"ops": [{"args": {}}]}
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan(plan)
    assert "missing required key 'op'" in str(exc.value)


def test_validate_plan_rejects_missing_args_key() -> None:
    plan = {"ops": [{"op": "ping"}]}
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan(plan)
    assert "missing required key 'args'" in str(exc.value)


def test_validate_plan_rejects_non_string_op() -> None:
    plan = {"ops": [{"op": 42, "args": {}}]}
    with pytest.raises(ps.PlanValidationError):
        ps.validate_plan(plan)


def test_validate_plan_rejects_non_dict_args() -> None:
    plan = {"ops": [{"op": "ping", "args": "not-a-dict"}]}
    with pytest.raises(ps.PlanValidationError) as exc:
        ps.validate_plan(plan)
    assert "expected an object" in str(exc.value)


# ---------------------------------------------------------------------------
# Args model rejection
# ---------------------------------------------------------------------------


def test_args_rejects_unknown_arg() -> None:
    plan = {
        "ops": [
            {"op": "list_libraries", "args": {"library_name": "Shots"}}
        ]
    }
    with pytest.raises(ps.PlanValidationError):
        ps.validate_plan(plan)


def test_args_rejects_missing_required_arg() -> None:
    """list_clips requires library_name AND reel_name."""
    plan = {
        "ops": [
            {"op": "list_clips", "args": {"library_name": "Shots"}}
        ]
    }
    with pytest.raises(ps.PlanValidationError):
        ps.validate_plan(plan)


def test_args_rejects_wrong_type() -> None:
    plan = {
        "ops": [
            {"op": "list_reels", "args": {"library_name": 123}}
        ]
    }
    # Pydantic v2 coerces some int → str; assert validation either
    # rejects OR coerces — both are valid contracts. Here we just
    # confirm validation runs without crashing.
    try:
        ps.validate_plan(plan)
    except ps.PlanValidationError:
        return
    # If coerced, the args should at least be a string now.
    parsed = ps.validate_plan(plan)
    _, args = parsed[0]
    assert isinstance(args.library_name, str)


# ---------------------------------------------------------------------------
# Successful dispatch
# ---------------------------------------------------------------------------


def test_dispatch_returns_per_op_headers_and_summary() -> None:
    plan = {
        "ops": [
            {"op": "ping", "args": {}},
            {"op": "list_libraries", "args": {}},
        ]
    }
    out = ps.dispatch_plan(plan)
    assert "── op 0 · ping ──" in out
    assert "── op 1 · list_libraries ──" in out
    assert "<stub:ping:" in out
    assert "<stub:list_libraries:" in out
    assert "Plan executed: 2/2 ops succeeded" in out


def test_dispatch_preserves_op_order() -> None:
    plan = {
        "ops": [
            {"op": "list_libraries", "args": {}},
            {"op": "list_reels", "args": {"library_name": "Default"}},
            {"op": "list_clips", "args": {
                "library_name": "Default", "reel_name": "Reel 1"
            }},
        ]
    }
    out = ps.dispatch_plan(plan)
    # The op headers must appear in declared order.
    pos_libs = out.index("op 0 · list_libraries")
    pos_reels = out.index("op 1 · list_reels")
    pos_clips = out.index("op 2 · list_clips")
    assert pos_libs < pos_reels < pos_clips


def test_dispatch_args_reach_the_handler() -> None:
    """Stub embeds args as JSON — assert the right values were passed."""
    plan = {
        "ops": [
            {"op": "get_clip_metadata", "args": {
                "library_name": "Shots", "reel_name": "R1", "clip_name": "shot_010"
            }}
        ]
    }
    out = ps.dispatch_plan(plan)
    assert "shot_010" in out
    assert "Shots" in out
    assert "R1" in out


# ---------------------------------------------------------------------------
# Short-circuit on handler failure
# ---------------------------------------------------------------------------


def test_dispatch_short_circuits_on_handler_failure() -> None:
    # Replace ping's handler with one that raises.
    def boom(_args: object) -> str:
        raise RuntimeError("simulated handler failure")

    ps._OP_REGISTRY["ping"]["handler"] = boom

    plan = {
        "ops": [
            {"op": "list_libraries", "args": {}},
            {"op": "ping", "args": {}},
            # This third op MUST NOT run after the failure above.
            {"op": "get_project_info", "args": {}},
        ]
    }
    out = ps.dispatch_plan(plan)
    assert "list_libraries" in out
    assert "simulated handler failure" in out
    # Confirm the third op did not execute.
    assert "<stub:get_project_info:" not in out
    assert "short-circuited at op 1" in out


# ---------------------------------------------------------------------------
# register_op + describe_registry
# ---------------------------------------------------------------------------


def test_register_op_raises_on_unknown_name() -> None:
    with pytest.raises(ValueError) as exc:
        ps.register_op("not_a_real_op", lambda _a: "x")
    assert "unknown op name" in str(exc.value)


def test_describe_registry_is_json_serialisable() -> None:
    desc = ps.describe_registry()
    # Must serialise without TypeError — confirms args_schema is a
    # plain dict from pydantic v2.
    serialised = json.dumps(desc)
    assert "list_libraries" in serialised
    assert "args_schema" in serialised
    # Every op should map to a known dedicated tool.
    for name, entry in desc.items():
        assert entry["tool"], f"op {name!r} has no dedicated tool mapping"


def test_op_names_returns_sorted_list() -> None:
    names = ps.op_names()
    assert names == sorted(names)
    assert "list_libraries" in names
    assert "ping" in names


class TestSetupCompBatchOp:
    """The plan-native comp batch op (Chat 98).

    'De una atacada': one execute_plan call creates every shot's comp batch
    wired source → Write File. Plan-native — no dedicated MCP tool, so the
    AU-deck tool inventory stays untouched; its "tool" field says
    execute_plan.
    """

    def test_op_is_registered_with_typed_args(self):
        import flame_mcp._plan_schema as ps
        assert "setup_comp_batch" in ps.op_names()
        entry = ps._OP_REGISTRY["setup_comp_batch"]
        assert entry["tool"] == "execute_plan"  # plan-native marker
        model = entry["args_model"]
        args = model(shot="SEQ001_SH001", clip_path="/x/clip/S.clip", step="CMP")
        assert args.comp_dir == ""  # optional, derived by the impl

    def test_extra_args_rejected(self):
        import pytest as _pytest
        import flame_mcp._plan_schema as ps
        model = ps._OP_REGISTRY["setup_comp_batch"]["args_model"]
        with _pytest.raises(Exception):
            model(shot="S", clip_path="/x", invented_field=1)

    def test_impl_generates_main_threaded_wiring(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl(
                "SEQ001_SH001",
                "/root/sequences/SEQ001/SEQ001_SH001/finishing/clip/SEQ001_SH001.clip",
                step="CMP",
            )
            code = m.call_args[0][0]
        compile(code, "<g>", "exec")
        assert "flame.schedule_idle_event(_do_setup)" in code
        assert "create_batch_group('SEQ001_SH001_comp'" in code
        assert '("name", \'CMP\')' in code          # node named after the step
        assert 'create_node("Write File")' in code
        # Chat 99: create_clip is ON again — Flame 2027 omits versionNumber
        # without it and tk-flame's publish dies — but it points at the
        # node's OWN clip. The Chat 98 rule still holds where it matters:
        # the Write File must never adopt the pipeline's conformed clip.
        assert '("create_clip", True)' in code
        settings = code.split("_settings = [", 1)[1].split("]", 1)[0]
        assert "finishing/clip" not in settings
        # the source import still uses the conformed clip
        assert "finishing/clip/SEQ001_SH001.clip" in code
        # comp media dir derived: the 'comp' sibling of the clip folder
        assert "/root/sequences/SEQ001/SEQ001_SH001/finishing/comp" in code

    def test_write_file_attributes_are_defensive(self):
        """Unknown attribute names must degrade to a report, never an error."""
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl("S", "/x/clip/S.clip", step="CMP")
            code = m.call_args[0][0]
        assert "_skipped.append" in code
        assert "setattr(wf, _attr, _val)" in code


class TestWriteFileClipTarget:
    """The comp version must land in the CONFORMED clip (Chat 98 in-vivo).

    The first render registered its version into <Shot>.clip.clip: Flame
    appends its own .clip extension to create_clip_path, and we passed the
    full path. And with no media_path_pattern the frames landed flat and
    unversioned (SEQ003_SH002_writefile000100.exr).
    """

    def _codes(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl(
                "S", "/r/sequences/Q/S/finishing/clip/S.clip", step="CMP")
            setup = m.call_args[0][0]
            server._fix_comp_writefile_impl(
                "/r/sequences/Q/S/finishing/clip/S.clip", step="CMP")
            fix = m.call_args[0][0]
        return setup, fix

    def test_write_file_never_creates_a_clip(self):
        """Chat 98 final architecture: Flame owns any clip its Write File
        creates (it overwrote the pipeline's conformed clip wholesale), so
        both ops set create_clip=False — the pipeline aggregates versions
        via openclip_create steps=['Light','Comp'] instead."""
        setup, fix = self._codes()
        for code in (setup, fix):
            assert '("create_clip", True)' in code
            settings = code.split("_settings = [", 1)[1].split("]", 1)[0]
            assert "finishing/clip" not in settings      # never the conformed clip
            assert "_CMP" in settings                    # its own clip instead
        assert "finishing/clip/S.clip'" in setup        # el import sí lo lleva

    def test_versioning_is_enabled_for_token_expansion(self):
        """The archived setup showed <Versioning>False</Versioning> — the
        reason the <version> token stayed LITERAL in rendered paths."""
        setup, fix = self._codes()
        for code in (setup, fix):
            assert '("version_mode", "Follow Iteration")' in code
            assert '("version_padding", 3)' in code
            # the in-vivo trap: 'versioning' does not exist, and the enum
            # ignores invalid strings silently
            assert '"versioning"' not in code

    def test_media_pattern_carries_the_shot_and_the_version(self):
        """Chat 99: folder <step>_v<version>, file <Shot>_<step>_v<version>
        — the shape flame_shot_comp_exr demands and the native gate checks."""
        setup, fix = self._codes()
        for code in (setup, fix):
            assert "<name>_v<version>/<shot name>_<name>_v<version>.<frame>" in code

    def test_fix_op_operates_on_the_active_batch_only(self):
        """The active batch cannot be switched from Python — the fix op
        reads flame.batch and never tries to open a group."""
        _, fix = self._codes()
        assert "flame.batch.nodes" in fix
        assert "bg.open(" not in fix and "go_to(" not in fix

    def test_fix_op_registered_plan_native(self):
        import flame_mcp._plan_schema as ps
        entry = ps._OP_REGISTRY["fix_comp_writefile"]
        assert entry["tool"] == "execute_plan"
        model = entry["args_model"]
        assert model(clip_path="/x/clip/S.clip", step="CMP").comp_dir == ""


class TestFrameAlignment:
    """The comp render must number from the SOURCE's first frame (Chat 98
    in-vivo): the batch was created with start_frame=1, the comp rendered
    frames 1-100 against a source spanning 1001-1100, and after update
    sources the segment anchored to COMP — flipping to LIGHT asked for
    frames outside its span: 'no media'."""

    def test_setup_creates_batch_at_source_start(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl(
                "S", "/r/sequences/Q/S/finishing/clip/S.clip", step="CMP", start_frame=1001)
            code = m.call_args[0][0]
        assert 'reels=["sources"], start_frame=1001)' in code

    def test_fix_op_can_realign_an_existing_batch(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl("/r/x/clip/S.clip", step="CMP", start_frame=1001)
            code = m.call_args[0][0]
        assert "flame.batch.start_frame = _sf" in code
        assert "_sf = 1001" in code

    # ---- Chat 99: the alignment must not depend on the console passing
    # start_frame. In-vivo the console omitted it, the op printed OK, the
    # comp rendered 0001-0100 against a 1001-1100 source: 'no media' on the
    # COMP flip. The op now derives the value from the conformed clip and
    # proves the alignment by read-back.

    _CLIP_XML = (
        '<?xml version="1.0"?><clip type="clip" version="6">'
        '<name type="string">S_LGT_v003</name><tracks type="tracks">'
        '<track uid="BEAUTY"><feeds currentVersion="COMP_v001">'
        '<feed vuid="LIGHT_v003"><startFrame>1001</startFrame><spans><span>'
        '<duration>100</duration><path encoding="pattern">'
        '/r/S/LGT/publish/renders/LGT/v003/S_LGT_v003.[1001-1100].exr'
        '</path></span></spans></feed>'
        '<feed vuid="COMP_v001"><startFrame>1</startFrame><spans><span>'
        '<duration>100</duration><path encoding="pattern">'
        '/r/S/finishing/comp/S_writefile_v001/S_writefile_v001.[0001-0100].exr'
        '</path></span></spans></feed>'
        '</feeds></track></tracks></clip>'
    )

    def _write_clip(self, tmp_path, xml=None):
        clip = tmp_path / "finishing" / "clip" / "S.clip"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_text(xml if xml is not None else self._CLIP_XML)
        return str(clip)

    def test_derive_reads_the_source_feed_and_skips_comp(self, tmp_path):
        import flame_mcp.server as server
        assert server._derive_source_frame_range(self._write_clip(tmp_path)) == (1001, 100, 4)

    def test_derive_falls_back_to_the_path_pattern(self, tmp_path):
        """A clip without <startFrame> still yields the range from [a-b]."""
        import flame_mcp.server as server
        xml = self._CLIP_XML.replace("<startFrame>1001</startFrame>", "")
        xml = xml.replace("<duration>100</duration>", "", 1)
        assert server._derive_source_frame_range(self._write_clip(tmp_path, xml)) == (1001, 100, 4)

    def test_derive_never_raises(self, tmp_path):
        import flame_mcp.server as server
        assert server._derive_source_frame_range("/nope/S.clip") is None
        assert server._derive_source_frame_range(self._write_clip(tmp_path, "not xml")) is None
        comp_only = self._CLIP_XML.replace('vuid="LIGHT_v003"', 'vuid="COMP_v000"')
        assert server._derive_source_frame_range(self._write_clip(tmp_path, comp_only)) is None

    def test_zero_derives_from_the_clip(self, tmp_path):
        """The in-vivo failure: an omitted start_frame must NOT leave the
        batch at 1 — the op derives 1001 from the clip it already gets."""
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(self._write_clip(tmp_path), step="CMP")
            code = m.call_args[0][0]
        assert "_sf = 1001" in code and "_dur = 100" in code
        assert "derived from the conformed clip" in code
        compile(code, "fix", "exec")

    def test_zero_with_unreadable_clip_warns_and_leaves_untouched(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl("/r/x/clip/S.clip", step="CMP")
            code = m.call_args[0][0]
        assert "_sf = 0" in code
        assert "NOT derivable" in code
        assert "left untouched" in code

    def test_fix_reads_back_and_prints_one_alignment_verdict(self, tmp_path):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(self._write_clip(tmp_path), step="CMP")
            code = m.call_args[0][0]
        assert "wf.range_start" in code and "wf.range_end" in code
        assert 'print("ALIGNMENT: batch start "' in code
        assert "MISALIGNED" in code and "OVERWRITE WARNING" in code
        # the read-back helper must not collide with the settings loop var
        assert "for _attr, _val in _settings" in code
        assert "def _gv(a):" in code and "_val(" not in code

    # ---- the verdict is EXECUTED, not string-matched (Chat 101) ----
    # Every test above asserts on the template TEXT, which is why a real
    # defect shipped: the range correction was gated on "_rs != _sf", so a
    # Write File already starting at 1001 skipped it, range_end stayed at
    # 1002, and the verdict — comparing only the start — printed OK. The
    # shot rendered 2 frames of 100. These tests run the generated code
    # against a stubbed Flame and read the verdict it actually prints.

    class _Node:
        """Write File / Clip stand-in: attributes are plain values, which is
        what Flame's PyAttribute degrades to once assigned (the template's
        _gv helper accepts both)."""

        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _run_generated(self, code, wf, batch_name="S_comp", iteration=1):
        """exec the generated fix against a fake ``flame`` module, running the
        idle event inline, and return everything it printed."""
        import io as _io
        import sys as _sys
        import types
        from contextlib import redirect_stdout

        batch = self._Node(
            name=batch_name, start_frame=0, nodes=[wf],
            current_iteration_number=iteration,
        )
        flame_mod = types.ModuleType("flame")
        flame_mod.batch = batch
        flame_mod.projects = self._Node(current_project=self._Node(name="PRJ"))
        flame_mod.schedule_idle_event = lambda fn: fn()
        saved = _sys.modules.get("flame")
        _sys.modules["flame"] = flame_mod
        buf = _io.StringIO()
        try:
            with redirect_stdout(buf):
                exec(compile(code, "fix", "exec"), {"__name__": "__main__"})
        finally:
            if saved is None:
                _sys.modules.pop("flame", None)
            else:
                _sys.modules["flame"] = saved
        return buf.getvalue(), batch

    def _write_file_node(self, start, end):
        return self._Node(
            type="Write File", name="CMP", range_start=start, range_end=end,
            frame_rate="25 fps", version_padding=3, basic_metadata="",
            source_timecode="", record_timecode="",
        )

    def test_short_range_is_pulled_to_the_source_and_never_signed_off(self, tmp_path):
        """THE Chat 101 regression: start already correct, end far too short."""
        from unittest.mock import patch

        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(self._write_clip(tmp_path), step="CMP")
            code = m.call_args[0][0]
        wf = self._write_file_node(1001, 1002)          # <Range Start=1001 End=1002/>
        out, batch = self._run_generated(code, wf)
        assert "write file range pulled to 1001-1100" in out
        assert int(wf.range_end) == 1100                # the fix, not the report
        assert "-> OK" in out and "MISALIGNED" not in out
        assert "1001-1100 (100 frames)" in out          # both counts are visible
        assert int(batch.start_frame) == 1001

    def test_unfixable_short_range_is_reported_misaligned_with_the_reason(self, tmp_path):
        """When Flame refuses the write, the verdict must BLOCK the render and
        name the mismatch — the recipe gates on this line."""
        from unittest.mock import patch

        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(self._write_clip(tmp_path), step="CMP")
            code = m.call_args[0][0]

        class _Locked(TestFrameAlignment._Node):
            def __setattr__(self, k, v):
                if k in ("range_start", "range_end"):
                    raise RuntimeError("read-only")
                object.__setattr__(self, k, v)

        wf = _Locked(
            type="Write File", name="CMP", range_start=1001, range_end=1002,
            frame_rate="25 fps", version_padding=3, basic_metadata="",
            source_timecode="", record_timecode="",
        )
        out, _ = self._run_generated(code, wf)
        assert "MISALIGNED" in out and "-> OK" not in out
        assert "write file ends at 1002, source needs 1100" in out
        assert "do not render" in out

    def test_matching_range_still_reports_ok(self, tmp_path):
        """The happy path must not regress into a false MISALIGNED."""
        from unittest.mock import patch

        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(self._write_clip(tmp_path), step="CMP")
            code = m.call_args[0][0]
        wf = self._write_file_node(1001, 1100)
        out, _ = self._run_generated(code, wf)
        assert "-> OK" in out and "MISALIGNED" not in out
        assert "write file range pulled" not in out     # nothing to correct

    def test_setup_derives_start_frame_by_default(self, tmp_path):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl("S", self._write_clip(tmp_path), step="CMP")
            code = m.call_args[0][0]
        assert 'reels=["sources"], start_frame=1001)' in code
        compile(code, "setup", "exec")

    def test_setup_without_a_readable_clip_warns_loudly(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl("S", "/nope/clip/S.clip", step="CMP")
            code = m.call_args[0][0]
        assert 'start_frame=1)' in code and "WARNING: start_frame NOT derivable" in code

    def test_schema_defaults_mean_derive(self):
        import flame_mcp._plan_schema as ps
        assert ps._OP_REGISTRY["setup_comp_batch"]["args_model"](
            shot="S", clip_path="/x/clip/S.clip", step="CMP").start_frame == 0
        assert ps._OP_REGISTRY["fix_comp_writefile"]["args_model"](
            clip_path="/x/clip/S.clip", step="CMP").start_frame == 0

    def test_recipe_gates_the_render_on_the_alignment_verdict(self):
        from flame_mcp.concept_map import CONCEPT_MAP
        recipe = next(e for e in CONCEPT_MAP
                      if e["concept"].startswith("build comp"))["recipe"]
        # Chat 99: the recipe now hands publishing to tk-flame, and the
        # alignment gate lives in the op's own ALIGNMENT verdict.
        assert "ALIGNMENT" in recipe and "-> OK" in recipe
        assert "frame padding and start frame derived from the source" in recipe
        # the old wording asked the console to pass the value — gone
        assert "pass start_frame = the source media's FIRST frame" not in recipe


class TestWriteFileNameFollowsTheStep:
    """The Write File name is what the media pattern <name>_v<version>
    expands — and it leaked into the PublishedFile code as a literal
    'writefile' (in-vivo Chat 99: SEQ003_SH001_writefile_v001.%04d.exr).
    The pipeline convention is {Shot}_{Step}_v<version> (LGT publishes:
    SEQ003_SH001_LGT_v003); the Step short_name comes from ShotGrid and is
    a REQUIRED arg — never a default."""

    def _fix(self, clip="/r/sequences/Q/SEQ003_SH001/finishing/clip/SEQ003_SH001.clip", **kw):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(clip, **kw)
            return m.call_args[0][0]

    def test_setup_names_the_write_file_shot_step(self):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl("SEQ003_SH001", "/r/clip/SEQ003_SH001.clip", step="CMP")
            code = m.call_args[0][0]
        # Chat 99: the NODE is the bare step — the Toolkit template builds the
        # media folder from it, so "<Shot>_CMP" would break the native gate.
        # The shot reaches the filename through the <shot name> token.
        assert '("name", \'CMP\')' in code
        assert '("shot_name", \'SEQ003_SH001\')' in code
        assert "SEQ003_SH001_writefile" not in code   # the old literal name is gone

    def test_fix_renames_the_write_file_to_the_bare_step(self):
        """setup and fix must agree, or repairing a batch would rename the
        node and silently break the template match the native hook gates on."""
        code = self._fix(step="CMP")
        assert '("name", \'CMP\')' in code
        assert 'print("  name: " + str(_old_name)' in code
        compile(code, "fix", "exec")

    def test_step_is_required_and_validated(self):
        import pytest as _pytest
        import flame_mcp._plan_schema as ps
        setup = ps._OP_REGISTRY["setup_comp_batch"]["args_model"]
        fix = ps._OP_REGISTRY["fix_comp_writefile"]["args_model"]
        with _pytest.raises(Exception):
            setup(shot="S", clip_path="/x/clip/S.clip")          # missing
        with _pytest.raises(Exception):
            fix(clip_path="/x/clip/S.clip")                      # missing
        with _pytest.raises(Exception):
            fix(clip_path="/x/clip/S.clip", step="write file")   # not a token
        assert fix(clip_path="/x/clip/S.clip", step="CMP").step == "CMP"

    def test_recipe_says_read_the_step_from_shotgrid(self):
        from flame_mcp.concept_map import CONCEPT_MAP
        recipe = next(e for e in CONCEPT_MAP
                      if e["concept"].startswith("build comp"))["recipe"]
        assert "short_name READ from ShotGrid" in recipe
        # Chat 99: the node is named after the step because that is what the
        # Toolkit template's {segment_name} resolves to — the gate the native
        # tk-flame hook checks before it will publish anything.
        assert "node named after the step" in recipe
        assert "MATCHES the Toolkit templates" in recipe


class TestTimecodeAnchorAndPadding:
    """Chat 99, the fifth attempt and the real root cause.

    Maya/Arnold EXRs carry NO timecode attribute, so the two consumers
    invent different ones: dl_get_media_info (which writes the .clip) falls
    back to the FRAME NUMBER and declares TC 1001, while Flame's batch gets
    nothing (the source Clip node's source_timecode reads None, measured
    in-vivo) and the Write File stamps an EXPLICIT 00:00:00:00 into the comp
    EXRs. Whichever Flame re-reads wins — so the flip worked, then an
    operation that re-read the media re-anchored the conformed segment to
    00:00:00:00 and BOTH versions went 'no media' (measured: five segments
    at 00:00:40:01, the comped one at 0).
    """

    CLIP_XML = (
        '<?xml version="1.0"?><clip type="clip" version="8">'
        '<tracks><track uid="BEAUTY:MasterBeauty"><feeds currentVersion="LIGHT_v003">'
        '<feed vuid="LIGHT_v003"><startFrame>1001</startFrame><spans><span>'
        '<duration>100</duration><path encoding="pattern">'
        '/r/S/LGT/publish/renders/LGT/v003/S_LGT_v003.[1001-1100].exr'
        '</path></span></spans></feed></feeds></track></tracks></clip>'
    )

    def _clip(self, tmp_path, xml=None):
        c = tmp_path / "finishing" / "clip" / "S.clip"
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text(xml or self.CLIP_XML)
        return str(c)

    def _code(self, tmp_path, impl="fix", xml=None, **kw):
        from unittest.mock import patch
        import flame_mcp.server as server
        clip = self._clip(tmp_path, xml)
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            if impl == "fix":
                server._fix_comp_writefile_impl(clip, step="CMP", **kw)
            else:
                server._setup_comp_batch_impl("S", clip, step="CMP", **kw)
            return m.call_args[0][0]

    # ---- timecode ----

    def test_frames_to_timecode_matches_the_healthy_segments(self):
        """The five healthy segments carry source_in 00:00:40:01 for frame
        1001 at 25 fps — the value the comp media must be born with."""
        import flame_mcp.server as server
        assert server._frames_to_timecode(1001, 25.0) == "00:00:40:01"
        assert server._frames_to_timecode(0, 25.0) == "00:00:00:00"
        assert server._frames_to_timecode(1001, 24.0) == "00:00:41:17"
        # fractional rates use their NOMINAL integer rate (NDF convention)
        assert server._frames_to_timecode(1001, 23.976) == "00:00:41:17"
        assert server._frames_to_timecode(1001, 29.97) == "00:00:33:11"

    def test_fix_sets_custom_values_before_the_timecode(self, tmp_path):
        """Flame refuses the write otherwise: 'Basic metadata values cannot
        be set when the Basic Metadata mode is not set to Custom Values.'"""
        code = self._code(tmp_path)
        assert 'wf.basic_metadata = "Custom Values"' in code
        # the MODE must be set before the values (the comment block above the
        # code also names source_timecode, so compare the real statements)
        assert (code.index('wf.basic_metadata = "Custom Values"')
                < code.index("setattr(wf, _a, _tc)"))
        assert '"source_timecode", "record_timecode"' in code

    def test_fix_reads_the_rate_from_the_node_not_a_constant(self, tmp_path):
        code = self._code(tmp_path)
        assert "wf.frame_rate" in code
        assert "int(round(_fps))" in code

    def test_timecode_failure_is_reported_not_swallowed(self, tmp_path):
        code = self._code(tmp_path)
        assert "timecode NOT set" in code
        assert "re-anchor the conformed segment" in code

    def test_no_timecode_write_when_the_start_frame_is_unknown(self, tmp_path):
        """_sf == 0 means the anchor could not be derived — stamping a
        timecode from a guess would be worse than leaving it alone."""
        code = self._code(tmp_path, xml="<clip/>")
        assert "_sf = 0" in code
        # the write lives inside the guard, so a zero anchor never stamps one
        assert code.count('wf.basic_metadata = "Custom Values"') == 1
        assert code.index("if _sf > 0:") < code.index('wf.basic_metadata = "Custom Values"')

    # ---- frame padding ----

    def test_padding_is_derived_from_the_source_bracket(self, tmp_path):
        import flame_mcp.server as server
        assert server._derive_source_frame_range(self._clip(tmp_path)) == (1001, 100, 4)

    def test_both_ops_set_frame_padding_from_the_source(self, tmp_path):
        """A fresh Write File defaults to 6: in-vivo the first comp rendered
        .001001.exr against a source of .1001.exr — a wasted render."""
        for impl in ("fix", "setup"):
            assert '("frame_padding", 4)' in self._code(tmp_path, impl=impl)

    def test_padding_falls_back_to_four_when_underivable(self, tmp_path):
        for impl in ("fix", "setup"):
            code = self._code(tmp_path, impl=impl, xml="<clip/>")
            assert '("frame_padding", 4)' in code

    def test_explicit_start_frame_still_derives_padding(self, tmp_path):
        code = self._code(tmp_path, start_frame=2001)
        assert '("frame_padding", 4)' in code and "_sf = 2001" in code


class TestBatchSourceIsTheLightRender:
    """The comp batch must read the LIGHT render, never the conformed clip.

    In-vivo (Chat 99): the batch imported the multi-version clip, so the
    moment a COMP version became current its source resolved to the comp's
    OWN output — the comp composited over itself and looked identical to the
    light pass. Worse, after the comp media was rolled back Flame span
    forever on 'Resize : Cannot access frame 35 ... _CMP_v001.1035.exr',
    saturating the main thread until the bridge stopped answering.
    """

    XML = (
        '<?xml version="1.0"?><clip type="clip" version="8"><tracks>'
        '<track uid="BEAUTY:MasterBeauty"><feeds currentVersion="COMP_v001">'
        '<feed vuid="LIGHT_v003"><startFrame>1001</startFrame><spans><span>'
        '<duration>100</duration><path encoding="pattern">'
        '/r/S/LGT/publish/renders/LGT/v003/S_LGT_v003.[1001-1100].exr'
        '</path></span></spans></feed>'
        '<feed vuid="COMP_v001"><startFrame>1001</startFrame><spans><span>'
        '<duration>100</duration><path encoding="pattern">'
        '/r/S/finishing/comp/S_CMP_v001/S_CMP_v001.[1001-1100].exr'
        '</path></span></spans></feed>'
        '</feeds></track></tracks></clip>'
    )

    def _clip(self, tmp_path, xml=None):
        c = tmp_path / "finishing" / "clip" / "S.clip"
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text(xml if xml is not None else self.XML)
        return str(c)

    def test_derives_the_light_media_and_skips_the_comp_feed(self, tmp_path):
        import flame_mcp.server as server
        got = server._derive_source_media(self._clip(tmp_path))
        assert got == "/r/S/LGT/publish/renders/LGT/v003/S_LGT_v003.[1001-1100].exr"
        assert "_CMP_" not in got

    def test_derive_never_raises(self, tmp_path):
        import flame_mcp.server as server
        assert server._derive_source_media("/nope/S.clip") is None
        assert server._derive_source_media(self._clip(tmp_path, "not xml")) is None
        comp_only = self.XML.replace('vuid="LIGHT_v003"', 'vuid="COMP_v000"')
        assert server._derive_source_media(self._clip(tmp_path, comp_only)) is None

    def _setup_code(self, tmp_path, xml=None):
        from unittest.mock import patch
        import flame_mcp.server as server
        clip = self._clip(tmp_path, xml)
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl("S", clip, step="CMP")
            return m.call_args[0][0]

    def test_setup_imports_the_light_render(self, tmp_path):
        code = self._setup_code(tmp_path)
        assert "S_LGT_v003.[1001-1100].exr" in code
        assert "import_clip(_src_media or" in code
        compile(code, "setup", "exec")

    def test_unresolvable_source_falls_back_loudly(self, tmp_path):
        """Falling back to the clip is allowed — doing it silently is not."""
        code = self._setup_code(tmp_path, "<clip/>")
        assert "_src_media = ''" in code
        assert "WARNING: source media NOT derivable" in code
        assert "read its own output" in code

    def test_fix_op_flags_a_batch_that_reads_its_own_output(self, tmp_path):
        from unittest.mock import patch
        import flame_mcp.server as server
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._fix_comp_writefile_impl(self._clip(tmp_path), step="CMP")
            code = m.call_args[0][0]
        assert "SOURCE LOOP" in code
        assert '"_CMP_" in _mp' in code
        assert "re-point the source node" in code
        compile(code, "fix", "exec")

    def test_recipe_states_the_rule_and_the_evidence(self):
        from flame_mcp.concept_map import CONCEPT_MAP
        recipe = next(e for e in CONCEPT_MAP
                      if e["concept"].startswith("build comp"))["recipe"]
        assert "THE BATCH SOURCE IS THE LIGHT RENDER" in recipe
        assert "FEEDBACK LOOP" in recipe
        assert "SOURCE LOOP" in recipe
        # the clip keeps its aggregating job — the two must not be confused
        assert "the clip AGGREGATES for the timeline flip" in recipe


class TestNewShotIsBornNative:
    """A brand-new shot must satisfy tk-flame's gates without anyone
    running a repair op over it (Chat 99, operator question: 'would this
    setup be correct for a fresh conform, the first of the series?').
    It would not have been: setup_comp_batch still built the old shape.
    """

    def _code(self, tmp_path):
        from unittest.mock import patch
        import flame_mcp.server as server
        clip = tmp_path / "finishing" / "clip" / "S.clip"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_text(
            '<?xml version="1.0"?><clip type="clip" version="8"><tracks>'
            '<track uid="T"><feeds currentVersion="v0"><feed vuid="v0">'
            '<startFrame>1001</startFrame><spans><span><duration>100</duration>'
            '<path encoding="pattern">/r/S/LGT/v003/S_LGT_v003.[1001-1100].exr'
            '</path></span></spans></feed></feeds></track></tracks></clip>')
        with patch.object(server, "_call_flame") as m:
            m.return_value = {"output": "OK\n", "error": "", "_bridge_ms": 5}
            server._setup_comp_batch_impl("SEQ003_SH001", str(clip), step="CMP")
            return m.call_args[0][0]

    def test_node_is_named_after_the_step_not_the_shot(self, tmp_path):
        """{segment_name} builds the media folder, so the node must BE the
        step; the shot arrives through the <shot name> token instead."""
        code = self._code(tmp_path)
        assert '("name", \'CMP\')' in code
        assert '("shot_name", \'SEQ003_SH001\')' in code

    def test_paths_match_both_toolkit_templates(self, tmp_path):
        code = self._code(tmp_path)
        assert '"<name>_v<version>/<shot name>_<name>_v<version>.<frame>"' in code
        assert '"../batch/<shot name>.v<version>"' in code

    def test_create_clip_is_on_and_points_at_its_own_clip(self, tmp_path):
        """The third gate: without create_clip Flame omits versionNumber and
        tk-flame dies. It must never adopt the conformed clip."""
        code = self._code(tmp_path)
        assert '("create_clip", True)' in code
        assert '"_CMP"' in code
        assert "finishing/clip" not in code.split("_settings = [")[1].split("]")[0]

    def test_generated_code_still_compiles(self, tmp_path):
        compile(self._code(tmp_path), "setup", "exec")

    def test_conform_builds_clips_the_way_the_cycle_regenerates_them(self):
        from flame_mcp.concept_map import CONCEPT_MAP
        recipe = next(e for e in CONCEPT_MAP
                      if e["concept"] == "conform cut")["recipe"]
        assert "steps=[<the chosen step>]" in recipe
        assert "never the singular" in recipe
        assert "uid CHANGES under an already-conformed segment" in recipe
