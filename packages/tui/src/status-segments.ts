import { basename } from "node:path";
import type { Color } from "./vendor/ink-renderer/index.js";
import type { StatusLineSegment } from "./vendor/ui/StatusLine.js";

export interface TaskCounts {
  pending: number;
  in_progress: number;
  completed: number;
}

export interface StatusSegmentInput {
  cwd: string;
  model: string;
  gitBranch?: string | null;
  isLoading: boolean;
  hasQuestion: boolean;
  totalTokens?: number;
  contextPercentRemaining?: number;
  contextWindow?: number;
  taskCounts: TaskCounts;
  elapsedMs: number;
  effort?: string;
  permissionMode?: string;
  /** Current permission state (only shown when not idle) */
  permissionState?: string;
  sessionId?: string | null;
  /** Agent counts: total, running, completed */
  agentCounts?: { total: number; running: number; completed: number };
}

export interface ContextBreakdownSegmentInput {
  systemPromptTokens?: number;
  conversationTokens?: number;
  skillsTokens?: number;
  toolSchemasTokens?: number;
  mcpToolsTokens?: number;
}

function formatPercent(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatTokensCompact(value: number): string {
  if (value < 0) return '0';
  if (value < 1000) return String(value);
  if (value < 1_000_000) return formatWithUnit(value, 1_000, 'K');
  return formatWithUnit(value, 1_000_000, 'M');
}

function formatWithUnit(value: number, divisor: number, unit: string): string {
  const divided = value / divisor;
  const decimals = divided < 10 ? 2 : divided < 100 ? 1 : 0;
  let formatted = divided.toFixed(decimals);
  formatted = formatted.replace(/0+$/, '').replace(/\.$/, '');
  return `${formatted}${unit}`;
}

export function buildContextBreakdownSegments(input: ContextBreakdownSegmentInput): StatusLineSegment[] {
  const parts: StatusLineSegment[] = [];
  const system = input.systemPromptTokens ?? 0;
  const conversation = input.conversationTokens ?? 0;
  const skills = input.skillsTokens ?? 0;
  const mcpTools = input.mcpToolsTokens ?? 0;
  const nonMcpTools = Math.max(0, (input.toolSchemasTokens ?? 0) - mcpTools);
  if (system > 0) parts.push({ content: `sys:${formatTokensCompact(system)}`, color: 'cyan' });
  if (conversation > 0) parts.push({ content: `msg:${formatTokensCompact(conversation)}`, color: 'green' });
  if (skills > 0) parts.push({ content: `skills:${formatTokensCompact(skills)}`, color: 'yellow' });
  if (nonMcpTools > 0) parts.push({ content: `tools:${formatTokensCompact(nonMcpTools)}`, color: 'yellow' });
  if (mcpTools > 0) parts.push({ content: `mcp:${formatTokensCompact(mcpTools)}`, color: 'red' });
  return parts;
}
function formatElapsed(elapsedMs: number): string | null {
  if (elapsedMs <= 0) return null;
  const seconds = Math.floor(elapsedMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toString().padStart(2, "0")}s`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function formatTasks(taskCounts: TaskCounts): string | null {
  const parts: string[] = [];
  if (taskCounts.in_progress > 0) parts.push(`~${taskCounts.in_progress}`);
  if (taskCounts.pending > 0) parts.push(`o${taskCounts.pending}`);
  if (taskCounts.completed > 0) parts.push(`x${taskCounts.completed}`);
  return parts.length > 0 ? `tasks ${parts.join(" ")}` : null;
}

function formatRunState(input: Pick<StatusSegmentInput, "isLoading" | "hasQuestion">): string {
  if (input.hasQuestion) return "Question";
  if (input.isLoading) return "Working";
  return "Ready";
}

export function getProjectLabel(cwd: string): string {
  return basename(cwd) || cwd;
}

const MODE_LABELS: Record<string, string> = {
  'workspace_write': 'suggest',
  'accept_edits': 'auto-edit',
  'bypass': 'full-auto',
  'plan': 'plan',
};

const MODE_COLORS: Record<string, Color> = {
  'workspace_write': 'yellow',
  'accept_edits': 'blue',
  'bypass': 'red',
  'plan': 'cyan',
};

const STATE_LABELS: Record<string, string> = {
  'exploring': 'exploring',
  'planning': 'planning',
  'awaiting_review': 'review',
  'questioning': 'question',
  'awaiting_confirm': 'confirm',
  'executing': 'executing',
};

const STATE_COLORS: Record<string, Color> = {
  'exploring': 'cyan',
  'planning': 'cyan',
  'awaiting_review': 'yellow',
  'questioning': 'yellow',
  'awaiting_confirm': 'yellow',
  'executing': 'green',
};

export function buildStatusSegments(input: StatusSegmentInput): StatusLineSegment[] {
  const modeLabel = input.permissionMode ? (MODE_LABELS[input.permissionMode] ?? input.permissionMode) : undefined;
  const modeColor = input.permissionMode ? (MODE_COLORS[input.permissionMode] ?? 'blue') : 'blue';
  const stateLabel = input.permissionState ? (STATE_LABELS[input.permissionState] ?? input.permissionState) : undefined;
  const stateColor = input.permissionState ? (STATE_COLORS[input.permissionState] ?? 'cyan') : 'cyan';
  const segments: StatusLineSegment[] = [
    { content: `project ${getProjectLabel(input.cwd)}`, color: "cyan" },
    { content: `model ${input.model}`, color: "white" },
    ...(input.effort && input.effort !== "auto" ? [{ content: `effort ${input.effort}`, color: "cyan" as const }] : []),
    ...(modeLabel ? [{ content: `mode ${modeLabel}`, color: modeColor }] : []),
    ...(stateLabel ? [{ content: `perm ${stateLabel}`, color: stateColor }] : []),
    { content: `state ${formatRunState(input)}`, color: input.isLoading ? "yellow" : "green" },
  ];

  if (input.gitBranch) {
    segments.splice(1, 0, { content: `branch ${input.gitBranch}`, color: "cyan" });
  }

  // Agent counts — CC-style: "Agents (2 running, 1 done)"
  if (input.agentCounts && input.agentCounts.total > 0) {
    const parts: string[] = [`Agents (${input.agentCounts.total})`];
    segments.push({
      content: parts[0],
      color: input.agentCounts.running > 0 ? "#E6B450" : "#5FAF5F",
    });
  }

  if (
    input.totalTokens !== undefined &&
    input.totalTokens > 0 &&
    input.contextPercentRemaining !== undefined
  ) {
    segments.push({
      content: `${input.totalTokens.toLocaleString()} tok | ${formatPercent(input.contextPercentRemaining)}% left`,
    });
  } else if (input.contextWindow !== undefined && input.contextWindow > 0) {
    segments.push({ content: `0 tok | 100% left`, color: 'gray' });
  }

  const taskSegment = formatTasks(input.taskCounts);
  if (taskSegment) {
    segments.push({ content: taskSegment });
  }

  const elapsed = formatElapsed(input.elapsedMs);
  if (elapsed) {
    segments.push({ content: elapsed });
  }

  if (input.sessionId) {
    segments.push({ content: `session ${input.sessionId.slice(-8)}`, color: "gray" });
  }

  return segments;
}
