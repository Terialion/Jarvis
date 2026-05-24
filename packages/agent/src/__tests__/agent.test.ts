// ============================================================================
// @jarvis/agent — comprehensive tests
// ============================================================================

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AgentEventBus } from '../events.js';
import { jitteredBackoff, withRetry } from '../retry.js';
import { ContextBuilder } from '../context.js';
import { ConversationSummarizer } from '../summary.js';
import { AgentLoop } from '../loop.js';
import { LLMProvider } from '../model.js';
import type { ChatMessage } from '@jarvis/shared';
import { ToolRegistry } from '@jarvis/tools';

// ============================================================================
// AgentEventBus
// ============================================================================

describe('AgentEventBus', () => {
  let bus: AgentEventBus;

  beforeEach(() => {
    bus = new AgentEventBus();
  });

  it('delivers events to registered handlers', () => {
    const received: Record<string, unknown>[] = [];
    bus.on('test', (payload) => received.push(payload));
    bus.emit('test', { value: 42 });

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ value: 42 });
  });

  it('supports multiple handlers for the same event', () => {
    const calls: string[] = [];
    bus.on('test', () => calls.push('a'));
    bus.on('test', () => calls.push('b'));
    bus.emit('test', {});

    expect(calls).toEqual(['a', 'b']);
  });

  it('does not call handlers for unregistered events', () => {
    const handler = vi.fn();
    bus.on('foo', handler);
    bus.emit('bar', {});
    expect(handler).not.toHaveBeenCalled();
  });

  it('removes handlers via off()', () => {
    const handler = vi.fn();
    bus.on('test', handler);
    bus.off('test', handler);
    bus.emit('test', {});
    expect(handler).not.toHaveBeenCalled();
  });

  it('off() is a no-op for unregistered handlers', () => {
    const handler = vi.fn();
    expect(() => bus.off('nonexistent', handler)).not.toThrow();
  });

  it('isolates errors in handlers — other handlers still run', () => {
    const calls: string[] = [];
    bus.on('test', () => {
      throw new Error('boom');
    });
    bus.on('test', () => calls.push('survivor'));
    bus.emit('test', {});
    expect(calls).toEqual(['survivor']);
  });

  it('clear() removes all handlers', () => {
    const handler = vi.fn();
    bus.on('a', handler);
    bus.on('b', handler);
    bus.clear();
    bus.emit('a', {});
    bus.emit('b', {});
    expect(handler).not.toHaveBeenCalled();
  });

  it('listenerCount() returns correct counts', () => {
    expect(bus.listenerCount('test')).toBe(0);
    bus.on('test', () => {});
    expect(bus.listenerCount('test')).toBe(1);
    bus.on('test', () => {});
    expect(bus.listenerCount('test')).toBe(2);
  });

  it('createEvent() returns a well-formed AgentEvent', () => {
    const event = AgentEventBus.createEvent('tool:start', 'turn_1', {
      name: 'bash',
    });
    expect(event.type).toBe('tool:start');
    expect(event.turnId).toBe('turn_1');
    expect(event.payload).toEqual({ name: 'bash' });
    expect(event.eventId).toMatch(/^evt_/);
  });

  it('emit does not throw when no handlers are registered', () => {
    expect(() => bus.emit('nonexistent', {})).not.toThrow();
  });
});

// ============================================================================
// jitteredBackoff
// ============================================================================

