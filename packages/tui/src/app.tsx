import type React from 'react';
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { execSync } from 'node:child_process';
import { readFileSync, existsSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { platform, arch, totalmem, freemem, uptime } from 'node:os';
import { REPL } from './vendor/ui/REPL.js';
import type { StatusDetailLine } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { WelcomeScreen } from './vendor/ui/WelcomeScreen.js';
import { loadSettings, saveSettings, type UserSettings } from './settings-store.js';
import { AgentLoop, AgentEventBus, ConversationSummarizer, TokenTracker, formatTokensCompact, estimateTokens, validateContextWindow, getAllModels, addUserModel, removeUserModel, parseModelName, findModel, buildSystemPrompt, createMemorySearchHandler, createMemoryGetHandler, type ThreadEvent, type ModelInfo } from '@jarvis/agent';
import {
  ToolRegistry,
  allBuiltinTools,
  createToolRuntime,
  setAskUserQuestionBridge,
  createSkillLoadTool,
  createSkillTool,
  createAgentTool,
  createListMcpResourcesTool,
  createReadMcpResourceTool,
  createMcpStatusTool,
  createMcpHealthcheckTool,
  createMcpToolEntries,
  webSearchTool,
  webFetchTool,
  createWebSearchTool,
  createWebFetchHandler,
  tryCreateTavilySearch,
  tryCreateTavilyFetch,
} from '@jarvis/tools';
import type { AskQuestionDef } from '@jarvis/tools';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import { SessionStore } from '@jarvis/store';
import { MarkdownMemoryStore } from '@jarvis/store';
import { SubagentPool, toolWhitelistForType, type SubagentConfig } from '@jarvis/subagents';
import { MCPClient, connectMcpServers, type McpConnectionStatus, type McpServerConfig } from '@jarvis/mcp';
import { HookRegistry } from '@jarvis/hooks';
import { LLMProvider } from '@jarvis/agent';
import type { ModelReasoningEffort } from '@jarvis/agent';
import type { TUIOptions, TUIDebugEvent } from './types.js';
import type { ChatMessage } from '@jarvis/shared';
import {
  getJarvisConfigPath,
  JARVIS_REASONING_EFFORTS,
  loadJarvisConfig,
  normalizeJarvisReasoningEffort,
  saveJarvisConfig,
  type JarvisReasoningEffort,
} from '@jarvis/shared';
import { formatToolLine } from './vendor/ui/tool-display.js';
import { buildStatusSegments } from './status-segments.js';
import type { CodexTaskSnapshot, CodexTurnSnapshot } from './presentation/codex-timeline-state.js';
import { buildContextPanelLines, resolveContextMode, type ToolTokenEntry, type SkillTokenEntry, type MemoryTokenEntry } from './context-panel.js';

// ============================================================================
// Slash command definitions
// ============================================================================

interface SlashCommandCtx {
  store: SessionStore | null;
  sid: string | null;
  skills?: SkillRegistry | null;
  historyRef: React.MutableRefObject<ChatMessage[]>;
  messages: Message[];
  setMessages: (v: Message[] | ((prev: Message[]) => Message[])) => void;
  setIsLoading: (v: boolean) => void;
  cwd: string;
  modelRef: React.MutableRefObject<string>;
  apiKeyRef: React.MutableRefObject<string | undefined>;
  baseURLRef: React.MutableRefObject<string | undefined>;
  reasoningEffortRef: React.MutableRefObject<string>;
  systemPromptRef: React.MutableRefObject<string | undefined>;
  modifiedFilesRef: React.MutableRefObject<Set<string>>;
  getAgent: () => AgentLoop;
  invalidateAgent: () => void;
  maxTurns: number;
  outputStyleRef: React.MutableRefObject<string>;
  permissionModeRef: React.MutableRefObject<string>;
  mcpClientRef: React.MutableRefObject<MCPClient | null>;
  mcpStatusesRef: React.MutableRefObject<McpConnectionStatus[]>;
  mcpConfiguredRef: React.MutableRefObject<Array<{ id: string; plugin?: string; config: McpServerConfig }>>;
  tokenTrackerRef: React.MutableRefObject<TokenTracker | null>;
  toolsRef: React.MutableRefObject<ToolRegistry | null>;
  liveContextUsageRef: React.MutableRefObject<LiveContextUsage | null>;
}

type LiveContextUsage = {
  contextWindow: number;
  usedTokens: number;
  usagePct: number;
  messageCount: number;
  systemPromptTokens?: number;
  projectContextTokens?: number;
  skillsTokens?: number;
  memoryTokens?: number;
  conversationTokens?: number;
  toolSchemasTokens?: number;
  mcpToolsTokens?: number;
  estimatedTotalTokens?: number;
};

interface SlashCommandDef {
  name: string;
  description: string;
  usage?: string;
  handler: (args: string[], ctx: SlashCommandCtx) => string | Promise<string>;
}

function makeSysMsg(msg: string): Message {
  return {
    id: `cmd_${Date.now()}_${crypto.randomUUID().slice(0, 6)}`,
    role: 'assistant',
    content: [{ type: 'text', text: msg } as MessageContent],
    timestamp: Date.now(),
  };
}

const TASK_TOOLS = new Set(['task_create', 'task_update', 'task_list']);

function discoverPluginSkillDirs(projectRoot: string): string[] {
  const roots = [
    join(projectRoot, '.jarvis', 'plugins'),
    join(process.env['USERPROFILE'] ?? '', '.jarvis', 'plugins'),
  ].filter(Boolean);
  const result: string[] = [];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    let dirents: import('node:fs').Dirent[] = [];
    try {
      dirents = readdirSync(root, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const dirent of dirents) {
      if (!dirent.isDirectory()) continue;
      const pluginRoot = join(root, dirent.name);
      const manifestPath = join(pluginRoot, 'plugin.json');
      if (!existsSync(manifestPath)) continue;
      try {
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as { skills?: string };
        if (manifest.skills) {
          result.push(join(pluginRoot, manifest.skills));
        }
      } catch {
        // ignore invalid plugin manifest
      }
    }
  }
  return [...new Set(result)];
}

function discoverPluginMcpServers(projectRoot: string): Array<{ id: string; plugin: string; config: McpServerConfig }> {
  const roots = [
    join(projectRoot, '.jarvis', 'plugins'),
    join(process.env['USERPROFILE'] ?? '', '.jarvis', 'plugins'),
  ].filter(Boolean);
  const servers: Array<{ id: string; plugin: string; config: McpServerConfig }> = [];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    let dirents: import('node:fs').Dirent[] = [];
    try {
      dirents = readdirSync(root, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const dirent of dirents) {
      if (!dirent.isDirectory()) continue;
      const pluginRoot = join(root, dirent.name);
      const manifestPath = join(pluginRoot, 'plugin.json');
      if (!existsSync(manifestPath)) continue;
      try {
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as { mcpServers?: string; enabled?: boolean };
        if (manifest.enabled === false || !manifest.mcpServers) continue;
        const mcpPath = join(pluginRoot, manifest.mcpServers, '.mcp.json');
        if (!existsSync(mcpPath)) continue;
        const mcpConfig = JSON.parse(readFileSync(mcpPath, 'utf8')) as { servers?: Record<string, McpServerConfig> };
        for (const [id, cfg] of Object.entries(mcpConfig.servers ?? {})) {
          if (!cfg || typeof cfg.command !== 'string' || !cfg.command.trim()) continue;
          servers.push({
            id,
            plugin: dirent.name,
            config: {
              ...cfg,
              cwd: cfg.cwd ?? projectRoot,
            },
          });
        }
      } catch {
        // ignore invalid plugin config
      }
    }
  }
  return servers;
}

function discoverUserMcpServers(projectRoot: string): Array<{ id: string; plugin?: string; config: McpServerConfig }> {
  const configPath = join(process.env['USERPROFILE'] ?? '', '.jarvis', 'mcp_server_config.json');
  if (!configPath || !existsSync(configPath)) return [];
  try {
    const raw = JSON.parse(readFileSync(configPath, 'utf8')) as {
      mcpServers?: Record<string, McpServerConfig>;
      servers?: Record<string, McpServerConfig>;
    };
    const serverMap = raw.mcpServers ?? raw.servers ?? {};
    const out: Array<{ id: string; plugin?: string; config: McpServerConfig }> = [];
    for (const [id, cfg] of Object.entries(serverMap)) {
      if (!cfg || typeof cfg.command !== 'string' || !cfg.command.trim()) continue;
      out.push({
        id,
        config: {
          ...cfg,
          cwd: cfg.cwd ?? projectRoot,
        },
      });
    }
    return out;
  } catch {
    return [];
  }
}

function getGitBranch(cwd: string): string | null {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', {
      cwd,
      stdio: ['ignore', 'pipe', 'ignore'],
      encoding: 'utf8',
    }).trim() || null;
  } catch {
    return null;
  }
}

function parseToolContent(name: string, raw: string): MessageContent | null {
  if (!TASK_TOOLS.has(name)) return null;
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    const tasks = (Array.isArray(data.tasks) ? data.tasks : data.task ? [data.task] : []) as Array<{
      id: string;
      subject: string;
      status: string;
    }>;
    const counts = (data.counts ?? { pending: 0, in_progress: 0, completed: 0 }) as {
      pending: number;
      in_progress: number;
      completed: number;
    };
    return {
      type: 'task_result',
      tasks: tasks.map((t) => ({
        id: t.id,
        subject: t.subject,
        status: t.status as 'pending' | 'in_progress' | 'completed',
      })),
      counts,
    };
  } catch {
    return null;
  }
}

const REVIEW_PROMPT = `Review the uncommitted changes shown below. Focus on:
1. **Correctness** — logic errors, edge cases, off-by-one
2. **Security** — injection vectors, missing validation, leaked secrets
3. **Style** — consistency with surrounding code, naming

Be concise. Flag only real problems. Skip style nits that don't affect correctness.`;

const SECURITY_REVIEW_PROMPT = `Audit the uncommitted changes shown below for security issues. Focus exclusively on:
1. **Injection** — SQL, command, shell, path traversal, template injection
2. **Secrets** — hardcoded keys, tokens, passwords, connection strings
3. **Input validation** — missing or bypassable checks, trust of user input
4. **Auth** — broken access control, missing authorization checks, session issues
5. **Crypto** — weak algorithms, broken nonce handling, timing attacks
6. **Data exposure** — logging sensitive data, error messages leaking internals

Be concise. Flag only real security problems. Not a general code review.`;

const INIT_CLAUDE_MD_TEMPLATE = `# CLAUDE.md

This file provides instructions to AI coding assistants working in this project.

## Project Overview

<!-- Describe what this project does in 1-2 sentences -->

## Build & Test

\`\`\`bash
# Build
npm run build

# Test
npm test
\`\`\`

## Code Style

- Follow existing patterns in the codebase
- Write minimal code — no unnecessary abstractions
- Verify changes with tests before committing
`;

