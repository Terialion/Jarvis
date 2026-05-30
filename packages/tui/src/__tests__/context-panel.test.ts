import { describe, expect, it } from 'vitest';
import { buildContextPanelLines, resolveContextMode } from '../context-panel.js';

describe('resolveContextMode', () => {
  it('defaults to overview for unknown mode', () => {
    expect(resolveContextMode([])).toBe('overview');
    expect(resolveContextMode(['weird'])).toBe('overview');
  });

  it('resolves known subgroup modes', () => {
    expect(resolveContextMode(['mcp'])).toBe('mcp');
    expect(resolveContextMode(['memory'])).toBe('memory');
    expect(resolveContextMode(['skills'])).toBe('skills');
    expect(resolveContextMode(['tools'])).toBe('tools');
    expect(resolveContextMode(['all'])).toBe('all');
  });
});

describe('buildContextPanelLines', () => {
  const baseInput = {
    mode: 'overview' as const,
    modelName: 'qwen3.6-reasoner',
    sessionId: 'b3af-2d7',
    messageCount: 42,
    uiMessageCount: 3,
    contextWindow: 200_000,
    estimatedTotalTokens: 24_900,
    providerReportedTokens: 22_500,
    systemPromptTokens: 1_600,
    messageTokens: 1_400,
    memoryEntries: [{ path: 'CLAUDE.md', tokens: 745 }],
    skillEntries: [{ name: 'verification-before-completion', tokens: 90, source: 'plugin' }],
    toolEntries: [
      { name: 'read_file', tokens: 120, isMcp: false },
      { name: 'mcp_status', tokens: 210, isMcp: true },
    ],
    mcpConfigured: [{ id: 'filesystem', plugin: 'common-mcp-smoke', command: 'pnpm' }],
    mcpStatuses: [{ id: 'filesystem', state: 'failed', error: 'spawn pnpm ENOENT' }],
  };

  it('returns compact overview with category totals', () => {
    const lines = buildContextPanelLines(baseInput);
    expect(lines[0]).toBe('Context Usage');
    expect(lines.join('\n')).toContain('Estimated: 24,900/200,000 tokens');
    expect(lines.join('\n')).toContain('Provider-reported: 22,500/200,000 tokens');
    expect(lines.join('\n')).toContain('Estimated usage by category');
    expect(lines.join('\n')).toContain('Groups: /context mcp');
  });

  it('includes MCP subgroup details', () => {
    const lines = buildContextPanelLines({ ...baseInput, mode: 'mcp' });
    const text = lines.join('\n');
    expect(text).toContain('MCP tools · /mcp');
    expect(text).toContain('filesystem (common-mcp-smoke)');
    expect(text).toContain('failed');
    expect(text).toContain('error: spawn pnpm ENOENT');
  });

  it('includes all subgroup blocks in all mode', () => {
    const lines = buildContextPanelLines({ ...baseInput, mode: 'all' });
    const text = lines.join('\n');
    expect(text).toContain('MCP tools · /mcp');
    expect(text).toContain('Memory files · /memory');
    expect(text).toContain('Skills · /skills');
    expect(text).toContain('System tools');
  });
});