describe('jitteredBackoff', () => {
  it('returns a positive number', () => {
    const delay = jitteredBackoff(1, 1000, 10000);
    expect(delay).toBeGreaterThan(0);
  });

  it('increases with attempt number', () => {
    // Due to jitter this isn't strictly monotonic, but on average it increases
    const d1 = jitteredBackoff(1, 1000, 100000, 0); // No jitter for test
    const d2 = jitteredBackoff(2, 1000, 100000, 0);
    const d3 = jitteredBackoff(3, 1000, 100000, 0);
    expect(d2).toBeGreaterThan(d1);
    expect(d3).toBeGreaterThan(d2);
  });

  it('caps at maxDelay', () => {
    const delay = jitteredBackoff(100, 5000, 30000, 0);
    expect(delay).toBeLessThanOrEqual(30000);
  });

  it('uses baseDelay for first attempt (no jitter)', () => {
    const delay = jitteredBackoff(1, 5000, 120000, 0);
    expect(delay).toBe(5000);
  });

  it('doubles each attempt (no jitter)', () => {
    expect(jitteredBackoff(1, 1000, 100000, 0)).toBe(1000);
    expect(jitteredBackoff(2, 1000, 100000, 0)).toBe(2000);
    expect(jitteredBackoff(3, 1000, 100000, 0)).toBe(4000);
    expect(jitteredBackoff(4, 1000, 100000, 0)).toBe(8000);
  });

  it('jitter reduces the delay (always <= exponential)', () => {
    for (let i = 0; i < 20; i++) {
      const delay = jitteredBackoff(3, 5000, 120000, 0.3);
      // Without jitter: 5000 * 2^2 = 20000
      // With 30% jitter: 14000-20000
      expect(delay).toBeLessThanOrEqual(20000);
      expect(delay).toBeGreaterThanOrEqual(14000);
    }
  });
});

// ============================================================================
// withRetry
// ============================================================================