const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    name: 'help',
    description: 'Show available commands',
    usage: '/help',
    handler: (_args, _ctx) => {
      const lines: string[] = ['Available commands:\n'];
      for (const cmd of SLASH_COMMANDS) {
        lines.push(`  /${cmd.name} — ${cmd.description}`);
      }
      return lines.join('\n');
    },
  },
  {
    name: 'clear',
    description: 'Clear conversation history and start a new session',
    usage: '/clear',
    handler: async (_args, ctx) => {
      ctx.historyRef.current = [];
      ctx.modifiedFilesRef.current = new Set();
      ctx.setMessages([]);
      if (ctx.store) {
        const sid = `session_${crypto.randomUUID().slice(0, 12)}`;
        await ctx.store.createSession(sid, { cwd: ctx.cwd });
        ctx.sid = sid;
      }
      return 'Conversation cleared. New session started.';
    },
  },
  {
    name: 'sessions',
    description: 'List recent sessions for this directory',
    usage: '/sessions',
    handler: async (_args, ctx) => {
      // Try SessionStore first
      if (ctx.store) {
        const sessionIds = await ctx.store.listSessions();
        const lines: string[] = [];
        for (const id of sessionIds.slice(-10).reverse()) {
          try {
            const sc = await ctx.store.getSidecar(id);
            const cwd = sc.cwd ?? '?';
            const title = sc.title ?? '(no title)';
            const updated = sc.updated_at.slice(0, 19).replace('T', ' ');
            const marker = id === ctx.sid ? ' *' : '  ';
            const shortId = id.slice(-16);
            lines.push(`${marker} ${shortId}  ${updated}  ${cwd}  ${title}`);
          } catch {
            lines.push(`    ${id.slice(-16)}  (no sidecar)`);
          }
        }
        if (lines.length > 0) return `Sessions (recent first, * = current):\n\n${lines.join('\n')}`;
        return 'No sessions found.';
      }

      // Fallback: read from .jarvis/sessions/ directory
      try {
        const sessionsDir = join(process.cwd(), '.jarvis', 'sessions');
        if (existsSync(sessionsDir)) {
          const files = readdirSync(sessionsDir, { withFileTypes: true })
            .filter((f) => f.isFile() && f.name.endsWith('.json'))
            .slice(-10).reverse();
          if (files.length === 0) return 'No sessions found in .jarvis/sessions/.';
          let output = `Sessions from .jarvis/sessions/ (${files.length}):\n\n`;
          for (const f of files) {
            output += `  ${f.name.replace('.json', '')}\n`;
          }
          return output.trim();
        }
      } catch { /* ignore */ }

      return 'No session store available and no .jarvis/sessions/ directory found.';
    },
  },
  {
    name: 'diff',
    description: 'Show uncommitted git changes',
    usage: '/diff',
    handler: (_args, ctx) => {
      try {
        const stat = execSync('git diff --stat', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 });
        if (!stat.trim()) return 'No uncommitted changes.';
        const diff = execSync('git diff', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 });
        const truncated = diff.length > 16000 ? diff.slice(0, 16000) + '\n... (truncated)' : diff;
        return truncated || 'No changes.';
      } catch (e) {
        return `Error running git diff: ${e instanceof Error ? e.message : String(e)}`;
      }
    },
  },
  {
    name: 'context',
    description: 'Show current session context info',
    usage: '/context [mcp|memory|skills|tools|all]',
    handler: (args, ctx) => {
      // Ensure runtime registries (tools/skills/mcp config) are initialized
      // even when user only runs slash commands before any normal prompt.
      try {
        ctx.getAgent();
      } catch {
        // best-effort init
      }
      const msgCount = ctx.historyRef.current.length;
      const totalChars = ctx.historyRef.current.reduce((sum, m) => sum + m.content.length, 0);
      const messageTokens = Math.ceil(totalChars / 4);
      const snapshot = ctx.tokenTrackerRef.current?.snapshot();
      const live = ctx.liveContextUsageRef.current;
      const contextWindow = live?.contextWindow ?? snapshot?.contextWindow ?? 200_000;
      const shortSid = (ctx.sid ?? 'none').slice(-16);
      const modelName = parseModelName(ctx.modelRef.current).cleanName;
      const defaultSystemPrompt = buildSystemPrompt(modelName);
      const systemPromptText = ctx.systemPromptRef.current?.trim()
        ? `${defaultSystemPrompt}\n\n${ctx.systemPromptRef.current}`
        : defaultSystemPrompt;
      const systemPromptTokens = estimateTokensFromText(systemPromptText);
      const memoryEntries = estimateMemoryEntries(ctx.cwd);
      const skillEntries: SkillTokenEntry[] = (ctx.skills?.listLoadable() ?? []).map((skill) => ({
        name: skill.name,
        source: skill.source,
        tokens: estimateTokensFromText(`${skill.name}\n${skill.description}`),
      }));
      const allToolSchemas = ctx.toolsRef.current?.getDefinitions() ?? [];
      const toolEntries: ToolTokenEntry[] = allToolSchemas.map((schema) => {
        const fn = (schema as { function?: { name?: string } }).function?.name ?? 'unknown';
        const serialized = JSON.stringify(schema);
        return {
          name: fn,
          tokens: estimateTokensFromText(serialized),
          isMcp: typeof fn === 'string' && fn.toLowerCase().includes('mcp'),
        };
      });
      const memoryTokens = memoryEntries.reduce((acc, item) => acc + item.tokens, 0);
      const skillTokens = skillEntries.reduce((acc, item) => acc + item.tokens, 0);
      const toolTokens = toolEntries.reduce((acc, item) => acc + item.tokens, 0);
      const estimatedTotalTokens =
        live?.estimatedTotalTokens
        ?? (systemPromptTokens + toolTokens + memoryTokens + skillTokens + messageTokens);
      const resolvedSystemPromptTokens = live?.systemPromptTokens ?? systemPromptTokens;
      const resolvedMessageTokens = live?.conversationTokens ?? messageTokens;
      return buildContextPanelLines({
        mode: resolveContextMode(args),
        modelName,
        sessionId: shortSid,
        messageCount: msgCount,
        uiMessageCount: ctx.messages.length,
        contextWindow,
        estimatedTotalTokens,
        providerReportedTokens: live?.usedTokens ?? snapshot?.totalTokens,
        systemPromptTokens: resolvedSystemPromptTokens,
        messageTokens: resolvedMessageTokens,
        projectContextTokens: live?.projectContextTokens,
        systemToolsTokens: live?.toolSchemasTokens,
        mcpToolsTokens: live?.mcpToolsTokens,
        memoryTokens: live?.memoryTokens,
        skillsTokens: live?.skillsTokens,
        conversationTokens: live?.conversationTokens,
        memoryEntries,
        skillEntries,
        toolEntries,
        mcpConfigured: ctx.mcpConfiguredRef.current.map((entry) => ({
          id: entry.id,
          plugin: entry.plugin,
          command: entry.config.command,
        })),
        mcpStatuses: ctx.mcpStatusesRef.current.map((status) => ({
          id: status.id,
          state: status.state,
          serverName: status.serverName,
          toolCount: status.toolCount,
          resourceCount: status.resourceCount,
          error: status.error,
        })),
      }).join('\n');
    },
  },
  {
    name: 'compact',
    description: 'Summarize conversation history to free context space',
    usage: '/compact',
    handler: (_args, ctx) => {
      const history = ctx.historyRef.current;
      if (history.length < 6) return 'Not enough messages to compact.';

      const summarizer = new ConversationSummarizer({ maxSummaryChars: 2000 });
      const summary = summarizer.summarize(history);
      const compacted = summarizer.compactSummary(summary);

      const lastUserIdx = history.length - 2;
      const lastMessages = history.slice(Math.max(0, lastUserIdx));
      const compactMsg: ChatMessage = {
        role: 'system',
        content: `<conversation-summary>\n${compacted}\n</conversation-summary>`,
        messageId: `compact_${Date.now()}`,
      };
      ctx.historyRef.current = [compactMsg, ...lastMessages];

      return `Compacted ${history.length} messages into a summary (${compacted.length} chars). Kept last exchange.`;
    },
  },
  {
    name: 'model',
    description: 'Show or set the current model. /model add <slug> <name> <provider> <ctx> to register a custom model.',
    usage: '/model [model-name | add <slug> <name> <provider> <ctx> | remove <slug>]',
    handler: (args, ctx) => {
      // /model add <slug> <displayName> <provider> <contextWindow>
      if (args[0] === 'add' && args.length >= 5) {
        const [_, slug, ...rest] = args;
        // Last arg is contextWindow, second-to-last is provider, rest is displayName
        const ctxWindow = parseInt(rest[rest.length - 1]!, 10);
        const provider = rest[rest.length - 2]!;
        const displayName = rest.slice(0, -2).join(' ');
        if (!slug || !displayName || !provider || isNaN(ctxWindow)) {
          return 'Usage: /model add <slug> <display-name> <provider> <context-window>\nExample: /model add qwen3.5-thinking "Qwen 3.5 Thinking" qwen 128000';
        }
        const added = addUserModel({ slug, displayName, provider, contextWindow: ctxWindow, maxContextWindow: ctxWindow });
        return added
          ? `Model "${displayName}" (${slug}) added to user catalog. Use /model to select it.`
          : `Model "${slug}" already exists in the catalog.`;
      }
      // /model remove <slug>
      if (args[0] === 'remove' && args.length >= 2) {
        const slug = args[1]!;
        const removed = removeUserModel(slug);
        return removed
          ? `Model "${slug}" removed from user catalog.`
          : `Model "${slug}" not found in user catalog (built-in models cannot be removed).`;
      }
      if (args.length > 0) {
        ctx.modelRef.current = args[0];
        saveSettings({ model: args[0] });
        ctx.invalidateAgent();
        return `Model set to: ${args[0]} (effective on next turn)`;
      }
      return `Current model: ${parseModelName(ctx.modelRef.current).cleanName}`;
    },
  },
  {
    name: 'review',
    description: 'Code-review uncommitted changes',
    usage: '/review',
    handler: async (_args, ctx) => {
      let diff: string;
      try {
        diff = execSync('git diff', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 });
      } catch {
        return 'Error: could not run git diff.';
      }
      if (!diff.trim()) return 'No uncommitted changes to review.';

      const truncated = diff.length > 12000 ? diff.slice(0, 12000) + '\n... (truncated)' : diff;
      const prompt = `${REVIEW_PROMPT}\n\n---\n${truncated}\n---`;

      ctx.setIsLoading(true);
      try {
        const agent = ctx.getAgent();
        const result = await agent.runTurn(prompt);
        return result.finalAnswer || 'Review complete (no text response).';
      } catch (e) {
        return `Review failed: ${e instanceof Error ? e.message : String(e)}`;
      } finally {
        ctx.setIsLoading(false);
      }
    },
  },
  {
    name: 'memory',
    description: 'Show or search project memory',
    usage: '/memory [search-term]',
    handler: (_args, ctx) => {
      const searchTerm = _args.join(' ').toLowerCase();
      const sources: string[] = [];

      // Check CLAUDE.md
      const claudeMdPath = join(ctx.cwd, 'CLAUDE.md');
      if (existsSync(claudeMdPath)) {
        const content = readFileSync(claudeMdPath, 'utf-8');
        if (!searchTerm) {
          sources.push(`CLAUDE.md (${content.length} chars)`);
        } else if (content.toLowerCase().includes(searchTerm)) {
          const lines = content.split('\n').filter((l) => l.toLowerCase().includes(searchTerm));
          sources.push(`CLAUDE.md matches:\n${lines.slice(0, 10).map((l) => `  ${l.trim()}`).join('\n')}`);
        }
      }

      // Check .jarvis/memory/
      const memDir = join(ctx.cwd, '.jarvis', 'memory');
      if (existsSync(memDir)) {
        try {
          const files = readdirSync(memDir);
          for (const f of files) {
            if (!f.endsWith('.md')) continue;
            const filePath = join(memDir, f);
            const content = readFileSync(filePath, 'utf-8');
            if (!searchTerm) {
              sources.push(`.jarvis/memory/${f} (${content.length} chars)`);
            } else if (content.toLowerCase().includes(searchTerm)) {
              const lines = content.split('\n').filter((l) => l.toLowerCase().includes(searchTerm));
              sources.push(`.jarvis/memory/${f} matches:\n${lines.slice(0, 10).map((l) => `  ${l.trim()}`).join('\n')}`);
            }
          }
        } catch { /* ignore read errors */ }
      }

      if (sources.length === 0) {
        return searchTerm
          ? `No memory entries matching "${searchTerm}".`
          : 'No memory files found (CLAUDE.md or .jarvis/memory/).';
      }
      return sources.join('\n\n');
    },
  },
  {
    name: 'rewind',
    description: 'Restore files modified by agent to their git state',
    usage: '/rewind',
    handler: (_args, ctx) => {
      const files = [...ctx.modifiedFilesRef.current];
      if (files.length === 0) return 'No files have been modified by the agent in this session.';

      try {
        for (const f of files) {
          execSync(`git checkout -- "${f}"`, { cwd: ctx.cwd, encoding: 'utf-8', timeout: 5000 });
        }
        ctx.modifiedFilesRef.current = new Set();
        return `Restored ${files.length} file(s):\n${files.map((f) => `  ${f}`).join('\n')}`;
      } catch (e) {
        return `Rewind failed: ${e instanceof Error ? e.message : String(e)}`;
      }
    },
  },
  {
    name: 'doctor',
    description: 'Run environment diagnostics',
    usage: '/doctor',
    handler: (_args, ctx) => {
      const lines: string[] = ['Environment diagnostics:\n'];

      lines.push(`Platform: ${platform()} ${arch()}`);
      lines.push(`Node.js: ${process.version}`);
      lines.push(`CWD: ${ctx.cwd}`);

      try {
        const npmVer = execSync('npm --version', { encoding: 'utf-8', timeout: 5000 }).trim();
        lines.push(`npm: ${npmVer}`);
      } catch {
        lines.push('npm: (not found)');
      }

      try {
        const gitVer = execSync('git --version', { encoding: 'utf-8', timeout: 5000 }).trim();
        lines.push(`Git: ${gitVer}`);
      } catch {
        lines.push('Git: (not found)');
      }

      try {
        const totalMem = totalmem();
        const freeMem = freemem();
        const usedMem = totalMem - freeMem;
        const memPct = Math.round((usedMem / totalMem) * 100);
        const gb = (n: number) => (n / 1024 ** 3).toFixed(1);
        lines.push(`Memory: ${gb(usedMem)}GB / ${gb(totalMem)}GB (${memPct}%)`);
      } catch {
        lines.push('Memory: (unavailable)');
      }

      try {
        const up = uptime();
        const h = Math.floor(up / 3600);
        const m = Math.floor((up % 3600) / 60);
        lines.push(`Uptime: ${h}h ${m}m`);
      } catch {
        lines.push('Uptime: (unavailable)');
      }

      try {
        const gitStatus = execSync('git status --short', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 5000 });
        const changed = gitStatus.split('\n').filter(Boolean).length;
        lines.push(`Git changes: ${changed} file(s)`);
      } catch {
        lines.push('Git: (not a repo or error)');
      }

      return lines.join('\n');
    },
  },
  {
    name: 'mcp',
    description: 'Show MCP server diagnostics',
    usage: '/mcp [full]',
    handler: async (args, ctx) => {
      // Ensure MCP config discovery has run even in slash-command-only sessions.
      try {
        ctx.getAgent();
      } catch {
        // best-effort init
      }
      const mode = (args[0] ?? '').toLowerCase();
      let statuses = ctx.mcpStatusesRef.current;
      if (statuses.length === 0 || statuses.every((status) => status.state === 'connecting' || status.state === 'retrying')) {
        statuses = await refreshMcpStatuses(ctx);
      }
      if (mode === 'full') {
        return formatMcpDiagnostics(
          ctx.mcpConfiguredRef.current,
          statuses,
          ctx.mcpClientRef.current,
        );
      }
      const totalCount = statuses.length;
      const readyCount = statuses.filter((status) => status.state === 'ready' || status.state === 'degraded').length;
      const firstError = statuses.find((status) => status.error)?.error;
      if (totalCount === 0) {
        return 'No MCP servers configured. Run mcp_bootstrap to add one, then restart Jarvis.';
      }
      if (firstError) {
        return `Pinned MCP summary under status line (${readyCount}/${totalCount} ready). First error: ${firstError}. Run /mcp full for full diagnostics table.`;
      }
      return `Pinned MCP summary under status line (${readyCount}/${totalCount} ready). Run /mcp full for full diagnostics table.`;
    },
  },
  {
    name: 'config',
    description: 'Show or set configuration',
    usage: '/config [key] [value]',
    handler: (args, ctx) => {
      const userConfig = loadJarvisConfig();
      const configPath = getJarvisConfigPath();
      const maskSecret = (value?: string) => (value ? `${value.slice(0, 4)}...${value.slice(-4)}` : '(not set)');
      if (args.length === 0) {
        const modelName = ctx.modelRef.current;
        const outputStyle = ctx.outputStyleRef.current;
        const sid = (ctx.sid ?? 'none').slice(-16);
        const providerKeys = userConfig.providers ? Object.keys(userConfig.providers) : [];
        const lines = [
          'Current configuration:\n',
          `  config-path  = ${configPath}`,
          `  model       = ${modelName}`,
          `  base-url    = ${ctx.baseURLRef.current ?? '(not set)'}`,
          `  api-key     = ${maskSecret(ctx.apiKeyRef.current)}`,
          `  effort      = ${ctx.reasoningEffortRef.current}`,
          `  max-turns   = ${ctx.maxTurns}`,
          `  output-style = ${outputStyle}`,
          `  permissions = ${ctx.permissionModeRef.current}`,
          `  system-prompt = ${ctx.systemPromptRef.current ? '(configured)' : '(not set)'}`,
          `  session     = ${sid}`,
          `  cwd         = ${ctx.cwd}`,
        ];
        if (providerKeys.length > 0) {
          lines.push('', `Providers (${providerKeys.join(', ')}):`);
          for (const [name, p] of Object.entries(userConfig.providers ?? {})) {
            lines.push(`  ${name}: base-url=${p.base_url ?? '(inherit)'}, api-key=${maskSecret(p.api_key)}`);
          }
        }
        lines.push(
          '',
          'Stored user config:',
          `  active-model = ${userConfig.active_model ?? userConfig.model ?? '(not set)'}`,
          `  base-url    = ${userConfig.base_url ?? '(not set)'}`,
          `  api-key     = ${maskSecret(userConfig.api_key)}`,
          `  effort      = ${userConfig.reasoning_effort ?? '(not set)'}`,
          `  max-turns   = ${userConfig.max_turns ?? '(not set)'}`,
          `  output-style = ${userConfig.output_style ?? '(not set)'}`,
          `  permissions = ${userConfig.permission_mode ?? '(not set)'}`,
          `  system-prompt = ${userConfig.system_prompt ? '(configured)' : '(not set)'}`,
        );
        return lines.join('\n');
      }

      const key = args[0].toLowerCase();
      const value = args.slice(1).join(' ').trim();

      if (key === 'model') {
        if (!value) return `model = ${ctx.modelRef.current}`;
        ctx.modelRef.current = value;
        saveJarvisConfig({ active_model: value });
        // Auto-resolve provider credentials for the new model
        const catalogEntry = findModel(value);
        const providerName = catalogEntry?.provider;
        const config = loadJarvisConfig();
        if (providerName && config.providers?.[providerName]) {
          const p = config.providers[providerName];
          if (p.api_key) ctx.apiKeyRef.current = p.api_key;
          if (p.base_url) ctx.baseURLRef.current = p.base_url;
          return `model = ${value} (provider: ${providerName}, auto-resolved credentials)`;
        }
        return `model = ${value} (effective next turn)`;
      }

      if (key === 'base-url') {
        if (!value) return `base-url = ${ctx.baseURLRef.current ?? '(not set)'}`;
        ctx.baseURLRef.current = value;
        saveJarvisConfig({ base_url: value });
        return `base-url = ${value} (effective next launch)`;
      }

      if (key === 'api-key') {
        if (!value) return `api-key = ${maskSecret(ctx.apiKeyRef.current)}`;
        ctx.apiKeyRef.current = value;
        saveJarvisConfig({ api_key: value });
        return 'api-key saved (effective next launch)';
      }

      if (key === 'effort' || key === 'reasoning-effort') {
        if (!value) return `effort = ${ctx.reasoningEffortRef.current}`;
        const normalized = normalizeJarvisReasoningEffort(value);
        if (!normalized) {
          return `Invalid effort. Options: ${JARVIS_REASONING_EFFORTS.join(', ')}`;
        }
        ctx.reasoningEffortRef.current = normalized;
        saveSettings({ reasoning_effort: normalized });
        ctx.invalidateAgent();
        return `effort = ${normalized} (effective next turn)`;
      }

      if (key === 'output-style') {
        if (!value) return `output-style = ${ctx.outputStyleRef.current}`;
        if (!['default', 'concise', 'verbose'].includes(value)) {
          return `Invalid style. Options: default, concise, verbose`;
        }
        ctx.outputStyleRef.current = value;
        saveSettings({ output_style: value as UserSettings['output_style'] });
        return `output-style = ${value}`;
      }

      if (key === 'permissions') {
        if (!value) return `permissions = ${ctx.permissionModeRef.current}`;
        if (!['workspace_write', 'accept_edits', 'bypass'].includes(value)) {
          return 'Invalid permission mode. Options: workspace_write, accept_edits, bypass';
        }
        ctx.permissionModeRef.current = value;
        saveSettings({ permission_mode: value as UserSettings['permission_mode'] });
        return `permissions = ${value}`;
      }

      if (key === 'max-turns') {
        if (!value) return `max-turns = ${ctx.maxTurns}`;
        const parsed = Number.parseInt(value, 10);
        if (!Number.isFinite(parsed) || parsed <= 0) {
          return 'max-turns must be a positive integer.';
        }
        saveSettings({ max_turns: parsed });
        return `max-turns = ${parsed} (effective next launch)`;
      }

      if (key === 'system-prompt') {
        if (!value) return `system-prompt = ${ctx.systemPromptRef.current ? '(configured)' : '(not set)'}`;
        ctx.systemPromptRef.current = value;
        saveJarvisConfig({ system_prompt: value });
        return 'system-prompt saved (effective next launch)';
      }

      return 'Unknown config key. Available: model, base-url, api-key, effort, output-style, permissions, max-turns, system-prompt';
    },
  },
  {
    name: 'effort',
    description: 'Show or set reasoning effort',
    usage: '/effort [auto|minimal|low|medium|high|xhigh|max]',
    handler: (args, ctx) => {
      if (args.length === 0) {
        return `Reasoning effort: ${ctx.reasoningEffortRef.current} (available: ${JARVIS_REASONING_EFFORTS.join(', ')})`;
      }
      const normalized = normalizeJarvisReasoningEffort(args[0]);
      if (!normalized) {
        return `Invalid effort "${args[0]}". Options: ${JARVIS_REASONING_EFFORTS.join(', ')}`;
      }
      ctx.reasoningEffortRef.current = normalized;
      saveSettings({ reasoning_effort: normalized });
      ctx.invalidateAgent();
      return `Reasoning effort set to: ${normalized} (effective next turn)`;
    },
  },
  {
    name: 'output-style',
    description: 'Set output style: default, concise, or verbose',
    usage: '/output-style [default|concise|verbose]',
    handler: (args, ctx) => {
      const validStyles = ['default', 'concise', 'verbose'];
      if (args.length === 0) {
        return `Output style: ${ctx.outputStyleRef.current} (available: ${validStyles.join(', ')})`;
      }
      const style = args[0].toLowerCase();
      if (!validStyles.includes(style)) {
        return `Invalid style "${style}". Options: ${validStyles.join(', ')}`;
      }
      ctx.outputStyleRef.current = style;
      saveSettings({ output_style: style as UserSettings['output_style'] });
      return `Output style set to: ${style}`;
    },
  },
  {
    name: 'security-review',
    description: 'Security audit of uncommitted changes',
    usage: '/security-review',
    handler: async (_args, ctx) => {
      let diff: string;
      try {
        diff = execSync('git diff', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 });
      } catch {
        return 'Error: could not run git diff.';
      }
      if (!diff.trim()) return 'No uncommitted changes to audit.';

      const truncated = diff.length > 12000 ? diff.slice(0, 12000) + '\n... (truncated)' : diff;
      const prompt = `${SECURITY_REVIEW_PROMPT}\n\n---\n${truncated}\n---`;

      ctx.setIsLoading(true);
      try {
        const agent = ctx.getAgent();
        const result = await agent.runTurn(prompt);
        return result.finalAnswer || 'Security review complete (no text response).';
      } catch (e) {
        return `Security review failed: ${e instanceof Error ? e.message : String(e)}`;
      } finally {
        ctx.setIsLoading(false);
      }
    },
  },
  {
    name: 'init',
    description: 'Initialize project with CLAUDE.md and .jarvis config',
    usage: '/init',
    handler: (_args, ctx) => {
      const created: string[] = [];
      const claudeMd = join(ctx.cwd, 'CLAUDE.md');
      const jarvisDir = join(ctx.cwd, '.jarvis');

      try {
        if (!existsSync(claudeMd)) {
          writeFileSync(claudeMd, INIT_CLAUDE_MD_TEMPLATE, 'utf-8');
          created.push('CLAUDE.md');
        } else {
          created.push('CLAUDE.md (already exists, skipped)');
        }
      } catch (e) {
        created.push(`CLAUDE.md (error: ${e instanceof Error ? e.message : String(e)})`);
      }

      try {
        if (!existsSync(jarvisDir)) {
          mkdirSync(jarvisDir, { recursive: true });
          created.push('.jarvis/');
        } else {
          created.push('.jarvis/ (already exists)');
        }
      } catch (e) {
        created.push(`.jarvis/ (error: ${e instanceof Error ? e.message : String(e)})`);
      }

      return `Project initialized:\n${created.map((f) => `  ${f}`).join('\n')}`;
    },
  },
  {
    name: 'permissions',
    description: 'Show or set tool permission mode',
    usage: '/permissions [workspace_write|accept_edits|bypass]',
    handler: (args, ctx) => {
      const modes = ['workspace_write', 'accept_edits', 'bypass'];
      if (args.length === 0) {
        return `Permission mode: ${ctx.permissionModeRef.current}\nAvailable: ${modes.join(', ')}`;
      }
      const mode = args[0].toLowerCase();
      if (!modes.includes(mode)) {
        return `Invalid mode "${mode}". Options: ${modes.join(', ')}`;
      }
      ctx.permissionModeRef.current = mode;
      saveSettings({ permission_mode: mode as UserSettings['permission_mode'] });
      return `Permission mode set to: ${mode}`;
    },
  },
  {
    name: 'skills',
    description: 'List available skills with descriptions',
    usage: '/skills [search]',
    handler: (_args, ctx) => {
      if (!ctx.skills) return 'Skills not loaded yet.';
      const all = ctx.skills.listLoadable();
      const search = _args.join(' ').toLowerCase();
      const filtered = search
        ? all.filter((s) => s.name.toLowerCase().includes(search) || s.description.toLowerCase().includes(search))
        : all;
      if (filtered.length === 0) return `No skills matching "${search}".`;
      const lines = filtered.map((s) => {
        const tagStr = s.tags?.length ? ` [${s.tags.join(', ')}]` : '';
        return `  ${s.name}${tagStr} — ${s.description}`;
      });
      const header = search
        ? `Skills matching "${search}" (${filtered.length}):`
        : `Available skills (${filtered.length}):`;
      return `${header}\n\n${lines.join('\n')}`;
    },
  },
];

