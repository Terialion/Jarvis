// ============================================================================
// list_agents tool — view organization members
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolHandler, ToolContext } from '@jarvis/tools';
import type { AgentRegistry } from '../registry.js';

export interface ListAgentsDeps {
  registry: AgentRegistry;
  selfId: string;
}

export function createListAgentsHandler(deps: ListAgentsDeps): ToolHandler {
  return async (_args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const all = deps.registry.listAll();

    const entries = all.map((a) => ({
      agentId: a.agentId,
      role: a.role,
      depth: a.depth,
      parentId: a.parentId,
      isSelf: a.agentId === deps.selfId,
    }));

    const byParent = new Map<string | null, typeof entries>();
    for (const e of entries) {
      const key = e.parentId;
      if (!byParent.has(key)) byParent.set(key, []);
      byParent.get(key)!.push(e);
    }

    function formatTree(parentId: string | null, indent: string): string[] {
      const children = byParent.get(parentId) || [];
      const lines: string[] = [];
      for (const child of children) {
        const marker = child.isSelf ? ' *' : '  ';
        lines.push(`${indent}${marker} ${child.agentId} (${child.role}, depth=${child.depth})`);
        lines.push(...formatTree(child.agentId, indent + '    '));
      }
      return lines;
    }

    const tree = formatTree(null, '');

    return JSON.stringify({
      count: entries.length,
      agents: entries,
      tree: tree.join('\n'),
    });
  };
}

export function createListAgentsTool(deps: ListAgentsDeps) {
  return {
    name: 'list_agents',
    toolset: 'orchestration',
    schema: toOpenAITool({
      name: 'list_agents',
      description: 'List all agents in the current organization, including their roles and relationships.',
      parameters: {
        type: 'object',
        properties: {},
        required: [],
      },
    }),
    handler: createListAgentsHandler(deps),
    isAsync: false,
    emoji: '📊',
    maxResultSizeChars: 20_000,
  };
}