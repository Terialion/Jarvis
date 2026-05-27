// ============================================================================
// SubagentRunner — execute subagent tasks with full AgentLoop instances
// ============================================================================

import type { AgentLoop, AgentRunResult } from '@jarvis/agent';
import type { AgentMailbox } from '@jarvis/agent';
import type { SubagentConfig, SubagentResult } from './models.js';
import {
  EXPLORE_TOOLS,
  PLAN_TOOLS,
  GENERAL_TOOLS,
  MAX_DEPTH,
  MAX_BUDGET_STEPS,
} from './models.js';

// ============================================================================
// RunnerDeps
// ============================================================================

export interface RunnerDeps {
  /** Create a new AgentLoop instance for a subagent. */
  createAgentLoop: (opts: {
    agentId: string;
    task: string;
    allowedTools: string[] | null;
    maxSteps: number;
    depth: number;
    mailbox: AgentMailbox;
    systemPrompt?: string;
  }) => AgentLoop;
}

// ============================================================================
// SubagentRunner
// ============================================================================

export class SubagentRunner {
  private deps: RunnerDeps;

  constructor(deps: RunnerDeps) {
    this.deps = deps;
  }

  // ========================================================================
  // Run
  // ========================================================================

  async run(config: SubagentConfig, mailbox: AgentMailbox): Promise<SubagentResult> {
    // Validate depth
    const depth = config.depth ?? 0;
    if (depth > MAX_DEPTH) {
      return {
        agentId: config.agentId,
        status: 'failed',
        error: `Depth ${depth} exceeds max ${MAX_DEPTH}`,
      };
    }

    // Validate budget
    const budget = config.budgetSteps ?? 5;
    if (budget < 1 || budget > MAX_BUDGET_STEPS) {
      return {
        agentId: config.agentId,
        status: 'failed',
        error: `Budget ${budget} out of range (1-${MAX_BUDGET_STEPS})`,
      };
    }

    // Get tool whitelist
    const allowedTools = toolWhitelistForType(config.agentType);

    try {
      const loop = this.deps.createAgentLoop({
        agentId: config.agentId,
        task: config.task,
        allowedTools,
        maxSteps: budget,
        depth,
        mailbox,
        systemPrompt: buildSubagentSystemPrompt({
        task: config.task,
        depth: config.depth ?? 0,
      }),
      });

      const result: AgentRunResult = await loop.runTurn(config.task);

      return {
        agentId: config.agentId,
        status: result.ok ? 'completed' : 'failed',
        answer: result.finalAnswer,
        error: result.ok ? undefined : result.finalAnswer,
        turnsUsed: result.toolCalls.length,
      };
    } catch (err) {
      return {
        agentId: config.agentId,
        status: 'failed',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}

// ============================================================================
// Tool whitelist
// ============================================================================

export function toolWhitelistForType(
  agentType: SubagentConfig['agentType'],
): string[] | null {
  switch (agentType) {
    case 'explore':
      return EXPLORE_TOOLS;
    case 'plan':
      return PLAN_TOOLS;
    case 'general':
      return GENERAL_TOOLS; // null = all tools
  }
}

// ============================================================================
// Subagent system prompt (OpenClaw buildSubagentSystemPrompt pattern)
// ============================================================================

export interface SubagentPromptParams {
  /** The task description to embed in the prompt */
  task: string;
  /** Nesting depth (0 = top-level, 1 = first child, etc.) */
  depth: number;
  /** Maximum allowed spawn depth */
  maxDepth?: number;
  /** Parent agent ID, for reference */
  parentId?: string;
  /** Agent type label (for role description) */
  agentType?: string;
  /** Whether this subagent can spawn its own subagents */
  canSpawn?: boolean;
}

export function buildSubagentSystemPrompt(params: SubagentPromptParams): string {
  const {
    task,
    depth,
    maxDepth = MAX_DEPTH,
    parentId,
    agentType = 'worker',
    canSpawn = depth < maxDepth,
  } = params;

  const parentLabel = depth >= 2 ? 'parent orchestrator' : 'main agent';
  const toolDesc = agentType === 'explore'
    ? 'read-only search tools (read, glob, grep, list)'
    : agentType === 'plan'
      ? 'read-only search + task management tools'
      : 'a full set of development tools (bash, file read/write/edit, glob, grep, web, etc.)';

  const lines: string[] = [];

  lines.push(
    '# Subagent Context',
    '',
    "You are a **subagent** spawned by the " + parentLabel + " for a specific task.",
    '',
    '## Your Role',
    "- You were created to handle: " + task,
    "- Complete this task. That's your entire purpose.",
    "- You are NOT the " + parentLabel + ". Don't try to be.",
    "- You have access to " + toolDesc,
    '',
    '## Rules',
    '1. **Stay focused** — Do your assigned task, nothing else',
    "2. **Complete the task** — Your final message will be automatically reported to the " + parentLabel,
    "3. **Don't initiate** — No heartbeats, no proactive actions, no side quests",
    "4. **Be ephemeral** — You may be terminated after task completion. That's fine.",
    "5. **Recover from truncated tool output** — If output was truncated, re-read using smaller chunks instead of full reads.",
    '',
    '## Output Format',
    'When complete, your final response should include:',
    '- What you accomplished or found',
    '- Any files you created or modified',
    '- Any issues encountered or remaining work',
    "- Any relevant details the " + parentLabel + " should know",
    '- Keep it concise but informative',
    '',
    "## What You DON'T Do",
    "- NO user conversations (that's the " + parentLabel + "'s job)",
    '- NO modifying files outside the project directory',
    '- NO setting up persistent services or cron jobs',
    "- NO pretending to be the " + parentLabel,
    '',
  );

  if (parentId) {
    lines.push(
      '## Communication',
      "You can communicate with your parent (" + parentId + ") using the `report` tool.",
      'Use `talk_to` to communicate with other peer agents.',
      'Use `list_agents` to see the current organization structure.',
      '',
    );
  }

  if (canSpawn) {
    lines.push(
      '## Sub-Agent Spawning',
      'You CAN spawn your own sub-agents using the `Agent` tool for parallel or complex work.',
      'Their results will automatically arrive in your mailbox — do NOT poll for status.',
      "Nesting depth limit: you are at depth " + depth + ", max is " + maxDepth + ".",
      'Coordinate their work and synthesize results before reporting back.',
      '',
    );
  } else if (depth >= maxDepth) {
    lines.push(
      '## Sub-Agent Spawning',
      'You are at the maximum depth and CANNOT spawn further sub-agents.',
      'Focus entirely on your assigned task.',
      '',
    );
  }

  lines.push(
    '## Metadata',
    "- Depth: " + depth + "/" + maxDepth,
  );
  if (parentId) lines.push("- Parent: " + parentId);
  lines.push("- Type: " + agentType, '');

  return lines.join('\n');
}