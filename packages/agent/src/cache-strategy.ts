// ============================================================================
// Cache strategy - provider-aware prompt cache breakpoint injection
// ============================================================================

const CACHE_COMPATIBLE_PROVIDERS = ['deepseek', 'anthropic', 'qwen'];

const CACHE_BREAKPOINT = { type: 'ephemeral' } as const;

/** Stable-content XML tags that should always be checkpointed. */
const STABLE_TAG_MARKERS = [
  '<project-context>',
  '<settings-update>',
  '<skills>',
  '<available-memory>',
  '<memory-context>',
];

/** Tags that vary between turns and must not be checkpointed. */
const VOLATILE_TAG_MARKERS = [
  '<conversation-summary>',
  '<conversation-history>',
  '<current-request>',
];

export function supportsPromptCaching(
  provider?: string | null,
  model?: string | null,
): boolean {
  const lower = ((provider ?? '') + (model ?? '')).toLowerCase();
  return CACHE_COMPATIBLE_PROVIDERS.some((p) => lower.includes(p));
}

/**
 * Mark a single message with a cache_control breakpoint.
 * Returns a shallow copy and does not mutate the original.
 */
export function markCacheable<T extends Record<string, unknown>>(message: T): T {
  return { ...message, cache_control: CACHE_BREAKPOINT };
}

/**
 * Inject cache_control breakpoints at stable-content boundaries.
 * Stable sections are checkpointed until the first volatile, per-turn boundary.
 */
export function injectCacheBreakpoints(
  messages: Array<Record<string, unknown>>,
  opts: { provider?: string | null; model?: string | null },
): Array<Record<string, unknown>> {
  if (!supportsPromptCaching(opts.provider, opts.model)) return messages;

  const result = [...messages];

  if (result.length > 0 && result[0].role === 'system') {
    result[0] = markCacheable(result[0]);
  }

  for (let i = 1; i < result.length; i++) {
    const msg = result[i];
    const content = String(msg.content ?? '');
    const promptPart = msg.promptPart as { category?: string; bucket?: string } | undefined;

    if (promptPart?.category === 'intent' || promptPart?.bucket === 'intent') {
      break;
    }

    if (promptPart?.category === 'history') {
      break;
    }

    if (VOLATILE_TAG_MARKERS.some((tag) => content.includes(tag))) {
      break;
    }

    if (
      promptPart?.category === 'context'
      && ['project', 'settings', 'skills', 'memory'].includes(promptPart.bucket ?? '')
    ) {
      result[i] = markCacheable(msg);
      continue;
    }

    if (msg.role === 'user' && STABLE_TAG_MARKERS.some((tag) => content.includes(tag))) {
      result[i] = markCacheable(msg);
    }
  }

  return result;
}
