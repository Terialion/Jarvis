// ============================================================================
// report tool — subagent reports to its supervisor
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolHandler, ToolContext } from '@jarvis/tools';
import type { AgentMailbox } from '@jarvis/agent';
import type { AgentRegistry } from '../registry.js';

export interface ReportDeps {
  registry: AgentRegistry;
  senderId: string;
  getMailbox: (agentId: string) => AgentMailbox | undefined;
}

export function createReportHandler(deps: ReportDeps): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const summary = String(args.summary ?? '').trim();

    if (!summary) {
      return JSON.stringify({ error: 'Missing summary' });
    }

    const me = deps.registry.get(deps.senderId);
    if (!me || !me.parentId) {
      return JSON.stringify({ error: 'No supervisor to report to (this agent has no parent).' });
    }

    const supervisorMailbox = deps.getMailbox(me.parentId);
    if (!supervisorMailbox) {
      return JSON.stringify({ error: `Supervisor ${me.parentId} has no active mailbox.` });
    }

    supervisorMailbox.deliver(deps.senderId, `[Report]\n${summary}`, true);

    return JSON.stringify({
      ok: true,
      from: deps.senderId,
      to: me.parentId,
      message: 'Report delivered to supervisor',
    });
  };
}

export function createReportTool(deps: ReportDeps) {
  return {
    name: 'report',
    toolset: 'orchestration',
    schema: toOpenAITool({
      name: 'report',
      description: 'Report progress or completion to your supervisor agent.',
      parameters: {
        type: 'object',
        properties: {
          summary: { type: 'string', description: 'Summary of what you accomplished or current status' },
        },
        required: ['summary'],
      },
    }),
    handler: createReportHandler(deps),
    isAsync: false,
    emoji: '📋',
    maxResultSizeChars: 5000,
  };
}