describe('withRetry', () => {
  it('returns the result on success (no retry needed)', async () => {
    const fn = vi.fn().mockResolvedValue('ok');
    const result = await withRetry(fn, { maxRetries: 3 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('retries on failure and succeeds', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error('fail1'))
      .mockRejectedValueOnce(new Error('fail2'))
      .mockResolvedValue('ok');

    const result = await withRetry(fn, {
      maxRetries: 3,
      baseDelay: 10,
      maxDelay: 50,
    });

    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it('throws after exhausting maxRetries', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('always fails'));

    await expect(
      withRetry(fn, { maxRetries: 2, baseDelay: 10, maxDelay: 50 }),
    ).rejects.toThrow('always fails');

    // Called 1 initial + 2 retries = 3 times
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it('does not retry when shouldRetry returns false', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('no-retry'));

    await expect(
      withRetry(
        fn,
        { maxRetries: 3, baseDelay: 10, maxDelay: 50 },
        () => false, // never retry
      ),
    ).rejects.toThrow('no-retry');

    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('retries on specific status codes', async () => {
    let calls = 0;
    const fn = async () => {
      calls++;
      if (calls < 3) {
        const err = new Error('rate limited') as Error & { status: number };
        (err as Error & { status: number }).status = 429;
        throw err;
      }
      return 'ok';
    };

    const result = await withRetry(fn, {
      maxRetries: 3,
      baseDelay: 10,
      maxDelay: 50,
    });

    expect(result).toBe('ok');
    expect(calls).toBe(3);
  });

  it('retryOn defaults to [429, 500, 502, 503, 504]', async () => {
    // Verify these codes trigger retry
    for (const code of [429, 500, 502, 503, 504]) {
      let attempts = 0;
      const fn = async () => {
        attempts++;
        if (attempts === 1) {
          const err = new Error(`HTTP ${code}`) as Error & { status: number };
          (err as Error & { status: number }).status = code;
          throw err;
        }
        return 'ok';
      };

      const result = await withRetry(fn, {
        maxRetries: 1,
        baseDelay: 5,
        maxDelay: 20,
      });
      expect(result).toBe('ok');
    }
  });

  it('respects custom retryOn codes', async () => {
    let calls = 0;
    const fn = async () => {
      calls++;
      if (calls === 1) {
        const err = new Error('Not Found') as Error & { status: number };
        (err as Error & { status: number }).status = 404;
        throw err;
      }
      return 'ok';
    };

    const result = await withRetry(fn, {
      maxRetries: 1,
      baseDelay: 5,
      maxDelay: 20,
      retryOn: [404],
    });

    expect(result).toBe('ok');
    expect(calls).toBe(2);
  });
});

// ============================================================================
// ContextBuilder
// ============================================================================

describe('ContextBuilder', () => {
  let builder: ContextBuilder;

  beforeEach(() => {
    builder = new ContextBuilder({ maxTokens: 10000, thresholdPercent: 0.5 });
  });

  it('estimates tokens correctly (chars/4)', () => {
    expect(builder.estimateTokens('hello')).toBe(2); // 5/4 = 1.25 -> 2
    expect(builder.estimateTokens('')).toBe(0);
    expect(builder.estimateTokens('abcd')).toBe(1); // 4/4 = 1
  });

  it('shouldCompress returns true when over threshold', () => {
    expect(builder.shouldCompress(6000)).toBe(true); // 6000 > 5000
  });

  it('shouldCompress returns false when under threshold', () => {
    expect(builder.shouldCompress(4000)).toBe(false); // 4000 < 5000
  });

  it('shouldCompress returns false at exact threshold', () => {
    expect(builder.shouldCompress(5000)).toBe(false); // 5000 not > 5000
  });

  it('buildMessages includes system prompt', () => {
    const messages = builder.buildMessages(
      'You are helpful',
      [],
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]).toEqual({ role: 'system', content: 'You are helpful' });
  });

  it('buildMessages converts ChatMessage history', () => {
    const history: ChatMessage[] = [
      {
        role: 'user',
        content: 'hello',
        messageId: 'msg_1',
      },
      {
        role: 'assistant',
        content: 'hi there',
        messageId: 'msg_2',
      },
    ];

    const messages = builder.buildMessages('system', history);
    expect(messages).toHaveLength(3);
    expect(messages[0].role).toBe('system');
    expect(messages[1].role).toBe('user');
    expect(messages[1].content).toBe('hello');
    expect(messages[2].role).toBe('assistant');
    expect(messages[2].content).toBe('hi there');
  });

  it('buildMessages handles tool messages with toolCallId', () => {
    const history: ChatMessage[] = [
      {
        role: 'tool',
        content: 'result',
        messageId: 'msg_3',
        toolCallId: 'call_1',
        name: 'bash',
      },
    ];

    const messages = builder.buildMessages('system', history);
    expect(messages[1].tool_call_id).toBe('call_1');
    expect(messages[1].name).toBe('bash');
  });

  it('buildMessages preserves tool_call_id and name in LLM output', () => {
    const history: ChatMessage[] = [
      {
        role: 'tool',
        content: 'file contents here',
        messageId: 'msg_t1',
        toolCallId: 'call_read_1',
        name: 'read',
      },
      {
        role: 'assistant',
        content: 'I read the file',
        messageId: 'msg_a1',
      },
    ];

    const messages = builder.buildMessages('system', history);

    // Tool message must have tool_call_id and name
    expect(messages[1].role).toBe('tool');
    expect(messages[1].content).toBe('file contents here');
    expect(messages[1].tool_call_id).toBe('call_read_1');
    expect(messages[1].name).toBe('read');

    // Assistant message must NOT have spurious tool_call_id
    expect(messages[2].role).toBe('assistant');
    expect(messages[2].tool_call_id).toBeUndefined();
    expect(messages[2].name).toBeUndefined();
  });

  it('buildMessages handles messages without optional fields', () => {
    const history: ChatMessage[] = [
      { role: 'user', content: 'hello', messageId: 'm1' },
      { role: 'assistant', content: 'hi', messageId: 'm2' },
    ];

    const messages = builder.buildMessages('system', history);

    expect(messages[1].tool_call_id).toBeUndefined();
    expect(messages[1].name).toBeUndefined();
    expect(messages[2].tool_call_id).toBeUndefined();
    expect(messages[2].name).toBeUndefined();
  });

  it('buildMessages returns empty system if no system prompt', () => {
    const messages = builder.buildMessages('', []);
    expect(messages).toHaveLength(0);
  });

  it('compactToolResults preserves protected ranges', () => {
    const messages: ChatMessage[] = [
      { role: 'system', content: 'sys', messageId: 'm1' },
      { role: 'user', content: 'q1', messageId: 'm2' },
      { role: 'assistant', content: 'a1', messageId: 'm3' },
      { role: 'tool', content: 'x'.repeat(1000), messageId: 'm4', name: 'bash' },
      { role: 'assistant', content: 'a2', messageId: 'm5' },
      { role: 'tool', content: 'y'.repeat(500), messageId: 'm6', name: 'read' },
      { role: 'assistant', content: 'done', messageId: 'm7' },
    ];

    const compacted = builder.compactToolResults(messages);

    // First 3 and last 6 are protected (only 7 total, so middle is small)
    // protectFirstN=3, protectLastN=6 -> start=3, end=7-6=1. Since start > end, nothing is compacted.
    // Actually: start=3, end=1. The for loop guard i < start || i >= end means for 7 msgs:
    // i=0: 0 < 3 -> skip, i=1: 1 < 3 -> skip, i=2: 2 < 3 -> skip
    // i=3: 3 >= 1 -> skip (i >= end)
    // So nothing gets compacted when total <= protectFirstN + protectLastN
    expect(compacted.length).toBe(7);
  });

  it('compactToolResults compacts middle tool messages', () => {
    const messages: ChatMessage[] = [
      { role: 'system', content: 'sys', messageId: 'm1' },
      { role: 'user', content: 'q', messageId: 'm2' },
      { role: 'assistant', content: 'a', messageId: 'm3' },
      { role: 'tool', content: 'x'.repeat(1000), messageId: 'm4', name: 'bash' },
      { role: 'assistant', content: 'resp', messageId: 'm5' },
      { role: 'tool', content: 'y'.repeat(500), messageId: 'm6', name: 'read' },
      { role: 'assistant', content: 'resp2', messageId: 'm7' },
      { role: 'user', content: 'q2', messageId: 'm8' },
      { role: 'assistant', content: 'a2', messageId: 'm9' },
      { role: 'assistant', content: 'final', messageId: 'm10' },
    ];

    // protectFirstN=3, protectLastN=6
    // start=3, end=10-6=4
    // Only index 3 (m4) is in range [3, 4)
    const compacted = builder.compactToolResults(messages);

    // First 3 are unchanged
    expect(compacted[0].content).toBe('sys');
    expect(compacted[1].content).toBe('q');
    expect(compacted[2].content).toBe('a');

    // Index 3 (m4, tool bash) should be compacted
    expect(compacted[3].content).toContain('[Tool result for bash');

    // Index 4+ are protected (last 6)
    expect(compacted[4].content).toBe('resp');
    expect(compacted[5].content).toBe('y'.repeat(500)); // not compacted - last 6 protected
  });

  it('compactToolResults does not compact non-tool messages', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'hello world this is a test message', messageId: 'm1' },
      { role: 'user', content: 'second unprotected message', messageId: 'm2' },
      { role: 'user', content: 'third', messageId: 'm3' },
      { role: 'user', content: 'fourth', messageId: 'm4' },
      { role: 'user', content: 'fifth', messageId: 'm5' },
      { role: 'assistant', content: 'sixth (protected)', messageId: 'm6' },
      { role: 'assistant', content: 'seventh (protected)', messageId: 'm7' },
      { role: 'assistant', content: 'eighth (protected)', messageId: 'm8' },
      { role: 'assistant', content: 'ninth (protected)', messageId: 'm9' },
      { role: 'assistant', content: 'tenth (protected)', messageId: 'm10' },
      { role: 'assistant', content: 'eleventh (protected)', messageId: 'm11' },
    ];

    // protectFirstN=3, protectLastN=6, start=3, end=11-6=5
    // indices 3 and 4 are in the middle range
    const compacted = builder.compactToolResults(messages);

    // Non-tool messages in the middle should be unchanged
    expect(compacted[3].content).toBe('fourth');
    expect(compacted[4].content).toBe('fifth');
  });
});

