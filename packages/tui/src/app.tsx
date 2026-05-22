import type React from 'react';
import { useState, useCallback, useRef } from 'react';
import { REPL } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { AgentLoop } from '@jarvis/agent';
import { ToolRegistry, allBuiltinTools } from '@jarvis/tools';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
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

  const getAgent = useCallback((): AgentLoop => {
    if (!agentRef.current) {
      const tools = new ToolRegistry();
      for (const tool of allBuiltinTools) {
        tools.register(tool);
      }
      toolsRef.current = tools;

      if (!skillsRef.current) {
        skillsRef.current = new SkillRegistry();
        // Discover project skills from .jarvis/skills/
        // In TUI context, use process.cwd() to find project root
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
      const result = await agent.run(prompt, historyRef.current);

      const content: MessageContent[] = [];

      // Tool results as tool_use blocks
      for (const tr of result.toolResults) {
        content.push({
          type: 'tool_use',
          toolName: tr.name,
          input: '',
          result: tr.content.slice(0, 2000),
          status: tr.ok ? 'success' : 'error',
        });
      }

      // Final answer
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
