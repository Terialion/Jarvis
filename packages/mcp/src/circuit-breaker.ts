// ============================================================================
// Circuit Breaker — prevents repeated calls to failing MCP servers
// ============================================================================
//
// Pattern: 3 consecutive failures → open circuit for 60 seconds.
// After cooldown, allow one probe call (half-open). Success resets.
// Based on OpenClaw/Hermes implementation.

const FAILURE_THRESHOLD = 3;
const COOLDOWN_MS = 60_000;

type CircuitState = 'closed' | 'open' | 'half-open';

export class CircuitBreaker {
  private failures = 0;
  private state: CircuitState = 'closed';
  private openedAt = 0;

  /** Check if a request is allowed. Returns null if OK, or error message if blocked. */
  check(): string | null {
    if (this.state === 'closed') return null;

    if (this.state === 'open') {
      const elapsed = Date.now() - this.openedAt;
      if (elapsed >= COOLDOWN_MS) {
        this.state = 'half-open';
        return null; // allow probe
      }
      return `Circuit breaker open: server failed ${FAILURE_THRESHOLD} times. Retry in ${Math.ceil((COOLDOWN_MS - elapsed) / 1000)}s`;
    }

    // half-open: allow one probe
    return null;
  }

  /** Record a successful call — resets the circuit. */
  recordSuccess(): void {
    this.failures = 0;
    this.state = 'closed';
  }

  /** Record a failed call — increments failure count, may open circuit. */
  recordFailure(): void {
    this.failures++;
    if (this.failures >= FAILURE_THRESHOLD) {
      this.state = 'open';
      this.openedAt = Date.now();
    }
  }

  /** Current state for diagnostics. */
  get currentState(): CircuitState {
    if (this.state === 'open' && Date.now() - this.openedAt >= COOLDOWN_MS) {
      return 'half-open';
    }
    return this.state;
  }

  get consecutiveFailures(): number {
    return this.failures;
  }
}
