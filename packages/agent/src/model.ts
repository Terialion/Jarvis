// ============================================================================
// LLM Provider — OpenAI-compatible chat completion with streaming support
// Non-native tool calling, FakeModelClient for testing
// ============================================================================

import OpenAI from 'openai';
import type { ToolCall, ToolSpec } from '@jarvis/shared';
import { normalizeMessages } from './normalizer.js';
import type { MessageRecord } from './normalizer.js';
import { parseModelName, resolveContextWindow } from './model-catalog.js';
import type { ParsedModelName } from './model-catalog.js';

// ============================================================================
// Configuration
// ============================================================================

export interface ModelConfig {
  baseURL?: string;
  apiKey?: string;
  model: string;
  provider?: string;
  temperature?: number;
  maxTokens?: number;
  maxRetries?: number;
  timeout?: number;
  /** Set to false for models that don't support native function calling. Default: true. */
  supportsNativeToolCalling?: boolean;
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
  finishReason: 'stop' | 'tool_calls' | 'length' | 'content_filter' | 'retry_with_tool_instruction' | 'empty';
  usage?: TokenUsage;
  raw?: Record<string, unknown>;
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
// ModelResponse (compat with shared)
// ============================================================================

export interface ModelResponse {
  assistantText: string;
  reasoningSummary?: string;
  toolCalls: ToolCall[];
  finalAnswer: string;
  finishReason: string;
  raw?: unknown;
}

// ============================================================================
// Tool intent detection helpers
// ============================================================================

const TOOL_INTENT_MARKERS = [
  // English tool-intent phrases
  'tool_call',
  'tool plan',
  'tool_plan',
  'run command',
  'list directory',
  'read file',
  // Chinese tool-intent phrases
  '让我尝试用', '让我试试', '让我来调用', '让我来执行', '让我来运行',
  '让我抓取', '让我读取', '让我搜索', '让我检查', '让我查看',
  '让我看一看', '让我看一下',
  '调用工具', '尝试用工具',
  '写入工具返回',
  '重试一次',
  '再试一下',
];

function looksLikeToolIntentText(text: string): boolean {
  const lowered = text.toLowerCase();
  return TOOL_INTENT_MARKERS.some((m) => lowered.includes(m));
}

// ============================================================================
// FakeModelClient — scriptable test double
// ============================================================================

export class FakeModelClient {
  private scripted: ModelResponse[];

  constructor(scripted: ModelResponse[] = []) {
    this.scripted = [...scripted];
  }

  backendInfo(): Record<string, string> {
    return {
      model_backend: 'fake',
      model_provider: 'fake',
      model_name: 'fake-agent-v0',
      api_key_source: 'none',
    };
  }

  complete(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
    stream?: boolean,
    metadata?: Record<string, unknown>,
  ): ModelResponse {
    void tools; void stream; void metadata;
    if (this.scripted.length > 0) {
      return this.scripted.shift()!;
    }

    const originalText = latestUserText(messages);
    const hasChinese = /[一-鿿]/.test(originalText);

    const noLlmMsg = hasChinese
      ? '没有配置LLM提供商。请设置 JARVIS_LLM_API_KEY 环境变量，或运行 jarvis config 进行配置。'
      : 'No LLM provider configured. Set the JARVIS_LLM_API_KEY environment variable or run `jarvis config`.';

    return {
      assistantText: noLlmMsg,
      finalAnswer: noLlmMsg,
      finishReason: 'stop',
      toolCalls: [],
    };
  }

  *completeStream(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
    metadata?: Record<string, unknown>,
  ): Generator<ModelChunk> {
    const response = this.complete(messages, tools, undefined, metadata);
    if (response.reasoningSummary) {
      yield { kind: 'reasoning_delta', reasoningDelta: response.reasoningSummary } as ModelChunk;
    }
    for (const call of response.toolCalls) {
      yield {
        kind: 'tool_call_delta',
        toolCallId: call.callId,
        toolName: call.name,
        toolArgumentsDelta: JSON.stringify(call.arguments),
      } as ModelChunk;
    }
    const text = response.finalAnswer || response.assistantText;
    if (text) {
      const words = text.split(' ');
      for (let i = 0; i < words.length; i += 3) {
        const chunk = (i > 0 ? ' ' : '') + words.slice(i, i + 3).join(' ');
        yield { kind: 'text_delta', textDelta: chunk } as ModelChunk;
      }
    }
    yield { kind: 'done', finishReason: response.finishReason || 'stop' } as ModelChunk;
  }

