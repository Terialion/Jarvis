import type React from 'react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { REPL } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { AgentLoop } from '@jarvis/agent';
import { ToolRegistry, allBuiltinTools } from '@jarvis/tools';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import { SessionStore } from '@jarvis/store';
import type { TUIOptions } from './types.js';
import type { ChatMessage } from '@jarvis/shared';

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
  }, [getAgent]);

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