function resolveSlashCommand(input: string): { command: SlashCommandDef; args: string[] } | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) return null;

  const parts = trimmed.slice(1).split(/\s+/);
  const name = parts[0]?.toLowerCase();
  const args = parts.slice(1);

  const command = SLASH_COMMANDS.find((c) => c.name === name) ?? null;
  return command ? { command, args } : null;
}

type REPLCommandDef = {
  name: string;
  description: string;
  onExecute: (args: string, fullInput: string) => void;
};

function buildReplCommands(
  ctx: SlashCommandCtx,
  setMessages: (v: Message[] | ((prev: Message[]) => Message[])) => void,
  skills?: SkillRegistry | null,
  setModelSelectorOpen?: (open: boolean) => void,
  setEffortSelectorOpen?: (open: boolean) => void,
): REPLCommandDef[] {
  const builtins = SLASH_COMMANDS.map((cmd) => {
    // Override /effort (no args) to open interactive selector
    if (cmd.name === 'effort') {
      return {
        name: cmd.name,
        description: cmd.description,
        onExecute: (rawArgs: string, fullInput: string) => {
          const userMsg: Message = {
            id: `cmd_${Date.now()}`,
            role: 'user',
            content: fullInput,
            timestamp: Date.now(),
          };
          const args = rawArgs ? rawArgs.split(/\s+/) : [];

          if (args.length === 0 && setEffortSelectorOpen) {
            setMessages((prev) => [...prev, userMsg]);
            setEffortSelectorOpen(true);
            return;
          }

          // Text-based effort set
          const result = cmd.handler(args, ctx);
          if (result instanceof Promise) {
            result.then((text) =>
              setMessages((prev) => [...prev, userMsg, makeSysMsg(text)]),
            );
          } else {
            setMessages((prev) => [...prev, userMsg, makeSysMsg(result)]);
          }
        },
      };
    }

    // Override /model (no args) to open interactive selector
    if (cmd.name === 'model') {
      return {
        name: cmd.name,
        description: cmd.description,
        onExecute: (rawArgs: string, fullInput: string) => {
          const userMsg: Message = {
            id: `cmd_${Date.now()}`,
            role: 'user',
            content: fullInput,
            timestamp: Date.now(),
          };
          const args = rawArgs ? rawArgs.split(/\s+/) : [];

          if (args.length === 0 && setModelSelectorOpen) {
            // Open interactive model selector
            setMessages((prev) => [...prev, userMsg]);
            setModelSelectorOpen(true);
            return;
          }

          // Text-based model set
          const result = cmd.handler(args, ctx);
          if (result instanceof Promise) {
            result.then((text) =>
              setMessages((prev) => [...prev, userMsg, makeSysMsg(text)]),
            );
          } else {
            setMessages((prev) => [...prev, userMsg, makeSysMsg(result)]);
          }
        },
      };
    }

    return {
      name: cmd.name,
      description: cmd.description,
      onExecute: (rawArgs: string, fullInput: string) => {
        const userMsg: Message = {
          id: `cmd_${Date.now()}`,
          role: 'user',
          content: fullInput,
          timestamp: Date.now(),
        };
        const args = rawArgs ? rawArgs.split(/\s+/) : [];
        const result = cmd.handler(args, ctx);
        if (result instanceof Promise) {
          result.then((text) =>
            setMessages((prev) => [...prev, userMsg, makeSysMsg(text)]),
          );
        } else {
          setMessages((prev) => [...prev, userMsg, makeSysMsg(result)]);
        }
      },
    };
  });

  // Auto-derive slash commands from skill names (CC/Codex convention)
  if (skills) {
    const seen = new Set(builtins.map((c) => c.name));
    const skillCmds = skills.listLoadable()
      .filter((s) => {
        const cmdName = s.slashCommand || s.name;
        return !seen.has(cmdName);
      })
      .map((s) => {
        const cmdName = s.slashCommand || s.name;
        seen.add(cmdName);
        return {
          name: cmdName,
          description: s.description,
          onExecute: (_rawArgs: string, fullInput: string) => {
            const userMsg: Message = {
              id: `cmd_${Date.now()}`,
              role: 'user',
              content: fullInput,
              timestamp: Date.now(),
            };
            setMessages((prev) => [
              ...prev,
              userMsg,
              makeSysMsg(`Skill "${s.name}" activated. Your next message will be processed with this skill's instructions.`),
            ]);
          },
        };
      });

    return [...builtins, ...skillCmds];
  }

  return builtins;
}

