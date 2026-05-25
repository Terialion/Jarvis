// ============================================================================
// TokenTracker — accumulate token usage across turns with compact display
// ============================================================================

import type { TokenUsage } from './model.js';

// ============================================================================
// Compact formatter (ported from Codex format_tokens_compact)
// ============================================================================

/**
 * Format a token count as a compact string.
 * Examples: 42 → "42", 1234 → "1.2K", 1234567 → "1.2M"
 */
export function formatTokensCompact(value: number): string {
  if (value < 0) return '0';
  if (value < 1000) return String(value);
  if (value < 1_000_000) return _formatWithUnit(value, 1_000, 'K');
  if (value < 1_000_000_000) return _formatWithUnit(value, 1_000_000, 'M');
  return _formatWithUnit(value, 1_000_000_000, 'B');
}

function _formatWithUnit(value: number, divisor: number, unit: string): string {
  const divided = value / divisor;
  let decimals: number;
  if (divided < 10) decimals = 2;
  else if (divided < 100) decimals = 1;
  else decimals = 0;

  let formatted = divided.toFixed(decimals);
  // Strip trailing zeros after decimal
  if (formatted.includes('.')) {
    formatted = formatted.replace(/0+$/, '');
    if (formatted.endsWith('.')) formatted = formatted.slice(0, -1);
  }
  return `${formatted}${unit}`;
}

// ============================================================================
// TokenTracker
// ============================================================================

export interface TokenSnapshot {
  /** Total tokens accumulated (used for context window % calculation) */
  totalTokens: number;
  /** Input tokens (prompt) */
  inputTokens: number;
  /** Output tokens (completion) */
  outputTokens: number;
  /** Cached tokens (prompt cache hits) */
  cachedTokens: number;
  /** Turn count */
  turnCount: number;
  /** Context window size in tokens */
  contextWindow: number;
}

export class TokenTracker {
  private _totalInput = 0;
  private _totalOutput = 0;
  private _totalCached = 0;
  private _turnCount = 0;
  private _contextWindow: number;

  constructor(contextWindow = 128_000) {
    this._contextWindow = contextWindow;
  }

  get contextWindow(): number {
    return this._contextWindow;
  }

  set contextWindow(cw: number) {
    this._contextWindow = cw;
  }

  /** Record token usage from one LLM call. */
  record(usage: TokenUsage): void {
    this._totalInput += usage.promptTokens;
    this._totalOutput += usage.completionTokens;
    this._totalCached += usage.cachedTokens;
    this._turnCount++;
  }

  /** Sum of input (non-cached) + output tokens */
  get totalBlended(): number {
    return this._totalInput - this._totalCached + this._totalOutput;
  }

  /** Total tokens in context window (includes system prompt + history) */
  get totalTokens(): number {
    return this._totalInput + this._totalOutput;
  }

  get inputTokens(): number {
    return this._totalInput;
  }

  get outputTokens(): number {
    return this._totalOutput;
  }

  get cachedTokens(): number {
    return this._totalCached;
  }

  get turnCount(): number {
    return this._turnCount;
  }

  /** Percentage of context window remaining. */
  get contextPercentRemaining(): number {
    // Use last-turn token count as estimate of current context size
    if (this._contextWindow <= 0) return 100;
    const used = this.totalTokens;
    const pct = Math.round(((this._contextWindow - used) / this._contextWindow) * 100);
    return Math.max(0, Math.min(100, pct));
  }

  /** Snapshot for display. */
  snapshot(): TokenSnapshot {
    return {
      totalTokens: this.totalTokens,
      inputTokens: this.inputTokens,
      outputTokens: this.outputTokens,
      cachedTokens: this.cachedTokens,
      turnCount: this.turnCount,
      contextWindow: this.contextWindow,
    };
  }

  /** Reset all counters. */
  reset(): void {
    this._totalInput = 0;
    this._totalOutput = 0;
    this._totalCached = 0;
    this._turnCount = 0;
  }
}
