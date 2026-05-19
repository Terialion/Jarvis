"""Integration tests for SubagentPool -- spawn/wait/list/close + concurrent execution."""
from __future__ import annotations

import time

from jarvis.core.subagents.models import SubagentConfig, SubagentStatus
from jarvis.core.subagents.pool import SubagentPool
from jarvis.core.subagents.policy import check_depth, tool_whitelist_for_type


def _fake_runner(config: SubagentConfig) -> dict:
    """Simulate subagent work."""
    time.sleep(0.05)  # simulate work
    return {
        "agent_id": config.agent_id,
        "status": "completed",
        "final_answer": f"Result from {config.agent_id}: processed task",
        "steps": config.budget_steps,
        "total_tokens": 1234,
    }


class TestSubagentPool:
    def test_submit_returns_immediately(self):
        pool = SubagentPool(max_workers=2)
        pool.set_runner(_fake_runner)
        config = SubagentConfig(
            agent_id="test_1", agent_type="Explore", task="Find all Python files",
            budget_steps=3, depth=0,
        )
        t0 = time.perf_counter()
        handle = pool.submit(config)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.02, f"submit blocked for {elapsed:.3f}s"
        assert handle.agent_id == "test_1"
        assert handle.status == SubagentStatus.RUNNING
        pool.shutdown(wait=True)

    def test_spawn_and_wait(self):
        pool = SubagentPool(max_workers=2)
        pool.set_runner(_fake_runner)
        config = SubagentConfig(
            agent_id="test_2", agent_type="Plan", task="Plan the refactor",
            budget_steps=5, depth=0,
        )
        pool.submit(config)
        result = pool.wait_agent("test_2", timeout=5.0)
        assert result["status"] == "completed"
        assert "Result from test_2" in str(result["result"])
        pool.shutdown(wait=True)

    def test_list_agents(self):
        pool = SubagentPool(max_workers=2)
        pool.set_runner(_fake_runner)
        for i in range(3):
            config = SubagentConfig(
                agent_id=f"test_{i}", agent_type="Explore", task=f"Task {i}",
                budget_steps=3, depth=0,
            )
            pool.submit(config)
        agents = pool.list_agents()
        assert len(agents) == 3
        pool.shutdown(wait=True)

    def test_close_agent(self):
        pool = SubagentPool(max_workers=2)

        def slow_runner(config: SubagentConfig) -> dict:
            time.sleep(10)
            return {"agent_id": config.agent_id, "status": "completed", "final_answer": "", "steps": 0, "total_tokens": 0}

        pool.set_runner(slow_runner)
        config = SubagentConfig(
            agent_id="slow_1", agent_type="Explore", task="Slow task",
            budget_steps=1, depth=0,
        )
        pool.submit(config)
        cancelled = pool.close_agent("slow_1")
        assert cancelled is True
        agents = pool.list_agents()
        assert agents[0]["status"] == "cancelled"
        pool.shutdown(wait=False)

    def test_concurrent_execution(self):
        pool = SubagentPool(max_workers=3)
        results_order = []

        def ordered_runner(config: SubagentConfig) -> dict:
            sleep_time = {"a": 0.1, "b": 0.05, "c": 0.15}.get(config.agent_id, 0.05)
            time.sleep(sleep_time)
            results_order.append(config.agent_id)
            return {"agent_id": config.agent_id, "status": "completed", "final_answer": config.agent_id, "steps": 1, "total_tokens": 100}

        pool.set_runner(ordered_runner)
        for aid in ["a", "b", "c"]:
            config = SubagentConfig(
                agent_id=aid, agent_type="Explore", task=f"Task {aid}",
                budget_steps=1, depth=0,
            )
            pool.submit(config)

        pool.wait_agent("a", timeout=5.0)
        pool.wait_agent("b", timeout=5.0)
        pool.wait_agent("c", timeout=5.0)

        assert len(results_order) == 3
        # b finishes first (shortest sleep)
        assert results_order[0] == "b"
        pool.shutdown(wait=True)

    def test_depth_rejection(self):
        pool = SubagentPool(max_workers=2, max_depth=2)
        pool.set_runner(_fake_runner)
        config = SubagentConfig(
            agent_id="deep_1", agent_type="Explore", task="Too deep",
            budget_steps=3, depth=3,
        )
        handle = pool.submit(config)
        assert handle.status == SubagentStatus.FAILED
        assert "Depth" in handle.error
        pool.shutdown(wait=True)

    def test_drain_notifications(self):
        pool = SubagentPool(max_workers=2)
        pool.set_runner(_fake_runner)
        config = SubagentConfig(
            agent_id="drain_1", agent_type="Explore", task="Task",
            budget_steps=3, depth=0,
        )
        pool.submit(config)
        pool.wait_agent("drain_1", timeout=5.0)
        notifs = pool.drain_notifications()
        assert len(notifs) == 1
        assert notifs[0]["agent_id"] == "drain_1"
        assert notifs[0]["status"] == "completed"
        # Drain is idempotent -- second call returns empty
        notifs2 = pool.drain_notifications()
        assert len(notifs2) == 0
        pool.shutdown(wait=True)


class TestSubagentPolicy:
    def test_explore_tools_are_read_only(self):
        tools = tool_whitelist_for_type("Explore")
        assert tools is not None
        write_tools = {"file_editor.write_file", "file_editor.replace_text", "command_runner.run"}
        assert write_tools.isdisjoint(tools)

    def test_plan_tools_include_task_management(self):
        tools = tool_whitelist_for_type("Plan")
        assert tools is not None
        assert "task.create" in tools
        assert "task.update" in tools
        assert "task.list" in tools

    def test_general_purpose_has_no_restrictions(self):
        tools = tool_whitelist_for_type("general-purpose")
        assert tools is None  # None = all allowed

    def test_unknown_type_gets_empty_set(self):
        tools = tool_whitelist_for_type("non-existent")
        assert tools == frozenset()

    def test_depth_check_allows_valid(self):
        result = check_depth(2, max_depth=2)
        assert result["ok"] is True

    def test_depth_check_rejects_exceeded(self):
        result = check_depth(3, max_depth=2)
        assert result["ok"] is False
        assert result["error"]["code"] == "MAX_SPAWN_DEPTH_EXCEEDED"
