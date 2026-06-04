// ============================================================================
// TUI module tests
// ============================================================================

import { describe, it, expect, vi, afterEach } from 'vitest';

afterEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
});

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
      model: 'deepseek-v4-pro',
      maxTurns: 30,
    };
    expect(opts.model).toBe('deepseek-v4-pro');
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

  it('disables Ink immediate exit on Ctrl+C for interactive sessions', async () => {
    const renderMock = vi.fn(async () => ({
      waitUntilExit: vi.fn(async () => undefined),
    }));

    vi.doMock('../vendor/ink-renderer/index.js', () => ({
      render: renderMock,
    }));

    const mod = await import('../entry.js');
    await mod.renderTUI({
      model: 'deepseek-v4-pro',
      maxTurns: 30,
    });

    expect(renderMock).toHaveBeenCalledTimes(1);
    const firstCall = renderMock.mock.calls[0] as unknown[] | undefined;
    expect(firstCall?.[1]).toMatchObject({
      exitOnCtrlC: false,
    });
  });
});
