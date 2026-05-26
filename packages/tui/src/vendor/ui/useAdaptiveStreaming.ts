// ============================================================================
// useAdaptiveStreaming — Codex-style Smooth/CatchUp gear streaming
// ============================================================================

import { useRef, useCallback, useEffect, useState } from 'react';

interface QueuedToken {
  text: string;
  enqueuedAt: number;
}

interface AdaptiveStreamingOptions {
  /** Smooth flush interval in ms (default 30) */
  smoothInterval?: number;
  /** Max tokens per smooth flush (default 3) */
  smoothBatchMax?: number;
  /** Enter catch-up when queue exceeds this many tokens */
  catchUpEnterDepth?: number;
  /** Enter catch-up when oldest token exceeds this age in ms */
  catchUpEnterAge?: number;
  /** Exit catch-up when queue drops below this depth */
  catchUpExitDepth?: number;
  /** Exit catch-up when oldest token is younger than this ms */
  catchUpExitAge?: number;
  /** Hold in Smooth for this many ms after exiting CatchUp */
  catchUpHysteresis?: number;
  /** Re-entry suppressed for this many ms (unless severe) */
  catchUpReentrySuppress?: number;
  /** Severe re-entry: depth > this OR age > this overrides suppression */
  severeDepth?: number;
  severeAge?: number;
}

export function useAdaptiveStreaming(
  onFlush: (text: string) => void,
  opts: AdaptiveStreamingOptions = {},
) {
  const {
    smoothInterval = 30,
    smoothBatchMax = 3,
    catchUpEnterDepth = 8,
    catchUpEnterAge = 120,
    catchUpExitDepth = 2,
    catchUpExitAge = 40,
    catchUpHysteresis = 80,
    catchUpReentrySuppress = 500,
    severeDepth = 20,
    severeAge = 500,
  } = opts;

  const queueRef = useRef<QueuedToken[]>([]);
  const modeRef = useRef<'smooth' | 'catchup'>('smooth');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastExitRef = useRef<number>(0);
  const [isRunning, setIsRunning] = useState(false);

  // Start the smooth interval timer
  const start = useCallback(() => {
    if (timerRef.current) return;
    setIsRunning(true);
    timerRef.current = setInterval(() => {
      const queue = queueRef.current;
      if (queue.length === 0) return;

      const now = Date.now();
      const oldest = queue[0];
      const oldestAge = oldest ? now - oldest.enqueuedAt : 0;
      const timeSinceExit = now - lastExitRef.current;

      // Decide gear
      const shouldEnterCatchUp =
        queue.length > catchUpEnterDepth || oldestAge > catchUpEnterAge;

      const severe = queue.length > severeDepth || oldestAge > severeAge;
      const suppressed = timeSinceExit < catchUpReentrySuppress && !severe;

      if (shouldEnterCatchUp && !suppressed) {
        modeRef.current = 'catchup';
      } else if (modeRef.current === 'catchup') {
        const canExit =
          queue.length <= catchUpExitDepth && oldestAge <= catchUpExitAge;
        if (canExit) {
          modeRef.current = 'smooth';
          lastExitRef.current = now;
        }
      }

      if (modeRef.current === 'catchup') {
        // Drain all
        const all = queueRef.current;
        queueRef.current = [];
        if (all.length > 0) {
          const text = all.map((t) => t.text).join('');
          onFlush(text);
        }
      } else {
        // Smooth: batch max N tokens
        const batch = queueRef.current.splice(0, smoothBatchMax);
        if (batch.length > 0) {
          const text = batch.map((t) => t.text).join('');
          onFlush(text);
        }
      }
    }, smoothInterval);
  }, [
    smoothInterval, smoothBatchMax,
    catchUpEnterDepth, catchUpEnterAge,
    catchUpExitDepth, catchUpExitAge,
    catchUpHysteresis, catchUpReentrySuppress,
    severeDepth, severeAge, onFlush,
  ]);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRunning(false);
    // Drain remaining
    const all = queueRef.current;
    queueRef.current = [];
    if (all.length > 0) {
      onFlush(all.map((t) => t.text).join(''));
    }
  }, [onFlush]);

  const push = useCallback((token: string) => {
    const q = queueRef.current;
    // Cap queue at 200 tokens to prevent OOM from very long responses
    if (q.length > 200) {
      // Flush oldest half to prevent unbounded growth
      const drain = q.splice(0, 100);
      const text = drain.map((t) => t.text).join('');
      onFlush(text);
    }
    q.push({ text: token, enqueuedAt: Date.now() });
  }, [onFlush]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return { start, stop, push, isRunning, mode: modeRef };
}
