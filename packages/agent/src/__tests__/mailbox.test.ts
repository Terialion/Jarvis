// ============================================================================
// AgentMailbox unit tests
// ============================================================================
// pnpm vitest packages/agent/src/__tests__/mailbox.test.ts

import { describe, expect, it } from 'vitest';
import { AgentMailbox } from '../mailbox.js';

describe('AgentMailbox', () => {
  it('returns empty arrays when no messages delivered', () => {
    const mb = new AgentMailbox();
    expect(mb.poll()).toEqual([]);
    expect(mb.drain()).toEqual([]);
    expect(mb.hasPending()).toBe(false);
    expect(mb.hasPendingTriggerTurn()).toBe(false);
    expect(mb.size).toBe(0);
  });

  it('delivers a message and allows polling', () => {
    const mb = new AgentMailbox();
    mb.deliver('agent-a', 'hello');

    expect(mb.size).toBe(1);
    expect(mb.hasPending()).toBe(true);

    const polled = mb.poll();
    expect(polled).toHaveLength(1);
    expect(polled[0].senderId).toBe('agent-a');
    expect(polled[0].message).toBe('hello');
    // poll should NOT remove messages
    expect(mb.size).toBe(1);
  });

  it('drain returns and clears all messages', () => {
    const mb = new AgentMailbox();
    mb.deliver('a', 'first');
    mb.deliver('b', 'second');

    const drained = mb.drain();
    expect(drained).toHaveLength(2);
    expect(drained[0].senderId).toBe('a');
    expect(drained[1].senderId).toBe('b');

    // After drain, mailbox should be empty
    expect(mb.size).toBe(0);
    expect(mb.hasPending()).toBe(false);
    expect(mb.drain()).toEqual([]);
  });

  it('drain returns messages in delivery order', () => {
    const mb = new AgentMailbox();
    mb.deliver('agent-1', 'msg-1');
    mb.deliver('agent-2', 'msg-2');
    mb.deliver('agent-3', 'msg-3');

    const drained = mb.drain();
    expect(drained.map((m) => m.message)).toEqual(['msg-1', 'msg-2', 'msg-3']);
  });

  it('clear removes all pending messages', () => {
    const mb = new AgentMailbox();
    mb.deliver('a', 'test');
    mb.deliver('b', 'test2');
    mb.clear();
    expect(mb.size).toBe(0);
    expect(mb.hasPending()).toBe(false);
  });

  it('hasPendingTriggerTurn detects trigger_turn messages', () => {
    const mb = new AgentMailbox();
    mb.deliver('a', 'normal message');
    expect(mb.hasPendingTriggerTurn()).toBe(false);

    mb.deliver('b', 'wake up!', true);
    expect(mb.hasPendingTriggerTurn()).toBe(true);
  });

  it('drain clears triggerTurn state', () => {
    const mb = new AgentMailbox();
    mb.deliver('a', 'wake', true);
    mb.drain();
    expect(mb.hasPendingTriggerTurn()).toBe(false);
  });

  it('onMessage fires when deliver is called', () => {
    const mb = new AgentMailbox();
    let count = 0;
    mb.onMessage(() => { count++; });

    mb.deliver('a', 'test1');
    mb.deliver('b', 'test2');

    expect(count).toBe(2);
  });

  it('onMessage returns unsubscribe function', () => {
    const mb = new AgentMailbox();
    let count = 0;
    const unsub = mb.onMessage(() => { count++; });

    mb.deliver('a', 'test');
    expect(count).toBe(1);

    unsub();
    mb.deliver('b', 'test2');
    expect(count).toBe(1); // not incremented
  });

  it('includes timestamp in delivered items', () => {
    const mb = new AgentMailbox();
    const before = Date.now();
    mb.deliver('a', 'test');
    const after = Date.now();

    const [item] = mb.drain();
    expect(item.timestamp).toBeGreaterThanOrEqual(before);
    expect(item.timestamp).toBeLessThanOrEqual(after);
  });

  it('handles rapid drain after drain (idempotent)', () => {
    const mb = new AgentMailbox();
    mb.deliver('a', 'msg');
    mb.drain();
    mb.drain();
    expect(mb.size).toBe(0);
  });
});