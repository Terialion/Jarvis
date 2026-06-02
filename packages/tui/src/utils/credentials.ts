// ============================================================================
// Credential resolution — shared provider config lookup for model switching
// ============================================================================

import { findModel } from '@jarvis/agent';
import { loadJarvisConfig } from '@jarvis/shared';

/** Official provider endpoints — used as baseURL fallback. */
const PROVIDER_BASE_URLS: Record<string, string> = {
  'deepseek': 'https://api.deepseek.com/v1',
  'openai': 'https://api.openai.com/v1',
  'anthropic': 'https://api.anthropic.com/v1',
  'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  'xiaomi': 'https://token-plan-cn.xiaomimimo.com/v1',
};

export interface ResolvedCredentials {
  apiKey: string | undefined;
  baseURL: string | undefined;
}

/**
 * Resolve API credentials for a given model based on provider config.
 *
 * Priority:
 * 1. Global proxy (config.proxy.enabled) — overrides everything
 * 2. Per-provider config (config.providers[providerName]) — explicit api_key + base_url
 * 3. Official provider endpoint (baseURL only, no apiKey)
 * 4. Undefined — LLMProvider constructor falls back to JARVIS_LLM_API_KEY / OPENAI_API_KEY env vars
 */
export function resolveModelCredentials(model: string): ResolvedCredentials {
  const catalogEntry = findModel(model);
  const providerName = catalogEntry?.provider;
  const config = loadJarvisConfig();

  // 1. Global proxy overrides everything
  if (config.proxy?.enabled) {
    return {
      apiKey: config.proxy.api_key,
      baseURL: config.proxy.base_url,
    };
  }

  let apiKey: string | undefined;
  let baseURL: string | undefined;

  // 2. Per-provider config (e.g. school proxy for deepseek/qwen, official key for openai)
  if (providerName && config.providers?.[providerName]) {
    const p = config.providers[providerName];
    apiKey = p.api_key;
    baseURL = p.base_url;
  }

  // 3. Official provider endpoint (baseURL only, no apiKey)
  if (!baseURL && providerName && PROVIDER_BASE_URLS[providerName]) {
    baseURL = PROVIDER_BASE_URLS[providerName];
  }

  return { apiKey, baseURL };
}
