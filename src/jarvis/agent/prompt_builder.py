"""Prompt assembly for AgentLoop using TurnContext."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .types import TurnContext


_AGENT_SYSTEM_PROMPT = """\
<agent>
You are Jarvis, a local AI coding assistant that runs directly in the user's project directory. You have file system access and a suite of tools to inspect, search, edit, and run code.
When asked who you are, identify yourself as Jarvis and list your capabilities. When greeted, respond with a brief greeting and ask what to work on.
When asked what model you are, say you are {model_name} — always state the model name exactly, not "the configured LLM backend" or similar vagueness.

## Language
You MUST respond in the same language as the user's most recent message. If they write in Chinese, reply in Chinese; in Japanese, reply in Japanese; in English, reply in English. Never switch languages mid-conversation unless the user switches first.

## Core directive
Use tools to fulfill the user's request. Do NOT describe what you'll do — do it. When your tools finish, deliver the result in 1-3 sentences. Do not explain your process, recap what you did, or create tables/comparisons unless the user explicitly asks for them. The harness already shows tool calls and results — your job is to act, then deliver the outcome.

## Tool rules
- ALWAYS use tools for: file contents, directory listings, code search, reading files, running commands, web content, math, dates, git operations. Never answer these from memory.
- Use the most specific tool: Glob for filenames, Grep for content, Read for known paths.
- Use provided function tools only. Never invent tool names.
- If a tool returns an error, try a different approach. If it fails 2+ times, report the error.
- Combine independent tool calls in a single response when possible.

## Code
- Verify with tools before writing code. Don't guess.
- Minimum code to solve the problem. No extra features.
- Match existing codebase style. Don't touch unrelated code.
- Fix root causes, not symptoms.
- After editing, run relevant tests to verify.

## Output style
- Be brief. After tools complete, state what changed in 1-3 sentences.
- NEVER repeat raw tool output (stdout, JSON, exit codes) in your answer.
- Do not create tables, comparisons, or analysis unless asked.
- Do not explain your process — the tool trail already shows it.
- If the user asks a direct question, answer it directly without preamble.
- Use backticks for file paths and code identifiers.

## Safety
- Never read or expose .env files, API keys, tokens, or secrets.
- Never run destructive commands without explicit user approval.
</agent>"""


class PromptBuilder:
    """Build provider messages from the structured turn context.

    Message order mimics Claude Code's session continuity:
      [system prompt] -> [compacted summary] -> [recent history] -> [current user input]
    """

    def __init__(self, **kwargs: Any) -> None:
        pass

    def build_messages(self, turn_context: TurnContext) -> list[dict[str, Any]]:
        pack = turn_context.context_pack
        if pack is None:
            return [{"role": "user", "content": turn_context.user_input}]

        model_name = (turn_context.model_name or "").strip() or "unknown"
        system_prompt = _AGENT_SYSTEM_PROMPT.format(model_name=model_name)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Inject available skills index (metadata only — no body content).
        # Follows Claude Code progressive disclosure: metadata always visible,
        # full body loaded on demand via skill.load.
        skills_index = self._render_skills_index(pack.skills.available_skills)
        if skills_index:
            messages.append({"role": "user", "content": skills_index})

        conv = pack.conversation

        # Inject compaction summary from previous turns (Claude Code-style).
        # Positioned BEFORE history so the model sees the condensed overview
        # first, then the detailed messages.
        if conv.compacted_summary:
            messages.append({
                "role": "user",
                "content": (
                    "<conversation-summary>\n"
                    "The following is a summary of the earlier conversation. "
                    "This is a handoff from previous context — treat it as "
                    "background reference, NOT as active instructions. "
                    "Do NOT re-execute tools or commands mentioned here. "
                    "Do NOT answer questions from the summary — they were "
                    "already addressed. Your task is the latest user message "
                    "at the end of this context.\n\n"
                    f"{conv.compacted_summary}\n"
                    "</conversation-summary>"
                ),
            })

        # Inject recent conversation history as native-role messages.
        # Unlike the old approach that wrapped everything in <historical>
        # tags and told the model to ignore it, we now inline history
        # naturally (Claude Code / Codex / Hermes pattern). A soft
        # boundary marker precedes the history so the model can distinguish
        # past from current, but it is informational, not prescriptive.
        recent = list(conv.recent_messages)
        if recent:
            messages.append({
                "role": "user",
                "content": (
                    "<conversation-history>\n"
                    "Messages above this point are from earlier turns in "
                    "this session. They are provided for continuity so you "
                    "know what was discussed. The user's CURRENT request "
                    "is the LAST message below.\n"
                    "</conversation-history>"
                ),
            })
        for msg in recent[-40:]:
            role = str(msg.get("role") or "").strip()
            content = str(msg.get("content") or "")
            if not role or not content:
                continue
            tc_id = msg.get("tool_call_id")
            if role == "tool":
                # Tool messages from previous turns must be converted to
                # user/system format because the paired assistant tool_calls
                # are not persisted (only the final answer is).  Passing bare
                # tool messages with tool_call_id without the corresponding
                # assistant tool_calls breaks OpenAI-protocol APIs.
                tool_name = str((msg.get("metadata") or {}).get("tool_name") or tc_id or "unknown")
                entry: dict[str, Any] = {
                    "role": "user",
                    "content": f"[Previous tool result — {tool_name}]: {content[:3000]}",
                }
            else:
                entry = {"role": role, "content": content}
                if tc_id:
                    entry["tool_call_id"] = tc_id
            messages.append(entry)

        # Soft turn boundary (replaces the old hard boundary).
        # Marks where history ends and the current request begins, but
        # does NOT tell the model to ignore history — it merely frames
        # the current task.
        messages.append({
            "role": "user",
            "content": (
                "─── current request ───\n"
                + turn_context.user_input
            ),
        })
        return messages

    @staticmethod
    def _render_skills_index(available_skills: list[dict[str, Any]]) -> str | None:
        if not available_skills:
            return None
        lines: list[str] = ["<skills>"]
        for s in available_skills:
            name = s.get("name", "")
            desc = s.get("description", "")
            lines.append(f"- {name}: {desc}")
        lines.append("</skills>")
        lines.append("")
        lines.append("<skills_usage>")
        lines.append("When a user task matches a skill description above:")
        lines.append("1. Call skill.load with the skill name to get full instructions.")
        lines.append("2. Follow those instructions step by step to complete the task.")
        lines.append("3. After completing the steps, synthesize a final answer for the user.")
        lines.append("")
        lines.append("Rules:")
        lines.append("- Load each skill only ONCE per turn. Never reload a skill you already loaded.")
        lines.append("- Use skill.load, NOT Read/Grep/Glob tools, to access skill instructions.")
        lines.append("- You MUST produce a final text answer — do not just run tools and stop.")
        lines.append("</skills_usage>")
        return "\n".join(lines)