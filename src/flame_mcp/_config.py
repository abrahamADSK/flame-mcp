"""
_config.py
==========
Shared helper for loading the persisted LLM model/backend configuration
from config.json. Used by both the MCP server (src/flame_mcp/server.py)
and the Flame-side bridge (hooks/flame_mcp_bridge.py).

Why a shared helper?
--------------------
Before this module, `_load_model_config` existed twice with identical
logic — once in server.py and once in flame_mcp_bridge.py. Bug fixes
had to be synchronised manually; ARCHITECTURE.md §11 flagged the
duplication as a known smell (Chat 44 audit).

Design constraints
------------------
The bridge runs INSIDE Flame's embedded Python interpreter, installed
at `/opt/Autodesk/shared/python/flame_mcp_bridge.py`. In that context
the `flame_mcp` package is not available on `sys.path`. Therefore this
helper MUST be callable without the package being importable — the
bridge is expected to make it importable via a `_PROJECT_ROOT`-relative
sys.path insertion (see hooks/flame_mcp_bridge.py for the bootstrap).

Public API
----------
load_model_config(config_path, *, default_model, default_backend,
                  default_ollama_url)
    Read the config.json file and return
    `(model, backend, ollama_url, ollama_cloud_key)`. All defaults are
    explicit arguments so each caller can keep its own canonical
    fall-back values (bridge uses DEFAULT_MODEL / DEFAULT_BACKEND /
    DEFAULT_OLLAMA_URL; the server previously used whatever was in
    config.json without defaults).

Backward compatibility
----------------------
- If `backend` is the legacy value `"ollama_local"` it is silently
  rewritten to `"ollama"` — same rule the bridge has enforced since the
  Ollama split.
- On any read / parse error the helper returns the defaults (empty
  cloud key). The caller must not rely on exceptions for control flow.
"""

from __future__ import annotations

import json
import os
from typing import Tuple


def load_model_config(
    config_path: str | os.PathLike,
    *,
    default_model: str,
    default_backend: str,
    default_ollama_url: str,
) -> Tuple[str, str, str, str]:
    """
    Load persisted model, backend, Ollama server URL, and cloud key
    from a config.json file.

    Parameters
    ----------
    config_path : str | os.PathLike
        Filesystem path to the config.json file to read.
    default_model : str
        Fallback model ID used when the file is missing, unreadable,
        or missing the `model` key.
    default_backend : str
        Fallback backend name. Applied the same way as `default_model`.
    default_ollama_url : str
        Fallback Ollama server URL (used for the `ollama` backend).

    Returns
    -------
    (model, backend, ollama_url, ollama_cloud_key) : tuple[str, str, str, str]
        Four-tuple of strings. `ollama_cloud_key` defaults to `""`
        when not set in config.json.

    Notes
    -----
    - The legacy backend name `"ollama_local"` is rewritten to
      `"ollama"` for backward compatibility with older configs.
    - All I/O errors (file missing, permission denied, malformed JSON)
      collapse to the defaults; no exception is raised.
    """
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        model = cfg.get("model", default_model)
        backend = cfg.get("backend", default_backend)
        # Backward compat: old configs may have "ollama_local"
        if backend == "ollama_local":
            backend = "ollama"
        ollama_url = cfg.get("ollama_url", default_ollama_url)
        cloud_key = cfg.get("ollama_cloud_key", "")
        return model, backend, ollama_url, cloud_key
    except Exception:
        return default_model, default_backend, default_ollama_url, ""
