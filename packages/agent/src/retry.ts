// ============================================================================
// Retry utilities — jittered backoff, error classification, failure tracking
// ============================================================================

import type { ToolCall, ToolResult } from '@jarvis/shared';

// ============================================================================
// Jittered Backoff
// ============================================================================

/**
 * Calculate delay with jittered exponential backoff.
 *
 * Formula: min(base * 2^(attempt-1), maxDelay) * (1 - jitterRatio * random)
 *
 * @param attempt  1-indexed attempt number (1 = first retry after initial failure)
 * @param baseDelay  Base delay in ms, default 5000
 * @param maxDelay   Maximum delay in ms, default 120000
 * @param jitterRatio  Fraction of delay to randomize, default 0.3 (30%)
 */
export function jitteredBackoff(
  attempt: number,
  baseDelay = 5_000,
  maxDelay = 120_000,
  jitterRatio = 0.3,
): number {
  const exponential = baseDelay * Math.pow(2, attempt - 1);
  const capped = Math.min(exponential, maxDelay);
  const jitter = capped * jitterRatio * Math.random();
  return capped - jitter;
}

// ============================================================================
// Retry Configuration
// ============================================================================

export interface RetryConfig {
  /** Maximum number of retry attempts (not including the initial call) */
  maxRetries: number;
  /** Base delay in ms between retries, default 5000 */
  baseDelay?: number;
  /** Maximum delay in ms between retries, default 120000 */
  maxDelay?: number;
  /** HTTP status codes that trigger a retry */
  retryOn?: number[];
}

// ============================================================================
// withRetry
// ============================================================================

/**
 * Execute an async function with retry logic.
 *
 * Retries on:
 * - Any error matching shouldRetry (if provided)
 * - HTTP errors with status codes in config.retryOn
 * - Network/timeout errors (by default)
 *
 * Uses jittered exponential backoff between attempts.
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  config: RetryConfig,
  shouldRetry?: (error: unknown) => boolean,
): Promise<T> {
  const baseDelay = config.baseDelay ?? 5_000;
  const maxDelay = config.maxDelay ?? 120_000;
  const retryOn = config.retryOn ?? [429, 500, 502, 503, 504];

  let lastError: unknown;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // If this was the last attempt, rethrow
      if (attempt >= config.maxRetries) {
        throw error;
      }

      // Check if we should retry this error
      const shouldRetryThis =
        shouldRetry?.(error) ??
        _isRetryableError(error, retryOn) ??
        true;

      if (!shouldRetryThis) {
        throw error;
      }

      // Wait before retrying
      const delay = jitteredBackoff(attempt + 1, baseDelay, maxDelay);
      await _sleep(delay);
    }
  }

  // Should never reach here, but satisfy TypeScript
  throw lastError;
}

// ============================================================================
// Internal helpers
// ============================================================================

function _sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Determine if an error is retryable based on common error shapes.
 */
function _isRetryableError(error: unknown, retryOn: number[]): boolean | null {
  if (error && typeof error === 'object') {
    const err = error as Record<string, unknown>;

    // Check HTTP status code on error object (OpenAI SDK pattern)
    if (typeof err['status'] === 'number') {
      if (retryOn.includes(err['status'] as number)) return true;
      return false;
    }

    if (err['error'] && typeof err['error'] === 'object') {
      const inner = err['error'] as Record<string, unknown>;
      if (typeof inner['status'] === 'number') {
        if (retryOn.includes(inner['status'] as number)) return true;
        return false;
      }
    }

    if (typeof err['code'] === 'string') {
      const code = err['code'] as string;
      if (['ECONNRESET', 'ETIMEDOUT', 'ECONNREFUSED', 'ENOTFOUND'].includes(code)) {
        return true;
      }
    }
  }

  if (error instanceof TypeError && error.message.includes('fetch failed')) {
    return true;
  }

  // Return null to defer to the default (retry unknown errors)
  return null;
}

// ============================================================================
// Error Classification
// ============================================================================

export interface ErrorClassification {
  category: string;
  retryable: boolean;
  replan: boolean;
  reason: string;
}

export class ErrorClassifier {
  classify(toolResult: ToolResult): ErrorClassification {
    const err = (toolResult.error ?? '').toLowerCase();
    if (!err) {
      return { category: 'none', retryable: false, replan: false, reason: 'no_error' };
    }
    if (err.includes('timeout')) {
      return { category: 'timeout', retryable: true, replan: false, reason: 'command_timeout' };
    }
    if (err.includes('approval_required') || err.includes('denied') || err.includes('permission')) {
      return { category: 'permission', retryable: false, replan: true, reason: 'permission_denied' };
    }
    if (err.includes('unknown tool') || err.includes('unknown_tool')) {
      return { category: 'tool_schema', retryable: true, replan: true, reason: 'unknown_tool' };
    }
    if (err.includes('not found') || err.includes('does_not_exist') || err.includes('no such file')) {
      return { category: 'not_found', retryable: false, replan: true, reason: 'missing_target' };
    }
    if (err.includes('invalid') || err.includes('malformed') || err.includes('parameter')) {
      return { category: 'bad_params', retryable: true, replan: true, reason: 'invalid_parameters' };
    }
    if (err.includes('assertion') || err.includes('test')) {
      return { category: 'test_failed', retryable: false, replan: true, reason: 'tests_failed' };
    }
    return { category: 'other', retryable: false, replan: true, reason: 'tool_failed' };
  }
}

