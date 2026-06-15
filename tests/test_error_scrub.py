"""test_error_scrub.py — unit tests for the shared OPSEC scrub+truncate helper
and its wiring into the flame-mcp error boundary.

``error_scrub`` is byte-identical across fpt-mcp / maya-mcp / flame-mcp
(canonical at ~/Projects/error_scrub_canonical.py). flame-mcp applies it in
``_call_flame`` (the bridge exception path → ``safe_error_message``) and ``_fmt``
(the universal error formatter → ``scrub_secrets``).
"""

from flame_mcp.error_scrub import MAX_ERROR_CHARS, safe_error_message, scrub_secrets
from flame_mcp.server import _fmt


class TestScrubSecrets:
    def test_redacts_key_value(self):
        assert scrub_secrets("boom api_key=ABC123 end") == "boom api_key=***redacted*** end"

    def test_redacts_colon_form(self):
        assert "***redacted***" in scrub_secrets("password: hunter2")

    def test_longer_key_matched_whole(self):
        assert scrub_secrets("script_key=XYZ") == "script_key=***redacted***"

    def test_naming_a_field_without_value_is_left_intact(self):
        msg = "invalid script_name or api_key"
        assert scrub_secrets(msg) == msg


class TestSafeErrorMessage:
    def test_scrub_then_truncate(self):
        out = safe_error_message(RuntimeError("token=SEKRET " + "x" * 1000))
        assert len(out) == MAX_ERROR_CHARS == 300
        assert "***redacted***" in out

    def test_empty_message_falls_back_to_class_name(self):
        assert safe_error_message(ValueError("")) == "ValueError"


class TestFmtScrubbing:
    def test_error_message_is_scrubbed(self):
        out = _fmt({"status": "error", "error": "fail api_key=ABC123"})
        assert out == "ERROR:\nfail api_key=***redacted***"

    def test_normal_output_is_not_scrubbed(self):
        # A successful result carrying 'key=value'-looking text must pass through
        # untouched — only the error branch is scrubbed.
        out = _fmt({"status": "ok", "output": "node key=value retained"})
        assert "key=value retained" in out
        assert "***redacted***" not in out
