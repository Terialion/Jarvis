import { describe, it, expect } from 'vitest';
import { HookRegistry } from '../registry.js';
import type { HookSpec, HookContext } from '../models.js';

// ============================================================================
// Helpers
// ============================================================================

function makeSpec(overrides: Partial<HookSpec> = {}): HookSpec {
  return {
    name: 'test-hook',
    stage: 'pre_tool_use',
    handler: () => ({ allowed: true }),
    ...overrides,
  };
}

// ============================================================================
// HookRegistry
// ============================================================================

describe('HookRegistry', () => {
  let registry: HookRegistry;

  beforeEach(() => {
    registry = new HookRegistry();
  });

  // ========================================================================
  // Registration
  // ========================================================================

  it('registers and lists hooks', () => {
    registry.register(makeSpec({ name: 'hook-a', stage: 'pre_tool_use' }));
    registry.register(makeSpec({ name: 'hook-b', stage: 'session_start' }));

    expect(registry.size).toBe(2);
    expect(registry.list()).toEqual(['hook-a', 'hook-b']);
  });

  it('filters list by stage', () => {
    registry.register(makeSpec({ name: 'hook-a', stage: 'pre_tool_use' }));
    registry.register(makeSpec({ name: 'hook-b', stage: 'session_start' }));

    expect(registry.list('pre_tool_use')).toEqual(['hook-a']);
  });

  it('unregisters hooks by name', () => {
    registry.register(makeSpec({ name: 'hook-a' }));
    registry.register(makeSpec({ name: 'hook-b' }));

    const removed = registry.unregister('hook-a');
    expect(removed).toBe(true);
    expect(registry.size).toBe(1);
    expect(registry.list()).toEqual(['hook-b']);
  });

  it('unregister returns false for unknown name', () => {
    expect(registry.unregister('nope')).toBe(false);
  });

  it('clears all hooks', () => {
    registry.register(makeSpec());
    registry.register(makeSpec({ name: 'hook-b' }));
    registry.clear();
    expect(registry.size).toBe(0);
  });

  it('starts with size 0', () => {
    expect(registry.size).toBe(0);
    expect(registry.list()).toEqual([]);
  });

  // ========================================================================
  // Execution — allowed
  // ========================================================================

  it('runs matching hooks and returns allowed', async () => {
    const calls: string[] = [];
    registry.register(
      makeSpec({
        stage: 'pre_tool_use',
        handler: () => {
          calls.push('hook1');
          return { allowed: true };
        },
      }),
    );

    const result = await registry.run('pre_tool_use', {
      toolName: 'bash',
    });

    expect(result.allowed).toBe(true);
    expect(calls).toEqual(['hook1']);
  });

  it('runs hooks in registration order', async () => {
    const calls: string[] = [];
    registry.register(
      makeSpec({
        name: 'first',
        handler: () => {
          calls.push('first');
          return { allowed: true };
        },
      }),
    );
    registry.register(
      makeSpec({
        name: 'second',
        handler: () => {
          calls.push('second');
          return { allowed: true };
        },
      }),
    );

    await registry.run('pre_tool_use', { toolName: 'bash' });
    expect(calls).toEqual(['first', 'second']);
  });

  // ========================================================================
  // Execution — denied
  // ========================================================================

  it('stops at first denial', async () => {
    const calls: string[] = [];
    registry.register(
      makeSpec({
        name: 'first',
        handler: () => {
          calls.push('first');
          return { allowed: false, reason: 'blocked' };
        },
      }),
    );
    registry.register(
      makeSpec({
        name: 'second',
        handler: () => {
          calls.push('second');
          return { allowed: true };
        },
      }),
    );

    const result = await registry.run('pre_tool_use', {
      toolName: 'bash',
    });

    expect(result.allowed).toBe(false);
    expect(result.reason).toBe('blocked');
    expect(calls).toEqual(['first']); // second never runs
  });

  // ========================================================================
  // Execution — matcher
  // ========================================================================

  it('skips hooks with non-matching toolName', async () => {
    const calls: string[] = [];
    registry.register(
      makeSpec({
        matcher: { toolName: 'bash' },
        handler: () => {
          calls.push('bash-hook');
          return { allowed: true };
        },
      }),
    );
    registry.register(
      makeSpec({
        matcher: { toolName: 'read' },
        handler: () => {
          calls.push('read-hook');
          return { allowed: true };
        },
      }),
    );

    await registry.run('pre_tool_use', { toolName: 'read' });
    expect(calls).toEqual(['read-hook']);
  });

  it('runs hooks with no matcher for any tool', async () => {
    const calls: string[] = [];
    registry.register(
      makeSpec({
        handler: () => {
          calls.push('global');
          return { allowed: true };
        },
      }),
    );

    await registry.run('pre_tool_use', { toolName: 'bash' });
    expect(calls).toEqual(['global']);
  });

  // ========================================================================
  // Execution — different stages
  // ========================================================================

  it('only runs hooks for the requested stage', async () => {
    const calls: string[] = [];
    registry.register(
      makeSpec({
        stage: 'session_start',
        handler: () => {
          calls.push('session');
          return { allowed: true };
        },
      }),
    );
    registry.register(
      makeSpec({
        stage: 'pre_tool_use',
        handler: () => {
          calls.push('tool');
          return { allowed: true };
        },
      }),
    );

    await registry.run('session_start');
    expect(calls).toEqual(['session']);
  });

  // ========================================================================
  // Convenience methods
  // ========================================================================

  it('runPreToolUse delegates to run with pre_tool_use stage', async () => {
    let receivedStage = '';
    registry.register(
      makeSpec({
        stage: 'pre_tool_use',
        handler: (_ctx) => {
          receivedStage = 'pre_tool_use';
          return { allowed: true };
        },
      }),
    );

    await registry.runPreToolUse({ toolName: 'bash' });
    expect(receivedStage).toBe('pre_tool_use');
  });

  it('runPostToolUse swallows errors', async () => {
    registry.register(
      makeSpec({
        stage: 'post_tool_use',
        handler: () => {
          throw new Error('boom');
        },
      }),
    );

    const result = await registry.runPostToolUse({ toolName: 'bash' });
    expect(result.allowed).toBe(true);
  });

  // ========================================================================
  // Async handlers
  // ========================================================================

  it('supports async handlers', async () => {
    let called = false;
    registry.register(
      makeSpec({
        handler: async () => {
          await new Promise((r) => setTimeout(r, 5));
          called = true;
          return { allowed: true };
        },
      }),
    );

    const result = await registry.run('pre_tool_use', {});
    expect(result.allowed).toBe(true);
    expect(called).toBe(true);
  });

  // ========================================================================
  // HookContext
  // ========================================================================

  it('passes full context to handler', async () => {
    let captured: HookContext = {};
    registry.register(
      makeSpec({
        handler: (ctx) => {
          captured = ctx;
          return { allowed: true };
        },
      }),
    );

    await registry.run('pre_tool_use', {
      toolName: 'bash',
      toolArgs: { command: 'ls' },
      sessionId: 'sess_1',
      turnId: 'turn_1',
    });

    expect(captured.toolName).toBe('bash');
    expect(captured.toolArgs).toEqual({ command: 'ls' });
    expect(captured.sessionId).toBe('sess_1');
    expect(captured.turnId).toBe('turn_1');
  });
});
