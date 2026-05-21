// ============================================================================
// Hook models — lifecycle hook types
// ============================================================================

// ============================================================================
// Hook Stage
// ============================================================================

export type HookStage =
  | 'session_start'
  | 'session_end'
  | 'turn_start'
  | 'turn_end'
  | 'compact_pre'
  | 'user_prompt_submit'
  | 'pre_tool_use'
  | 'post_tool_use'
  | 'stop';

// ============================================================================
// Hook Matcher
// ============================================================================

export interface HookMatcher {
  /** Match by tool name (for pre_tool_use / post_tool_use) */
  toolName?: string;
  /** Match by risk level */
  riskLevel?: string;
}

// ============================================================================
// Hook Result
// ============================================================================

export interface HookResult {
  /** Whether the action is allowed to proceed */
  allowed: boolean;
  /** Short reason code for denial */
  reason?: string;
  /** Human-readable message */
  message?: string;
  /** Arbitrary data from the hook */
  metadata?: Record<string, unknown>;
}

// ============================================================================
// Hook Spec
// ============================================================================

export interface HookSpec {
  /** Unique hook identifier */
  name: string;
  /** Which lifecycle stage this hook fires on */
  stage: HookStage;
  /** Optional matcher to filter when the hook fires */
  matcher?: HookMatcher;
  /** The handler function */
  handler: (context: HookContext) => HookResult | Promise<HookResult>;
}

// ============================================================================
// Hook Context
// ============================================================================

export interface HookContext {
  /** Name of the tool being called (pre_tool_use / post_tool_use) */
  toolName?: string;
  /** Arguments passed to the tool */
  toolArgs?: Record<string, unknown>;
  /** Tool result (post_tool_use only) */
  toolResult?: string;
  /** Session ID */
  sessionId?: string;
  /** Turn ID */
  turnId?: string;
}
