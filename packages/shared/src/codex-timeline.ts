import type { ThreadEvent, ThreadItem } from './thread-events.js';
import { buildToolCardView, type PresentationTextLine, type PresentationTextSegment } from './interactive-presentation.js';

function formatTokensCompact(value: number): string {
  if (value < 0) return '0';
  if (value < 1000) return String(value);
  if (value < 1_000_000) return formatWithUnit(value, 1_000, 'K');
  if (value < 1_000_000_000) return formatWithUnit(value, 1_000_000, 'M');
  return formatWithUnit(value, 1_000_000_000, 'B');
}

function formatWithUnit(value: number, divisor: number, unit: string): string {
  const divided = value / divisor;
  let decimals: number;
  if (divided < 10) decimals = 2;
  else if (divided < 100) decimals = 1;
  else decimals = 0;
  let formatted = divided.toFixed(decimals);
  if (formatted.includes('.')) {
    formatted = formatted.replace(/0+$/, '');
    if (formatted.endsWith('.')) formatted = formatted.slice(0, -1);
  }
  return `${formatted}${unit}`;
}

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
  | ({
      id: string;
      kind: 'tool_call';
    } & ReturnType<typeof buildToolCardView>)
  | {
      id: string;
      kind: 'agent_message';
      label: string;
      meta?: string;
      text: string;
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
    | { kind: 'user_message'; messageId: string }
    | { kind: 'timeline_item'; turnId: string; itemId: string };
};

