// ============================================================================
// MemoryExtractor — LLM-driven 2-phase memory extraction pipeline
// Pattern from Codex memories/ subsystem
// ============================================================================

import type { CompactionModelClient } from './compactor.js';

// ============================================================================
// Types
// ============================================================================

export interface MemoryExtractionConfig {
  /** Whether extraction is enabled. Default: false. */
  enabled: boolean;
  /** Max sessions to scan for raw memories. Default: 5. */
  maxSessions: number;
  /** Max tokens per session transcript. Default: 150_000. */
  maxTokensPerSession: number;
  /** Max concurrent extraction jobs. Default: 4. */
  concurrency: number;
  /** Context window ratio to use for extraction prompts. Default: 0.7. */
  contextRatio: number;
}

export interface RawMemory {
  sessionId: string;
  kind: string;
  text: string;
  confidence: number;
}

export interface ConsolidatedMemory {
  summary: string;
  lastUpdated: string;
  sourceSessions: string[];
}

// ============================================================================
// Extraction prompts
// ============================================================================

const EXTRACTION_PROMPT = [
  'Extract important memories from this conversation transcript.',
  'Focus on:',
  '- User preferences and style (names, tools, workflows they prefer)',
  '- Project facts (tech stack, architecture decisions, conventions)',
  '- Active tasks and their current state',
  '- Key decisions and their rationale',
  '',
  'Output as JSON array: [{"kind": "user_pref"|"project_fact"|"task"|"decision", "text": "...", "confidence": 0.0-1.0}]',
  'Confidence: 1.0 = explicitly stated, 0.5 = implied, <0.5 = uncertain.',
  'Only include facts that are clearly stated, not speculation.',
].join('\n');

const CONSOLIDATION_PROMPT = [
  'You are consolidating raw memory fragments extracted from multiple',
  'conversation sessions. Merge them into a coherent memory summary.',
  '',
  'Rules:',
  '- Remove duplicates — keep the most recent/confident version.',
  '- Resolve contradictions — pick the most recent statement.',
  '- Group by topic (preferences, project facts, active tasks, decisions).',
  '- Drop low-confidence (<0.5) or trivial memories.',
  '- Format as markdown sections.',
  '- Keep total output under 5000 tokens.',
  '',
  'Raw memory fragments:',
].join('\n');

// ============================================================================
// MemoryExtractor
// ============================================================================

export class MemoryExtractor {
  private config: Required<MemoryExtractionConfig>;
  private modelClient: CompactionModelClient | null;
  private memoryStore: {
    write(params: { name: string; description: string; memoryType: string; content: string }): Promise<void>;
  } | null;

  constructor(opts?: {
    config?: Partial<MemoryExtractionConfig>;
    modelClient?: CompactionModelClient | null;
    memoryStore?: {
      write(params: { name: string; description: string; memoryType: string; content: string }): Promise<void>;
    } | null;
  }) {
    this.config = {
      enabled: opts?.config?.enabled ?? false,
      maxSessions: opts?.config?.maxSessions ?? 5,
      maxTokensPerSession: opts?.config?.maxTokensPerSession ?? 150_000,
      concurrency: opts?.config?.concurrency ?? 4,
      contextRatio: opts?.config?.contextRatio ?? 0.7,
    };
    this.modelClient = opts?.modelClient ?? null;
    this.memoryStore = opts?.memoryStore ?? null;
  }

  get isEnabled(): boolean {
    return this.config.enabled && this.modelClient !== null;
  }

  // ==========================================================================
  // Phase 1: Extract raw memories from session transcripts
  // ==========================================================================

  async extractRawMemories(
    transcripts: Array<{ sessionId: string; messages: Array<{ role: string; content: string }> }>,
  ): Promise<RawMemory[]> {
    if (!this.modelClient) return [];

    const sessions = transcripts.slice(0, this.config.maxSessions);
    const results: RawMemory[] = [];

    // Process in parallel with concurrency limit
    const chunks: Array<Array<typeof sessions[0]>> = [];
    for (let i = 0; i < sessions.length; i += this.config.concurrency) {
      chunks.push(sessions.slice(i, i + this.config.concurrency));
    }

    for (const chunk of chunks) {
      const chunkResults = await Promise.all(
        chunk.map(async (session) => {
          try {
            return await this._extractFromSession(session);
          } catch {
            return [];
          }
        }),
      );
      for (const r of chunkResults) {
        results.push(...r);
      }
    }

    return results;
  }

