import { describe, expect, it } from 'vitest';
import { TuiStreamAssembler } from '../vendor/shared/stream-assembler.js';

describe('TuiStreamAssembler', () => {
  it('replaces malformed streamed text with finalized text and clears the run', () => {
    const assembler = new TuiStreamAssembler();

    const streamed = assembler.ingestDelta(
      'run-1',
      { content: [{ type: 'text', text: 'hello **wor' }] },
      false,
    );

    expect(streamed).toBe('hello **wor');
    expect(assembler.activeRuns).toBe(1);

    const finalized = assembler.finalize(
      'run-1',
      { content: [{ type: 'text', text: 'hello world' }] },
      false,
    );

    expect(finalized).toBe('hello world');
    expect(assembler.activeRuns).toBe(0);
  });

  it('falls back to streamed text when final content is empty', () => {
    const assembler = new TuiStreamAssembler();

    assembler.ingestDelta(
      'run-2',
      { content: [{ type: 'text', text: 'partial streamed answer' }] },
      false,
    );

    const finalized = assembler.finalize(
      'run-2',
      { content: [{ type: 'text', text: '' }] },
      false,
    );

    expect(finalized).toBe('partial streamed answer');
    expect(assembler.activeRuns).toBe(0);
  });
});
