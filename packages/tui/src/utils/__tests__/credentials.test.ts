import { describe, it, expect } from 'vitest';
import { resolveModelCredentials } from '../credentials.js';

describe('resolveModelCredentials', () => {
  it('resolves credentials for deepseek model', () => {
    const result = resolveModelCredentials('deepseek-v4-flash');
    expect(result.baseURL).toBeDefined();
    expect(typeof result.baseURL).toBe('string');
  });

  it('resolves credentials for qwen model', () => {
    const result = resolveModelCredentials('qwen3.6-reasoner');
    expect(result.baseURL).toBeDefined();
    expect(typeof result.baseURL).toBe('string');
  });

  it('returns both undefined for unknown model with no provider', () => {
    const result = resolveModelCredentials('totally-unknown-model-xyz');
    expect(result.apiKey).toBeUndefined();
    expect(result.baseURL).toBeUndefined();
  });

  it('does not throw for empty or garbage model names', () => {
    expect(() => resolveModelCredentials('')).not.toThrow();
    expect(() => resolveModelCredentials('!@#$%^&*()')).not.toThrow();
  });

  it('returns consistent results for same model', () => {
    const r1 = resolveModelCredentials('deepseek-v4-flash');
    const r2 = resolveModelCredentials('deepseek-v4-flash');
    expect(r1.apiKey).toBe(r2.apiKey);
    expect(r1.baseURL).toBe(r2.baseURL);
  });
});
