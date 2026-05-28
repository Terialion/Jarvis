import { describe, expect, it } from 'vitest';
import { buildCodexTimelineState } from '../presentation/codex-timeline-state.js';

describe('codex timeline tool card polish', () => {
  it('formats write_file as Write(path) with structured summary and default preview', () => {
    const content = [
      '/**',
      ' * Lightweight doc consistency check.',
      ' * Verifies README claims do not drift.',
      ' */',
      "import { readFileSync } from 'node:fs';",
      "import { join } from 'node:path';",
      "import { allBuiltinTools } from '../packages/tools/src/index.js';",
      'console.log(allBuiltinTools.length);',
      'export {};',
      'void 0;',
      'console.log("done");',
    ].join('\n');

    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_write' },
        {
          type: 'item.completed',
          turn_id: 'turn_write',
          item: {
            id: 'tool_write',
            type: 'tool_call',
            tool_name: 'write_file',
            status: 'completed',
            arguments: {
              path: 'scripts/check-doc-consistency.ts',
              content,
            },
            result: JSON.stringify({
              ok: true,
              path: 'scripts/check-doc-consistency.ts',
              existedBefore: false,
              bytesWritten: 240,
            }),
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    const tool = state.turns[0]?.items.find((item) => item.kind === 'tool_call');
    expect(tool?.kind).toBe('tool_call');
    if (tool?.kind === 'tool_call') {
      expect(tool.label).toBe('Write(check-doc-consistency.ts)');
      expect(tool.collapsedDetail).toBe('Wrote 11 lines to check-doc-consistency.ts');
      expect(tool.argumentsText).toBe('check-doc-consistency.ts | 11 lines');
      expect(tool.alwaysShowPreview).toBe(true);
      expect(tool.previewLines).toHaveLength(10);
      expect(tool.previewOverflowCount).toBe(1);
      expect(tool.previewLines?.[0]).toBe('/**');
      expect(tool.previewLines?.[1]).toContain('Lightweight doc consistency check');
    }
  });

  it('shows overwrite write_file operations as Update(path)', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_overwrite' },
        {
          type: 'item.completed',
          turn_id: 'turn_overwrite',
          item: {
            id: 'tool_overwrite',
            type: 'tool_call',
            tool_name: 'write_file',
            status: 'completed',
            arguments: {
              path: 'packages/cli/src/main.ts',
              content: ['one', 'two', 'three'].join('\n'),
            },
            result: JSON.stringify({
              ok: true,
              path: 'packages/cli/src/main.ts',
              existedBefore: true,
              bytesWritten: 12,
            }),
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    const tool = state.turns[0]?.items.find((item) => item.kind === 'tool_call');
    expect(tool?.kind).toBe('tool_call');
    if (tool?.kind === 'tool_call') {
      expect(tool.label).toBe('Update(packages\\cli\\src\\main.ts)');
      expect(tool.collapsedDetail).toBe('Replaced 3 lines in packages\\cli\\src\\main.ts');
    }
  });

  it('formats edit_file as Update(path) with added/removed counts and default diff preview', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_update' },
        {
          type: 'item.completed',
          turn_id: 'turn_update',
          item: {
            id: 'tool_update',
            type: 'tool_call',
            tool_name: 'edit_file',
            status: 'completed',
            arguments: {
              path: 'README.md',
              old_string: [
                'Jarvis ships with 22+ built-in tools across several categories:',
                '**Interaction:** ask_user_question, memory_search, memory_get',
                '**Extensibility:** skill.load, Skill (direct invocation), Agent (subagent delegation), MCP resource/tool exposure',
              ].join('\n'),
              new_string: [
                'Jarvis ships with built-in tools across several categories (exact count varies by configuration).',
                '**Interaction:** ask_user_question',
                '**Extensibility:** skill.load, Skill (direct invocation), Agent (subagent delegation), MCP resource/tool exposure, memory_search, memory_get (registered at runtime)',
              ].join('\n'),
            },
            result: JSON.stringify({
              ok: true,
              path: 'README.md',
              replacements: 3,
            }),
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    const tool = state.turns[0]?.items.find((item) => item.kind === 'tool_call');
    expect(tool?.kind).toBe('tool_call');
    if (tool?.kind === 'tool_call') {
      expect(tool.label).toBe('Update(README.md)');
      expect(tool.collapsedDetail).toBe('Added 3 lines, removed 3 lines in README.md');
      expect(tool.argumentsText).toBe('README.md | -3 +3');
      expect(tool.alwaysShowPreview).toBe(true);
      expect(tool.previewLines?.[0]).toMatch(/^- /);
      expect(tool.previewLines?.at(-1)).toMatch(/^\+ /);
    }
  });

  it('uses compact english thought and progress labels', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_live' },
        {
          type: 'item.started',
          turn_id: 'turn_live',
          item: {
            id: 'reason_live',
            type: 'reasoning',
            text: 'Let me inspect the repo before editing files.',
          },
        },
      ],
      liveStatus: {
        isLoading: true,
        elapsedMs: 2_000,
        tokenCount: 168,
      },
      turnSnapshots: [{ turnId: 'turn_live', elapsedMs: 2_000, tokenCount: 168 }],
      messages: [],
    });

    const reasoning = state.turns[0]?.items.find((item) => item.kind === 'reasoning');
    const progress = state.turns[0]?.items.find((item) => item.kind === 'progress');
    expect(reasoning?.kind).toBe('reasoning');
    expect(progress?.kind).toBe('progress');
    if (reasoning?.kind === 'reasoning') {
      expect(reasoning.label).toBe('Thought for 2s');
    }
    if (progress?.kind === 'progress') {
      expect(progress.label).toBe('Concocting...');
      expect(progress.elapsedText).toBe('2s · ↓168 tokens');
    }
  });
});
