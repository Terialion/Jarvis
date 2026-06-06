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
