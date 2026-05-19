/**
 * Shared types for Jarvis TUI ←→ Python bridge protocol.
 *
 * Communication is via newline-delimited JSON over stdin/stdout.
 * The TUI process (Node/Ink) is the parent; the Python agent is a child process.
 */

// ── Python → TUI events ────────────────────────────────────────────

export interface InitEvent {
  type: "init";
  model: string;
  project_root: string;
  git_branch: string;
  permission_mode: string;
}

export interface ChunkEvent {
  type: "chunk";
  data: ModelChunk;
}

export interface DoneEvent {
  type: "done";
  finish_reason: string;
  token_count?: number;
  cost?: number;
}

export interface AskUserEvent {
  type: "ask_user";
  question: string;
  header: string;
  options: AskUserOption[];
  multi_select: boolean;
}

export interface ModelChunk {
  kind: "text_delta" | "reasoning_delta" | "progress_delta" | "tool_call_delta" | "done" | "event";
  text_delta?: string;
  reasoning_delta?: string;
  progress_delta?: string;
  tool_call_id?: string;
  tool_name?: string;
  tool_arguments_delta?: string;
  finish_reason?: string;
}

export interface AskUserOption {
  label: string;
  description: string;
}

export interface ContextUsageEvent {
  type: "context_usage";
  data: {
    used_tokens: number;
    context_window: number;
    usage_pct: number;
    message_count: number;
  };
}

export type PythonEvent = InitEvent | ChunkEvent | DoneEvent | AskUserEvent | ContextUsageEvent;

// ── TUI → Python requests ──────────────────────────────────────────

export interface InputRequest {
  type: "input";
  text: string;
}

export interface CancelRequest {
  type: "cancel";
}

export interface AskUserResponse {
  type: "ask_user_response";
  answers: Record<string, string>;
}

export type TUIRequest = InputRequest | CancelRequest | AskUserResponse;

// ── Turn state ─────────────────────────────────────────────────────

export interface ToolInfo {
  name: string;
  display: string;
  args: string;
  status: "ok" | "error" | "running";
  result?: string;
}

export interface TurnState {
  messages: Message[];
  isStreaming: boolean;
  currentAnswer: string;
  currentThinking: string;
  currentTools: ToolInfo[];
  statusText: string;
  modelName: string;
  gitBranch: string;
  permissionMode: string;
  latency: string;
  tokenCount: number;
  cost: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  thinking?: string;
  tools?: ToolInfo[];
  timestamp: number;
}

export interface SubagentInfo {
  agent_id: string;
  agent_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  steps: number;
  max_steps: number;
  depth: number;
  result?: string;
  error?: string;
}
