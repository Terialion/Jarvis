#!/usr/bin/env tsx
// ============================================================================
// Model Benchmark — measure TTFT, throughput, and latency for all configured models
// Usage: tsx scripts/benchmark-models.ts [options]
//
// Options:
//   --models <slug,...>   Comma-separated model slugs to benchmark (default: all)
//   --iterations <n>      Number of runs per model (default: 3)
//   --prompt <text>       Prompt to send (default: "Return hello world in JSON")
//   --max-tokens <n>      Max completion tokens (default: 100)
//   --concurrent          Run models concurrently (default: sequential)
//   --timeout <ms>        Per-request timeout in ms (default: 60000)
// ============================================================================

import { LLMProvider, getAllModels, type ModelInfo } from '@jarvis/agent';
import { loadJarvisConfig, type JarvisConfig, type ProviderConfig } from '@jarvis/shared';

// ============================================================================
// Types
// ============================================================================

interface BenchmarkResult {
  model: string;
  displayName: string;
  provider: string;
  success: number;
  fail: number;
  /** Time to first token (ms) */
  ttftMs: number[];
  /** Total duration (ms) */
  totalMs: number[];
  /** Output tokens per second */
  tokensPerSec: number[];
  /** Total tokens generated */
  outputTokens: number[];
}

// ============================================================================
// CLI args
// ============================================================================

function parseArgs(): {
  modelSlugs: string[];
  iterations: number;
  prompt: string;
  maxTokens: number;
  concurrent: boolean;
  timeout: number;
} {
  const args = process.argv.slice(2);
  const get = (flag: string, def: string): string => {
    const idx = args.indexOf(flag);
    return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : def;
  };
  const has = (flag: string): boolean => args.includes(flag);

  return {
    modelSlugs: get('--models', '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    iterations: Math.max(1, parseInt(get('--iterations', '3'), 10) || 3),
    prompt: get('--prompt', 'Return hello world in JSON format with a greeting and a timestamp.'),
    maxTokens: Math.max(10, parseInt(get('--max-tokens', '100'), 10) || 100),
    concurrent: has('--concurrent'),
    timeout: Math.max(5000, parseInt(get('--timeout', '60000'), 10) || 60000),
  };
}

// ============================================================================
// Resolve credentials for a model
// ============================================================================

function resolveProviderConfig(
  model: ModelInfo,
  config: JarvisConfig,
): { baseURL: string; apiKey: string } {
  const providerName = model.provider;
  const providerCfg: ProviderConfig | undefined = config.providers?.[providerName];

  // Resolve API key: per-provider -> global config -> env vars (generic + provider-specific)
  const apiKey =
    providerCfg?.api_key?.trim() ||
    config.api_key?.trim() ||
    process.env['JARVIS_LLM_API_KEY']?.trim() ||
    process.env[`${providerName.toUpperCase()}_API_KEY`]?.trim() ||
    process.env['DEEPSEEK_API_KEY']?.trim() ||
    process.env['OPENAI_API_KEY']?.trim() ||
    '';

  // Resolve base URL: per-provider -> global config -> env vars -> default
  const baseURL =
    providerCfg?.base_url?.trim() ||
    config.base_url?.trim() ||
    process.env['JARVIS_LLM_BASE_URL']?.trim() ||
    `https://api.${providerName}.com/v1`; // fallback guess

  return { baseURL, apiKey };
}

// ============================================================================
// Run a single benchmark iteration
// ============================================================================

interface IterationResult {
  success: boolean;
  ttftMs: number;
  totalMs: number;
  tokensPerSec: number;
  outputTokens: number;
  error?: string;
}

async function runIteration(
  slug: string,
  baseURL: string,
  apiKey: string,
  prompt: string,
  maxTokens: number,
  timeout: number,
): Promise<IterationResult> {
  const provider = new LLMProvider({
    model: slug,
    baseURL,
    apiKey,
    maxTokens,
    timeout,
    maxRetries: 0,
    supportsNativeToolCalling: false,
    temperature: 0,
  });

  const startTime = performance.now();
  let firstTokenTime: number | null = null;
  let outputTokens = 0;

  try {
    const response = await provider.chatStream(
      [{ role: 'user', content: prompt }],
      [],
      {
        onToken: (token: string) => {
          if (firstTokenTime === null) {
            firstTokenTime = performance.now();
          }
          // Rough token estimate: 1 token ≈ 4 chars for English
          outputTokens += Math.max(1, Math.ceil(token.length / 4));
        },
      },
    );

    const endTime = performance.now();

    if (firstTokenTime === null) {
      // No streaming tokens received, use total time as fallback
      firstTokenTime = endTime;
    }

    // If we have usage info from the response, use that for more accurate token count
    if (response.usage?.completionTokens) {
      outputTokens = response.usage.completionTokens;
    } else if (response.content) {
      outputTokens = Math.max(outputTokens, Math.ceil(response.content.length / 4));
    }

    const ttft = firstTokenTime - startTime;
    const total = endTime - startTime;
    const tokensPerSec = total > 0 ? (outputTokens / total) * 1000 : 0;

    return { success: true, ttftMs: ttft, totalMs: total, tokensPerSec, outputTokens };
  } catch (err) {
    const endTime = performance.now();
    const errorMsg = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      ttftMs: firstTokenTime ? firstTokenTime - startTime : endTime - startTime,
      totalMs: endTime - startTime,
      tokensPerSec: 0,
      outputTokens: 0,
      error: errorMsg,
    };
  }
}

