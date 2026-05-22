import { describe, it, expect } from 'vitest';
import { HookRegistry } from '@jarvis/hooks';
import type { HookStage, HookResult } from '@jarvis/hooks';

describe('E2E: Hooks', () => {
  it('registers and fires pre_tool_use hook', async () => {
    const registry = new HookRegistry();
    const fired: string[] = [];

    registry.register({
      name: 'test-pre-tool',
      stage: 'pre_tool_use',
      handler: async (ctx) => {
        fired.push(`pre:${ctx.toolName}`);
        return { allowed: true };
      },
    });

    const result = await registry.run('pre_tool_use', { toolName: 'bash', toolArgs: {} });
    expect(result.allowed).toBe(true);
    expect(fired).toContain('pre:bash');
  });

  it('registers and fires post_tool_use hook', async () => {
    const registry = new HookRegistry();
    const results: string[] = [];

    registry.register({
      name: 'test-post-tool',
      stage: 'post_tool_use',
      handler: async (ctx) => {
        results.push(`post:${ctx.toolName}:result=${ctx.toolResult}`);
        return { allowed: true };
      },
    });

    await registry.run('post_tool_use', {
      toolName: 'read',
      toolResult: 'file content',
    });
    expect(results).toContain('post:read:result=file content');
  });

  it('multiple hooks for same stage all fire', async () => {
    const registry = new HookRegistry();
    const order: string[] = [];

    registry.register({
      name: 'hook-1',
      stage: 'pre_tool_use',
      handler: async () => { order.push('first'); return { allowed: true }; },
    });
    registry.register({
      name: 'hook-2',
      stage: 'pre_tool_use',
      handler: async () => { order.push('second'); return { allowed: true }; },
    });

    await registry.run('pre_tool_use', { toolName: 'edit', toolArgs: {} });
    expect(order).toEqual(['first', 'second']);
  });

  it('hook can block execution', async () => {
    const registry = new HookRegistry();

    registry.register({
      name: 'blocker',
      stage: 'pre_tool_use',
      handler: async () => ({ allowed: false, reason: 'Blocked by policy', message: 'Dangerous command denied' }),
    });

    const result: HookResult = await registry.run('pre_tool_use', {
      toolName: 'bash',
      toolArgs: { command: 'rm -rf /' },
    });
    expect(result.allowed).toBe(false);
    expect(result.reason).toBe('Blocked by policy');
  });

  it('registers hooks for all lifecycle stages', async () => {
    const registry = new HookRegistry();
    const stages: HookStage[] = [
      'session_start', 'session_end', 'turn_start', 'turn_end',
      'pre_tool_use', 'post_tool_use', 'stop',
    ];

    for (const s of stages) {
      registry.register({
        name: `hook-${s}`,
        stage: s,
        handler: async () => ({ allowed: true }),
      });
    }

    expect(registry.size).toBe(stages.length);
    for (const s of stages) {
      const names = registry.list(s);
      expect(names).toContain(`hook-${s}`);
    }
  });

  it('hook with matcher only fires for matching tool', async () => {
    const registry = new HookRegistry();
    const fired: string[] = [];

    registry.register({
      name: 'bash-only',
      stage: 'pre_tool_use',
      matcher: { toolName: 'bash' },
      handler: async (ctx) => {
        fired.push(`matched:${ctx.toolName}`);
        return { allowed: true };
      },
    });

    await registry.run('pre_tool_use', { toolName: 'read', toolArgs: {} });
    await registry.run('pre_tool_use', { toolName: 'bash', toolArgs: { command: 'ls' } });
    await registry.run('pre_tool_use', { toolName: 'write', toolArgs: {} });

    // Should only have fired for bash
    expect(fired).toEqual(['matched:bash']);
  });
});
