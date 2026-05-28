import type React from 'react';
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { execSync } from 'node:child_process';
import { readFileSync, existsSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { platform, arch, totalmem, freemem, uptime } from 'node:os';
import { REPL } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { WelcomeScreen } from './vendor/ui/WelcomeScreen.js';
import { loadSettings, saveSettings, type UserSettings } from './settings-store.js';
import { AgentLoop, AgentEventBus, ConversationSummarizer, TokenTracker, parseModelName, type ThreadEvent } from '@jarvis/agent';
import {
  ToolRegistry,
  allBuiltinTools,
  setAskUserQuestionBridge,
  createSkillLoadTool,
  createSkillTool,
  createAgentTool,
  createListMcpResourcesTool,
  createReadMcpResourceTool,
  createMcpToolEntries,
} from '@jarvis/tools';
import type { AskQuestionDef } from '@jarvis/tools';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import { SessionStore } from '@jarvis/store';
import { SubagentPool, toolWhitelistForType, type SubagentConfig } from '@jarvis/subagents';
import { MCPClient } from '@jarvis/mcp';
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
} from '@jarvis/shared';
import { formatToolLine } from './vendor/ui/tool-display.js';
import { buildStatusSegments } from './status-segments.js';
import type { CodexTaskSnapshot } from './presentation/codex-timeline-state.js';

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
}

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
    usage: '/context',
    handler: (_args, ctx) => {
      const msgCount = ctx.historyRef.current.length;
      const totalChars = ctx.historyRef.current.reduce((sum, m) => sum + m.content.length, 0);
      const estTokens = Math.ceil(totalChars / 4);
      const shortSid = (ctx.sid ?? 'none').slice(-16);
      const modFiles = ctx.modifiedFilesRef.current.size;
      return [
        `Session: ${shortSid}`,
        `Model: ${ctx.modelRef.current}`,
        `Messages: ${msgCount}`,
        `Estimated tokens: ${estTokens.toLocaleString()}`,
        `Modified files: ${modFiles}`,
        `UI messages: ${ctx.messages.length}`,
      ].join('\n');
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
    description: 'Show or set the current model',
    usage: '/model [model-name]',
    handler: (args, ctx) => {
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
        const result = await agent.run(prompt, []);
        return result.answer || 'Review complete (no text response).';
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
        return [
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
          '',
          'Stored user config:',
          `  model       = ${userConfig.model ?? '(not set)'}`,
          `  base-url    = ${userConfig.base_url ?? '(not set)'}`,
          `  api-key     = ${maskSecret(userConfig.api_key)}`,
          `  effort      = ${userConfig.reasoning_effort ?? '(not set)'}`,
          `  max-turns   = ${userConfig.max_turns ?? '(not set)'}`,
          `  output-style = ${userConfig.output_style ?? '(not set)'}`,
          `  permissions = ${userConfig.permission_mode ?? '(not set)'}`,
          `  system-prompt = ${userConfig.system_prompt ? '(configured)' : '(not set)'}`,
        ].join('\n');
      }

      const key = args[0].toLowerCase();
      const value = args.slice(1).join(' ').trim();

      if (key === 'model') {
        if (!value) return `model = ${ctx.modelRef.current}`;
        ctx.modelRef.current = value;
        saveSettings({ model: value });
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
        const result = await agent.run(prompt, []);
        return result.answer || 'Security review complete (no text response).';
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
): REPLCommandDef[] {
  const builtins = SLASH_COMMANDS.map((cmd) => ({
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
  }));

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

// ============================================================================
// App
// ============================================================================

export function App({ options }: { options: TUIOptions }): React.ReactNode {
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadEvents, setThreadEvents] = useState<ThreadEvent[]>([]);
  const [codexTaskSnapshots, setCodexTaskSnapshots] = useState<CodexTaskSnapshot[]>([]);
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
  const modelRef = useRef<string>(savedSettings.model || options.model);
  const apiKeyRef = useRef<string | undefined>(options.apiKey);
  const baseURLRef = useRef<string | undefined>(options.baseURL);
  const reasoningEffortRef = useRef<string>(savedSettings.reasoning_effort || options.reasoningEffort || 'high');
  const systemPromptRef = useRef<string | undefined>(options.systemPrompt);
  const modifiedFilesRef = useRef<Set<string>>(new Set());
  const outputStyleRef = useRef<string>(savedSettings.output_style || 'default');
  const permissionModeRef = useRef<string>(savedSettings.permission_mode || 'workspace_write');
  const poolRef = useRef<SubagentPool | null>(null);
  const mcpRef = useRef<MCPClient | null>(null);
  const tokenTrackerRef = useRef<TokenTracker | null>(null);
  const elapsedRef = useRef<number>(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const taskCountRef = useRef<{ pending: number; in_progress: number; completed: number }>({ pending: 0, in_progress: 0, completed: 0 });
  const abortRef = useRef<AbortController | null>(null);

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

      const tools = new ToolRegistry();
      for (const tool of allBuiltinTools) {
        tools.register(tool);
      }
      toolsRef.current = tools;

      if (!skillsRef.current) {
        skillsRef.current = new SkillRegistry();
        skillsRef.current.discover({
          builtinDir: 'skills',
          projectDir: '.jarvis/skills',
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

          const result = await subLoop.run(config.task);
          return {
            agentId: config.agentId,
            status: 'completed' as const,
            answer: result.answer,
            turnsUsed: result.turnsUsed,
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
    setSpinnerVerb(undefined);
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
      const prevLen = historyRef.current.length;
      const result = await agent.run(prompt, historyRef.current);

      // Track files modified by this turn
      for (const tr of result.toolResults) {
        if (FILE_MODIFYING_TOOLS.has(tr.name)) {
          const files = extractModifiedFiles(tr.name, tr.content);
          for (const f of files) {
            modifiedFilesRef.current.add(f);
          }
        }
      }

      // Drain and commit any remaining streaming text BEFORE building
      // the final message (so we know if text was already committed)
      const committedStreamingText = drainAndCommit();
      const normalizedCommittedText = committedStreamingText?.trim() ?? '';
      const finalAnswer = typeof result.answer === 'string' ? result.answer.trim() : '';

      const content: MessageContent[] = [];
      let taskSnapshot: CodexTaskSnapshot | null = null;

      // Show reasoning as a collapsible thinking block
      if ('reasoning' in result && typeof result.reasoning === 'string' && result.reasoning) {
        content.push({
          type: 'thinking',
          text: result.reasoning,
        });
      }

      // Collect file changes for summary display
      const fileChanges: FileChange[] = [];
      for (const tr of result.toolResults) {
        const change = computeFileChange(tr.name, tr.content);
        if (change) fileChanges.push(change);

        const parsed = parseToolContent(tr.name, tr.content);
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
        content.push({ type: 'text', text: result.answer });
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

      const stats = runStatsRef.current;
      const reasoningText = typeof result.reasoning === 'string' ? result.reasoning : '';
      const liveStreamingText = streamingContentRef.current ?? '';
      const committedText = committedStreamingText ?? '';
      emitDebugEvent({
        type: 'run_completed',
        prompt,
        elapsedMs: Date.now() - turnStartedAt,
        finalAnswerLength: result.answer.length,
        finalAnswerPreview: result.answer.slice(0, 200),
        finalAnswerTail: result.answer.slice(-200),
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
        turnsUsed: result.turnsUsed,
        toolResults: result.toolResults.map((toolResult) => ({
          name: toolResult.name,
          ok: toolResult.ok,
          contentLength: toolResult.content.length,
          error: toolResult.error,
        })),
        newMessageCount: result.messages.length - prevLen,
        timestamp: Date.now(),
      });

      // Persist new messages from this turn to SessionStore
      historyRef.current = result.messages;
      const newMsgs = result.messages.slice(prevLen);
      const store = sessionStoreRef.current;
      const sid = sessionIdRef.current;
      if (store && sid) {
        for (const msg of newMsgs) {
          const meta = { ...(msg.metadata ?? {}) };
          if (msg.name) meta['_name'] = msg.name;
          store.appendMessage(sid, msg.role, msg.content, {
            turnId: result.turnId,
            toolCallId: msg.toolCallId,
            metadata: Object.keys(meta).length > 0 ? meta : undefined,
          });
        }
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
        },
        setMessages,
        skillsRef.current,
      ),
    // Rebuild only when getAgent changes (lazy init via useCallback)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [getAgent, invalidateAgent, options.maxTurns, messages],
  );

  const statusSegments: StatusLineSegment[] = useMemo(() => {
    const tracker = tokenTrackerRef.current;
    return buildStatusSegments({
      cwd,
      model: parseModelName(modelRef.current).cleanName,
      gitBranch,
      isLoading,
      hasQuestion: askQuestions !== null,
      totalTokens: tracker?.turnCount ? tracker.totalBlended : undefined,
      contextPercentRemaining: tracker?.turnCount ? tracker.contextPercentRemaining : undefined,
      taskCounts: taskCountRef.current,
      elapsedMs,
      sessionId: sessionIdRef.current,
    });
  }, [askQuestions, cwd, elapsedMs, gitBranch, isLoading, messages.length, modelRef.current]);

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
      commands={replCommands}
      askUserQuestion={askUserQuestion}
      spinnerTokenCount={tokenTrackerRef.current?.totalBlended}
      spinnerVerb={spinnerVerb}
      spinnerStatus={spinnerStatus}
      spinnerDetails={spinnerDetails}
      spinnerRunning={spinnerRunning}
      spinnerCompleted={spinnerCompleted}
      agents={agentEntries}
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
