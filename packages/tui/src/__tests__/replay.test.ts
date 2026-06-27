import { afterEach, describe, expect, it, vi } from 'vitest';
import { existsSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import type { ReplayOptions } from '../replay.js';

afterEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
});

describe('runReplay shutdown', () => {
  it('waits for root exit and cleanup before returning', async () => {
    const render = vi.fn();
    const unmount = vi.fn();
    const waitUntilExit = vi.fn(async () => undefined);
    const cleanup = vi.fn();

    vi.doMock('../vendor/ink-renderer/root.js', () => ({
      createRoot: vi.fn(async () => ({
        render,
        unmount,
        waitUntilExit,
        cleanup,
      })),
    }));

    const writeSpy = vi.spyOn(process.stdout, 'write').mockReturnValue(true);
    const { runReplay } = await import('../replay.js');
    const snapshotDir = mkdtempSync(join(tmpdir(), 'jarvis-replay-test-'));

    const options: ReplayOptions = {
      model: 'test-model',
      maxTurns: 1,
      prompt: 'hello',
      waitMs: 0,
      inputDelayMs: 0,
      submitCount: 1,
      betweenPromptsMs: 0,
      interruptCount: 0,
      expandDetailsCount: 0,
      searchNextCount: 0,
      snapshotDir,
      width: 80,
      height: 24,
      shellMode: false,
    };

    await runReplay(options);

    expect(render).toHaveBeenCalledTimes(1);
    expect(unmount).toHaveBeenCalledTimes(1);
    expect(waitUntilExit).toHaveBeenCalledTimes(1);
    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(existsSync(join(snapshotDir, 'meta.json'))).toBe(true);
    expect(writeSpy).toHaveBeenCalled();
  });
});

