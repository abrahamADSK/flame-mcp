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


class TestBurstGuard:
    """Structural writes are spaced by the bridge (Chat 55 / Chat 98).

    The hardened conform recipe fired eight structural creates in 1.5 s;
    Flame raised its error report one second after the burst and crashed
    violently. The same tools, humanly paced across turns, completed the
    Chat 92 conform — spacing was the differentiator, so the bridge now
    enforces it for every caller.
    """

    def test_throttle_applies_regardless_of_the_dt_marker(self, source):
        """The '# DT' marker skips the redirect check only. It was precisely
        the dedicated create_* tools that produced the burst."""
        handler = source.split("local_ns = {'flame': flame}", 1)[0]
        guard = handler.rsplit("Burst guard", 1)[1]
        assert "_BRIDGE_CREATION_INTENT_RE.search(code)" in guard
        assert "_throttle_structural_write(_gap)" in guard
        # And the guard sits AFTER the marker strip, on the shared path —
        # not inside the `if not _is_dt:` redirect branch.
        redirect_branch = source.split("if not _is_dt:", 1)[1].split(
            "local_ns = {'flame': flame}", 1)[0]
        assert "Burst guard" in redirect_branch  # comment shares the block…
        assert redirect_branch.index("conn.close()") < redirect_branch.index(
            "Burst guard")  # …but runs after the redirect early-returns

    def test_sleep_is_on_the_handler_thread_not_flames_main_thread(self, source):
        """Pacing must never touch the Chat 63 main-thread invariant: the
        throttle is called in _handle_connection, before the exec thread."""
        handler = source.split("def _handle_connection(conn):", 1)[1]
        before_exec = handler.split("def _exec_target():", 1)[0]
        assert "_throttle_structural_write(_gap)" in before_exec

    def test_gap_logic_enforces_spacing(self):
        """Replicates the throttle body against a fake clock — the real one
        is module state inside a Qt-free import, but timing tests on real
        sleeps are flaky, so the arithmetic is exercised directly."""
        WRITE_GAP = 2.0
        last = [0.0]
        clock = [100.0]

        def throttle():
            wait = WRITE_GAP - (clock[0] - last[0])
            if wait > 0:
                clock[0] += wait  # "sleep"
            else:
                wait = 0.0
            last[0] = clock[0]
            return wait

        assert throttle() == 0.0          # cold start: no previous write
        assert throttle() == WRITE_GAP    # immediate second write waits fully
        clock[0] += 0.5
        assert throttle() == pytest.approx(1.5)   # partial gap tops up
        clock[0] += 10
        assert throttle() == 0.0          # calm period: no wait

    def test_recipe_gates_flame_structure_on_clips_existing(self):
        """The crashed run built 4 libraries with ZERO .clip files on disk.
        Empty structure must be deleted by hand (structural deletes deadlock
        Flame 2027), so the recipe now full-stops on a missing clip."""
        from flame_mcp.concept_map import CONCEPT_MAP
        recipe = next(
            e for e in CONCEPT_MAP if e["concept"] == "conform cut"
        )["recipe"]
        gate = recipe.split("GATE", 1)[1]
        assert "EXIST on disk" in gate
        assert "full stop" in gate
        assert gate.index("EXIST") < recipe.split("GATE", 1)[1].index("librar")