  static _looksLikeToolIntentText(text: string): boolean {
    return looksLikeToolIntentText(text);
  }
}

// ============================================================================
// ModelChunk (streaming delta)
// ============================================================================

export interface ModelChunk {
  kind: string;
  textDelta?: string;
  progressDelta?: string;
  toolCallId?: string;
  toolName?: string;
  toolArgumentsDelta?: string;
  finishReason?: string;
  reasoningDelta?: string;
  usage?: Record<string, unknown>;
}

// ============================================================================
// LLMProvider
// ============================================================================

export class LLMProvider {
  private client: OpenAI;
  private config: ModelConfig;
  /** Parsed model info with clean name (annotations stripped) and context window */
  readonly parsedModel: ParsedModelName;
  /** Resolved context window for this model session */
  readonly contextWindow: number;
  supportsNativeToolCalling: boolean;

  constructor(config: ModelConfig) {
    this.parsedModel = parseModelName(config.model);
    this.contextWindow = resolveContextWindow(config.model);

    this.config = {
      maxRetries: 3,
      timeout: 120_000,
      ...config,
      // Ensure the clean model name (no [size] annotation) is used for API calls
      model: this.parsedModel.cleanName,
    };

    const apiKey =
      this.config.apiKey ??
      process.env['JARVIS_LLM_API_KEY'] ??
      process.env['OPENAI_API_KEY'];

    if (!apiKey) {
      throw new Error(
        'No API key configured. Set JARVIS_LLM_API_KEY or OPENAI_API_KEY, or pass apiKey in ModelConfig.',
      );
    }

    this.client = new OpenAI({
      baseURL: this.config.baseURL,
      apiKey,
      timeout: this.config.timeout,
      maxRetries: this.config.maxRetries,
    });

    this.supportsNativeToolCalling = config.supportsNativeToolCalling ?? true;
  }

  /** Formatted model name for display (includes context annotation if known). */
  get displayModelName(): string {
    if (this.parsedModel.hasExplicitAnnotation || this.parsedModel.catalogInfo) {
      const cw = this.contextWindow;
      if (cw >= 1_000_000) {
        const m = cw / 1_000_000;
        return `${this.config.model}[${m === Math.round(m) ? Math.round(m) : m.toFixed(1)}m]`;
      }
      return `${this.config.model}[${Math.round(cw / 1000)}k]`;
    }
    return this.config.model;
  }

  // ==========================================================================
  // Non-streaming chat completion
  // ==========================================================================

