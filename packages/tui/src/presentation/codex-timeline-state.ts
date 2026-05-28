import { formatTokensCompact, type ThreadEvent, type ThreadItem } from '@jarvis/agent';
import { relative } from 'node:path';
import { formatToolLine } from '../vendor/ui/tool-display.js';

export type CodexLiveStatus = {
  isLoading: boolean;
  elapsedMs?: number;
  tokenCount?: number;
  verb?: string;
  status?: string;
  details?: string[];
  completed?: string[];
  running?: string;
};

export type CodexTurnSnapshot = {
  turnId: string;
  elapsedMs?: number;
  tokenCount?: number;
};

export type CodexTaskStatus = 'pending' | 'in_progress' | 'completed';

export type CodexTaskSnapshot = {
  turnId: string;
  sourceId: string;
  counts: {
    pending: number;
    in_progress: number;
    completed: number;
  };
  tasks: Array<{
    id: string;
    subject: string;
    status: CodexTaskStatus;
  }>;
};

export type CodexUserMessageView = {
  id: string;
  text: string;
};

export type CodexAssistantMessageView = {
  id: string;
  text: string;
  role: 'assistant' | 'system';
};

export type CodexTimelineItemView =
  | {
      id: string;
      kind: 'reasoning';
      label: string;
      meta?: string;
      text: string;
    }
  | {
      id: string;
      kind: 'agent_message';
      label: string;
      meta?: string;
      text: string;
    }
  | {
      id: string;
      kind: 'tool_call';
      label: string;
      status: string;
      statusLabel: string;
      summary?: string;
      collapsedDetail?: string;
      argumentsText?: string;
      resultText?: string;
      errorText?: string;
      previewLines?: string[];
      previewOverflowCount?: number;
      alwaysShowPreview?: boolean;
      previewKind?: 'code' | 'diff';
    }
  | {
      id: string;
      kind: 'todo_list';
      label: string;
      summary?: string;
      lines: string[];
      collapsedLines?: string[];
      overflowCount?: number;
    }
  | {
      id: string;
      kind: 'error';
      label: string;
      text: string;
    }
  | {
      id: string;
      kind: 'progress';
      label: string;
      elapsedText?: string;
      lines: string[];
    };

export type CodexTimelineTurnView = {
  turnId: string;
  turnNumber: number;
  status: 'running' | 'completed' | 'failed';
  statusText: string;
  statsText?: string;
  items: CodexTimelineItemView[];
};

export type CodexSearchDocument = {
  id: string;
  text: string;
  target:
    | {
        kind: 'user_message';
        messageId: string;
      }
    | {
        kind: 'timeline_item';
        turnId: string;
        itemId: string;
      };
};

export type CodexTimelineState = {
  locale: 'en' | 'zh';
  blocks: Array<
    | {
        id: string;
        kind: 'user_message';
        message: CodexUserMessageView;
      }
    | {
        id: string;
        kind: 'assistant_message';
        message: CodexAssistantMessageView;
      }
    | {
        id: string;
        kind: 'turn';
        turn: CodexTimelineTurnView;
      }
  >;
  turns: CodexTimelineTurnView[];
  searchDocuments: CodexSearchDocument[];
};

export type CodexTimelineSearchState = {
  query: string;
  activeDocumentId?: string;
  activeExcerpt?: string | null;
};

type TimelineTurnState = {
  turnId: string;
  status: 'running' | 'completed' | 'failed';
  stopReason?: string;
  errorMessage?: string;
  itemOrder: string[];
  itemState: Map<string, ThreadItem>;
};

type BuildStateInput = {
  events: ThreadEvent[];
  liveStatus: CodexLiveStatus;
  messages: Array<
    | ({ role: 'user' } & CodexUserMessageView)
    | ({ role: 'assistant' | 'system' } & CodexAssistantMessageView)
  >;
  taskSnapshots?: CodexTaskSnapshot[];
  turnSnapshots?: CodexTurnSnapshot[];
};

