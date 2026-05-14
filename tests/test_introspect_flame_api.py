"""
test_introspect_flame_api.py
============================
Tests for ``scripts/introspect_flame_api.py``.

The script's central correctness property — that it actually walks Flame's
Python API — can only be exercised inside Flame's embedded Python (the
``flame`` module is a Boost.Python C++ binding that does NOT exist on a
normal system Python install). What we CAN exercise here is the script's
"no flame module" code path: that it exits cleanly with the documented
exit code and message instead of crashing.

The integration test that asserts ``rag/api_graph.json`` content stays in
sync with the real Flame API lives outside the CI test suite and is run
manually by the maintainer when bumping Flame versions (see the script's
header docstring for cadence).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "introspect_flame_api.py"


def _load_introspector() -> ModuleType:
    """Import ``introspect_flame_api`` as a module from its file path.

    The script lives under ``scripts/`` which is NOT a Python package, so
    we cannot just ``import scripts.introspect_flame_api``. Use the
    importlib machinery to load it as a one-off module.
    """
    spec = importlib.util.spec_from_file_location(
        "introspect_flame_api", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_mode_without_flame_exits_2(monkeypatch, capsys):
    """``--check`` must exit with code 2 when the ``flame`` module is absent.

    We force the absence by inserting a sentinel in ``sys.modules['flame']``
    that raises ``ImportError`` on lookup. ``_try_import_flame`` catches
    ``ImportError`` and returns ``None``, which triggers the documented
    "REQUIRES FLAME OPEN" path.
    """
    # Make sure no real flame module is cached from a prior test run.
    monkeypatch.delitem(sys.modules, "flame", raising=False)

    # If something on the test host actually provides a ``flame`` module,
    # mask the finder by inserting a meta_path hook that raises ImportError
    # for that exact name.
    class _BlockFlameFinder:
        def find_spec(self, name, path, target=None):  # noqa: D401, ARG002
            if name == "flame":
                raise ImportError("blocked by test")
            return None

    monkeypatch.setattr(sys, "meta_path", [_BlockFlameFinder(), *sys.meta_path])

    module = _load_introspector()
    rc = module.main(["--check"])
    assert rc == module.EXIT_FLAME_MISSING
    captured = capsys.readouterr()
    # The user-facing message must include the documented sentinel string
    # so shell callers can grep for it.
    assert "REQUIRES FLAME OPEN" in captured.err


def test_default_run_without_flame_does_not_write_output(monkeypatch, tmp_path):
    """Running without ``flame`` must NOT touch the output JSON path.

    Regression: an early draft attempted ``out_path.parent.mkdir`` before
    checking flame availability, which created stray empty directories on
    machines without Flame.
    """
    monkeypatch.delitem(sys.modules, "flame", raising=False)

    class _BlockFlameFinder:
        def find_spec(self, name, path, target=None):  # noqa: D401, ARG002
            if name == "flame":
                raise ImportError("blocked by test")
            return None

    monkeypatch.setattr(sys, "meta_path", [_BlockFlameFinder(), *sys.meta_path])

    out_path = tmp_path / "subdir" / "api_graph.json"
    module = _load_introspector()
    rc = module.main(["--output", str(out_path)])

    assert rc == module.EXIT_FLAME_MISSING
    # No file should have been written.
    assert not out_path.exists()


def test_build_graph_against_fake_flame_module():
    """``build_graph`` must produce the documented shape against a stub.

    We hand-roll a minimal stand-in for the ``flame`` module so we can
    exercise the walker logic in CI without a real Flame install. This
    test is intentionally lightweight — it verifies the SHAPE of the
    output (keys present, classes recognised, dunders filtered) rather
    than the contents (which only the live introspection can validate).
    """
    module = _load_introspector()

    fake = ModuleType("flame")

    class PyClipStub:
        """Stand-in for PyClip — has a method and a name attribute."""

        name = "stub_clip"

        def save_as(self, path):
            """Save the clip under a new name."""
            return path

    def delete(obj):
        """Stub for flame.delete()."""
        return None

    fake.PyClip = PyClipStub
    fake.delete = delete
    fake.batch = object()  # module-level attribute, not callable
    fake.get_version = lambda: "2026.test.0"

    graph = module.build_graph(fake)

    # Meta section is populated.
    assert graph["_meta"]["flame_version"] == "2026.test.0"
    assert graph["_meta"]["introspector"].endswith("introspect_flame_api.py")
    assert graph["_meta"]["classes_total"] == 1
    # functions_total counts module-level callables.
    assert graph["_meta"]["functions_total"] >= 1

    # Class shape.
    assert "PyClipStub" in graph["classes"]
    cls_info = graph["classes"]["PyClipStub"]
    assert "save_as" in cls_info["methods"]
    assert "name" in cls_info["attrs"]
    assert cls_info["attrs"]["name"]["kind"] == "str"

    # Module attribute bucket holds the non-callable.
    assert "flame.batch" in graph["module_attrs"]

    # Free function bucket holds flame.delete.
    assert "flame.delete" in graph["functions"]