// ============================================================================
// Tool names that modify the filesystem
// ============================================================================

const FILE_MODIFYING_TOOLS = new Set(['write', 'edit', 'bash']);

function extractModifiedFiles(toolName: string, toolResult: string): string[] {
  const files: string[] = [];
  if (toolName === 'write' || toolName === 'edit') {
    const match = toolResult.match(/^\[(?:wrote|edited)\]\s+(.+)$/m);
    if (match) files.push(match[1].trim());
  }
  return files;
}

function safeJsonParse(raw: string): Record<string, unknown> | null {
  try { return JSON.parse(raw); } catch { return null; }
}

interface FileChange {
  filename: string;
  added: number;
  removed: number;
}

function computeFileChange(toolName: string, toolResult: string): FileChange | null {
  if (toolName !== 'write' && toolName !== 'edit') return null;
  const parsed = safeJsonParse(toolResult);
  if (!parsed) return null;
  const filename = (parsed['path'] || parsed['file'] || parsed['filename'] || '') as string;
  if (!filename) return null;
  if (toolName === 'write') {
    const content = (parsed['content'] || '') as string;
    return { filename, added: content.split('\n').length, removed: 0 };
  }
  const oldStr = (parsed['old_string'] || '') as string;
  const newStr = (parsed['new_string'] || '') as string;
  return {
    filename,
    added: newStr ? newStr.split('\n').length : 0,
    removed: oldStr ? oldStr.split('\n').length : 0,
  };
}

function formatFileChangeSummary(changes: FileChange[]): string {
  return changes.map((c) => {
    const display = c.filename.replace(/\\/g, '/');
    const parts: string[] = [];
    if (c.added > 0) parts.push(`Added ${c.added}`);
    if (c.removed > 0) parts.push(`Removed ${c.removed}`);
    const summary = parts.length > 0 ? parts.join(', ') : 'modified';
    return `● ${display}\n  ⎿  ${summary} lines`;
  }).join('\n');
}

function formatMcpDiagnostics(
  configured: Array<{ id: string; plugin?: string; config: McpServerConfig }>,
  statuses: McpConnectionStatus[],
  client: MCPClient | null,
): string {
  const lines: string[] = ['MCP diagnostics:\n'];
  lines.push(`Configured servers: ${configured.length}`);
  lines.push(`Connected servers: ${client?.connections.length ?? 0}`);
  lines.push('');

  if (configured.length > 0) {
    lines.push('Configured:');
    lines.push('  ID                   Source        Command');
    lines.push('  -------------------- ------------- ------------------------------');
    for (const entry of configured) {
      const id = entry.id.padEnd(20, ' ').slice(0, 20);
      const source = (entry.plugin ?? 'user').padEnd(13, ' ').slice(0, 13);
      const cmd = (entry.config.command ?? '').slice(0, 30);
      lines.push(`  ${id} ${source} ${cmd}`);
    }
    lines.push('');
  }

  if (statuses.length > 0) {
    lines.push('Connection status:');
    lines.push('  ID                   State       Server                  Tools  Resources');
    lines.push('  -------------------- ----------- ----------------------- ------ ---------');
    for (const status of statuses) {
      const id = status.id.padEnd(20, ' ').slice(0, 20);
      const state = status.state.padEnd(11, ' ').slice(0, 11);
      const server = (status.serverName ?? '-').padEnd(23, ' ').slice(0, 23);
      const tools = String(status.toolCount ?? 0).padStart(6, ' ');
      const resources = String(status.resourceCount ?? 0).padStart(9, ' ');
      lines.push(`  ${id} ${state} ${server} ${tools} ${resources}`);
      if (status.error) lines.push(`    error: ${status.error}`);
    }
  } else {
    lines.push('No connection status available yet. Start a new turn or restart Jarvis after config changes.');
  }

  return lines.join('\n');
}

async function refreshMcpStatuses(
  ctx: Pick<SlashCommandCtx, 'mcpClientRef' | 'mcpConfiguredRef' | 'mcpStatusesRef'>,
): Promise<McpConnectionStatus[]> {
  if (!ctx.mcpClientRef.current) {
    ctx.mcpClientRef.current = new MCPClient();
  }
  const configured = ctx.mcpConfiguredRef.current;
  if (configured.length === 0) {
    ctx.mcpStatusesRef.current = [];
    return [];
  }
  ctx.mcpClientRef.current.disconnectAll();
  const statuses = await connectMcpServers(ctx.mcpClientRef.current, configured);
  ctx.mcpStatusesRef.current = statuses;
  return statuses;
}

function estimateTokensFromText(text: string | undefined): number {
  // Delegate to shared CJK-aware estimator from @jarvis/agent
  return estimateTokens(text);
}

