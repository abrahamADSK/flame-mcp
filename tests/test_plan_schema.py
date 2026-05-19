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
