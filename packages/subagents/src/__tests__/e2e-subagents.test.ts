import { describe, it, expect } from 'vitest';
import { AgentMailbox } from '@jarvis/agent';
import { SubagentPool, SubagentRunner, toolWhitelistForType } from '@jarvis/subagents';
import type { SubagentConfig } from '@jarvis/subagents';

describe('E2E: Subagents', () => {
  it('toolWhitelistForType: returns correct tools per type', () => {
    const explore = toolWhitelistForType('explore');
    expect(explore).toContain('read');
    expect(explore).toContain('glob');
    expect(explore).toContain('grep');
    expect(explore).not.toContain('bash');

    const general = toolWhitelistForType('general');
    expect(general).toBeNull(); // null = all tools
  });

  it('SubagentPool: submits a subagent and waits for result', async () => {
    const pool = new SubagentPool();

    pool.setRunner(async (config: SubagentConfig, _mb: AgentMailbox) => ({
      agentId: config.agentId,
      status: 'completed',
      answer: `Task "${config.task}" completed with budget ${config.budgetSteps}`,
      turnsUsed: 3,
    }));

    const handle = pool.submit({
      agentId: 'test-agent-1',
      agentType: 'explore',
      task: 'Find all TypeScript files',
      budgetSteps: 10,
    });

    expect(['pending', 'running']).toContain(handle.status);

    const result = await handle.completion;
    expect(result.status).toBe('completed');
    expect(result.answer).toContain('Find all TypeScript files');
    expect(result.turnsUsed).toBe(3);
  });

  it('SubagentPool: throws if no runner configured', () => {
    const pool = new SubagentPool();
    expect(() => pool.submit({
      agentId: 'no-runner',
      agentType: 'general',
      task: 'test',
    })).toThrow('no runner configured');
  });

  it('SubagentPool: throws if duplicate agentId', () => {
    const pool = new SubagentPool();
    pool.setRunner(async () => ({ agentId: 'dup', status: 'completed' }));

    pool.submit({ agentId: 'dup-agent', agentType: 'general', task: 'first' });
    expect(() => pool.submit({ agentId: 'dup-agent', agentType: 'general', task: 'second' }))
      .toThrow('already exists');
  });

  it('SubagentRunner: runs a task with createAgentLoop', async () => {
    const calls: Array<{ agentId: string; task: string }> = [];
    const mockLoop = {
      runTurn: async () => ({ ok: true, finalAnswer: 'Found 5 results', toolCalls: [], events: [], summary: {} }),
    };

    const runner = new SubagentRunner({
      createAgentLoop: (opts) => {
        calls.push({ agentId: opts.agentId, task: opts.task });
        return mockLoop as any;
      },
    });

    const result = await runner.run({
      agentId: 'runner-test',
      agentType: 'explore',
      task: 'Search for AgentLoop usage',
      budgetSteps: 5,
    }, new AgentMailbox());

    expect(result.status).toBe('completed');
    expect(result.answer).toBe('Found 5 results');
    expect(calls).toHaveLength(1);
    expect(calls[0].agentId).toBe('runner-test');
  });

  it('SubagentRunner: rejects depth exceeding max', async () => {
    const runner = new SubagentRunner({
      createAgentLoop: () => ({ runTurn: async () => ({ ok: true }) } as any),
    });

    const result = await runner.run({
      agentId: 'deep-agent',
      agentType: 'general',
      task: 'Too deep',
      depth: 3,
    }, new AgentMailbox());

    expect(result.status).toBe('failed');
    expect(result.error).toContain('Depth');
  });

  it('SubagentRunner: rejects invalid budget', async () => {
    const runner = new SubagentRunner({
      createAgentLoop: () => ({ runTurn: async () => ({ ok: true }) } as any),
    });

    const result = await runner.run({
      agentId: 'bad-budget',
      agentType: 'general',
      task: 'Bad budget',
      budgetSteps: 0,
    }, new AgentMailbox());

    expect(result.status).toBe('failed');
    expect(result.error).toContain('Budget');
  });
});