  private async _extractFromSession(
    session: { sessionId: string; messages: Array<{ role: string; content: string }> },
  ): Promise<RawMemory[]> {
    if (!this.modelClient) return [];

    // Build transcript text limited to maxTokensPerSession
    const maxChars = this.config.maxTokensPerSession * 4; // rough estimate
    let transcriptText = '';
    for (const msg of session.messages) {
      const line = `[${msg.role}]: ${msg.content}\n`;
      if (transcriptText.length + line.length > maxChars) break;
      transcriptText += line;
    }

    try {
      const result = await this.modelClient.complete({
        messages: [
          { role: 'user', content: EXTRACTION_PROMPT },
          { role: 'user', content: transcriptText.slice(0, maxChars) },
        ],
        max_tokens: 4000,
      });

      const text = result.content ?? result.text ?? '';
      const theJson = extractJsonArray(text);
      if (!theJson) return [];

      return theJson
        .filter((item: unknown) => typeof item === 'object' && item !== null)
        .map((item: Record<string, unknown>) => ({
          sessionId: session.sessionId,
          kind: String(item['kind'] ?? 'project_fact'),
          text: String(item['text'] ?? '').slice(0, 500),
          confidence: Math.min(1, Math.max(0, Number(item['confidence'] ?? 0.5))),
        }));
    } catch {
      return [];
    }
  }

  // ==========================================================================
  // Phase 2: Consolidate raw memories into a summary
  // ==========================================================================

  async consolidateMemories(rawMemories: RawMemory[]): Promise<ConsolidatedMemory | null> {
    if (!this.modelClient || rawMemories.length === 0) return null;

    // Deduplicate by text similarity (simple prefix match)
    const seen = new Set<string>();
    const unique = rawMemories.filter((m) => {
      const prefix = m.text.slice(0, 60).toLowerCase();
      if (seen.has(prefix)) return false;
      seen.add(prefix);
      return m.confidence >= 0.5;
    });

    if (unique.length === 0) return null;

    const memoryText = unique
      .map((m) => `[${m.kind}|conf=${m.confidence}] ${m.text}`)
      .join('\n');

    try {
      const result = await this.modelClient.complete({
        messages: [
          { role: 'user', content: CONSOLIDATION_PROMPT },
          { role: 'user', content: memoryText.slice(0, 10000) },
        ],
        max_tokens: 5000,
      });

      const summary = (result.content ?? result.text ?? '').trim();
      if (!summary) return null;

      const sourceSessions = [...new Set(rawMemories.map((m) => m.sessionId))];

      return {
        summary,
        lastUpdated: new Date().toISOString(),
        sourceSessions,
      };
    } catch {
      // Fallback: return simple concatenation
      return {
        summary: unique.map((m) => `- [${m.kind}] ${m.text}`).join('\n'),
        lastUpdated: new Date().toISOString(),
        sourceSessions: [...new Set(rawMemories.map((m) => m.sessionId))],
      };
    }
  }

  // ==========================================================================
  // Full pipeline: extract → consolidate → write to memory store
  // ==========================================================================

  async run(
    transcripts: Array<{ sessionId: string; messages: Array<{ role: string; content: string }> }>,
  ): Promise<ConsolidatedMemory | null> {
    if (!this.isEnabled) return null;

    const raw = await this.extractRawMemories(transcripts);
    const consolidated = await this.consolidateMemories(raw);

    if (consolidated && this.memoryStore) {
      try {
        await this.memoryStore.write({
          name: 'auto_memory_summary',
          description: 'LLM-extracted memory summary from past sessions',
          memoryType: 'project',
          content: consolidated.summary,
        });
      } catch { /* best-effort */ }
    }

    return consolidated;
  }
}

// ============================================================================
// Helper: extract JSON array from text
// ============================================================================

function extractJsonArray(text: string): Array<Record<string, unknown>> | null {
  const trimmed = text.trim();

  // Try direct parse
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed;
  } catch { /* not direct JSON */ }

  // Try to find JSON array between [ and ]
  const start = trimmed.indexOf('[');
  if (start === -1) return null;

  let depth = 0;
  let end = start;
  for (let i = start; i < trimmed.length; i++) {
    if (trimmed[i] === '[') depth++;
    else if (trimmed[i] === ']') {
      depth--;
      if (depth === 0) {
        end = i + 1;
        break;
      }
    }
  }

  if (end > start) {
    try {
      const parsed = JSON.parse(trimmed.slice(start, end));
      if (Array.isArray(parsed)) return parsed;
    } catch { /* not parseable */ }
  }

  return null;
}
