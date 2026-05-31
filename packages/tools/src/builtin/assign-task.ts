// ============================================================================
// assign_task tool — assign a new task to an existing agent
// ============================================================================
//
// Sends a task message to an agent's mailbox. The agent will pick it up
// on its next turn (if it has mailbox polling enabled).

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import type { SendMessagePool } from './send-message.js';

export const assignTaskSchema = toOpenAITool({
  name: 'assign_task',
  description: 'Assign a new task to an existing agent. The agent will receive it as a message.',
  parameters: {
    type: 'object',
    properties: {
      target: {
        type: 'string',
        description: 'The agent ID to assign the task to',
      },
      task: {
        type: 'string',
        description: 'The task description',
      },
    },
    required: ['target', 'task'],
  },
});

export function createAssignTaskHandler(pool: SendMessagePool, currentAgentId: string): ToolHandler {
  return (args: Record<string, unknown>): string => {
    const target = String(args.target ?? '').trim();
    const task = String(args.task ?? '').trim();

    if (!target || !task) {
      return JSON.stringify({ error: 'Missing required parameters: target and task' });
    }

    // Check if target exists
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

    mailbox.deliver(currentAgentId, `[NEW TASK]\n${task}`, true);

    return JSON.stringify({
      ok: true,
      target,
      message: `Task assigned to ${target}`,
    });
  };
}

export function createAssignTaskTool(pool: SendMessagePool, currentAgentId: string): ToolEntry {
  return {
    name: 'assign_task',
    toolset: 'orchestration',
    schema: assignTaskSchema,
    handler: createAssignTaskHandler(pool, currentAgentId),
    isAsync: false,
    emoji: '📌',
  };
}
