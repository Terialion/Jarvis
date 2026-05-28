// ============================================================================
// Codex-style thread events and items
// ============================================================================

export type ThreadUsage = {
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
};

export type ToolCallThreadItemStatus = 'in_progress' | 'completed' | 'failed';

export type AgentMessageThreadItem = {
  id: string;
  type: 'agent_message';
  text: string;
};

export type ReasoningThreadItem = {
  id: string;
  type: 'reasoning';
  text: string;
};

export type ToolCallThreadItem = {
  id: string;
  type: 'tool_call';
  tool_name: string;
  arguments: Record<string, unknown>;
  status: ToolCallThreadItemStatus;
  result?: string;
  error?: string;
  duration_ms?: number;
};

export type TodoThreadItem = {
  text: string;
  completed: boolean;
};

export type TodoListThreadItem = {
  id: string;
  type: 'todo_list';
  items: TodoThreadItem[];
};

export type ErrorThreadItem = {
  id: string;
  type: 'error';
  message: string;
};

export type ThreadItem =
  | AgentMessageThreadItem
  | ReasoningThreadItem
  | ToolCallThreadItem
  | TodoListThreadItem
  | ErrorThreadItem;

export type ThreadStartedEvent = {
  type: 'thread.started';
  thread_id: string;
};

export type TurnStartedEvent = {
  type: 'turn.started';
  turn_id: string;
};

export type TurnCompletedEvent = {
  type: 'turn.completed';
  turn_id: string;
  stop_reason: string;
  usage?: ThreadUsage | null;
};

export type TurnFailedEvent = {
  type: 'turn.failed';
  turn_id: string;
  error: {
    message: string;
  };
};

export type ItemStartedEvent = {
  type: 'item.started';
  turn_id: string;
  item: ThreadItem;
};

export type ItemUpdatedEvent = {
  type: 'item.updated';
  turn_id: string;
  item: ThreadItem;
};

export type ItemCompletedEvent = {
  type: 'item.completed';
  turn_id: string;
  item: ThreadItem;
};

export type ThreadErrorEvent = {
  type: 'error';
  message: string;
};

export type ThreadEvent =
  | ThreadStartedEvent
  | TurnStartedEvent
  | TurnCompletedEvent
  | TurnFailedEvent
  | ItemStartedEvent
  | ItemUpdatedEvent
  | ItemCompletedEvent
  | ThreadErrorEvent;
