// ============================================================================
// Subagent models — configuration, status, and handle types
// ============================================================================

export type SubagentStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface SubagentConfig {
  /** Unique identifier for this subagent */
  agentId: string;
  /** Agent type — determines tool whitelist */
  agentType: 'explore' | 'plan' | 'general';
  /** Task description to execute */
  task: string;
  /** Maximum conversation turns */
  budgetSteps?: number;
  /** Nesting depth (0 = top-level) */
  depth?: number;
}

export interface SubagentHandle {
  agentId: string;
  status: SubagentStatus;
  /** Promise that resolves when the subagent completes */
  completion: Promise<SubagentResult>;
  /** Cancel the subagent */
  cancel: () => void;
}

export interface SubagentResult {
  agentId: string;
  status: SubagentStatus;
  answer?: string;
  error?: string;
  turnsUsed?: number;
}

// ============================================================================
// Tool whitelists per agent type
// ============================================================================

export const EXPLORE_TOOLS = [
  'read',
  'glob',
  'grep',
  'list',
];

export const PLAN_TOOLS = [
  ...EXPLORE_TOOLS,
  'task_create',
  'task_update',
  'task_list',
];

export const GENERAL_TOOLS: string[] | null = null; // null = all tools

/** Maximum subagent nesting depth */
export const MAX_DEPTH = 2;

/** Maximum budget steps per subagent */
export const MAX_BUDGET_STEPS = 50;