function estimateMemoryEntries(cwd: string): MemoryTokenEntry[] {
  const entries: MemoryTokenEntry[] = [];
  const claudePath = join(cwd, 'CLAUDE.md');
  if (existsSync(claudePath)) {
    entries.push({
      path: 'CLAUDE.md',
      tokens: estimateTokensFromText(readFileSync(claudePath, 'utf8')),
    });
  }
  const memoryDir = join(cwd, '.jarvis', 'memory');
  if (existsSync(memoryDir)) {
    try {
      const files = readdirSync(memoryDir).filter((f) => f.endsWith('.md'));
      for (const file of files) {
        entries.push({
          path: `.jarvis/memory/${file}`,
          tokens: estimateTokensFromText(readFileSync(join(memoryDir, file), 'utf8')),
        });
      }
    } catch {
      // ignore memory read errors
    }
  }
  return entries;
}

function buildContextProgressBar(percentRemaining?: number): StatusDetailLine | null {
  if (percentRemaining === undefined || !Number.isFinite(percentRemaining)) {
    return { content: 'CTX [░░░░░░░░░░░░░░░░░░] used 0% · left 100%', color: 'gray' };
  }
  const width = 18;
  const left = Math.max(0, Math.min(100, percentRemaining));
  const used = Math.max(0, 100 - left);
  const filled = Math.round((used / 100) * width);
  const bar = `${'█'.repeat(filled)}${'░'.repeat(Math.max(0, width - filled))}`;
  const color: StatusDetailLine['color'] =
    used < 60 ? 'green' : used < 85 ? 'yellow' : 'red';
  return { content: `CTX [${bar}] used ${used.toFixed(1)}% · left ${left.toFixed(1)}%`, color };
}

function buildMcpFooterLines(
  statuses: McpConnectionStatus[],
): StatusDetailLine[] {
  if (statuses.length === 0) return [{ content: '[MCP --] waiting for status', color: 'gray' }];
  const ok = statuses.filter((status) => status.state === 'ready' || status.state === 'degraded');
  const failed = statuses.filter((status) => status.state === 'failed');
  const firstError = failed[0]?.error;
  const summaryColor: StatusDetailLine['color'] = failed.length > 0 ? 'red' : 'green';
  const summary = `[MCP ${ok.length}/${statuses.length}]`;
  if (!firstError) return [{ content: summary, color: summaryColor }];
  const compactError = firstError.length > 92 ? `${firstError.slice(0, 92)}...` : firstError;
  return [
    { content: summary, color: summaryColor },
    { content: `[MCP ERR] ${compactError}`, color: 'red' },
  ];
}

function estimateTurnTokenCount(stats: {
  trackerStartBlended: number;
  tokenChars: number;
  reasoningChars: number;
} | null, tracker: TokenTracker | null): number | undefined {
  if (!stats) return undefined;
  const blendedDelta = Math.max(0, (tracker?.totalBlended ?? 0) - stats.trackerStartBlended);
  if (blendedDelta > 0) return blendedDelta;

  const approxFromChars = Math.round((stats.tokenChars + stats.reasoningChars) / 4);
  return approxFromChars > 0 ? approxFromChars : undefined;
}

// ============================================================================
// App
// ============================================================================