class TestImportSettle:
    """Media-heavy writes wait for Flame's database writes to land (Chat 98).

    The Python API returns from create_library/create_reel BEFORE Flame
    finishes writing its project database (the app log shows committing/
    syncing continuing after the call). The evidence ladder, all in-vivo the
    same night: creates at 2 s survived eight-in-a-row twice; an import 2 s
    after creates killed Flame while six at 10 s were clean; and five
    overwrites at 3-5 s placed fine until the SIXTH segfaulted at address
    0x0 inside PySequence.overwrite — so timeline edits joined the settle
    tier (measured for imports, extrapolated for edits).
    """

    def test_settle_pattern_covers_imports_and_timeline_edits(self, source):
        assert "_IMPORT_SETTLE_SECS = 10.0" in source
        settle = source.split("_BRIDGE_SETTLE_RE = _re_bridge.compile(", 1)[1]
        settle = settle.split(")", 1)[0]
        assert r"import_clips\s*\(" in settle
        assert r"\.overwrite\s*\(" in settle
        assert r"\.insert\s*\(" in settle

    def test_inserts_are_creation_intent_too(self, source):
        """timeline_insert's generated code was never write-throttled at all:
        PySequence.insert matched neither regex until Chat 98."""
        creation = source.split("_BRIDGE_CREATION_INTENT_RE = _re_bridge.compile(", 1)[1]
        creation = creation.split(")", 1)[0]
        assert r"\.insert\s*\(" in creation

    def test_settle_ops_get_the_long_runway(self, source):
        guard = source.split("Burst guard", 1)[1].split(
            "local_ns = {'flame': flame}", 1)[0]
        assert "_IMPORT_SETTLE_SECS if _is_settle else _WRITE_GAP_SECS" in guard
        assert "_throttle_structural_write(_gap)" in guard

    def test_throttle_takes_the_gap_as_a_parameter(self, source):
        assert "def _throttle_structural_write(required_gap=_WRITE_GAP_SECS):" in source

    def test_two_tier_gap_logic(self):
        """Fake-clock replica: creates space 2 s; an import tops up to 10 s
        since the LAST structural write of any kind."""
        WRITE_GAP, SETTLE = 2.0, 10.0
        last = [0.0]
        clock = [100.0]

        def throttle(gap):
            wait = gap - (clock[0] - last[0])
            if wait > 0:
                clock[0] += wait
            else:
                wait = 0.0
            last[0] = clock[0]
            return wait

        assert throttle(WRITE_GAP) == 0.0            # first create: cold
        assert throttle(WRITE_GAP) == 2.0            # second create: 2 s
        assert throttle(SETTLE) == pytest.approx(10.0)  # import right after
        clock[0] += 4.0
        assert throttle(SETTLE) == pytest.approx(6.0)   # next import tops up
        clock[0] += 60.0
        assert throttle(SETTLE) == 0.0               # calm project: no wait


class TestCrashWarningConsumedOnDisplay:
    """The crash-recovery warning shows ONCE (Chat 98).

    It used to stay armed in the module global with the file still saying
    'running', so every console open for the rest of the session reopened
    with last night's crash. Consumed on display: global reset + file
    cleared.
    """

    def test_display_consumes_the_warning(self, source):
        block = source.split("def _action_open_chat", 1)[1].split("\ndef ", 1)[0]
        assert "global _last_crash_info" in block
        shown = block.split("_append_bubble(\"error\", m))", 1)[1]
        assert "_last_crash_info = None" in shown
        assert "_clear_crash_recovery()" in shown


class TestSaveArmsTheSettleClock:
    """Flame's own saves count as structural writes (Chat 98).

    The autosave is a massive structural write the settle clock could not
    see — it only counted OUR writes, so a timeline edit landing six
    seconds after 'AUTOSAVE ( completed )' looked fully settled and
    segfaulted Flame. The projectSaved Python hook (Flame calls it after
    EVERY save, autosave included) now arms the clock.
    """

    def test_hook_exists_and_arms_the_clock(self, source):
        block = source.split("def projectSaved(", 1)[1].split("\ndef ", 1)[0]
        assert "_last_structural_write[0] = time.monotonic()" in block
        assert "_write_gap_lock" in block

    def test_hook_swallows_its_own_failures(self, source):
        """A logging hiccup inside a Flame-called hook must never propagate
        into Flame's save path."""
        block = source.split("def projectSaved(", 1)[1].split("\ndef ", 1)[0]
        assert "except Exception:" in block
        assert "pass" in block


class TestCorruptionWarningNeedsARealError:
    """The C++ corruption warning fires on errors, not on documentation
    (Chat 98): a tool result carrying our own comments about last night's
    unordered_map::at crash told the operator Flame was corrupted while it
    was perfectly healthy."""

    def test_marker_alone_is_not_enough(self, source):
        block = source.split("Flame C++ corruption warning", 1)[1].split(
            "_extract_stats_footer", 1)[0]
        assert "_cpp_marker and 'ERROR:' in full_text" in block
