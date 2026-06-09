// ============================================================================
// spawn_agent tool — create and run a new subagent (Hermes + Codex pattern)
// ============================================================================

import type { ToolHandler, ToolContext } from '@jarvis/tools';
import { getBackgroundTaskRegistry } from '@jarvis/tools';
import type { AgentMailbox } from '@jarvis/agent';
import type { SubagentPool } from '../pool.js';
import type { AgentRegistry, AgentIdentity } from '../registry.js';

export interface SpawnAgentDeps {
  pool: SubagentPool;
  registry: AgentRegistry;
  /** Parent's mailbox so the subagent can send messages back */
  parentMailbox: AgentMailbox;
  /** Parent agent ID */
  parentId: string;
  /** Current depth level */
  depth: number;
}

export function createSpawnAgentHandler(deps: SpawnAgentDeps): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const description = String(args.description ?? '').trim();
    const prompt = String(args.prompt ?? '').trim();
    const agentType = (['explore', 'plan', 'general', 'review'] as const).includes(args.subagent_type as never)
      ? (args.subagent_type as 'explore' | 'plan' | 'general' | 'review')
      : 'general';
    const reviewRequired = args.review_required !== false;
    const expectedOutput = typeof args.expected_output === 'string' ? args.expected_output : undefined;
    const successCriteria = typeof args.success_criteria === 'string' ? args.success_criteria : undefined;

    if (!description || !prompt) {
      return JSON.stringify({ error: 'Missing required parameters: description and prompt' });
    }

    const agentId = `agent_${crypto.randomUUID().slice(0, 8)}`;
    const childDepth = deps.depth + 1;

    // Register child agent identity
    const identity: AgentIdentity = {
      agentId,
      role: agentType,
      parentId: deps.parentId,
      depth: childDepth,
      agentType,
      capabilities: [],
      registeredAt: Date.now(),
    };
    deps.registry.register(identity);

    // Submit to pool for execution
    const handle = deps.pool.submit({
      agentId,
      agentType,
      task: `## ${description}\n\n${prompt}`,
      depth: childDepth,
      parentId: deps.parentId,
      reviewRequired,
      expectedOutput,
      successCriteria,
    });

    // Register in background task registry so task_output can find it
    const bgTaskId = getBackgroundTaskRegistry().register({
      type: 'agent',
      status: 'running',
      description: `${agentType}: ${description}`,
      promise: new Promise((resolve) => {
        handle.completion.then((result) => {
          resolve({
            result: result.answer || result.error || '(no output)',
            error: result.status === 'failed' ? result.error : undefined,
          });
        }).catch((err) => {
          resolve({ error: err instanceof Error ? err.message : String(err) });
        });
      }),
      cancel: () => { handle.cancel?.(); },
    });

    // Return immediately — results will flow via mailbox notifications
    handle.completion.then((result) => {
      // Deliver result to parent's mailbox
      deps.parentMailbox.deliver(agentId, {
        kind: result.reviewResult ? 'review' : 'result',
        summary: `Task ${result.status === 'completed' ? 'completed' : 'failed'}: ${result.payload?.summary || result.answer || result.error || '(no output)'}`,
        payload: result,
      }, true);
    }).catch((err) => {
      deps.parentMailbox.deliver(agentId, {
        kind: 'result',
        summary: `Error: ${err instanceof Error ? err.message : String(err)}`,
        payload: { error: err instanceof Error ? err.message : String(err) },
      }, true);
    });

    return JSON.stringify({
      agentId,
      taskId: bgTaskId,
      status: 'spawned',
      depth: childDepth,
      message: `Agent "${agentId}" spawned for: ${description}`,
    });
  };
}

export function createSpawnAgentTool(deps: SpawnAgentDeps) {
  return {
    name: 'Agent',
    toolset: 'orchestration',
    schema: {
      type: 'object',
      description: 'Launch a new agent to handle complex, multi-step tasks.',
      parameters: {
        type: 'object',
        properties: {
          description: { type: 'string', description: 'A short (3-5 word) description of the task' },
          prompt: { type: 'string', description: 'The task for the agent to perform' },
          subagent_type: {
            type: 'string',
            enum: ['explore', 'plan', 'general', 'review'],
            default: 'general',
            description: 'Agent type: explore (read-only), plan (explore + task tools), general (all tools), review (read-only verifier)',
          },
          review_required: { type: 'boolean', default: true, description: 'Whether a reviewer should verify the worker result.' },
          expected_output: { type: 'string', description: 'Optional expected output contract for the subagent.' },
          success_criteria: { type: 'string', description: 'Optional success criteria for the subagent and reviewer.' },
        },
        required: ['description', 'prompt'],
      },
    },
    handler: createSpawnAgentHandler(deps),
    isAsync: true,
    emoji: '🤖',
    maxResultSizeChars: 50_000,
  };
}
