// ============================================================================
// LLM Provider — OpenAI-compatible chat completion with streaming support
// ============================================================================

import OpenAI from 'openai';
import type { ToolCall } from '@jarvis/shared';

// ============================================================================
// Configuration
// ============================================================================

export interface ModelConfig {
  /** Base URL for the API endpoint (e.g. "https://api.deepseek.com/v1") */
  baseURL?: string;
  /** API key (falls back to env JARVIS_LLM_API_KEY) */
  apiKey?: string;
  /** Model identifier (e.g. "deepseek-chat", "gpt-4o") */
  model: string;
  /** Sampling temperature (0-2), default depends on provider */
  temperature?: number;
  /** Max completion tokens */
  maxTokens?: number;
  /** Max retry attempts on transient failures, default 3 */
  maxRetries?: number;
  /** Request timeout in ms, default 120000 */
  timeout?: number;
}

// ============================================================================
// Token Usage
// ============================================================================

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  cachedTokens: number;
}

// ============================================================================
// LLM Response (normalized from provider)
// ============================================================================

export interface LLMResponse {
  content: string;
  toolCalls: ToolCall[];
  finishReason: 'stop' | 'tool_calls' | 'length' | 'content_filter';
  usage?: TokenUsage;
}

// ============================================================================
// Message type for LLM calls
// ============================================================================

export interface LLMMessage {
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
// Stream callbacks
// ============================================================================

export interface StreamCallbacks {
  onToken?: (token: string) => void;
  onToolCall?: (toolCall: ToolCall) => void;
}

// ============================================================================
// LLMProvider
// ============================================================================

export class LLMProvider {
  private client: OpenAI;
  private config: ModelConfig;

  constructor(config: ModelConfig) {
    this.config = {
      maxRetries: 3,
      timeout: 120_000,
      ...config,
    };

    // Use a placeholder key when none is provided (for testing / lazy config)
    const apiKey =
      this.config.apiKey ??
      process.env['JARVIS_LLM_API_KEY'] ??
      process.env['OPENAI_API_KEY'] ??
      'sk-placeholder';

    this.client = new OpenAI({
      baseURL: this.config.baseURL,
      apiKey,
      timeout: this.config.timeout,
      maxRetries: this.config.maxRetries,
    });
  }

  // ==========================================================================
  // Non-streaming chat completion
  // ==========================================================================

  async chat(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
  ): Promise<LLMResponse> {
    const params: OpenAI.Chat.Completions.ChatCompletionCreateParamsNonStreaming = {
      model: this.config.model,
      messages: messages as OpenAI.Chat.Completions.ChatCompletionMessageParam[],
      stream: false,
    };

    if (this.config.temperature !== undefined) {
      params.temperature = this.config.temperature;
    }
    if (this.config.maxTokens !== undefined) {
      params.max_tokens = this.config.maxTokens;
    }
    if (tools && tools.length > 0) {
      params.tools = tools as unknown as OpenAI.Chat.Completions.ChatCompletionTool[];
    }

    const response = await this.client.chat.completions.create(params);
    return this._normalizeResponse(response);
  }

  // ==========================================================================
  // Streaming chat completion
  // ==========================================================================