  async chat(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
  ): Promise<LLMResponse> {
    // Extract tool names for safe→canonical mapping
    // Tools from ToolRegistry are already in OpenAI format: { type:"function", function:{ name, description, parameters } }
    const safeToCanonical = LLMProvider._extractSafeNameMap(tools ?? []);

    // For non-native-tool-calling models: inject tool schemas as text into system prompt
    let prepared = messages;
    if (tools && tools.length > 0 && !this.supportsNativeToolCalling) {
      prepared = LLMProvider._injectToolDescriptionsFromDefs(prepared, tools);
    }

    // Normalize messages for the provider (Qwen, DeepSeek reasoner, etc.)
    const normalized = normalizeMessages(
      prepared as MessageRecord[],
      { provider: this.config.provider ?? '', model: this.config.model },
    ) as unknown as LLMMessage[];

    const params: OpenAI.Chat.Completions.ChatCompletionCreateParamsNonStreaming = {
      model: this.config.model,
      messages: normalized as OpenAI.Chat.Completions.ChatCompletionMessageParam[],
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
    return this._normalizeResponse(response, safeToCanonical);
  }

  /** Build safe_name → canonical_name map from OpenAI-format tool defs. */
  private static _extractSafeNameMap(
    tools: Record<string, unknown>[],
  ): Record<string, string> {
    const map: Record<string, string> = {};
    for (const tool of tools) {
      const fn = (tool as Record<string, unknown>)['function'] as Record<string, unknown> | undefined;
      const name = fn?.['name'] as string | undefined;
      if (name) {
        const safeName = name.replace(/\./g, '_').replace(/-/g, '_');
        if (safeName !== name) {
          map[safeName] = name;
        }
      }
    }
    return map;
  }

  /** Inject tool descriptions as text for non-native-tool-calling models from OpenAI-format defs. */
  private static _injectToolDescriptionsFromDefs(
    messages: LLMMessage[],
    tools: Record<string, unknown>[],
  ): LLMMessage[] {
    const toolEntries: string[] = [];
    for (const tool of tools) {
      const fn = (tool as Record<string, unknown>)['function'] as Record<string, unknown> | undefined;
      if (!fn) continue;
      const name = String(fn['name'] ?? '');
      const desc = String(fn['description'] ?? '');
      const params = (fn['parameters'] as Record<string, unknown>) ?? {};
      const properties = (params['properties'] as Record<string, unknown>) ?? {};
      const required = (params['required'] as string[]) ?? [];
      const safeName = name.replace(/\./g, '_').replace(/-/g, '_');
      let entry = `- ${safeName}: ${desc}`;
      if (Object.keys(properties).length > 0) {
        const paramDesc = Object.entries(properties as Record<string, { description?: string; type?: string }>)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => `${k}: ${v?.description || v?.type || 'string'}`)
          .join(', ');
        entry += `\n  Parameters: ${paramDesc}`;
      }
      if (required.length > 0) {
        entry += `\n  Required: ${required.join(', ')}`;
      }
      toolEntries.push(entry);
    }

    const toolText = `<tool_schemas>\n${toolEntries.join('\n')}\n</tool_schemas>\n\nWhen you need to call a tool, respond with a JSON object:\n\n\`\`\`json\n{"tool_calls": [{"tool_name": "<name>", "arguments": {<params>}}]}\n\`\`\`\n\nOnly use tools listed above. Always output valid JSON.`;

    const systemMsg = messages.find((m) => m.role === 'system');
    if (systemMsg) {
      systemMsg.content = `${systemMsg.content}\n\n${toolText}`;
    } else {
      messages.unshift({ role: 'system', content: toolText });
    }
    return messages;
  }

  // ==========================================================================
  // Streaming chat completion
  // ==========================================================================

  async chatStream(
    messages: LLMMessage[],
    tools?: Record<string, unknown>[],
    callbacks?: StreamCallbacks,
  ): Promise<LLMResponse> {
    // Normalize messages for the provider
    const normalizedStream = normalizeMessages(
      messages as MessageRecord[],
      { provider: this.config.provider ?? '', model: this.config.model },
    ) as unknown as LLMMessage[];

    const params: OpenAI.Chat.Completions.ChatCompletionCreateParamsStreaming = {
      model: this.config.model,
      messages: normalizedStream as OpenAI.Chat.Completions.ChatCompletionMessageParam[],
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

      toolCalls.push({
        callId,
        name: acc.name,
        arguments: parsedArgs,
        source: 'model',
      });
      callbacks?.onToolCall?.(toolCalls[toolCalls.length - 1]);
    }

    return { content, toolCalls, finishReason, usage };
  }

  // ==========================================================================
  // Non-native tool calling support (static utilities)
  // ==========================================================================

  static _looksLikeToolIntentText(text: string): boolean {
    return looksLikeToolIntentText(text);
  }

