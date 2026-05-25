// ============================================================================
// Model catalog — known model info and context window parsing
// References: Codex models.json, Claude Code context annotations
// ============================================================================

export interface ModelInfo {
  /** Short identifier used in API calls (e.g. "deepseek-v4-pro") */
  slug: string;
  /** Human-readable name */
  displayName: string;
  /** Provider key (deepseek, openai, anthropic, etc.) */
  provider: string;
  /** Default context window in tokens */
  contextWindow: number;
  /** Maximum context window (some models support extended) */
  maxContextWindow: number;
  /** Known aliases for this model */
  aliases?: string[];
}

// ============================================================================
// Known Model Catalog
// ============================================================================

const KNOWN_MODELS: ModelInfo[] = [
  // DeepSeek
  { slug: 'deepseek-v4-pro', displayName: 'DeepSeek V4 Pro', provider: 'deepseek', contextWindow: 1_000_000, maxContextWindow: 1_000_000, aliases: ['deepseek-v4-pro[1m]'] },
  { slug: 'deepseek-v4-flash-ascend', displayName: 'DeepSeek V4 Flash Ascend', provider: 'deepseek', contextWindow: 1_000_000, maxContextWindow: 1_000_000 },
  { slug: 'deepseek-chat', displayName: 'DeepSeek Chat', provider: 'deepseek', contextWindow: 128_000, maxContextWindow: 128_000 },
  { slug: 'qwen3.6-reasoner', displayName: 'Qwen 3.6 Reasoner', provider: 'deepseek', contextWindow: 128_000, maxContextWindow: 128_000 },
  { slug: 'qwen3.6-chat', displayName: 'Qwen 3.6 Chat', provider: 'deepseek', contextWindow: 128_000, maxContextWindow: 128_000 },

  // OpenAI
  { slug: 'gpt-5.4', displayName: 'GPT-5.4', provider: 'openai', contextWindow: 272_000, maxContextWindow: 1_000_000 },
  { slug: 'gpt-5.4-mini', displayName: 'GPT-5.4 Mini', provider: 'openai', contextWindow: 272_000, maxContextWindow: 272_000 },
  { slug: 'gpt-5.3-codex', displayName: 'GPT-5.3 Codex', provider: 'openai', contextWindow: 272_000, maxContextWindow: 272_000 },

  // Anthropic Claude
  { slug: 'claude-opus-4-7', displayName: 'Claude Opus 4.7', provider: 'anthropic', contextWindow: 200_000, maxContextWindow: 200_000 },
  { slug: 'claude-sonnet-4-6', displayName: 'Claude Sonnet 4.6', provider: 'anthropic', contextWindow: 200_000, maxContextWindow: 200_000 },
  { slug: 'claude-haiku-4-5-20251001', displayName: 'Claude Haiku 4.5', provider: 'anthropic', contextWindow: 200_000, maxContextWindow: 200_000 },
  { slug: 'claude-opus-4-6', displayName: 'Claude Opus 4.6', provider: 'anthropic', contextWindow: 200_000, maxContextWindow: 200_000 },

  // Google
  { slug: 'gemini-2.5-pro', displayName: 'Gemini 2.5 Pro', provider: 'google', contextWindow: 1_000_000, maxContextWindow: 2_000_000 },
  { slug: 'gemini-2.5-flash', displayName: 'Gemini 2.5 Flash', provider: 'google', contextWindow: 1_000_000, maxContextWindow: 1_000_000 },

  // OpenRouter common
  { slug: 'openai/gpt-5.4', displayName: 'GPT-5.4 (OpenRouter)', provider: 'openrouter', contextWindow: 272_000, maxContextWindow: 1_000_000 },
  { slug: 'anthropic/claude-opus-4-7', displayName: 'Claude Opus 4.7 (OpenRouter)', provider: 'openrouter', contextWindow: 200_000, maxContextWindow: 200_000 },
];

