// ============================================================================
// Subagent models — configuration, status, handle types, and agent identity
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
// Agent Identity (Codex AgentMetadata + Hermes _delegate_depth pattern)
// ============================================================================

export interface AgentIdentity {
  /** Unique agent identifier within the organization */
  agentId: string;
  /** Human-readable role label (e.g. "developer", "qa", "architect") */
  role: string;
  /** Parent agent ID (null for root/supervisor) */
  parentId: string | null;
  /** Nesting depth (0 = supervisor) */
  depth: number;
  /** Agent type — determines tool capabilities */
  agentType: 'explore' | 'plan' | 'general';
  /** Capability tags */
  capabilities: string[];
  /** When the agent was registered */
  registeredAt: number;
}

export type AgentLifecycleStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

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