  static _parseToolPlanFromContent(
    contentText: string,
    safeToCanonical: Record<string, string> = {},
  ): ModelResponse | null {
    const text = contentText.trim();
    if (!text) return null;

    const parsed = parseFirstJsonObject(stripFence(text));
    if (!parsed || typeof parsed !== 'object') return null;

    let payload = parsed as Record<string, unknown>;
    if (payload['tool_plan_json'] && typeof payload['tool_plan_json'] === 'object') {
      payload = payload['tool_plan_json'] as Record<string, unknown>;
    }

    const toolCallsRaw = payload['tool_calls'] as Array<Record<string, unknown>> | undefined;
    const toolCalls: ToolCall[] = [];
    if (Array.isArray(toolCallsRaw)) {
      for (const item of toolCallsRaw) {
        if (typeof item !== 'object') continue;
        const toolName = String(item['tool_name'] || item['name'] || '').trim();
        if (!toolName) continue;
        const canonicalName = safeToCanonical[toolName] || toolName;
        const args =
          typeof item['arguments'] === 'object' && item['arguments'] !== null
            ? (item['arguments'] as Record<string, unknown>)
            : {};
        toolCalls.push({
          callId: `call_${crypto.randomUUID()}`,
          name: canonicalName,
          arguments: args,
          source: 'model',
        });
      }
    }

    if (toolCalls.length > 0) {
      return {
        reasoningSummary: String(payload['thought'] || ''),
        toolCalls,
        finalAnswer: '',
        assistantText: '',
        finishReason: 'tool_calls',
        raw: parsed,
      };
    }

    const answer = String(
      payload['final_answer_text'] ||
        payload['final_answer'] ||
        payload['answer'] ||
        '',
    ).trim();
    if (answer) {
      return {
        assistantText: answer,
        finalAnswer: answer,
        toolCalls: [],
        finishReason: 'stop',
        raw: parsed,
      };
    }

    return null;
  }

  static _parseXmlToolCalls(
    text: string,
    safeToCanonical: Record<string, string> = {},
  ): ToolCall[] {
    const out: ToolCall[] = [];
    const funcPattern = /<tool_call>\s*<function=([^>]+)>(.*?)<\/function>\s*<\/tool_call>/gs;
    const paramPattern = /<parameter=([^>]+)>\s*(.*?)\s*<\/parameter>/gs;

    for (const m of text.matchAll(funcPattern)) {
      const funcName = m[1].trim();
      const body = m[2];
      const args: Record<string, unknown> = {};
      for (const pm of body.matchAll(paramPattern)) {
        const key = pm[1].trim();
        const val = pm[2].trim();
        try {
          args[key] = JSON.parse(val);
        } catch {
          args[key] = val;
        }
      }
      if (funcName) {
        const canonical = safeToCanonical[funcName] || funcName;
        out.push({
          callId: `call_xml_${crypto.randomUUID()}`,
          name: canonical,
          arguments: args,
          source: 'model',
        });
      }
    }
    return out;
  }

  static _filterArtifactsFromAcc(textParts: string[]): string {
    let joined = textParts.join('');

    // Brace-counting: find {"tool_plan_json":{...}} with arbitrary nesting
    const needle = '"tool_plan_json"';
    while (true) {
      const idx = joined.indexOf(needle);
      if (idx === -1) break;
      let braceStart = -1;
      for (let i = idx; i >= 0; i--) {
        if (joined[i] === '{') {
          braceStart = i;
          break;
        }
      }
      if (braceStart === -1) break;
      let depth = 0;
      let pos = braceStart;
      while (pos < joined.length) {
        if (joined[pos] === '{') depth++;
        else if (joined[pos] === '}') {
          depth--;
          if (depth === 0) break;
        }
        pos++;
      }
      joined = joined.slice(0, braceStart) + joined.slice(pos + 1);
    }

    // Remove ```json ... ``` code fences
    joined = joined.replace(/```json\s*[\s\S]*?```/g, '');

    // Remove <tool_call> XML
    joined = joined.replace(
      /<tool_call>\s*<function=[^>]+>.*?<\/function>\s*<\/tool_call>/gs,
      '',
    );

    return joined.trim();
  }