export function App({ options }: { options: TUIOptions }): React.ReactNode {
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadEvents, setThreadEvents] = useState<ThreadEvent[]>([]);
  const [codexTaskSnapshots, setCodexTaskSnapshots] = useState<CodexTaskSnapshot[]>([]);
  const [codexTurnSnapshots, setCodexTurnSnapshots] = useState<CodexTurnSnapshot[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const agentRef = useRef<AgentLoop | null>(null);
  const historyRef = useRef<ChatMessage[]>([]);
  const toolsRef = useRef<ToolRegistry | null>(null);
  const skillsRef = useRef<SkillRegistry | null>(null);
  const executorRef = useRef<SkillExecutor | null>(null);
  const sessionStoreRef = useRef<SessionStore | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionReadyRef = useRef(false);
  const savedSettings = loadSettings();
  const modelRef = useRef<string>(savedSettings.active_model || savedSettings.model || options.model);
  const apiKeyRef = useRef<string | undefined>(options.apiKey);
  const baseURLRef = useRef<string | undefined>(options.baseURL);
  const reasoningEffortRef = useRef<string>(savedSettings.reasoning_effort || options.reasoningEffort || 'high');
  const systemPromptRef = useRef<string | undefined>(options.systemPrompt);
  const modifiedFilesRef = useRef<Set<string>>(new Set());
  const outputStyleRef = useRef<string>(savedSettings.output_style || 'default');
  const permissionModeRef = useRef<string>(savedSettings.permission_mode || 'workspace_write');
  const poolRef = useRef<SubagentPool | null>(null);
  const mcpRef = useRef<MCPClient | null>(null);
  const mcpStatusesRef = useRef<McpConnectionStatus[]>([]);
  const mcpConfiguredRef = useRef<Array<{ id: string; plugin?: string; config: McpServerConfig }>>([]);
  const tokenTrackerRef = useRef<TokenTracker | null>(null);
  const liveContextUsageRef = useRef<LiveContextUsage | null>(null);
  const elapsedRef = useRef<number>(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const taskCountRef = useRef<{ pending: number; in_progress: number; completed: number }>({ pending: 0, in_progress: 0, completed: 0 });
  const abortRef = useRef<AbortController | null>(null);

  // Model selector state
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false);

  // Effort selector state
  const [effortSelectorOpen, setEffortSelectorOpen] = useState(false);

  // Persistent command history — survives restarts like CC/Codex
  const HISTORY_FILE = join(process.cwd(), '.jarvis', 'history.json');
  const historyRef2 = useRef<string[]>([]);
  if (historyRef2.current.length === 0 && existsSync(HISTORY_FILE)) {
    try {
      const data = JSON.parse(readFileSync(HISTORY_FILE, 'utf-8'));
      if (Array.isArray(data)) historyRef2.current = data.slice(0, 500);
    } catch { /* corrupt file, start fresh */ }
  }
  const [historyVersion, setHistoryVersion] = useState(0);
  const handleHistoryAdd = useCallback((entry: string) => {
    // Dedup consecutive duplicates
    if (historyRef2.current[0] === entry) return;
    historyRef2.current = [entry, ...historyRef2.current].slice(0, 500);
    setHistoryVersion((v) => v + 1);
    try {
      mkdirSync(join(process.cwd(), '.jarvis'), { recursive: true });
      writeFileSync(HISTORY_FILE, JSON.stringify(historyRef2.current, null, 2), 'utf-8');
    } catch { /* best-effort */ }
  }, []);

  // AskUserQuestion bridge state
  const [askQuestions, setAskQuestions] = useState<AskQuestionDef[] | null>(null);
  const askResolveRef = useRef<((answers: Record<string, string>) => void) | null>(null);
  const askRejectRef = useRef<((err: Error) => void) | null>(null);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingThinking, setStreamingThinking] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [spinnerVerb, setSpinnerVerb] = useState<string | undefined>(undefined);
  const [spinnerStatus, setSpinnerStatus] = useState<string | undefined>(undefined);
  const [spinnerDetails, setSpinnerDetails] = useState<string[]>([]);
  const [spinnerCompleted, setSpinnerCompleted] = useState<string[]>([]);
  const [spinnerRunning, setSpinnerRunning] = useState<string | undefined>(undefined);
  const [contextUsageVersion, setContextUsageVersion] = useState(0);
  const [mcpStatusVersion, setMcpStatusVersion] = useState(0);
  const [agentEntries, setAgentEntries] = useState<import('./vendor/ui/AgentsPanel.js').AgentStatusEntry[]>([]);
  const cwd = process.cwd();
  const gitBranch = useMemo(() => getGitBranch(cwd), [cwd, messages.length]);

  // Subscribe to agent store
  useEffect(() => {
    let unsub: (() => void) | undefined;
    import('./agent-store.js').then(({ agentStore }) => {
      unsub = agentStore.subscribe(() => {
        setAgentEntries(agentStore.getSnapshot());
      });
    });
    return () => { unsub?.(); };
  }, []);
  const streamFlushRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamAccumRef = useRef<string>(''); // full accumulated content (OpenClaw replacement mode)
  const reasoningBufferRef = useRef<string>('');
  const reasoningFlushedRef = useRef(false);
  const reasoningDisplayThrottle = useRef<number>(0);
  const streamingContentRef = useRef<string | null>(null);
  const threadEventsRef = useRef<ThreadEvent[]>([]);
  const eventBusRef = useRef<AgentEventBus | null>(null);
  const runStatsRef = useRef<{
    prompt: string;
    startedAt: number;
    trackerStartBlended: number;
    tokenEvents: number;
    tokenChars: number;
    reasoningEvents: number;
    reasoningChars: number;
    toolStarts: number;
    toolEnds: number;
    hadStreamingContent: boolean;
    hadStreamingThinking: boolean;
  } | null>(null);
  const emitDebugEvent = useCallback((event: TUIDebugEvent) => {
    options.debugHooks?.onEvent?.(event);
  }, [options.debugHooks]);
  const invalidateAgent = useCallback(() => {
    agentRef.current = null;
    tokenTrackerRef.current = null;
    liveContextUsageRef.current = null;
  }, []);

  // Model selector handlers
  const handleModelSelect = useCallback((result: import('./vendor/ui/ModelSelector.js').ModelSelectionResult) => {
    const { model, mode } = result;
    modelRef.current = model;
    if (mode === 'default') {
      saveSettings({ model });
    }
    invalidateAgent();
    setModelSelectorOpen(false);
    setMessages((prev) => [
      ...prev,
      makeSysMsg(`Model set to: ${model}${mode === 'session' ? ' (this session only)' : ''}`),
    ]);
  }, [invalidateAgent, setMessages]);

  const handleModelSelectorCancel = useCallback(() => {
    setModelSelectorOpen(false);
  }, []);

  const handleModelEffortChange = useCallback((effort: string) => {
    reasoningEffortRef.current = effort;
    saveSettings({ reasoning_effort: effort as JarvisReasoningEffort });
    invalidateAgent();
  }, [invalidateAgent]);

  // Effort selector handlers
  const handleEffortSelect = useCallback((effort: string) => {
    reasoningEffortRef.current = effort;
    saveSettings({ reasoning_effort: effort as JarvisReasoningEffort });
    invalidateAgent();
    setEffortSelectorOpen(false);
    setMessages((prev) => [...prev, makeSysMsg(`Reasoning effort set to: ${effort}`)]);
  }, [invalidateAgent, setMessages]);

  const handleEffortSelectorCancel = useCallback(() => {
    setEffortSelectorOpen(false);
  }, []);

  const pushSpinnerDetail = useCallback((line: string | null) => {
    if (!line) return;
    setSpinnerDetails((prev) => {
      if (prev[prev.length - 1] === line) return prev;
      const next = [...prev, line];
      return next.length > 6 ? next.slice(-6) : next;
    });
  }, []);

  // Commit current streaming content as an assistant message (CC/OpenClaw pattern:
  // model text between tool calls should appear as separate messages)
  const commitStreaming = useCallback((): string | null => {
    const text = streamingContentRef.current;
    if (text && text.trim()) {
      const msg: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: [{ type: 'text' as const, text }],
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, msg]);
      streamingContentRef.current = null;
      setStreamingContent(null);
      return text;
    }
    return null;
  }, []);

  const drainAndCommit = useCallback((): string | null => {
    if (streamFlushRef.current) {
      clearTimeout(streamFlushRef.current);
      const chunk = streamAccumRef.current;
      streamAccumRef.current = '';
      streamFlushRef.current = null;
      if (chunk) {
        setStreamingContent((prev) => {
          const next = (prev ?? '') + chunk;
          streamingContentRef.current = next;
          return next;
        });
      }
    }
    return commitStreaming();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Set up the AskUserQuestion bridge for the tool
  useEffect(() => {
    setAskUserQuestionBridge((questions) => {
      return new Promise<Record<string, string>>((resolve, reject) => {
        askResolveRef.current = resolve;
        askRejectRef.current = reject;
        setAskQuestions(questions);
      });
    });
    return () => setAskUserQuestionBridge(null);
  }, []);

  // Initialize session store and restore previous session for this directory
  useEffect(() => {
    const store = new SessionStore();
    sessionStoreRef.current = store;

    const cwd = process.cwd();
    store.listSessions().then(async (sessionIds) => {
      let best: { id: string; updatedAt: string } | null = null;

      for (const sid of sessionIds) {
        try {
          const sidecar = await store.getSidecar(sid);
          if (sidecar.cwd === cwd) {
            if (!best || sidecar.updated_at > best.updatedAt) {
              best = { id: sid, updatedAt: sidecar.updated_at };
            }
          }
        } catch {
          // Skip sessions with missing sidecar
        }
      }

      if (best) {
        sessionIdRef.current = best.id;
        const rawMessages = await store.loadMessages(best.id);
        const chatMessages: ChatMessage[] = rawMessages.map((m) => {
          const meta = (m.metadata ?? {}) as Record<string, unknown>;
          return {
            role: m.role as ChatMessage['role'],
            content: m.content as string,
            messageId: m.message_id as string,
            toolCallId: m.tool_call_id as string | undefined,
            name: meta['_name'] as string | undefined,
            metadata: meta,
          };
        });
        historyRef.current = chatMessages;
      } else {
        const sid = `session_${crypto.randomUUID().slice(0, 12)}`;
        await store.createSession(sid, { cwd });
        sessionIdRef.current = sid;
      }

      sessionReadyRef.current = true;
    });
  }, []);

  const getAgent = useCallback((): AgentLoop => {
    if (!agentRef.current) {
      if (!eventBusRef.current) {
        eventBusRef.current = new AgentEventBus();
      }
      const eventBus = eventBusRef.current;
      const bindProgressEvent = (eventName: string) => {
        eventBus.on(eventName, (payload) => {
          pushSpinnerDetail(summarizeEventProgress(eventName, payload));
          if (eventName === 'llm:request') {
            setSpinnerStatus('preparing the next step');
          }
          if (eventName === 'tool:executing') {
            setSpinnerStatus(`using ${humanizeToolName(payload.toolName)}`);
          }
          if (eventName === 'turn:warning' && typeof payload.warning === 'string') {
            setSpinnerStatus(payload.warning);
          }
          if (eventName === 'turn:complete' && typeof payload.stopReason === 'string') {
            setSpinnerStatus('finalizing the response');
          }
        });
      };
      for (const eventName of ['turn:start', 'skills:matched', 'context:compressing', 'llm:request', 'llm:response', 'tool:executing', 'tool:result', 'turn:warning', 'turn:complete']) {
        bindProgressEvent(eventName);
      }
      eventBus.on('context_window_usage', (payload) => {
        const used = Number(payload.used_tokens ?? 0);
        const window = Number(payload.context_window ?? tokenTrackerRef.current?.contextWindow ?? 200_000);
        const pct = Number(payload.usage_pct ?? (window > 0 ? used / window : 0));
        const messageCount = Number(payload.message_count ?? 0);
        const prev = liveContextUsageRef.current;
        liveContextUsageRef.current = {
          ...(prev ?? {
            contextWindow: window,
            usedTokens: used,
            usagePct: pct,
            messageCount,
          }),
          contextWindow: window,
          usedTokens: used,
          usagePct: pct,
          messageCount,
        };
        setContextUsageVersion((v) => v + 1);
      });
      eventBus.on('context_usage_breakdown', (payload) => {
        const prev = liveContextUsageRef.current;
        const contextWindow = Number(payload.context_window ?? prev?.contextWindow ?? tokenTrackerRef.current?.contextWindow ?? 200_000);
        const estimatedTotal = Number(payload.estimated_total_tokens ?? 0);
        const estimatedUsagePct = contextWindow > 0 ? (estimatedTotal / contextWindow) : 0;
        liveContextUsageRef.current = {
          ...(prev ?? {
            contextWindow,
            usedTokens: Number(payload.estimated_total_tokens ?? payload.used_tokens ?? 0),
            usagePct: estimatedUsagePct,
            messageCount: Number(payload.message_count ?? 0),
          }),
          contextWindow,
          usedTokens: estimatedTotal > 0 ? estimatedTotal : (prev?.usedTokens ?? 0),
          usagePct: estimatedUsagePct,
          systemPromptTokens: Number(payload.system_prompt_tokens ?? 0),
          projectContextTokens: Number(payload.project_context_tokens ?? 0),
          skillsTokens: Number(payload.skills_tokens ?? 0),
          memoryTokens: Number(payload.memory_tokens ?? 0),
          conversationTokens: Number(payload.conversation_tokens ?? 0),
          toolSchemasTokens: Number(payload.tool_schemas_tokens ?? 0),
          mcpToolsTokens: Number(payload.mcp_tools_tokens ?? 0),
          estimatedTotalTokens: estimatedTotal,
        };
        setContextUsageVersion((v) => v + 1);
      });

      const tools = new ToolRegistry();
      for (const tool of allBuiltinTools) {
        tools.register(tool);
      }
      // Register web tools (mirrors CLI main.ts registerWebTools)
      {
        const tavilySearch = tryCreateTavilySearch();
        const tavilyFetch = tryCreateTavilyFetch();
        if (tavilySearch) { tools.register(createWebSearchTool(tavilySearch)); }
        else { tools.register(webSearchTool); }
        if (tavilyFetch) { tools.register({ ...webFetchTool, handler: createWebFetchHandler(tavilyFetch) }); }
        else { tools.register(webFetchTool); }
      }
      // Memory search/get tools (mirrors CLI main.ts bootstrap)
      {
        const memoryStore = new MarkdownMemoryStore();
        tools.register({
          name: 'memory_search',
          toolset: 'memory',
          description: 'Search persistent memory entries by keyword',
          isAsync: true,
          schema: {
            type: 'function',
            function: {
              name: 'memory_search',
              description: 'Search persistent memory entries by keyword',
              parameters: {
                type: 'object',
                properties: {
                  query: { type: 'string', description: 'Search query' },
                  maxResults: { type: 'number', description: 'Max results (default 5)' },
                  memoryType: { type: 'string', description: 'Filter by type: user, project, feedback, reference' },
                },
                required: ['query'],
              },
            },
          },
          handler: (args: Record<string, unknown>) => createMemorySearchHandler(memoryStore)(args),
        });
        tools.register({
          name: 'memory_get',
          toolset: 'memory',
          description: 'Read a specific memory entry by name',
          isAsync: true,
          schema: {
            type: 'function',
            function: {
              name: 'memory_get',
              description: 'Read a specific memory entry by name',
              parameters: {
                type: 'object',
                properties: {
                  name: { type: 'string', description: 'Memory entry name' },
                },
                required: ['name'],
              },
            },
          },
          handler: (args: Record<string, unknown>) => createMemoryGetHandler(memoryStore)(args),
        });
      }
      toolsRef.current = tools;

      if (!skillsRef.current) {
        const pluginSkillDirs = discoverPluginSkillDirs(process.cwd());
        skillsRef.current = new SkillRegistry();
        skillsRef.current.discover({
          builtinDir: 'skills',
          projectDir: '.jarvis/skills',
          extraDirs: pluginSkillDirs.map((p) => ({ path: p, source: 'plugin' as const })),
        });
      }
      if (!executorRef.current) {
        executorRef.current = new SkillExecutor(skillsRef.current);
      }
      tools.register(createSkillLoadTool(skillsRef.current));
      tools.register(createSkillTool(skillsRef.current));

      // MCP client — wire resource listing/reading tools + dynamic tool exposure
      if (!mcpRef.current) {
        mcpRef.current = new MCPClient();
      }
      tools.register(createListMcpResourcesTool(mcpRef.current));
      tools.register(createReadMcpResourceTool(mcpRef.current));
      tools.register(createMcpStatusTool(mcpRef.current));
      tools.register(createMcpHealthcheckTool(mcpRef.current));
      const mcpServers = [
        ...discoverUserMcpServers(process.cwd()),
        ...discoverPluginMcpServers(process.cwd()),
      ];
      mcpConfiguredRef.current = mcpServers;
      if (mcpServers.length > 0) {
        void connectMcpServers(mcpRef.current, mcpServers).then((statuses) => {
          mcpStatusesRef.current = statuses;
          setMcpStatusVersion((v) => v + 1);
          for (const mcpTool of createMcpToolEntries(mcpRef.current!)) {
            try {
              tools.register(mcpTool);
            } catch {
              // ignore duplicate dynamic tool registration
            }
          }
        });
      }
      for (const mcpTool of createMcpToolEntries(mcpRef.current)) {
        tools.register(mcpTool);
      }

      // Subagent pool — wire Agent tool with agent store updates
      if (!poolRef.current) {
        poolRef.current = new SubagentPool();

        // Wire pool status updates to agent store for TUI panel
        poolRef.current.onStatusUpdate = (entry) => {
          import('./agent-store.js').then(({ agentStore }) => {
            agentStore.upsert({
              agentId: entry.agentId,
              status: entry.status,
              role: entry.role ?? 'unknown',
              depth: entry.depth ?? 0,
              parentId: null,
              task: entry.task,
              startedAt: Date.now(),
            });
          });
        };
        const provider = new LLMProvider({
          model: modelRef.current,
          apiKey: apiKeyRef.current,
          baseURL: baseURLRef.current,
          reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
        });
        poolRef.current.setRunner(async (config: SubagentConfig) => {
          const subTools = new ToolRegistry();
          const whitelist = toolWhitelistForType(config.agentType);
          for (const tool of allBuiltinTools) {
            if (!whitelist || whitelist.includes(tool.name)) {
              subTools.register(tool);
            }
          }
          subTools.register(createSkillLoadTool(skillsRef.current!));
          subTools.register(createSkillTool(skillsRef.current!));

          const subLoop = new AgentLoop({
            model: {
              model: modelRef.current,
              apiKey: apiKeyRef.current,
              baseURL: baseURLRef.current,
              reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
            },
            maxTurns: config.budgetSteps ?? 5,
            tools: subTools,
            provider,
            skillRegistry: skillsRef.current!,
            skillExecutor: executorRef.current!,
            hooks: new HookRegistry(),
          });

          const result = await subLoop.runTurn(config.task);
          return {
            agentId: config.agentId,
            status: result.ok ? ('completed' as const) : ('failed' as const),
            answer: result.finalAnswer,
            turnsUsed: result.toolCalls.length,
          };
        });
      }
      tools.register(createAgentTool(poolRef.current));

      if (!tokenTrackerRef.current) {
        const mainProvider = new LLMProvider({
          model: modelRef.current,
          apiKey: apiKeyRef.current,
          baseURL: baseURLRef.current,
          reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
        });
        tokenTrackerRef.current = new TokenTracker(mainProvider.contextWindow);
      }
      agentRef.current = new AgentLoop({
        model: {
          model: modelRef.current,
          apiKey: apiKeyRef.current,
          baseURL: baseURLRef.current,
          reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
        },
        maxTurns: options.maxTurns,
        systemPrompt: options.systemPrompt,
        eventBus,
        onThreadEvent: (event) => {
          threadEventsRef.current.push(event);
          setThreadEvents((prev) => [...prev, event]);
        },
        tools,
        skillRegistry: skillsRef.current,
        skillExecutor: executorRef.current,
        tokenTracker: tokenTrackerRef.current,
        onToken: (token: string) => {
          if (runStatsRef.current) {
            runStatsRef.current.tokenEvents += 1;
            runStatsRef.current.tokenChars += token.length;
            runStatsRef.current.hadStreamingContent = true;
          }
          // First content token: flush live reasoning as thinking block
          if (!reasoningFlushedRef.current && reasoningBufferRef.current) {
            const thinkingText = reasoningBufferRef.current;
            reasoningFlushedRef.current = true;
            setStreamingThinking(null);
            if (thinkingText.length > 20) {
              setMessages((prev) => [...prev, {
                id: `thinking_${Date.now()}`,
                role: 'assistant',
                content: [{ type: 'thinking' as const, text: thinkingText.slice(0, 65536) }],
                timestamp: Date.now(),
              }]);
            }
            setSpinnerStatus('drafting the response');
          }
          // Skip DSML tool call tags leaked into visible text
          if (token.includes('｜')) return;
          // Buffer tokens and flush periodically (append mode)
          streamAccumRef.current += token;
          if (!streamFlushRef.current) {
            streamFlushRef.current = setTimeout(() => {
              const chunk = streamAccumRef.current;
              streamAccumRef.current = '';
              streamFlushRef.current = null;
              setStreamingContent((prev) => {
                const next = (prev ?? '') + chunk;
                streamingContentRef.current = next;
                return next;
              });
            }, 50);
          }
        },
        onReasoningDelta: (delta: string) => {
          if (runStatsRef.current) {
            runStatsRef.current.reasoningEvents += 1;
            runStatsRef.current.reasoningChars += delta.length;
            runStatsRef.current.hadStreamingThinking = true;
          }
          const buf = reasoningBufferRef.current + delta;
          reasoningBufferRef.current = buf.length > 262144 ? buf.slice(-262144) : buf;
          // Live thinking display: throttle React state updates (CC/OpenClaw pattern)
          const now = Date.now();
          if (now - reasoningDisplayThrottle.current > 200) {
            reasoningDisplayThrottle.current = now;
            setStreamingThinking(buf);
          }
          const boldMatch = delta.match(/\*\*([^*]+)\*\*/);
          if (boldMatch) {
            setSpinnerVerb(boldMatch[1]);
          } else if (!spinnerVerb) {
            const clean = delta.replace(/[#*`\n]/g, ' ').replace(/\s+/g, ' ').trim();
            if (clean.length > 10) setSpinnerVerb(clean.slice(0, 60));
          }
        },
        onToolStart: (callId, toolName, args) => {
          if (runStatsRef.current) {
            runStatsRef.current.toolStarts += 1;
          }
          emitDebugEvent({
            type: 'tool_started',
            toolName,
            callId,
            timestamp: Date.now(),
          });
          setSpinnerRunning(toolName);
          drainAndCommit(); // Drain flush buffer then commit text before tool
          const argRecord = typeof args === 'object' && args !== null
            ? (args as Record<string, unknown>)
            : undefined;
          const input = formatToolLine(toolName, argRecord);
          setMessages((prev) => [...prev, {
            id: `tool_${callId}`,
            role: 'assistant',
            content: [{
              type: 'tool_use' as const,
              toolName,
              input,
              status: 'running' as const,
            }],
            timestamp: Date.now(),
          }]);
        },
        onToolEnd: (callId, toolName, result) => {
          if (runStatsRef.current) {
            runStatsRef.current.toolEnds += 1;
          }
          emitDebugEvent({
            type: 'tool_finished',
            toolName,
            callId,
            ok: result.ok,
            resultLength: result.content.length,
            timestamp: Date.now(),
          });
          setSpinnerRunning(undefined);
          setSpinnerCompleted((prev) => [...prev, toolName]);
          setMessages((prev) => prev.map((m) => {
            if (m.id === `tool_${callId}`) {
              const now = Date.now();
              const content = [...(m.content as MessageContent[])];
              const toolBlock = content.find((c) => c.type === 'tool_use');
              if (toolBlock && 'status' in toolBlock) {
                const durationMs = m.timestamp ? now - m.timestamp : undefined;
                const updated = { ...toolBlock, status: result.ok ? 'success' as const : 'error' as const, result: result.content.slice(0, 2000), durationMs };
                return { ...m, content: content.map((c) => c.type === 'tool_use' ? updated : c) };
              }
            }
            return m;
          }));
        },
        sessionStore: sessionStoreRef.current ?? undefined,
        toolRuntime: createToolRuntime(tools, {
          permissionMode: permissionModeRef.current,
          sandbox: loadJarvisConfig().sandbox,
          projectRoot: process.cwd(),
        }),
      });
    }
    return agentRef.current;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  const onSubmit = useCallback(async (prompt: string) => {
    // Interrupt any in-progress run (supports type-ahead)
    agentRef.current?.interrupt('superseded_by_new_prompt');
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const turnStartedAt = Date.now();
    runStatsRef.current = {
      prompt,
      startedAt: turnStartedAt,
      trackerStartBlended: tokenTrackerRef.current?.totalBlended ?? 0,
      tokenEvents: 0,
      tokenChars: 0,
      reasoningEvents: 0,
      reasoningChars: 0,
      toolStarts: 0,
      toolEnds: 0,
      hadStreamingContent: false,
      hadStreamingThinking: false,
    };
    emitDebugEvent({
      type: 'run_started',
      prompt,
      timestamp: turnStartedAt,
    });

    const userMsg: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);
    setStreamingContent(null);
    setStreamingThinking(null);
    streamingContentRef.current = null;
    setSpinnerVerb('Concocting');
    setSpinnerStatus(undefined);
    setSpinnerDetails([]);
    setSpinnerCompleted([]);
    setSpinnerRunning(undefined);
    streamAccumRef.current = ''; // Clear accumulated content
    reasoningBufferRef.current = '';
    reasoningDisplayThrottle.current = 0;
    reasoningFlushedRef.current = false;
    if (streamFlushRef.current) { clearTimeout(streamFlushRef.current); streamFlushRef.current = null; }

    // Create abort controller for this run
    const abort = new AbortController();
    abortRef.current = abort;

    // Start elapsed timer
    const startTime = Date.now();
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    elapsedRef.current = 0;
    setElapsedMs(0);
    elapsedTimerRef.current = setInterval(() => {
      elapsedRef.current = Date.now() - startTime;
      setElapsedMs(elapsedRef.current);
    }, 1000);

    try {
      if (abort.signal.aborted) throw new DOMException('Aborted', 'AbortError');

      const agent = getAgent();
      const store = sessionStoreRef.current;
      const sid = sessionIdRef.current!;

      // Persist user message to session store (truth source for runTurn context)
      if (store && sid) {
        await store.appendMessage(sid, 'user', prompt, { turnId: undefined });
      }
      // Keep historyRef for slash-command compat (display layer only)
      historyRef.current = [...historyRef.current, {
        role: 'user',
        content: prompt,
        messageId: `msg_${crypto.randomUUID()}`,
      }];

      const result = await agent.runTurn(prompt, {
        sessionId: sid ?? undefined,
        cwd: process.cwd(),
      });

      // Persist final answer to session store
      if (store && sid && result.finalAnswer) {
        await store.saveFinalAnswer(sid, result.turnId, result.finalAnswer);
      }

      // Track files modified by this turn
      for (const tr of result.toolResults) {
        const name = tr['name'] as string ?? '';
        if (FILE_MODIFYING_TOOLS.has(name)) {
          const files = extractModifiedFiles(name, tr['content'] as string ?? '');
          for (const f of files) {
            modifiedFilesRef.current.add(f);
          }
        }
      }

      // Drain and commit any remaining streaming text BEFORE building
      // the final message (so we know if text was already committed)
      const committedStreamingText = drainAndCommit();
      const normalizedCommittedText = committedStreamingText?.trim() ?? '';
      const finalAnswer = typeof result.finalAnswer === 'string' ? result.finalAnswer.trim() : '';

      const content: MessageContent[] = [];
      let taskSnapshot: CodexTaskSnapshot | null = null;

      // Show reasoning as a collapsible thinking block
      if (result.reasoning) {
        content.push({
          type: 'thinking',
          text: result.reasoning,
        });
      }

      // Collect file changes for summary display
      const fileChanges: FileChange[] = [];
      for (const tr of result.toolResults) {
        const name = tr['name'] as string ?? '';
        const trContent = tr['content'] as string ?? '';
        const change = computeFileChange(name, trContent);
        if (change) fileChanges.push(change);

        const parsed = parseToolContent(name, trContent);
        if (parsed) {
          if (parsed.type === 'task_result' && parsed.counts) {
            taskCountRef.current = parsed.counts;
            taskSnapshot = {
              turnId: result.turnId,
              sourceId: `task_snapshot_${result.turnId}`,
              counts: parsed.counts,
              tasks: parsed.tasks,
            };
          } else {
            content.push(parsed);
          }
        }
        // Note: tool_use blocks already pushed via onToolStart/onToolEnd
        // during agent execution — skip here to avoid duplicates.
      }

      // Preserve the final answer unless the trailing streamed text already
      // rendered the same content.
      if (finalAnswer && finalAnswer !== normalizedCommittedText) {
        content.push({ type: 'text', text: result.finalAnswer });
      }

      // Append file change summary if any files were modified
      if (fileChanges.length > 0) {
        content.push({
          type: 'diff',
          filename: `Changes (${fileChanges.length} file${fileChanges.length > 1 ? 's' : ''})`,
          diff: formatFileChangeSummary(fileChanges),
        });
      }

      if (content.length > 0) {
        const assistantMsg: Message = {
          id: `msg_${Date.now()}`,
          role: 'assistant',
          content,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }

      if (taskSnapshot) {
        setCodexTaskSnapshots((prev) => [
          ...prev.filter((snapshot) => snapshot.turnId !== taskSnapshot!.turnId),
          taskSnapshot!,
        ]);
      }

      const turnTokenCount = estimateTurnTokenCount(runStatsRef.current, tokenTrackerRef.current);
      setCodexTurnSnapshots((prev) => [
        ...prev.filter((snapshot) => snapshot.turnId !== result.turnId),
        {
          turnId: result.turnId,
          elapsedMs: Date.now() - turnStartedAt,
          tokenCount: turnTokenCount,
        },
      ]);

      const stats = runStatsRef.current;
      const reasoningText = result.reasoning ?? '';
      const liveStreamingText = streamingContentRef.current ?? '';
      const committedText = committedStreamingText ?? '';
      const resultAnswer = result.finalAnswer ?? '';
      emitDebugEvent({
        type: 'run_completed',
        prompt,
        elapsedMs: Date.now() - turnStartedAt,
        finalAnswerLength: resultAnswer.length,
        finalAnswerPreview: resultAnswer.slice(0, 200),
        finalAnswerTail: resultAnswer.slice(-200),
        reasoningLength: reasoningText.length,
        streamedContentLength: liveStreamingText.length,
        committedStreamingLength: committedText.length,
        tokenEvents: stats?.tokenEvents ?? 0,
        tokenChars: stats?.tokenChars ?? 0,
        reasoningEvents: stats?.reasoningEvents ?? 0,
        reasoningChars: stats?.reasoningChars ?? 0,
        toolStarts: stats?.toolStarts ?? 0,
        toolEnds: stats?.toolEnds ?? 0,
        hadStreamingContent: stats?.hadStreamingContent ?? false,
        hadStreamingThinking: stats?.hadStreamingThinking ?? false,
        toolResultCount: result.toolResults.length,
        stopReason: result.stopReason,
        turnsUsed: result.toolCalls.length,
        toolResults: result.toolResults.map((tr: Record<string, unknown>) => ({
          name: tr['name'] as string ?? '',
          ok: tr['ok'] as boolean ?? false,
          contentLength: typeof tr['content'] === 'string' ? (tr['content'] as string).length : 0,
          error: tr['error'] as string | undefined,
        })),
        newMessageCount: 1,
        timestamp: Date.now(),
      });

      // Append assistant message to historyRef for display/slash-command compat
      if (result.finalAnswer) {
        historyRef.current = [...historyRef.current, {
          role: 'assistant' as const,
          content: result.finalAnswer,
          messageId: `msg_${crypto.randomUUID()}`,
        }];
      }
    } catch (err) {
      const isAbort = err instanceof DOMException && err.name === 'AbortError';
      const stats = runStatsRef.current;
      emitDebugEvent({
        type: 'run_failed',
        prompt,
        elapsedMs: Date.now() - turnStartedAt,
        tokenEvents: stats?.tokenEvents ?? 0,
        tokenChars: stats?.tokenChars ?? 0,
        reasoningEvents: stats?.reasoningEvents ?? 0,
        reasoningChars: stats?.reasoningChars ?? 0,
        toolStarts: stats?.toolStarts ?? 0,
        toolEnds: stats?.toolEnds ?? 0,
        hadStreamingContent: stats?.hadStreamingContent ?? false,
        hadStreamingThinking: stats?.hadStreamingThinking ?? false,
        error: err instanceof Error ? err.message : String(err),
        isAbort,
        timestamp: Date.now(),
      });
      const errorContent: MessageContent = isAbort
        ? { type: 'text', text: 'Conversation interrupted.' }
        : { type: 'error', message: err instanceof Error ? err.message : String(err) };
      const errMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: [errorContent],
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      // Cleanup: commit any remaining text (handles error/abort path —
      // on success path this is a no-op since drainAndCommit already ran)
      commitStreaming();
      abortRef.current = null;
      setIsLoading(false);
      setStreamingContent(null);
      streamAccumRef.current = '';
      if (streamFlushRef.current) { clearTimeout(streamFlushRef.current); streamFlushRef.current = null; }
      // Stop elapsed timer
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
      setElapsedMs(elapsedRef.current);
      runStatsRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getAgent, options.model]);

  const replCommands: REPLCommandDef[] = useMemo(
    () =>
      buildReplCommands(
        {
          store: sessionStoreRef.current,
          sid: sessionIdRef.current,
          skills: skillsRef.current,
          historyRef,
          messages,
          setMessages,
          setIsLoading,
          cwd: process.cwd(),
          modelRef,
          apiKeyRef,
          baseURLRef,
          reasoningEffortRef,
          systemPromptRef,
          modifiedFilesRef,
          getAgent,
          invalidateAgent,
          maxTurns: options.maxTurns,
          outputStyleRef,
          permissionModeRef,
          mcpClientRef: mcpRef,
          mcpStatusesRef,
          mcpConfiguredRef,
          tokenTrackerRef,
          toolsRef,
          liveContextUsageRef,
        },
        setMessages,
        skillsRef.current,
        setModelSelectorOpen,
        setEffortSelectorOpen,
      ),
    // Rebuild only when getAgent changes (lazy init via useCallback)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [getAgent, invalidateAgent, options.maxTurns, messages],
  );

  useEffect(() => {
    try {
      getAgent();
    } catch {
      // Best-effort prewarm only.
    }
  }, [getAgent]);

  const statusSegments: StatusLineSegment[] = useMemo(() => {
    const tracker = tokenTrackerRef.current;
    const liveUsage = liveContextUsageRef.current;
    const liveUsedPct = liveUsage
      ? Math.max(0, Math.min(100, liveUsage.usagePct * 100))
      : undefined;
    const liveContextRemaining = liveUsedPct !== undefined
      ? Math.max(0, Math.min(100, 100 - liveUsedPct))
      : undefined;
    return buildStatusSegments({
      cwd,
      model: parseModelName(modelRef.current).cleanName,
      gitBranch,
      effort: reasoningEffortRef.current,
      isLoading,
      hasQuestion: askQuestions !== null,
      totalTokens: tracker?.turnCount ? tracker.totalBlended : undefined,
      contextPercentRemaining: liveContextRemaining ?? (tracker?.turnCount ? tracker.contextPercentRemaining : undefined),
      taskCounts: taskCountRef.current,
      elapsedMs,
      sessionId: sessionIdRef.current,
    });
  }, [askQuestions, contextUsageVersion, cwd, elapsedMs, gitBranch, isLoading, messages.length, modelRef.current]);

  const statusDetailLines = useMemo(() => {
    const lines: StatusDetailLine[] = [];
    const tracker = tokenTrackerRef.current;
    const liveUsage = liveContextUsageRef.current;
    const liveUsedPct = liveUsage
      ? Math.max(0, Math.min(100, liveUsage.usagePct * 100))
      : undefined;
    const liveContextRemaining = liveUsedPct !== undefined
      ? Math.max(0, Math.min(100, 100 - liveUsedPct))
      : undefined;
    const contextLine = buildContextProgressBar(
      liveContextRemaining ?? (tracker?.turnCount ? tracker.contextPercentRemaining : undefined),
    );
    if (contextLine) lines.push(contextLine);
    // Per-component breakdown (when available from context_usage_breakdown event)
    if (liveUsage) {
      const parts: string[] = [];
      if (liveUsage.systemPromptTokens) parts.push(`sys:${formatTokensCompact(liveUsage.systemPromptTokens)}`);
      if (liveUsage.conversationTokens) parts.push(`msg:${formatTokensCompact(liveUsage.conversationTokens)}`);
      if (liveUsage.skillsTokens) parts.push(`skills:${formatTokensCompact(liveUsage.skillsTokens)}`);
      if (liveUsage.mcpToolsTokens) parts.push(`mcp:${formatTokensCompact(liveUsage.mcpToolsTokens)}`);
      const toolTotal = (liveUsage.toolSchemasTokens ?? 0) + (liveUsage.mcpToolsTokens ?? 0);
      if (toolTotal > 0 && !liveUsage.mcpToolsTokens) parts.push(`tools:${formatTokensCompact(toolTotal)}`);
      if (parts.length > 0) {
        lines.push({ content: `  ${parts.join(' · ')}`, color: 'gray' });
      }
    }
    // Context window size guard — warn for small windows
    const contextWindow = liveUsage?.contextWindow ?? tracker?.contextWindow ?? 128_000;
    const guard = validateContextWindow(contextWindow);
    if (guard.level !== 'ok') {
      lines.push({ content: `CTX guard: ${guard.message}`, color: guard.level === 'error' ? 'red' : 'yellow' });
    }
    const mcpLines = buildMcpFooterLines(mcpStatusesRef.current);
    const mcpHealthy = mcpStatusesRef.current.length > 0
      && mcpStatusesRef.current.every((status) => status.state === 'ready' || status.state === 'degraded');
    if (!mcpHealthy) {
      lines.push(...mcpLines);
    } else if (lines.length === 0) {
      // keep one short line only if nothing else is shown
      lines.push(mcpLines[0]!);
    }
    return lines.slice(0, 3);
  }, [contextUsageVersion, elapsedMs, isLoading, mcpStatusVersion, messages.length]);

  const spinnerTokenCount = useMemo(() => {
    if (!isLoading) return undefined;
    return estimateTurnTokenCount(runStatsRef.current, tokenTrackerRef.current);
  }, [elapsedMs, isLoading, messages.length, streamingContent, streamingThinking]);

  // Interrupt handler — cancels current agent run
  const handleInterrupt = useCallback(() => {
    agentRef.current?.interrupt('user_interrupt');
    if (abortRef.current) {
      abortRef.current.abort();
    }
    setSpinnerStatus('stopping this turn');
    pushSpinnerDetail('Interrupt requested');
  }, [pushSpinnerDetail]);

  // Exit handler — clean shutdown (Ctrl+C double-tap or Ctrl+D)
  const handleExit = useCallback(() => {
    agentRef.current?.interrupt('process_exit');
    if (abortRef.current) abortRef.current.abort();
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    process.exit(0);
  }, []);

  // AskUserQuestion submit handler
  const handleAskSubmit = useCallback(
    (answers: Record<string, string>) => {
      askResolveRef.current?.(answers);
      askResolveRef.current = null;
      askRejectRef.current = null;
      setAskQuestions(null);
    },
    [],
  );

  const handleAskCancel = useCallback(() => {
    askRejectRef.current?.(new Error('User cancelled'));
    askResolveRef.current = null;
    askRejectRef.current = null;
    setAskQuestions(null);
  }, []);

  useEffect(() => {
    if (messages.length === 0) {
      threadEventsRef.current = [];
      setThreadEvents([]);
      setCodexTaskSnapshots([]);
      setCodexTurnSnapshots([]);
    }
  }, [messages.length]);

  const askUserQuestion = askQuestions
    ? { questions: askQuestions, onSubmit: handleAskSubmit, onCancel: handleAskCancel }
    : undefined;

  return (
    <REPL
      messages={messages}
      threadEvents={threadEvents}
      codexTaskSnapshots={codexTaskSnapshots}
      codexTurnSnapshots={codexTurnSnapshots}
      presentationMode={options.presentationMode ?? 'codex'}
      isLoading={isLoading}
      streamingContent={streamingContent}
      streamingThinking={streamingThinking}
      streamingElapsedMs={elapsedMs}
      onSubmit={onSubmit}
      onInterrupt={handleInterrupt}
      onExit={handleExit}
      model={modelRef.current}
      statusSegments={statusSegments}
      statusDetailLines={statusDetailLines}
      commands={replCommands}
      askUserQuestion={askUserQuestion}
      spinnerTokenCount={spinnerTokenCount}
      spinnerVerb={spinnerVerb}
      spinnerStatus={spinnerStatus}
      spinnerDetails={spinnerDetails}
      spinnerRunning={spinnerRunning}
      spinnerCompleted={spinnerCompleted}
      agents={agentEntries}
      history={historyRef2.current}
      onHistoryAdd={handleHistoryAdd}
      modelSelectorOpen={modelSelectorOpen}
      modelSelectorCurrentModel={modelRef.current}
      modelSelectorCurrentEffort={reasoningEffortRef.current}
      modelSelectorKnownModels={getAllModels()}
      onModelSelect={handleModelSelect}
      onModelSelectorCancel={handleModelSelectorCancel}
      onModelEffortChange={handleModelEffortChange}
      effortSelectorOpen={effortSelectorOpen}
      effortSelectorCurrent={reasoningEffortRef.current}
      effortSelectorLevels={JARVIS_REASONING_EFFORTS}
      onEffortSelect={handleEffortSelect}
      onEffortSelectorCancel={handleEffortSelectorCancel}
      welcome={<WelcomeScreen appName="Jarvis" subtitle="AI Coding Assistant" model={parseModelName(modelRef.current).cleanName} color="#00BFFF" tips={['Send a prompt to begin', '/help for commands', 'Ctrl+C twice exits']} />}
    />
  );
}

function summarizeEventProgress(event: string, payload: Record<string, unknown>): string | null {
  switch (event) {
    case 'turn:start':
      return 'Opening a new turn';
    case 'skills:matched': {
      const skills = Array.isArray(payload.skills) ? payload.skills : [];
      if (skills.length === 0) return null;
      const names = skills
        .map((item) => (item && typeof item === 'object' ? String((item as Record<string, unknown>).name ?? '') : ''))
        .filter(Boolean)
        .slice(0, 3);
      return names.length > 0 ? `Loaded context from ${names.join(', ')}` : null;
    }
    case 'context:compressing':
      return 'Condensing earlier context';
    case 'llm:request':
      return 'Preparing the next model step';
    case 'llm:response': {
      const toolCallCount = typeof payload.toolCallCount === 'number' ? payload.toolCallCount : 0;
      const contentLength = typeof payload.contentLength === 'number' ? payload.contentLength : 0;
      if (toolCallCount > 0) return `Prepared ${toolCallCount} tool call${toolCallCount > 1 ? 's' : ''}`;
      if (contentLength > 0) return 'Started drafting the response';
      return 'Prepared an empty step';
    }
    case 'tool:executing':
      return `Using ${humanizeToolName(payload.toolName)}`;
    case 'tool:result': {
      const ok = payload.ok === true;
      const toolName = humanizeToolName(payload.toolName);
      return ok ? `Finished ${toolName}` : `Could not use ${toolName}`;
    }
    case 'turn:warning':
      return typeof payload.warning === 'string' ? payload.warning : 'Turn finished with a warning';
    case 'turn:complete':
      return 'Completed this turn';
    default:
      return null;
  }
}

function humanizeToolName(value: unknown): string {
  const raw = String(value ?? 'tool').trim();
  if (!raw) return 'tool';
  return raw.replace(/[_-]+/g, ' ');
}
