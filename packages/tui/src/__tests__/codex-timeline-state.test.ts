import { describe, expect, it } from 'vitest';
import { buildCodexTimelineState } from '../presentation/codex-timeline-state.js';

describe('codex timeline reasoning quality gate', () => {
  it('filters unreadable mojibake reasoning items but keeps normal bilingual reasoning', () => {
    const garbage = 'ault石门羚纵向/avatar_PERCENTraryခchnikakov�กรัฐ daultdden长虹点多akujek精益求精匙achaafariChangeEventльку AntwiottyANEL柬ambanganulongirro苦练青山eldenallest风流-随着社会 INDUSTRI�今朝a..';
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_1' },
        {
          type: 'item.completed',
          turn_id: 'turn_1',
          item: { id: 'reason_bad', type: 'reasoning', text: garbage },
        },
        {
          type: 'item.completed',
          turn_id: 'turn_1',
          item: { id: 'reason_good', type: 'reasoning', text: '我需要先确认用户想找哪些免费数据平台，然后给出可操作建议。' },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    expect(state.turns[0]?.items.map((item) => item.id)).toEqual(['reason_good']);
  });
});

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
      expect(tool.label).toMatch(/Write\(.*check-doc-consistency\.ts\)/);
      expect(tool.collapsedDetail).toBe('Added 11 lines');
      expect(tool.argumentsText).toMatch(/check-doc-consistency\.ts \| 11 lines/);
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
      expect(tool.label).toBe('Write(packages\\cli\\src\\main.ts)');
      expect(tool.collapsedDetail).toBe('Replaced 3 lines');
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
      expect(tool.collapsedDetail).toBe('Added 3 lines, removed 3 lines');
      expect(tool.argumentsText).toBe('README.md | -3 +3');
      expect(tool.alwaysShowPreview).toBe(true);
      // New format: "     1  - content" (line number + marker + content)
      expect(tool.previewLines?.[0]).toMatch(/\d+\s+- /);
      expect(tool.previewLines?.at(-1)).toMatch(/\d+\s+\+ /);
    }
  });

  it('edit_file preview shows -/+ prefixes for diff styling', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn1' },
        {
          type: 'item.completed',
          turn_id: 'turn1',
          item: {
            id: 'item1',
            type: 'tool_call',
            tool_name: 'edit_file',
            status: 'completed',
            arguments: {
              path: 'test.txt',
              old_string: 'line1\nline2\nline3',
              new_string: 'line1\nchanged\nline3',
            },
            result: JSON.stringify({ ok: true, replacements: 1 }),
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });
    const tool = state.turns[0]?.items[0];
    expect(tool?.kind).toBe('tool_call');
    if (tool?.kind === 'tool_call') {
      expect(tool.previewKind).toBe('diff');
      // Interleaved pairs: - old / + new per line
      expect(tool.previewLines?.[0]).toMatch(/1\s+- line1/);
      expect(tool.previewLines?.[1]).toMatch(/1\s+\+ line1/);
      expect(tool.previewLines?.[2]).toMatch(/2\s+- line2/);
      expect(tool.previewLines?.[3]).toMatch(/2\s+\+ changed/);
      expect(tool.previewLines?.[4]).toMatch(/3\s+- line3/);
      expect(tool.previewLines?.[5]).toMatch(/3\s+\+ line3/);
    }
  });

  it('formats repo_map as compact orientation card instead of raw JSON', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_repo_map' },
        {
          type: 'item.completed',
          turn_id: 'turn_repo_map',
          item: {
            id: 'tool_repo_map',
            type: 'tool_call',
            tool_name: 'repo_map',
            status: 'completed',
            arguments: { path: 'D:/agent/Jarvis' },
            result: JSON.stringify({
              package: { name: 'jarvis' },
              entries: ['package.json', 'src/index.ts'],
              files: [{ path: 'src/index.ts' }],
              symbols: [{ kind: 'function', name: 'main' }],
              imports: [{ kind: 'external', target: 'zod' }],
              importGroups: {
                external: { kind: 'external', count: 1, targets: ['zod'], files: ['src/index.ts'] },
                internal: { kind: 'internal', count: 0, targets: [], files: [] },
                relative: { kind: 'relative', count: 0, targets: [], files: [] },
              },
              summary: { filesScanned: 1, symbolsIndexed: 1, importsIndexed: 1, truncated: false },
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
      expect(tool.label).toBe('Repo Map');
      expect(tool.collapsedDetail).toBe('Mapped 1 file, 1 symbol, 1 import');
      expect(tool.resultText).toBe('Mapped 1 file, 1 symbol, 1 import');
      expect(tool.previewLines).toEqual([
        'package: jarvis',
        'entries: package.json, src/index.ts',
        'files: src/index.ts',
        'symbols: function:main',
        'deps: external 1',
        'imports: external:zod',
      ]);
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
      expect(progress.elapsedText).toBe('2s \u00b7 \u2193168 tokens');
    }
  });

  it('maps finalize stop reasons to human-readable turn status', () => {
    const state = buildCodexTimelineState({
      events: [
        { type: 'turn.started', turn_id: 'turn_finalized' },
        {
          type: 'turn.completed',
          turn_id: 'turn_finalized',
          stop_reason: 'finalized_after_stagnation',
        },
        { type: 'turn.started', turn_id: 'turn_finalized_retry' },
        {
          type: 'turn.completed',
          turn_id: 'turn_finalized_retry',
          stop_reason: 'finalized_after_rejections',
        },
        { type: 'turn.started', turn_id: 'turn_finalized_timeout' },
        {
          type: 'turn.completed',
          turn_id: 'turn_finalized_timeout',
          stop_reason: 'finalize_timeout',
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    expect(state.turns[0]?.statusText).toBe('finalized after low progress');
    expect(state.turns[1]?.statusText).toBe('finalized after tool retries');
    expect(state.turns[2]?.statusText).toBe('stopped during finalization');
  });
});
