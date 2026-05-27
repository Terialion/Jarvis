// ============================================================================
// Agent tool — spawn subagents for complex, multi-step tasks
// Factory pattern: accepts a SubagentPool at creation time
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';
import { getBackgroundTaskRegistry } from './task.js';

// ---- minimal pool interface (avoids coupling to @jarvis/subagents) ----

export interface AgentPool {
  submit(config: {
    agentId: string;
    agentType: 'explore' | 'plan' | 'general';
    task: string;
    budgetSteps?: number;
    depth?: number;
  }): {
    agentId: string;
    status: string;
    completion: Promise<{ agentId: string; status: string; answer?: string; error?: string; turnsUsed?: number }>;
    cancel: () => void;
  };
}

// ---- schema ----

export const agentSchema = toOpenAITool({
  name: 'Agent',
  description:
    'Launch a new agent to handle complex, multi-step tasks. Available agent types: explore (read-only search), plan (explore + task tools), general (all tools). Use for parallel independent work or isolating context-heavy research.',
  parameters: {
    type: 'object',
    properties: {
      description: {
        type: 'string',
        description: 'A short (3-5 word) description of the task',
      },
      prompt: {
        type: 'string',
        description: 'The task for the agent to perform',
      },
      subagent_type: {
        type: 'string',
        enum: ['explore', 'plan', 'general'],
        default: 'general',
        description: 'Agent type: explore (read/search only), plan (explore + task tools), general (all tools)',
      },
      run_in_background: {
        type: 'boolean',
        default: false,
        description: 'Set to true to run in background. You will be notified when it completes.',
      },
    },
    required: ['description', 'prompt'],
  },
});

// ---- factory ----

export function createAgentHandler(pool: AgentPool): ToolHandler {
  const activeAgents = new Map<string, { cancel: () => void }>();

  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const description = String(args.description ?? '').trim();
    const prompt = String(args.prompt ?? '').trim();
    const agentType = (['explore', 'plan', 'general'] as const).includes(args.subagent_type as never)
      ? (args.subagent_type as 'explore' | 'plan' | 'general')
      : 'general';
    const runInBackground = args.run_in_background === true;

    if (!description || !prompt) {
      return JSON.stringify({ error: 'Missing required parameters: description and prompt' });
    }

    const agentId = `agent_${crypto.randomUUID().slice(0, 8)}`;

    try {
      const depth = typeof args.depth === 'number' ? args.depth : 1;

      const handle = pool.submit({
        agentId,
        agentType,
        task: `## ${description}\n\n${prompt}`,
        depth,
      });

      activeAgents.set(agentId, { cancel: handle.cancel });

      // Default: async spawn — return immediately, results arrive via mailbox
      // When runInBackground=true, also register with background task tracker

      if (runInBackground) {
        const bgRegistry = getBackgroundTaskRegistry();
        const bgCompletion = handle.completion.then((result) => ({
          result: JSON.stringify({ agentId: result.agentId, status: result.status, answer: result.answer ?? '', error: result.error ?? null, turnsUsed: result.turnsUsed ?? 0 }),
        }));
        const origCancel = handle.cancel.bind(handle);
        bgRegistry.register({
          type: 'agent',
          status: 'running',
          description: `Agent: ${description}`,
          promise: bgCompletion,
          cancel: () => { activeAgents.delete(agentId); origCancel(); },
        });
      }

      // Always async — results flow back via mailbox at next turn
      handle.completion.then(() => activeAgents.delete(agentId)).catch(() => activeAgents.delete(agentId));

      return JSON.stringify({
        agentId,
        status: 'spawned',
        message: `Agent "${agentId}" spawned asynchronously for: ${description}. Results will arrive in your mailbox when complete. Use list_agents to check status.`,
      });
    } catch (err) {
      activeAgents.delete(agentId);
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `Agent spawn failed: ${message}` });
    }
  };
}

export function createAgentTool(pool: AgentPool): ToolEntry {
  return {
    name: 'Agent',
    toolset: 'orchestration',
    schema: agentSchema,
    handler: createAgentHandler(pool),
    isAsync: true,
    emoji: '🤖',
    maxResultSizeChars: 50_000,
  };
}
