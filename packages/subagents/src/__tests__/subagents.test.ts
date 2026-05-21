import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SubagentPool } from '../pool.js';
import { SubagentRunner, toolWhitelistForType } from '../runner.js';
import { EXPLORE_TOOLS, PLAN_TOOLS, MAX_DEPTH, MAX_BUDGET_STEPS } from '../models.js';
import type { SubagentConfig, SubagentResult } from '../models.js';

// ============================================================================
// SubagentRunner
// ============================================================================

describe('SubagentRunner', () => {
  function makeRunner() {
    const runTurn = vi.fn().mockResolvedValue({ answer: 'done', turnsUsed: 3 });
    return {
      runner: new SubagentRunner({ runTurn }),
      runTurn,
    };
  }

  it('runs a task and returns result', async () => {
    const { runner, runTurn } = makeRunner();
    const result = await runner.run({
      agentId: 'agent_1',
      agentType: 'general',
      task: 'find files',
    });

    expect(result.status).toBe('completed');
    expect(result.answer).toBe('done');
    expect(result.turnsUsed).toBe(3);
    expect(runTurn).toHaveBeenCalledWith('find files', null, 5);
  });

  it('enforces depth limit', async () => {
    const { runner } = makeRunner();
    const result = await runner.run({
      agentId: 'deep',
      agentType: 'explore',
      task: 'look',
      depth: MAX_DEPTH + 1,
    });

    expect(result.status).toBe('failed');
    expect(result.error).toContain('Depth');
  });

  it('enforces budget range', async () => {
    const { runner } = makeRunner();

    const tooLow = await runner.run({
      agentId: 'low',
      agentType: 'explore',
      task: 'x',
      budgetSteps: 0,
    });
    expect(tooLow.status).toBe('failed');

    const tooHigh = await runner.run({
      agentId: 'high',
      agentType: 'explore',
      task: 'x',
      budgetSteps: MAX_BUDGET_STEPS + 1,
    });
    expect(tooHigh.status).toBe('failed');
  });

  it('catches runner errors', async () => {
    const runTurn = vi.fn().mockRejectedValue(new Error('crash'));
    const runner = new SubagentRunner({ runTurn });

    const result = await runner.run({
      agentId: 'crash',
      agentType: 'general',
      task: 'fail',
    });

    expect(result.status).toBe('failed');
    expect(result.error).toBe('crash');
  });
});

// ============================================================================
// toolWhitelistForType
// ============================================================================

describe('toolWhitelistForType', () => {
  it('returns read-only tools for explore', () => {
    expect(toolWhitelistForType('explore')).toEqual(EXPLORE_TOOLS);
  });

  it('returns read + task tools for plan', () => {
    expect(toolWhitelistForType('plan')).toEqual(PLAN_TOOLS);
  });

  it('returns null (all tools) for general', () => {
    expect(toolWhitelistForType('general')).toBeNull();
  });
});

// ============================================================================
// SubagentPool
// ============================================================================

describe('SubagentPool', () => {
  let pool: SubagentPool;

  beforeEach(() => {
    pool = new SubagentPool();
  });

  function makeConfig(
    overrides: Partial<SubagentConfig> = {},
  ): SubagentConfig {
    return {
      agentId: 'agent_1',
      agentType: 'general',
      task: 'test task',
      ...overrides,
    };
  }

  it('throws when submitting without a runner', () => {
    expect(() => pool.submit(makeConfig())).toThrow('no runner configured');
  });

  it('submits and runs a subagent', async () => {
    pool.setRunner(async (config) => ({
      agentId: config.agentId,
      status: 'completed',
      answer: 'ok',
      turnsUsed: 1,
    }));

    const handle = pool.submit(makeConfig());
    // Status may be 'pending' or 'running' depending on timing
    expect(['pending', 'running']).toContain(handle.status);

    const result = await handle.completion;
    expect(result.status).toBe('completed');
    expect(result.answer).toBe('ok');
  });

  it('rejects duplicate agent IDs', async () => {
    pool.setRunner(async () => ({
      agentId: 'x',
      status: 'completed',
    }));

    pool.submit(makeConfig({ agentId: 'dup' }));
    expect(() => pool.submit(makeConfig({ agentId: 'dup' }))).toThrow(
      'already exists',
    );
  });

  it('cancels a running subagent', async () => {
    pool.setRunner(async () => {
      await new Promise((r) => setTimeout(r, 200));
      return { agentId: 'x', status: 'completed' };
    });

    const handle = pool.submit(makeConfig({ agentId: 'cancel-me' }));
    handle.cancel();

    const result = await handle.completion;
    expect(result.status).toBe('cancelled');
  });

  it('lists agents with statuses', async () => {
    pool.setRunner(async (config) => ({
      agentId: config.agentId,
      status: 'completed',
    }));

    pool.submit(makeConfig({ agentId: 'a1' }));
    pool.submit(makeConfig({ agentId: 'a2' }));

    const list = pool.listAgents();
    expect(list).toHaveLength(2);
    expect(list.map((a) => a.agentId).sort()).toEqual(['a1', 'a2']);
  });

  it('waitAgent resolves when subagent completes', async () => {
    pool.setRunner(async (config) => ({
      agentId: config.agentId,
      status: 'completed',
      answer: 'done',
    }));

    pool.submit(makeConfig({ agentId: 'waiter' }));
    const result = await pool.waitAgent('waiter');
    expect(result.answer).toBe('done');
  });

  it('waitAgent throws for unknown agent', async () => {
    await expect(pool.waitAgent('unknown')).rejects.toThrow('not found');
  });

  it('waitAgent times out', async () => {
    pool.setRunner(async () => {
      await new Promise((r) => setTimeout(r, 500));
      return { agentId: 'slow', status: 'completed' };
    });

    pool.submit(makeConfig({ agentId: 'slow' }));
    await expect(pool.waitAgent('slow', 50)).rejects.toThrow('Timeout');
  });

  it('counts active agents', async () => {
    pool.setRunner(async () => {
      await new Promise((r) => setTimeout(r, 100));
      return { agentId: 'x', status: 'completed' };
    });

    expect(pool.activeCount()).toBe(0);
    pool.submit(makeConfig({ agentId: 'a' }));
    pool.submit(makeConfig({ agentId: 'b' }));
    // Immediately after submit, they should be pending or running
    expect(pool.activeCount()).toBeGreaterThanOrEqual(1);
  });

  it('drains notifications', async () => {
    pool.setRunner(async (config) => ({
      agentId: config.agentId,
      status: 'completed',
    }));

    const handle = pool.submit(makeConfig({ agentId: 'notif-test' }));
    await handle.completion;

    const notifs = pool.drainNotifications();
    expect(notifs.length).toBeGreaterThan(0);
    // After draining, queue should be empty
    expect(pool.drainNotifications()).toEqual([]);
  });

  it('shuts down and cancels active agents', async () => {
    pool.setRunner(async () => {
      await new Promise((r) => setTimeout(r, 500));
      return { agentId: 'x', status: 'completed' };
    });

    pool.submit(makeConfig({ agentId: 's1' }));
    pool.submit(makeConfig({ agentId: 's2' }));
    pool.shutdown();

    expect(pool.listAgents()).toEqual([]);
  });
});
