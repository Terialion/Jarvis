<div align="center">

<img src=".github/jarvis-banner.svg" alt="Jarvis" width="600">

# J.A.R.V.I.S

**Just A Rather Very Intelligent System**

[![Version](https://img.shields.io/badge/version-3.4-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-red)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#)

A local-first AI coding agent that runs in your terminal.  
File system access · 42 built-in tools · 107 skills · multi-provider LLM support.

[Quick Start](#quick-start) ·
[Features](#features) ·
[Configuration](#configuration) ·
[Skills](#skills) ·
[Architecture](#architecture)

</div>

---

## Why Jarvis?

Jarvis is a terminal-native coding agent inspired by Claude Code, OpenAI Codex, and OpenCode. It works directly in your project directory — reading, searching, editing, and running code through a unified tool interface. No web UI, no electron shell, no context switching.

**What makes it different:**
- **Local-first** — runs in your terminal, in your project root
- **Multi-provider** — DeepSeek, OpenAI, Gemini, Ollama, Qwen, and any OpenAI-compatible endpoint
- **Skill ecosystem** — 117 community skills ranging from arxiv paper search to browser automation
- **Safety by default** — writes, shell commands, and network access gate through an approval system
- **Streaming reasoning** — transparent thinking panel with Ctrl+T toggle, like Claude Code

---

## Quick Start

### Prerequisites
- Python 3.10+
- An LLM API key (DeepSeek, OpenAI, or any compatible provider)

### Install

```bash
# Clone
git clone https://github.com/terialion/jarvis.git
cd jarvis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install
pip install -r requirements.txt
```

### Configure

```bash
# Set your API key (choose one)
export JARVIS_LLM_API_KEY=sk-your-key-here
export JARVIS_LLM_PROVIDER=deepseek    # deepseek | openai | gemini | ollama | qwen | custom
```

Or create a `.env` file:

```bash
JARVIS_LLM_API_KEY=sk-your-key-here
JARVIS_LLM_PROVIDER=deepseek
JARVIS_LLM_MODEL=deepseek-v4-pro
```

### Run

```bash
python -m jarvis.cli
```

```
> Welcome to Jarvis. What would you like to work on?

> 帮我看看这个项目的结构
  [Thinking ...]
  ✓ List(src/) · depth 2
  ✓ Read(README.md)
  ...
  ┄ Thinking (42 lines) — press Ctrl+T to toggle ┄
```

---

## Features

### Terminal-native agent loop

Jarvis implements a full ReAct (Reasoning → Action → Observation) loop with streaming output. The agent reasons about your request, selects the right tools, executes them, observes the results, and iterates until the task is complete.

| Capability | Description |
|-----------|-------------|
| **Streaming output** | Real-time token streaming with tool call progress indicators |
| **Thinking panel** | Reasoning text rendered in a collapsible panel, togglable with `Ctrl+T` |
| **Context compaction** | Multi-stage auto-compaction with iterative summary accumulation |
| **Checkpoint/rollback** | Save task state and file snapshots, roll back on failure |
| **Sub-agent delegation** | Fork sub-agents for parallel or isolated work |
| **Team collaboration** | Multi-agent teams with inbox messaging and plan review |
| **Worktree isolation** | Git worktree per task for safe parallel execution |
| **Background tasks** | Fire-and-forget tasks with status polling |
| **Persistent memory** | ChromaDB-backed semantic memory with cross-session recall |

### 42 built-in tools

Every tool goes through permission evaluation, pre/post security hooks, and approval gating.

| Category | Tools |
|----------|-------|
| **File reading** | `repo_reader.read_file`, `glob`, `grep`, `search_files`, `search_symbol`, `list_tree` |
| **File editing** | `file_editor.write_file`, `replace_text`, `insert_text`, `diff` |
| **Shell** | `command_runner.run`, `test_runner.run_test` |
| **Web** | `web.search`, `web.fetch`, `web.browse` |
| **Memory** | `memory.write`, `memory.search`, `memory.remember` |
| **Task planning** | `task.create`, `task.update`, `task.list`, `task.delegate` |
| **Background** | `bg.task.run`, `bg.task.check`, `bg.task.cancel` |
| **Checkpoint** | `checkpoint.create`, `checkpoint.list`, `checkpoint.rollback` |
| **Skills** | `skill.load`, `skill.run` |
| **MCP** | `mcp.list_servers`, `mcp.call` |
| **Interaction** | `agent.ask_user` |
| **Team** | `team.spawn`, `team.message`, `team.inbox`, `team.plan_review`, `team.shutdown` |
| **Worktree** | `worktree.create`, `worktree.run`, `worktree.list`, `worktree.cleanup` |

### 9 LLM providers

Configure once, switch anytime. All providers use a unified OpenAI-compatible chat completions API.

| Provider | Default Model | Config |
|----------|--------------|--------|
| **DeepSeek** | deepseek-v4-pro | `JARVIS_LLM_API_KEY` |
| **OpenAI** | gpt-4.1-mini | `JARVIS_LLM_API_KEY` |
| **Gemini** | gemini-2.5-flash | `JARVIS_LLM_API_KEY` |
| **Qwen** | qwen3.6-reasoner | `JARVIS_LLM_API_KEY` |
| **OpenRouter** | openai/gpt-4.1-mini | `JARVIS_LLM_API_KEY` |
| **MiniMax** | MiniMax-M2 | `JARVIS_LLM_API_KEY` |
| **Ollama** | llama3.1 | `JARVIS_LLM_API_KEY` |
| **Custom** | (set via env) | Any OpenAI-compatible endpoint |

Models that lack native tool calling (e.g. Qwen reasoner) work through Jarvis's automatic tool-description injection into the system prompt — the model outputs `tool_plan` JSON that Jarvis parses and executes.

### 107 community skills

Skills are self-contained markdown packages that teach Jarvis how to perform specific tasks. The skill system auto-discovers skills from `skills/`, `~/.jarvis/skills/`, and `JARVIS_SKILL_DIRS`.

```
arxiv-reader        — Search and summarize arXiv papers
github              — gh CLI integration for issues, PRs, CI
weather             — Weather forecasts (no API key)
canvas-design       — Generate PNG/PDF visual art
file-manager        — Organize and manage files
news-summary        — Daily news briefings
code-generator      — Generate code from descriptions
browser-use         — Playwright-based browser automation
pptx-generator      — Create PowerPoint presentations
...and 107 more
```

Each skill declares its allowed tools and risk level. Jarvis infers missing risk levels from the skill body, and the matcher auto-selects the right skill based on your request.

---

## Configuration

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JARVIS_LLM_API_KEY` | LLM API key | (required) |
| `JARVIS_LLM_PROVIDER` | Provider: deepseek, openai, gemini, ollama, qwen, etc. | `openai_compatible` |
| `JARVIS_LLM_MODEL` | Model name override | provider default |
| `JARVIS_LLM_BASE_URL` | Custom API base URL | provider default |
| `JARVIS_LLM_TEMPERATURE` | Sampling temperature | `0.2` |
| `JARVIS_LLM_MAX_TOKENS` | Max completion tokens | `32768` |
| `JARVIS_LLM_TIMEOUT_SECONDS` | HTTP timeout | `300` |
| `JARVIS_LLM_COMPACTION_THRESHOLD` | Token threshold for auto-compaction | `12000` |
| `JARVIS_SKILL_DIRS` | Extra skill directories (`:`-separated) | — |
| `JARVIS_LLM_DEBUG` | Write provider debug logs to `temp/` | `false` |

### Provider-specific API keys

Jarvis also reads provider-native environment variables:

```bash
DEEPSEEK_API_KEY    # DeepSeek
OPENAI_API_KEY      # OpenAI / OpenRouter
GEMINI_API_KEY      # Gemini
MINIMAX_API_KEY     # MiniMax
OLLAMA_API_KEY      # Ollama
```

### `.env` file

Copy `.env.example` and edit:

```bash
cp .env.example .env
```

Jarvis loads `.env` from the project root automatically (disable with `JARVIS_LLM_DISABLE_DOTENV=1`).

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                    CLI (cli.py)                  │
│  prompt_toolkit input · rich streaming display   │
│  slash commands · markdown rendering             │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│              AgentLoop (agent/loop.py)           │
│  ReAct cycle · context management · retry logic  │
│  streaming chunk dispatch · tool orchestration   │
└──────┬──────────────────────────────┬────────────┘
       │                              │
┌──────▼─────────┐            ┌────────▼────────────┐
│  ModelClient   │            │  ToolRegistryAdapter│
│  (model.py)    │            │  (agent/tools.py)   │
│                │            │                     │
│  Multi-provider│            │  33 registered tools│
│  Tool injection│            │  Permission gating  │
│  Streaming SSE │            │  Security hooks     │
└──────┬─────────┘            └────────┬────────────┘
       │                              │
┌──────▼────────┐            ┌────────▼────────────┐
│  LLM Provider │            │   Core Services     │
│  (core/llm/)  │            │  RepoReader         │
│               │            │  FileEditor         │
│  OpenAI-compat│            │  CommandRunner      │
│  HTTP/SSE     │            │  MemoryStore        │
│  Sanitization │            │  SkillRegistry      │
└───────────────┘            └─────────────────────┘
```

### Key design decisions

- **Agent/tool boundary** — The agent loop never calls tools directly. All tool calls pass through `ToolCallExecutor`, which enforces permission policy, security hooks, and approval gating.
- **Model abstraction** — `ModelClient` is a protocol. `RuntimeModelClient` wraps `OpenAICompatibleProvider`. `FakeModelClient` serves deterministic scripted responses for tests.
- **Skill isolation** — Skills declare allowed tools and risk levels. The loader auto-infers missing metadata. The lifecycle manager can quarantine untrusted skills.
- **Provider-agnostic** — Tools and `tool_choice` fields are only sent when the model supports native function calling. Otherwise, tool schemas are injected into the system prompt.

---

## Skills

### Creating a skill

```
skills/my-skill/
├── SKILL.md          # Frontmatter + body (required)
└── _meta.json        # Optional sidecar metadata
```

**SKILL.md:**

```markdown
---
name: my-skill
description: What this skill does in one sentence.
allowed-tools: repo_reader.read_file, command_runner.run
risk_level: read_only
---

# My Skill

Instructions the agent follows when this skill is loaded...
```

### Skill frontmatter reference

| Field | Description |
|-------|-------------|
| `name` | Unique skill identifier |
| `description` | One-line summary (used by matcher) |
| `allowed-tools` | Comma-separated tool names or aliases: `read`, `write`, `bash`, `webfetch` |
| `risk_level` | `read_only` / `write_approval_required` / `command` / `network` / `credentialed` |
| `alwaysApply` | If `true`, skill is always loaded into the prompt |
| `read_when` | List of trigger phrases that auto-load this skill |

---

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -q

# Run a specific test suite
python -m pytest tests/cli/ -q

# Type checking
mypy src/jarvis/

# Lint
ruff check src/
```

### Project layout

```
src/jarvis/
├── agent/          # AgentLoop, model clients, prompt builder, types
├── api/            # HTTP API server, timeline
├── cli.py          # CLI entry point
├── cli_agent_output.py
├── cli_command_map.py
├── cli_ui/         # Rich streaming display, console, input
├── coding/         # Patch planning, coding workflow
├── config/         # Config manager, schema, vault
├── core/           # RepoReader, FileEditor, CommandRunner, LLM provider
│   ├── cli_response/
│   ├── coding_loop/
│   └── llm/        # LLM config, runtime provider, HTTP transport
├── skills/         # Skill loader, registry, matcher, lifecycle, executor
├── store/          # Memory store (Markdown + SQLite)
├── tools/          # BaseTool, ToolRegistry
└── web/            # Web fetch, search, browse, safety
```

---

## Acknowledgments

Jarvis draws inspiration from:

- [Claude Code](https://claude.ai/code) — terminal agent UX, thinking panel, tool display
- [OpenAI Codex](https://github.com/openai/codex) — Rust-based agent architecture, sandboxing
- [OpenCode](https://github.com/opencode-ai/opencode) — multi-provider LLM abstraction
- [DeepSeek](https://deepseek.com) — primary LLM backend

---

## License

MIT © 2024-2026 J.A.R.V.I.S Project

---

<div align="center">

⭐ **If this project helps you, consider giving it a star!**

</div>
