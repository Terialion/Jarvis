import { basename } from "node:path";
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
  taskCounts: TaskCounts;
  elapsedMs: number;
  effort?: string;
  sessionId?: string | null;
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

export function buildStatusSegments(input: StatusSegmentInput): StatusLineSegment[] {
  const segments: StatusLineSegment[] = [
    { content: `project ${getProjectLabel(input.cwd)}`, color: "cyan" },
    { content: `model ${input.model}` },
    ...(input.effort && input.effort !== "auto" ? [{ content: `effort ${input.effort}`, color: "magenta" as const }] : []),
    { content: `state ${formatRunState(input)}`, color: input.isLoading ? "yellow" : "green" },
  ];

  if (input.gitBranch) {
    segments.splice(1, 0, { content: `branch ${input.gitBranch}`, color: "magenta" });
  }

  if (
    input.totalTokens !== undefined &&
    input.totalTokens > 0 &&
    input.contextPercentRemaining !== undefined
  ) {
    segments.push({
      content: `${input.totalTokens.toLocaleString()} tok | ${input.contextPercentRemaining}% left`,
    });
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