describe('summarizeViewportDebugEvents', () => {
  it('captures viewport event count and latest state', async () => {
    const events = [
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 12,
        scrollHeight: 50,
        viewportHeight: 20,
        remainingScrollDistance: 18,
        clampMin: 8,
        clampMax: 40,
        paintScrollTop: 12,
        clampedToMaxScroll: 12,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: false,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        liveAnswerLength: 0,
        liveThinkingLength: 256,
        transcriptItemCount: 5,
        transcriptTotalHeight: 80,
        transcriptRangeStart: 2,
        transcriptRangeEnd: 8,
        timestamp: 1,
      },
      {
        type: 'tool_runtime_state',
        stage: 'dispatch_started',
        toolName: 'bash',
        callId: 'call_1',
        timestamp: 2,
      },
      {
        type: 'viewport_state',
        mode: 'selection',
        followOutput: false,
        hasSelection: true,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 12,
        scrollHeight: 54,
        viewportHeight: 20,
        remainingScrollDistance: 22,
        clampMin: 10,
        clampMax: 42,
        paintScrollTop: 12,
        clampedToMaxScroll: 12,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: false,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        liveAnswerLength: 0,
        liveThinkingLength: 256,
        transcriptItemCount: 5,
        transcriptTotalHeight: 84,
        transcriptRangeStart: 3,
        transcriptRangeEnd: 9,
        timestamp: 2,
      },
      {
        type: 'stream_finalized',
        runId: 'run_1',
        reason: 'turn_complete',
        finalAnswerLength: 40,
        committedTextLength: 40,
        replacedStreamed: false,
        timestamp: 3,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 18,
        scrollHeight: 54,
        viewportHeight: 20,
        remainingScrollDistance: 16,
        clampMin: 12,
        clampMax: 44,
        paintScrollTop: 14,
        clampedToMaxScroll: 18,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: true,
        usedMountedRangeClamp: true,
        followedThisFrame: false,
        liveAnswerLength: 1024,
        liveThinkingLength: 0,
        transcriptItemCount: 6,
        transcriptTotalHeight: 84,
        transcriptRangeStart: 4,
        transcriptRangeEnd: 10,
        timestamp: 3,
      },
    ] as const;
    const { summarizeViewportDebugEvents, buildViewportDiagnostics } = await import('../replay.js');
    const summary = summarizeViewportDebugEvents(events as never);
    const diagnostics = buildViewportDiagnostics(events as never);

    expect(summary.viewportEventCount).toBe(3);
    expect(summary.viewportModesSeen).toEqual(['history', 'selection']);
    expect(summary.enteredHistoryMode).toBe(true);
    expect(summary.enteredSelectionMode).toBe(true);
    expect(summary.lastViewportState?.mode).toBe('history');
    expect(summary.lastViewportState?.hasSelection).toBe(false);
    expect(summary.lastViewportState?.clampMin).toBe(12);
    expect(summary.lastViewportState?.transcriptRangeStart).toBe(4);
    expect(diagnostics.eventCount).toBe(3);
    expect(diagnostics.suspiciousChanges).toHaveLength(1);
    expect(diagnostics.suspiciousChanges[0]?.reason).toBe('paint_clamp_shift');
    expect(diagnostics.suspiciousChanges[0]?.to.scrollTop).toBe(18);
    expect(diagnostics.suspiciousChanges[0]?.to.paintScrollTop).toBe(14);
    expect(diagnostics.suspiciousChanges[0]?.to.liveAnswerLength).toBe(1024);
    expect(diagnostics.suspiciousChanges[0]?.nearbyEvents).toContain('tool_runtime_state:dispatch_started:bash');
    expect(diagnostics.suspiciousChanges[0]?.nearbyEvents).toContain('stream_finalized:turn_complete:40');
  });

  it('classifies imperative scroll mutations as manual scroll actions', async () => {
    const events = [
      {
        type: 'viewport_manual_scroll',
        action: 'scroll_by',
        targetTop: 0,
        delta: -14,
        timestamp: 1,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 14,
        scrollHeight: 80,
        viewportHeight: 35,
        remainingScrollDistance: 31,
        paintScrollTop: 14,
        clampedToMaxScroll: 14,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: false,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        timestamp: 2,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 0,
        scrollHeight: 80,
        viewportHeight: 35,
        remainingScrollDistance: 45,
        paintScrollTop: 14,
        clampedToMaxScroll: 14,
        mutationSource: 'imperative_scroll_to',
        usedPaintClamp: false,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        timestamp: 3,
      },
    ] as const;
    const { buildViewportDiagnostics } = await import('../replay.js');
    const diagnostics = buildViewportDiagnostics(events as never);

    expect(diagnostics.manualChanges).toHaveLength(1);
    expect(diagnostics.manualChanges[0]?.toScrollTop).toBe(0);
    expect(diagnostics.manualChanges[0]?.action).toBe('scroll_by');
    expect(diagnostics.manualChanges[0]?.delta).toBe(-14);
    expect(diagnostics.manualChanges[0]?.targetTop).toBe(0);
    expect(diagnostics.suspiciousChanges).toHaveLength(0);
  });

  it('summarizes turn phase events for replay diagnostics', async () => {
    const events = [
      {
        type: 'turn_phase',
        phase: 'analyze',
        detail: 'entered_analysis',
        step: 2,
        timestamp: 1,
      },
      {
        type: 'turn_phase',
        phase: 'finalize',
        detail: 'forced_synthesis_after_tool_collection',
        step: 3,
        toolCallsSoFar: 2,
        timestamp: 2,
      },
      {
        type: 'turn_phase',
        phase: 'finalize',
        detail: 'forcing_markdown_answer',
        step: 4,
        finalizeReason: 'stagnation',
        finalizeAttempts: 1,
        timestamp: 3,
      },
    ] as const;
    const { summarizeTurnPhaseDebugEvents } = await import('../replay.js');
    const summary = summarizeTurnPhaseDebugEvents(events as never);

    expect(summary.eventCount).toBe(3);
    expect(summary.phasesSeen).toEqual(['analyze', 'finalize']);
    expect(summary.detailsSeen).toEqual([
      'entered_analysis',
      'forced_synthesis_after_tool_collection',
      'forcing_markdown_answer',
    ]);
    expect(summary.lastPhaseEvent?.detail).toBe('forcing_markdown_answer');
    expect(summary.sawEnterFinalize).toBe(false);
    expect(summary.sawNoProgressHardStop).toBe(false);
    expect(summary.sawEmptyStepDuringFinalize).toBe(false);
    expect(summary.terminalPhaseTrail).toEqual([
      'analyze:entered_analysis',
      'finalize:forced_synthesis_after_tool_collection',
      'finalize:forcing_markdown_answer',
    ]);
  });

  it('captures terminal finalize and no-progress phase markers', async () => {
    const events = [
      {
        type: 'turn_phase',
        phase: 'finalize',
        detail: 'enter_finalize',
        timestamp: 1,
      },
      {
        type: 'turn_phase',
        phase: 'finalize',
        detail: 'empty_step_during_finalize',
        finalizeReason: 'stagnation',
        finalizeAttempts: 1,
        timestamp: 2,
      },
      {
        type: 'turn_phase',
        phase: 'finalize',
        detail: 'no_progress_hard_stop',
        noProgressCount: 5,
        finalizeReason: 'stagnation',
        timestamp: 3,
      },
    ] as const;
    const { summarizeTurnPhaseDebugEvents } = await import('../replay.js');
    const summary = summarizeTurnPhaseDebugEvents(events as never);

    expect(summary.sawEnterFinalize).toBe(true);
    expect(summary.sawEmptyStepDuringFinalize).toBe(true);
    expect(summary.sawNoProgressHardStop).toBe(true);
    expect(summary.terminalPhaseTrail).toEqual([
      'finalize:enter_finalize',
      'finalize:empty_step_during_finalize',
      'finalize:no_progress_hard_stop',
    ]);
  });

  it('labels suspicious viewport changes with nearby output activity', async () => {
    const events = [
      {
        type: 'stream_chunk_flushed',
        runId: 'answer_run',
        chunkLength: 20,
        displayLength: 320,
        sourceLength: 320,
        timestamp: 1,
      },
      {
        type: 'tool_runtime_state',
        stage: 'dispatch_started',
        toolName: 'bash',
        callId: 'bash_1',
        timestamp: 1,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 24,
        scrollHeight: 90,
        viewportHeight: 24,
        pendingScrollDelta: 0,
        remainingScrollDistance: 42,
        clampMin: 16,
        clampMax: 70,
        paintScrollTop: 24,
        clampedToMaxScroll: 24,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: false,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        liveAnswerLength: 320,
        liveThinkingLength: 0,
        transcriptItemCount: 9,
        transcriptTotalHeight: 110,
        transcriptRangeStart: 3,
        transcriptRangeEnd: 12,
        timestamp: 2,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 0,
        scrollHeight: 94,
        viewportHeight: 24,
        pendingScrollDelta: 0,
        remainingScrollDistance: 70,
        clampMin: 0,
        clampMax: 58,
        paintScrollTop: 0,
        clampedToMaxScroll: 0,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: true,
        usedMountedRangeClamp: true,
        followedThisFrame: false,
        liveAnswerLength: 520,
        liveThinkingLength: 0,
        transcriptItemCount: 10,
        transcriptTotalHeight: 118,
        transcriptRangeStart: 0,
        transcriptRangeEnd: 10,
        timestamp: 3,
      },
    ] as const;
    const { buildViewportDiagnostics } = await import('../replay.js');
    const diagnostics = buildViewportDiagnostics(events as never);

    expect(diagnostics.suspiciousChanges).toHaveLength(1);
    expect(diagnostics.suspiciousChanges[0]?.outputActivity).toEqual(['answer_stream', 'bash_output', 'tool_output']);
  }, 10000);

  it('includes turn phase context in nearby viewport diagnostics', async () => {
    const events = [
      {
        type: 'turn_phase',
        phase: 'finalize',
        detail: 'forced_synthesis_after_tool_collection',
        step: 3,
        toolCallsSoFar: 2,
        timestamp: 1,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 16,
        scrollHeight: 72,
        viewportHeight: 20,
        remainingScrollDistance: 36,
        clampMin: 10,
        clampMax: 52,
        paintScrollTop: 16,
        clampedToMaxScroll: 16,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: false,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        liveAnswerLength: 0,
        liveThinkingLength: 120,
        transcriptItemCount: 6,
        transcriptTotalHeight: 92,
        transcriptRangeStart: 4,
        transcriptRangeEnd: 10,
        timestamp: 2,
      },
      {
        type: 'viewport_state',
        mode: 'history',
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: true,
        scrollTop: 20,
        scrollHeight: 72,
        viewportHeight: 20,
        remainingScrollDistance: 32,
        clampMin: 12,
        clampMax: 56,
        paintScrollTop: 14,
        clampedToMaxScroll: 20,
        mutationSource: 'render_persist_clamp',
        usedPaintClamp: true,
        usedMountedRangeClamp: false,
        followedThisFrame: false,
        liveAnswerLength: 512,
        liveThinkingLength: 0,
        transcriptItemCount: 7,
        transcriptTotalHeight: 96,
        transcriptRangeStart: 5,
        transcriptRangeEnd: 11,
        timestamp: 3,
      },
    ] as const;
    const { buildViewportDiagnostics } = await import('../replay.js');
    const diagnostics = buildViewportDiagnostics(events as never);

    expect(diagnostics.suspiciousChanges).toHaveLength(1);
    expect(diagnostics.suspiciousChanges[0]?.nearbyEvents).toContain(
      'turn_phase:finalize:forced_synthesis_after_tool_collection:step=3,tools=2',
    );
  });
});
