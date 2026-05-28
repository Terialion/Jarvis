// ============================================================================
// Cache strategy — provider-aware prompt cache breakpoint injection
//
// Anthropic/DeepSeek/Qwen all support cache_control: { type: "ephemeral" }
// breakpoints. Each breakpoint tells the provider "this message and everything
// before it is worth caching." Multiple breakpoints create nested cache regions:
// when only the user's request changes, ALL prefixes hit; when memory updates,
// earlier prefixes still hit.
// ============================================================================

// Providers known to support Anthropic-compatible prompt caching
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

/** Tags that vary between turns — must NOT be checkpointed. */
const VOLATILE_TAG_MARKERS = [
  '<conversation-summary>',
  '<conversation-history>',
  '─── current request ───',
];

// ============================================================================
// Public API
// ============================================================================

export function supportsPromptCaching(
  provider?: string | null,
  model?: string | null,
): boolean {
  const lower = ((provider ?? '') + (model ?? '')).toLowerCase();
  return CACHE_COMPATIBLE_PROVIDERS.some((p) => lower.includes(p));
}

/**
 * Mark a single message with a cache_control breakpoint.
 * Returns a shallow copy — does not mutate the original.
 */
export function markCacheable<T extends Record<string, unknown>>(message: T): T {
  return { ...message, cache_control: CACHE_BREAKPOINT };
}

/**
 * Inject cache_control breakpoints at stable-content boundaries.
 * Walks the messages array, marking: system prompt, project context,
 * skills index, and memory snapshots. Skips conversation history and
 * the current user request (those change every turn).
 */
export function injectCacheBreakpoints(
  messages: Array<Record<string, unknown>>,
  opts: { provider?: string | null; model?: string | null },
): Array<Record<string, unknown>> {
  if (!supportsPromptCaching(opts.provider, opts.model)) return messages;

  const result = [...messages];

  // System prompt is always cacheable (doesn't change within a session)
  if (result.length > 0 && result[0].role === 'system') {
    result[0] = markCacheable(result[0]);
  }

  // Walk remaining messages: checkpoint stable sections, stop at volatile ones
  for (let i = 1; i < result.length; i++) {
    const msg = result[i];
    const content = String(msg.content ?? '');

    // Stop at volatile boundaries — conversation history & user input are per-turn
    if (VOLATILE_TAG_MARKERS.some((tag) => content.includes(tag))) {
      break;
    }

    // Checkpoint stable sections
    if (msg.role === 'user' && STABLE_TAG_MARKERS.some((tag) => content.includes(tag))) {
      result[i] = markCacheable(msg);
    }
  }

  return result;
}