  static _buildOpenaiToolSchema(
    tools: ToolSpec[],
  ): { safeSchema: Record<string, unknown>[]; safeToCanonical: Record<string, string> } {
    const safeSchema: Record<string, unknown>[] = [];
    const safeToCanonical: Record<string, string> = {};
    for (const tool of tools) {
      const safeName = tool.name.replace(/\./g, '_').replace(/-/g, '_');
      safeToCanonical[safeName] = tool.name;
      safeSchema.push({
        type: 'function',
        function: {
          name: safeName,
          description: tool.description,
          parameters: {
            type: 'object',
            properties: (tool.inputSchema['properties'] as Record<string, unknown>) ?? {},
            required: (tool.inputSchema['required'] as string[]) ?? [],
          },
        },
      });
    }
    return { safeSchema, safeToCanonical };
  }

  static _injectToolDescriptions(
    messages: LLMMessage[],
    tools: ToolSpec[],
  ): LLMMessage[] {
    const toolEntries: string[] = [];
    for (const tool of tools) {
      const safeName = tool.name.replace(/\./g, '_').replace(/-/g, '_');
      const params = (tool.inputSchema['properties'] as Record<string, unknown>) ?? {};
      const required = (tool.inputSchema['required'] as string[]) ?? [];
      let entry = `- ${safeName}: ${tool.description}`;
      if (Object.keys(params).length > 0) {
        const paramDesc = Object.entries(params as Record<string, { description?: string; type?: string }>)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => `${k}: ${v?.description || v?.type || 'string'}`)
          .join(', ');
        entry += `\n  Parameters: ${paramDesc}`;
      }
      if (required.length > 0) {
        entry += `\n  Required: ${required.join(', ')}`;
      }
      toolEntries.push(entry);
    }

    const toolText =
      '\n## Available tools\n' +
      'You have the following tools available. To use a tool, output JSON in this format:\n' +
      '```json\n' +
      '{"tool_plan_json": {"thought": "<reasoning>", "tool_calls": [' +
      '{"tool_name": "<name>", "arguments": {<args>}}]}}\n' +
      '```\n\n' +
      toolEntries.join('\n');

    let injected = false;
    const out = messages.map((m) => {
      if (m.role === 'system' && !injected) {
        injected = true;
        return { ...m, content: m.content + toolText };
      }
      return m;
    });
    if (!injected) {
      out.unshift({ role: 'system', content: toolText });
    }
    return out;
  }

  static _redactSensitiveMessage(message: LLMMessage): LLMMessage {
    if (message.role === 'user' || message.role === 'system') {
      let content = message.content;
      // Redact sk-... keys
      content = content.replace(/\bsk-[A-Za-z0-9_-]{4,}\b/g, '[REDACTED_SECRET]');
      // Redact env var assignments
      content = content.replace(
        /\b(JARVIS_LLM_API_KEY|DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*=\s*\S+/gi,
        '$1=[REDACTED]',
      );
      // Redact api_key/token/password: value
      content = content.replace(
        /\b(api[_-]?key|token|password)\s*[:=]\s*\S+/gi,
        '$1:[REDACTED]',
      );
      // Redact Authorization: Bearer ...
      content = content.replace(
        /\bAuthorization\s*:\s*Bearer\s+\S+/gi,
        'Authorization:[REDACTED]',
      );
      return { ...message, content };
    }
    return message;
  }

  // ==========================================================================
  // Normalize an OpenAI response to LLMResponse
  // ==========================================================================

  private _normalizeResponse(
    response: OpenAI.Chat.Completions.ChatCompletion,
    safeToCanonical: Record<string, string> = {},
  ): LLMResponse {
    const choice = response.choices?.[0];
    const message = choice?.message;
    const rawFinish = choice?.finish_reason ?? 'stop';

    const reasonMap: Record<string, LLMResponse['finishReason']> = {
      stop: 'stop',
      tool_calls: 'tool_calls',
      length: 'length',
      content_filter: 'content_filter',
    };

    // Parse native tool calls
    const nativeToolCalls: ToolCall[] = (message?.tool_calls ?? [])
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
        const canonicalName = safeToCanonical[tc.function.name] ?? tc.function.name;
        return {
          callId: tc.id,
          name: canonicalName,
          arguments: parsedArgs,
          source: 'model',
        };
      });

