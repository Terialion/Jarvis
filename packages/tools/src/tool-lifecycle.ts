import type { ToolRuntimeLifecycleEvent } from './runtime.js';

export type ToolLifecycleRunStatus =
  | 'awaiting_approval'
  | 'approved'
  | 'running'
  | 'completed'
  | 'failed'
  | 'denied';

export interface ToolLifecycleRun {
  callId: string;
  toolName: string;
  stage: ToolRuntimeLifecycleEvent['stage'];
  status: ToolLifecycleRunStatus;
  terminal: boolean;
  argsKey?: string;
  risk?: string;
  ok?: boolean;
  reason?: string;
  durationMs?: number;
}

export interface ToolLifecycleState {
  runsByCallId: Record<string, ToolLifecycleRun>;
  runOrder: string[];
}

export interface ToolLifecycleSummary {
  statusLine?: string;
  runningLine?: string;
  completedLines: string[];
  counts: {
    awaitingApproval: number;
    running: number;
    completed: number;
    failed: number;
    denied: number;
  };
}

function toRunStatus(event: ToolRuntimeLifecycleEvent): ToolLifecycleRunStatus {
  switch (event.stage) {
    case 'approval_requested':
      return 'awaiting_approval';
    case 'approval_granted':
      return 'approved';
    case 'approval_denied':
      return 'denied';
    case 'dispatch_started':
      return 'running';
    case 'dispatch_completed':
      return 'completed';
    case 'dispatch_failed':
      return 'failed';
  }
}

function isTerminalStatus(status: ToolLifecycleRunStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'denied';
}

function formatTerminalStatus(run: ToolLifecycleRun): string {
  switch (run.status) {
    case 'completed':
      return `completed ${run.toolName}`;
    case 'failed':
      return `tool failed: ${run.toolName}`;
    case 'denied':
      return `approval denied: ${run.toolName}`;
    default:
      return run.toolName;
  }
}

export function createToolLifecycleState(): ToolLifecycleState {
  return {
    runsByCallId: {},
    runOrder: [],
  };
}

export function applyToolLifecycleEvent(
  state: ToolLifecycleState,
  event: ToolRuntimeLifecycleEvent,
): ToolLifecycleState {
  const status = toRunStatus(event);
  const previous = state.runsByCallId[event.callId];
  const nextRun: ToolLifecycleRun = {
    callId: event.callId,
    toolName: event.toolName,
    stage: event.stage,
    status,
    terminal: isTerminalStatus(status),
    argsKey: 'argsKey' in event ? event.argsKey : previous?.argsKey,
    risk: 'risk' in event ? event.risk : previous?.risk,
    ok: 'ok' in event ? event.ok : previous?.ok,
    reason: 'reason' in event ? event.reason : previous?.reason,
    durationMs: 'durationMs' in event ? event.durationMs : previous?.durationMs,
  };

  return {
    runsByCallId: {
      ...state.runsByCallId,
      [event.callId]: nextRun,
    },
    runOrder: previous ? state.runOrder : [...state.runOrder, event.callId],
  };
}

export function buildToolLifecycleSummary(state: ToolLifecycleState): ToolLifecycleSummary {
  const runs = state.runOrder
    .map((callId) => state.runsByCallId[callId])
    .filter((run): run is ToolLifecycleRun => Boolean(run));

  const awaitingApproval = runs.filter((run) => run.status === 'awaiting_approval');
  const running = runs.filter((run) => run.status === 'running' || run.status === 'approved');
  const completed = runs.filter((run) => run.status === 'completed');
  const failed = runs.filter((run) => run.status === 'failed');
  const denied = runs.filter((run) => run.status === 'denied');
  const terminalRuns = runs.filter((run) => run.terminal);
  const latestTerminalRun = terminalRuns.at(-1);

  let statusLine: string | undefined;
  if (awaitingApproval.length > 0) {
    statusLine = `waiting for approval: ${awaitingApproval[awaitingApproval.length - 1]?.toolName}`;
  } else if (running.length > 0) {
    statusLine = `running ${running[running.length - 1]?.toolName}`;
  } else if (latestTerminalRun) {
    statusLine = formatTerminalStatus(latestTerminalRun);
  }

  return {
    statusLine,
    runningLine: running.at(-1)?.toolName,
    completedLines: terminalRuns.slice(-3).map((run) => run.toolName),
    counts: {
      awaitingApproval: awaitingApproval.length,
      running: running.length,
      completed: completed.length,
      failed: failed.length,
      denied: denied.length,
    },
  };
}
