// ============================================================================
// SubagentRunner — execute subagent tasks with restricted tool sets
// ============================================================================

import type { SubagentConfig, SubagentResult } from './models.js';
import {
  EXPLORE_TOOLS,
  PLAN_TOOLS,
  GENERAL_TOOLS,
  MAX_DEPTH,
  MAX_BUDGET_STEPS,
} from './models.js';

// ============================================================================
// SubagentRunner
// ============================================================================

export interface RunnerDeps {
  /** Execute a single-turn agent run and return the answer. */
  runTurn: (
    task: string,
    allowedTools: string[] | null,
    maxTurns: number,
  ) => Promise<{ answer: string; turnsUsed: number }>;
}

export class SubagentRunner {
  private deps: RunnerDeps;

  constructor(deps: RunnerDeps) {
    this.deps = deps;
  }

  // ========================================================================
  // Run
  // ========================================================================

  async run(config: SubagentConfig): Promise<SubagentResult> {
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
      const { answer, turnsUsed } = await this.deps.runTurn(
        config.task,
        allowedTools,
        budget,
      );

      return {
        agentId: config.agentId,
        status: 'completed',
        answer,
        turnsUsed,
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
