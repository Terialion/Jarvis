import type React from 'react';
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { execSync } from 'node:child_process';
import { readFileSync, existsSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { platform, arch, totalmem, freemem, uptime } from 'node:os';
import { REPL } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { AgentLoop, ConversationSummarizer, TokenTracker, formatTokensCompact } from '@jarvis/agent';
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
import type { TUIOptions } from './types.js';
import type { ChatMessage } from '@jarvis/shared';

// ============================================================================
// Slash command definitions
// ============================================================================

interface SlashCommandCtx {
  store: SessionStore | null;
  sid: string | null;
  historyRef: React.MutableRefObject<ChatMessage[]>;
  messages: Message[];
  setMessages: (v: Message[] | ((prev: Message[]) => Message[])) => void;
  setIsLoading: (v: boolean) => void;
  cwd: string;
  modelRef: React.MutableRefObject<string>;
  modifiedFilesRef: React.MutableRefObject<Set<string>>;
  getAgent: () => AgentLoop;
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
    id: `cmd_${Date.now()}`,
    role: 'assistant',
    content: [{ type: 'text', text: msg } as MessageContent],
    timestamp: Date.now(),
  };
}

const TASK_TOOLS = new Set(['task_create', 'task_update', 'task_list']);

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
      if (!ctx.store) return 'Session store not available.';
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
      return lines.length > 0
        ? `Sessions (recent first, * = current):\n\n${lines.join('\n')}`
        : 'No sessions found.';
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
        return `Model set to: ${args[0]} (effective on next turn)`;
      }
      return `Current model: ${ctx.modelRef.current}`;
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
      if (args.length === 0) {
        const modelName = ctx.modelRef.current;
        const outputStyle = ctx.outputStyleRef.current;
        const sid = (ctx.sid ?? 'none').slice(-16);
        return [
          'Current configuration:\n',
          `  model       = ${modelName}`,
          `  max-turns   = ${ctx.maxTurns}`,
          `  output-style = ${outputStyle}`,
          `  session     = ${sid}`,
          `  cwd         = ${ctx.cwd}`,
        ].join('\n');
      }

      const key = args[0].toLowerCase();
      const value = args[1];

      if (key === 'model') {
        if (!value) return `model = ${ctx.modelRef.current}`;
        ctx.modelRef.current = value;
        return `model = ${value} (effective next turn)`;
      }

      if (key === 'output-style') {
        if (!value) return `output-style = ${ctx.outputStyleRef.current}`;
        if (!['default', 'concise', 'verbose'].includes(value)) {
          return `Invalid style. Options: default, concise, verbose`;
        }
        ctx.outputStyleRef.current = value;
        return `output-style = ${value}`;
      }

      if (key === 'max-turns') {
        if (!value) return `max-turns = ${ctx.maxTurns}`;
        return 'max-turns is read-only during a session.';
      }

      return `Unknown config key: ${key}. Available: model, output-style, max-turns`;
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
      return `Permission mode set to: ${mode}`;
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
): REPLCommandDef[] {
  return SLASH_COMMANDS.map((cmd) => ({
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
  const [isLoading, setIsLoading] = useState(false);
  const agentRef = useRef<AgentLoop | null>(null);
  const historyRef = useRef<ChatMessage[]>([]);
  const toolsRef = useRef<ToolRegistry | null>(null);
  const skillsRef = useRef<SkillRegistry | null>(null);
  const executorRef = useRef<SkillExecutor | null>(null);
  const sessionStoreRef = useRef<SessionStore | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionReadyRef = useRef(false);
  const modelRef = useRef<string>(options.model);
  const modifiedFilesRef = useRef<Set<string>>(new Set());
  const outputStyleRef = useRef<string>('default');
  const permissionModeRef = useRef<string>('workspace_write');
  const poolRef = useRef<SubagentPool | null>(null);
  const mcpRef = useRef<MCPClient | null>(null);
  const tokenTrackerRef = useRef<TokenTracker | null>(null);
  const elapsedRef = useRef<number>(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // AskUserQuestion bridge state
  const [askQuestions, setAskQuestions] = useState<AskQuestionDef[] | null>(null);
  const askResolveRef = useRef<((answers: Record<string, string>) => void) | null>(null);
  const askRejectRef = useRef<((err: Error) => void) | null>(null);

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

      // Subagent pool — wire Agent tool
      if (!poolRef.current) {
        poolRef.current = new SubagentPool();
        const provider = new LLMProvider({
          model: modelRef.current,
          apiKey: options.apiKey,
          baseURL: options.baseURL,
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
              apiKey: options.apiKey,
              baseURL: options.baseURL,
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
        tokenTrackerRef.current = new TokenTracker(
          provider.contextWindow,
        );
      }
      agentRef.current = new AgentLoop({
        model: {
          model: modelRef.current,
          apiKey: options.apiKey,
          baseURL: options.baseURL,
        },
        maxTurns: options.maxTurns,
        systemPrompt: options.systemPrompt,
        tools,
        skillRegistry: skillsRef.current,
        skillExecutor: executorRef.current,
        tokenTracker: tokenTrackerRef.current,
      });
    }
    return agentRef.current;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  const onSubmit = useCallback(async (prompt: string) => {
    const userMsg: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    // Start elapsed timer
    const startTime = Date.now();
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    elapsedRef.current = 0;
    elapsedTimerRef.current = setInterval(() => {
      elapsedRef.current = Date.now() - startTime;
    }, 1000);

    try {
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

      const content: MessageContent[] = [];

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
          content.push(parsed);
        } else {
          content.push({
            type: 'tool_use',
            toolName: tr.name,
            input: '',
            result: tr.content.slice(0, 2000),
            status: tr.ok ? 'success' : 'error',
          });
        }
      }

      if (result.answer) {
        content.push({
          type: 'text',
          text: result.answer,
        });
      }

      // Append file change summary if any files were modified
      if (fileChanges.length > 0) {
        content.push({
          type: 'diff',
          filename: `Changes (${fileChanges.length} file${fileChanges.length > 1 ? 's' : ''})`,
          diff: formatFileChangeSummary(fileChanges),
        });
      }

      const assistantMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content:
          content.length === 1 && content[0].type === 'text'
            ? (content[0] as { type: 'text'; text: string }).text
            : content,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

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
      const errMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: [
          {
            type: 'error',
            message: err instanceof Error ? err.message : String(err),
          },
        ],
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
      // Stop elapsed timer
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getAgent, options.model]);

  const replCommands: REPLCommandDef[] = useMemo(
    () =>
      buildReplCommands(
        {
          store: sessionStoreRef.current,
          sid: sessionIdRef.current,
          historyRef,
          messages,
          setMessages,
          setIsLoading,
          cwd: process.cwd(),
          modelRef,
          modifiedFilesRef,
          getAgent,
          maxTurns: options.maxTurns,
          outputStyleRef,
          permissionModeRef,
        },
        setMessages,
      ),
    // Rebuild only when getAgent changes (lazy init via useCallback)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [getAgent, options.maxTurns, messages],
  );

  const statusSegments: StatusLineSegment[] = useMemo(() => {
    const segs: StatusLineSegment[] = [];
    // Model name
    segs.push({ content: `model: ${modelRef.current}` });

    // Token + context info (updated after each turn)
    const tracker = tokenTrackerRef.current;
    if (tracker && tracker.turnCount > 0) {
      const blended = tracker.totalBlended;
      const pct = tracker.contextPercentRemaining;
      segs.push({
        content: `${formatTokensCompact(blended)} tokens (${pct}% left)`,
      });
    }

    // Elapsed time
    if (elapsedRef.current > 0) {
      const secs = Math.floor(elapsedRef.current / 1000);
      if (secs < 60) {
        segs.push({ content: `${secs}s` });
      } else if (secs < 3600) {
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        segs.push({ content: `${m}m ${s.toString().padStart(2, '0')}s` });
      } else {
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        segs.push({ content: `${h}h ${m}m` });
      }
    }

    return segs;
  }, [messages.length, modelRef.current]);

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

  const askUserQuestion = askQuestions
    ? { questions: askQuestions, onSubmit: handleAskSubmit, onCancel: handleAskCancel }
    : undefined;

  return (
    <REPL
      messages={messages}
      isLoading={isLoading}
      onSubmit={onSubmit}
      model={modelRef.current}
      statusSegments={statusSegments}
      commands={replCommands}
      askUserQuestion={askUserQuestion}
    />
  );
}
