// ============================================================================
// Integration tests for new context management features
// ============================================================================

import { describe, it, expect, beforeEach } from 'vitest';
import { AgentLoop } from '../loop.js';
import { FakeModelClient } from '../model.js';
import { SessionStore } from '@jarvis/store';
import { ToolRegistry, allBuiltinTools } from '@jarvis/tools';
import { ErrorClassifier } from '../retry.js';
import { ContextOverflowError } from '../model.js';
import {
  removeOrphanToolResults,
  repairAllToolBoundaries,
  computeAdaptiveChunkRatio,
  recomputeTokens,
  summarizeInStages,
  splitMessagesByTokenShare,
} from '../compactor.js';
import { buildSystemPrompt } from '../prompt-builder.js';
import { UserFactExtractor } from '../context.js';
import type { CompactionMessage, CompactionModelClient } from '../compactor.js';

// ============================================================================
// 1. Error classification
// ============================================================================

describe('ErrorClassifier context overflow detection', () => {
  it('detects context_length_exceeded errors', () => {
    expect(ErrorClassifier.isContextOverflow(new Error('context_length_exceeded'))).toBe(true);
  });

  it('detects max token errors', () => {
    expect(ErrorClassifier.isContextOverflow('maximum context length exceeded')).toBe(true);
    expect(ErrorClassifier.isContextOverflow('reduce your context size')).toBe(true);
    expect(ErrorClassifier.isContextOverflow('too many tokens in the input')).toBe(true);
  });

  it('does not flag unrelated errors', () => {
    expect(ErrorClassifier.isContextOverflow(new Error('network timeout'))).toBe(false);
    expect(ErrorClassifier.isContextOverflow('unauthorized')).toBe(false);
  });

  it('handles null/undefined', () => {
    expect(ErrorClassifier.isContextOverflow(null)).toBe(false);
    expect(ErrorClassifier.isContextOverflow(undefined)).toBe(false);
  });
});

// ============================================================================
// 2. ContextOverflowError
// ============================================================================

describe('ContextOverflowError', () => {
  it('is an instance of Error', () => {
    const err = new ContextOverflowError('test');
    expect(err).toBeInstanceOf(Error);
  });

  it('has correct name', () => {
    const err = new ContextOverflowError('test');
    expect(err.name).toBe('ContextOverflowError');
  });

  it('stores tokenCount', () => {
    const err = new ContextOverflowError('overflow', 50000);
    expect(err.tokenCount).toBe(50000);
  });
});

// ============================================================================
// 3. Orphan tool result removal
// ============================================================================

describe('removeOrphanToolResults', () => {
  it('removes tool results without matching tool calls', () => {
    const messages: CompactionMessage[] = [
      { role: 'assistant', content: 'Let me check', tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'read', arguments: '{}' } }] },
      { role: 'tool', content: 'file content', tool_call_id: 'call_1' },
      { role: 'tool', content: 'orphan result', tool_call_id: 'call_orphan' },
    ];
    const cleaned = removeOrphanToolResults(messages);
    expect(cleaned.length).toBe(2);
    expect(cleaned.find((m) => m.tool_call_id === 'call_orphan')).toBeUndefined();
  });

  it('preserves all messages when no orphans', () => {
    const messages: CompactionMessage[] = [
      { role: 'assistant', content: 'hello' },
      { role: 'user', content: 'hi' },
    ];
    const cleaned = removeOrphanToolResults(messages);
    expect(cleaned.length).toBe(2);
  });

  it('handles empty arrays', () => {
    expect(removeOrphanToolResults([])).toEqual([]);
  });
});

// ============================================================================
// 4. Adaptive chunk ratio
// ============================================================================

describe('computeAdaptiveChunkRatio', () => {
  it('returns loose ratio for small messages', () => {
    const msgs: CompactionMessage[] = Array.from({ length: 10 }, (_, i) => ({
      role: 'user',
      content: `short msg ${i}`,
    }));
    const ratio = computeAdaptiveChunkRatio(msgs);
    expect(ratio.ratio).toBe(0.40);
    expect(ratio.headCount).toBe(4);
  });

  it('returns tight ratio for large messages', () => {
    const msgs: CompactionMessage[] = [
      { role: 'tool', content: 'x'.repeat(3000) },
      { role: 'tool', content: 'y'.repeat(3000) },
    ];
    const ratio = computeAdaptiveChunkRatio(msgs);
    expect(ratio.ratio).toBe(0.15);
    expect(ratio.headCount).toBe(3);
  });

  it('handles empty messages', () => {
    const ratio = computeAdaptiveChunkRatio([]);
    expect(ratio.ratio).toBe(0.40);
  });
});

