import { describe, expect, it } from 'vitest';
import { summarizeAgentEventProgress } from '../progress-summary.js';

describe('summarizeAgentEventProgress', () => {
  it('renders specific turn phase details with clearer progress text', () => {
    expect(
      summarizeAgentEventProgress('turn:phase', {
        phase: 'finalize',
        detail: 'retry_after_tool_intent_during_finalize',
      }),
    ).toBe('Retrying final answer synthesis without more tools');

    expect(
      summarizeAgentEventProgress('turn:phase', {
        phase: 'analyze',
        detail: 'clearing_stale_plan_mode_state',
      }),
    ).toBe('Clearing stale plan-mode state before continuing');

    expect(
      summarizeAgentEventProgress('turn:phase', {
        phase: 'finalize',
        detail: 'rejecting_tool_calls_during_finalize',
      }),
    ).toBe('Rejecting extra tool calls during finalization');
  });
});
