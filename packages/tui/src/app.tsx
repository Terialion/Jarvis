import type React from 'react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { execSync } from 'node:child_process';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { platform, arch, totalmem, freemem, uptime } from 'node:os';
import { REPL } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { AgentLoop, ConversationSummarizer } from '@jarvis/agent';
import { ToolRegistry, allBuiltinTools } from '@jarvis/tools';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import { SessionStore } from '@jarvis/store';
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

const REVIEW_PROMPT = `Review the uncommitted changes shown below. Focus on:
1. **Correctness** — logic errors, edge cases, off-by-one
2. **Security** — injection vectors, missing validation, leaked secrets
3. **Style** — consistency with surrounding code, naming

Be concise. Flag only real problems. Skip style nits that don't affect correctness.`;

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
];

function resolveSlashCommand(input: string): SlashCommandDef | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) return null;

  const parts = trimmed.slice(1).split(/\s+/);
  const name = parts[0]?.toLowerCase();
  const args = parts.slice(1);

  return SLASH_COMMANDS.find((c) => c.name === name) ?? null;
}

// ============================================================================
// Tool names that modify the filesystem
// ============================================================================

const FILE_MODIFYING_TOOLS = new Set(['write', 'edit', 'bash']);

function extractModifiedFiles(toolName: string, toolResult: string): string[] {
  const files: string[] = [];
  if (toolName === 'write' || toolName === 'edit') {
    // Tool results for write/edit include the file path in the result content
    const match = toolResult.match(/^\[(?:wrote|edited)\]\s+(.+)$/m);
    if (match) files.push(match[1].trim());
  }
  return files;
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
          projectDir: '.jarvis/skills',
        });
      }
      if (!executorRef.current) {
        executorRef.current = new SkillExecutor(skillsRef.current);
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
      });
    }
    return agentRef.current;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  const onSubmit = useCallback(async (prompt: string) => {
    // Check for slash commands
    const command = resolveSlashCommand(prompt);
    if (command) {
      const result = await command.handler([], {
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
      });
      setMessages((prev) => [...prev, makeSysMsg(result)]);
      return;
    }

    const userMsg: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

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

      for (const tr of result.toolResults) {
        content.push({
          type: 'tool_use',
          toolName: tr.name,
          input: '',
          result: tr.content.slice(0, 2000),
          status: tr.ok ? 'success' : 'error',
        });
      }

      if (result.answer) {
        content.push({
          type: 'text',
          text: result.answer,
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
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getAgent, options.model]);

  const statusSegments: StatusLineSegment[] = [
    { content: `model: ${modelRef.current}` },
  ];

  return (
    <REPL
      messages={messages}
      isLoading={isLoading}
      onSubmit={onSubmit}
      model={modelRef.current}
      statusSegments={statusSegments}
    />
  );
}