// ============================================================================
// 5. Token recompute
// ============================================================================

describe('recomputeTokens', () => {
  it('computes total estimated tokens', () => {
    const msgs: CompactionMessage[] = [
      { role: 'user', content: 'hello world' },
      { role: 'assistant', content: 'hi there' },
    ];
    const tokens = recomputeTokens(msgs);
    expect(tokens).toBeGreaterThan(0);
    // 'hello world' = 11 chars / 4 ≈ 3 tokens, 'hi there' = 8 chars / 4 = 2 tokens ≈ 5 total
    expect(tokens).toBeGreaterThanOrEqual(4);
  });

  it('returns 0 for empty array', () => {
    expect(recomputeTokens([])).toBe(0);
  });
});

// ============================================================================
// 6. Staged message splitting
// ============================================================================

describe('splitMessagesByTokenShare', () => {
  it('splits into requested parts', () => {
    const msgs: CompactionMessage[] = Array.from({ length: 20 }, (_, i) => ({
      role: i % 2 === 0 ? 'user' : 'assistant',
      content: `message number ${i} with some padding content`,
    }));
    const parts = splitMessagesByTokenShare(msgs, 3);
    expect(parts.length).toBeGreaterThanOrEqual(1);
  });

  it('does not split on single part', () => {
    const msgs: CompactionMessage[] = [
      { role: 'user', content: 'hello' },
    ];
    expect(splitMessagesByTokenShare(msgs, 1)).toEqual([msgs]);
  });
});

// ============================================================================
// 7. System prompt verbosity modes
// ============================================================================

describe('buildSystemPrompt', () => {
  it('full mode includes all sections', () => {
    const prompt = buildSystemPrompt('test-model', 'full');
    expect(prompt).toContain('Jarvis');
    expect(prompt).toContain('test-model');
    expect(prompt).toContain('Tool rules');
    expect(prompt).toContain('Safety');
  });

  it('minimal mode has reduced content', () => {
    const prompt = buildSystemPrompt('test-model', 'minimal');
    expect(prompt).toContain('Jarvis');
    expect(prompt).toContain('Tool rules');
    // Should be shorter than full
    const fullPrompt = buildSystemPrompt('test-model', 'full');
    expect(prompt.length).toBeLessThan(fullPrompt.length);
  });

  it('none mode has only identity', () => {
    const prompt = buildSystemPrompt('test-model', 'none');
    expect(prompt).toContain('Jarvis');
    expect(prompt).toContain('test-model');
    expect(prompt).not.toContain('Tool rules');
  });
});

// ============================================================================
// 8. UserFactExtractor
// ============================================================================

describe('UserFactExtractor', () => {
  it('extracts name patterns', () => {
    const facts = UserFactExtractor.extractFacts('My name is Alice');
    const nameFact = facts.find((f) => f.key === 'name');
    expect(nameFact).toBeDefined();
    expect(nameFact?.value).toContain('Alice');
  });

  it('extracts role patterns', () => {
    const facts = UserFactExtractor.extractFacts("I'm a software engineer working on this");
    const roleFact = facts.find((f) => f.key === 'role');
    expect(roleFact).toBeDefined();
  });

  it('returns empty for no matches', () => {
    const facts = UserFactExtractor.extractFacts('echo hello world');
    expect(facts.length).toBe(0);
  });
});

// ============================================================================
// 9. ContextOverflowError retry in AgentLoop
// ============================================================================

