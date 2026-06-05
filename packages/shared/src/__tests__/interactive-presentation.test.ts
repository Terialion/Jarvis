import { describe, expect, it } from 'vitest';
import { buildInlinePlanReviewText, buildPlanTaskSummaryLines, buildToolCardView, renderSlashResultText } from '../interactive-presentation.js';
import { buildCodexTimelineState, buildMainScreenStatusTextView, buildWelcomeScreenTextView, renderCodexTimelineBlocks } from '../codex-timeline.js';

describe('interactive presentation', () => {
  it('formats write tool cards with structured summary and preview', () => {
    const card = buildToolCardView({
      toolName: 'write_file',
      args: {
        path: 'scripts/check-doc-consistency.ts',
        content: ['alpha', 'beta', 'gamma'].join('\n'),
      },
      resultText: JSON.stringify({
        ok: true,
        path: 'scripts/check-doc-consistency.ts',
        existedBefore: false,
      }),
      status: 'completed',
    });

    expect(card.label).toMatch(/Write\(.*check-doc-consistency\.ts\)/);
    expect(card.collapsedDetail).toBe('Added 3 lines');
    expect(card.argumentsText).toMatch(/check-doc-consistency\.ts \| 3 lines/);
    expect(card.previewLines).toEqual(['alpha', 'beta', 'gamma']);
    expect(card.previewKind).toBe('code');
  });

  it('formats edit tool cards with compact diff preview', () => {
    const card = buildToolCardView({
      toolName: 'edit_file',
      args: {
        path: 'README.md',
        old_string: 'a\nb\nc',
        new_string: 'a\nx\nc',
      },
      resultText: JSON.stringify({ ok: true, replacements: 1 }),
      status: 'completed',
    });

    expect(card.label).toBe('Update(README.md)');
    expect(card.collapsedDetail).toBe('Added 3 lines, removed 3 lines');
    expect(card.argumentsText).toBe('README.md | -3 +3');
    expect(card.previewKind).toBe('diff');
    expect(card.previewLines?.[0]).toMatch(/1\s+- a/);
    expect(card.previewLines?.[1]).toMatch(/1\s+\+ a/);
  });

  it('serializes slash result blocks to plain text', () => {
    const text = renderSlashResultText([
      { kind: 'section', title: 'Context Usage', lines: ['Estimated: 12/200 tokens', 'Messages: 3'] },
      { kind: 'list', title: 'Groups', items: ['/context', '/mcp'] },
    ]);

    expect(text).toContain('Context Usage');
    expect(text).toContain('Estimated: 12/200 tokens');
    expect(text).toContain('- /context');
  });

  it('formats inline plan review text with stable separators', () => {
    const text = buildInlinePlanReviewText({
      summary: 'Create benchmark tool',
      steps: [
        { step: 'Inspect workspace', files: ['workspace'] },
        { step: 'Write script', verification: 'run benchmark once' },
      ],
      allowedPrompts: [{ tool: 'bash', prompt: 'Allow benchmark run' }],
    });

    expect(text).toContain('Updated plan: Create benchmark tool');
    expect(text).toContain('1. Inspect workspace | [workspace]');
    expect(text).toContain('2. Write script | verify: run benchmark once');
    expect(text).toContain('Required permissions:');
  });

  it('formats compact plan task summary lines for shell renderers', () => {
    const lines = buildPlanTaskSummaryLines({
      summary: 'Create benchmark tool',
      steps: [
        { step: 'Inspect workspace', files: ['workspace'] },
        { step: 'Write script', verification: 'run benchmark once' },
      ],
      allowedPrompts: [{ tool: 'Bash', prompt: 'Allow benchmark run' }],
    });

    expect(lines[0]).toBe('Task summary: Create benchmark tool');
    expect(lines[1]).toBe('2 steps');
    expect(lines[2]).toBe('1. Inspect workspace | 1 file');
    expect(lines[3]).toBe('2. Write script | has verification');
    expect(lines).toContain('Required permissions:');
    expect(lines.at(-1)).toBe('Review: [Enter] proceed | [e] edit | [c] cancel');
  });

  it('builds welcome screen text view with tips and model metadata', () => {
    const welcome = buildWelcomeScreenTextView({
      appName: 'Jarvis',
      subtitle: 'AI Coding Assistant',
      model: 'deepseek-v4-flash',
      tips: ['Send a prompt to begin', '/help for commands'],
    });

    expect(welcome.lines.length).toBeGreaterThan(5);
    expect(welcome.lines.some((line) => line.some((segment) => segment.content === 'Jarvis'))).toBe(true);
    expect(welcome.lines.some((line) => line.some((segment) => segment.content.includes('/help for commands')))).toBe(true);
  });

  it('renders codex timeline blocks as terminal-friendly text', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_1' },
        {
          type: 'item.completed',
          turn_id: 'turn_1',
          item: {
            id: 'reason_1',
            type: 'reasoning',
            text: 'Check the request, then respond.',
          },
        },
        {
          type: 'item.completed',
          turn_id: 'turn_1',
          item: {
            id: 'answer_1',
            type: 'agent_message',
            text: 'Hello from Jarvis.',
          },
        },
        {
          type: 'turn.completed',
          turn_id: 'turn_1',
          stop_reason: 'completed',
        },
      ],
      liveStatus: { isLoading: false },
      messages: [{ id: 'user_1', role: 'user', text: '你好' }],
    });

    const lines = renderCodexTimelineBlocks(state);
    expect(lines[0]).toBe('> You');
    expect(lines.some((line) => line.includes('| Turn 1 | completed | 2 items'))).toBe(true);
    expect(lines.some((line) => line.includes('| > Thought'))).toBe(true);
    expect(lines.some((line) => line.includes('| o Answer | 1 block'))).toBe(true);
  });

  it('builds status summary view with ctx and mcp lines', () => {
    const status = buildMainScreenStatusTextView({
      segments: [
        { content: 'project Jarvis', color: 'cyan' },
        { content: 'branch feature/ts-fullstack-migration', color: 'cyan' },
        { content: 'model deepseek-v4-flash', color: 'white' },
      ],
      viewportLabel: '[Live mode] Following output | pinned to the latest message',
      viewportColor: 'green',
      usedPercent: 3.5,
      leftPercent: 96.5,
      breakdownSegments: [
        { content: 'sys:708', color: 'cyan' },
        { content: 'msg:15.8K', color: 'green' },
      ],
      mcpSegments: [
        { content: '[MCP --]', color: 'gray' },
        { content: 'waiting for status', color: 'gray' },
      ],
    });

    expect(status.lines[1]?.[0]?.content).toContain('[Live mode]');
    expect(status.lines[2]?.map((segment) => segment.content).join('')).toContain('CTX [');
    expect(status.lines[3]?.[0]?.content).toBe('sys:708');
    expect(status.lines[4]?.[0]?.content).toBe('[MCP --]');
  });
});