// ============================================================================
// Format helpers
// ============================================================================

function avg(arr: number[]): string {
  if (arr.length === 0) return 'N/A';
  return (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1);
}

function min(arr: number[]): string {
  if (arr.length === 0) return 'N/A';
  return Math.min(...arr).toFixed(1);
}

function max(arr: number[]): string {
  if (arr.length === 0) return 'N/A';
  return Math.max(...arr).toFixed(1);
}

function pad(s: string, len: number): string {
  return s.padEnd(len);
}

// ============================================================================
// Main
// ============================================================================

async function main() {
  const cli = parseArgs();
  const config = loadJarvisConfig();
  const allModels = getAllModels();

  // Filter to requested models, or use all
  const targets: ModelInfo[] = cli.modelSlugs.length > 0
    ? allModels.filter((m) => cli.modelSlugs.includes(m.slug))
    : allModels;

  if (targets.length === 0) {
    console.error('No models found to benchmark.');
    console.error('Available models:', allModels.map((m) => m.slug).join(', '));
    process.exit(1);
  }

  console.log('='.repeat(120));
  console.log('  LLM Model Benchmark');
  console.log('='.repeat(120));
  console.log(`  Prompt:      "${cli.prompt.slice(0, 80)}${cli.prompt.length > 80 ? '...' : ''}"`);
  console.log(`  Max tokens:  ${cli.maxTokens}`);
  console.log(`  Iterations:  ${cli.iterations}`);
  console.log(`  Mode:        ${cli.concurrent ? 'concurrent' : 'sequential'}`);
  console.log(`  Models:      ${targets.length} (${targets.map((m) => m.slug).join(', ')})`);
  console.log('-'.repeat(120));
  console.log('');

  const results: BenchmarkResult[] = [];

  const runModel = async (model: ModelInfo): Promise<void> => {
    const { baseURL, apiKey } = resolveProviderConfig(model, config);
    const hasKey = apiKey.length > 0;

    console.log(`  [${model.slug}] resolving credentials...` + (hasKey ? '' : ' ⚠️  NO API KEY'));

    const result: BenchmarkResult = {
      model: model.slug,
      displayName: model.displayName,
      provider: model.provider,
      success: 0,
      fail: 0,
      ttftMs: [],
      totalMs: [],
      tokensPerSec: [],
      outputTokens: [],
    };

    if (!hasKey) {
      result.fail = cli.iterations;
      results.push(result);
      return;
    }

    for (let i = 0; i < cli.iterations; i++) {
      process.stdout.write(`  [${model.slug}] iteration ${i + 1}/${cli.iterations}... `);
      const iterResult = await runIteration(
        model.slug,
        baseURL,
        apiKey,
        cli.prompt,
        cli.maxTokens,
        cli.timeout,
      );

      if (iterResult.success) {
        result.success++;
        result.ttftMs.push(iterResult.ttftMs);
        result.totalMs.push(iterResult.totalMs);
        result.tokensPerSec.push(iterResult.tokensPerSec);
        result.outputTokens.push(iterResult.outputTokens);
        process.stdout.write(`✅ TTFT=${iterResult.ttftMs.toFixed(0)}ms Total=${iterResult.totalMs.toFixed(0)}ms ${iterResult.tokensPerSec.toFixed(1)}tok/s\n`);
      } else {
        result.fail++;
        process.stdout.write(`❌ ${(iterResult.error ?? 'unknown').slice(0, 60)}\n`);
      }
    }

    results.push(result);
  };

  if (cli.concurrent) {
    await Promise.all(targets.map(runModel));
  } else {
    for (const model of targets) {
      await runModel(model);
    }
  }

  // ==========================================================================
  // Results table
  // ==========================================================================

  console.log('');
  console.log('='.repeat(120));
  console.log('  RESULTS');
  console.log('='.repeat(120));

  const header = [
    pad('Model', 28),
    pad('Provider', 12),
    pad('Success', 8),
    pad('TTFT(avg)', 12),
    pad('TTFT(min)', 12),
    pad('Total(avg)', 12),
    pad('Total(min)', 12),
    pad('Tok/s(avg)', 12),
  ].join(' | ');

  console.log(header);
  console.log('-'.repeat(120));

  for (const r of results) {
    const line = [
      pad(r.model, 28),
      pad(r.provider, 12),
      pad(`${r.success}/${r.success + r.fail}`, 8),
      pad(r.ttftMs.length > 0 ? `${avg(r.ttftMs)}ms` : 'N/A', 12),
      pad(r.ttftMs.length > 0 ? `${min(r.ttftMs)}ms` : 'N/A', 12),
      pad(r.totalMs.length > 0 ? `${avg(r.totalMs)}ms` : 'N/A', 12),
      pad(r.totalMs.length > 0 ? `${min(r.totalMs)}ms` : 'N/A', 12),
      pad(r.tokensPerSec.length > 0 ? `${avg(r.tokensPerSec)}` : 'N/A', 12),
    ].join(' | ');
    console.log(line);
  }

  console.log('-'.repeat(120));
  console.log('');
}

main().catch((err) => {
  console.error('Benchmark failed:', err);
  process.exit(1);
});