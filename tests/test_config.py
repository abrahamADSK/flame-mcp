"""
test_config.py
==============
Unit tests for the shared model-config loader (`flame_mcp._config`).

Covers:
- Missing file → defaults are returned.
- Malformed JSON → defaults are returned (no exception).
- Happy path: every key present is returned verbatim.
- Partial config: only missing keys fall back to defaults.
- Legacy backend `"ollama_local"` is rewritten to `"ollama"`.
- `ollama_cloud_key` defaults to empty string when absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flame_mcp._config import load_model_config


# ── Canonical defaults used across the suite ─────────────────────────────────
DEFAULTS = dict(
    default_model="claude-sonnet-4-6",
    default_backend="anthropic",
    default_ollama_url="http://localhost:11434",
)


# ── Missing / malformed file ─────────────────────────────────────────────────

def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    """File that does not exist → defaults, empty cloud key, no raise."""
    missing = tmp_path / "config.json"
    assert not missing.exists()

    model, backend, ollama_url, cloud_key = load_model_config(missing, **DEFAULTS)

    assert model == DEFAULTS["default_model"]
    assert backend == DEFAULTS["default_backend"]
    assert ollama_url == DEFAULTS["default_ollama_url"]
    assert cloud_key == ""


def test_malformed_json_returns_defaults(tmp_path: Path) -> None:
    """Malformed JSON → caller sees defaults, not a JSONDecodeError."""
    bad = tmp_path / "config.json"
    bad.write_text("this is { not json")

    result = load_model_config(bad, **DEFAULTS)

    assert result == (
        DEFAULTS["default_model"],
        DEFAULTS["default_backend"],
        DEFAULTS["default_ollama_url"],
        "",
    )


def test_non_dict_json_returns_defaults(tmp_path: Path) -> None:
    """JSON list at top level → defaults (no AttributeError on .get())."""
    weird = tmp_path / "config.json"
    weird.write_text(json.dumps(["not", "a", "dict"]))

    result = load_model_config(weird, **DEFAULTS)

    assert result[0] == DEFAULTS["default_model"]
    assert result[3] == ""


# ── Happy paths ──────────────────────────────────────────────────────────────

def test_full_config_returned_verbatim(tmp_path: Path) -> None:
    """Every key present → all four values propagate unchanged."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "model": "claude-opus-4-7",
        "backend": "ollama",
        "ollama_url": "http://192.168.1.50:11434",
        "ollama_cloud_key": "sk-ollama-abc123",
    }))

    model, backend, ollama_url, cloud_key = load_model_config(cfg, **DEFAULTS)

    assert model == "claude-opus-4-7"
    assert backend == "ollama"
    assert ollama_url == "http://192.168.1.50:11434"
    assert cloud_key == "sk-ollama-abc123"


def test_partial_config_mixes_values_and_defaults(tmp_path: Path) -> None:
    """Only `model` present → backend / url / key fall back to defaults."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"model": "qwen3.5-mcp"}))

    model, backend, ollama_url, cloud_key = load_model_config(cfg, **DEFAULTS)

    assert model == "qwen3.5-mcp"
    assert backend == DEFAULTS["default_backend"]
    assert ollama_url == DEFAULTS["default_ollama_url"]
    assert cloud_key == ""


# ── Legacy compatibility ─────────────────────────────────────────────────────

def test_legacy_backend_ollama_local_rewritten(tmp_path: Path) -> None:
    """Old configs using `ollama_local` must be transparently upgraded."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "model": "qwen3.5-mcp",
        "backend": "ollama_local",
    }))

    _, backend, _, _ = load_model_config(cfg, **DEFAULTS)

    assert backend == "ollama"


def test_other_backends_not_rewritten(tmp_path: Path) -> None:
    """The compat rewrite targets only `ollama_local`; other values pass through."""
    for backend_in in ("ollama", "ollama_cloud", "ollama_mac", "anthropic"):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"backend": backend_in}))

        _, backend_out, _, _ = load_model_config(cfg, **DEFAULTS)

        assert backend_out == backend_in, f"backend {backend_in} was rewritten"


# ── Path-likes ───────────────────────────────────────────────────────────────

def test_accepts_string_path(tmp_path: Path) -> None:
    """The helper accepts `str` as well as `pathlib.Path`."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"model": "str-path-model"}))

    model, _, _, _ = load_model_config(str(cfg), **DEFAULTS)

    assert model == "str-path-model"


# ── Defaults are keyword-only ────────────────────────────────────────────────

def test_defaults_are_keyword_only() -> None:
    """Calling with positional defaults must fail — the API is keyword-only."""
    with pytest.raises(TypeError):
        load_model_config(  # type: ignore[misc]
            "/nonexistent",
            "m", "b", "u",
        )