// ============================================================================
// Parser — handles "model-name[contextSize]" annotations
// ============================================================================

const CONTEXT_ANNOTATION_RE = /^(.+?)\[(\d+(?:\.\d+)?)([km])?\]$/i;

export interface ParsedModelName {
  /** Clean model name for API calls */
  cleanName: string;
  /** Resolved context window in tokens, or undefined if unknown */
  contextWindow?: number;
  /** Whether a [size] annotation was explicitly provided */
  hasExplicitAnnotation: boolean;
  /** The catalog entry if this is a known model */
  catalogInfo?: ModelInfo;
}

/**
 * Parse a model name string.
 * Handles annotations like:
 *   "deepseek-v4-pro[1m]" → cleanName="deepseek-v4-pro", contextWindow=1_000_000
 *   "gpt-5.4[128k]"       → cleanName="gpt-5.4", contextWindow=128_000
 *   "deepseek-chat"       → cleanName="deepseek-chat", contextWindow=128_000 (from catalog)
 */
export function parseModelName(modelName: string): ParsedModelName {
  const trimmed = modelName.trim();
  const annotationMatch = trimmed.match(CONTEXT_ANNOTATION_RE);

  let cleanName = trimmed;
  let hasExplicitAnnotation = false;
  let contextWindow: number | undefined;

  // Strip [size] annotation
  if (annotationMatch) {
    cleanName = annotationMatch[1].trim();
    hasExplicitAnnotation = true;

    const value = parseFloat(annotationMatch[2]);
    const unit = annotationMatch[3]?.toLowerCase();

    if (unit === 'k') {
      contextWindow = Math.round(value * 1_000);
    } else if (unit === 'm') {
      contextWindow = Math.round(value * 1_000_000);
    } else {
      // No unit — assume raw tokens
      contextWindow = Math.round(value);
    }
  }

  // Look up in catalog
  const catalogInfo = findModel(cleanName);

  // Catalog overrides context window only if no explicit annotation
  if (contextWindow === undefined && catalogInfo) {
    contextWindow = catalogInfo.contextWindow;
  }

  return { cleanName, contextWindow, hasExplicitAnnotation, catalogInfo };
}

// ============================================================================
// Catalog lookup
// ============================================================================

/** Look up a model by slug or alias. */
export function findModel(modelName: string): ModelInfo | undefined {
  const trimmed = modelName.trim().toLowerCase();

  // Direct slug match
  const bySlug = KNOWN_MODELS.find((m) => m.slug === trimmed);
  if (bySlug) return bySlug;

  // Alias match
  const byAlias = KNOWN_MODELS.find((m) => m.aliases?.some((a) => a.toLowerCase() === trimmed));
  if (byAlias) return byAlias;

  // Prefix match (for versioned models like "gpt-5.4-2025-01-01")
  const byPrefix = KNOWN_MODELS.find(
    (m) => trimmed.startsWith(m.slug) && trimmed.length > m.slug.length,
  );
  if (byPrefix) return byPrefix;

  return undefined;
}

/** Get context window for a model string, falling back to a default. */
export function resolveContextWindow(
  modelName: string,
  defaultWindow = 128_000,
): number {
  const parsed = parseModelName(modelName);
  return parsed.contextWindow ?? defaultWindow;
}

/** Format a model name with context annotation for display. */
export function formatModelWithContext(modelName: string): string {
  const parsed = parseModelName(modelName);
  if (!parsed.contextWindow) return parsed.cleanName;

  // Format nicely: >1M → "1m", <1M → "128k"
  if (parsed.contextWindow >= 1_000_000) {
    const m = parsed.contextWindow / 1_000_000;
    return `${parsed.cleanName}[${m === Math.round(m) ? Math.round(m) : m.toFixed(1)}m]`;
  }
  const k = parsed.contextWindow / 1_000;
  return `${parsed.cleanName}[${Math.round(k)}k]`;
}
