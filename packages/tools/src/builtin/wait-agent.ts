// ============================================================================
// wait_agent tool — wait for a specific agent to complete
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

export const waitAgentSchema = toOpenAITool({
  name: 'wait_agent',
  description: 'Wait for a specific agent to complete and get its result.',
  parameters: {
    type: 'object',
    properties: {
      target: {
        type: 'string',
        description: 'The agent ID to wait for (e.g. "agent_abc123")',
      },
      timeout_ms: {
        type: 'number',
        description: 'Maximum time to wait in milliseconds (default: 120000)',
        default: 120000,
      },
    },
    required: ['target'],
  },
});

export interface WaitAgentPool {
  waitAgent(agentId: string, timeoutMs?: number): Promise<{ agentId: string; status: string; answer?: string; error?: string }>;
  listAgents(): Array<{ agentId: string; status: string }>;
}

export function createWaitAgentHandler(pool: WaitAgentPool): ToolHandler {
  return async (args: Record<string, unknown>): Promise<string> => {
    const target = String(args.target ?? '').trim();
    const timeoutMs = typeof args.timeout_ms === 'number' ? args.timeout_ms : 120000;

    if (!target) {
      return JSON.stringify({ error: 'Missing required parameter: target' });
    }

    // Check if target exists
    const agents = pool.listAgents();
    const exists = agents.some((a) => a.agentId === target);
    if (!exists) {
      return JSON.stringify({
        error: `Agent "${target}" not found. Active agents: ${agents.map((a) => a.agentId).join(', ') || '(none)'}`,
      });
    }

    try {
      const result = await pool.waitAgent(target, timeoutMs);
      return JSON.stringify({
        agentId: result.agentId,
        status: result.status,
        answer: result.answer ?? null,
        error: result.error ?? null,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `wait_agent failed: ${message}` });
    }
  };
}

export function createWaitAgentTool(pool: WaitAgentPool): ToolEntry {
  return {
    name: 'wait_agent',
    toolset: 'orchestration',
    schema: waitAgentSchema,
    handler: createWaitAgentHandler(pool),
    isAsync: true,
    emoji: '⏳',
    maxResultSizeChars: 50_000,
  };
}
