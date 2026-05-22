"""Tool registry/executor bridge for AgentLoop."""

from __future__ import annotations

import concurrent.futures
import os
import re
import time
from pathlib import Path
from typing import cast
from typing import Any

from typing import Callable

from ..core.background import BackgroundTaskManager
from ..core.subagents.pool import SubagentPool
from ..core.subagents.tools import (
    handle_close_agent,
    handle_list_agents,
    handle_spawn_agent,
    handle_wait_agent,
)
from ..core.checkpoint_manager import CheckpointManager
from ..core.command_runner import CommandRunner
from ..core.failure_analyzer import FailureAnalyzer
from ..core.file_editor import FileEditor
from ..core.policy import (
    ApprovalStore,
    HookInput,
    HookRegistry,
    PermissionPolicy,
    ToolRule,
    default_security_hook_registry,
    get_approval_store,
    redact_args_preview,
)
from ..core.repo_reader import RepoReader
from ..core.test_runner import TestRunner
from ..core.tools.registry import ToolRegistry as CoreToolRegistry
from ..core.tools.schema import ToolCall as CoreToolCall
from ..core.tools.schema import ToolContext as CoreToolContext
from ..core.tools.schema import ToolResult as CoreToolResult
from ..core.tools.schema import ToolSpec as CoreToolSpec
from ..skills.loader import SkillLoader
from ..skills.registry import SkillRegistry
from ..store.memory_store import MemoryStore
from ..web.cache import WebCache
from ..web.browser import run_web_browse
from ..web.fetch import HttpFetchTransport, run_web_fetch
from ..web.providers.router import ProviderRouter
from ..web.schema import FetchRequest, SearchQuery
from ..web.search import run_web_search
from ..web.safety import block_reason_for_url
from .types import AgentEvent
from .types import ToolCall, ToolResult, ToolSpec


