"""
test_session_continuity.py
==========================
The in-Flame console keeps ONE CLI conversation across turns (Chat 98).

Every turn spawns a fresh ``claude -p``. Before this, the child started from
zero each time and only saw the digest ``_build_prompt`` injected: the last 4
messages truncated to 500 characters. Measured in-vivo on a conform, that made
the model re-discover the FPT link, the project id, the Cut and its CutItems
FIVE times, and re-fetch the workflow recipe on every turn because it fell
outside the digest. Five round-trips to place six clips.

The fix captures the CLI's ``session_id`` from the stream events and passes
``--resume`` on the next turn.

Why these tests read the source
-------------------------------
The wiring lives in methods of the chat-widget class, whose ``__init__`` calls
``_import_qt()`` and needs a live Qt display / Flame host. Same constraint as
``test_effort_config.py``: the suite stays 100% offline, so the structural
contract is asserted against the source, and the prompt-selection logic is
replicated (it is four lines) and exercised directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[1] / "hooks" / "flame_mcp_bridge.py"


@pytest.fixture(scope="module")
def source() -> str:
    return _HOOK.read_text(encoding="utf-8")


class TestResumeWiring:
    """The four points that make session continuity work."""

    def test_resume_is_passed_when_a_session_exists(self, source):
        assert "cmd.extend(['--resume', self._session_id])" in source, (
            "the console must continue its CLI conversation across turns"
        )

    def test_session_id_is_captured_from_stream_events(self, source):
        # Without the capture there is never an id to resume from.
        assert "sid = event.get('session_id')" in source
        assert "self._session_id = sid" in source

    def test_clear_drops_the_session(self, source):
        """Clear must be a real fresh start, not a blank transcript in front
        of a conversation that still remembers."""
        clear = source.split("def _on_clear(self):", 1)[1].split("def ", 1)[0]
        assert "self._session_id = None" in clear

    def test_a_dead_session_does_not_wedge_the_console(self, source):
        """A pruned transcript makes --resume abort. The id must be dropped so
        the next send starts fresh instead of failing forever."""
        assert "if self._session_id and 'session' in err.lower():" in source
        wedge = source.split("if self._session_id and 'session' in err.lower():", 1)[1]
        assert "self._session_id = None" in wedge.split("raise", 1)[0]


class TestPromptSelection:
    """Replicates _build_prompt's branch (the method needs Qt to instantiate).

    With a live session the message goes alone — re-injecting the digest would
    duplicate what the child already remembers, in a truncated copy.
    """

    @staticmethod
    def _build_prompt(session_id, messages):
        history = messages[:-1]
        user_msg = messages[-1]["content"]
        if session_id or not history:
            return user_msg
        lines = ["<recent_conversation>"]
        for msg in history[-4:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            if len(content) > 500:
                content = content[:500] + "…"
            lines.append(f"{role}: {content}")
        lines.append("</recent_conversation>")
        lines.append(f"\n{user_msg}")
        return "\n".join(lines)

    def _convo(self):
        return [
            {"role": "user", "content": "conform the main cut"},
            {"role": "assistant", "content": "here is the plan"},
            {"role": "user", "content": "go ahead"},
        ]

    def test_live_session_sends_the_message_alone(self):
        prompt = self._build_prompt("abc-123", self._convo())
        assert prompt == "go ahead"
        assert "<recent_conversation>" not in prompt

    def test_first_turn_of_a_session_sends_the_message_alone(self):
        prompt = self._build_prompt(None, [{"role": "user", "content": "hola"}])
        assert prompt == "hola"

    def test_digest_is_the_fallback_without_a_session(self):
        """Still the behaviour after a resume failure — degraded, not absent."""
        prompt = self._build_prompt(None, self._convo())
        assert "<recent_conversation>" in prompt
        assert "conform the main cut" in prompt
        assert prompt.endswith("go ahead")

    def test_digest_truncates_long_messages(self):
        long_answer = "x" * 900
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": long_answer},
            {"role": "user", "content": "go ahead"},
        ]
        prompt = self._build_prompt(None, messages)
        assert "…" in prompt
        assert long_answer not in prompt  # this is exactly what --resume avoids


class TestBubblePalette:
    """The operator's own prompts render in Autodesk yellow (Chat 98).

    Same accent the FPT console uses for the user role. Before this, only the
    small "You:" label carried colour and both bodies were #ddd, so the
    operator's input blended into the assistant's output.
    """

    def _palette(self, source):
        return source.split("def _append_bubble", 1)[1].split("\n    def ", 1)[0]

    def test_user_body_is_autodesk_yellow(self, source):
        palette = self._palette(source)
        assert '"user":      ("#ffff00", "You", "#ffff00")' in palette

    def test_body_colour_is_per_role_not_hardcoded(self, source):
        """The body used to be a fixed #ddd, which is why the colour never
        reached the operator's text."""
        palette = self._palette(source)
        assert "color:{body};" in palette
        assert "color:#ddd;" not in palette

    def test_assistant_body_is_unchanged(self, source):
        """Only the user role changes — the assistant keeps its grey body."""
        palette = self._palette(source)
        assert '"assistant": ("#34d399", "Claude", "#ddd")' in palette


class TestIdleWatchdog:
    """The watchdog measures SILENCE, not duration (Chat 98).

    It used to cap total wall-clock, which was fine while every turn was a
    question-and-answer exchange. Once the conform recipe stopped asking
    needless questions, the whole workflow became ONE long turn — ~30 tool
    calls — and was killed at 180 s mid-run while streaming events perfectly.
    """

    def _watch(self, source):
        return source.split("def _watch():", 1)[1].split("\n            watchdog", 1)[0]

    def test_deadline_is_refreshed_by_output(self, source):
        loop = source.split("for raw_line in proc.stdout:", 1)[1][:400]
        assert "_last_event[0] = time.monotonic()" in loop

    def test_unparseable_output_still_counts_as_alive(self, source):
        """The refresh must happen BEFORE the json parse, or a burst of
        malformed lines would read as silence."""
        loop = source.split("for raw_line in proc.stdout:", 1)[1][:600]
        assert loop.index("_last_event[0]") < loop.index("json.loads")

    def test_silence_kills_the_process(self, source):
        watch = self._watch(source)
        assert "_idle_secs" in watch
        assert "proc.kill()" in watch

    def test_there_is_an_absolute_ceiling(self, source):
        """Idle-only would let a pathological loop run forever."""
        watch = self._watch(source)
        assert "_hard_secs" in watch
        assert "_hard_stop[0] = True" in watch

    def test_the_two_stops_report_differently(self, source):
        """A ceiling stop is not a hang, and must not be reported as one."""
        assert "if _hard_stop[0]:" in source
        assert "nothing was hung" in source

    def test_hint_is_not_about_ollama_on_anthropic(self, source):
        """The old message always blamed the Ollama server, even on Anthropic."""
        assert 'startswith("ollama")' in source
        assert "Reload hook" in source

    @pytest.mark.parametrize(
        "since_event,elapsed,expected",
        [
            (10, 30, "run"),      # busy conform, well inside both budgets
            (10, 3000, "hard"),   # still streaming, but past the ceiling
            (200, 300, "idle"),   # gone quiet — a real hang
            (179, 400, "run"),    # just inside the silence budget
        ],
    )
    def test_decision_table(self, since_event, elapsed, expected):
        """Replicates the branch inside _watch (idle 180 s, ceiling 1800 s)."""
        idle_secs, hard_secs = 180, 1800
        if elapsed > hard_secs:
            got = "hard"
        elif since_event <= idle_secs:
            got = "run"
        else:
            got = "idle"
        assert got == expected
