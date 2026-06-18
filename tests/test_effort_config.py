"""
test_effort_config.py
======================
Unit tests for the effort-level persistence added to the in-Flame bridge
(`hooks/flame_mcp_bridge.py`).

The effort selector (Auto / Low / Medium / High / Max, default Auto) mirrors
the model selector: the chosen value is persisted to ``config.json`` under the
``effort`` key and restored on widget init. The reasoning-hardening env vars
(``CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING`` / ``CLAUDE_CODE_EFFORT_LEVEL``) are
injected into the spawned ``claude`` subprocess based on this value:

  - effort == "auto"  → both vars ABSENT (CLI adaptive-thinking default).
  - effort in fixed   → DISABLE_ADAPTIVE_THINKING="1" + EFFORT_LEVEL=<effort>.

Why this test is config-dict level (not method level)
-----------------------------------------------------
``_load_effort_config`` / ``_save_effort_config`` are instance methods on the
chat-widget class, whose ``__init__`` calls ``_import_qt()`` and would require a
live Qt display / Flame host to instantiate. To keep this suite 100% offline
(no Qt, no Flame), the tests:

  1. Import ONLY the module-level constants (``AVAILABLE_EFFORTS``,
     ``DEFAULT_EFFORT``) — the bridge module imports cleanly without Qt because
     Qt is loaded lazily inside ``__init__``. The constants are loaded directly
     from the file via ``importlib`` so the test does not depend on ``hooks``
     being an importable package.
  2. Replicate the small load/save read logic (identical to the bridge methods)
     against a temp ``config.json`` and assert defaulting + round-trip.

This also exercises the same env-injection contract the bridge applies.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# ── Load the module-level effort constants from the bridge file ──────────────
# The bridge lives in hooks/ (not an importable package). Load it by path so
# the test is independent of sys.path / cwd. The module imports cleanly offline
# because Qt is only imported inside the widget __init__, not at module scope.
_BRIDGE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "flame_mcp_bridge.py"
_spec = importlib.util.spec_from_file_location("_flame_mcp_bridge_for_test", _BRIDGE_PATH)
assert _spec is not None and _spec.loader is not None
_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bridge)

AVAILABLE_EFFORTS = _bridge.AVAILABLE_EFFORTS
DEFAULT_EFFORT = _bridge.DEFAULT_EFFORT

_VALID_EFFORTS = [value for _, value in AVAILABLE_EFFORTS]


# ── Replicated load/save logic (kept identical to the bridge methods) ────────
# Mirrors `_FlameChat._load_effort_config` / `_save_effort_config` so the
# behaviour can be exercised without instantiating the Qt widget.

def _load_effort(config_file: Path) -> str:
    """Replica of the bridge's `_load_effort_config` (default DEFAULT_EFFORT)."""
    try:
        if config_file.exists():
            with open(config_file) as f:
                cfg = json.load(f)
            val = cfg.get("effort", DEFAULT_EFFORT)
            if any(val == e[1] for e in AVAILABLE_EFFORTS):
                return val
    except Exception:
        pass
    return DEFAULT_EFFORT


def _save_effort(config_file: Path, effort: str) -> None:
    """Replica of the bridge's `_save_effort_config` (preserves other keys)."""
    cfg: dict = {}
    if config_file.exists():
        try:
            with open(config_file) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, ValueError):
            cfg = {}
    cfg["effort"] = effort
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Constants sanity ─────────────────────────────────────────────────────────

def test_available_efforts_are_the_expected_five() -> None:
    """The selector exposes exactly Auto/Low/Medium/High/Max in order."""
    assert AVAILABLE_EFFORTS == [
        ("Auto", "auto"),
        ("Low", "low"),
        ("Medium", "medium"),
        ("High", "high"),
        ("Max", "max"),
    ]


def test_default_effort_is_auto() -> None:
    """Default effort must be 'auto' (adaptive-thinking default)."""
    assert DEFAULT_EFFORT == "auto"
    assert DEFAULT_EFFORT in _VALID_EFFORTS


