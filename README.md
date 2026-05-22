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
- **Python heritage** — 313-file Python reference implementation coexists with active TypeScript rewrite

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

Add your API credentials to `.env` in the project root:

```bash
JARVIS_LLM_API_KEY=sk-your-key-here
JARVIS_LLM_MODEL=deepseek-v4-pro
JARVIS_LLM_BASE_URL=https://api.llm.ustc.edu.cn    # custom endpoint (optional)
```

Or export as environment variables:
```bash
export JARVIS_LLM_API_KEY=sk-your-key-here
export JARVIS_LLM_MODEL=deepseek-v4-pro
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

### 8 built-in tools

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands with timeout control |
| `read` | Read file contents with offset/limit |
| `write` | Create or overwrite files |
| `edit` | Exact string replacement in files |
| `glob` | Fast file pattern matching |
| `grep` | Regex content search with ripgrep |
| `webSearch` | Web search with domain filtering |
| `webFetch` | Fetch and process web page content |

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

### `.env` file

Jarvis loads `.env` from the project root automatically. Copy `.env.example` and edit.

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
└──────┬──────────────────────────────┬────────────┘
       │                              │
┌──────▼─────────┐            ┌────────▼────────────┐
│  LLMProvider   │            │   ToolRegistry       │
│  (model.ts)    │            │   (packages/tools)   │
│                │            │                      │
│  OpenAI-compat │            │  8 built-in tools    │
│  SSE streaming │            │  bash/read/write/    │
│  Normalizer    │            │  edit/glob/grep/     │
│  RetryPolicy   │            │  webSearch/webFetch  │
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
- **Skill isolation** — Skills declare allowed tools and risk levels; matcher uses 7 scoring dimensions
- **Persistent state** — SessionStore writes append-only JSONL transcripts + mutable sidecar JSON
- **Python heritage** — `src/jarvis/` (313 .py files) serves as reference specification; all active development is TypeScript

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
├── tools/         # ToolRegistry, 8 built-in tools, runtime
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
