/**
 * Snapshot test for AskUserQuestion component.
 * Renders with vitest's JSX transform and captures terminal output.
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { Writable } from 'node:stream';
import { renderSync } from '../vendor/ink-renderer/root.js';
import { AskUserQuestion } from '../vendor/ui/AskUserQuestion.js';
import type { AskQuestionDef } from '@jarvis/tools';

function renderToString(node: React.ReactNode): string {
  let output = '';
  const stream = new Writable({
    write(chunk: string | Buffer, _encoding: BufferEncoding, callback: (error?: Error | null) => void) {
      output += typeof chunk === 'string' ? chunk : chunk.toString('utf8');
      callback();
    },
  });

  const instance = renderSync(node, {
    stdout: stream as unknown as NodeJS.WriteStream,
    stdin: process.stdin,
    stderr: process.stderr,
    exitOnCtrlC: false,
    patchConsole: false,
  });

  // Let the render complete
  // Cleanup
  instance.unmount();
  try { instance.cleanup?.(); } catch { /* ignore */ }

  return output;
}

const singleSelect: AskQuestionDef = {
  question: 'Which library should we use for date formatting?',
  header: 'Date Library',
  options: [
    { label: 'dayjs', description: 'Lightweight (2KB), immutable API, great plugin system' },
    { label: 'date-fns', description: 'Tree-shakeable, functional style, 200+ functions' },
    { label: 'luxon', description: 'Full-featured, timezone support, Intl-based' },
  ],
};

const multiSelect: AskQuestionDef = {
  question: 'Which features do you want to enable?',
  header: 'Features',
  options: [
    { label: 'Dark mode', description: 'Full dark theme support' },
    { label: 'Notifications', description: 'Push notifications' },
    { label: 'Auto-save', description: 'Auto-save every 30s' },
  ],
  multiSelect: true,
};

const multiQuestion: AskQuestionDef[] = [
  {
    question: 'What authentication method should we use?',
    header: 'Auth',
    options: [
      { label: 'OAuth 2.0 + PKCE', description: 'Industry standard, supports social login' },
      { label: 'API Keys', description: 'Simplest, good for machine-to-machine' },
    ],
  },
  {
    question: 'How should we handle sessions?',
    header: 'Sessions',
    options: [
      { label: 'JWT (stateless)', description: 'Self-contained tokens' },
      { label: 'Database sessions', description: 'Server-side control' },
    ],
  },
];

describe('AskUserQuestion snapshot', () => {
  it('renders single-select question', () => {
    const output = renderToString(
      <AskUserQuestion
        questions={[singleSelect]}
        onSubmit={() => {}}
        onCancel={() => {}}
      />
    );
    console.log('\n=== Single-select ===\n' + output);
    expect(output).toBeTruthy();
    // Verify key visual elements
    expect(output).toContain('Date Library');
    expect(output).toContain('Which library should we use for date formatting?');
    expect(output).toContain('dayjs');
    expect(output).toContain('date-fns');
    expect(output).toContain('luxon');
    expect(output).toContain('Enter to confirm');
  });

  it('renders multi-select question', () => {
    const output = renderToString(
      <AskUserQuestion
        questions={[multiSelect]}
        onSubmit={() => {}}
        onCancel={() => {}}
      />
    );
    console.log('\n=== Multi-select ===\n' + output);
    expect(output).toBeTruthy();
    expect(output).toContain('Features');
    expect(output).toContain('Dark mode');
    expect(output).toContain('Notifications');
    expect(output).toContain('Auto-save');
    expect(output).toContain('Space to toggle');
  });

  it('renders multi-question flow (shows first question)', () => {
    const output = renderToString(
      <AskUserQuestion
        questions={multiQuestion}
        onSubmit={() => {}}
        onCancel={() => {}}
      />
    );
    console.log('\n=== Multi-question ===\n' + output);
    expect(output).toBeTruthy();
    expect(output).toContain('Auth');
    expect(output).toContain('(1/2)');
    expect(output).toContain('OAuth');
    expect(output).toContain('API Keys');
  });
});
