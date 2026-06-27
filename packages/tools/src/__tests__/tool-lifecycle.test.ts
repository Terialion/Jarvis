import { describe, expect, it } from 'vitest';
import {
  applyToolLifecycleEvent,
  buildToolLifecycleSummary,
  createToolLifecycleState,
} from '../tool-lifecycle.js';

describe('tool lifecycle state', () => {
  it('tracks approval and execution transitions for a single tool run', () => {
    let state = createToolLifecycleState();

    state = applyToolLifecycleEvent(state, {
      stage: 'approval_requested',
      toolName: 'write_file',
      callId: 'call_1',
      argsKey: 'foo.ts',
      risk: 'write_approval_required',
    });

    expect(state.runsByCallId['call_1']).toMatchObject({
      toolName: 'write_file',
      status: 'awaiting_approval',
      terminal: false,
      argsKey: 'foo.ts',
      risk: 'write_approval_required',
    });

    state = applyToolLifecycleEvent(state, {
      stage: 'approval_granted',
      toolName: 'write_file',
      callId: 'call_1',
      argsKey: 'foo.ts',
    });

    expect(state.runsByCallId['call_1']?.status).toBe('approved');

    state = applyToolLifecycleEvent(state, {
      stage: 'dispatch_started',
      toolName: 'write_file',
      callId: 'call_1',
    });

    expect(state.runsByCallId['call_1']?.status).toBe('running');

    state = applyToolLifecycleEvent(state, {
      stage: 'dispatch_completed',
      toolName: 'write_file',
      callId: 'call_1',
      ok: true,
      durationMs: 24,
    });

    expect(state.runsByCallId['call_1']).toMatchObject({
      status: 'completed',
      terminal: true,
      ok: true,
      durationMs: 24,
    });
  });

  it('marks denied and failed runs as terminal', () => {
    let state = createToolLifecycleState();

    state = applyToolLifecycleEvent(state, {
      stage: 'approval_denied',
      toolName: 'bash',
      callId: 'call_2',
      argsKey: 'rm -rf tmp',
      reason: 'User denied',
    });

    expect(state.runsByCallId['call_2']).toMatchObject({
      status: 'denied',
      terminal: true,
      reason: 'User denied',
    });

    state = applyToolLifecycleEvent(state, {
      stage: 'dispatch_failed',
      toolName: 'web_search',
      callId: 'call_3',
      durationMs: 91,
      reason: 'network timeout',
    });

    expect(state.runsByCallId['call_3']).toMatchObject({
      status: 'failed',
      terminal: true,
      reason: 'network timeout',
      durationMs: 91,
    });
  });

  it('builds summary lines from shared lifecycle state', () => {
    let state = createToolLifecycleState();

    state = applyToolLifecycleEvent(state, {
      stage: 'approval_requested',
      toolName: 'web_search',
      callId: 'call_1',
      argsKey: 'jarvis',
      risk: 'network',
    });

    let summary = buildToolLifecycleSummary(state);
    expect(summary.statusLine).toBe('waiting for approval: web_search');
    expect(summary.runningLine).toBeUndefined();
    expect(summary.counts.awaitingApproval).toBe(1);

    state = applyToolLifecycleEvent(state, {
      stage: 'approval_granted',
      toolName: 'web_search',
      callId: 'call_1',
      argsKey: 'jarvis',
    });
    state = applyToolLifecycleEvent(state, {
      stage: 'dispatch_started',
      toolName: 'web_search',
      callId: 'call_1',
    });

    summary = buildToolLifecycleSummary(state);
    expect(summary.statusLine).toBe('running web_search');
    expect(summary.runningLine).toBe('web_search');
    expect(summary.counts.running).toBe(1);

    state = applyToolLifecycleEvent(state, {
      stage: 'dispatch_completed',
      toolName: 'web_search',
      callId: 'call_1',
      ok: true,
      durationMs: 18,
    });

    summary = buildToolLifecycleSummary(state);
    expect(summary.statusLine).toBe('completed web_search');
    expect(summary.runningLine).toBeUndefined();
    expect(summary.completedLines).toContain('web_search');
    expect(summary.counts.completed).toBe(1);
  });
});
