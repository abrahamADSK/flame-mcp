"""error_scrub.py — OPSEC-safe error-message sanitisation shared across the
MCP ecosystem (fpt-mcp / maya-mcp / flame-mcp).

Canonical source: ``~/Projects/error_scrub_canonical.py``. Byte-identical
copies live in each repo's package (``<pkg>/error_scrub.py``); propagate edits
with ``/propagate-change``. The module has NO package-relative imports (only the
stdlib ``re``), so the three copies are literally identical.

Why this exists
---------------
All three servers echo exception text back to the model at their tool
boundaries. fpt-mcp additionally classifies ShotGrid ``Fault`` exceptions into a
structured ``{error, error_type, hint, retryable}`` shape (``sg_errors.py``);
that taxonomy stays fpt-specific because flame (Wiretap) and maya (Maya Command
Port) do not raise ShotGrid ``Fault`` exceptions and their tools return plain
error strings.

What the three DO share is the OPSEC primitive below: before any exception text
reaches the model it must (a) have credential-shaped tokens redacted and (b) be
length-bounded. This module is that primitive, single-sourced so a fix to the
secret regex lands in every server at once.
"""

from __future__ import annotations

import re

#: Cap on how much raw exception/server text is echoed back to the model.
MAX_ERROR_CHARS = 300

#: Redact credential-shaped ``key=value`` / ``key: value`` tokens. Longer key
#: names are listed FIRST so e.g. ``script_key`` is matched whole rather than as
#: a trailing ``key``. Only a ``key=value`` shape is redacted, so a message that
#: merely *names* a field ("invalid script_name or api_key") is left intact.
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api_key|script_key|password|secret|token|key)\b(\s*[=:]\s*)(\S+)"
)


def scrub_secrets(text: str) -> str:
    """Redact credential-shaped values embedded in free text.

    Replaces the *value* of a ``key=value`` / ``key: value`` token with
    ``***redacted***`` while leaving the key name and separator intact.
    """
    return _SECRET_VALUE_RE.sub(r"\1\2***redacted***", text)


def safe_error_message(exc: BaseException, max_len: int = MAX_ERROR_CHARS) -> str:
    """Return a scrubbed, length-bounded string for *exc*.

    Scrub FIRST, then truncate, so a secret sitting near the ``max_len``
    boundary cannot be left half-exposed by the cut. Falls back to the
    exception class name when ``str(exc)`` is empty.
    """
    text = str(exc) or exc.__class__.__name__
    return scrub_secrets(text)[:max_len]
