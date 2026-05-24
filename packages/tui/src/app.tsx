import type React from 'react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { execSync } from 'node:child_process';
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

interface SlashCommandDef {
  name: string;
  description: string;
  usage?: string;
  handler: (args: string[], ctx: {
    store: SessionStore | null;
    sid: string | null;
    historyRef: React.MutableRefObject<ChatMessage[]>;
    messages: Message[];
    setMessages: (v: Message[] | ((prev: Message[]) => Message[])) => void;
    cwd: string;
    model: string;
  }) => string | Promise<string>;
}

function makeCommand(msg: string): Message {
  return {
    id: `cmd_${Date.now()}`,
    role: 'assistant',
    content: [{ type: 'text', text: msg } as MessageContent],
    timestamp: Date.now(),
  };
}

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
      ctx.setMessages([]);
      // Create new session so cleared history isn't resumed
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
      return [
        `Session: ${shortSid}`,
        `Model: ${ctx.model}`,
        `Messages: ${msgCount}`,
        `Estimated tokens: ${estTokens.toLocaleString()}`,
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

      // Keep the last user+assistant exchange, replace older history with summary
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
          model: options.model,
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
  }, [options]);

  const onSubmit = useCallback(async (prompt: string) => {
    // Check for slash commands
    const command = resolveSlashCommand(prompt);
    if (command) {
      const result = await command.handler(command.usage?.split(' ')?.slice(1) ?? [], {
        store: sessionStoreRef.current,
        sid: sessionIdRef.current,
        historyRef,
        messages,
        setMessages,
        cwd: process.cwd(),
        model: options.model,
      });
      setMessages((prev) => [...prev, makeCommand(result)]);
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
  }, [getAgent, messages, options.model]);

  const statusSegments: StatusLineSegment[] = [
    { content: `model: ${options.model}` },
  ];

  return (
    <REPL
      messages={messages}
      isLoading={isLoading}
      onSubmit={onSubmit}
      model={options.model}
      statusSegments={statusSegments}
    />
  );
}