class ToolRegistryAdapter:
    """Collect and expose tool specs, backed by existing Jarvis core tools."""

    def __init__(
        self,
        *,
        project_root: str,
        permission_mode: str = "workspace_write",
        memory_store: MemoryStore | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        thread_store: Any = None,
        bg_task_manager: BackgroundTaskManager | None = None,
        mcp_client: Any = None,
        user_prompt: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.project_root = str(Path(project_root).resolve())
        self.permission_mode = permission_mode
        self.allow_live_web = True
        self.memory_store = memory_store or MemoryStore()
        self.checkpoint_manager = checkpoint_manager
        self.thread_store = thread_store
        self.bg_task_manager = bg_task_manager or BackgroundTaskManager(max_workers=4)
        self.subagent_pool = SubagentPool(max_workers=4, max_depth=2)
        self._mcp_client = mcp_client  # lazy-init: use _get_mcp_client()
        self.user_prompt = user_prompt  # callback for agent.ask_user

        from ..core.tasks.manager import PersistentTaskManager
        self.persistent_task_manager = PersistentTaskManager(
            tasks_dir=Path(self.project_root) / ".jarvis" / "tasks"
        )

        self.repo_reader = RepoReader()
        self.file_editor = FileEditor(project_root=self.project_root)
        self.command_runner = CommandRunner()
        self.test_runner = TestRunner(test_commands=["pytest"])
        self.failure_analyzer = FailureAnalyzer()
        self.skill_loader = SkillLoader()
        self.skill_registry = SkillRegistry(project_root=self.project_root)
        self.web_router = ProviderRouter(default_provider="bing")
        self.web_cache = WebCache()
        self.web_transport = HttpFetchTransport()
        self.hook_registry = default_security_hook_registry()

        from ..core.teams import MessageBus, TeammateManager
        from ..core.teams.protocols import PlanTracker, ShutdownTracker
        team_dir = Path(self.project_root) / ".jarvis" / "team"
        self.message_bus = MessageBus(inbox_dir=team_dir / "inbox")
        self.teammate_manager = TeammateManager(
            team_dir=team_dir,
            bus=self.message_bus,
            tool_registry=self,
        )
        self.shutdown_tracker = ShutdownTracker()
        self.plan_tracker = PlanTracker()

        from ..core.worktree import EventBus, WorktreeManager
        worktree_events = EventBus(Path(self.project_root) / ".jarvis" / "worktrees" / "events.jsonl")
        self.worktree_manager = WorktreeManager(
            repo_root=Path(self.project_root),
            tasks=self.persistent_task_manager,
            events=worktree_events,
        )

        self.core_registry = CoreToolRegistry()
        self._register_core_specs()
        self._register_bg_tool_specs()
        self._register_team_tool_specs()
        self._register_worktree_tool_specs()
        self._register_mcp_tool_specs()
        self._register_subagent_tool_specs()

        # Wire subagent pool runner (model_client set later by AgentLoop)
        from ..core.subagents.runner import SubagentRunner
        _runner = SubagentRunner(
            project_root=self.project_root,
            model_client=None,
            tool_registry=self,
        )
        self.subagent_pool.set_runner(_runner.run)

    def list_tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for spec in self.core_registry.list_all():
            specs.append(
                ToolSpec(
                    name=spec.name,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    risk_level=spec.risk_level,
                    requires_approval=spec.requires_approval,
                    permissions=sorted(spec.permissions),
                )
            )
        return specs

    def _register_core_specs(self) -> None:
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.search_files",
                description="Search files by text pattern in repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory to search in. Defaults to project root."},
                        "pattern": {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["pattern"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_search_files,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.read_file",
                description="Read a file from the local filesystem. Use this instead of cat/head/tail in terminal. Supports line-range slicing via start_line/end_line.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_read_file,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.list_tree",
                description="List files and directories in the repository tree. Use this to verify if directories/files exist before answering. Empty directories appear with '/' suffix. Use this instead of ls/dir in terminal.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to list. Defaults to project root."},
                        "path": {"type": "string", "description": "Subdirectory to focus on (alternative to repo_path)."},
                        "max_depth": {"type": "integer", "description": "Max directory depth (default 3)"},
                    },
                    "required": [],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_list_tree,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.grep",
                description="Fast content search using ripgrep. Use this instead of grep/rg in terminal. Usage: 'grep(pattern=\"def my_function\", glob=\"*.py\")' — find functio"
                            "n definitions. 'grep(pattern=\"TODO\", glob=\"*.ts\")' — find TODOs in TypeScript files."
                            " 'grep(pattern=\"import.*from\", glob=\"*.py\", context=2)' — show 2 lines around each match.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "The regular expression pattern to search for in file contents."
                        },
                        "glob": {
                            "type": "string",
                            "description": "Glob pattern to filter files (e.g. '*.py', '*.{ts,tsx}'). Maps to rg --glob."
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search in. Defaults to project root."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max number of matches to return (default 20)."
                        },
                        "context": {
                            "type": "integer",
                            "description": "Number of lines to show before and after each match (rg -C)."
                        },
                        "multiline": {
                            "type": "boolean",
                            "description": "Enable multiline mode where . matches newlines (rg --multiline-dotall)."
                        },
                    },
                    "required": ["pattern"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_grep,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.search_symbol",
                description="Search for a symbol (function/class/variable definition) in the repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory to search in. Defaults to project root."},
                        "symbol": {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["symbol"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_search_symbol,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="repo_reader.glob",
                description="Find files and directories by glob pattern (e.g. '*.py', 'src/**/*.ts', '*.{ts,tsx}'). Use this instead of ls/find/dir in terminal. Supports brace expansion and recursive '**' patterns.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern to match file paths (supports **, *, ?, [a-z], {ts,tsx})."},
                        "path": {"type": "string", "description": "Directory to search in. Defaults to project root."},
                        "max_results": {"type": "integer", "description": "Max matches to return (default 500)."},
                    },
                    "required": ["pattern"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_glob,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="file_editor.replace_text",
                description="Replace text in a file (single replacement).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to edit."},
                        "old_string": {"type": "string", "description": "Text to replace (alias: old, old_str)."},
                        "new_string": {"type": "string", "description": "Replacement text (alias: new, new_str)."},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"write"},
                handler=self._handle_replace_text,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="file_editor.insert_text",
                description="Insert text before or after an anchor string in a file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "anchor": {"type": "string", "description": "Text to find as insertion point."},
                        "content": {"type": "string", "description": "Text to insert."},
                        "position": {"type": "string", "description": "'before' or 'after' the anchor (default 'after')."},
                    },
                    "required": ["path", "anchor", "content"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"write"},
                handler=self._handle_insert_text,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="file_editor.write_file",
                description="Write or overwrite a file. Creates parent directories if needed, and automatically creates new files.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "create": {"type": "boolean", "description": "Allow creating a new file (default true)."},
                    },
                    "required": ["path", "content"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"write"},
                handler=self._handle_write_file,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="file_editor.diff",
                description="Show unified diff of changes made to a file since last snapshot.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_diff,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="command_runner.run",
                description="Run a shell command. Only use for actual execution — do NOT use for reading/searching files (use repo_reader tools instead). Do NOT use cat/head/tail/ls/find/grep — use repo_reader.read_file, repo_reader.glob, or repo_reader.grep instead.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                        "timeout_s": {"type": "integer"},
                    },
                    "required": ["command"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"shell"},
                handler=self._handle_command_run,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="test_runner.run_test",
                description="Run tests. Pass a shell command like 'pytest tests/' or 'python -m pytest'. Falls back to 'pytest' if no command given.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to run tests (e.g. 'pytest tests/', 'python -m pytest tests/test_foo.py')."},
                        "cwd": {"type": "string", "description": "Working directory for the test command."},
                        "timeout_s": {"type": "integer", "description": "Timeout in seconds (default 60)."},
                    },
                    "required": [],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=True,
                permissions={"shell"},
                handler=self._handle_test_run,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="skill.load",
                description="Load the full body of a named SKILL.md document.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_skill_load,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="skill.run",
                description="Invoke an executable Jarvis skill by name with JSON arguments.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read", "shell"},
                handler=self._handle_skill_run_marker,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="web.search",
                description="Search the web via providerized search without fetching page bodies.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "provider": {"type": "string"},
                        "engine": {"type": "string"},
                        "top_k": {"type": "integer"},
                        "freshness": {"type": "string"},
                        "site": {"type": "string"},
                        "task_id": {"type": "string"},
                    },
                    "required": ["query"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_web_search,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="task.delegate",
                description="Delegate a sub-task to a sub-agent that runs autonomously.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "budget_steps": {"type": "integer"},
                    },
                    "required": ["task"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read", "shell"},
                handler=self._handle_task_delegate,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="checkpoint.create",
                description="Create a restorable checkpoint of current task state and optionally snapshot changed files.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task identifier to checkpoint."},
                        "label": {"type": "string", "description": "Human-readable checkpoint label."},
                        "file_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of file paths to snapshot for rollback.",
                        },
                    },
                    "required": ["task_id", "label"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_checkpoint_create,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="checkpoint.rollback",
                description="Roll back task state and files to a previously created checkpoint. Requires approval.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "checkpoint_id": {"type": "string"},
                    },
                    "required": ["task_id", "checkpoint_id"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"write"},
                handler=self._handle_checkpoint_rollback,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="checkpoint.list",
                description="List all checkpoints for a task.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                    },
                    "required": ["task_id"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_checkpoint_list,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="memory.search",
                description="Search typed memory (feedback, references, user profile, project facts) using full-text search.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query."},
                        "memory_type": {
                            "type": "string",
                            "description": "Optional: feedback, reference, user_profile, project_fact",
                        },
                        "limit": {"type": "integer", "description": "Max results (default 10)."},
                    },
                    "required": ["query"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_memory_search,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="memory.write",
                description="Write a typed memory record to persistent storage for future context.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "memory_type": {
                            "type": "string",
                            "description": "Type: feedback, reference, user_profile, or project_fact.",
                        },
                        "key": {"type": "string", "description": "Short label for this memory."},
                        "value": {"type": "string", "description": "The information to remember."},
                    },
                    "required": ["memory_type", "key", "value"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_memory_write,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="memory.remember",
                description="Remember a fact for future conversations. Auto-infers memory type from content.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Short label (e.g. 'user_name', 'project_stack')."},
                        "value": {"type": "string", "description": "The information to remember."},
                    },
                    "required": ["key", "value"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_memory_remember,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="task.create",
                description="Create a structured task plan with ordered steps to accomplish a goal.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "What this plan aims to accomplish."},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "depends_on": {"type": "array", "items": {"type": "string"}},
                                    "estimated_tool": {"type": "string"},
                                },
                                "required": ["description"],
                            },
                            "description": "Ordered list of plan steps.",
                        },
                    },
                    "required": ["goal", "steps"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_task_create,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="task.update",
                description="Update step statuses or add steps to an existing plan.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plan_id": {"type": "string", "description": "Plan identifier."},
                        "step_updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "step_id": {"type": "string"},
                                    "status": {"type": "string", "description": "pending|in_progress|completed|failed"},
                                    "result": {"type": "string"},
                                },
                            },
                            "description": "Step status updates.",
                        },
                        "new_steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "depends_on": {"type": "array", "items": {"type": "string"}},
                                    "estimated_tool": {"type": "string"},
                                },
                            },
                            "description": "New steps to append.",
                        },
                    },
                    "required": ["plan_id"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_task_update,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="task.list",
                description="List task plans for the current session.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "all_sessions": {
                            "type": "boolean",
                            "description": "If true, list tasks from all sessions, not just the current one.",
                        },
                    },
                    "required": [],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_task_list,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="task.get",
                description="Get full details of a task plan by plan_id, including step statuses.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plan_id": {"type": "string", "description": "Plan identifier."},
                    },
                    "required": ["plan_id"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_task_get,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="web.fetch",
                description="Safely fetch a readable web document via HTTP GET without executing JavaScript.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "extract_mode": {"type": "string"},
                        "max_chars": {"type": "integer"},
                        "provenance": {"type": "object"},
                    },
                    "required": ["url"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_web_fetch,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="web.browse",
                description="Browse a web page using headless browser — renders JavaScript (SPA pages). Use for pages that web.fetch can't extract. Returns rendered text and interactive elements.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Page URL to browse."},
                        "action": {"type": "string", "description": "'snapshot' (text + elements) or 'screenshot' (includes image). Default: snapshot."},
                    },
                    "required": ["url"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_web_browse,
            )
        )

    def _register_bg_tool_specs(self) -> None:
        """Register background task tools."""
        self.core_registry.register(
            CoreToolSpec(
                name="bg.task.run",
                description="Run a function in the background. Use for long-running operations like tests or web fetches. Returns a task_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "Short description of the task"},
                        "tool_name": {"type": "string", "description": "Name of the tool to run in background (e.g. test_runner.run_test)"},
                        "tool_arguments": {"type": "object", "description": "Arguments for the tool"},
                    },
                    "required": ["tool_name"],
                },
                risk_level="medium",
                requires_approval=False,
                permissions={"shell"},
                output_schema={"type": "object"},
                handler=self._handle_bg_task_run,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="bg.task.check",
                description="Check the status of a background task. Returns status and result if completed.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "The task_id returned by bg.task.run"},
                        "wait": {"type": "boolean", "description": "Block until task completes (default: false)"},
                        "timeout": {"type": "number", "description": "Max seconds to wait when wait=true"},
                    },
                    "required": ["task_id"],
                },
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                output_schema={"type": "object"},
                handler=self._handle_bg_task_check,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="bg.task.cancel",
                description="Cancel a running background task.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "The task_id to cancel"},
                    },
                    "required": ["task_id"],
                },
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                output_schema={"type": "object"},
                handler=self._handle_bg_task_cancel,
            )
        )

    def _handle_bg_task_run(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        tool_name = str(arguments.get("tool_name") or "")
        tool_args = dict(arguments.get("tool_arguments") or {})
        description = str(arguments.get("description") or tool_name)

        # Resolve the target tool handler
        spec = self.core_registry.get(tool_name)
        if spec is None or spec.handler is None:
            return self._wrap_core_result("bg.task.run", {"ok": False, "error": f"Unknown tool: {tool_name}"})

        handler = spec.handler
        task_id = self.bg_task_manager.submit(
            description=description,
            fn=lambda h=handler, a=tool_args, c=context: h(a, c).to_dict(),
        )
        return self._wrap_core_result("bg.task.run", {"ok": True, "data": {"task_id": task_id, "status": "running"}})

    def _handle_bg_task_check(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        task_id = str(arguments.get("task_id") or "")
        wait = bool(arguments.get("wait", False))
        timeout = float(arguments.get("timeout", 30.0))
        if wait:
            status = self.bg_task_manager.check_blocking(task_id, timeout=timeout)
        else:
            status = self.bg_task_manager.check(task_id)
        return self._wrap_core_result("bg.task.check", {"ok": True, "data": status})

    def _handle_bg_task_cancel(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        task_id = str(arguments.get("task_id") or "")
        cancelled = self.bg_task_manager.cancel(task_id)
        return self._wrap_core_result("bg.task.cancel", {"ok": cancelled, "data": {"task_id": task_id, "cancelled": cancelled}})

    # ── Team tools ─────────────────────────────────────────────────

    def _register_team_tool_specs(self) -> None:
        self.core_registry.register(
            CoreToolSpec(
                name="team.spawn",
                description="Spawn a named teammate agent that runs autonomously in the background.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Unique name for the teammate."},
                        "role": {"type": "string", "description": "Role description (e.g. coder, tester, reviewer)."},
                        "prompt": {"type": "string", "description": "Initial task or goal for the teammate."},
                    },
                    "required": ["name", "role", "prompt"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_write"},
                handler=self._handle_team_spawn,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="team.list",
                description="List all teammates and their current status.",
                input_schema={"type": "object", "properties": {}, "required": []},
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_team_list,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="team.message",
                description="Send a message to a teammate.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Teammate name."},
                        "content": {"type": "string", "description": "Message content."},
                    },
                    "required": ["to", "content"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_team_message,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="team.inbox",
                description="Read and drain the lead's inbox for messages from teammates.",
                input_schema={"type": "object", "properties": {}, "required": []},
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_team_inbox,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="team.broadcast",
                description="Send a message to all teammates at once.",
                input_schema={
                    "type": "object",
                    "properties": {"content": {"type": "string", "description": "Broadcast message."}},
                    "required": ["content"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_team_broadcast,
            )
        )
        # Protocol tools (s10)
        self.core_registry.register(
            CoreToolSpec(
                name="team.shutdown",
                description="Request a teammate to shut down gracefully.",
                input_schema={
                    "type": "object",
                    "properties": {"teammate": {"type": "string", "description": "Teammate name to shut down."}},
                    "required": ["teammate"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_write"},
                handler=self._handle_team_shutdown,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="team.shutdown_status",
                description="Check the status of a shutdown request.",
                input_schema={
                    "type": "object",
                    "properties": {"request_id": {"type": "string"}},
                    "required": ["request_id"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_team_shutdown_status,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="team.plan_review",
                description="Approve or reject a teammate's plan approval request.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                        "approve": {"type": "boolean"},
                        "feedback": {"type": "string", "description": "Optional feedback on the plan."},
                    },
                    "required": ["request_id", "approve"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_write"},
                handler=self._handle_team_plan_review,
            )
        )

    # ── Team tool handlers ──────────────────────────────────────────

    def _handle_team_spawn(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        name = str(arguments.get("name") or "").strip()
        role = str(arguments.get("role") or "").strip()
        prompt = str(arguments.get("prompt") or "").strip()
        if not name or not role:
            return CoreToolResult(
                tool_name="team.spawn", ok=False,
                error="missing_fields: name and role are required",
                metadata={"error_code": "missing_fields"},
            )
        result = self.teammate_manager.spawn(name, role, prompt)
        return CoreToolResult(
            tool_name="team.spawn",
            ok=True,
            output=result,
            metadata={"result_code": "ok"},
        )

    def _handle_team_list(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        members = self.teammate_manager.list_all()
        return CoreToolResult(
            tool_name="team.list",
            ok=True,
            output={"members": members},
            metadata={"result_code": "ok"},
        )

    def _handle_team_message(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        to = str(arguments.get("to") or "").strip()
        content = str(arguments.get("content") or "").strip()
        if not to or not content:
            return CoreToolResult(
                tool_name="team.message", ok=False,
                error="missing_fields: to and content are required",
                metadata={"error_code": "missing_fields"},
            )
        result = self.message_bus.send("lead", to, content)
        return CoreToolResult(
            tool_name="team.message",
            ok=result.get("ok", False),
            output=result,
            metadata={"result_code": "ok" if result.get("ok") else "error"},
        )

    def _handle_team_inbox(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        msgs = self.message_bus.read_inbox("lead")
        return CoreToolResult(
            tool_name="team.inbox",
            ok=True,
            output={"messages": msgs},
            metadata={"result_code": "ok"},
        )

    def _handle_team_broadcast(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        content = str(arguments.get("content") or "").strip()
        if not content:
            return CoreToolResult(
                tool_name="team.broadcast", ok=False,
                error="missing_fields: content is required",
                metadata={"error_code": "missing_fields"},
            )
        teammates = self.teammate_manager.member_names()
        result = self.message_bus.broadcast("lead", content, teammates)
        return CoreToolResult(
            tool_name="team.broadcast",
            ok=True,
            output=result,
            metadata={"result_code": "ok"},
        )

    def _handle_team_shutdown(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        teammate = str(arguments.get("teammate") or "").strip()
        if not teammate:
            return CoreToolResult(
                tool_name="team.shutdown", ok=False,
                error="missing_fields: teammate is required",
                metadata={"error_code": "missing_fields"},
            )
        req_id = self.shutdown_tracker.create(teammate)
        self.message_bus.send(
            "lead", teammate,
            "Please shut down gracefully.",
            msg_type="shutdown_request",
            extra={"request_id": req_id},
        )
        return CoreToolResult(
            tool_name="team.shutdown",
            ok=True,
            output={"request_id": req_id, "teammate": teammate, "status": "pending"},
            metadata={"result_code": "ok"},
        )

    def _handle_team_shutdown_status(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        request_id = str(arguments.get("request_id") or "").strip()
        status = self.shutdown_tracker.status(request_id)
        if status is None:
            return CoreToolResult(
                tool_name="team.shutdown_status", ok=False,
                error=f"request_not_found:{request_id}",
                metadata={"error_code": "request_not_found"},
            )
        return CoreToolResult(
            tool_name="team.shutdown_status",
            ok=True,
            output=status,
            metadata={"result_code": "ok"},
        )

    def _handle_team_plan_review(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        request_id = str(arguments.get("request_id") or "").strip()
        approve = bool(arguments.get("approve", False))
        feedback = str(arguments.get("feedback") or "").strip()

        result = self.plan_tracker.review(request_id, approve, feedback)
        if result is None:
            return CoreToolResult(
                tool_name="team.plan_review", ok=False,
                error=f"request_not_found:{request_id}",
                metadata={"error_code": "request_not_found"},
            )
        return CoreToolResult(
            tool_name="team.plan_review",
            ok=True,
            output=result,
            metadata={"result_code": "ok"},
        )

    # ── Worktree tools ────────────────────────────────────────────────

    def _register_worktree_tool_specs(self) -> None:
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.create",
                description="Create a new git worktree for isolated work. Optionally bind to a task.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Worktree name (1-40 chars, alphanumeric + ._-)."},
                        "task_id": {"type": "string", "description": "Optional task ID to bind this worktree to."},
                        "base_ref": {"type": "string", "description": "Git ref to branch from (default: HEAD)."},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"shell"},
                handler=self._handle_worktree_create,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.list",
                description="List all managed worktrees and their status.",
                input_schema={"type": "object", "properties": {}, "required": []},
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_worktree_list,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.status",
                description="Show git status of a worktree.",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Worktree name."}},
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_worktree_status,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.run",
                description="Run a shell command inside a worktree directory.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Worktree name."},
                        "command": {"type": "string", "description": "Shell command to run."},
                    },
                    "required": ["name", "command"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"shell"},
                handler=self._handle_worktree_run,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.remove",
                description="Remove a worktree. Optionally mark its bound task as completed.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Worktree name."},
                        "force": {"type": "boolean", "description": "Force removal even with uncommitted changes."},
                        "complete_task": {"type": "boolean", "description": "Mark bound task as completed on removal."},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="high",
                requires_approval=True,
                permissions={"shell"},
                handler=self._handle_worktree_remove,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.keep",
                description="Mark a worktree as kept (preserved, not removed).",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Worktree name."}},
                    "required": ["name"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_worktree_keep,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="worktree.events",
                description="Show recent worktree lifecycle events.",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "description": "Max events to return (default 20)."}},
                    "required": [],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_worktree_events,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="task.bind_worktree",
                description="Bind a task to a worktree by name.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task plan identifier."},
                        "worktree": {"type": "string", "description": "Worktree name to bind."},
                    },
                    "required": ["task_id", "worktree"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_task_bind_worktree,
            )
        )

    # ── Subagent tools ──────────────────────────────────────────────────

    def _register_subagent_tool_specs(self) -> None:
        pool = self.subagent_pool

        self.core_registry.register(
            CoreToolSpec(
                name="spawn_agent",
                description=(
                    "Spawn a subagent that runs asynchronously in parallel. "
                    "Use agent_type='Explore' for search/read tasks, 'Plan' for planning, "
                    "'general-purpose' for full capabilities. Returns immediately with agent_id. "
                    "Use list_agents to check progress, wait_agent to block until completion."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Task description for the subagent."},
                        "agent_type": {
                            "type": "string",
                            "description": "Agent type: Explore (read-only search), Plan (read-only + task planning), general-purpose (all tools).",
                            "enum": ["Explore", "Plan", "general-purpose"],
                        },
                        "budget_steps": {"type": "integer", "description": "Max steps (default 10)."},
                        "depth": {"type": "integer", "description": "Nesting depth (0=top-level, 1=child, 2=grandchild)."},
                    },
                    "required": ["task"],
                },
                output_schema={"type": "object"},
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read", "shell"},
                handler=lambda args, ctx: handle_spawn_agent(args, ctx, pool),
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="wait_agent",
                description="Block until a specific subagent completes. Returns the agent's result.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The agent_id returned by spawn_agent."},
                        "timeout": {"type": "number", "description": "Max seconds to wait (default 60)."},
                    },
                    "required": ["agent_id"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=lambda args, ctx: handle_wait_agent(args, ctx, pool),
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="list_agents",
                description="List all subagents with their status (running/completed/failed) and progress.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=lambda args, ctx: handle_list_agents(args, ctx, pool),
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="close_agent",
                description="Cancel a running subagent by agent_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The agent_id to cancel."},
                    },
                    "required": ["agent_id"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=lambda args, ctx: handle_close_agent(args, ctx, pool),
            )
        )

    # ── Worktree tool handlers ────────────────────────────────────────

    def _handle_worktree_create(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        name = str(arguments.get("name") or "").strip()
        task_id = str(arguments.get("task_id") or "").strip() or None
        base_ref = str(arguments.get("base_ref") or "HEAD").strip()
        if not name:
            return CoreToolResult(
                tool_name="worktree.create", ok=False,
                error="missing_fields: name is required",
                metadata={"error_code": "missing_fields"},
            )
        result = self.worktree_manager.create(name, task_id=task_id, base_ref=base_ref)
        return CoreToolResult(
            tool_name="worktree.create",
            ok=result.get("ok", False),
            output=result.get("worktree") if result.get("ok") else result.get("error"),
            error=result.get("error"),
            metadata={"result_code": "ok" if result.get("ok") else "worktree_create_failed"},
        )

    def _handle_worktree_list(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        data = self.worktree_manager.list_all()
        return CoreToolResult(
            tool_name="worktree.list",
            ok=True,
            output=data,
            metadata={"result_code": "ok"},
        )

    def _handle_worktree_status(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        name = str(arguments.get("name") or "").strip()
        result = self.worktree_manager.status(name)
        return CoreToolResult(
            tool_name="worktree.status",
            ok=result.get("ok", False),
            output=result.get("status_output"),
            error=result.get("error"),
            metadata={"result_code": "ok" if result.get("ok") else "worktree_status_failed"},
        )

    def _handle_worktree_run(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        name = str(arguments.get("name") or "").strip()
        command = str(arguments.get("command") or "").strip()
        if not name or not command:
            return CoreToolResult(
                tool_name="worktree.run", ok=False,
                error="missing_fields: name and command are required",
                metadata={"error_code": "missing_fields"},
            )
        result = self.worktree_manager.run(name, command)
        return CoreToolResult(
            tool_name="worktree.run",
            ok=result.get("ok", False),
            output={"stdout": result.get("stdout"), "stderr": result.get("stderr"), "returncode": result.get("returncode")},
            error=result.get("error"),
            metadata={"result_code": "ok" if result.get("ok") else "worktree_run_failed"},
        )

    def _handle_worktree_remove(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        name = str(arguments.get("name") or "").strip()
        force = bool(arguments.get("force", False))
        complete_task = bool(arguments.get("complete_task", False))
        result = self.worktree_manager.remove(name, force=force, complete_task=complete_task)
        return CoreToolResult(
            tool_name="worktree.remove",
            ok=result.get("ok", False),
            output=result.get("worktree"),
            error=result.get("error"),
            metadata={"result_code": "ok" if result.get("ok") else "worktree_remove_failed"},
        )

    def _handle_worktree_keep(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        name = str(arguments.get("name") or "").strip()
        result = self.worktree_manager.keep(name)
        return CoreToolResult(
            tool_name="worktree.keep",
            ok=result.get("ok", False),
            output=result.get("worktree"),
            error=result.get("error"),
            metadata={"result_code": "ok" if result.get("ok") else "worktree_keep_failed"},
        )

    def _handle_worktree_events(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        limit = int(arguments.get("limit") or 20)
        entries = self.worktree_manager.events.list_recent(limit=limit) if self.worktree_manager.events else []
        return CoreToolResult(
            tool_name="worktree.events",
            ok=True,
            output={"events": entries},
            metadata={"result_code": "ok"},
        )

    def _handle_task_bind_worktree(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        task_id = str(arguments.get("task_id") or "").strip()
        worktree = str(arguments.get("worktree") or "").strip()
        if not task_id or not worktree:
            return CoreToolResult(
                tool_name="task.bind_worktree", ok=False,
                error="missing_fields: task_id and worktree are required",
                metadata={"error_code": "missing_fields"},
            )
        result = self.persistent_task_manager.bind_worktree(task_id, worktree)
        if result is None:
            return CoreToolResult(
                tool_name="task.bind_worktree", ok=False,
                error=f"task_not_found:{task_id}",
                metadata={"error_code": "task_not_found"},
            )
        return CoreToolResult(
            tool_name="task.bind_worktree",
            ok=True,
            output=result,
            metadata={"result_code": "ok"},
        )

    def _register_mcp_tool_specs(self) -> None:
        self.core_registry.register(
            CoreToolSpec(
                name="mcp.list_servers",
                description="List connected MCP servers and their available tools.",
                input_schema={"type": "object", "properties": {}, "required": []},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                output_schema={"type": "object"},
                handler=self._handle_mcp_list_servers,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="mcp.call",
                description="Call a tool on an external MCP server. Use mcp.list_servers first to see available tools.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "server": {"type": "string", "description": "MCP server name."},
                        "tool": {"type": "string", "description": "Tool name on the server."},
                        "arguments": {"type": "object", "description": "Arguments to pass to the tool."},
                    },
                    "required": ["server", "tool"],
                },
                risk_level="medium",
                requires_approval=False,
                permissions={"repo_read", "shell"},
                output_schema={"type": "object"},
                handler=self._handle_mcp_call,
            )
        )
        self.core_registry.register(
            CoreToolSpec(
                name="agent.ask_user",
                description="Ask the user a question with predefined options. Use when you need clarification or a decision.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "The question to ask the user."},
                        "header": {"type": "string", "description": "Short label displayed as a chip/tag (max 12 chars)."},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string", "description": "Display text for the option (1-5 words)."},
                                    "description": {"type": "string", "description": "Explanation of what this option means."},
                                },
                                "required": ["label", "description"],
                            },
                            "description": "2-4 mutually exclusive options (or use multi_select).",
                        },
                        "multi_select": {"type": "boolean", "description": "Allow multiple answers to be selected (default false)."},
                    },
                    "required": ["question", "options"],
                },
                output_schema={"type": "object"},
                risk_level="low",
                requires_approval=False,
                permissions={"repo_read"},
                handler=self._handle_ask_user,
            )
        )

    def _get_mcp_client(self) -> Any:
        if self._mcp_client is None:
            from ..gateway.mcp_client import MCPClient
            self._mcp_client = MCPClient()
        return self._mcp_client

    def _handle_mcp_list_servers(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = arguments
        _ = context
        mcp = self._get_mcp_client()
        servers = []
        for name in mcp.server_names:
            try:
                tools = mcp.list_tools(name)
            except Exception:
                tools = []
            servers.append({
                "name": name,
                "tool_count": len(tools),
                "tools": [{"name": t.get("name"), "description": t.get("description", "")} for t in tools],
            })
        return self._wrap_core_result("mcp.list_servers", {"ok": True, "servers": servers})

    def _handle_mcp_call(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        server = str(arguments.get("server") or "")
        tool = str(arguments.get("tool") or "")
        tool_args = dict(arguments.get("arguments") or {})
        if not server or not tool:
            return self._wrap_core_result("mcp.call", {"ok": False, "error": "server and tool are required"})
        mcp = self._get_mcp_client()
        try:
            result = mcp.call_tool(server, tool, tool_args)
            return self._wrap_core_result("mcp.call", {"ok": True, "server": server, "tool": tool, "result": result})
        except Exception as exc:
            return self._wrap_core_result("mcp.call", {"ok": False, "error": str(exc)})

    def _handle_ask_user(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        question = str(arguments.get("question") or "")
        header = str(arguments.get("header") or "")
        options = list(arguments.get("options") or [])
        multi_select = bool(arguments.get("multi_select", False))

        if not question or not options:
            return self._wrap_core_result("agent.ask_user", {"ok": False, "error": {"code": "invalid_input", "message": "question and options are required"}})

        if self.user_prompt is None:
            return self._wrap_core_result("agent.ask_user", {"ok": False, "error": {"code": "no_user_available", "message": "No user prompt callback configured. Running in non-interactive mode."}})

        try:
            answer = self.user_prompt(question=question, header=header, options=options, multi_select=multi_select)
            return self._wrap_core_result("agent.ask_user", {"ok": True, "data": answer})
        except Exception as exc:
            return self._wrap_core_result("agent.ask_user", {"ok": False, "error": {"code": "prompt_failed", "message": str(exc)}})

    def _handle_grep(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        repo_path = str(arguments.get("path") or context.workspace_root or self.project_root)
        pattern = str(arguments.get("pattern") or "")
        glob_filter = arguments.get("glob")
        max_results = int(arguments.get("max_results") or 20)
        ctx = int(arguments.get("context") or 0)
        multiline = bool(arguments.get("multiline"))
        result = self.repo_reader.grep(
            repo_path=repo_path, pattern=pattern, glob=glob_filter,
            max_results=max_results, context=ctx, multiline=multiline,
        )
        return self._wrap_core_result("repo_reader.grep", result)

    def _handle_search_files(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        repo_path = str(arguments.get("path") or arguments.get("repo_path") or context.workspace_root or self.project_root)
        pattern = str(arguments.get("pattern") or "")
        max_results = int(arguments.get("max_results") or 20)
        result = self.repo_reader.grep(repo_path=repo_path, pattern=pattern, max_results=max_results)
        return self._wrap_core_result("repo_reader.search_files", result)

    def _handle_read_file(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        path = str(arguments.get("path") or arguments.get("file_path") or "")
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        result = self.repo_reader.read_file(path=path, start_line=start_line, end_line=end_line)
        return self._wrap_core_result("repo_reader.read_file", result)

    def _handle_list_tree(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        repo_path = str(arguments.get("path") or arguments.get("repo_path") or context.workspace_root or self.project_root)
        max_depth = int(arguments.get("max_depth") or 3)
        result = self.repo_reader.list_tree(repo_path=repo_path, max_depth=max_depth)
        return self._wrap_core_result("repo_reader.list_tree", result)

    def _handle_search_symbol(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        repo_path = str(arguments.get("path") or arguments.get("repo_path") or context.workspace_root or self.project_root)
        symbol = str(arguments.get("symbol") or "")
        max_results = int(arguments.get("max_results") or 20)
        # Use grep with regex to find actual definitions: class X, def X, etc.
        pattern = rf"\b(def|class|async\s+def)\s+{re.escape(symbol)}\b"
        result = self.repo_reader.grep(repo_path=repo_path, pattern=pattern, max_results=max_results)
        return self._wrap_core_result("repo_reader.search_symbol", result)

    def _handle_glob(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        pattern = str(arguments.get("pattern") or "")
        if not pattern:
            return self._wrap_core_result("repo_reader.glob", {"ok": False, "error": {"code": "missing_pattern", "message": "pattern is required"}})
        search_path = Path(str(arguments.get("path") or context.workspace_root or self.project_root))
        if not search_path.exists():
            return self._wrap_core_result("repo_reader.glob", {"ok": False, "error": {"code": "path_not_found", "message": f"path not found: {search_path}"}})
        max_results = int(arguments.get("max_results") or 500)

        # Expand brace patterns (e.g. "*.{ts,tsx}" -> ["*.ts", "*.tsx"])
        patterns = self._expand_braces(pattern)
        matches_set: dict[str, Path] = {}  # use relative path as key for dedup
        for pat in patterns:
            try:
                for p in search_path.glob(pat):
                    key = str(p.relative_to(search_path)).replace("\\", "/")
                    if key not in matches_set:
                        matches_set[key] = p
                    if len(matches_set) >= max_results:
                        break
            except Exception:
                continue
            if len(matches_set) >= max_results:
                break

        matches = sorted(matches_set.values(), key=lambda p: (not p.is_dir(), str(p)))[:max_results]
        items = [
            {"path": str(p.relative_to(search_path)).replace("\\", "/"), "type": "dir" if p.is_dir() else "file"}
            for p in matches
        ]
        if len(matches_set) >= max_results:
            items.append({"path": "...", "type": "truncated", "note": f"output truncated at {max_results} matches"})
        return self._wrap_core_result("repo_reader.glob", {"ok": True, "data": {"pattern": pattern, "matches": items}})

    @staticmethod
    def _expand_braces(pattern: str) -> list[str]:
        """Expand brace patterns like '*.{ts,tsx}' into ['*.ts', '*.tsx']."""
        import re
        brace_re = re.compile(r'\{([^{}]+)\}')
        m = brace_re.search(pattern)
        if not m:
            return [pattern]
        alternatives = [alt.strip() for alt in m.group(1).split(",")]
        prefix = pattern[:m.start()]
        suffix = pattern[m.end():]
        results: list[str] = []
        for alt in alternatives:
            # Recurse in case of nested braces
            expanded = ToolRegistryAdapter._expand_braces(prefix + alt + suffix)
            results.extend(expanded)
        return results

    def _handle_replace_text(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        result = self.file_editor.replace_text(
            path=str(arguments.get("path") or arguments.get("file_path") or ""),
            old=str(arguments.get("old") or arguments.get("old_string") or arguments.get("old_str") or ""),
            new=str(arguments.get("new") or arguments.get("new_string") or arguments.get("new_str") or ""),
        )
        wrapped = self._wrap_core_result("file_editor.replace_text", result)
        if wrapped.ok:
            wrapped.metadata["changed_files"] = [str(arguments.get("path") or "")]
        return wrapped

    def _handle_insert_text(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        result = self.file_editor.insert_text(
            path=str(arguments.get("path") or arguments.get("file_path") or ""),
            anchor=str(arguments.get("anchor") or ""),
            content=str(arguments.get("content") or ""),
            position=str(arguments.get("position") or "after"),
        )
        wrapped = self._wrap_core_result("file_editor.insert_text", result)
        if wrapped.ok:
            wrapped.metadata["changed_files"] = [str(arguments.get("path") or "")]
        return wrapped

    def _handle_write_file(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        result = self.file_editor.write_file(
            path=str(arguments.get("path") or arguments.get("file_path") or ""),
            content=str(arguments.get("content") or ""),
            create=bool(arguments.get("create", True)),
        )
        wrapped = self._wrap_core_result("file_editor.write_file", result)
        if wrapped.ok:
            wrapped.metadata["changed_files"] = [str(arguments.get("path") or "")]
        return wrapped

    def _handle_diff(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        result = self.file_editor.diff(path=str(arguments.get("path") or arguments.get("file_path") or ""))
        return self._wrap_core_result("file_editor.diff", result)

    def _handle_command_run(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        command = str(arguments.get("command") or "")
        cwd = str(arguments.get("cwd") or context.workspace_root or self.project_root)
        timeout_s = int(arguments.get("timeout_s") or 30)
        result = self.command_runner.run(command=command, cwd=cwd, timeout_s=timeout_s)
        wrapped = self._wrap_core_result("command_runner.run", result)
        wrapped.metadata["commands_run"] = [command]
        if "pytest" in command.lower():
            wrapped.metadata["tests_run"] = [command]
        return wrapped

    def _handle_test_run(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        command = arguments.get("command")
        cwd = str(arguments.get("cwd") or context.workspace_root or self.project_root)
        timeout_s = int(arguments.get("timeout_s") or 60)
        result = self.test_runner.run_test(command=command, cwd=cwd, timeout_s=timeout_s)
        wrapped = self._wrap_core_result("test_runner.run_test", result)
        wrapped.metadata["tests_run"] = [str((result.get("data") or {}).get("command") or command or "default")]
        return wrapped

    def _handle_skill_load(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        name = str(arguments.get("name") or "").strip()
        if not name:
            return CoreToolResult(
                tool_name="skill.load",
                ok=False,
                error="missing_skill_name",
                metadata={"error_code": "missing_skill_name"},
            )
        try:
            spec = self.skill_registry.get_loadable(name)
        except KeyError:
            return CoreToolResult(
                tool_name="skill.load",
                ok=False,
                error=f"skill_not_found:{name}",
                metadata={"error_code": "skill_not_found", "skill_name": name},
            )
        except PermissionError as exc:
            code = str(exc)
            return CoreToolResult(
                tool_name="skill.load",
                ok=False,
                error=code,
                metadata={"error_code": code, "skill_name": name},
            )
        body = self.skill_registry.load_body(name)
        skill_dir = str(Path(spec.path).parent)
        if "${SKILL_DIR}" in body:
            body = body.replace("${SKILL_DIR}", skill_dir)
        config_block = self._build_skill_config_block(spec)
        parts = [
            f'<skill name="{spec.name}">',
            body.strip(),
            "</skill>",
        ]
        if config_block:
            parts.append(config_block)
        parts.append("")
        parts.append(
            "Now follow the skill instructions above to help the user. "
            "After completing the steps, produce a final answer. "
            "Do NOT reload this skill — you already have its full instructions."
        )
        wrapped = "\n".join(parts)
        return CoreToolResult(
            tool_name="skill.load",
            ok=True,
            output=wrapped,
            metadata={
                "result_code": "ok",
                "skill_name": spec.name,
                "risk_level": spec.risk_level,
                "allowed_tools": list(spec.allowed_tools),
                "skill_path": spec.path,
            },
        )

    @staticmethod
    def _build_skill_config_block(spec: Any) -> str | None:
        """Build a [Skill config: ...] block from declared config variables.

        Looks for config declarations in spec.metadata.config or
        spec.metadata.jarvis.config.  Resolves values from environment
        variables with fallback to declared defaults.
        """
        raw_config = spec.metadata.get("config") or spec.metadata.get("jarvis", {}).get("config")
        if not raw_config:
            return None
        if isinstance(raw_config, dict):
            raw_config = [raw_config]
        if not isinstance(raw_config, list):
            return None

        pairs: list[tuple[str, str]] = []
        for item in raw_config:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if not key:
                continue
            value = os.environ.get(key, item.get("default", ""))
            pairs.append((key, str(value) if value else "(not set)"))

        if not pairs:
            return None

        lines = ["[Skill config:"]
        for key, value in pairs:
            lines.append(f"  {key} = {value}")
        lines.append("]")
        return "\n".join(lines)

    def _handle_skill_run_marker(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = arguments, context
        return CoreToolResult(
            tool_name="skill.run",
            ok=False,
            error="skill_run_must_be_handled_by_agent_loop",
            metadata={"error_code": "skill_run_agent_loop_boundary"},
        )

    def _handle_task_delegate(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        task = str(arguments.get("task") or "").strip()
        if not task:
            return CoreToolResult(
                tool_name="task.delegate",
                ok=False,
                error="task.delegate requires a non-empty task description.",
                metadata={"error_code": "empty_task"},
            )
        try:
            from ..core.subagents.models import SubagentRun
            from ..core.subagents.runner import SubagentRunner

            budget = int(arguments.get("budget_steps") or 4)
            runner = SubagentRunner(
                project_root=self.project_root,
                tool_registry=self,
            )
            subagent_run = SubagentRun(
                subagent_id=f"sub_{context.request_id or 'delegate'}",
                parent_run_id=context.session_id or "",
                task=task,
                budget_steps=min(max(1, budget), 20),
            )
            result = runner.run_subtask(subagent_run)
            return CoreToolResult(
                tool_name="task.delegate",
                ok=result.get("status") != "failed",
                output=result.get("result", {}).get("final_answer", ""),
                metadata={
                    "subagent_id": result.get("subagent_id"),
                    "status": result.get("status"),
                    "trace": result.get("trace", []),
                },
            )
        except Exception as exc:
            return CoreToolResult(
                tool_name="task.delegate",
                ok=False,
                error=f"subagent_error:{type(exc).__name__}:{exc}",
                metadata={"error_code": "subagent_error"},
            )

    def _handle_web_search(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        query = SearchQuery(
            query=str(arguments.get("query") or "").strip(),
            provider=str(arguments.get("provider") or "auto"),
            engine=str(arguments.get("engine") or ""),
            top_k=int(arguments.get("top_k") or 5),
            freshness=str(arguments.get("freshness") or "") or None,
            site=str(arguments.get("site") or "") or None,
            task_id=str(arguments.get("task_id") or "") or None,
        )
        result = run_web_search(query, router=self.web_router, cache=self.web_cache, allow_live=self.allow_live_web)
        return CoreToolResult(
            tool_name="web.search",
            ok=bool(result.ok),
            output=result.to_dict(),
            error=result.error,
            metadata={
                "result_code": "ok" if result.ok else "web_search_failed",
                "provider": query.provider,
                "query": query.query,
                "result_count": len(result.results),
            },
        )

    def _handle_web_fetch(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        request = FetchRequest(
            url=str(arguments.get("url") or "").strip(),
            extract_mode=str(arguments.get("extract_mode") or "markdown"),
            max_chars=int(arguments.get("max_chars") or 12000),
            provenance=dict(arguments.get("provenance") or {}),
        )
        result = run_web_fetch(request, cache=self.web_cache, transport=self.web_transport)
        return CoreToolResult(
            tool_name="web.fetch",
            ok=bool(result.ok),
            output=result.to_dict(),
            error=result.error,
            metadata={
                "result_code": "ok" if result.ok else "web_fetch_failed",
                "url": request.url,
                "document_count": len(result.documents),
                "blocked": any(bool(run.get("blocked")) for run in result.runs if isinstance(run, dict)),
            },
        )

    def _handle_web_browse(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        url = str(arguments.get("url") or "").strip()
        action = str(arguments.get("action") or "snapshot").strip()
        if not url:
            return CoreToolResult(
                tool_name="web.browse", ok=False,
                error="url is required",
                metadata={"error_code": "missing_url"},
            )
        result = run_web_browse(url, action=action)
        return CoreToolResult(
            tool_name="web.browse",
            ok=bool(result.get("ok")),
            output=result,
            error=result.get("error"),
            metadata={
                "result_code": "ok" if result.get("ok") else "web_browse_failed",
                "url": url,
                "action": action,
                "title": result.get("title", ""),
            },
        )

    def _handle_checkpoint_create(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        task_id = str(arguments.get("task_id") or "").strip()
        label = str(arguments.get("label") or "").strip()
        file_paths = list(arguments.get("file_paths") or [])
        if not task_id or not label:
            return CoreToolResult(
                tool_name="checkpoint.create", ok=False,
                error="task_id and label are required",
                metadata={"error_code": "missing_fields"},
            )
        if self.checkpoint_manager is None:
            return CoreToolResult(
                tool_name="checkpoint.create", ok=False,
                error="checkpoint_manager_not_available",
                metadata={"error_code": "checkpoint_unavailable"},
            )
        result = self.checkpoint_manager.create_checkpoint(
            task_id, label, file_paths=file_paths,
        )
        return CoreToolResult(
            tool_name="checkpoint.create",
            ok=bool(result.get("ok")),
            output=result.get("data"),
            error=result.get("error", {}).get("message"),
            metadata={"result_code": "ok" if result.get("ok") else "checkpoint_create_failed"},
        )

    def _handle_checkpoint_rollback(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        task_id = str(arguments.get("task_id") or "").strip()
        checkpoint_id = str(arguments.get("checkpoint_id") or "").strip()
        if not task_id or not checkpoint_id:
            return CoreToolResult(
                tool_name="checkpoint.rollback", ok=False,
                error="task_id and checkpoint_id are required",
                metadata={"error_code": "missing_fields"},
            )
        if self.checkpoint_manager is None:
            return CoreToolResult(
                tool_name="checkpoint.rollback", ok=False,
                error="checkpoint_manager_not_available",
                metadata={"error_code": "checkpoint_unavailable"},
            )
        result = self.checkpoint_manager.rollback(task_id, checkpoint_id)
        return CoreToolResult(
            tool_name="checkpoint.rollback",
            ok=bool(result.get("ok")),
            output=result.get("data"),
            error=result.get("error", {}).get("message"),
            metadata={"result_code": "ok" if result.get("ok") else "rollback_failed"},
        )

    def _handle_checkpoint_list(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        task_id = str(arguments.get("task_id") or "").strip()
        if not task_id:
            return CoreToolResult(
                tool_name="checkpoint.list", ok=False,
                error="task_id is required",
                metadata={"error_code": "missing_fields"},
            )
        if self.checkpoint_manager is None:
            return CoreToolResult(
                tool_name="checkpoint.list", ok=False,
                error="checkpoint_manager_not_available",
                metadata={"error_code": "checkpoint_unavailable"},
            )
        result = self.checkpoint_manager.list_checkpoints(task_id)
        return CoreToolResult(
            tool_name="checkpoint.list",
            ok=bool(result.get("ok")),
            output=result.get("data"),
            error=result.get("error", {}).get("message"),
            metadata={"result_code": "ok" if result.get("ok") else "list_failed"},
        )

    def _handle_memory_search(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        query = str(arguments.get("query") or "").strip()
        if not query:
            return CoreToolResult(
                tool_name="memory.search", ok=False,
                error="empty_query", metadata={"error_code": "empty_query"},
            )
        memory_type = str(arguments.get("memory_type") or "").strip() or None
        limit = int(arguments.get("limit") or 10)
        records = self.memory_store.search(query, memory_type=memory_type, limit=limit)
        return CoreToolResult(
            tool_name="memory.search",
            ok=True,
            output={
                "results": [
                    {
                        "memory_type": r.get("memory_type", ""),
                        "key": r.get("key", ""),
                        "value": r.get("value_redacted", r.get("value", "")),
                        "memory_id": r.get("memory_id", ""),
                    }
                    for r in records
                ]
            },
            metadata={"result_code": "ok", "count": len(records)},
        )

    def _handle_memory_write(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        memory_type = str(arguments.get("memory_type") or "").strip()
        key = str(arguments.get("key") or "").strip()
        value = str(arguments.get("value") or "")
        description = str(arguments.get("description") or "").strip()
        if not memory_type or not key or not value:
            return CoreToolResult(
                tool_name="memory.write", ok=False,
                error="missing_fields: memory_type, key, value are required",
                metadata={"error_code": "missing_fields"},
            )
        allowed = {"feedback", "reference", "user_profile", "project_fact"}
        if memory_type not in allowed:
            return CoreToolResult(
                tool_name="memory.write", ok=False,
                error=f"invalid_memory_type:{memory_type} (allowed: {', '.join(sorted(allowed))})",
                metadata={"error_code": "invalid_memory_type"},
            )
        # Write to both SQLite and markdown (hybrid approach)
        record, md_path = self.memory_store.write_to_both(
            memory_type, key, value, description=description,
        )
        return CoreToolResult(
            tool_name="memory.write",
            ok=True,
            output={
                "memory_id": record["memory_id"],
                "memory_type": record["memory_type"],
                "key": record["key"],
                "markdown_file": str(md_path),
            },
            metadata={"result_code": "ok"},
        )

    def _handle_memory_remember(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        key = str(arguments.get("key") or "").strip()
        value = str(arguments.get("value") or "")
        if not key or not value:
            return CoreToolResult(
                tool_name="memory.remember", ok=False,
                error="missing_fields: key and value are required",
                metadata={"error_code": "missing_fields"},
            )
        record = self.memory_store.remember("user_profile", key, value)
        return CoreToolResult(
            tool_name="memory.remember",
            ok=True,
            output={"memory_id": record["memory_id"], "key": record["key"]},
            metadata={"result_code": "ok"},
        )

    def _handle_task_create(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        goal = str(arguments.get("goal") or "").strip()
        steps_raw = list(arguments.get("steps") or [])
        if not goal or not steps_raw:
            return CoreToolResult(
                tool_name="task.create", ok=False,
                error="missing_fields: goal and steps are required",
                metadata={"error_code": "missing_fields"},
            )
        session_id = str(context.session_id or "")
        if not session_id:
            return CoreToolResult(
                tool_name="task.create", ok=False,
                error="no_session: task plans require an active session",
                metadata={"error_code": "no_session"},
            )
        from ..core.tasks import TaskPlan
        plan = TaskPlan.new(session_id=session_id, goal=goal, steps=steps_raw)
        if self.thread_store is not None:
            import json as _json
            self.thread_store.save_task_plan(
                plan_id=plan.plan_id,
                session_id=plan.session_id,
                goal=plan.goal,
                steps_json=_json.dumps([s.to_dict() for s in plan.steps], ensure_ascii=False),
                status=plan.status,
            )
        # Also persist to cross-session PersistentTaskManager
        blocked_by: list[str] = []
        for s in plan.steps:
            for dep in s.depends_on:
                if dep.startswith("plan_") and dep not in blocked_by:
                    blocked_by.append(dep)
        self.persistent_task_manager.create(
            subject=plan.goal,
            description="\n".join(s.description for s in plan.steps),
            session_id=plan.session_id,
            task_id=plan.plan_id,
            blocked_by=blocked_by,
            metadata={"steps": [s.to_dict() for s in plan.steps]},
        )
        return CoreToolResult(
            tool_name="task.create",
            ok=True,
            output=plan.to_dict(),
            metadata={"result_code": "ok"},
        )

    def _handle_task_update(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        plan_id = str(arguments.get("plan_id") or "").strip()
        if not plan_id:
            return CoreToolResult(
                tool_name="task.update", ok=False,
                error="missing_fields: plan_id is required",
                metadata={"error_code": "missing_fields"},
            )
        if self.thread_store is None:
            return CoreToolResult(
                tool_name="task.update", ok=False,
                error="no_thread_store: task plans require persistence",
                metadata={"error_code": "no_thread_store"},
            )
        import json as _json
        record = self.thread_store.load_task_plan(plan_id)
        if record is None:
            return CoreToolResult(
                tool_name="task.update", ok=False,
                error=f"plan_not_found:{plan_id}",
                metadata={"error_code": "plan_not_found"},
            )
        from ..core.tasks import TaskPlan, TaskPlanStep
        plan = TaskPlan.from_dict({
            "plan_id": record.plan_id,
            "session_id": record.session_id,
            "goal": record.goal,
            "steps": _json.loads(record.steps_json),
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": _json.loads(record.metadata_json),
        })
        step_updates = list(arguments.get("step_updates") or [])
        new_steps_raw = list(arguments.get("new_steps") or [])
        step_map = {s.step_id: s for s in plan.steps}
        for upd in step_updates:
            sid = str(upd.get("step_id") or "")
            if sid in step_map:
                new_status = str(upd.get("status") or "")
                if new_status in {"pending", "in_progress", "completed", "failed"}:
                    step_map[sid].status = new_status
                result_val = upd.get("result")
                if result_val is not None:
                    step_map[sid].result = str(result_val)
        next_num = len(plan.steps) + 1
        for ns in new_steps_raw:
            plan.steps.append(TaskPlanStep(
                step_id=f"step_{next_num}",
                description=str(ns.get("description") or ""),
                depends_on=list(ns.get("depends_on") or []),
                estimated_tool=ns.get("estimated_tool"),
            ))
            next_num += 1
        from datetime import datetime, timezone
        plan.updated_at = datetime.now(timezone.utc).isoformat()
        self.thread_store.save_task_plan(
            plan_id=plan.plan_id,
            session_id=plan.session_id,
            goal=plan.goal,
            steps_json=_json.dumps([s.to_dict() for s in plan.steps], ensure_ascii=False),
            status=plan.status,
        )
        # Sync status to PersistentTaskManager (triggers blockedBy auto-clear on completion)
        self.persistent_task_manager.update(
            plan.plan_id,
            status=plan.status,
        )
        return CoreToolResult(
            tool_name="task.update",
            ok=True,
            output=plan.to_dict(),
            metadata={"result_code": "ok"},
        )

    def _handle_task_list(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        all_sessions = bool(arguments.get("all_sessions", False))
        session_id = str(context.session_id or "")
        if not session_id or self.thread_store is None:
            return CoreToolResult(
                tool_name="task.list",
                ok=True,
                output={"plans": []},
                metadata={"result_code": "ok"},
            )
        import json as _json
        records = self.thread_store.list_task_plans(session_id=session_id)
        plans: list[dict] = []
        for r in records:
            try:
                steps = _json.loads(r.steps_json)
            except Exception:
                steps = []
            plans.append({
                "plan_id": r.plan_id,
                "goal": r.goal,
                "status": r.status,
                "steps_count": len(steps),
                "created_at": r.created_at,
            })
        # Merge in cross-session tasks from PersistentTaskManager
        if all_sessions:
            ptm_tasks = self.persistent_task_manager.list_all()
            seen_ids = {p["plan_id"] for p in plans}
            for t in ptm_tasks:
                tid = t.get("id", "")
                if tid not in seen_ids:
                    metadata = t.get("metadata", {})
                    steps = metadata.get("steps", []) if isinstance(metadata, dict) else []
                    plans.append({
                        "plan_id": tid,
                        "goal": t.get("subject", ""),
                        "status": t.get("status", "active"),
                        "steps_count": len(steps),
                        "created_at": str(t.get("created_at", "")),
                    })
        return CoreToolResult(
            tool_name="task.list",
            ok=True,
            output={"plans": plans},
            metadata={"result_code": "ok"},
        )

    def _handle_task_get(self, arguments: dict[str, Any], context: CoreToolContext) -> CoreToolResult:
        _ = context
        plan_id = str(arguments.get("plan_id") or "").strip()
        if not plan_id:
            return CoreToolResult(
                tool_name="task.get", ok=False,
                error="missing_fields: plan_id is required",
                metadata={"error_code": "missing_fields"},
            )
        # Try PersistentTaskManager first (cross-session file), then fall back to thread_store
        task = self.persistent_task_manager.get(plan_id)
        if task is not None:
            metadata = task.get("metadata", {})
            steps = metadata.get("steps", []) if isinstance(metadata, dict) else []
            return CoreToolResult(
                tool_name="task.get",
                ok=True,
                output={
                    "plan_id": task["id"],
                    "goal": task.get("subject", ""),
                    "status": task.get("status", "active"),
                    "owner": task.get("owner", ""),
                    "worktree": task.get("worktree", ""),
                    "blocked_by": task.get("blockedBy", []),
                    "steps": steps,
                    "created_at": str(task.get("created_at", "")),
                    "updated_at": str(task.get("updated_at", "")),
                },
                metadata={"result_code": "ok"},
            )
        if self.thread_store is not None:
            import json as _json
            record = self.thread_store.load_task_plan(plan_id)
            if record is not None:
                try:
                    steps = _json.loads(record.get("steps_json", "[]"))
                except Exception:
                    steps = []
                return CoreToolResult(
                    tool_name="task.get",
                    ok=True,
                    output={
                        "plan_id": record.get("plan_id", ""),
                        "goal": record.get("goal", ""),
                        "status": record.get("status", "active"),
                        "steps": steps,
                        "created_at": str(record.get("created_at", "")),
                        "updated_at": str(record.get("updated_at", "")),
                    },
                    metadata={"result_code": "ok"},
                )
        return CoreToolResult(
            tool_name="task.get", ok=False,
            error=f"plan_not_found:{plan_id}",
            metadata={"error_code": "plan_not_found"},
        )

    @staticmethod
    def _wrap_core_result(tool_name: str, raw: dict[str, Any]) -> CoreToolResult:
        if raw.get("ok"):
            return CoreToolResult(
                tool_name=tool_name,
                ok=True,
                output=raw.get("data"),
                metadata={"result_code": "ok"},
            )
        err = raw.get("error") or {}
        if isinstance(err, str):
            return CoreToolResult(
                tool_name=tool_name,
                ok=False,
                error=err,
                metadata={"error_code": "tool_error"},
            )
        return CoreToolResult(
            tool_name=tool_name,
            ok=False,
            error=str(err.get("message") or err.get("code") or "tool_error"),
            metadata={"error_code": err.get("code"), "error_detail": err},
        )


class ToolCallExecutor:
    """Execute agent ToolCall through ToolRuntime safety/permission/approval chain."""

    def __init__(
        self,
        *,
        registry_adapter: ToolRegistryAdapter,
        permission_mode: str = "workspace_write",
        auto_approve: bool = False,
        permission_policy: PermissionPolicy | None = None,
        approval_store: ApprovalStore | None = None,
        hook_registry: HookRegistry | None = None,
        tool_timeout_s: int = 30,
    ) -> None:
        self.registry_adapter = registry_adapter
        self.permission_mode = permission_mode
        self.auto_approve = auto_approve
        self.permission_policy = permission_policy or PermissionPolicy.from_permission_mode(permission_mode)
        self.approval_store = approval_store or get_approval_store()
        self.hook_registry = hook_registry or registry_adapter.hook_registry
        self.tool_timeout_s = tool_timeout_s

    def execute(self, call: ToolCall, context: dict[str, Any] | None = None) -> ToolResult:
        ctx = context or {}
        tool_context = CoreToolContext(
            workspace_root=str(ctx.get("cwd") or self.registry_adapter.project_root),
            permission_mode=str(ctx.get("permission_mode") or self.permission_mode),
            mode=str(ctx.get("mode") or "agent"),
            session_id=str(ctx.get("session_id") or ""),
            request_id=str(ctx.get("turn_id") or ""),
            metadata=dict(ctx),
        )
        spec = self.registry_adapter.core_registry.get(call.name)
        if spec is None:
            return ToolResult(call_id=call.id, name=call.name, ok=False, error=f"tool_not_found:{call.name}", metadata={"agent_events": []})

        agent_events: list[dict[str, Any]] = []
        args_preview = redact_args_preview(call.arguments)

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            agent_events.append(
                AgentEvent.new(
                    turn_id=str(ctx.get("turn_id") or ""),
                    event_type=event_type,
                    payload=payload,
                ).to_dict()
            )

        if call.name == "web.fetch":
            initial_reason = block_reason_for_url(str(call.arguments.get("url") or ""))
            if initial_reason is not None:
                emit("web_fetch_blocked", {"tool_name": call.name, "url": call.arguments.get("url"), "block_reason": initial_reason})
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"ssrf_blocked:{initial_reason}",
                    metadata={"blocked": True, "block_reason": initial_reason, "agent_events": agent_events, "args_preview": args_preview},
                )

        policy_decision = self.permission_policy.evaluate(call.name, call.arguments)
        emit("permission_policy_evaluated", policy_decision.to_dict())

        if call.name == "web.fetch":
            domain_decision = self.permission_policy.evaluate_domain(
                str(call.arguments.get("url") or ""),
                tool_name=call.name,
                arguments=call.arguments,
            )
            emit("domain_policy_evaluated", domain_decision.to_dict())
            if domain_decision.action == "deny":
                emit("domain_policy_denied", domain_decision.to_dict())
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"domain_policy_denied:{domain_decision.reason}",
                    metadata={"agent_events": agent_events, "args_preview": args_preview, "domain": domain_decision.domain},
                )
            if domain_decision.action == "require_approval":
                policy_decision = domain_decision
                emit("domain_approval_required", domain_decision.to_dict())

        approved_request = self.approval_store.find_matching_approved(
            tool_name=call.name,
            arguments_preview=args_preview,
            session_id=str(ctx.get("session_id") or "") or None,
        )
        denied_request = self.approval_store.find_matching_denied(
            tool_name=call.name,
            arguments_preview=args_preview,
            session_id=str(ctx.get("session_id") or "") or None,
        )

        if policy_decision.action == "deny":
            emit("tool_policy_denied", policy_decision.to_dict())
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"tool_policy_denied:{policy_decision.reason}",
                metadata={"agent_events": agent_events, "args_preview": args_preview},
            )

        if denied_request is not None:
            emit("approval_denied", {"approval_id": denied_request.approval_id, "tool_name": call.name, "retry": True})
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"approval_denied:{denied_request.approval_id}",
                metadata={"agent_events": agent_events, "args_preview": args_preview},
            )

        if policy_decision.action == "require_approval" and not (self.auto_approve or approved_request is not None):
            pending = self.approval_store.find_matching_pending(
                tool_name=call.name,
                arguments_preview=args_preview,
                session_id=str(ctx.get("session_id") or "") or None,
            )
            request = pending or self.approval_store.create_request(
                tool_name=call.name,
                arguments_preview=args_preview,
                risk_level=policy_decision.risk_level,
                reason=policy_decision.reason,
                session_id=str(ctx.get("session_id") or "") or None,
                turn_id=str(ctx.get("turn_id") or "") or None,
            )
            emit(
                "approval_created",
                {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason},
            )
            emit(
                "approval_required",
                {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason},
            )
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"approval_required:{request.approval_id}",
                metadata={
                    "approval_required": True,
                    "approval_id": request.approval_id,
                    "agent_events": agent_events,
                    "args_preview": args_preview,
                },
            )

        emit("tool_policy_allowed", policy_decision.to_dict())
        if approved_request is not None:
            emit("approval_approved", {"approval_id": approved_request.approval_id, "tool_name": call.name, "retry": True})

        pre_input = HookInput(
            hook_type="pre_tool_use",
            tool_name=call.name,
            arguments_preview=args_preview,
            result_preview=None,
            context={"risk_level": spec.risk_level, "permission_mode": tool_context.permission_mode},
        )
        pre_results = self.hook_registry.run_pre_tool_use(pre_input)
        for hook, hook_result in pre_results:
            emit("pretool_hook_started", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action})
            emit("pretool_hook_completed", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action, "message": hook_result.message})
            if hook_result.action in {"warn", "escalate"}:
                emit("security_warning_emitted", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
            if hook_result.action == "deny":
                emit("pretool_hook_denied", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"pretool_hook_denied:{hook_result.message}",
                    metadata={"agent_events": agent_events, "args_preview": args_preview},
                )
            if hook_result.action == "require_approval" and not self.auto_approve:
                request = self.approval_store.create_request(
                    tool_name=call.name,
                    arguments_preview=args_preview,
                    risk_level=str(hook_result.risk_level or spec.risk_level),
                    reason=hook_result.message,
                    session_id=str(ctx.get("session_id") or "") or None,
                    turn_id=str(ctx.get("turn_id") or "") or None,
                )
                emit("approval_created", {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason})
                emit("approval_required", {"approval_id": request.approval_id, "tool_name": request.tool_name, "risk_level": request.risk_level, "reason": request.reason})
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"approval_required:{request.approval_id}",
                    metadata={"approval_required": True, "approval_id": request.approval_id, "agent_events": agent_events, "args_preview": args_preview},
                )

        core_call = CoreToolCall(tool_name=call.name, arguments=dict(call.arguments), reason=call.reason)
        t0 = time.perf_counter()
        if spec.handler is None:
            core_result = CoreToolResult(tool_name=call.name, ok=False, error=f"no_handler:{call.name}")
        else:
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = pool.submit(spec.handler, core_call.arguments, tool_context)
                core_result = cast(CoreToolResult, future.result(timeout=self.tool_timeout_s))
            except concurrent.futures.TimeoutError:
                core_result = CoreToolResult(
                    tool_name=call.name, ok=False,
                    error=f"tool_timeout: {call.name} exceeded {self.tool_timeout_s}s",
                    metadata={},
                )
            except Exception as exc:
                core_result = CoreToolResult(tool_name=call.name, ok=False, error=f"handler_error:{type(exc).__name__}:{exc}", metadata={})
            finally:
                pool.shutdown(wait=False)
        duration_s = round(time.perf_counter() - t0, 3)
        if not core_result.metadata:
            core_result.metadata = {}
        core_result.metadata["duration_s"] = duration_s

        if call.name == "web.fetch" and isinstance(core_result.output, dict):
            runs = list(core_result.output.get("runs") or [])
            blocked_run = next((run for run in runs if isinstance(run, dict) and run.get("blocked")), None)
            if blocked_run is not None:
                emit("web_fetch_blocked", {"tool_name": call.name, "url": call.arguments.get("url"), "block_reason": blocked_run.get("block_reason"), "final_url": blocked_run.get("final_url")})
            else:
                emit("web_fetch_completed" if core_result.ok else "web_fetch_failed", {"tool_name": call.name, "url": call.arguments.get("url")})
        elif call.name == "web.search":
            emit("web_search_completed" if core_result.ok else "web_search_failed", {"tool_name": call.name, "query": call.arguments.get("query")})

        post_preview = core_result.output if isinstance(core_result.output, dict) else {"output": core_result.output}
        post_input = HookInput(
            hook_type="post_tool_use",
            tool_name=call.name,
            arguments_preview=args_preview,
            result_preview=post_preview,
            context={
                "risk_level": spec.risk_level,
                "permission_mode": tool_context.permission_mode,
                "contains_secret_text": bool(core_result.output and "REDACTED" in str(core_result.output)),
            },
        )
        post_results = self.hook_registry.run_post_tool_use(post_input)
        for hook, hook_result in post_results:
            emit("posttool_hook_started", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action})
            emit("posttool_hook_completed", {"hook_name": hook.name, "tool_name": call.name, "action": hook_result.action, "message": hook_result.message})
            if hook_result.action in {"warn", "escalate"}:
                emit("posttool_hook_warning", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
                emit("security_warning_emitted", {"hook_name": hook.name, "tool_name": call.name, "message": hook_result.message})
            if hook_result.action == "redact" and isinstance(core_result.output, str):
                core_result.output = str(redact_args_preview({"output": core_result.output}).get("output") or "")

        metadata = dict(core_result.metadata or {})
        if core_result.output is not None and isinstance(core_result.output, dict):
            for key in ("changed_files", "commands_run", "tests_run"):
                if key in core_result.output and key not in metadata:
                    metadata[key] = core_result.output.get(key)
        metadata["agent_events"] = agent_events
        metadata["args_preview"] = args_preview
        tool_duration_s = metadata.pop("duration_s", None)

        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=core_result.ok,
            content=core_result.output if core_result.output is not None else "",
            error=core_result.error,
            metadata=metadata,
            duration_s=tool_duration_s,
        )
