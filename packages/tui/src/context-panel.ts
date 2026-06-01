export type ContextMode = 'overview' | 'mcp' | 'memory' | 'skills' | 'tools' | 'all';

export type MemoryTokenEntry = { path: string; tokens: number };
export type SkillTokenEntry = { name: string; tokens: number; source?: string };
export type ToolTokenEntry = { name: string; tokens: number; isMcp: boolean };
export type McpConfiguredEntry = { id: string; plugin?: string; command: string };
export type McpStatusEntry = {
  id: string;
  state: string;
  serverName?: string;
  toolCount?: number;
  resourceCount?: number;
  error?: string;
};

export type ContextPanelInput = {
  mode: ContextMode;
  modelName: string;
  sessionId: string;
  messageCount: number;
  uiMessageCount: number;
  contextWindow: number;
  estimatedTotalTokens: number;
  providerReportedTokens?: number;
  systemPromptTokens: number;
  messageTokens: number;
  projectContextTokens?: number;
  systemToolsTokens?: number;
  mcpToolsTokens?: number;
  memoryTokens?: number;
  skillsTokens?: number;
  conversationTokens?: number;
  memoryEntries: MemoryTokenEntry[];
  skillEntries: SkillTokenEntry[];
  toolEntries: ToolTokenEntry[];
  mcpConfigured: McpConfiguredEntry[];
  mcpStatuses: McpStatusEntry[];
};

function pct(tokens: number, contextWindow: number): string {
  return contextWindow > 0 ? ((tokens / contextWindow) * 100).toFixed(1) : '0.0';
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    const m = tokens / 1_000_000;
    return `${m === Math.round(m) ? Math.round(m) : m.toFixed(1)}m`;
  }
  if (tokens >= 1_000) {
    const k = tokens / 1_000;
    return `${k === Math.round(k) ? Math.round(k) : k.toFixed(1)}k`;
  }
  return String(tokens);
}

/** Build a 20-cell context grid like CC's ⛀⛁⛶ visualization. */
function contextGrid(usedPct: number, width = 20): string {
  const clamped = Math.max(0, Math.min(100, usedPct));
  const filled = Math.round((clamped / 100) * width);
  const cells: string[] = [];
  for (let i = 0; i < width; i++) {
    if (i < filled) {
      cells.push(i % 3 === 0 ? '⛀' : '⛁');
    } else {
      cells.push('⛶');
    }
  }
  return cells.join(' ');
}

function toTreeLines(values: string[]): string[] {
  if (values.length === 0) return ['  (none)'];
  return values.map((value, index) => `${index === values.length - 1 ? '└' : '├'} ${value}`);
}

function normalizeMode(raw?: string): ContextMode {
  const value = (raw ?? '').trim().toLowerCase();
  if (value === 'mcp' || value === 'memory' || value === 'skills' || value === 'tools' || value === 'all') {
    return value;
  }
  return 'overview';
}

export function resolveContextMode(args: string[]): ContextMode {
  return normalizeMode(args[0]);
}

