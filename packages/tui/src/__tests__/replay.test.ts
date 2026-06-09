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
        transcriptTotalHeight: 80,
        transcriptRangeStart: 2,
        transcriptRangeEnd: 8,
        timestamp: 1,
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
        transcriptTotalHeight: 84,
        transcriptRangeStart: 3,
        transcriptRangeEnd: 9,
        timestamp: 2,
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
    expect(diagnostics.suspiciousChanges[0]?.reason).toBe('clamp_shift');
    expect(diagnostics.suspiciousChanges[0]?.to.scrollTop).toBe(18);
  });
});
