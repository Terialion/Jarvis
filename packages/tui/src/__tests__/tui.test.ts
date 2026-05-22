// ============================================================================
// TUI module tests
// ============================================================================

import { describe, it, expect } from 'vitest';

describe('TUI module exports', () => {
  it('exports renderTUI', async () => {
    const mod = await import('../index.js');
    expect(mod.renderTUI).toBeDefined();
    expect(typeof mod.renderTUI).toBe('function');
  });

  it('exports TUIOptions type', async () => {
    const opts: import('../types.js').TUIOptions = {
      model: 'test-model',
      apiKey: 'sk-test',
      maxTurns: 10,
    };
    expect(opts.model).toBe('test-model');
    expect(opts.maxTurns).toBe(10);
  });
});

describe('TUIOptions type', () => {
  it('accepts minimal config', () => {
    const opts: import('../types.js').TUIOptions = {
      model: 'deepseek-chat',
      maxTurns: 30,
    };
    expect(opts.model).toBe('deepseek-chat');
    expect(opts.apiKey).toBeUndefined();
    expect(opts.baseURL).toBeUndefined();
    expect(opts.systemPrompt).toBeUndefined();
  });

  it('accepts full config', () => {
    const opts: import('../types.js').TUIOptions = {
      model: 'gpt-4',
      apiKey: 'sk-abc',
      baseURL: 'https://api.openai.com/v1',
      maxTurns: 50,
      systemPrompt: 'You are helpful.',
    };
    expect(opts.model).toBe('gpt-4');
    expect(opts.apiKey).toBe('sk-abc');
    expect(opts.baseURL).toBe('https://api.openai.com/v1');
    expect(opts.maxTurns).toBe(50);
    expect(opts.systemPrompt).toBe('You are helpful.');
  });
});

describe('entry.tsx renderTUI', () => {
  it('is an async function', async () => {
    const mod = await import('../entry.js');
    expect(mod.renderTUI).toBeDefined();
    expect(typeof mod.renderTUI).toBe('function');
  });
});