function truncate(text: string, limit = 280): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}...`;
}

function normalizeText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function isLikelyDuplicateText(left: string, right: string): boolean {
  const a = normalizeText(left);
  const b = normalizeText(right);
  if (!a || !b) return false;
  if (a === b) return true;
  const shorter = a.length <= b.length ? a : b;
  const longer = shorter === a ? b : a;
  if (shorter.length >= 12 && longer.includes(shorter)) return true;
  let prefixLength = 0;
  const limit = Math.min(a.length, b.length);
  while (prefixLength < limit && a[prefixLength] === b[prefixLength]) {
    prefixLength += 1;
  }
  return prefixLength >= 48 && Math.abs(a.length - b.length) <= 24;
}

function formatElapsed(elapsedMs?: number): string | undefined {
  if (!elapsedMs || elapsedMs < 0) return undefined;
  const seconds = Math.floor(elapsedMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toString().padStart(2, '0')}s`;
}

function formatTokenDelta(tokenCount?: number): string | undefined {
  if (!tokenCount || tokenCount <= 0) return undefined;
  return `↓${formatTokensCompact(tokenCount)} tokens`;
}

function buildDisplayStatsText(elapsedMs?: number, tokenCount?: number): string | undefined {
  return [formatElapsed(elapsedMs), formatTokenDelta(tokenCount)].filter(Boolean).join(' · ') || undefined;
}

