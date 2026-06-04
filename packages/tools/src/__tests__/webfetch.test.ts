import { describe, it, expect } from 'vitest';
import { createWebFetchHandler } from '../builtin/web-fetch.js';

describe('web_fetch', () => {
  const handler = createWebFetchHandler();

  it('blocks private IPs (SSRF protection)', async () => {
    const result = await handler({ url: 'http://127.0.0.1/secret', prompt: 'test' }, {});
    const parsed = JSON.parse(result as string);
    expect(parsed.error).toContain('private/local');
  });

  it('blocks localhost (SSRF protection)', async () => {
    const result = await handler({ url: 'http://localhost:8080/api', prompt: 'test' }, {});
    const parsed = JSON.parse(result as string);
    expect(parsed.error).toContain('private/local');
  });

  it('fetches real URL (network-dependent)', async () => {
    const result = await handler({ url: 'https://httpbin.org/html', prompt: 'What does this contain?' }, {});
    const parsed = JSON.parse(result as string);
    // Network may not be available in CI
    if (parsed.error) {
      expect(parsed.error).toMatch(/fetch|HTTP|timeout|network/i);
    } else {
      expect(parsed.content).toBeTruthy();
      expect(parsed.content.length).toBeGreaterThan(50);
      expect(parsed.extractor).toBeDefined();
    }
  }, 30_000);
});
