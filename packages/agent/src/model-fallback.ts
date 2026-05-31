// ============================================================================
// Fallback LLM Provider — automatic failover between providers
// ============================================================================
//
// Tries providers in order. If one fails with a retryable error (network,
// auth, 429, 5xx), tries the next. Non-retryable errors (400, invalid request)
// are thrown immediately without fallback.

import type { LLMMessage, LLMResponse, StreamCallbacks, ModelConfig } from './model.js';
import { LLMProvider } from './model.js';

/** Error types that trigger fallback to next provider. */
function isRetryableError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message.toLowerCase();

  // Network errors
  if (msg.includes('econnrefused') || msg.includes('econnreset') ||
      msg.includes('etimedout') || msg.includes('enotfound') ||
      msg.includes('socket hang up') || msg.includes('network')) {
    return true;
  }

  // Rate limit (429)
  if (msg.includes('429') || msg.includes('rate limit')) {
    return true;
  }

  // Server errors (5xx)
  if (msg.includes('500') || msg.includes('502') || msg.includes('503') || msg.includes('504')) {
    return true;
  }

  // Auth errors (might be expired key)
  if (msg.includes('401') || msg.includes('unauthorized') || msg.includes('invalid api key')) {
    return true;
  }

  // Timeout
  if (msg.includes('timeout') || msg.includes('timed out')) {
    return true;
  }

  return false;
}

export interface FallbackProviderConfig {
  /** Primary + fallback providers in priority order */
  providers: ModelConfig[];
  /** Log fallback events (default: true) */
  logFallback?: boolean;
}

/**
 * Wraps multiple LLMProviders. Tries primary first, falls back to alternatives
 * on retryable errors (network, auth, rate limit, 5xx).
 */
export class FallbackLLMProvider {
  private providers: LLMProvider[];
  private currentIndex = 0;
  private logFallback: boolean;

  constructor(config: FallbackProviderConfig) {
    this.logFallback = config.logFallback !== false;
    this.providers = config.providers.map((cfg) => new LLMProvider(cfg));
  }

  /** Get the currently active provider. */
  get active(): LLMProvider {
    return this.providers[this.currentIndex]!;
  }

  /** Get all providers (for diagnostics). */
  get all(): LLMProvider[] {
    return [...this.providers];
  }

  /** Get current provider index (0 = primary). */
  get activeIndex(): number {
    return this.currentIndex;
  }

  /** Reset to primary provider. */
  resetToPrimary(): void {
    this.currentIndex = 0;
  }

  /** Chat with automatic fallback. */
  async chat(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
  ): Promise<LLMResponse> {
    let lastError: unknown;

    for (let i = this.currentIndex; i < this.providers.length; i++) {
      try {
        const result = await this.providers[i]!.chat(messages, tools);
        // Success — if we fell back, stay on this provider for the rest of the session
        if (i !== this.currentIndex) {
          if (this.logFallback) {
            console.warn(`[FallbackLLM] Switched to provider ${i} (${this.providers[i]!.parsedModel.cleanName})`);
          }
          this.currentIndex = i;
        }
        return result;
      } catch (error) {
        lastError = error;
        if (!isRetryableError(error) || i === this.providers.length - 1) {
          throw error;
        }
        if (this.logFallback) {
          const errMsg = error instanceof Error ? error.message : String(error);
          console.warn(`[FallbackLLM] Provider ${i} (${this.providers[i]!.parsedModel.cleanName}) failed: ${errMsg.slice(0, 100)}. Trying next...`);
        }
      }
    }

    throw lastError;
  }

  /** Stream chat with automatic fallback. */
  async chatStream(
    messages: LLMMessage[],
    tools: Record<string, unknown>[],
    callbacks: StreamCallbacks,
  ): Promise<LLMResponse> {
    let lastError: unknown;

    for (let i = this.currentIndex; i < this.providers.length; i++) {
      try {
        const result = await this.providers[i]!.chatStream(messages, tools, callbacks);
        if (i !== this.currentIndex) {
          if (this.logFallback) {
            console.warn(`[FallbackLLM] Switched to provider ${i} (${this.providers[i]!.parsedModel.cleanName})`);
          }
          this.currentIndex = i;
        }
        return result;
      } catch (error) {
        lastError = error;
        if (!isRetryableError(error) || i === this.providers.length - 1) {
          throw error;
        }
        if (this.logFallback) {
          const errMsg = error instanceof Error ? error.message : String(error);
          console.warn(`[FallbackLLM] Provider ${i} (${this.providers[i]!.parsedModel.cleanName}) failed: ${errMsg.slice(0, 100)}. Trying next...`);
        }
      }
    }

    throw lastError;
  }

  /** Get diagnostics info. */
  diagnostics(): { active: number; total: number; models: string[] } {
    return {
      active: this.currentIndex,
      total: this.providers.length,
      models: this.providers.map((p) => p.parsedModel.cleanName),
    };
  }
}
