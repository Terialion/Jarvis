// ============================================================================
// Communication tools tests
// ============================================================================
// pnpm vitest packages/subagents/src/__tests__/tools.test.ts

import { describe, expect, it, beforeEach } from 'vitest';
import { AgentMailbox } from '@jarvis/agent';
import { AgentRegistry } from '../registry.js';
import { SubagentPool } from '../pool.js';
import { createSpawnAgentHandler } from '../tools/spawn-agent.js';
import { createTalkToHandler } from '../tools/talk-to.js';
import { createReportHandler } from '../tools/report.js';
import { createListAgentsHandler } from '../tools/list-agents.js';
import { createRedirectAgentHandler } from '../tools/redirect-agent.js';

function makeRegistry(): AgentRegistry {
  const reg = new AgentRegistry();
  reg.register({
    agentId: 'supervisor',
    role: 'supervisor',
    parentId: null,
    depth: 0,
    agentType: 'general',
    capabilities: [],
    registeredAt: Date.now(),
  });
  return reg;
}

describe('talk_to', () => {
  let registry: AgentRegistry;
  let pool: SubagentPool;
  let parentMailbox: AgentMailbox;

  beforeEach(() => {
    registry = makeRegistry();
    pool = new SubagentPool();
    parentMailbox = new AgentMailbox();
  });

  it('delivers a message to another agent', async () => {
    // Register two agents and their mailboxes
    registry.register({
      agentId: 'worker-1',
      role: 'developer',
      parentId: 'supervisor',
      depth: 1,
      agentType: 'general',
      capabilities: [],
      registeredAt: Date.now(),
    });

    // Create pool with runner that gives mailbox to agents
    pool.setRunner(async () => ({ agentId: 'worker-1', status: 'completed' }));
    pool.submit({ agentId: 'worker-1', agentType: 'explore', task: 'test' });

    const handler = createTalkToHandler({
      registry,
      pool,
      senderId: 'supervisor',
    });

    const result = JSON.parse(await handler(
      { targetId: 'worker-1', message: 'How is the task going?' },
      {} as any,
    ));

    expect(result.ok).toBe(true);
    expect(result.to).toBe('worker-1');

    // Worker's mailbox should have the message
    const workerMb = pool.getMailbox('worker-1');
    expect(workerMb).toBeDefined();
    expect(workerMb!.hasPending()).toBe(true);
    const msgs = workerMb!.drain();
    expect(msgs[0].senderId).toBe('supervisor');
    expect(msgs[0].message).toBe('How is the task going?');
  });

  it('rejects unknown target', async () => {
    const handler = createTalkToHandler({
      registry,
      pool,
      senderId: 'supervisor',
    });

    const result = JSON.parse(await handler(
      { targetId: 'no-such-agent', message: 'hello' },
      {} as any,
    ));

    expect(result.error).toContain('not found');
  });

  it('requires targetId and message', async () => {
    const handler = createTalkToHandler({ registry, pool, senderId: 'supervisor' });

    const r1 = JSON.parse(await handler({}, {} as any));
    expect(r1.error).toContain('Missing targetId');

    const r2 = JSON.parse(await handler({ targetId: 'x' }, {} as any));
    expect(r2.error).toContain('Missing message');
  });
});

describe('report', () => {
  it('delivers a report to supervisor', async () => {
    const registry = makeRegistry();
    registry.register({
      agentId: 'worker-1',
      role: 'developer',
      parentId: 'supervisor',
      depth: 1,
      agentType: 'general',
      capabilities: [],
      registeredAt: Date.now(),
    });

    const supeMailbox = new AgentMailbox();
    const mailboxes = new Map<string, AgentMailbox>();
    mailboxes.set('supervisor', supeMailbox);

    const handler = createReportHandler({
      registry,
      senderId: 'worker-1',
      getMailbox: (id) => mailboxes.get(id),
    });

    const result = JSON.parse(await handler(
      { summary: 'Task completed: refactored auth module' },
      {} as any,
    ));

    expect(result.ok).toBe(true);
    expect(supeMailbox.hasPending()).toBe(true);
    const msgs = supeMailbox.drain();
    expect(msgs[0].senderId).toBe('worker-1');
    expect(msgs[0].message).toContain('Task completed');
    expect(msgs[0].message).toContain('[Report]');
  });

  it('rejects when no supervisor exists', async () => {
    const registry = makeRegistry();
    // supervisor has no parent
    const handler = createReportHandler({
      registry,
      senderId: 'supervisor',
      getMailbox: () => new AgentMailbox(),
    });

    const result = JSON.parse(await handler({ summary: 'test' }, {} as any));
    expect(result.error).toContain('No supervisor');
  });
});