    if (nativeToolCalls.length > 0) {
      return {
        content: message?.content ?? '',
        toolCalls: nativeToolCalls,
        finishReason: 'tool_calls',
        usage: LLMProvider._extractUsage(response),
      };
    }

    // No native tool calls — check content + reasoning for tool intent
    const contentText = String(message?.content ?? '');
    const reasoningText = String(
      (message as unknown as Record<string, unknown>)['reasoning_content'] ?? '',
    );

    for (const sourceText of [contentText, reasoningText]) {
      if (!sourceText || !sourceText.trim()) continue;

      if (
        LLMProvider._looksLikeToolIntentText(sourceText) ||
        sourceText.includes('tool_plan_json')
      ) {
        // Try to salvage tool calls from text
        const salvaged = LLMProvider._parseToolPlanFromContent(sourceText, safeToCanonical);
        if (salvaged && salvaged.toolCalls.length > 0) {
          return {
            content: salvaged.finalAnswer || salvaged.assistantText,
            toolCalls: salvaged.toolCalls,
            finishReason: 'tool_calls',
            raw: salvaged.raw as Record<string, unknown> | undefined,
          };
        }

        // Tool intent detected but can't salvage — nudge the model
        if (sourceText === contentText) {
          return {
            content: '',
            toolCalls: [],
            finishReason: 'retry_with_tool_instruction',
            raw: { retry_reason: 'natural_language_tool_intent' },
          };
        }
      }
    }

    // Normal text response — return as final answer
    if (contentText.trim()) {
      return {
        content: contentText,
        toolCalls: [],
        finishReason: reasonMap[rawFinish] ?? 'stop',
        usage: LLMProvider._extractUsage(response),
      };
    }

    // Empty response — try salvage from content as last resort
    const fallback = LLMProvider._parseToolPlanFromContent(contentText, safeToCanonical);
    if (fallback && fallback.toolCalls.length > 0) {
      return {
        content: fallback.finalAnswer || fallback.assistantText,
        toolCalls: fallback.toolCalls,
        finishReason: 'tool_calls',
        raw: fallback.raw as Record<string, unknown> | undefined,
      };
    }

    return {
      content: fallback?.finalAnswer || fallback?.assistantText || contentText || '',
      toolCalls: [],
      finishReason: 'empty',
      usage: LLMProvider._extractUsage(response),
    };
  }

  private static _extractUsage(
    response: OpenAI.Chat.Completions.ChatCompletion,
  ): TokenUsage | undefined {
    if (!response.usage) return undefined;
    return {
      promptTokens: response.usage.prompt_tokens,
      completionTokens: response.usage.completion_tokens,
      totalTokens: response.usage.total_tokens,
      cachedTokens:
        ((response.usage as unknown as Record<string, unknown>)[
          'prompt_tokens_details'
        ] as Record<string, unknown>)?.['cached_tokens'] as number ?? 0,
    };
  }
}

// ============================================================================
// Shared helpers
// ============================================================================

function latestUserText(messages: LLMMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'user') {
      return messages[i].content;
    }
  }
  return '';
}

function stripFence(text: string): string {
  let t = text.trim();
  if (t.startsWith('```')) t = t.slice(3);
  if (t.endsWith('```')) t = t.slice(0, -3);
  return t.trim();
}

function parseFirstJsonObject(text: string): Record<string, unknown> | null {
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{' || text[i] === '[') {
      try {
        const obj = JSON.parse(text.slice(i));
        if (typeof obj === 'object' && obj !== null) return obj;
      } catch {
        // Try to find a balanced brace pair
        let depth = 0;
        let end = i;
        for (let j = i; j < text.length; j++) {
          if (text[j] === '{' || text[j] === '[') depth++;
          else if (text[j] === '}' || text[j] === ']') {
            depth--;
            if (depth === 0) {
              end = j + 1;
              break;
            }
          }
        }
        if (end > i) {
          try {
            const obj = JSON.parse(text.slice(i, end));
            if (typeof obj === 'object' && obj !== null) return obj;
          } catch { /* continue */ }
        }
      }
    }
  }
  return null;
}
