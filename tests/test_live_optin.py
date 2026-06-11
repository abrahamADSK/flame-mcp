"""
test_live_optin.py
==================
Lock test for the FLAME_LIVE opt-in gate on the live-Flame harness.

Chat 64 incident: a routine ``pytest tests/`` run with Flame open armed
``test_flame_live.py`` (its availability gates probe the bridge at
collection time) and queued render/export idle events on Flame's main
thread → freeze. The harness is now opt-in via ``FLAME_LIVE=1``; this
test pins the gate so it cannot regress silently: importing the module
without the env var must raise pytest's module-level Skipped BEFORE any
bridge probing happens.

Hermetic — never touches a socket: without FLAME_LIVE the module skips
at the gate; the import is aborted before `_flame_unreachable()` runs.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_LIVE_MODULE = Path(__file__).parent / "test_flame_live.py"


def _import_live_module():
    """Import test_flame_live.py fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "_flame_live_under_test", _LIVE_MODULE
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_flame_live_under_test", None)
    return module


def test_live_harness_skips_without_optin(monkeypatch):
    """Without FLAME_LIVE=1 the module must skip at collection time."""
    monkeypatch.delenv("FLAME_LIVE", raising=False)
    with pytest.raises(pytest.skip.Exception) as excinfo:
        _import_live_module()
    assert "FLAME_LIVE=1" in str(excinfo.value), (
        "module-level skip fired but lost the opt-in instruction: "
        + str(excinfo.value)
    )


def test_live_harness_rejects_non_armed_values(monkeypatch):
    """Only the literal '1' arms the harness — '0', 'true', etc. do not."""
    for value in ("0", "true", "yes", ""):
        monkeypatch.setenv("FLAME_LIVE", value)
        with pytest.raises(pytest.skip.Exception):
            _import_live_module()