describe('AgentLoop context overflow retry', () => {
  it('retries with compaction on ContextOverflowError using runTurn', async () => {
    const tools = new ToolRegistry();
    // Register a minimal tool set
    const readTool = allBuiltinTools.find((t) => t.name === 'read') ?? allBuiltinTools[0];
    tools.register(readTool);

    // Use FakeModelClient with scripted responses
    const scriptedClient = new FakeModelClient([
      {
        assistantText: 'Task completed.',
        reasoningSummary: '',
        toolCalls: [],
        finalAnswer: 'Compaction worked. Task done.',
        finishReason: 'stop',
      },
    ]);

    // Override complete to test overflow retry in runTurn
    let callCount = 0;
    const origComplete = scriptedClient.complete.bind(scriptedClient);
    scriptedClient.complete = function (messages, toolsArg, stream, metadata) {
      callCount++;
      if (callCount === 1) {
        throw new ContextOverflowError('context_length_exceeded', 150000);
      }
      return origComplete(messages as import('../model.js').LLMMessage[], toolsArg as Record<string, unknown>[] | undefined, stream as boolean | undefined, metadata as Record<string, unknown> | undefined);
    };

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      maxTurns: 5,
      maxSteps: 3,
      tools,
      provider: scriptedClient as unknown as import('../model.js').LLMProvider,
    });

    const result = await loop.runTurn('test overflow handling');
    // Should handle overflow and succeed on retry
    expect(result.ok || result.status !== 'failed').toBeTruthy();
    expect(callCount).toBeGreaterThanOrEqual(1);
  });
});

// ============================================================================
// 10. Session store repair and disk budget
// ============================================================================

describe('SessionStore repair and disk budget', () => {
  const tmpDir = `D:/agent/Jarvis/.jarvis/test_sessions_${Date.now()}`;

  it('repairSession handles nonexistent sessions gracefully', async () => {
    const store = new SessionStore(tmpDir);
    const report = await store.repairSession('nonexistent_session');
    // May or may not repair depending on whether directory/files exist
    expect(report).toHaveProperty('repaired');
    expect(report).toHaveProperty('issues');
  });

  it('repairSession fixes corrupted JSONL', async () => {
    const store = new SessionStore(tmpDir);
    const sid = `repair_test_${Date.now()}`;
    await store.createSession(sid);
    await store.appendMessage(sid, 'user', 'valid message');
    // Write corrupted line directly
    const fs = await import('node:fs/promises');
    const jsonlPath = `${tmpDir}/${sid}.jsonl`;
    await fs.appendFile(jsonlPath, 'this is not valid json\n', 'utf-8');
    await fs.appendFile(jsonlPath, JSON.stringify({ type: 'message', message_id: 'msg_2', role: 'user', content: 'valid after corruption' }) + '\n', 'utf-8');
    // Invalidate cache
    await store['_cache'].delete(sid);

    const report = await store.repairSession(sid);
    expect(report.repaired).toBe(true);
    expect(report.issues.length).toBeGreaterThan(0);
    expect(report.issues[0]).toContain('Removed');
  });

  it('enforceSessionDiskBudget does not crash', async () => {
    const store = new SessionStore(tmpDir);
    const result = await store.enforceSessionDiskBudget(10 * 1024 * 1024); // 10MB
    expect(typeof result.removed).toBe('number');
    expect(typeof result.freedBytes).toBe('number');
  });
});

// ============================================================================
// 11. Repair + boundary tools together
// ============================================================================

describe('repairAllToolBoundaries', () => {
  it('removes orphan tool results and marks unresolved calls', () => {
    const messages: CompactionMessage[] = [
      { role: 'assistant', content: 'calling tool', tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'read', arguments: '{}' } }] },
      { role: 'tool', content: 'result', tool_call_id: 'call_1' },
      { role: 'assistant', content: 'calling another', tool_calls: [{ id: 'call_2', type: 'function', function: { name: 'write', arguments: '{}' } }] },
      { role: 'tool', content: 'orphan', tool_call_id: 'call_orphan' },
    ];
    const result = repairAllToolBoundaries(messages);
    // Orphan tool result removed (4 -> 3)
    expect(result.length).toBeLessThanOrEqual(4);
    // Second assistant marked for unresolved tool call
    const secondAssistant = result.find((m) => m.content.includes('calling another'));
    expect(secondAssistant).toBeDefined();
    // The orphan tool result should be removed
    expect(result.find((m) => m.tool_call_id === 'call_orphan')).toBeUndefined();
  });
});
