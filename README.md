<div align="center">

# J.A.R.V.I.S

**Just A Rather Very Intelligent System**

[![Version](https://img.shields.io/badge/version-0.2-blue)](CHANGELOG.md)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-blue)](https://www.typescriptlang.org/)
[![Node](https://img.shields.io/badge/node-20+-green)](https://nodejs.org/)
[![License](https://img.shields.io/badge/license-MIT-red)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#)

A local-first AI coding agent that runs in your terminal.  
File system access · multi-provider LLM · ReAct agent loop · skill ecosystem.

[Quick Start](#quick-start) ·
[Features](#features) ·
[Configuration](#configuration) ·
[Architecture](#architecture) ·
[Development](#development)

</div>

---

## Why Jarvis?

Jarvis is a terminal-native coding agent inspired by Claude Code, OpenAI Codex, and OpenCode. It works directly in your project directory — reading, searching, editing, and running code through a unified tool interface.

**What makes it different:**
- **TypeScript monorepo** — 11 packages, pnpm workspaces, turborepo builds
- **Local-first** — runs in your terminal, in your project root
- **Multi-provider** — DeepSeek, OpenAI, Gemini, Qwen, and any OpenAI-compatible endpoint
- **5-stage compaction** — progressive context compression from budget reduction to LLM summarization
- **ReAct loop** — Reasoning → Action → Observation with retry, bridge safety checks, and context state persistence
- **Skill system** — auto-discovery, 7-dimension matching with Chinese keyword support, policy-gated execution
- **Reference Python implementation** — preserved as a reference/spec; active development is TypeScript

---

## Quick Start

### Prerequisites
- Node.js 20+
- pnpm 9+
- An LLM API key (DeepSeek, OpenAI, or any compatible provider)

### Install

```bash
git clone https://github.com/terialion/jarvis.git
cd jarvis
pnpm install
```

### Configure

Jarvis now prefers a user config file at `~/.jarvis/config.json`.

On first launch, run:

```bash
pnpm jarvis
```

Jarvis will guide you through model, base URL, API key, reasoning effort, and permission mode setup inside the TUI.

You can still use environment variables as a fallback:

```bash
JARVIS_LLM_API_KEY=sk-your-key-here
JARVIS_LLM_MODEL=deepseek-v4-pro
JARVIS_LLM_BASE_URL=https://api.llm.ustc.edu.cn
```

### Run

```bash
# One-shot mode
pnpm jarvis -p "explain this codebase"

# Development mode (tsx)
cd packages/cli && pnpm dev -- -p "your task"
```

---

## Features

### Terminal-native agent loop

Jarvis implements a ReAct (Reasoning → Action → Observation) loop with streaming output. The agent reasons about your request, selects tools, executes them, observes results, and iterates until complete.

| Capability | Description |
|-----------|-------------|
| **Streaming output** | Real-time token streaming via SSE |
| **Multi-provider** | DeepSeek, OpenAI-compatible, Qwen, with per-provider message normalization |
| **Context compaction** | 5-stage pipeline: budget → snip → micro-compact → collapse → LLM summarization |
| **Retry logic** | Jittered backoff with failure tracking, error classification, and replan policy |
| **Persistent sessions** | JSONL transcript + sidecar state (active task, skill/research observations, handoff) |
| **Skill execution** | Auto-discovery, 7-dimension matching, allowlist/denylist policy filtering |
| **Context state** | In-memory ContextStore with hydration from session sidecar |
| **Sub-agents** | Isolated agent delegation with worktree support |

### Built-in tools

Jarvis ships with built-in tools across several categories (exact count varies by configuration — see `allBuiltinTools` in `packages/tools/src/index.ts` for the current list):

**File system:** `bash`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `notebook_edit`

**Task management:** `task_create`, `task_update`, `task_list`, `task_get`, `task_output`, `task_stop`

**Agent control:** `enter_plan_mode`, `exit_plan_mode`, `enter_worktree`, `exit_worktree`

**Scheduling:** `cron_create`, `cron_delete`, `cron_list`, `schedule_wakeup`

**Interaction:** `ask_user_question`

**Extensibility:** `skill.load`, `Skill` (direct invocation), `Agent` (subagent delegation), MCP resource/tool exposure, `memory_search`, `memory_get` (registered at runtime)

### LLM providers

All providers use a unified OpenAI-compatible chat completions API. Provider-specific message normalization ensures compatibility with Qwen and DeepSeek reasoner models.

| Provider | Notes |
|----------|-------|
| **DeepSeek** | Primary; reasoner mode merges system prompt into first user message |
| **OpenAI** | Full native tool calling |
| **Qwen** | System-at-front, consecutive user message merging |
| **Custom** | Any OpenAI-compatible endpoint via `JARVIS_LLM_BASE_URL` |

---

## Configuration

### User config

Primary configuration lives in `~/.jarvis/config.json`.

Common fields:

| Field | Description | Default |
|-------|-------------|---------|
| `model` | Default model name | `deepseek-chat` |
| `api_key` | LLM API key | (required) |
| `base_url` | Custom API base URL | `https://api.deepseek.com/v1` |
| `reasoning_effort` | Reasoning intensity | `high` |
| `max_turns` | Default turn budget | `30` |
| `permission_mode` | Permission gating mode | `workspace_write` |
| `output_style` | Response style hint | `default` |
| `system_prompt` | Optional global instruction override | (unset) |

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JARVIS_LLM_API_KEY` | LLM API key | (required) |
| `JARVIS_LLM_MODEL` | Model name | `deepseek-chat` |
| `JARVIS_LLM_BASE_URL` | Custom API base URL | `https://api.deepseek.com/v1` |
| `JARVIS_LLM_TEMPERATURE` | Sampling temperature | — |
| `JARVIS_LLM_MAX_TOKENS` | Max completion tokens | — |
| `JARVIS_LLM_TIMEOUT_SECONDS` | HTTP timeout | — |
| `JARVIS_LLM_PROVIDER` | Provider hint for normalization | — |
| `JARVIS_MODE` | Runtime mode | — |

### Provider-specific API keys

Jarvis also reads provider-native environment variables:

```bash
DEEPSEEK_API_KEY    # DeepSeek
OPENAI_API_KEY      # OpenAI / compatible endpoints
```

### Permission modes

Jarvis supports three permission modes, configured via `/permissions` in TUI or `permission_mode` in `~/.jarvis/config.json`:

| Mode | Behavior |
|------|----------|
| `workspace_write` | Read-only tools auto-approved; write/bash/network require approval |
| `accept_edits` | File edits auto-approved; bash/network still require approval |
| `bypass` | All tools auto-approved (use with caution) |

Dangerous shell commands (sudo, rm -rf /, curl-to-shell, etc.) are always blocked by `ApprovalGate` regardless of permission mode.

### `.env` fallback

Jarvis still loads `.env` from the project root automatically, but it is treated as a fallback for local and legacy setups.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  CLI (packages/cli)               │
│  argument parsing · one-shot mode · TUI launch   │
│  slash commands · .env loading                   │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│            AgentLoop (packages/agent)             │
│  ReAct cycle · context building · retry logic    │
│  5-stage compaction · message normalization      │
│  ContextStore hydration · ContextUpdater chain   │
│  run() [legacy] · runTurn() [primary]            │
└──────┬──────────────────────────────┬────────────┘
       │                              │
┌──────▼─────────┐            ┌────────▼────────────┐
│  LLMProvider   │            │   ToolRuntime        │
│  (model.ts)    │            │   (packages/tools)   │
│                │            │                      │
│  OpenAI-compat │            │  PermissionManager   │
│  SSE streaming │            │  ApprovalGate        │
│  Normalizer    │            │  ToolRegistry        │
│  RetryPolicy   │            │  Built-in tools           │
└──────┬─────────┘            └──────────┬───────────┘
       │                                 │
┌──────▼─────────────────────────────────▼───────────┐
│                  Supporting packages               │
│  skills  · store  · hooks  · mcp  · plugins        │
│  shared  · subagents  · tui                        │
└────────────────────────────────────────────────────┘
```

### Key design decisions

- **Monorepo** — 11 packages under `packages/`, managed by pnpm workspaces and turborepo
- **Protocol interfaces** — `LLMProvider` wraps any OpenAI-compatible endpoint with provider-specific normalization
- **Permission gating** — `PermissionManager` enforces per-tool approval modes (`workspace_write` / `accept_edits` / `bypass`); `ApprovalGate` blocks dangerous shell commands
- **Unified tool execution** — `ToolRuntime` is the single entry point for tool dispatch, enforcing permissions and result truncation
- **Skill isolation** — Skills declare allowed tools and risk levels; matcher uses 7 scoring dimensions
- **Persistent state** — SessionStore writes append-only JSONL transcripts + mutable sidecar JSON
- **Reference implementation** — `src/jarvis/` is preserved as a reference specification; all active development is TypeScript

---

## Project layout

```
packages/
├── agent/         # AgentLoop, LLMProvider, ContextBuilder, Compactor, Normalizer
├── cli/           # CLI entry point, argument parsing, slash commands, one-shot runner
├── hooks/         # Hook registry and lifecycle hooks
├── mcp/           # MCP (Model Context Protocol) client
├── plugins/       # Plugin discovery and loading
├── shared/        # Shared TypeScript types and utilities
├── skills/        # Skill loader, registry, matcher (7-dim), executor
├── store/         # SessionStore (JSONL + sidecar), MemoryStore
├── subagents/     # Sub-agent delegation and isolation
├── tools/         # ToolRegistry, ToolRuntime, PermissionManager, ApprovalGate, Built-in tools         
└── tui/           # Custom ink-style React renderer for terminal UI

src/jarvis/        # Python reference implementation (313 files)
docs/              # Design specs and documentation
```

---

## Development

```bash
# Install dependencies
pnpm install

# Type-check all packages
pnpm typecheck

# Run all tests (412 tests, 11 packages)
pnpm test

# Run a single package's tests
pnpm --filter @jarvis/agent test

# Build all packages
pnpm build

# Run one-shot agent
pnpm jarvis -p "your task"
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
