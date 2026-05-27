// ============================================================================
// pause_agent / resume_agent tools
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolHandler, ToolContext } from '@jarvis/tools';
import type { AgentLoop } from '@jarvis/agent';

export interface PauseResumeDeps {
  getAgentLoop: (agentId: string) => AgentLoop | undefined;
}

export function createPauseAgentHandler(deps: PauseResumeDeps): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const agentId = String(args.agentId ?? '').trim();
    if (!agentId) {
      return JSON.stringify({ error: 'Missing agentId' });
    }
    const loop = deps.getAgentLoop(agentId);
    if (!loop) {
      return JSON.stringify({ error: `Agent "${agentId}" not found or not controllable.` });
    }
    loop.pause();
    return JSON.stringify({
      ok: true, agentId, action: 'paused',
      message: `Agent "${agentId}" paused.`,
    });
  };
}

export function createPauseAgentTool(deps: PauseResumeDeps) {
  return {
    name: 'pause_agent',
    toolset: 'orchestration',
    schema: toOpenAITool({
      name: 'pause_agent',
      description: 'Pause a running agent at the next step boundary.',
      parameters: {
        type: 'object',
        properties: { agentId: { type: 'string', description: 'The agent ID to pause' } },
        required: ['agentId'],
      },
    }),
    handler: createPauseAgentHandler(deps),
    isAsync: false,
    emoji: '⏸️',
    maxResultSizeChars: 2000,
  };
}

export function createResumeAgentHandler(deps: PauseResumeDeps): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const agentId = String(args.agentId ?? '').trim();
    if (!agentId) {
      return JSON.stringify({ error: 'Missing agentId' });
    }
    const loop = deps.getAgentLoop(agentId);
    if (!loop) {
      return JSON.stringify({ error: `Agent "${agentId}" not found or not controllable.` });
    }
    loop.resume();
    return JSON.stringify({
      ok: true, agentId, action: 'resumed',
      message: `Agent "${agentId}" resumed.`,
    });
  };
}

export function createResumeAgentTool(deps: PauseResumeDeps) {
  return {
    name: 'resume_agent',
    toolset: 'orchestration',
    schema: toOpenAITool({
      name: 'resume_agent',
      description: 'Resume a paused agent.',
      parameters: {
        type: 'object',
        properties: { agentId: { type: 'string', description: 'The agent ID to resume' } },
        required: ['agentId'],
      },
    }),
    handler: createResumeAgentHandler(deps),
    isAsync: false,
    emoji: '▶️',
    maxResultSizeChars: 2000,
  };
}