# ── Load: defaulting ───────────────────────────────────────────────────────

def test_missing_file_returns_default(tmp_path: Path) -> None:
    """No config.json → default 'auto', no raise."""
    missing = tmp_path / "config.json"
    assert not missing.exists()
    assert _load_effort(missing) == "auto"


def test_missing_effort_key_returns_default(tmp_path: Path) -> None:
    """config.json present but no 'effort' key → default 'auto'."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"model": "claude-opus-4-8", "backend": "anthropic"}))
    assert _load_effort(cfg) == "auto"


def test_malformed_json_returns_default(tmp_path: Path) -> None:
    """Malformed config.json → default 'auto' (no JSONDecodeError)."""
    bad = tmp_path / "config.json"
    bad.write_text("this is { not json")
    assert _load_effort(bad) == "auto"


def test_invalid_effort_value_returns_default(tmp_path: Path) -> None:
    """An unknown effort value is rejected → default 'auto'."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"effort": "ludicrous"}))
    assert _load_effort(cfg) == "auto"


# ── Load: happy path ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("effort", _VALID_EFFORTS)
def test_each_valid_effort_round_trips(tmp_path: Path, effort: str) -> None:
    """Every valid effort persists and reloads verbatim."""
    cfg = tmp_path / "config.json"
    _save_effort(cfg, effort)
    assert _load_effort(cfg) == effort


# ── Save: key preservation ───────────────────────────────────────────────────

def test_save_preserves_other_keys(tmp_path: Path) -> None:
    """Saving effort must not clobber model/backend/ollama_url."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "model": "claude-opus-4-8",
        "backend": "anthropic",
        "ollama_url": "http://192.168.1.50:11434",
    }))

    _save_effort(cfg, "high")

    data = json.loads(cfg.read_text())
    assert data["effort"] == "high"
    assert data["model"] == "claude-opus-4-8"
    assert data["backend"] == "anthropic"
    assert data["ollama_url"] == "http://192.168.1.50:11434"


def test_save_on_malformed_file_starts_clean(tmp_path: Path) -> None:
    """A malformed config.json is replaced by a clean file holding only effort."""
    cfg = tmp_path / "config.json"
    cfg.write_text("not { valid json")

    _save_effort(cfg, "medium")

    data = json.loads(cfg.read_text())
    assert data == {"effort": "medium"}


def test_save_then_load_overwrites_previous(tmp_path: Path) -> None:
    """A second save replaces the persisted effort; load reflects the latest."""
    cfg = tmp_path / "config.json"
    _save_effort(cfg, "low")
    assert _load_effort(cfg) == "low"
    _save_effort(cfg, "max")
    assert _load_effort(cfg) == "max"


# ── Env-injection contract (mirrors the _agent_loop branch) ──────────────────
# Documents the contract the bridge applies when spawning the claude subprocess.

def _inject_env(base_env: dict, effort: str) -> dict:
    """Replica of the bridge's subprocess env-injection branch."""
    env = dict(base_env)
    if effort and effort != "auto":
        env["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] = "1"
        env["CLAUDE_CODE_EFFORT_LEVEL"] = effort
    else:
        env.pop("CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", None)
        env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
    return env


def test_auto_clears_both_hardening_vars() -> None:
    """'auto' pops both vars even when inherited from os.environ."""
    inherited = {
        "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING": "1",
        "CLAUDE_CODE_EFFORT_LEVEL": "max",
        "PATH": "/usr/bin",
    }
    env = _inject_env(inherited, "auto")
    assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" not in env
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in env
    assert env["PATH"] == "/usr/bin"  # unrelated keys untouched


@pytest.mark.parametrize("effort", ["low", "medium", "high", "max"])
def test_fixed_effort_sets_both_hardening_vars(effort: str) -> None:
    """Any fixed level disables adaptive thinking and forces that effort."""
    env = _inject_env({}, effort)
    assert env["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] == "1"
    assert env["CLAUDE_CODE_EFFORT_LEVEL"] == effort