// ============================================================================
// ConversationSummarizer
// ============================================================================

describe('ConversationSummarizer', () => {
  let summarizer: ConversationSummarizer;

  beforeEach(() => {
    summarizer = new ConversationSummarizer({ maxSummaryChars: 2000 });
  });

  it('handles empty message list', () => {
    const summary = summarizer.summarize([]);
    expect(summary.goal).toBe('No conversation yet');
    expect(summary.files).toEqual([]);
    expect(summary.decisions).toEqual([]);
  });

  it('extracts goal from first user message', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'Please refactor the auth module', messageId: 'm1' },
    ];
    const summary = summarizer.summarize(messages);
    expect(summary.goal).toBe('Please refactor the auth module');
  });

  it('truncates long goals', () => {
    const longGoal = 'x'.repeat(500);
    const messages: ChatMessage[] = [
      { role: 'user', content: longGoal, messageId: 'm1' },
    ];
    const summary = summarizer.summarize(messages);
    expect(summary.goal.length).toBeLessThan(longGoal.length);
    expect(summary.goal.endsWith('...')).toBe(true);
  });

  it('detects files mentioned in messages', () => {
    const messages: ChatMessage[] = [
      {
        role: 'user',
        content: 'Fix /src/auth.ts and config.json',
        messageId: 'm1',
      },
      {
        role: 'assistant',
        content: 'Also check src/utils/helper.ts',
        messageId: 'm2',
      },
    ];
    const summary = summarizer.summarize(messages);
    expect(summary.files).toContain('/src/auth.ts');
    expect(summary.files).toContain('config.json');
    expect(summary.files).toContain('src/utils/helper.ts');
  });

  it('detects decisions in messages', () => {
    const messages: ChatMessage[] = [
      {
        role: 'assistant',
        content: 'I decided to use PostgreSQL for storage.',
        messageId: 'm1',
      },
      {
        role: 'assistant',
        content: 'Will use express for the HTTP server.',
        messageId: 'm2',
      },
    ];
    const summary = summarizer.summarize(messages);
    expect(summary.decisions).toContain('I decided to use PostgreSQL for storage.');
    expect(summary.decisions).toContain('Will use express for the HTTP server.');
  });

  it('detects questions', () => {
    const messages: ChatMessage[] = [
      {
        role: 'user',
        content: 'What architecture should we use? How do we handle auth?',
        messageId: 'm1',
      },
    ];
    const summary = summarizer.summarize(messages);
    expect(summary.resolvedQuestions.length + summary.pendingQuestions.length).toBe(2);
  });

  it('compactSummary produces a string within max length', () => {
    const summary = {
      goal: 'Build a web app',
      progress: '3 turns completed',
      decisions: ['Use TypeScript'],
      resolvedQuestions: ['Which framework?'],
      pendingQuestions: ['How to deploy?'],
      files: ['src/index.ts'],
      remainingWork: 'Implement auth module',
    };

    const compact = summarizer.compactSummary(summary);
    expect(typeof compact).toBe('string');
    expect(compact.length).toBeLessThanOrEqual(2000);
    expect(compact).toContain('Goal:');
    expect(compact).toContain('Progress:');
    expect(compact).toContain('Use TypeScript');
  });
});

