// ============================================================================
// Subagent models — configuration, status, handle types, and agent identity
// ============================================================================

export type SubagentStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ReviewDecision = 'pass' | 'needs_fix' | 'blocked';
export type BuiltinAgentType = 'explore' | 'plan' | 'general' | 'review';

export interface SubagentArtifact {
  kind: string;
  label: string;
  path?: string;
  detail?: string;
}

export interface SubagentEvidence {
  kind: string;
  summary: string;
  source?: string;
}

export interface SubagentRisk {
  severity: 'low' | 'medium' | 'high';
  summary: string;
}

export interface ReviewFinding {
  severity: 'low' | 'medium' | 'high';
  summary: string;
  detail?: string;
  file?: string;
}

export interface StructuredSubagentPayload {
  kind: 'explore' | 'plan' | 'implement' | 'review' | 'general';
  summary: string;
  artifacts: SubagentArtifact[];
  evidence: SubagentEvidence[];
  risks: SubagentRisk[];
  nextActions: string[];
  confidence: number;
  rawAnswer: string;
  facts?: string[];
  files?: string[];
  openQuestions?: string[];
  tasks?: string[];
  dependencies?: string[];
  assumptions?: string[];
  changedFiles?: string[];
  commandsRun?: string[];
  verification?: string[];
  findings?: ReviewFinding[];
  decision?: ReviewDecision;
}

export interface SubagentConfig {
  /** Unique identifier for this subagent */
  agentId: string;
  /** Agent type — determines tool whitelist */
  agentType: string;
  /** Task description to execute */
  task: string;
  /** Maximum conversation turns */
  budgetSteps?: number;
  /** Nesting depth (0 = top-level) */
  depth?: number;
  /** Model override for this subagent */
  model?: string;
  /** Reasoning effort override */
  reasoningEffort?: string;
  /** Permission mode override */
  permissionMode?: string;
  /** Custom system prompt (from agent definition) */
  systemPrompt?: string;
  /** Tool whitelist override (null = all tools) */
  tools?: string[] | null;
  /** Blocked tools (always blocked) */
  blockedTools?: string[];
  /** Fork parent context (inherit message history) */
  forkContext?: boolean;
  /** Parent agent's messages for fork mode */
  parentMessages?: Array<{ role: string; content: string }>;
  /** Parent agent ID (for tree display) */
  parentId?: string;
  /** Whether a reviewer should verify this result before parent consumption. */
  reviewRequired?: boolean;
  /** Optional expected output contract for worker/reviewer prompts. */
  expectedOutput?: string;
  /** Optional success criteria for worker/reviewer prompts. */
  successCriteria?: string;
  /** Optional bundle metadata for first-phase wave orchestration. */
  taskBundleId?: string;
  workItemId?: string;
  waveId?: string;
  /** Review metadata when the config itself is a reviewer task. */
  reviewOfAgentId?: string;
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
  payload?: StructuredSubagentPayload;
  reviewStatus?: ReviewDecision;
  reviewResult?: StructuredSubagentPayload;
}

export interface WorkItem {
  id: string;
  title: string;
  task: string;
  agentType: string;
  reviewRequired?: boolean;
  expectedOutput?: string;
  successCriteria?: string;
  dependsOn?: string[];
  metadata?: Record<string, string>;
}

export interface TaskBundle {
  id: string;
  title: string;
  summary?: string;
  waveId: string;
  items: WorkItem[];
}

export interface WaveResult {
  bundleId: string;
  waveId: string;
  status: 'completed' | 'failed' | 'blocked';
  results: SubagentResult[];
  passedReviews: number;
  failedReviews: number;
  blockedReviews: number;
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
  agentType: BuiltinAgentType;
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

export const REVIEW_TOOLS = [
  ...EXPLORE_TOOLS,
  'task_list',
];

export const GENERAL_TOOLS: string[] | null = null; // null = all tools

/** Maximum subagent nesting depth */
export const MAX_DEPTH = 2;

/** Maximum budget steps per subagent */
export const MAX_BUDGET_STEPS = 50;
