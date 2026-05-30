// ============================================================================
// Model Speed Test — benchmark available models by latency
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const modelSpeedTestSchema = toOpenAITool({
  name: 'model_speed_test',
  description:
    'Test which available LLM model is currently the fastest. Sends a simple request to each model via the configured API and returns results sorted by response time. Use when you want to find the fastest model for the current session.',
  parameters: {
    type: 'object',
    properties: {
      models: {
        type: 'array',
        items: { type: 'string' },
        description:
          'Optional list of model names to test. If omitted, all models from the /v1/models endpoint are tested.',
      },
      concurrency: {
        type: 'number',
        default: 5,
        description: 'Max concurrent requests. Default: 5.',
      },
      test_message: {
        type: 'string',
        default: '你好',
        description: 'Test message to send. Default: "你好".',
      },
      max_tokens: {
        type: 'number',
        default: 16,
        description: 'Max tokens to generate per test. Default: 16.',
      },
    },
    required: [],
  },
});

// ---- types ----

interface ModelResult {
  model: string;
  status: 'ok' | 'error';
  totalMs: number;
  firstTokenMs?: number;
  tokens?: number;
  error?: string;
}

// ---- helpers ----

function getBaseURL(): string {
  return (
    process.env.JARVIS_LLM_BASE_URL ||
    process.env.OPENAI_BASE_URL ||
    'https://api.deepseek.com/v1'
  );
}

function getApiKey(): string {
  return (
    process.env.JARVIS_LLM_API_KEY ||
    process.env.DEEPSEEK_API_KEY ||
    process.env.OPENAI_API_KEY ||
    ''
  );
}

async function fetchModels(baseURL: string, apiKey: string): Promise<string[]> {
  try {
    const res = await fetch(`${baseURL}/models`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (
      data.data?.map((m: { id: string }) => m.id).filter(Boolean) ?? []
    );
  } catch {
    return [];
  }
}

async function testModel(
  baseURL: string,
  apiKey: string,
  model: string,
  testMessage: string,
  maxTokens: number,
): Promise<ModelResult> {
  const start = Date.now();
  let firstTokenMs: number | undefined;

  try {
    const res = await fetch(`${baseURL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: testMessage }],
        max_tokens: maxTokens,
        stream: true,
      }),
    });

    if (!res.ok) {
      const errBody = await res.text().catch(() => '');
      return {
        model,
        status: 'error',
        totalMs: Date.now() - start,
        error: `HTTP ${res.status}: ${errBody.slice(0, 200)}`,
      };
    }

    if (!res.body) {
      return {
        model,
        status: 'error',
        totalMs: Date.now() - start,
        error: 'No response body',
      };
    }

    let tokenCount = 0;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;
        const payload = trimmed.slice(6);
        if (payload === '[DONE]') continue;

        try {
          const json = JSON.parse(payload);
          const content = json.choices?.[0]?.delta?.content;
          if (content) {
            tokenCount++;
            if (firstTokenMs === undefined) {
              firstTokenMs = Date.now() - start;
            }
          }
        } catch {
          // skip unparseable chunks
        }
      }
    }

    return {
      model,
      status: 'ok',
      totalMs: Date.now() - start,
      firstTokenMs,
      tokens: tokenCount,
    };
  } catch (err) {
    return {
      model,
      status: 'error',
      totalMs: Date.now() - start,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

// ---- handler ----

const handler: ToolHandler = async (args) => {
  const apiKey = getApiKey();
  if (!apiKey) {
    return JSON.stringify({
      error: 'No API key found. Set JARVIS_LLM_API_KEY or configure ~/.jarvis/config.json.',
    });
  }

  const baseURL = getBaseURL();
  const concurrency = Number(args.concurrency ?? 5);
  const testMessage = String(args.test_message ?? '你好');
  const maxTokens = Number(args.max_tokens ?? 16);

  // Resolve model list
  let models: string[];
  if (args.models && Array.isArray(args.models)) {
    models = args.models.filter((m) => typeof m === 'string' && m);
  } else {
    models = await fetchModels(baseURL, apiKey);
  }

  if (!models.length) {
    return JSON.stringify({
      error:
        'No models found. Either the /v1/models endpoint returned nothing, or no models were specified.',
    });
  }

  // Run benchmark with concurrency limit
  const results: ModelResult[] = [];
  for (let i = 0; i < models.length; i += concurrency) {
    const batch = models.slice(i, i + concurrency);
    const batchResults = await Promise.all(
      batch.map((m) => testModel(baseURL, apiKey, m, testMessage, maxTokens)),
    );
    results.push(...batchResults);
  }

  // Sort: ok first (by totalMs asc), then errors
  results.sort((a, b) => {
    if (a.status === 'ok' && b.status !== 'ok') return -1;
    if (a.status !== 'ok' && b.status === 'ok') return 1;
    return a.totalMs - b.totalMs;
  });

  // Format output
  const fastest = results.find((r) => r.status === 'ok');
  return JSON.stringify(
    {
      base_url: baseURL,
      total_tested: results.length,
      fastest_model: fastest?.model,
      fastest_total_ms: fastest?.totalMs,
      fastest_first_token_ms: fastest?.firstTokenMs,
      results,
    },
    null,
    2,
  );
};

// ---- entry ----

export const modelSpeedTestTool: ToolEntry = {
  name: 'model_speed_test',
  toolset: 'llm',
  schema: modelSpeedTestSchema,
  handler,
  checkFn: () => true,
  isAsync: true,
  emoji: '⚡',
  maxResultSizeChars: 20_000,
};