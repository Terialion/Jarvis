import type { ThreadEvent, ThreadItem } from '@jarvis/agent';
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
  if (shorter.length >= 12 && longer.includes(shorter)) {
    return true;
  }

  let prefixLength = 0;
  const limit = Math.min(a.length, b.length);
  while (prefixLength < limit && a[prefixLength] === b[prefixLength]) {
    prefixLength += 1;
  }

  return prefixLength >= 48 && Math.abs(a.length - b.length) <= 24;
}

function formatElapsed(elapsedMs?: number): string | undefined {
  if (!elapsedMs || elapsedMs < 0) return undefined;
  const elapsedSeconds = Math.floor(elapsedMs / 1000);
  if (elapsedSeconds < 60) return `${elapsedSeconds}s`;
  return `${Math.floor(elapsedSeconds / 60)}m ${(elapsedSeconds % 60).toString().padStart(2, '0')}s`;
}

function formatTurnStatus(
  status: CodexTimelineTurnView['status'],
  stopReason?: string,
): string {
  if (status === 'running') return 'working';
  if (status === 'failed') return stopReason ? `failed: ${stopReason}` : 'failed';
  return stopReason ? `completed: ${stopReason}` : 'completed';
}

function formatToolStatus(status: string): string {
  switch (status) {
    case 'completed':
      return 'done';
    case 'failed':
      return 'failed';
    case 'running':
      return 'running';
    default:
      return status;
  }
}

function splitToolHeadline(summary: string, fallback: string): { label: string; summary?: string } {
  const separatorIndex = summary.indexOf(': ');
  if (separatorIndex === -1) {
    return {
      label: fallback,
      summary: summary === fallback ? undefined : summary,
    };
  }

  return {
    label: summary.slice(0, separatorIndex),
    summary: summary.slice(separatorIndex + 2),
  };
}

function buildToolCollapsedDetail(args: {
  status: string;
  summary?: string;
  resultText?: string;
  errorText?: string;
}): string | undefined {
  if (args.errorText) {
    return `failed | ${truncate(args.errorText, 140)}`;
  }
  if (args.summary) {
    return args.summary;
  }
  if (args.status === 'completed' && args.resultText) {
    return `done | ${truncate(args.resultText, 140)}`;
  }
  return undefined;
}

function buildTodoCollapsedLines(lines: string[]): { lines: string[]; overflowCount: number } {
  if (lines.length <= 2) {
    return { lines, overflowCount: 0 };
  }

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

  return {
    lines: prioritized,
    overflowCount: lines.length - prioritized.length,
  };
}

function buildProgressItem(liveStatus: CodexLiveStatus): CodexTimelineItemView | null {
  if (!liveStatus.isLoading) return null;

  const lines: string[] = [];
  if (liveStatus.status) lines.push(liveStatus.status);
  for (const detail of liveStatus.details ?? []) {
    lines.push(detail);
  }
  for (const completed of liveStatus.completed ?? []) {
    lines.push(`Done: ${completed}`);
  }
  if (liveStatus.running) {
    lines.push(`Running: ${liveStatus.running}`);
  }
  if (liveStatus.tokenCount && liveStatus.tokenCount > 0) {
    lines.push(
      `Generated ${liveStatus.tokenCount >= 1000 ? `${(liveStatus.tokenCount / 1000).toFixed(1)}K` : liveStatus.tokenCount} tokens`,
    );
  }
  if (lines.length === 0) {
    lines.push('Waiting for the next visible step');
  }

  return {
    id: 'progress_live',
    kind: 'progress',
    label: liveStatus.verb || 'Working',
    elapsedText: formatElapsed(liveStatus.elapsedMs),
    lines,
  };
}

