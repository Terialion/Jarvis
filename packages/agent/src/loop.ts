// ============================================================================
// AgentLoop — the core agent loop orchestrating LLM calls and tool dispatch
// ============================================================================

import type { ChatMessage, ToolResult } from '@jarvis/shared';
import type { ToolRegistry } from '@jarvis/tools';
import { LLMProvider, type ModelConfig } from './model.js';
import { AgentEventBus } from './events.js';
import { ContextBuilder, type ContextConfig } from './context.js';
import { withRetry, type RetryConfig } from './retry.js';

// ============================================================================
// Configuration
// ============================================================================

export interface AgentLoopConfig {
  /** Model configuration for the LLM provider */
  model: ModelConfig;
  /** Maximum conversation turns before stopping, default 30 */
  maxTurns?: number;
  /** Tool registry for dispatching tool calls */
  tools?: ToolRegistry;
  /** System prompt prepended to every conversation */
  systemPrompt?: string;
  /** Event bus for emitting lifecycle events */
  eventBus?: AgentEventBus;
  /** Context builder configuration */
  context?: ContextConfig;
  /** Optional pre-configured LLM provider (for testing) */
  provider?: LLMProvider;
}

// ============================================================================
// Turn Result
// ============================================================================

export interface TurnResult {
  turnId: string;
  messages: ChatMessage[];
  answer: string;
  toolResults: ToolResult[];
  stopReason: string;
  turnsUsed: number;
}

// ============================================================================
// AgentLoop
// ============================================================================

export class AgentLoop {
  private config: Required<Omit<AgentLoopConfig, 'tools' | 'eventBus' | 'provider'>> & {
    tools?: ToolRegistry;
    eventBus?: AgentEventBus;
    provider?: LLMProvider;
  };
  private provider: LLMProvider;
  private tools?: ToolRegistry;
  private eventBus?: AgentEventBus;
  private contextBuilder: ContextBuilder;

  constructor(config: AgentLoopConfig) {
    this.config = {
      model: config.model,
      maxTurns: config.maxTurns ?? 30,
      systemPrompt: config.systemPrompt ?? '',
      context: config.context ?? {},
      tools: config.tools,
      eventBus: config.eventBus,
      provider: config.provider,
    };

    this.provider = config.provider ?? new LLMProvider(config.model);
    this.tools = config.tools;
    this.eventBus = config.eventBus;
    this.contextBuilder = new ContextBuilder(config.context);
  }

  // ========================================================================
  // Run a single conversation turn
  // ========================================================================

  async run(
    userMessage: string,
    history: ChatMessage[] = [],
  ): Promise<TurnResult> {
    const turnId = `turn_${crypto.randomUUID()}`;
    let allMessages: ChatMessage[] = [...history];
    const allToolResults: ToolResult[] = [];

    // Create the user message
    const userMsg: ChatMessage = {
      role: 'user',
      content: userMessage,
      messageId: `msg_${crypto.randomUUID()}`,
    };
    allMessages.push(userMsg);

    this.eventBus?.emit('turn:start', { turnId, userMessage });

    let turnsUsed = 0;
    let finalContent = '';
    let stopReason = 'unknown';

    for (let turn = 0; turn < this.config.maxTurns; turn++) {
      turnsUsed = turn + 1;

      // Build messages for LLM call
      const llmMessages = this.contextBuilder.buildMessages(this.config.systemPrompt, allMessages);

      // Compaction check
      const estimatedTokens = this.contextBuilder.estimateMessageTokens(allMessages);
      if (this.contextBuilder.shouldCompress(estimatedTokens)) {
        this.eventBus?.emit('context:compressing', {
          turnId,
          estimatedTokens,
          maxTokens: this.config.context.maxTokens ?? 128_000,
        });
        // Note: full compaction via summarization would require an LLM call.
        // For now, we compact old tool results inline.
        allMessages = this.contextBuilder.compactToolResults(allMessages);
      }

      // Get tool definitions from registry
      const toolDefs = this.tools
        ? this.tools.getDefinitions()
        : [];

      // Call LLM with retry
      this.eventBus?.emit('llm:request', { turnId, turn, messageCount: llmMessages.length });

      let response: Awaited<ReturnType<typeof this.provider.chat>>;
      try {
        response = await withRetry(
          () => this.provider.chat(llmMessages, toolDefs),
          {
            maxRetries: this.config.model.maxRetries ?? 3,
            baseDelay: 5_000,
            maxDelay: 120_000,
          },
        );
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err);
        this.eventBus?.emit('llm:error', { turnId, turn, error: errMsg });
        stopReason = 'llm_error';
        finalContent = `Error calling LLM after retries: ${errMsg}`;
        break;
      }

      const { content, toolCalls, finishReason } = response;

      this.eventBus?.emit('llm:response', {
        turnId,
        turn,
        finishReason,
        contentLength: content.length,
        toolCallCount: toolCalls.length,
      });

      // Create assistant message
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content,
        messageId: `msg_${crypto.randomUUID()}`,
      };
      allMessages.push(assistantMsg);

