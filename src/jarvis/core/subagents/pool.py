"""SubagentPool — ThreadPoolExecutor-based parallel subagent execution.

Follows Hermes-Agent's delegate_task pattern: submit returns immediately,
results collected via drain-then-inject before each LLM call.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Lock
from typing import Any, Callable

from .models import SubagentConfig, SubagentHandle, SubagentStatus


class SubagentPool:
    """Manages parallel subagent execution via ThreadPoolExecutor."""

    def __init__(self, max_workers: int = 4, max_depth: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._agents: dict[str, SubagentHandle] = {}
        self._futures: dict[str, Future] = {}
        self._lock = Lock()
        self._notification_queue: list[dict[str, Any]] = []
        self.max_depth = max_depth
        self._run_fn: Callable | None = None  # set by AgentLoop after init

        # Metrics (align with Codex)
        self.spawn_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.total_steps = 0
        self.total_tokens = 0
        self.max_depth_reached = 0

    def set_runner(self, fn: Callable) -> None:
        """Set the function used to run a subagent in a thread."""
        self._run_fn = fn

    def submit(self, config: SubagentConfig) -> SubagentHandle:
        """Submit a subagent for async execution. Returns immediately."""
        if self._run_fn is None:
            raise RuntimeError("SubagentPool.run_fn not set -- call set_runner() first")

        if config.depth > self.max_depth:
            return SubagentHandle(
                agent_id=config.agent_id,
                agent_type=config.agent_type,
                status=SubagentStatus.FAILED,
                error=f"Depth {config.depth} exceeds max {self.max_depth}",
                depth=config.depth,
            )

        handle = SubagentHandle(
            agent_id=config.agent_id,
            agent_type=config.agent_type,
            status=SubagentStatus.RUNNING,
            max_steps=config.budget_steps,
            depth=config.depth,
        )

        future = self._executor.submit(self._run_wrapped, config, handle)
        with self._lock:
            self._agents[config.agent_id] = handle
            self._futures[config.agent_id] = future
            self.spawn_count += 1
            self.max_depth_reached = max(self.max_depth_reached, config.depth)

        return handle

    def _run_wrapped(self, config: SubagentConfig, handle: SubagentHandle) -> None:
        try:
            result = self._run_fn(config)
            with self._lock:
                handle.status = SubagentStatus.COMPLETED
                handle.result = str(result.get("final_answer", ""))[:8000]
                handle.steps = int(result.get("steps", 0))
                handle.total_tokens = int(result.get("total_tokens", 0))
                self.completed_count += 1
                self.total_steps += handle.steps
                self.total_tokens += handle.total_tokens
                self._notification_queue.append({
                    "agent_id": config.agent_id,
                    "agent_type": config.agent_type,
                    "status": "completed",
                    "result": handle.result,
                    "steps": handle.steps,
                    "total_tokens": handle.total_tokens,
                })
        except Exception as exc:
            with self._lock:
                handle.status = SubagentStatus.FAILED
                handle.error = str(exc)
                self.failed_count += 1
                self._notification_queue.append({
                    "agent_id": config.agent_id,
                    "agent_type": config.agent_type,
                    "status": "failed",
                    "error": str(exc),
                })

    def list_agents(self) -> list[dict[str, Any]]:
        """Return status of all agents (active and completed)."""
        with self._lock:
            return [
                {
                    "agent_id": h.agent_id,
                    "agent_type": h.agent_type,
                    "status": h.status.value,
                    "steps": h.steps,
                    "max_steps": h.max_steps,
                    "depth": h.depth,
                    "error": h.error,
                }
                for h in self._agents.values()
            ]

    def wait_agent(self, agent_id: str, timeout: float = 60.0) -> dict[str, Any]:
        """Block until a specific agent completes or timeout expires."""
        with self._lock:
            handle = self._agents.get(agent_id)
            future = self._futures.get(agent_id)
            if handle is None:
                return {"agent_id": agent_id, "status": "not_found"}
            status = handle.status
            result = handle.result
            error = handle.error
        if status in (SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.CANCELLED):
            return {"agent_id": agent_id, "status": status.value, "result": result, "error": error}
        if future is not None:
            try:
                future.result(timeout=timeout)
            except FutureTimeoutError:
                pass
        with self._lock:
            h = self._agents.get(agent_id)
            if h is None:
                return {"agent_id": agent_id, "status": "not_found"}
            return {"agent_id": agent_id, "status": h.status.value, "result": h.result, "error": h.error}

    def close_agent(self, agent_id: str) -> bool:
        """Cancel a running agent. Returns True if cancelled."""
        with self._lock:
            handle = self._agents.get(agent_id)
            future = self._futures.get(agent_id)
            if handle is None:
                return False
            status = handle.status
        if status != SubagentStatus.RUNNING:
            return False
        if future is not None and not future.done():
            future.cancel()
        with self._lock:
            handle.status = SubagentStatus.CANCELLED
        return True

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for h in self._agents.values() if h.status == SubagentStatus.RUNNING)

    def drain_notifications(self) -> list[dict[str, Any]]:
        """Return and clear all pending completion notifications."""
        with self._lock:
            notifs = list(self._notification_queue)
            self._notification_queue.clear()
        return notifs

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