function materializeTurns(events: ThreadEvent[]): TimelineTurnState[] {
  const turns = new Map<string, TimelineTurnState>();
  const order: string[] = [];

  for (const event of events) {
    if (event.type === 'thread.started' || event.type === 'error') {
      continue;
    }

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
      if (!turn.itemState.has(event.item.id)) {
        turn.itemOrder.push(event.item.id);
      }
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

function materializeTaskSnapshots(
  turns: TimelineTurnState[],
  taskSnapshots: CodexTaskSnapshot[],
): void {
  if (taskSnapshots.length === 0) return;

  const turnMap = new Map(turns.map((turn) => [turn.turnId, turn] as const));
  for (const snapshot of taskSnapshots) {
    const turn = turnMap.get(snapshot.turnId);
    if (!turn) continue;

    const hasNativeTodo = [...turn.itemState.values()].some((item) => item.type === 'todo_list');
    if (hasNativeTodo) continue;

    if (!turn.itemState.has(snapshot.sourceId)) {
      turn.itemOrder.push(snapshot.sourceId);
    }
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

function buildItemView(item: ThreadItem, taskSnapshot?: CodexTaskSnapshot): CodexTimelineItemView | null {
  switch (item.type) {
    case 'reasoning':
      {
        if (!normalizeText(item.text)) return null;
        const stepCount = Math.max(1, Math.ceil(item.text.length / 160));
        return {
          id: item.id,
          kind: 'reasoning',
          label: 'Thinking',
          meta: `${stepCount} step${stepCount === 1 ? '' : 's'}`,
          text: truncate(item.text, 360),
        };
      }
    case 'agent_message':
      {
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
      if (item.status === 'failed') {
        return null;
      }
      const formattedLine = formatToolLine(item.tool_name, item.arguments);
      const headline = splitToolHeadline(formattedLine, item.tool_name);
      const argText = JSON.stringify(item.arguments, null, 2);
      return {
        id: item.id,
        kind: 'tool_call',
        label: headline.label,
        status: item.status,
        statusLabel: formatToolStatus(item.status),
        summary: headline.summary,
        collapsedDetail: buildToolCollapsedDetail({
          status: item.status,
          summary: headline.summary,
          resultText: item.result ? truncate(item.result, 260) : undefined,
          errorText: item.error ? truncate(item.error, 260) : undefined,
        }),
        argumentsText: argText !== '{}' ? truncate(argText, 220) : undefined,
        resultText: item.result ? truncate(item.result, 260) : undefined,
        errorText: item.error ? truncate(item.error, 260) : undefined,
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
        label: 'Error',
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
      ].filter(Boolean).join(' ');
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
  const prefix = start > 0 ? '...' : '';
  const suffix = end < compact.length ? '...' : '';
  return `${prefix}${compact.slice(start, end)}${suffix}`;
}

export function buildCodexTimelineState({
  events,
  liveStatus,
  messages,
  taskSnapshots = [],
}: BuildStateInput): CodexTimelineState {
  const rawTurns = materializeTurns(events);
  materializeTaskSnapshots(rawTurns, taskSnapshots);
  const snapshotById = new Map(taskSnapshots.map((snapshot) => [snapshot.sourceId, snapshot] as const));

  const turns = rawTurns.map<CodexTimelineTurnView>((turn) => {
    const items = turn.itemOrder
      .map((itemId) => turn.itemState.get(itemId))
      .filter((item): item is ThreadItem => Boolean(item))
      .map((item) => buildItemView(item, snapshotById.get(item.id)))
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
        items: [progressItem],
      });
    } else {
      const lastTurn = turns[turns.length - 1]!;
      if (lastTurn.status === 'running') {
        lastTurn.items = [...lastTurn.items, progressItem];
      }
    }
  }

  turns.forEach((turn, index) => {
    turn.turnNumber = index + 1;
  });

  const blocks: CodexTimelineState["blocks"] = [];
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
        blocks.push({
          id: `turn:${nextTurn.turnId}`,
          kind: 'turn',
          turn: nextTurn,
        });
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
    const isFallbackAssistant =
      message.role === 'assistant' &&
      !hasRenderedTurns;
    const shouldRenderAsPlainAssistant =
      isCommandOutput ||
      message.role === 'system' ||
      isFallbackAssistant;

    if (!shouldRenderAsPlainAssistant) {
      continue;
    }

    const normalizedMessage = normalizeText(message.text);
    const duplicatesTurnContent = turns.some((turn) =>
      turn.items.some((item) =>
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
        target: {
          kind: 'timeline_item',
          turnId: turn.turnId,
          itemId: item.id,
        },
      });
    }
  }

  return {
    blocks,
    turns,
    searchDocuments,
  };
}