  async chatStream(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
    callbacks?: StreamCallbacks,
  ): Promise<LLMResponse> {
    const params: OpenAI.Chat.Completions.ChatCompletionCreateParamsStreaming = {
      model: this.config.model,
      messages: messages as OpenAI.Chat.Completions.ChatCompletionMessageParam[],
      stream: true,
      stream_options: { include_usage: true },
    };

    if (this.config.temperature !== undefined) {
      params.temperature = this.config.temperature;
    }
    if (this.config.maxTokens !== undefined) {
      params.max_tokens = this.config.maxTokens;
    }
    if (tools && tools.length > 0) {
      params.tools = tools as unknown as OpenAI.Chat.Completions.ChatCompletionTool[];
    }

    const stream = await this.client.chat.completions.create(params);

    // Accumulate content and tool calls from stream chunks
    let content = '';
    const toolCallAccumulators = new Map<
      number,
      { id: string; name: string; arguments: string }
    >();
    let finishReason: LLMResponse['finishReason'] = 'stop';
    let usage: TokenUsage | undefined;

    for await (const chunk of stream) {
      const delta = chunk.choices?.[0]?.delta;
      const chunkFinishReason = chunk.choices?.[0]?.finish_reason;

      if (delta?.content) {
        content += delta.content;
        callbacks?.onToken?.(delta.content);
      }

      if (delta?.tool_calls) {
        for (const tc of delta.tool_calls) {
          const idx = tc.index;
          if (!toolCallAccumulators.has(idx)) {
            toolCallAccumulators.set(idx, {
              id: tc.id ?? '',
              name: tc.function?.name ?? '',
              arguments: '',
            });
          }
          const acc = toolCallAccumulators.get(idx)!;
          if (tc.id) acc.id = tc.id;
          if (tc.function?.name) acc.name = tc.function.name;
          if (tc.function?.arguments) acc.arguments += tc.function.arguments;
        }
      }

      if (chunkFinishReason) {
        const reasonMap: Record<string, LLMResponse['finishReason']> = {
          stop: 'stop',
          tool_calls: 'tool_calls',
          length: 'length',
          content_filter: 'content_filter',
        };
        finishReason = reasonMap[chunkFinishReason] ?? 'stop';
      }

      // Usage may come in the final chunk when stream_options.include_usage is set
      if (chunk.usage) {
        usage = {
          promptTokens: chunk.usage.prompt_tokens ?? 0,
          completionTokens: chunk.usage.completion_tokens ?? 0,
          totalTokens: chunk.usage.total_tokens ?? 0,
          cachedTokens:
            (chunk.usage as unknown as Record<string, unknown>)['prompt_tokens_details'] &&
            typeof (
              (chunk.usage as unknown as Record<string, unknown>)[
                'prompt_tokens_details'
              ] as Record<string, unknown>
            )?.['cached_tokens'] === 'number'
              ? (
                  (
                    (chunk.usage as unknown as Record<string, unknown>)[
                      'prompt_tokens_details'
                    ] as Record<string, unknown>
                  )['cached_tokens'] as number
                )
              : 0,
        };
      }
    }

    // Build tool calls from accumulators
    const toolCalls: ToolCall[] = [];
    const sorted = [...toolCallAccumulators.entries()].sort(([a], [b]) => a - b);
    for (const [, acc] of sorted) {
      const callId = acc.id || `call_${crypto.randomUUID()}`;
      let parsedArgs: Record<string, unknown> = {};
      try {
        parsedArgs = JSON.parse(acc.arguments);
      } catch {
        parsedArgs = { _raw: acc.arguments };
      }

      const toolCall: ToolCall = {
        callId,
        name: acc.name,
        arguments: parsedArgs,
        source: 'model',
      };
      toolCalls.push(toolCall);
      callbacks?.onToolCall?.(toolCall);
    }

    return {
      content,
      toolCalls,
      finishReason,
      usage,
    };
  }

  // ==========================================================================
  // Normalize an OpenAI response to LLMResponse
  // ==========================================================================

  private _normalizeResponse(
    response: OpenAI.Chat.Completions.ChatCompletion,
  ): LLMResponse {
    const choice = response.choices?.[0];
    const message = choice?.message;
    const finishReason = choice?.finish_reason ?? 'stop';

    const reasonMap: Record<string, LLMResponse['finishReason']> = {
      stop: 'stop',
      tool_calls: 'tool_calls',
      length: 'length',
      content_filter: 'content_filter',
    };

    const toolCalls: ToolCall[] = (message?.tool_calls ?? [])
      .filter((tc): tc is OpenAI.Chat.Completions.ChatCompletionMessageFunctionToolCall =>
        'function' in tc,
      )
      .map((tc) => {
        let parsedArgs: Record<string, unknown> = {};
        try {
          parsedArgs = JSON.parse(tc.function.arguments);
        } catch {
          parsedArgs = { _raw: tc.function.arguments };
        }
        return {
          callId: tc.id,
          name: tc.function.name,
          arguments: parsedArgs,
          source: 'model',
        };
      });

    const usage: TokenUsage | undefined = response.usage
      ? {
          promptTokens: response.usage.prompt_tokens,
          completionTokens: response.usage.completion_tokens,
          totalTokens: response.usage.total_tokens,
          cachedTokens:
            (response.usage as unknown as Record<string, unknown>)[
              'prompt_tokens_details'
            ] &&
            typeof (
              (response.usage as unknown as Record<string, unknown>)[
                'prompt_tokens_details'
              ] as Record<string, unknown>
            )?.['cached_tokens'] === 'number'
              ? (
                  (
                    (response.usage as unknown as Record<string, unknown>)[
                      'prompt_tokens_details'
                    ] as Record<string, unknown>
                  )['cached_tokens'] as number
                )
              : 0,
        }
      : undefined;

    return {
      content: message?.content ?? '',
      toolCalls,
      finishReason: reasonMap[finishReason] ?? 'stop',
      usage,
    };
  }
}