      // If model stopped, we're done
      if (finishReason === 'stop') {
        finalContent = content;
        stopReason = 'stop';
        break;
      }

      // If model wants to call tools
      if (finishReason === 'tool_calls' && toolCalls.length > 0) {
        for (const tc of toolCalls) {
          this.eventBus?.emit('tool:executing', {
            turnId,
            turn,
            toolName: tc.name,
            args: tc.arguments,
          });

          let toolResult: ToolResult;
          if (this.tools) {
            const rawResult = await this.tools.dispatch(
              tc.name,
              tc.arguments,
            );

            // Parse the dispatch result into a structured ToolResult
            let parsed: Record<string, unknown> | null = null;
            try {
              parsed = JSON.parse(rawResult);
            } catch {
              // Not valid JSON
            }

            toolResult = {
              callId: tc.callId,
              name: tc.name,
              ok: parsed === null || typeof parsed.error !== 'string',
              content: rawResult,
              error:
                parsed && typeof parsed.error === 'string'
                  ? parsed.error
                  : undefined,
              durationMs: 0,
            };
          } else {
            toolResult = {
              callId: tc.callId,
              name: tc.name,
              ok: false,
              content: '',
              error: 'No tool registry configured',
              durationMs: 0,
            };
          }

          allToolResults.push(toolResult);

          // Create tool result message
          const toolMsg: ChatMessage = {
            role: 'tool',
            content: toolResult.content,
            messageId: `msg_${crypto.randomUUID()}`,
            name: tc.name,
            toolCallId: tc.callId,
          };
          allMessages.push(toolMsg);

          this.eventBus?.emit('tool:result', {
            turnId,
            turn,
            toolName: tc.name,
            ok: toolResult.ok,
            contentLength: toolResult.content.length,
            durationMs: toolResult.durationMs,
          });
        }
        continue; // Loop again for next turn
      }

      // Handle length/content_filter — not ideal, break
      if (finishReason === 'length') {
        finalContent = content;
        stopReason = 'length';
        this.eventBus?.emit('turn:warning', {
          turnId,
          turn,
          warning: 'Response truncated due to length limit',
        });
        break;
      }

      if (finishReason === 'content_filter') {
        stopReason = 'content_filter';
        finalContent = content || 'Response blocked by content filter';
        break;
      }

      // Unknown finish reason — treat as stop
      finalContent = content;
      stopReason = finishReason;
      break;
    }

    // Check if we hit max turns
    if (turnsUsed >= this.config.maxTurns && !finalContent) {
      stopReason = 'max_turns';
      finalContent =
        allMessages
          .filter((m) => m.role === 'assistant')
          .pop()?.content ?? '';
    }

    this.eventBus?.emit('turn:complete', {
      turnId,
      turnsUsed,
      stopReason,
      answerLength: finalContent.length,
    });

    return {
      turnId,
      messages: allMessages,
      answer: finalContent,
      toolResults: allToolResults,
      stopReason,
      turnsUsed,
    };
  }
}
