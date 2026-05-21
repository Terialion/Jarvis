// ============================================================================
// ContextBuilder — token budget management and message compaction
// ============================================================================

import type { ChatMessage } from '@jarvis/shared';

// ============================================================================
// Configuration
// ============================================================================

export interface ContextConfig {
  /** Maximum token budget for the full context window */
  maxTokens?: number;
  /** Fraction of maxTokens at which compression is triggered (0-1) */
  thresholdPercent?: number;
  /** Number of messages from the start to protect (system + early context) */
  protectFirstN?: number;
  /** Number of messages from the end to protect (recent conversation) */
  protectLastN?: number;
}

// ============================================================================
// Internal context types
// ============================================================================

interface ContextMessage {
  role: string;
  content: string;
  tool_call_id?: string;
  name?: string;
  tool_calls?: Array<{
    id: string;
    type: 'function';
    function: { name: string; arguments: string };
  }>;
}

// ============================================================================
// ContextBuilder
// ============================================================================

export class ContextBuilder {
  private config: Required<ContextConfig>;

  constructor(config: ContextConfig = {}) {
    this.config = {
      maxTokens: config.maxTokens ?? 128_000,
      thresholdPercent: config.thresholdPercent ?? 0.75,
      protectFirstN: config.protectFirstN ?? 3,
      protectLastN: config.protectLastN ?? 6,
    };
  }

  // ========================================================================
  // Build full message list for the model
  // ========================================================================

  buildMessages(
    systemPrompt: string,
    history: ChatMessage[],
    tools: Record<string, unknown>[],
  ): ContextMessage[] {
    const messages: ContextMessage[] = [];

    // 1. System prompt
    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }

    // 2. Convert history ChatMessages to LLM format
    for (const msg of history) {
      const cm: ContextMessage = {
        role: msg.role,
        content: msg.content,
        tool_call_id: msg.toolCallId,
        name: msg.name,
      };
      messages.push(cm);
    }

    return messages;
  }

  // ========================================================================
  // Check if compression is needed
  // ========================================================================

  shouldCompress(estimatedTokens: number): boolean {
    return estimatedTokens > this.config.maxTokens * this.config.thresholdPercent;
  }

  // ========================================================================
  // Estimate token count (rough: chars/4 for English text)
  // ========================================================================

  estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }

  /**
   * Estimate token count for an array of ChatMessages.
   */
  estimateMessageTokens(messages: ChatMessage[]): number {
    let total = 0;
    for (const msg of messages) {
      total += this.estimateTokens(msg.content);
    }
    return total;
  }

  // ========================================================================
  // Compact old tool results to summaries
  // ========================================================================

  /**
   * Replace the content of older tool result messages with a summary.
   * Preserves the first `protectFirstN` and last `protectLastN` messages.
   *
   * Tool result messages are identified by role === 'tool'.
   * Their content is replaced with: "[Tool result for {name}: {contentSummary}]"
   */
  compactToolResults(messages: ChatMessage[]): ChatMessage[] {
    const { protectFirstN, protectLastN } = this.config;
    const total = messages.length;

    if (total <= protectFirstN + protectLastN) {
      return messages;
    }

    const start = protectFirstN;
    const end = total - protectLastN;

    const compacted = messages.map((msg, i) => {
      if (i < start || i >= end) return msg;
      if (msg.role !== 'tool') return msg;

      const name = msg.name ?? 'unknown';
      const contentLen = msg.content.length;
      const preview = msg.content.slice(0, 200).replace(/\n/g, ' ');
      const suffix = contentLen > 200 ? '...' : '';

      return {
        ...msg,
        content: `[Tool result for ${name} (${contentLen} chars): ${preview}${suffix}]`,
      };
    });

    return compacted;
  }
}
