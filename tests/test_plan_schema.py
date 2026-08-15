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
        assert 'create_node("Write File")' in code
        # MEDIA-ONLY (Chat 98): the Write File never creates a clip — Flame
        # owns any clip it creates and overwrote the pipeline's in-vivo.
        assert '("create_clip", False)' in code
        assert "create_clip_path" not in code
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
            assert '("create_clip", False)' in code
            assert "create_clip_path" not in code
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

    def test_media_pattern_is_versioned(self):
        setup, fix = self._codes()
        for code in (setup, fix):
            assert "<name>_v<version>/<name>_v<version>.<frame>" in code

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
        assert server._derive_source_frame_range(self._write_clip(tmp_path)) == (1001, 100)

    def test_derive_falls_back_to_the_path_pattern(self, tmp_path):
        """A clip without <startFrame> still yields the range from [a-b]."""
        import flame_mcp.server as server
        xml = self._CLIP_XML.replace("<startFrame>1001</startFrame>", "")
        xml = xml.replace("<duration>100</duration>", "", 1)
        assert server._derive_source_frame_range(self._write_clip(tmp_path, xml)) == (1001, 100)

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
        assert "FRAME ALIGNMENT is AUTOMATIC" in recipe
        assert "render ONLY on OK" in recipe
        assert "NUMBERING CHECK" in recipe and ".1001.exr, not .0001.exr" in recipe
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
        assert '("name", \'SEQ003_SH001_CMP\')' in code
        assert "SEQ003_SH001_writefile" not in code   # the old literal name is gone

    def test_fix_renames_the_write_file_from_the_clip_stem(self):
        code = self._fix(step="CMP")
        assert '("name", \'SEQ003_SH001_CMP\')' in code
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
        assert "'<shot>_<step>'" in recipe and "{Shot}_{Step}_v<version>" in recipe
        assert "leaked into the PublishedFile code" in recipe
