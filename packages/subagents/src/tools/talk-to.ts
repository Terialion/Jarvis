// ============================================================================
// talk_to tool — agent-to-agent point-to-point communication
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolHandler, ToolContext } from '@jarvis/tools';
import type { AgentRegistry } from '../registry.js';
import type { SubagentPool } from '../pool.js';

export interface TalkToDeps {
  registry: AgentRegistry;
  pool: SubagentPool;
  senderId: string;
}

export function createTalkToHandler(deps: TalkToDeps): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const targetId = String(args.targetId ?? args.agentId ?? '').trim();
    const message = String(args.message ?? '').trim();

    if (!targetId) {
      return JSON.stringify({ error: 'Missing targetId — specify which agent to talk to' });
    }
    if (!message) {
      return JSON.stringify({ error: 'Missing message' });
    }

    const target = deps.registry.get(targetId);
    if (!target) {
      return JSON.stringify({ error: `Agent "${targetId}" not found. Use list_agents to see available agents.` });
    }

    const targetMailbox = deps.pool.getMailbox(targetId);
    if (!targetMailbox) {
      return JSON.stringify({ error: `Agent "${targetId}" has no active mailbox (may have already completed).` });
    }

    targetMailbox.deliver(deps.senderId, message, true);

    return JSON.stringify({
      ok: true,
      from: deps.senderId,
      to: targetId,
      message: `Message delivered to ${targetId}`,
    });
  };
}

export function createTalkToTool(deps: TalkToDeps) {
  return {
    name: 'talk_to',
    toolset: 'orchestration',
    schema: toOpenAITool({
      name: 'talk_to',
      description: 'Send a message to another agent. The recipient will see it at the start of their next turn. Use list_agents first to find available agents.',
      parameters: {
        type: 'object',
        properties: {
          targetId: { type: 'string', description: 'The agent ID to send the message to' },
          message: { type: 'string', description: 'The message to send' },
        },
        required: ['targetId', 'message'],
      },
    }),
    handler: createTalkToHandler(deps),
    isAsync: false,
    emoji: '💬',
    maxResultSizeChars: 5000,
  };
}