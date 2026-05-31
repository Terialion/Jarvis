// ============================================================================
// list_agents tool — list all active agents and their status
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

export const listAgentsSchema = toOpenAITool({
  name: 'list_agents',
  description: 'List all active agents and their current status.',
  parameters: {
    type: 'object',
    properties: {},
  },
});

export interface ListAgentsPool {
  listAgents(): Array<{ agentId: string; status: string }>;
  getActiveCount(): number;
}

export function createListAgentsHandler(pool: ListAgentsPool): ToolHandler {
  return (): string => {
    const agents = pool.listAgents();
    const activeCount = pool.getActiveCount();

    return JSON.stringify({
      agents: agents.map((a) => ({
        agentId: a.agentId,
        status: a.status,
      })),
      activeCount,
      totalCount: agents.length,
    });
  };
}

export function createListAgentsTool(pool: ListAgentsPool): ToolEntry {
  return {
    name: 'list_agents',
    toolset: 'orchestration',
    schema: listAgentsSchema,
    handler: createListAgentsHandler(pool),
    isAsync: false,
    emoji: '📋',
  };
}
