// ============================================================================
// Retry utilities — jittered exponential backoff + withRetry wrapper
// ============================================================================

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
      // Explicit non-retryable status codes (400, 401, 403, etc.)
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
