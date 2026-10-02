"""
test_write_gate_fallback.py
===========================
The "switch to X" hint must name a model the write gate accepts.

Sonnet left ``WRITE_ALLOWED_MODELS`` on 2026-06-10; the hint kept
suggesting it until Chat 109. These tests pin the default to a
write-capable tier and keep it consistent with ``_model_can_write``.
"""

from __future__ import annotations

from flame_mcp import server as srv


def test_fallback_default_is_write_capable(monkeypatch) -> None:
    """With no ``fallback_model`` configured, the hint names Opus."""
    monkeypatch.setattr(srv, "_get_config", lambda: {})
    assert srv._fallback_model_name() == "Opus"


def test_fallback_default_passes_write_gate(monkeypatch) -> None:
    """The default suggestion, as a model id, is accepted by the gate."""
    monkeypatch.setattr(srv, "_get_config", lambda: {})
    suggested = srv._fallback_model_name().lower()
    monkeypatch.setattr(srv, "_get_current_model", lambda: f"claude-{suggested}-5-5")
    assert srv._model_can_write()


def test_fallback_config_overrides_default(monkeypatch) -> None:
    """An explicit ``fallback_model`` in config wins over the default."""
    monkeypatch.setattr(srv, "_get_config", lambda: {"fallback_model": "claude-opus-5-5"})
    assert srv._fallback_model_name() == "claude-opus-5-5"


def test_shipped_example_fallback_passes_write_gate(monkeypatch) -> None:
    """config.example.json's fallback_model must itself be write-capable."""
    import json
    from pathlib import Path

    example = json.loads(
        (Path(__file__).resolve().parents[1] / "config.example.json").read_text()
    )
    monkeypatch.setattr(srv, "_get_config", lambda: {})
    monkeypatch.setattr(srv, "_get_current_model", lambda: example["fallback_model"])
    assert srv._model_can_write()
