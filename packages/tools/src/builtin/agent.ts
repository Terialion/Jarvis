// ============================================================================
// Agent tool — spawn subagents for complex, multi-step tasks
// Factory pattern: accepts a SubagentPool at creation time
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';

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
      const handle = pool.submit({
        agentId,
        agentType,
        task: `## ${description}\n\n${prompt}`,
        depth: 0,
      });

      activeAgents.set(agentId, { cancel: handle.cancel });

      if (runInBackground) {
        // Don't await — return immediately
        handle.completion
          .then(() => activeAgents.delete(agentId))
          .catch(() => activeAgents.delete(agentId));

        return JSON.stringify({
          agentId,
          status: handle.status,
          message: `Agent "${agentId}" started in background for task: ${description}`,
        });
      }

      // Foreground: wait for completion
      const result = await handle.completion;
      activeAgents.delete(agentId);

      return JSON.stringify({
        agentId: result.agentId,
        status: result.status,
        answer: result.answer ?? '',
        error: result.error ?? null,
        turnsUsed: result.turnsUsed ?? 0,
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