describe('list_agents', () => {
  it('lists all agents with tree structure', async () => {
    const registry = makeRegistry();
    registry.register({
      agentId: 'dev-1',
      role: 'developer',
      parentId: 'supervisor',
      depth: 1,
      agentType: 'general',
      capabilities: [],
      registeredAt: Date.now(),
    });
    registry.register({
      agentId: 'qa-1',
      role: 'qa',
      parentId: 'supervisor',
      depth: 1,
      agentType: 'explore',
      capabilities: [],
      registeredAt: Date.now(),
    });

    const handler = createListAgentsHandler({ registry, selfId: 'supervisor' });
    const result = JSON.parse(await handler({}, {} as any));

    expect(result.count).toBe(3);
    expect(result.agents).toHaveLength(3);
    expect(result.tree).toContain('supervisor');
    expect(result.tree).toContain('dev-1');
    expect(result.tree).toContain('qa-1');
    expect(result.tree).toContain('*'); // self marker
  });
});

describe('spawn_agent', () => {
  it('spawns a new subagent and registers it', async () => {
    const registry = makeRegistry();
    const pool = new SubagentPool();
    const parentMailbox = new AgentMailbox();

    pool.setRunner(async (config, _mb) => ({
      agentId: config.agentId,
      status: 'completed',
      answer: 'done',
      turnsUsed: 1,
    }));

    const handler = createSpawnAgentHandler({
      pool,
      registry,
      parentMailbox,
      parentId: 'supervisor',
      depth: 0,
    });

    const result = JSON.parse(await handler(
      { description: 'Test search', prompt: 'Find all .ts files' },
      {} as any,
    ));

    expect(result.status).toBe('spawned');
    expect(result.agentId).toMatch(/^agent_/);
    expect(result.depth).toBe(1);

    // Wait for completion notification
    await new Promise((r) => setTimeout(r, 100));
    const msgs = parentMailbox.drain();
    expect(msgs.length).toBeGreaterThanOrEqual(1);
    if (msgs.length > 0) {
      expect(msgs[0].message).toContain('done');
    }

    // Verify registry entry
    const registered = registry.get(result.agentId);
    expect(registered).toBeDefined();
    expect(registered!.parentId).toBe('supervisor');
  });

  it('requires description and prompt', async () => {
    const handler = createSpawnAgentHandler({
      pool: new SubagentPool(),
      registry: makeRegistry(),
      parentMailbox: new AgentMailbox(),
      parentId: 'supervisor',
      depth: 0,
    });

    const r1 = JSON.parse(await handler({}, {} as any));
    expect(r1.error).toContain('Missing required parameters');
  });
});

// ============================================================================
// pause_agent / resume_agent / redirect_agent
// ============================================================================

describe('pause_agent and resume_agent', () => {
  it.skip('pause sets paused flag, resume clears it', () => {
    // Requires a real AgentLoop — tested at integration level
  });
});

describe('redirect_agent', () => {
  it('redirects an agent to a new task via mailbox', async () => {
    const registry = makeRegistry();
    const mailbox = new AgentMailbox();

    // Mock AgentLoop with mailbox
    const loops = new Map<string, any>();
    loops.set('worker-1', {
      mailbox,
      redirect(task: string) {
        mailbox.deliver('supervisor', `[REDIRECT] New task: ${task}`, true);
      },
    });

    const handler = createRedirectAgentHandler({
      getAgentLoop: (id) => loops.get(id),
    });

    const result = JSON.parse(await handler(
      { agentId: 'worker-1', task: 'Fix the auth bug instead' },
      {} as any,
    ));

    expect(result.ok).toBe(true);
    expect(result.action).toBe('redirected');

    const msgs = mailbox.drain();
    expect(msgs).toHaveLength(1);
    expect(msgs[0].message).toContain('Fix the auth bug instead');
    expect(msgs[0].message).toContain('[REDIRECT]');
  });

  it('rejects missing agentId', async () => {
    const handler = createRedirectAgentHandler({ getAgentLoop: () => undefined });
    const r = JSON.parse(await handler({ task: 'do X' }, {} as any));
    expect(r.error).toContain('Missing agentId');
  });

  it('rejects missing task', async () => {
    const handler = createRedirectAgentHandler({ getAgentLoop: () => undefined });
    const r = JSON.parse(await handler({ agentId: 'x' }, {} as any));
    expect(r.error).toContain('Missing task');
  });
});