export type CodexTimelineState = {
  locale: 'en' | 'zh';
  blocks: Array<
    | { id: string; kind: 'user_message'; message: CodexUserMessageView }
    | { id: string; kind: 'assistant_message'; message: CodexAssistantMessageView }
    | { id: string; kind: 'turn'; turn: CodexTimelineTurnView }
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
  if (stopReason === 'finalized_after_stagnation') return 'finalized after low progress';
  if (stopReason === 'finalized_after_rejections') return 'finalized after tool retries';
  if (stopReason === 'finalize_timeout') return 'stopped during finalization';
  if (stopReason === 'consecutive_rejections') return 'stopped after repeated retries';
  return `completed: ${stopReason}`;
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
    case 'reasoning':
      if (!normalizeText(item.text)) return null;
      return {
        id: item.id,
        kind: 'reasoning',
        label: turnElapsedMs ? `Thought for ${formatElapsed(turnElapsedMs)}` : 'Thought',
        text: truncate(item.text, 360),
      };
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
      const toolCard = buildToolCardView({
        toolName: item.tool_name,
        args: item.arguments,
        resultText: item.result,
        status: item.status,
        errorText: item.error,
      });
      if (item.status === 'failed' && !toolCard.mcpSource) return null;
      return { id: item.id, kind: 'tool_call', ...toolCard };
    }
    case 'todo_list':
      return taskSnapshot
        ? buildTaskItem(taskSnapshot)
        : (() => {
            const lines = item.items.map((todo: { text: string; completed: boolean }) => `${todo.completed ? 'x' : '-'} ${todo.text}`);
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
      return { id: item.id, kind: 'error', label: 'Run failed', text: item.message };
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
        item.mcpSource ? `mcp:${item.mcpSource}` : undefined,
        item.status,
        item.summary,
        item.argumentsText,
        item.resultText,
        item.errorText,
        item.failureReason,
        ...(item.previewLines ?? []),
      ]
        .filter(Boolean)
        .join(' ');
    case 'todo_list':
      return [item.label, item.summary, ...item.lines].filter(Boolean).join(' ');
    case 'progress':
      return [item.label, item.elapsedText, ...item.lines].filter(Boolean).join(' ');
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
      blocks.push({ id: `user:${message.id}`, kind: 'user_message', message: { id: message.id, text: message.text } });
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

export function renderCodexUserMessageLines(message: CodexUserMessageView): string[] {
  return ['> You', `  ${message.text}`];
}

export function renderCodexAssistantMessageLines(message: CodexAssistantMessageView): string[] {
  return ['o Jarvis', ...message.text.split('\n').map((line) => `  ${line}`)];
}

function renderPreviewLines(lines: string[]): string[] {
  return lines.map((line) => `      ${line}`);
}

function renderItemLines(item: CodexTimelineItemView): string[] {
  switch (item.kind) {
    case 'reasoning':
      return [
        `  | > ${item.label}${item.meta ? ` | ${item.meta}` : ''}`,
        '      Ctrl+O to inspect details',
        ...item.text.split('\n').map((line) => `      |  ${line}`),
      ];
    case 'agent_message':
      return [
        `  | o ${item.label}${item.meta ? ` | ${item.meta}` : ''}`,
        ...item.text.split('\n').map((line) => `      |  ${line}`),
      ];
    case 'tool_call': {
      const lines = [`  | * ${item.label} | ${item.statusLabel}`];
      if (item.collapsedDetail) lines.push(`      |  ${item.collapsedDetail}`);
      if (item.argumentsText) lines.push(`      |  ${item.argumentsText}`);
      if ((item.previewLines?.length ?? 0) > 0) {
        lines.push(...renderPreviewLines(item.previewLines!));
        if ((item.previewOverflowCount ?? 0) > 0) {
          lines.push(`      ... +${item.previewOverflowCount} more lines`);
        }
      }
      return lines;
    }
    case 'todo_list':
      return [
        `  | ~ ${item.label}${item.summary ? ` | ${item.summary}` : ''}`,
        ...(item.collapsedLines ?? item.lines).map((line) => `      ${line}`),
        ...(item.overflowCount ? [`      ... +${item.overflowCount} more`] : []),
      ];
    case 'error':
      return [`  | x ${item.label}`, ...item.text.split('\n').map((line) => `      ${line}`)];
    case 'progress':
      return [
        `  | ~ ${item.label}${item.elapsedText ? ` | ${item.elapsedText}` : ''}`,
        ...item.lines.map((line) => `      ${line}`),
      ];
  }
}

export function renderCodexTurnLines(turn: CodexTimelineTurnView): string[] {
  const header = `| Turn ${turn.turnNumber} | ${turn.statusText} | ${turn.items.length} item${turn.items.length === 1 ? '' : 's'}${turn.statsText ? ` | ${turn.statsText}` : ''}`;
  const lines = [header];
  for (const item of turn.items) {
    lines.push('', ...renderItemLines(item));
  }
  return lines;
}

export function renderCodexTimelineBlocks(state: CodexTimelineState): string[] {
  const lines: string[] = [];
  for (const block of state.blocks) {
    if (lines.length > 0) lines.push('');
    if (block.kind === 'user_message') {
      lines.push(...renderCodexUserMessageLines(block.message));
      continue;
    }
    if (block.kind === 'assistant_message') {
      lines.push(...renderCodexAssistantMessageLines(block.message));
      continue;
    }
    lines.push(...renderCodexTurnLines(block.turn));
  }
  return lines;
}

export type MainScreenTextColor = 'cyan' | 'green' | 'yellow' | 'red' | 'gray' | 'white' | 'blue';

export type MainScreenTextView = {
  lines: PresentationTextLine[];
};

export function buildWelcomeScreenTextView(input: {
  appName: string;
  subtitle?: string;
  model?: string;
  tips?: string[];
  color?: MainScreenTextColor;
}): MainScreenTextView {
  const color = input.color ?? 'cyan';
  const logo = [
    '     ███████     ',
    '   ███     ███   ',
    '  ██   ███   ██  ',
    ' ██   ██ ██   ██ ',
    ' ██   ██ ██   ██ ',
    '  ██   ███   ██  ',
    '   ███     ███   ',
    '     ███████     ',
  ];
  const info: PresentationTextLine[] = [
    [{ content: input.appName, color, bold: true }],
    ...(input.subtitle ? [[{ content: input.subtitle, color: 'gray' as const }]] : []),
    ...(input.model ? [[{ content: input.model, color: 'gray' as const }]] : []),
  ];
  const offset = 2;
  const lines: PresentationTextLine[] = logo.map((logoLine, index) => {
    const segments: PresentationTextSegment[] = [{ content: logoLine, color }];
    const infoLine = info[index - offset];
    if (infoLine) {
      segments.push({ content: '  ' });
      segments.push(...infoLine);
    }
    return segments;
  });
  if (input.tips?.length) {
    lines.push([]);
    lines.push(
      input.tips.reduce<PresentationTextSegment[]>((acc, tip, index) => {
        if (index > 0) acc.push({ content: ' · ', color: 'gray' });
        acc.push({ content: tip, color: 'gray' });
        return acc;
      }, []),
    );
  }
  return { lines };
}

function makeUsageBar(usedPercent?: number, width = 18): string {
  const normalized = Math.max(0, Math.min(100, usedPercent ?? 0));
  const filled = Math.round((normalized / 100) * width);
  return `[${'█'.repeat(filled)}${'░'.repeat(Math.max(0, width - filled))}]`;
}

export function buildMainScreenStatusTextView(input: {
  segments: PresentationTextSegment[];
  viewportLabel: string;
  viewportColor?: MainScreenTextColor;
  usedPercent?: number;
  leftPercent?: number;
  breakdownSegments?: PresentationTextSegment[];
  mcpSegments?: PresentationTextSegment[];
}): MainScreenTextView {
  const lines: PresentationTextLine[] = [
    input.segments,
    [{ content: input.viewportLabel, color: input.viewportColor ?? 'green', bold: true }],
  ];
  const used = Math.max(0, Math.min(100, input.usedPercent ?? 0));
  const left = Math.max(0, Math.min(100, input.leftPercent ?? 100));
  lines.push([
    { content: 'CTX ', color: 'gray' },
    { content: makeUsageBar(used), color: used >= 80 ? 'red' : used >= 60 ? 'yellow' : 'green' },
    { content: ` used ${used.toFixed(1)}% · left ${left.toFixed(1)}%`, color: 'gray' },
  ]);
  if (input.breakdownSegments?.length) lines.push(input.breakdownSegments);
  if (input.mcpSegments?.length) lines.push(input.mcpSegments);
  return { lines };
}

export function buildMainScreenHeaderSegments(input: {
  projectLabel: string;
  branch?: string | null;
  model: string;
  effort?: string;
  modeLabel?: string;
  modeColor?: MainScreenTextColor;
  stateLabel: string;
  stateColor?: MainScreenTextColor;
  totalTokens?: number;
  leftPercent?: number;
  elapsedText?: string;
  sessionSuffix?: string;
}): PresentationTextSegment[] {
  const segments: PresentationTextSegment[] = [
    { content: `project ${input.projectLabel}`, color: 'cyan' },
    ...(input.branch ? [{ content: `branch ${input.branch}`, color: 'cyan' as const }] : []),
    { content: `model ${input.model}`, color: 'white' },
    ...(input.effort ? [{ content: `effort ${input.effort}`, color: 'cyan' as const }] : []),
    ...(input.modeLabel ? [{ content: `mode ${input.modeLabel}`, color: input.modeColor ?? 'blue' }] : []),
    { content: `state ${input.stateLabel}`, color: input.stateColor ?? 'green' },
  ];
  if (typeof input.totalTokens === 'number' && typeof input.leftPercent === 'number') {
    segments.push({
      content: `${input.totalTokens.toLocaleString()} tok | ${input.leftPercent.toFixed(1)}% left`,
      color: input.totalTokens > 0 ? 'white' : 'gray',
    });
  }
  if (input.elapsedText) segments.push({ content: input.elapsedText, color: 'gray' });
  if (input.sessionSuffix) segments.push({ content: `session ${input.sessionSuffix}`, color: 'gray' });
  return segments;
}