function humanizePhaseName(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatTurnStatus(status: CodexTimelineTurnView['status'], stopReason?: string): string {
  if (status === 'running') return 'working';
  if (status === 'failed') return stopReason ? `failed: ${stopReason}` : 'failed';
  if (!stopReason || stopReason === 'completed' || stopReason === 'stop') return 'completed';
  if (stopReason === 'consecutive_rejections') return 'stopped after repeated retries';
  return `completed: ${stopReason}`;
}

function formatToolStatus(status: string): string {
  switch (status) {
    case 'completed':
      return 'done';
    case 'failed':
      return 'failed';
    case 'running':
      return 'in_progress';
    default:
      return status;
  }
}

function splitToolHeadline(summary: string, fallback: string): { label: string; summary?: string } {
  const separatorIndex = summary.indexOf(': ');
  if (separatorIndex === -1) {
    return { label: fallback, summary: summary === fallback ? undefined : summary };
  }
  return { label: summary.slice(0, separatorIndex), summary: summary.slice(separatorIndex + 2) };
}

function getPathLabel(pathValue: unknown): string | undefined {
  if (typeof pathValue !== 'string' || !pathValue.trim()) return undefined;
  const normalized = pathValue.trim().replace(/\//g, '\\');
  const cwd = process.cwd().replace(/\//g, '\\');
  if (normalized.toLowerCase().startsWith(cwd.toLowerCase())) {
    const rel = relative(cwd, normalized).replace(/\//g, '\\');
    return rel || normalized;
  }
  return normalized;
}

function getLineArray(text: string): string[] {
  return text.replace(/\r/g, '').split('\n');
}

function countLines(text: string): number {
  if (!text) return 0;
  return getLineArray(text).length;
}

function parseJsonObject(text?: string): Record<string, unknown> | null {
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function wasOverwriteWrite(resultText?: string): boolean {
  const parsed = parseJsonObject(resultText);
  return parsed?.existedBefore === true;
}

function buildToolTitle(
  toolName: string,
  args: Record<string, unknown>,
  fallbackLabel: string,
  resultText?: string,
): string {
  switch (toolName) {
    case 'bash': {
      const command = typeof args.command === 'string' ? normalizeText(args.command) : '';
      return command ? `Bash(${truncate(command, 56)})` : 'Bash';
    }
    case 'write_file': {
      const pathLabel = getPathLabel(args.path);
      const verb = wasOverwriteWrite(resultText) ? 'Update' : 'Write';
      return pathLabel ? `${verb}(${pathLabel})` : verb;
    }
    case 'edit_file': {
      const pathLabel = getPathLabel(args.path);
      return pathLabel ? `Update(${pathLabel})` : 'Update';
    }
    case 'read_file': {
      const pathLabel = getPathLabel(args.path);
      return pathLabel ? `Read(${pathLabel})` : 'Read';
    }
    case 'glob': {
      const pattern = typeof args.pattern === 'string' ? normalizeText(args.pattern) : '';
      return pattern ? `Glob(${truncate(pattern, 40)})` : 'Glob';
    }
    case 'grep': {
      const pattern = typeof args.pattern === 'string' ? normalizeText(args.pattern) : '';
      return pattern ? `Grep(${truncate(pattern, 36)})` : 'Grep';
    }
    case 'skill.load': {
      const skill = typeof args.skill === 'string' ? normalizeText(args.skill) : '';
      return skill ? `Skill(${skill})` : 'Skill';
    }
    default:
      return fallbackLabel;
  }
}

function buildToolResultSummary(
  toolName: string,
  args: Record<string, unknown>,
  resultText?: string,
): string | undefined {
  const parsed = parseJsonObject(resultText);
  switch (toolName) {
    case 'write_file': {
      const pathLabel = getPathLabel(args.path);
      const content = typeof args.content === 'string' ? args.content : '';
      const lineCount = countLines(content);
      if (pathLabel && lineCount > 0 && wasOverwriteWrite(resultText)) {
        return `Replaced ${lineCount} lines in ${pathLabel}`;
      }
      if (pathLabel && lineCount > 0) return `Wrote ${lineCount} lines to ${pathLabel}`;
      if (pathLabel) return `Wrote file ${pathLabel}`;
      break;
    }
    case 'edit_file': {
      const pathLabel = getPathLabel(args.path);
      const replacements = parsed && typeof parsed.replacements === 'number' ? parsed.replacements : undefined;
      const oldString = typeof args.old_string === 'string' ? args.old_string : '';
      const newString = typeof args.new_string === 'string' ? args.new_string : '';
      const removedLines = countLines(oldString);
      const addedLines = countLines(newString);
      if (pathLabel && (addedLines > 0 || removedLines > 0)) {
        return `Added ${addedLines} lines, removed ${removedLines} lines in ${pathLabel}`;
      }
      if (pathLabel && replacements) return `Updated ${pathLabel} (${replacements} replacements)`;
      if (pathLabel) return `Updated ${pathLabel}`;
      break;
    }
    case 'read_file': {
      const pathLabel = getPathLabel(args.path);
      if (pathLabel) return `Read ${pathLabel}`;
      break;
    }
  }

  if (parsed?.ok === true && typeof parsed.path === 'string') {
    return `Updated ${getPathLabel(parsed.path) ?? parsed.path}`;
  }

  return undefined;
}

function buildToolArgumentsSummary(toolName: string, args: Record<string, unknown>): string | undefined {
  switch (toolName) {
    case 'bash': {
      const command = typeof args.command === 'string' ? normalizeText(args.command) : '';
      return command ? truncate(command, 180) : undefined;
    }
    case 'write_file': {
      const pathLabel = getPathLabel(args.path);
      const content = typeof args.content === 'string' ? args.content : '';
      const lineCount = countLines(content);
      return pathLabel ? `${pathLabel} | ${lineCount} lines` : undefined;
    }
    case 'edit_file': {
      const pathLabel = getPathLabel(args.path);
      const oldString = typeof args.old_string === 'string' ? args.old_string : '';
      const newString = typeof args.new_string === 'string' ? args.new_string : '';
      if (!pathLabel) return undefined;
      return `${pathLabel} | -${countLines(oldString)} +${countLines(newString)}`;
    }
    case 'read_file': {
      const pathLabel = getPathLabel(args.path);
      const limit = typeof args.limit === 'number' ? args.limit : undefined;
      return pathLabel ? `${pathLabel}${limit ? ` | first ${limit} lines` : ''}` : undefined;
    }
    default: {
      const argText = JSON.stringify(args, null, 2);
      return argText !== '{}' ? truncate(argText, 220) : undefined;
    }
  }
}

function buildToolCollapsedDetail(summary?: string, resultText?: string, errorText?: string): string | undefined {
  if (errorText) return `failed | ${truncate(errorText, 140)}`;
  if (summary) return summary;
  if (resultText) return `done | ${truncate(resultText, 140)}`;
  return undefined;
}

function buildPreviewLines(lines: string[], limit = 10): { previewLines?: string[]; previewOverflowCount?: number } {
  const normalized = lines
    .map((line) => line.replace(/\t/g, '  '))
    .filter((line, index, array) => !(index === array.length - 1 && line === ''));
  if (normalized.length === 0) return {};
  return {
    previewLines: normalized.slice(0, limit),
    previewOverflowCount: Math.max(0, normalized.length - limit),
  };
}

function buildToolPreview(toolName: string, args: Record<string, unknown>): {
  previewLines?: string[];
  previewOverflowCount?: number;
  alwaysShowPreview?: boolean;
  previewKind?: 'code' | 'diff';
} {
  if (toolName === 'write_file' && typeof args.content === 'string') {
    return { ...buildPreviewLines(getLineArray(args.content), 10), alwaysShowPreview: true, previewKind: 'code' };
  }

  if (toolName === 'edit_file') {
    const oldString = typeof args.old_string === 'string' ? args.old_string : '';
    const newString = typeof args.new_string === 'string' ? args.new_string : '';
    const preview: string[] = [];
    for (const line of getLineArray(oldString).slice(0, 5)) preview.push(`- ${line}`);
    for (const line of getLineArray(newString).slice(0, 5)) preview.push(`+ ${line}`);
    return { ...buildPreviewLines(preview, 10), alwaysShowPreview: true, previewKind: 'diff' };
  }

  return {};
}

function buildTodoCollapsedLines(lines: string[]): { lines: string[]; overflowCount: number } {
  if (lines.length <= 2) return { lines, overflowCount: 0 };
  const rank = (line: string): number => {
    if (line.startsWith('~')) return 0;
    if (line.startsWith('-')) return 1;
    if (line.startsWith('x')) return 2;
    return 3;
  };
  const prioritized = [...lines]
    .map((line, index) => ({ line, index }))
    .sort((left, right) => rank(left.line) - rank(right.line) || left.index - right.index)
    .slice(0, 2)
    .map((entry) => entry.line);
  return { lines: prioritized, overflowCount: lines.length - prioritized.length };
}

function buildProgressItem(liveStatus: CodexLiveStatus): CodexTimelineItemView | null {
  if (!liveStatus.isLoading) return null;
  const lines: string[] = [];
  if (liveStatus.status) lines.push(liveStatus.status);
  for (const detail of liveStatus.details ?? []) lines.push(detail);
  for (const completed of liveStatus.completed ?? []) lines.push(`Done: ${completed}`);
  if (liveStatus.running) lines.push(`Running: ${liveStatus.running}`);
  if (lines.length === 0) lines.push('Waiting for the next visible step');
  return {
    id: 'progress_live',
    kind: 'progress',
    label: liveStatus.running
      ? `Using ${humanizePhaseName(liveStatus.running)}`
      : liveStatus.tokenCount && liveStatus.tokenCount > 0
        ? 'Concocting...'
        : 'Working',
    elapsedText: buildDisplayStatsText(liveStatus.elapsedMs, liveStatus.tokenCount),
    lines,
  };
}

function materializeTurns(events: ThreadEvent[]): TimelineTurnState[] {
  const turns = new Map<string, TimelineTurnState>();
  const order: string[] = [];
  for (const event of events) {
    if (event.type === 'thread.started' || event.type === 'error') continue;
    const turnId = event.turn_id;
    if (!turns.has(turnId)) {
      turns.set(turnId, {
        turnId,
        status: 'running',
        itemOrder: [],
        itemState: new Map(),
      });
      order.push(turnId);
    }
    const turn = turns.get(turnId)!;
    if (event.type === 'item.started' || event.type === 'item.updated' || event.type === 'item.completed') {
      if (!turn.itemState.has(event.item.id)) turn.itemOrder.push(event.item.id);
      turn.itemState.set(event.item.id, event.item);
      continue;
    }
    if (event.type === 'turn.completed') {
      turn.status = 'completed';
      turn.stopReason = event.stop_reason;
      continue;
    }
    if (event.type === 'turn.failed') {
      turn.status = 'failed';
      turn.stopReason = event.error.message;
      turn.errorMessage = event.error.message;
    }
  }
  return order.map((turnId) => turns.get(turnId)!);
}

function buildTaskSummary(snapshot: CodexTaskSnapshot): string | undefined {
  const parts = [
    snapshot.counts.in_progress > 0 ? `${snapshot.counts.in_progress} active` : null,
    snapshot.counts.pending > 0 ? `${snapshot.counts.pending} pending` : null,
    snapshot.counts.completed > 0 ? `${snapshot.counts.completed} done` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(' | ') : undefined;
}

function buildTaskLines(snapshot: CodexTaskSnapshot): string[] {
  if (snapshot.tasks.length > 0) {
    return snapshot.tasks.map((task) => `${task.status === 'completed' ? 'x' : task.status === 'in_progress' ? '~' : '-'} ${task.subject}`);
  }
  const summary = buildTaskSummary(snapshot);
  return summary ? [summary] : ['No task details available'];
}

function buildTaskItem(snapshot: CodexTaskSnapshot): CodexTimelineItemView {
  const lines = buildTaskLines(snapshot);
  const collapsed = buildTodoCollapsedLines(lines);
  return {
    id: snapshot.sourceId,
    kind: 'todo_list',
    label: 'Plan',
    summary: buildTaskSummary(snapshot),
    lines,
    collapsedLines: collapsed.lines,
    overflowCount: collapsed.overflowCount,
  };
}

function materializeTaskSnapshots(turns: TimelineTurnState[], taskSnapshots: CodexTaskSnapshot[]): void {
  if (taskSnapshots.length === 0) return;
  const turnMap = new Map(turns.map((turn) => [turn.turnId, turn] as const));
  for (const snapshot of taskSnapshots) {
    const turn = turnMap.get(snapshot.turnId);
    if (!turn) continue;
    const hasNativeTodo = [...turn.itemState.values()].some((item) => item.type === 'todo_list');
    if (hasNativeTodo) continue;
    if (!turn.itemState.has(snapshot.sourceId)) turn.itemOrder.push(snapshot.sourceId);
    turn.itemState.set(snapshot.sourceId, {
      id: snapshot.sourceId,
      type: 'todo_list',
      items: snapshot.tasks.map((task) => ({
        text: task.subject,
        completed: task.status === 'completed',
      })),
    });
  }
}

function buildItemView(
  item: ThreadItem,
  taskSnapshot?: CodexTaskSnapshot,
  turnElapsedMs?: number,
): CodexTimelineItemView | null {
  switch (item.type) {
    case 'reasoning': {
      if (!normalizeText(item.text)) return null;
      return {
        id: item.id,
        kind: 'reasoning',
        label: turnElapsedMs ? `Thought for ${formatElapsed(turnElapsedMs)}` : 'Thought',
        text: truncate(item.text, 360),
      };
    }
    case 'agent_message': {
      if (!normalizeText(item.text)) return null;
      const blockCount = Math.max(1, Math.ceil(item.text.length / 260));
      return {
        id: item.id,
        kind: 'agent_message',
        label: 'Answer',
        meta: `${blockCount} block${blockCount === 1 ? '' : 's'}`,
        text: item.text,
      };
    }
    case 'tool_call': {
      if (item.status === 'failed') return null;
      const formattedLine = formatToolLine(item.tool_name, item.arguments);
      const headline = splitToolHeadline(formattedLine, item.tool_name);
      const resultSummary = buildToolResultSummary(item.tool_name, item.arguments, item.result);
      const preview = buildToolPreview(item.tool_name, item.arguments);
      return {
        id: item.id,
        kind: 'tool_call',
        label: buildToolTitle(item.tool_name, item.arguments, headline.label, item.result),
        status: item.status,
        statusLabel: formatToolStatus(item.status),
        summary: resultSummary ?? headline.summary,
        collapsedDetail: buildToolCollapsedDetail(
          resultSummary ?? headline.summary,
          item.result ? truncate(item.result, 260) : undefined,
          item.error ? truncate(item.error, 260) : undefined,
        ),
        argumentsText: buildToolArgumentsSummary(item.tool_name, item.arguments),
        resultText: resultSummary ?? (item.result ? truncate(item.result, 260) : undefined),
        errorText: item.error ? truncate(item.error, 260) : undefined,
        previewLines: preview.previewLines,
        previewOverflowCount: preview.previewOverflowCount,
        alwaysShowPreview: preview.alwaysShowPreview,
        previewKind: preview.previewKind,
      };
    }
    case 'todo_list':
      return taskSnapshot
        ? buildTaskItem(taskSnapshot)
        : (() => {
            const lines = item.items.map((todo) => `${todo.completed ? 'x' : '-'} ${todo.text}`);
            const collapsed = buildTodoCollapsedLines(lines);
            return {
              id: item.id,
              kind: 'todo_list',
              label: 'Plan',
              lines,
              collapsedLines: collapsed.lines,
              overflowCount: collapsed.overflowCount,
            };
          })();
    case 'error':
      return {
        id: item.id,
        kind: 'error',
        label: 'Run failed',
        text: item.message,
      };
    default:
      return null;
  }
}

function getSearchableText(item: CodexTimelineItemView): string {
  switch (item.kind) {
    case 'reasoning':
    case 'agent_message':
    case 'error':
      return `${item.label} ${item.text}`.trim();
    case 'tool_call':
      return [
        item.label,
        item.status,
        item.summary,
        item.argumentsText,
        item.resultText,
        item.errorText,
        ...(item.previewLines ?? []),
      ]
        .filter(Boolean)
        .join(' ');
    case 'todo_list':
      return [item.label, item.summary, ...item.lines].filter(Boolean).join(' ');
    case 'progress':
      return [item.label, item.elapsedText, ...item.lines].filter(Boolean).join(' ');
    default:
      return '';
  }
}

export function buildSearchExcerpt(text: string, query: string): string | null {
  if (!query) return null;
  const compact = text.replace(/\s+/g, ' ').trim();
  if (!compact) return null;
  const lowerText = compact.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const matchIndex = lowerText.indexOf(lowerQuery);
  if (matchIndex === -1) return null;
  const start = Math.max(0, matchIndex - 24);
  const end = Math.min(compact.length, matchIndex + query.length + 24);
  return `${start > 0 ? '...' : ''}${compact.slice(start, end)}${end < compact.length ? '...' : ''}`;
}

export function buildCodexTimelineState({
  events,
  liveStatus,
  messages,
  taskSnapshots = [],
  turnSnapshots = [],
}: BuildStateInput): CodexTimelineState {
  const locale: 'en' | 'zh' = 'en';
  const rawTurns = materializeTurns(events);
  materializeTaskSnapshots(rawTurns, taskSnapshots);

  const snapshotById = new Map(taskSnapshots.map((snapshot) => [snapshot.sourceId, snapshot] as const));
  const turnSnapshotById = new Map(turnSnapshots.map((snapshot) => [snapshot.turnId, snapshot] as const));

  const turns = rawTurns.map<CodexTimelineTurnView>((turn) => {
    const turnElapsedMs =
      turnSnapshotById.get(turn.turnId)?.elapsedMs ??
      (turn.status === 'running' ? liveStatus.elapsedMs : undefined);

    const items = turn.itemOrder
      .map((itemId) => turn.itemState.get(itemId))
      .filter((item): item is ThreadItem => Boolean(item))
      .map((item) => buildItemView(item, snapshotById.get(item.id), turnElapsedMs))
      .filter((item): item is CodexTimelineItemView => Boolean(item));

    if (turn.status === 'failed' && turn.errorMessage && !items.some((item) => item.kind === 'error')) {
      items.push({
        id: `turn_error_${turn.turnId}`,
        kind: 'error',
        label: 'Run failed',
        text: turn.errorMessage,
      });
    }

    return {
      turnId: turn.turnId,
      turnNumber: 0,
      status: turn.status,
      statusText: formatTurnStatus(turn.status, turn.stopReason),
      statsText: buildDisplayStatsText(
        turnSnapshotById.get(turn.turnId)?.elapsedMs,
        turnSnapshotById.get(turn.turnId)?.tokenCount,
      ),
      items,
    };
  });

  const progressItem = buildProgressItem(liveStatus);
  if (progressItem) {
    if (turns.length === 0) {
      turns.push({
        turnId: 'turn_live',
        turnNumber: 0,
        status: 'running',
        statusText: 'working',
        statsText: buildDisplayStatsText(liveStatus.elapsedMs, liveStatus.tokenCount),
        items: [progressItem],
      });
    } else {
      const lastTurn = turns[turns.length - 1]!;
      if (lastTurn.status === 'running') {
        lastTurn.statsText = buildDisplayStatsText(liveStatus.elapsedMs, liveStatus.tokenCount);
        lastTurn.items = [...lastTurn.items, progressItem];
      }
    }
  }

  turns.forEach((turn, index) => {
    turn.turnNumber = index + 1;
  });

  const blocks: CodexTimelineState['blocks'] = [];
  const searchDocuments: CodexSearchDocument[] = [];
  let turnIndex = 0;
  let pendingCommandOutput = false;

  for (const message of messages) {
    if (message.role === 'user') {
      blocks.push({
        id: `user:${message.id}`,
        kind: 'user_message',
        message: { id: message.id, text: message.text },
      });
      searchDocuments.push({
        id: `user:${message.id}`,
        text: message.text,
        target: { kind: 'user_message', messageId: message.id },
      });

      if (message.text.trim().startsWith('/')) {
        pendingCommandOutput = true;
        continue;
      }

      pendingCommandOutput = false;
      const nextTurn = turns[turnIndex];
      if (nextTurn) {
        blocks.push({ id: `turn:${nextTurn.turnId}`, kind: 'turn', turn: nextTurn });
        turnIndex += 1;
      }
      continue;
    }

    if (!normalizeText(message.text)) {
      pendingCommandOutput = false;
      continue;
    }

    const isCommandOutput = pendingCommandOutput || message.id.startsWith('cmd_');
    const hasRenderedTurns = turns.length > 0;
    const isFallbackAssistant = message.role === 'assistant' && !hasRenderedTurns;
    const shouldRenderAsPlainAssistant =
      isCommandOutput || message.role === 'system' || isFallbackAssistant;

    if (!shouldRenderAsPlainAssistant) continue;

    const normalizedMessage = normalizeText(message.text);
    const duplicatesTurnContent = turns.some((turn) =>
      turn.items.some(
        (item) =>
          (item.kind === 'reasoning' || item.kind === 'agent_message' || item.kind === 'error') &&
          isLikelyDuplicateText(item.text, normalizedMessage),
      ),
    );

    if (duplicatesTurnContent) {
      pendingCommandOutput = false;
      continue;
    }

    blocks.push({
      id: `assistant:${message.id}`,
      kind: 'assistant_message',
      message: { id: message.id, text: message.text, role: message.role },
    });
    searchDocuments.push({
      id: `assistant:${message.id}`,
      text: message.text,
      target: { kind: 'user_message', messageId: message.id },
    });
    pendingCommandOutput = false;
  }

  for (const turn of turns) {
    for (const item of turn.items) {
      searchDocuments.push({
        id: `item:${turn.turnId}:${item.id}`,
        text: getSearchableText(item),
        target: { kind: 'timeline_item', turnId: turn.turnId, itemId: item.id },
      });
    }
  }

  return {
    locale,
    blocks,
    turns,
    searchDocuments,
  };
}