export function buildContextPanelLines(input: ContextPanelInput): string[] {
  const usedPct = input.contextWindow > 0
    ? Math.round((input.estimatedTotalTokens / input.contextWindow) * 100)
    : 0;
  const leftPct = Math.max(0, 100 - usedPct);
  const grid = contextGrid(usedPct);
  const memoryTokens = input.memoryTokens ?? input.memoryEntries.reduce((acc, item) => acc + item.tokens, 0);
  const skillsTokens = input.skillsTokens ?? input.skillEntries.reduce((acc, item) => acc + item.tokens, 0);
  const toolTokens = input.systemToolsTokens ?? input.toolEntries.reduce((acc, item) => acc + item.tokens, 0);
  const mcpToolTokens = input.mcpToolsTokens ?? input.toolEntries.filter((item) => item.isMcp).reduce((acc, item) => acc + item.tokens, 0);
  const conversationTokens = input.conversationTokens ?? input.messageTokens;
  const projectContextTokens = input.projectContextTokens ?? 0;
  const freeTokens = Math.max(0, input.contextWindow - input.estimatedTotalTokens);
  const totalFmt = formatTokens(input.estimatedTotalTokens);
  const windowFmt = formatTokens(input.contextWindow);

  // Category breakdown lines (CC style: ⛁ name: Xk tokens (Y%))
  const categoryLines = [
    `⛁ System prompt: ${formatTokens(input.systemPromptTokens)} tokens (${pct(input.systemPromptTokens, input.contextWindow)}%)`,
    `⛁ System tools: ${formatTokens(toolTokens)} tokens (${pct(toolTokens, input.contextWindow)}%)`,
    `⛁ MCP tools: ${formatTokens(mcpToolTokens)} tokens (${pct(mcpToolTokens, input.contextWindow)}%)`,
    ...(projectContextTokens > 0 ? [`⛁ Project context: ${formatTokens(projectContextTokens)} tokens (${pct(projectContextTokens, input.contextWindow)}%)`] : []),
    `⛁ Memory files: ${formatTokens(memoryTokens)} tokens (${pct(memoryTokens, input.contextWindow)}%)`,
    `⛁ Skills: ${formatTokens(skillsTokens)} tokens (${pct(skillsTokens, input.contextWindow)}%)`,
    `⛁ Messages: ${formatTokens(conversationTokens)} tokens (${pct(conversationTokens, input.contextWindow)}%)`,
    `⛶ Free space: ${formatTokens(freeTokens)} (${leftPct}%)`,
  ];

  // Grid lines: 4 rows of 5 cells each, with category info on the right
  const gridCells = grid.split(' ');
  const gridRows: string[] = [];
  for (let row = 0; row < 4; row++) {
    const rowCells = gridCells.slice(row * 5, row * 5 + 5).join(' ');
    const rightCol = row === 0 ? `  ${input.modelName}`
      : row === 1 ? `  ${totalFmt}/${windowFmt} tokens (${usedPct}%)`
      : row === 2 ? ''
      : '';
    gridRows.push(`  ${rowCells}${rightCol}`);
  }

  const lines: string[] = [
    'Context Usage',
    ...gridRows,
    '',
    '  Estimated usage by category',
    ...categoryLines.map((line) => `  ${line}`),
  ];

  if (input.mode === 'overview') {
    lines.push('', '  Groups: /context mcp · /context memory · /context skills · /context tools · /context all');
    return lines;
  }

  const includeAll = input.mode === 'all';

  if (includeAll || input.mode === 'mcp') {
    lines.push('', '  MCP tools · /mcp');
    lines.push(...toTreeLines(input.mcpConfigured.map((entry) => {
      const status = input.mcpStatuses.find((item) => item.id === entry.id);
      const err = status?.error ? ` · error: ${status.error}` : '';
      return `${entry.id}: ${formatTokens(status?.toolCount ? status.toolCount * 100 : 0)} tokens${err}`;
    })).map((l) => `  ${l}`));
  }

  if (includeAll || input.mode === 'memory') {
    lines.push('', '  Memory files · /memory');
    lines.push(...toTreeLines(input.memoryEntries.map((entry) => {
      const name = entry.path.split(/[/\\]/).pop() ?? entry.path;
      return `${name}: ${formatTokens(entry.tokens)} tokens`;
    })).map((l) => `  ${l}`));
  }

  if (includeAll || input.mode === 'skills') {
    lines.push('', '  Skills · /skills');
    const sorted = [...input.skillEntries].sort((a, b) => b.tokens - a.tokens).slice(0, 20);
    lines.push(...toTreeLines(sorted.map((entry) => `${entry.name}: ~${formatTokens(entry.tokens)} tokens`)).map((l) => `  ${l}`));
  }

  if (includeAll || input.mode === 'tools') {
    lines.push('', '  System tools');
    const sorted = [...input.toolEntries].sort((a, b) => b.tokens - a.tokens).slice(0, 20);
    lines.push(...toTreeLines(sorted.map((entry) => `${entry.name}: ~${formatTokens(entry.tokens)} tokens`)).map((l) => `  ${l}`));
  }

  return lines;
}