// ============================================================================
// AgentLoop
// ============================================================================

// Helper to create a mock LLM provider
function createMockProvider(responses: Array<{
  content: string;
  toolCalls?: Array<{ name: string; arguments: Record<string, unknown>; callId: string }>;
  finishReason?: 'stop' | 'tool_calls' | 'length' | 'content_filter';
}>) {
  let callIndex = 0;
  return {
    chat: vi.fn().mockImplementation(async () => {
      const resp = responses[callIndex] ?? responses[responses.length - 1];
      callIndex++;
      return {
        content: resp?.content ?? '',
        toolCalls: resp?.toolCalls ?? [],
        finishReason: resp?.finishReason ?? 'stop',
      };
    }),
    chatStream: vi.fn(),
  };
}

describe('AgentLoop', () => {
  it('returns answer when LLM responds with stop', async () => {
    const mockProvider = createMockProvider([
      { content: 'Hello, how can I help?', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Hi');

    expect(result.answer).toBe('Hello, how can I help?');
    expect(result.stopReason).toBe('stop');
    expect(result.turnsUsed).toBe(1);
    expect(mockProvider.chat).toHaveBeenCalledTimes(1);
  });

  it('includes system prompt in messages', async () => {
    const mockProvider = createMockProvider([
      { content: 'OK', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      systemPrompt: 'You are a helpful coding assistant.',
      provider: mockProvider as unknown as LLMProvider,
    });

    await loop.run('Hi');

    const callArgs = mockProvider.chat.mock.calls[0];
    const messages = callArgs[0] as Array<{ role: string; content: string }>;
    expect(messages[0]).toEqual({
      role: 'system',
      content: 'You are a helpful coding assistant.',
    });
  });

  it('dispatches tool calls and continues loop', async () => {
    const registry = new ToolRegistry();
    registry.register({
      name: 'echo',
      toolset: 'test',
      schema: {
        type: 'function',
        function: {
          name: 'echo',
          description: 'Echo back the message',
          parameters: {
            type: 'object',
            properties: {
              message: { type: 'string' },
            },
            required: ['message'],
          },
        },
      },
      handler: (args) => JSON.stringify({ echoed: args.message }),
    });

    const mockProvider = createMockProvider([
      {
        content: '',
        toolCalls: [
          {
            name: 'echo',
            arguments: { message: 'hello' },
            callId: 'call_1',
          },
        ],
        finishReason: 'tool_calls',
      },
      { content: 'Tool executed successfully', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      tools: registry,
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Echo hello');

    expect(result.turnsUsed).toBe(2);
    expect(result.toolResults).toHaveLength(1);
    expect(result.toolResults[0].name).toBe('echo');
    expect(result.toolResults[0].ok).toBe(true);
    expect(result.answer).toBe('Tool executed successfully');
    expect(mockProvider.chat).toHaveBeenCalledTimes(2);
  });

  it('handles multiple tool calls in one turn', async () => {
    const registry = new ToolRegistry();
    registry.register({
      name: 'tool_a',
      toolset: 'test',
      schema: {
        type: 'function',
        function: {
          name: 'tool_a',
          description: 'Tool A',
          parameters: { type: 'object', properties: {} },
        },
      },
      handler: () => JSON.stringify({ result: 'A' }),
    });
    registry.register({
      name: 'tool_b',
      toolset: 'test',
      schema: {
        type: 'function',
        function: {
          name: 'tool_b',
          description: 'Tool B',
          parameters: { type: 'object', properties: {} },
        },
      },
      handler: () => JSON.stringify({ result: 'B' }),
    });

    const mockProvider = createMockProvider([
      {
        content: 'Calling tools',
        toolCalls: [
          { name: 'tool_a', arguments: {}, callId: 'call_a' },
          { name: 'tool_b', arguments: {}, callId: 'call_b' },
        ],
        finishReason: 'tool_calls',
      },
      { content: 'Done', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      tools: registry,
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Do both');

    expect(result.toolResults).toHaveLength(2);
    expect(result.toolResults[0].name).toBe('tool_a');
    expect(result.toolResults[1].name).toBe('tool_b');
    expect(result.answer).toBe('Done');
  });

  it('respects maxTurns limit', async () => {
    const registry = new ToolRegistry();
    registry.register({
      name: 'loop',
      toolset: 'test',
      schema: {
        type: 'function',
        function: {
          name: 'loop',
          description: 'A tool that makes the model keep calling',
          parameters: { type: 'object', properties: {} },
        },
      },
      handler: () => JSON.stringify({ ok: true }),
    });

    // Always return tool_calls — should hit maxTurns
    const infiniteToolCalls = Array.from({ length: 10 }, () => ({
      content: 'still going',
      toolCalls: [{ name: 'loop', arguments: {}, callId: `call_${Math.random()}` }],
      finishReason: 'tool_calls' as const,
    }));

    const mockProvider = createMockProvider(infiniteToolCalls);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      tools: registry,
      maxTurns: 3,
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Start');

    expect(result.turnsUsed).toBe(3);
    expect(result.stopReason).toBe('max_turns');
  });

  it('handles tool not found gracefully', async () => {
    const registry = new ToolRegistry();

    const mockProvider = createMockProvider([
      {
        content: '',
        toolCalls: [
          {
            name: 'nonexistent',
            arguments: {},
            callId: 'call_1',
          },
        ],
        finishReason: 'tool_calls',
      },
      { content: 'Handled missing tool', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      tools: registry,
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Try missing tool');

    expect(result.toolResults).toHaveLength(1);
    expect(result.toolResults[0].ok).toBe(false);
    expect(result.toolResults[0].content).toContain('Tool not found');
    // Loop should continue and get the stop response
    expect(result.answer).toBe('Handled missing tool');
  });

  it('emits lifecycle events', async () => {
    const mockProvider = createMockProvider([
      { content: 'OK', finishReason: 'stop' },
    ]);

    const eventBus = new AgentEventBus();
    const events: string[] = [];
    eventBus.on('turn:start', () => events.push('turn:start'));
    eventBus.on('llm:request', () => events.push('llm:request'));
    eventBus.on('llm:response', () => events.push('llm:response'));
    eventBus.on('turn:complete', () => events.push('turn:complete'));

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
      eventBus,
    });

    await loop.run('Hi');

    expect(events).toContain('turn:start');
    expect(events).toContain('llm:request');
    expect(events).toContain('llm:response');
    expect(events).toContain('turn:complete');
  });

  it('handles length finish reason', async () => {
    const mockProvider = createMockProvider([
      {
        content: 'Very long response that was truncated...',
        finishReason: 'length',
      },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Generate a lot');

    expect(result.stopReason).toBe('length');
    expect(result.answer).toBe('Very long response that was truncated...');
    expect(result.turnsUsed).toBe(1);
  });

  it('handles content_filter finish reason', async () => {
    const mockProvider = createMockProvider([
      { content: '', finishReason: 'content_filter' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Bad request');

    expect(result.stopReason).toBe('content_filter');
  });

  it('includes history in messages', async () => {
    const mockProvider = createMockProvider([
      { content: 'Sure, continuing...', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const history: ChatMessage[] = [
      { role: 'user', content: 'Previous question', messageId: 'm_old1' },
      { role: 'assistant', content: 'Previous answer', messageId: 'm_old2' },
    ];

    await loop.run('Follow up', history);

    const callArgs = mockProvider.chat.mock.calls[0];
    const messages = callArgs[0] as Array<{ role: string; content: string }>;
    expect(messages.some((m) => m.content === 'Previous question')).toBe(true);
    expect(messages.some((m) => m.content === 'Previous answer')).toBe(true);
    expect(messages.some((m) => m.content === 'Follow up')).toBe(true);
  });

  it('sends tool history messages with role=tool and tool_call_id', async () => {
    const mockProvider = createMockProvider([
      { content: 'Understood, continuing...', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const history: ChatMessage[] = [
      { role: 'user', content: 'Read the config', messageId: 'm_u1' },
      { role: 'assistant', content: 'Let me read it', messageId: 'm_a1' },
      {
        role: 'tool',
        content: '{"port": 3000}',
        messageId: 'm_t1',
        toolCallId: 'call_read_cfg',
        name: 'read',
      },
    ];

    await loop.run('Check that config', history);

    const callArgs = mockProvider.chat.mock.calls[0];
    const messages = callArgs[0] as Array<{
      role: string;
      content: string;
      tool_call_id?: string;
      name?: string;
    }>;

    const toolMsg = messages.find((m) => m.role === 'tool');
    expect(toolMsg).toBeDefined();
    expect(toolMsg!.tool_call_id).toBe('call_read_cfg');
    expect(toolMsg!.name).toBe('read');
    expect(toolMsg!.content).toContain('port');
  });

  it('returns messages array in result', async () => {
    const mockProvider = createMockProvider([
      { content: 'Answer', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Question');

    expect(result.messages.length).toBeGreaterThanOrEqual(2); // user + assistant
    expect(result.messages[0].role).toBe('user');
    expect(result.messages[result.messages.length - 1].role).toBe('assistant');
  });

  it('works without tools configured', async () => {
    const mockProvider = createMockProvider([
      { content: 'No tools needed', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const result = await loop.run('Simple question');

    expect(result.answer).toBe('No tools needed');
    expect(result.stopReason).toBe('stop');
  });
});

// ============================================================================
// LLMProvider (unit tests — no real API calls)
// ============================================================================

describe('LLMProvider', () => {
  it('constructs with minimal config', () => {
    const provider = new LLMProvider({
      model: 'test-model',
      apiKey: 'sk-test',
    });
    expect(provider).toBeDefined();
  });

  it('uses provided apiKey', () => {
    const provider = new LLMProvider({
      model: 'test-model',
      apiKey: 'sk-test',
    });
    expect(provider).toBeDefined();
  });

  it('falls back to JARVIS_LLM_API_KEY env var', () => {
    process.env['JARVIS_LLM_API_KEY'] = 'env-key';
    const provider = new LLMProvider({ model: 'test-model' });
    expect(provider).toBeDefined();
    delete process.env['JARVIS_LLM_API_KEY'];
  });

  it('accepts full config', () => {
    const provider = new LLMProvider({
      baseURL: 'https://api.example.com/v1',
      apiKey: 'sk-test',
      model: 'example-model',
      temperature: 0.7,
      maxTokens: 4096,
      maxRetries: 5,
      timeout: 60000,
    });
    expect(provider).toBeDefined();
  });
});
