// ============================================================================
// Agent tool — spawn subagents for complex, multi-step tasks
// Factory pattern: accepts a SubagentPool at creation time
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';
import { getBackgroundTaskRegistry } from './task.js';

// ---- minimal pool interface (avoids coupling to @jarvis/subagents) ----

export interface AgentPool {
  submit(config: {
    agentId: string;
    agentType: string;
    task: string;
    budgetSteps?: number;
    depth?: number;
    model?: string;
    reasoningEffort?: string;
    permissionMode?: string;
    systemPrompt?: string;
    tools?: string[] | null;
    blockedTools?: string[];
    forkContext?: boolean;
    parentMessages?: Array<{ role: string; content: string }>;
  }): {
    agentId: string;
    status: string;
    completion: Promise<{ agentId: string; status: string; answer?: string; error?: string; turnsUsed?: number }>;
    cancel: () => void;
  };
}

/** Agent definition from .jarvis/agents/*.md */
export interface AgentFileDefinition {
  name: string;
  description: string;
  model?: string;
  reasoningEffort?: string;
  tools: string[] | null;
  blockedTools: string[];
  maxSteps?: number;
  permissionMode?: string;
  systemPrompt: string;
}

// ---- schema ----

export const agentSchema = toOpenAITool({
  name: 'Agent',
  description:
    'Launch a new agent to handle complex, multi-step tasks. Built-in types: explore (read-only search), plan (explore + task tools), general (all tools). Custom agent types from .jarvis/agents/*.md are also available.',
  parameters: {
    type: 'object',
    properties: {
      description: {
        type: 'string',
        description: 'A short (3-5 word) description of the task',
      },
      prompt: {
        type: 'string',
        description: 'The task for the agent to perform',
      },
      subagent_type: {
        type: 'string',
        default: 'general',
        description: 'Agent type: explore, plan, general, or a custom agent name from .jarvis/agents/',
      },
      model: {
        type: 'string',
        description: 'Override the model for this agent (e.g. "deepseek-v3", "haiku")',
      },
      run_in_background: {
        type: 'boolean',
        default: false,
        description: 'Set to true to run in background. You will be notified when it completes.',
      },
      fork_context: {
        type: 'boolean',
        default: false,
        description: 'Inherit parent conversation context (saves tokens, like Claude Code fork mode)',
      },
    },
    required: ['description', 'prompt'],
  },
});

// ---- factory ----

export function createAgentHandler(pool: AgentPool, agentDefs?: Map<string, AgentFileDefinition>): ToolHandler {
  const activeAgents = new Map<string, { cancel: () => void }>();

  return async (args: Record<string, unknown>, context: ToolContext): Promise<string> => {
    const description = String(args.description ?? '').trim();
    const prompt = String(args.prompt ?? '').trim();
    const agentTypeName = String(args.subagent_type ?? 'general').trim();
    const runInBackground = args.run_in_background === true;
    const forkContext = args.fork_context === true;
    const modelOverride = typeof args.model === 'string' ? args.model : undefined;

    if (!description || !prompt) {
      return JSON.stringify({ error: 'Missing required parameters: description and prompt' });
    }

    // Resolve agent type: built-in or custom definition
    const builtins = ['explore', 'plan', 'general'];
    const isBuiltin = builtins.includes(agentTypeName);
    const agentDef = agentDefs?.get(agentTypeName);

    if (!isBuiltin && !agentDef) {
      const available = [...builtins, ...(agentDefs ? agentDefs.keys() : [])];
      return JSON.stringify({ error: `Unknown agent type "${agentTypeName}". Available: ${available.join(', ')}` });
    }

    const agentId = `agent_${crypto.randomUUID().slice(0, 8)}`;

    try {
      const depth = typeof args.depth === 'number' ? args.depth : 1;

      // Build submit config from agent definition
      const submitConfig: Parameters<AgentPool['submit']>[0] = {
        agentId,
        agentType: agentTypeName,
        task: `## ${description}\n\n${prompt}`,
        depth,
      };

      // Apply agent definition overrides
      if (agentDef) {
        submitConfig.model = modelOverride ?? agentDef.model;
        submitConfig.reasoningEffort = agentDef.reasoningEffort;
        submitConfig.permissionMode = agentDef.permissionMode;
        submitConfig.systemPrompt = agentDef.systemPrompt;
        submitConfig.tools = agentDef.tools;
        submitConfig.blockedTools = agentDef.blockedTools;
      } else if (modelOverride) {
        submitConfig.model = modelOverride;
      }

      // Fork context mode
      if (forkContext && context.historyRef) {
        submitConfig.forkContext = true;
        submitConfig.parentMessages = context.historyRef.current.map((m) => ({
          role: m.role,
          content: m.content,
        }));
      }

      const handle = pool.submit(submitConfig);

      activeAgents.set(agentId, { cancel: handle.cancel });

      if (runInBackground) {
        const bgRegistry = getBackgroundTaskRegistry();
        const bgCompletion = handle.completion.then((result) => ({
          result: JSON.stringify({ agentId: result.agentId, status: result.status, answer: result.answer ?? '', error: result.error ?? null, turnsUsed: result.turnsUsed ?? 0 }),
        }));
        const origCancel = handle.cancel.bind(handle);
        bgRegistry.register({
          type: 'agent',
          status: 'running',
          description: `Agent: ${description}`,
          promise: bgCompletion,
          cancel: () => { activeAgents.delete(agentId); origCancel(); },
        });
      }

      handle.completion.then(() => activeAgents.delete(agentId)).catch(() => activeAgents.delete(agentId));

      const agentLabel = agentDef ? agentDef.name : agentTypeName;
      return JSON.stringify({
        agentId,
        status: 'spawned',
        type: agentLabel,
        model: submitConfig.model ?? 'inherit',
        message: `Agent "${agentId}" (${agentLabel}) spawned for: ${description}. Results will arrive in mailbox when complete.`,
      });
    } catch (err) {
      activeAgents.delete(agentId);
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `Agent spawn failed: ${message}` });
    }
  };
}

export function createAgentTool(pool: AgentPool, agentDefs?: Map<string, AgentFileDefinition>): ToolEntry {
  return {
    name: 'Agent',
    toolset: 'orchestration',
    schema: agentSchema,
    handler: createAgentHandler(pool, agentDefs),
    isAsync: true,
    emoji: '🤖',
    maxResultSizeChars: 50_000,
  };
}
