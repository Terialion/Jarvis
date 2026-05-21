// ============================================================================
// Jarvis Core Domain Types
// ============================================================================

/** Status of an agent turn. */
export type TurnStatus =
  | 'created'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

/** A single chat message (OpenAI-compatible format). */
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  /** Auto-generated msg_<uuid> */
  messageId: string;
  name?: string;
  toolCallId?: string;
  metadata?: Record<string, unknown>;
}

/** Tool definition as registered in the system. */
export interface ToolSpec {
  name: string;
  description: string;
  /** JSON Schema for parameters */
  inputSchema: Record<string, unknown>;
  riskLevel: 'low' | 'medium' | 'high';
  /** Source of the tool, e.g. "jarvis", "plugin" */
  source: string;
  requiresApproval: boolean;
}

/** A tool call from the model. */
export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  /** Auto-generated call_<uuid> */
  callId: string;
  /** Source of the call: "model" or "human" */
  source: string;
  metadata?: Record<string, unknown>;
}

/** Result from executing a tool. */
export interface ToolResult {
  callId: string;
  name: string;
  ok: boolean;
  content: string;
  data?: Record<string, unknown>;
  error?: string;
  errorType?: string;
  durationMs: number;
}

/** Normalized response from any LLM provider. */
export interface ModelResponse {
  content: string;
  toolCalls: ToolCall[];
  stopReason: 'stop' | 'tool_calls' | 'length' | 'content_filter';
  reasoning?: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    cachedTokens: number;
  };
  providerData?: Record<string, unknown>;
}

/** Event emitted during agent execution. */
export interface AgentEvent {
  type: string;
  turnId: string;
  payload: Record<string, unknown>;
  /** Auto-generated evt_<uuid> */
  eventId: string;
}

/** Final result of an agent run. */
export interface AgentRunResult {
  threadId: string;
  turnId: string;
  status: TurnStatus;
  answer: string;
  messages: ChatMessage[];
  toolResults: ToolResult[];
  events: AgentEvent[];
  summary: Record<string, unknown>;
  stopReason: string;
}

/** Error from a tool execution during agent loop. */
export interface ToolError {
  turn: number;
  toolName: string;
  arguments: string;
  error: string;
  toolResult: string;
}