// ============================================================================
// RetryPolicy
// ============================================================================

export class RetryPolicy {
  private maxRetries: number;
  private retryCounts = new Map<string, number>();

  constructor(maxRetries = 2) {
    this.maxRetries = maxRetries;
  }

  shouldRetry(call: ToolCall, classification: ErrorClassification): boolean {
    if (!classification.retryable) return false;
    const key = `${call.name}:${classification.category}`;
    const used = this.retryCounts.get(key) ?? 0;
    if (used >= this.maxRetries) return false;
    this.retryCounts.set(key, used + 1);
    return true;
  }
}

// ============================================================================
// FailureTracker
// ============================================================================

export interface FailureRecord {
  toolName: string;
  errorCategory: string;
  errorMessage: string;
  step: number;
}

export class FailureTracker {
  private maxConsecutive: number;
  private maxSameTool: number;
  private maxRepeat: number;
  consecutiveFailures: FailureRecord[] = [];
  toolFailureCounts = new Map<string, number>();
  toolTotalCalls = new Map<string, number>();
  private _synthesisNudged = new Set<string>();

  constructor(maxConsecutive = 5, maxSameTool = 4, maxRepeat = 3) {
    this.maxConsecutive = maxConsecutive;
    this.maxSameTool = maxSameTool;
    this.maxRepeat = maxRepeat;
  }

  recordFailure(
    toolName: string,
    errorCategory: string,
    errorMessage: string,
    step: number,
  ): void {
    this.consecutiveFailures.push({ toolName, errorCategory, errorMessage, step });
    this.toolFailureCounts.set(toolName, (this.toolFailureCounts.get(toolName) ?? 0) + 1);
    this.toolTotalCalls.set(toolName, (this.toolTotalCalls.get(toolName) ?? 0) + 1);
  }

  recordSuccess(toolName: string): void {
    this.consecutiveFailures = [];
    this.toolFailureCounts.delete(toolName);
    this.toolTotalCalls.set(toolName, (this.toolTotalCalls.get(toolName) ?? 0) + 1);
  }

  shouldStop(): { stop: boolean; reason: string } {
    if (this.consecutiveFailures.length >= this.maxConsecutive) {
      const last = this.consecutiveFailures[this.consecutiveFailures.length - 1];
      return {
        stop: true,
        reason: `${this.maxConsecutive} consecutive tool failures. Last error (${last.toolName}): ${last.errorMessage.slice(0, 200)}`,
      };
    }
    return { stop: false, reason: '' };
  }

  shouldRejectTool(toolName: string): { reject: boolean; reason: string; kind: string } {
    const failCount = this.toolFailureCounts.get(toolName) ?? 0;
    if (failCount >= this.maxSameTool) {
      return {
        reject: true,
        reason: `Tool \`${toolName}\` has failed ${failCount} times; try a different approach or stop.`,
        kind: 'failure',
      };
    }
    const total = this.toolTotalCalls.get(toolName) ?? 0;
    if (total >= this.maxRepeat) {
      return {
        reject: true,
        reason: `Tool \`${toolName}\` has been called ${total} times this turn. Stop calling it and synthesize a final answer from the results you already have.`,
        kind: 'repeat',
      };
    }
    return { reject: false, reason: '', kind: '' };
  }

  isRepeatHardStop(toolName: string): boolean {
    if (this._synthesisNudged.has(toolName)) return true;
    this._synthesisNudged.add(toolName);
    return false;
  }
}

// ============================================================================
// ReplanPolicy
// ============================================================================

export class ReplanPolicy {
  private maxReplans: number;
  replanCount = 0;

  constructor(maxReplans = 2) {
    this.maxReplans = maxReplans;
  }

  shouldReplan(classification: ErrorClassification): boolean {
    if (!classification.replan) return false;
    if (this.replanCount >= this.maxReplans) return false;
    this.replanCount++;
    return true;
  }

  buildReplanObservation(
    toolResult: ToolResult,
    classification: ErrorClassification,
  ): Record<string, unknown> {
    return {
      event: 'replan_hint',
      tool_name: toolResult.name,
      category: classification.category,
      reason: classification.reason,
      error: toolResult.error,
    };
  }
}
