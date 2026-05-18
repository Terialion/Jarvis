from __future__ import annotations

from uuid import uuid4

from .audit import GatewayAuditStore
from .channel_directory import ChannelDirectory
from .mcp import MCPGatewayService
from .schema import GatewayRequest, GatewayResponse
from ..agent.loop import AgentLoop
from ..agent.types import ChatInput
from ..coding.workflow import CodingWorkflow
from ..store.memory_store import MemoryStore
from ..store.redaction import redact_for_persistence
from ..store import ThreadStore


class GatewayService:
    def __init__(
        self,
        *,
        channel_directory: ChannelDirectory,
        audit_store: GatewayAuditStore,
        thread_store: ThreadStore,
        memory_store: MemoryStore,
        benchmark_loader,
    ) -> None:
        self.channel_directory = channel_directory
        self.audit_store = audit_store
        self.thread_store = thread_store
        self.memory_store = memory_store
        self.benchmark_loader = benchmark_loader
        self.mcp = MCPGatewayService(
            channel_directory=channel_directory,
            audit_store=audit_store,
            thread_store=thread_store,
            memory_store=memory_store,
            benchmark_loader=benchmark_loader,
            agent_runner=self.run_agent,
            coding_runner=self.run_coding,
        )

    def run_agent(self, *, text: str, thread_id: str) -> dict:
        loop = AgentLoop(
            project_root=".",
            permission_mode="workspace_write",
            auto_approve=False,
        )
        result = loop.run_turn(ChatInput(text=text, cwd=".", session_id=thread_id, metadata={"source": "gateway"}))
        return result.to_dict()

    def run_coding(self, *, action: str, target: str, apply: bool = False) -> dict:
        workflow = CodingWorkflow(
            project_root=".",
            auto_approve=False,
            thread_store=self.thread_store,
            session_id=f"gateway_coding_{uuid4().hex[:8]}",
        )
        if action == "review":
            run = workflow.review(target or ".")
        elif action == "test":
            run = workflow.run_tests(target or None)
        elif action == "fix":
            run = workflow.fix(target or None, apply=apply, run_tests_after=True)
        else:
            raise ValueError(f"unsupported coding action: {action}")
        return workflow.to_agent_result(run).to_dict()

    def run_gateway(self, request: GatewayRequest) -> GatewayResponse:
        result = self.run_agent(text=request.text, thread_id=request.metadata.get("thread_id") or request.request_id)
        return GatewayResponse(
            request_id=request.request_id,
            status=str(result.get("status") or "completed"),
            output=str(result.get("final_answer") or ""),
            agent_result=redact_for_persistence(result),
            events_redacted=list(redact_for_persistence(result.get("events") or [])),
        )

