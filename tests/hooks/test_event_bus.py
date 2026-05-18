"""Tests for s16: LifecycleEventBus + AgentLoop hook integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jarvis.core.hooks.event_bus import LifecycleEventBus
from src.jarvis.core.hooks.schema import HookResult, HookSpec, HookStage


# ── LifecycleEventBus unit tests ──────────────────────────────────────


class TestLifecycleEventBus:
    def test_register_and_fire(self):
        """Registered hooks should be called when their stage fires."""
        bus = LifecycleEventBus()
        calls: list[dict] = []

        def handler(**kwargs) -> HookResult:
            calls.append(kwargs)
            return HookResult(allowed=True)

        bus.register(HookSpec(
            name="test_hook",
            stage="turn_start",
            handler=handler,
        ))
        result = bus.fire(HookStage.TURN_START, {"turn_id": "t1", "text": "hello"})
        assert result.allowed
        assert len(calls) == 1
        assert calls[0]["turn_id"] == "t1"
        assert calls[0]["text"] == "hello"

    def test_fire_first_denial_blocks(self):
        """When a hook returns allowed=False, fire returns that denial."""
        bus = LifecycleEventBus()

        def allow(**kwargs) -> HookResult:
            return HookResult(allowed=True)

        def deny(**kwargs) -> HookResult:
            return HookResult(allowed=False, reason="blocked by policy")

        def never_called(**kwargs) -> HookResult:
            raise AssertionError("should not be called")

        bus.register(HookSpec(name="allow_hook", stage="turn_start", handler=allow))
        bus.register(HookSpec(name="deny_hook", stage="turn_start", handler=deny))
        bus.register(HookSpec(name="never_hook", stage="turn_start", handler=never_called))

        result = bus.fire(HookStage.TURN_START, {})
        assert not result.allowed
        assert result.reason == "blocked by policy"

    def test_fire_returns_allow_when_no_hooks(self):
        """When no hooks are registered, fire returns allowed=True."""
        bus = LifecycleEventBus()
        result = bus.fire(HookStage.TURN_START, {})
        assert result.allowed

    def test_fire_returns_allow_when_handler_none(self):
        """Hooks with no handler are silently skipped."""
        bus = LifecycleEventBus()
        bus.register(HookSpec(name="no_handler", stage="turn_start", handler=None))
        result = bus.fire(HookStage.TURN_START, {})
        assert result.allowed

    def test_fire_audit_swallows_errors(self):
        """Audit hooks should never raise or deny."""
        bus = LifecycleEventBus()

        def raises(**kwargs) -> HookResult:
            raise RuntimeError("oops")

        bus.register(HookSpec(name="failing", stage="turn_end", handler=raises))
        result = bus.fire_audit(HookStage.TURN_END, {})
        assert result.allowed  # audit errors are swallowed

    def test_fire_handler_exception_becomes_denial(self):
        """If a handler raises, fire should return a denial."""
        bus = LifecycleEventBus()

        def raises(**kwargs) -> HookResult:
            raise ValueError("bad hook")

        bus.register(HookSpec(name="bad_hook", stage="turn_start", handler=raises))
        result = bus.fire(HookStage.TURN_START, {})
        assert not result.allowed
        assert "bad_hook" in result.reason
        assert "ValueError" in result.reason

    def test_multiple_hooks_same_stage_all_pass(self):
        """All hooks for a stage should run if none deny."""
        bus = LifecycleEventBus()
        seen: list[str] = []

        def h1(**kwargs): seen.append("h1"); return HookResult(allowed=True)
        def h2(**kwargs): seen.append("h2"); return HookResult(allowed=True)
        def h3(**kwargs): seen.append("h3"); return HookResult(allowed=True)

        bus.register(HookSpec(name="h1", stage="turn_start", handler=h1))
        bus.register(HookSpec(name="h2", stage="turn_start", handler=h2))
        bus.register(HookSpec(name="h3", stage="turn_start", handler=h3))

        result = bus.fire(HookStage.TURN_START, {})
        assert result.allowed
        assert seen == ["h1", "h2", "h3"]

    def test_unregister_removes_hook(self):
        """Unregister should remove the hook by name."""
        bus = LifecycleEventBus()
        calls: list[str] = []

        def h(**kwargs): calls.append("called"); return HookResult(allowed=True)

        bus.register(HookSpec(name="to_remove", stage="turn_start", handler=h))
        assert bus.unregister("to_remove") is True
        result = bus.fire(HookStage.TURN_START, {})
        assert result.allowed
        assert len(calls) == 0

    def test_unregister_nonexistent_returns_false(self):
        bus = LifecycleEventBus()
        assert bus.unregister("nope") is False

    def test_list_hooks_returns_metadata(self):
        bus = LifecycleEventBus()
        bus.register(HookSpec(name="h1", stage="turn_start", description="first hook"))
        bus.register(HookSpec(name="h2", stage="session_end", handler=lambda **kw: HookResult(allowed=True)))
        hooks = bus.list_hooks()
        assert len(hooks) == 2
        assert {h["name"] for h in hooks} == {"h1", "h2"}

    def test_snapshot_includes_count(self):
        bus = LifecycleEventBus()
        bus.register(HookSpec(name="h", stage="turn_start"))
        snap = bus.snapshot()
        assert snap["count"] == 1

    def test_dict_handler_returning_false_allowed(self):
        """A handler returning dict with allowed=False should be treated as denial."""
        bus = LifecycleEventBus()

        def dict_deny(**kwargs) -> dict:
            return {"allowed": False, "reason": "dict-based denial"}

        bus.register(HookSpec(name="dict_hook", stage="turn_start", handler=dict_deny))
        result = bus.fire(HookStage.TURN_START, {})
        assert not result.allowed
        assert result.reason == "dict-based denial"


# ── AgentLoop integration tests ───────────────────────────────────────


class TestAgentLoopWithEventBus:
    def test_turn_start_hook_can_deny(self, tmp_path: Path):
        """TURN_START hook that denies should block the turn."""
        from src.jarvis.agent.loop import AgentLoop
        from src.jarvis.agent.types import ChatInput

        bus = LifecycleEventBus()

        def deny_turn(**kwargs) -> HookResult:
            return HookResult(allowed=False, reason="Agent is in maintenance mode")

        bus.register(HookSpec(name="maintenance_mode", stage="turn_start", handler=deny_turn))

        loop = AgentLoop(
            project_root=str(tmp_path),
            max_steps=2,
            event_bus=bus,
        )
        result = loop.run_turn(ChatInput(text="do something", cwd=str(tmp_path), project_id="test"))
        assert not result.ok or result.stop_reason == "hook_denied"
        assert "maintenance" in result.final_answer.lower()

    def test_turn_start_hook_can_allow(self, tmp_path: Path):
        """TURN_START hook that allows should let the turn proceed."""
        from src.jarvis.agent.loop import AgentLoop
        from src.jarvis.agent.types import ChatInput

        bus = LifecycleEventBus()
        fired: list[dict] = []

        def allow_turn(**kwargs) -> HookResult:
            fired.append(kwargs)
            return HookResult(allowed=True)

        bus.register(HookSpec(name="logger", stage="turn_start", handler=allow_turn))

        loop = AgentLoop(
            project_root=str(tmp_path),
            max_steps=2,
            event_bus=bus,
        )
        result = loop.run_turn(ChatInput(text="say hello", cwd=str(tmp_path), project_id="test"))
        assert len(fired) == 1
        assert fired[0]["text"] == "say hello"

    def test_lifecycle_audit_hooks_fired(self, tmp_path: Path):
        """Session/turn/compact lifecycle audit hooks should fire during a turn."""
        from src.jarvis.agent.loop import AgentLoop
        from src.jarvis.agent.types import ChatInput

        bus = LifecycleEventBus()
        events: list[str] = []

        def record_event(**kwargs) -> HookResult:
            events.append(kwargs.get("_stage", "unknown"))
            return HookResult(allowed=True)

        # Use a wrapper to identify which stage fired
        def make_handler(stage_name):
            def handler(**kwargs):
                events.append(stage_name)
                return HookResult(allowed=True)
            return handler

        bus.register(HookSpec(name="sess_start", stage="session_start", handler=make_handler("session_start")))
        bus.register(HookSpec(name="turn_start", stage="turn_start", handler=make_handler("turn_start")))
        bus.register(HookSpec(name="compact_pre", stage="compact_pre", handler=make_handler("compact_pre")))
        bus.register(HookSpec(name="turn_end", stage="turn_end", handler=make_handler("turn_end")))
        bus.register(HookSpec(name="sess_end", stage="session_end", handler=make_handler("session_end")))

        loop = AgentLoop(
            project_root=str(tmp_path),
            max_steps=2,
            event_bus=bus,
        )
        loop.run_turn(ChatInput(text="hello", cwd=str(tmp_path), project_id="test"))

        # session_start, turn_start, compact_pre should all fire
        assert "session_start" in events
        assert "turn_start" in events
        assert "compact_pre" in events
        # turn_end and session_end fire on completion or exception
        assert "turn_end" in events
        assert "session_end" in events
        # Order check: session_start before turn_start before compact_pre
        si = events.index("session_start")
        ti = events.index("turn_start")
        ci = events.index("compact_pre")
        assert si < ti < ci

    def test_event_bus_none_does_not_crash(self, tmp_path: Path):
        """When event_bus is None (default), AgentLoop should work normally."""
        from src.jarvis.agent.loop import AgentLoop
        from src.jarvis.agent.types import ChatInput

        loop = AgentLoop(
            project_root=str(tmp_path),
            max_steps=2,
            event_bus=None,
        )
        result = loop.run_turn(ChatInput(text="hello", cwd=str(tmp_path), project_id="test"))
        # Should not crash — any result is fine
        assert result is not None

    def test_hook_handler_error_is_caught(self, tmp_path: Path):
        """When a pre hook raises an exception, the turn should be denied safely."""
        from src.jarvis.agent.loop import AgentLoop
        from src.jarvis.agent.types import ChatInput

        bus = LifecycleEventBus()

        def explode(**kwargs) -> HookResult:
            raise RuntimeError("hook bug")

        bus.register(HookSpec(name="buggy", stage="turn_start", handler=explode))

        loop = AgentLoop(
            project_root=str(tmp_path),
            max_steps=2,
            event_bus=bus,
        )
        result = loop.run_turn(ChatInput(text="anything", cwd=str(tmp_path), project_id="test"))
        assert result.stop_reason == "hook_denied"
        assert "RuntimeError" in result.final_answer


# ── Multiple hooks by priority ────────────────────────────────────────


class TestHookPriority:
    def test_hooks_execute_in_registration_order(self):
        bus = LifecycleEventBus()
        order: list[int] = []

        def make(i):
            def h(**kwargs):
                order.append(i)
                return HookResult(allowed=True)
            return h

        for i in range(5):
            bus.register(HookSpec(name=f"h{i}", stage="turn_start", handler=make(i)))

        bus.fire(HookStage.TURN_START, {})
        assert order == [0, 1, 2, 3, 4]

    def test_mixed_deny_and_allow_short_circuits(self):
        """First denial should prevent later hooks from running."""
        bus = LifecycleEventBus()
        order: list[int] = []

        def allow(i):
            def h(**kwargs):
                order.append(i)
                return HookResult(allowed=True)
            return h

        def deny(**kwargs):
            order.append(99)
            return HookResult(allowed=False, reason="stop")

        bus.register(HookSpec(name="a1", stage="turn_start", handler=allow(1)))
        bus.register(HookSpec(name="a2", stage="turn_start", handler=allow(2)))
        bus.register(HookSpec(name="deny", stage="turn_start", handler=deny))
        bus.register(HookSpec(name="a3", stage="turn_start", handler=allow(3)))

        result = bus.fire(HookStage.TURN_START, {})
        assert not result.allowed
        assert 3 not in order  # should not have run
