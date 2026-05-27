// ============================================================================
// redirect_agent tool — redirect a running agent to a new task
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolHandler, ToolContext } from '@jarvis/tools';
import type { AgentLoop } from '@jarvis/agent';

export interface RedirectDeps {
  getAgentLoop: (agentId: string) => AgentLoop | undefined;
}

export function createRedirectAgentHandler(deps: RedirectDeps): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const agentId = String(args.agentId ?? '').trim();
    const newTask = String(args.task ?? '').trim();

    if (!agentId) return JSON.stringify({ error: 'Missing agentId' });
    if (!newTask) return JSON.stringify({ error: 'Missing task' });

    const loop = deps.getAgentLoop(agentId);
    if (!loop) {
      return JSON.stringify({ error: `Agent "${agentId}" not found or not controllable.` });
    }
    loop.redirect(newTask);
    return JSON.stringify({
      ok: true, agentId, action: 'redirected',
      message: `Agent "${agentId}" redirected to new task.`,
    });
  };
}

export function createRedirectAgentTool(deps: RedirectDeps) {
  return {
    name: 'redirect_agent',
    toolset: 'orchestration',
    schema: toOpenAITool({
      name: 'redirect_agent',
      description: 'Redirect a running agent to a new task. The agent stops current work and starts the new task.',
      parameters: {
        type: 'object',
        properties: {
          agentId: { type: 'string', description: 'The agent ID to redirect' },
          task: { type: 'string', description: 'The new task for the agent' },
        },
        required: ['agentId', 'task'],
      },
    }),
    handler: createRedirectAgentHandler(deps),
    isAsync: false,
    emoji: '🔄',
    maxResultSizeChars: 2000,
  };
}