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

function usageBar(usedPct: number, width = 24): string {
  const clamped = Math.max(0, Math.min(100, usedPct));
  const used = Math.round((clamped / 100) * width);
  return `${'■'.repeat(used)}${'·'.repeat(Math.max(0, width - used))}`;
}

function categoryLine(name: string, tokens: number, contextWindow: number): string {
  return `  - ${name}: ${tokens.toLocaleString()} tokens (${pct(tokens, contextWindow)}%)`;
}

function toTreeLines(values: string[]): string[] {
  if (values.length === 0) return ['  (none)'];
  return values.map((value, index) => `${index === values.length - 1 ? '  └ ' : '  ├ '}${value}`);
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
  const bar = usageBar(usedPct);
  const memoryTokens = input.memoryTokens ?? input.memoryEntries.reduce((acc, item) => acc + item.tokens, 0);
  const skillsTokens = input.skillsTokens ?? input.skillEntries.reduce((acc, item) => acc + item.tokens, 0);
  const toolTokens = input.systemToolsTokens ?? input.toolEntries.reduce((acc, item) => acc + item.tokens, 0);
  const mcpToolTokens = input.mcpToolsTokens ?? input.toolEntries.filter((item) => item.isMcp).reduce((acc, item) => acc + item.tokens, 0);
  const conversationTokens = input.conversationTokens ?? input.messageTokens;
  const projectContextTokens = input.projectContextTokens ?? 0;
  const freeTokens = Math.max(0, input.contextWindow - input.estimatedTotalTokens);
  const providerReported = typeof input.providerReportedTokens === 'number'
    ? input.providerReportedTokens
    : null;
  const providerPct = providerReported !== null && input.contextWindow > 0
    ? ((providerReported / input.contextWindow) * 100).toFixed(1)
    : '0.0';
  const estimatedPct = input.contextWindow > 0
    ? ((input.estimatedTotalTokens / input.contextWindow) * 100).toFixed(1)
    : '0.0';

  const lines: string[] = [
    'Context Usage',
    `${bar}  ${input.modelName}`,
    `Estimated: ${input.estimatedTotalTokens.toLocaleString()}/${input.contextWindow.toLocaleString()} tokens (${estimatedPct}% used, ${leftPct}% left)`,
    `Provider-reported: ${(providerReported ?? 0).toLocaleString()}/${input.contextWindow.toLocaleString()} tokens (${providerPct}%)`,
    '',
    'Estimated usage by category',
    categoryLine('System prompt', input.systemPromptTokens, input.contextWindow),
    categoryLine('Project context', projectContextTokens, input.contextWindow),
    categoryLine('System tools', toolTokens, input.contextWindow),
    categoryLine('MCP tools', mcpToolTokens, input.contextWindow),
    categoryLine('Memory files', memoryTokens, input.contextWindow),
    categoryLine('Skills', skillsTokens, input.contextWindow),
    categoryLine('Messages', conversationTokens, input.contextWindow),
    categoryLine('Free space', freeTokens, input.contextWindow),
    '',
    `Session: ${input.sessionId} · Messages: ${input.messageCount} · UI messages: ${input.uiMessageCount}`,
  ];

  if (input.mode === 'overview') {
    lines.push('Groups: /context mcp · /context memory · /context skills · /context tools · /context all');
    return lines;
  }

  const includeAll = input.mode === 'all';

  if (includeAll || input.mode === 'mcp') {
    lines.push('', 'MCP tools · /mcp');
    lines.push(...toTreeLines(input.mcpConfigured.map((entry) => {
      const status = input.mcpStatuses.find((item) => item.id === entry.id);
      const state = status?.state ?? 'unknown';
      const err = status?.error ? ` · error: ${status.error}` : '';
      return `${entry.id} (${entry.plugin ?? 'user'}) · ${entry.command} · ${state}${err}`;
    })));
  }

  if (includeAll || input.mode === 'memory') {
    lines.push('', 'Memory files · /memory');
    lines.push(...toTreeLines(input.memoryEntries.map((entry) => `${entry.path}: ${entry.tokens.toLocaleString()} tokens`)));
  }

  if (includeAll || input.mode === 'skills') {
    lines.push('', 'Skills · /skills');
    const sorted = [...input.skillEntries].sort((a, b) => b.tokens - a.tokens).slice(0, 20);
    lines.push(...toTreeLines(sorted.map((entry) => `${entry.name}${entry.source ? ` (${entry.source})` : ''}: ~${entry.tokens} tokens`)));
  }

  if (includeAll || input.mode === 'tools') {
    lines.push('', 'System tools');
    const sorted = [...input.toolEntries].sort((a, b) => b.tokens - a.tokens).slice(0, 20);
    lines.push(...toTreeLines(sorted.map((entry) => `${entry.name}: ~${entry.tokens} tokens${entry.isMcp ? ' (mcp)' : ''}`)));
  }

  return lines;
}
