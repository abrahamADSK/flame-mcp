"""
test_progress_streaming.py
==========================
Tests for the visible-progress streaming port (Chat 62 design, Chat 63 impl):
MCP-native ``ctx.info`` heartbeats from the long-running flame-mcp tools.

Design under test (src/flame_mcp/server.py):
  The five long-running tools (execute_python, flame_wiretap_tree,
  render_batch, export_clip, import_clips) are split into a sync
  ``_<name>_impl`` body — called by the execute_plan op registry and by the
  rest of this suite — plus an async ``@mcp.tool`` wrapper that runs the
  body in a worker thread via ``_to_thread_with_heartbeat``, emitting an
  ``ctx.info`` line every ``interval`` seconds while the body blocks.

Covered:
  1. ``_to_thread_with_heartbeat`` — silent on fast bodies, heartbeats on
     slow ones, tolerates ``ctx=None``, propagates exceptions.
  2. Async wrappers — coroutine functions that pass through the impl result.
  3. execute_plan registry — handlers remain SYNC (a wrapper leaking into
     the registry would make execute_plan return coroutine objects).

No Flame instance or MCP SDK required (conftest stubs).
"""

import asyncio
import inspect
import time
from unittest.mock import AsyncMock

import pytest

from flame_mcp import server as srv


# ── Helpers ──────────────────────────────────────────────────────────────

def _mock_ctx():
    ctx = AsyncMock()
    ctx.info = AsyncMock()
    return ctx


# ── 1. _to_thread_with_heartbeat ─────────────────────────────────────────

class TestToThreadWithHeartbeat:
    """Heartbeat helper: silence on fast bodies, info lines on slow ones."""

    @pytest.mark.asyncio
    async def test_fast_body_emits_nothing(self):
        ctx = _mock_ctx()

        out = await srv._to_thread_with_heartbeat(
            lambda: "done", ctx, "fast_op", interval=1
        )

        assert out == "done"
        ctx.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_slow_body_emits_heartbeats(self):
        ctx = _mock_ctx()

        def slow():
            time.sleep(0.35)
            return "done"

        out = await srv._to_thread_with_heartbeat(slow, ctx, "slow_op", interval=0.1)

        assert out == "done"
        assert ctx.info.await_count >= 1
        msg = ctx.info.await_args_list[0].args[0]
        assert "slow_op still running in Flame" in msg

    @pytest.mark.asyncio
    async def test_none_ctx_is_tolerated(self):
        def slow():
            time.sleep(0.25)
            return "done"

        out = await srv._to_thread_with_heartbeat(slow, None, "op", interval=0.1)

        assert out == "done"

    @pytest.mark.asyncio
    async def test_body_exception_propagates(self):
        def boom():
            raise RuntimeError("bridge dead")

        with pytest.raises(RuntimeError, match="bridge dead"):
            await srv._to_thread_with_heartbeat(boom, _mock_ctx(), "op", interval=1)


# ── 2. Async wrappers pass through their sync impl ───────────────────────

class TestWrappersPassThrough:
    """Each MCP wrapper is async and returns the impl's result unchanged."""

    def test_wrappers_are_coroutine_functions(self):
        for name in (
            "execute_python",
            "flame_wiretap_tree",
            "render_batch",
            "export_clip",
            "import_clips",
            # F5b fix: execute_plan can dispatch the 120 s import op, so it too
            # must offload to a worker thread instead of blocking the loop.
            "execute_plan",
        ):
            assert asyncio.iscoroutinefunction(getattr(srv, name)), name
            assert not asyncio.iscoroutinefunction(
                getattr(srv, f"_{name}_impl")
            ), f"_{name}_impl must stay sync"

    @pytest.mark.asyncio
    async def test_execute_plan_wrapper_passthrough(self, monkeypatch):
        """execute_plan is async and returns its sync impl's result unchanged."""
        def fake_impl(plan):
            return f"PLAN-RESULT:{len(plan.get('ops', []))}"

        monkeypatch.setattr(srv, "_execute_plan_impl", fake_impl)

        out = await srv.execute_plan({"ops": [{"op": "ping", "args": {}}]})

        assert out == "PLAN-RESULT:1"

    @pytest.mark.asyncio
    async def test_execute_python_wrapper_passthrough(self, monkeypatch):
        ctx = _mock_ctx()
        seen = {}

        def fake_impl(code, timeout=15, dry_run=False):
            seen["args"] = (code, timeout, dry_run)
            return "IMPL-RESULT"

        monkeypatch.setattr(srv, "_execute_python_impl", fake_impl)

        out = await srv.execute_python("print(1)", timeout=42, dry_run=True, ctx=ctx)

        assert out == "IMPL-RESULT"
        assert seen["args"] == ("print(1)", 42, True)

    @pytest.mark.asyncio
    async def test_import_clips_wrapper_passthrough(self, monkeypatch):
        def fake_impl(path, library_name, reel_name=""):
            return f"imported:{path}:{library_name}:{reel_name}"

        monkeypatch.setattr(srv, "_import_clips_impl", fake_impl)

        out = await srv.import_clips("/media/a.mov", "Lib", "Reel 1")

        assert out == "imported:/media/a.mov:Lib:Reel 1"


# ── 3. execute_plan registry stays synchronous ───────────────────────────

class TestPlanRegistrySync:
    """The op registry must point at the sync impls, never the wrappers."""

    def test_registered_handlers_are_sync(self):
        for op in ("render_batch", "export_clip", "import_clips"):
            handler = srv._plan._OP_REGISTRY[op]["handler"]
            assert handler is not None, f"{op} handler not wired"
            assert not asyncio.iscoroutinefunction(handler), (
                f"{op} handler is a coroutine function — execute_plan would "
                "return unawaited coroutine objects"
            )

    def test_render_batch_impl_returns_str(self, monkeypatch):
        """The sync impl returns a plain str (what the registry hands out).

        NOTE: deliberately calls the impl, not the registry handler — the
        execute_plan tests overwrite registry handlers with stubs at module
        level and do not restore them, so reading the registry here is
        order-fragile.
        """
        monkeypatch.setattr(
            srv, "_call_flame",
            lambda code, timeout=15, dedicated_tool=True: {
                "status": "ok", "output": "Render scheduled via idle event.",
                "_bridge_ms": 1,
            },
        )

        out = srv._render_batch_impl(
            render_option="Background Reactor",
            generate_proxies=False,
            include_history=False,
        )

        assert isinstance(out, str)
        assert not inspect.iscoroutine(out)
        assert "Render scheduled" in out
