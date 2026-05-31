// ============================================================================
// send_message tool — send a message to another agent's mailbox
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

export const sendMessageSchema = toOpenAITool({
  name: 'send_message',
  description: 'Send a message to another agent. The target agent will receive it in its mailbox.',
  parameters: {
    type: 'object',
    properties: {
      target: {
        type: 'string',
        description: 'The agent ID to send to (e.g. "agent_abc123")',
      },
      message: {
        type: 'string',
        description: 'The message content',
      },
    },
    required: ['target', 'message'],
  },
});

export interface SendMessagePool {
  getMailbox(agentId: string): { deliver(senderId: string, message: string, triggerTurn?: boolean): void } | undefined;
  listAgents(): Array<{ agentId: string; status: string }>;
}

export function createSendMessageHandler(pool: SendMessagePool, currentAgentId: string): ToolHandler {
  return (args: Record<string, unknown>): string => {
    const target = String(args.target ?? '').trim();
    const message = String(args.message ?? '').trim();

    if (!target || !message) {
      return JSON.stringify({ error: 'Missing required parameters: target and message' });
    }

    // Check if target agent exists
    const agents = pool.listAgents();
    const exists = agents.some((a) => a.agentId === target);
    if (!exists) {
      return JSON.stringify({
        error: `Agent "${target}" not found. Active agents: ${agents.map((a) => a.agentId).join(', ') || '(none)'}`,
      });
    }

    const mailbox = pool.getMailbox(target);
    if (!mailbox) {
      return JSON.stringify({ error: `Agent "${target}" has no mailbox (may have completed)` });
    }

    mailbox.deliver(currentAgentId, message, false);

    return JSON.stringify({
      ok: true,
      target,
      message: `Message sent to ${target}`,
    });
  };
}

export function createSendMessageTool(pool: SendMessagePool, currentAgentId: string): ToolEntry {
  return {
    name: 'send_message',
    toolset: 'orchestration',
    schema: sendMessageSchema,
    handler: createSendMessageHandler(pool, currentAgentId),
    isAsync: false,
    emoji: '📨',
  };
}
