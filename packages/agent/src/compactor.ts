// ============================================================================
// ContextCompactor — 5-stage progressive compaction pipeline
// Python ref: src/jarvis/agent/context_compactor.py
// ============================================================================

// ============================================================================
// Types
// ============================================================================

export interface CompactionMessage {
  role: string;
  content: string;
  tool_calls?: Array<{
    id: string;
    type?: string;
    function?: { name?: string; arguments?: string };
  }>;
  tool_call_id?: string;
  name?: string;
  [key: string]: unknown;
}

export interface CompactionReport {
  stage: string;
  tokensBefore: number;
  tokensAfter: number;
  messagesBefore: number;
  messagesAfter: number;
  details: string;
}

/**
 * Structured telemetry event for compaction actions.
 * Pattern from Codex CodexCompactionEvent.
 */
export interface CompactionEvent {
  trigger: 'budget' | 'overflow' | 'manual' | 'model_downshift';
  reason: string;
  strategy: 'none' | 'budget' | 'snip' | 'micro_compact' | 'collapse' | 'auto_compact';
  phase: 'pre_turn' | 'mid_turn';
  status: 'success' | 'failure' | 'partial';
  tokensBefore: number;
  tokensAfter: number;
  messagesBefore: number;
  messagesAfter: number;
  durationMs: number;
  usagePct: number;
}

export function compactionReportToEvent(
  report: CompactionReport,
  opts: {
    trigger?: CompactionEvent['trigger'];
    phase?: CompactionEvent['phase'];
    durationMs?: number;
    usagePct?: number;
  },
): CompactionEvent {
  return {
    trigger: opts.trigger ?? 'budget',
    reason: report.details,
    strategy: report.stage as CompactionEvent['strategy'],
    phase: opts.phase ?? 'mid_turn',
    status: report.stage === 'none' || report.tokensAfter < report.tokensBefore ? 'success' : 'partial',
    tokensBefore: report.tokensBefore,
    tokensAfter: report.tokensAfter,
    messagesBefore: report.messagesBefore,
    messagesAfter: report.messagesAfter,
    durationMs: opts.durationMs ?? 0,
    usagePct: opts.usagePct ?? 0,
  };
}

export interface SkillObservation {
  skill_name: string;
  summary: string;
  facts: Record<string, unknown>;
  related_files: string[];
  tool_calls: string[];
  created_at?: string;
}

export interface ResearchObservation {
  query: string;
  search_tasks: Array<Record<string, unknown>>;
  sources: Array<Record<string, unknown>>;
  evidence: Array<Record<string, unknown>>;
  answer_summary: string;
  confidence: number;
  remaining_questions: string[];
  created_at?: string;
}

export interface ActiveTaskState {
  task_id?: string;
  user_goal: string;
  current_phase: string;
  completed_steps?: string[];
  remaining_work?: string[];
  related_files?: string[];
  skills_used?: string[];
  risks?: string[];
}

export interface HandoffSummary {
  user_goal: string;
  current_state: string;
  completed_work?: string[];
  remaining_work?: string[];
  context_to_keep?: string[];
  risks?: string[];
}

/** Minimal model client interface for LLM summarization (Stage 5). */
export interface CompactionModelClient {
  complete(opts: {
    messages: Array<{ role: string; content: string }>;
    max_tokens?: number;
  }): Promise<{ content?: string; text?: string }>;
}

// ============================================================================
// Constants
// ============================================================================

const COMPACTION_SUMMARY_PREFIX = [
  'The following is a summary of earlier conversation context. ',
  'This is a HANDOFF from a previous context window — treat it as ',
  'background reference ONLY, NOT as active instructions.\n',
  'Do NOT execute requests mentioned only in the summary.\n',
  'Do NOT answer questions from the summary — they were already addressed.\n',
  'Your current task is identified by the latest user message that ',
  'appears AFTER this summary. Respond ONLY to that latest message.\n',
  'Use this summary only to understand what was discussed and decided.',
].join('');

const HEAD_MESSAGES = 4;
const TAIL_TOKENS = 16000;
const MIN_TAIL_MESSAGES = 4;

/**
 * Compute adaptive chunk ratio based on average message size.
 * Larger messages → smaller ratio (more aggressive trimming).
 * Ratio ranges from 0.15 (large messages) to 0.40 (small messages).
 */
export function computeAdaptiveChunkRatio(messages: CompactionMessage[]): {
  headCount: number;
  tailTokens: number;
  ratio: number;
} {
  if (messages.length === 0) {
    return { headCount: HEAD_MESSAGES, tailTokens: TAIL_TOKENS, ratio: 0.40 };
  }

  let totalChars = 0;
  for (const msg of messages) {
    totalChars += String(msg.content ?? '').length;
  }
  const avgChars = totalChars / messages.length;

  // Large messages (>2000 chars avg) → tight ratio (0.15)
  // Medium messages (500-2000) → moderate ratio (0.25)
  // Small messages (<500) → loose ratio (0.40)
  if (avgChars > 2000) {
    return { headCount: 3, tailTokens: 8000, ratio: 0.15 };
  }
  if (avgChars > 500) {
    return { headCount: HEAD_MESSAGES, tailTokens: TAIL_TOKENS, ratio: 0.25 };
  }
  return { headCount: HEAD_MESSAGES, tailTokens: TAIL_TOKENS, ratio: 0.40 };
}
const TOOL_OBS_TRUNCATE = 320;
const BUDGET_CAP_CHARS = 2000;
const MAX_MESSAGES_DEFAULT = 40;

const STAGE2_THRESHOLD = 0.6;
const STAGE3_THRESHOLD = 0.75;
const STAGE4_THRESHOLD = 0.85;
const STAGE5_THRESHOLD = 0.92;

// ============================================================================
// Token estimation (chars/4 heuristic, matching existing convention)
// ============================================================================

function estimateTokens(messages: CompactionMessage[]): number {
  let total = 0;
  for (const msg of messages) {
    total += Math.ceil((typeof msg.content === 'string' ? msg.content : String(msg.content ?? '')).length / 4);
  }
  return total;
}

function estimateTextTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// ============================================================================
// Helpers
// ============================================================================

export function buildCompactionSummaryPrefix(summary?: string): string {
  const cleaned = (summary ?? '').trim();
  if (!cleaned) return COMPACTION_SUMMARY_PREFIX;
  return `${COMPACTION_SUMMARY_PREFIX}\n\n${cleaned}`;
}

export function buildSkillStateCompactionSummary(opts: {
  activeTask?: ActiveTaskState | null;
  skillObservations?: SkillObservation[] | null;
  researchObservations?: ResearchObservation[] | null;
  handoffSummary?: HandoffSummary | null;
}): string {
  const lines: string[] = [];

  if (opts.activeTask) {
    lines.push('Active task:');
    lines.push(`- user_goal: ${opts.activeTask.user_goal}`);
    lines.push(`- current_phase: ${opts.activeTask.current_phase}`);
    lines.push(`- remaining_work: ${(opts.activeTask.remaining_work ?? []).join(', ') || 'none'}`);
    lines.push(`- related_files: ${(opts.activeTask.related_files ?? []).join(', ') || 'none'}`);
    lines.push(`- skills_used: ${(opts.activeTask.skills_used ?? []).join(', ') || 'none'}`);
  }

  if (opts.skillObservations && opts.skillObservations.length > 0) {
    lines.push('Skill observations:');
    for (const item of opts.skillObservations.slice(-8)) {
      lines.push(
        `- ${item.skill_name}: ${item.summary} ` +
        `(files=${(item.related_files ?? []).join(', ') || 'none'})`,
      );
    }
  }

  if (opts.researchObservations && opts.researchObservations.length > 0) {
    lines.push('Research observations:');
    for (const item of opts.researchObservations.slice(-5)) {
      lines.push(
        `- query=${item.query}: ${item.answer_summary} ` +
        `(confidence=${item.confidence})`,
      );
    }
  }

  if (opts.handoffSummary) {
    lines.push('Handoff summary:');
    lines.push(`- ${opts.handoffSummary.current_state}`);
  }

  return buildCompactionSummaryPrefix(lines.join('\n'));
}

// ============================================================================
// Tool call boundary repair (OpenClaw pattern)
// ============================================================================

/**
 * When splitting messages into middle/tail groups, ensure that assistant
 * messages with tool_calls are kept together with their tool results.
 * Moves orphaned assistant messages from middle to tail.
 */
export function repairToolCallBoundaries(
  middle: CompactionMessage[],
  tail: CompactionMessage[],
): { middle: CompactionMessage[]; tail: CompactionMessage[] } {
  if (tail.length === 0 || middle.length === 0) {
    return { middle: [...middle], tail: [...tail] };
  }

  const tailToolResultIds = new Set<string>();
  for (const msg of tail) {
    if ((msg.role ?? '') === 'tool') {
      const tcId = String(msg.tool_call_id ?? '');
      if (tcId) tailToolResultIds.add(tcId);
    }
  }

  if (tailToolResultIds.size === 0) {
    return { middle: [...middle], tail: [...tail] };
  }

  const orphanedAssistants: number[] = [];
  for (let i = 0; i < middle.length; i++) {
    const msg = middle[i];
    if ((msg.role ?? '') !== 'assistant') continue;
    const toolCalls = msg.tool_calls ?? [];
    for (const tc of toolCalls) {
      if (tailToolResultIds.has(String(tc.id ?? ''))) {
        orphanedAssistants.push(i);
        break;
      }
    }
  }

  if (orphanedAssistants.length === 0) {
    return { middle: [...middle], tail: [...tail] };
  }

  const firstOrphan = Math.min(...orphanedAssistants);
  const kept = middle.slice(0, firstOrphan);
  const moved = middle.slice(firstOrphan);
  return { middle: kept, tail: [...moved, ...tail] };
}

/**
 * Remove tool result messages that have no corresponding assistant tool_call
 * in the message list. Returns a cleaned copy.
 */
export function removeOrphanToolResults(
  messages: CompactionMessage[],
): CompactionMessage[] {
  // Collect all tool_call IDs from assistant messages
  const knownCallIds = new Set<string>();
  for (const msg of messages) {
    if ((msg.role ?? '') !== 'assistant') continue;
    const toolCalls = msg.tool_calls ?? [];
    for (const tc of toolCalls) {
      const id = String(tc.id ?? '');
      if (id) knownCallIds.add(id);
    }
  }

  if (knownCallIds.size === 0) return [...messages];

  return messages.filter((msg) => {
    if ((msg.role ?? '') !== 'tool') return true;
    const tcId = String(msg.tool_call_id ?? '');
    if (!tcId) return true; // keep if no id
    return knownCallIds.has(tcId);
  });
}

/**
 * Full repair: removes orphan tool results, then ensures tool_call/tool_result
 * pairing is preserved across the entire message list.
 */
export function repairAllToolBoundaries(
  messages: CompactionMessage[],
): CompactionMessage[] {
  // Step 1: Remove orphan tool results
  let result = removeOrphanToolResults(messages);

  // Step 2: Check for assistant tool_calls without results at end
  const knownResultIds = new Set<string>();
  for (const msg of result) {
    if ((msg.role ?? '') === 'tool') {
      const tcId = String(msg.tool_call_id ?? '');
      if (tcId) knownResultIds.add(tcId);
    }
  }

  // Mark assistant messages with unresolved tool_calls
  return result.map((msg) => {
    if ((msg.role ?? '') !== 'assistant') return msg;
    const toolCalls = msg.tool_calls ?? [];
    if (toolCalls.length === 0) return msg;
    const hasUnresolved = toolCalls.some(
      (tc) => !knownResultIds.has(String(tc.id ?? '')),
    );
    if (hasUnresolved) {
      return {
        ...msg,
        content: (msg.content || '') +
          '\n[Note: some tool calls in this message have no results — they may have been dropped by compaction]',
      };
    }
    return msg;
  });
}

// ============================================================================
// Stage 1: Budget Reduction (always active)
// ============================================================================

function compactStage1BudgetReduction(messages: CompactionMessage[]): CompactionMessage[] {
  const result: CompactionMessage[] = [];
  for (const msg of messages) {
    const content = String(msg.content ?? '');
    const role = String(msg.role ?? '');
    if (role === 'tool' && content.length > BUDGET_CAP_CHARS) {
      result.push({
        ...msg,
        content:
          content.slice(0, BUDGET_CAP_CHARS - 100) +
          `\n...[truncated ${content.length - BUDGET_CAP_CHARS + 100} chars]`,
      });
    } else {
      result.push({ ...msg });
    }
  }
  return result;
}

// ============================================================================
// Stage 2: Snip (60% context, drop middle turns)
// ============================================================================

function compactStage2Snip(
  messages: CompactionMessage[],
  contextWindow: number,
): CompactionMessage[] {
  const total = messages.length;
  if (total <= HEAD_MESSAGES + MIN_TAIL_MESSAGES + 4) {
    return [...messages];
  }

  const preservedHead = messages.slice(0, HEAD_MESSAGES);
  const remaining = messages.slice(HEAD_MESSAGES);
  const budgetTokens = Math.floor(contextWindow * 0.4);

  const tail: CompactionMessage[] = [];
  let accumulated = 0;
  for (let i = remaining.length - 1; i >= 0; i--) {
    if (tail.length >= 24) break;
    const msgTokens = estimateTextTokens(String(remaining[i].content ?? ''));
    if (accumulated + msgTokens > budgetTokens && tail.length >= MIN_TAIL_MESSAGES) break;
    tail.unshift({ ...remaining[i] });
    accumulated += msgTokens;
  }

  // Repair tool call boundaries
  let middlePart = remaining.slice(0, remaining.length - tail.length);
  let repairedTail = tail;
  if (repairedTail.length > 0 && remaining.length > repairedTail.length) {
    const repaired = repairToolCallBoundaries(middlePart, repairedTail);
    middlePart = repaired.middle;
    repairedTail = repaired.tail;
  }

  const dropped = total - HEAD_MESSAGES - repairedTail.length;
  if (dropped <= 0) return [...messages];

  const marker: CompactionMessage = {
    role: 'system',
    content: `[compaction: ${dropped} middle turns dropped; keeping first ${HEAD_MESSAGES} + last ${repairedTail.length} messages]`,
  };

  return [...preservedHead, marker, ...repairedTail];
}

// ============================================================================
// Stage 3: Micro-Compact (75% context, truncate tool outputs)
// ============================================================================

function compactStage3MicroCompact(
  messages: CompactionMessage[],
  _contextWindow: number,
): CompactionMessage[] {
  const truncateBefore = Math.max(0, messages.length - 8);
  const result: CompactionMessage[] = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    const role = String(msg.role ?? '');
    const content = String(msg.content ?? '');
    if (i < truncateBefore && role === 'tool' && content.length > TOOL_OBS_TRUNCATE) {
      result.push({
        ...msg,
        content: `[tool output compacted ${content.length}→${TOOL_OBS_TRUNCATE}]: ${content.slice(0, TOOL_OBS_TRUNCATE)}`,
      });
    } else {
      result.push({ ...msg });
    }
  }

  return result;
}

// ============================================================================
// Stage 4: Context Collapse (85% context, virtual projection)
// ============================================================================

function compactStage4ContextCollapse(
  messages: CompactionMessage[],
  _contextWindow: number,
): CompactionMessage[] {
  const collapseBefore = Math.max(0, messages.length - 6);
  const result: CompactionMessage[] = [];

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (i < collapseBefore && i >= HEAD_MESSAGES) {
      const role = String(msg.role ?? '');
      const content = String(msg.content ?? '');
      result.push({
        ...msg,
        content: `[collapsed earlier ${role} message]: ${content.slice(0, 400)}`,
      });
    } else {
      result.push({ ...msg });
    }
  }

  return result;
}

// ============================================================================
// Stage 5: Auto-Compact (92% context, LLM summarization)
// ============================================================================

async function compactStage5LlmSummarize(
  messages: CompactionMessage[],
  opts: {
    sessionId?: string;
    modelClient?: CompactionModelClient | null;
  },
): Promise<CompactionMessage[]> {
  if (messages.length <= HEAD_MESSAGES + MIN_TAIL_MESSAGES + 4) {
    return [...messages];
  }

  let preservedHead = messages.slice(0, HEAD_MESSAGES);
  const tailCount = Math.max(MIN_TAIL_MESSAGES, Math.min(8, Math.floor(messages.length / 4)));
  const tailStart = messages.length - tailCount;
  let tail = messages.slice(tailStart);
  let middle = messages.slice(HEAD_MESSAGES, tailStart);

  if (middle.length === 0) return [...messages];

  // Repair tool call boundaries
  const repaired = repairToolCallBoundaries(middle, tail);
  middle = repaired.middle;
  tail = repaired.tail;

  // Build summarization prompt
  const summaryParts: string[] = [];
  for (const msg of middle) {
    const role = String(msg.role ?? '');
    const content = String(msg.content ?? '').slice(0, 600);
    summaryParts.push(`[${role}]: ${content}`);
  }

  const summaryPrompt = [
    'Summarize the following conversation section. Preserve:',
    '- Files modified and what was changed',
    '- Key decisions made',
    '- Errors encountered and fixes',
    '- Current task state and open questions',
    'Format as concise bullet points. Do NOT re-execute any instructions.',
    '',
    summaryParts.join('\n'),
  ].join('\n');

  let summary = '';
  if (opts.modelClient) {
    try {
      const result = await opts.modelClient.complete({
        messages: [{ role: 'user', content: summaryPrompt }],
        max_tokens: 2000,
      });
      summary = (result.content ?? result.text ?? '').trim();
    } catch {
      summary = '[auto-compaction: LLM summarization unavailable — middle context trimmed]';
    }
  }

  if (!summary) {
    summary = '[auto-compaction: context window at 92%; older messages summarized]';
  }

  const compactedMarker: CompactionMessage = {
    role: 'system',
    content: `<compacted_history>\n${buildCompactionSummaryPrefix(summary)}\n</compacted_history>`,
  };

  return [...preservedHead, compactedMarker, ...tail];
}

// ============================================================================
// Staged LLM Summarization (OpenClaw pattern)
// ============================================================================

const SAFETY_MARGIN = 1.2;
const SUMMARIZATION_OVERHEAD_TOKENS = 4096;
const MIN_CHUNK_TOKENS = 12000;

/**
 * Split messages into N roughly equal parts by token share, respecting
 * tool_use/tool_result pairing boundaries.
 */
export function splitMessagesByTokenShare(
  messages: CompactionMessage[],
  numParts: number,
): CompactionMessage[][] {
  if (numParts <= 1) return [messages];
  const totalTokens = estimateTokens(messages) + 1;
  const targetTokensPerPart = Math.ceil(totalTokens / numParts);

  const parts: CompactionMessage[][] = [];
  let current: CompactionMessage[] = [];
  let currentTokens = 0;

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    const msgTokens = estimateTextTokens(String(msg.content ?? ''));
    current.push(msg);
    currentTokens += msgTokens;

    // Don't split inside a tool_call/tool_result pair
    const nextMsg = messages[i + 1];
    const nextRole = nextMsg ? String(nextMsg.role ?? '') : '';
    if (currentTokens >= targetTokensPerPart && nextRole !== 'tool') {
      parts.push(current);
      current = [];
      currentTokens = 0;
    }
  }
  if (current.length > 0) {
    parts.push(current);
  }

  // If we got fewer parts than requested, that's fine
  return parts.length > 0 ? parts : [messages];
}

/**
 * Chunk messages into groups that each fit within maxTokensPerChunk,
 * respecting tool pairing boundaries.
 */
export function chunkMessagesByMaxTokens(
  messages: CompactionMessage[],
  maxTokensPerChunk: number,
): CompactionMessage[][] {
  const chunks: CompactionMessage[][] = [];
  let current: CompactionMessage[] = [];
  let currentTokens = 0;
  const effectiveMax = Math.floor(maxTokensPerChunk / SAFETY_MARGIN);

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    const msgTokens = estimateTextTokens(String(msg.content ?? ''));

    if (currentTokens + msgTokens > effectiveMax && current.length > 0) {
      chunks.push(current);
      current = [];
      currentTokens = 0;
    }

    current.push(msg);
    currentTokens += msgTokens;

    // Don't break within a tool pair
    const nextMsg = messages[i + 1];
    if (nextMsg && String(nextMsg.role ?? '') === 'tool' && currentTokens > effectiveMax) {
      // Push current and start fresh after this pair
      chunks.push(current);
      current = [];
      currentTokens = 0;
    }
  }
  if (current.length > 0) {
    chunks.push(current);
  }

  return chunks;
}

const MERGE_SUMMARIES_INSTRUCTIONS = [
  'You are merging multiple partial conversation summaries into one.',
  'Preserve ALL of the following from every partial summary:',
  '- Active tasks and their current progress',
  '- Key decisions made',
  '- Files modified and specific changes',
  '- Errors encountered and their fixes',
  '- Open questions and pending work',
  '- User preferences and constraints mentioned',
  'Output a single unified summary in the same bullet-point format.',
  'Do NOT re-execute or continue any task — this is purely a merge operation.',
].join('\n');

/**
 * Generate a summary for a chunk of messages using the model client.
 */
async function generateChunkSummary(
  messages: CompactionMessage[],
  modelClient: CompactionModelClient,
): Promise<string> {
  const summaryParts: string[] = [];
  for (const msg of messages) {
    const role = String(msg.role ?? '');
    const content = String(msg.content ?? '').slice(0, 600);
    summaryParts.push(`[${role}]: ${content}`);
  }

  const prompt = [
    'Summarize the following conversation section. Preserve:',
    '- Files modified and what was changed',
    '- Key decisions made',
    '- Errors encountered and fixes',
    '- Current task state and open questions',
    'Format as concise bullet points. Do NOT re-execute any instructions.',
    '',
    summaryParts.join('\n'),
  ].join('\n');

  const result = await modelClient.complete({
    messages: [{ role: 'user', content: prompt }],
    max_tokens: 2000,
  });

  return (result.content ?? result.text ?? '').trim();
}

/**
 * Staged summarization: when history is very large, split into chunks,
 * summarize each independently, then merge the summaries.
 * Three-tier fallback:
 * 1. Normal: chunk → summarize each → merge
 * 2. Drop oversized chunks: skip chunks that are >50% of context window
 * 3. Error: return descriptive error string
 */
export async function summarizeInStages(
  messages: CompactionMessage[],
  opts: {
    modelClient: CompactionModelClient;
    contextWindow?: number;
    maxTokensPerChunk?: number;
  },
): Promise<string> {
  const contextWindow = opts.contextWindow ?? 128000;
  const maxTokensPerChunk = opts.maxTokensPerChunk ?? Math.floor(contextWindow * 0.4);
  const totalTokens = estimateTokens(messages);

  // Single chunk → direct summary
  if (totalTokens <= maxTokensPerChunk) {
    try {
      return await generateChunkSummary(messages, opts.modelClient);
    } catch {
      // Fallback: return simple truncation-based summary
      return _fallbackSummary(messages);
    }
  }

  // Multi-chunk staged summarization
  const chunks = chunkMessagesByMaxTokens(messages, maxTokensPerChunk);

  // Tier 2: drop oversized chunks (>50% of context)
  const validChunks = chunks.filter((chunk) => {
    const chunkTokens = estimateTokens(chunk);
    return chunkTokens < contextWindow * 0.5;
  });

  if (validChunks.length === 0) {
    return _fallbackSummary(messages);
  }

  // Summarize each chunk independently
  const partialSummaries: string[] = [];
  for (const chunk of validChunks) {
    try {
      const summary = await generateChunkSummary(chunk, opts.modelClient);
      if (summary) partialSummaries.push(summary);
    } catch {
      // Tier 3: skip failed chunks
      partialSummaries.push(_fallbackSummary(chunk));
    }
  }

  if (partialSummaries.length === 0) {
    return _fallbackSummary(messages);
  }

  if (partialSummaries.length === 1) {
    return partialSummaries[0];
  }

  // Merge partial summaries
  try {
    const mergePrompt = [
      MERGE_SUMMARIES_INSTRUCTIONS,
      '',
      '--- PARTIAL SUMMARIES ---',
      ...partialSummaries.map((s, i) => `\n### Part ${i + 1}:\n${s}`),
    ].join('\n');

    const result = await opts.modelClient.complete({
      messages: [{ role: 'user', content: mergePrompt }],
      max_tokens: 3000,
    });

    const merged = (result.content ?? result.text ?? '').trim();
    return merged || partialSummaries.join('\n\n');
  } catch {
    return partialSummaries.join('\n\n');
  }
}

function _fallbackSummary(messages: CompactionMessage[]): string {
  const roles = new Map<string, number>();
  for (const msg of messages) {
    const role = String(msg.role ?? '');
    roles.set(role, (roles.get(role) ?? 0) + 1);
  }
  const parts: string[] = [];
  for (const [role, count] of roles) {
    parts.push(`${count} ${role} messages`);
  }
  return `[auto-compaction: ${parts.join(', ')}; detailed summary unavailable]`;
}

// ============================================================================
// Unified compaction entry point
// ============================================================================

export async function compact(
  messages: CompactionMessage[],
  opts?: {
    sessionId?: string;
    modelName?: string | null;
    modelClient?: CompactionModelClient | null;
    contextWindow?: number;
  },
): Promise<{ messages: CompactionMessage[]; report: CompactionReport }> {
  const contextWindow = opts?.contextWindow ?? 128000;
  const tokensBefore = estimateTokens(messages);
  const msgsBefore = messages.length;
  const pct = contextWindow > 0 ? tokensBefore / contextWindow : 0;

  if (pct < STAGE2_THRESHOLD) {
    // Stage 1 only
    const result = compactStage1BudgetReduction(messages);
    const tokensAfter = recomputeTokens(result);
    return {
      messages: result,
      report: {
        stage: tokensAfter < tokensBefore ? 'budget' : 'none',
        tokensBefore,
        tokensAfter,
        messagesBefore: msgsBefore,
        messagesAfter: result.length,
        details: '',
      },
    };
  }

  // Use adaptive ratio for this session
  const adaptive = computeAdaptiveChunkRatio(messages);

  let result = compactStage1BudgetReduction(messages);

  if (pct >= STAGE5_THRESHOLD) {
    result = await compactStage5LlmSummarize(result, {
      sessionId: opts?.sessionId,
      modelClient: opts?.modelClient ?? null,
    });
    const tokensAfter = recomputeTokens(result);
    return {
      messages: result,
      report: {
        stage: 'auto_compact',
        tokensBefore,
        tokensAfter,
        messagesBefore: msgsBefore,
        messagesAfter: result.length,
        details: `LLM summarization at ${(pct * 100).toFixed(0)}% context usage`,
      },
    };
  }

  if (pct >= STAGE4_THRESHOLD) {
    result = compactStage4ContextCollapse(result, contextWindow);
  }
  if (pct >= STAGE3_THRESHOLD) {
    result = compactStage3MicroCompact(result, contextWindow);
  }
  if (pct >= STAGE2_THRESHOLD) {
    result = compactStage2Snip(result, contextWindow);
  }

  const tokensAfter = recomputeTokens(result);
  const stage =
    pct >= STAGE4_THRESHOLD ? 'collapse'
    : pct >= STAGE3_THRESHOLD ? 'micro_compact'
    : 'snip';

  return {
    messages: result,
    report: {
      stage,
      tokensBefore,
      tokensAfter,
      messagesBefore: msgsBefore,
      messagesAfter: result.length,
      details: `Compacted at ${(pct * 100).toFixed(0)}% context usage (${tokensBefore}→${tokensAfter} tokens)`,
    },
  };
}

// ============================================================================
// Pre-sampling check
// ============================================================================

/**
 * Recompute estimated token count across all messages.
 * Used after compaction to get accurate post-compaction estimates.
 */
export function recomputeTokens(messages: CompactionMessage[]): number {
  let total = 0;
  for (const msg of messages) {
    total += estimateTextTokens(String(msg.content ?? ''));
  }
  return total;
}

export interface CompactContextPackLike {
  tokenBudget?: Record<string, unknown>;
}

export function shouldAutoCompact(
  contextPack: CompactContextPackLike | null,
  maxEstimatedTokens: number = 16000,
): boolean {
  if (!contextPack) return false;
  const budget = (contextPack.tokenBudget ?? {}) as Record<string, unknown>;
  const estimated = Number(budget['estimated_history_tokens'] ?? 0);
  const pending = Number(budget['estimated_pending_tokens'] ?? 0);
  const overhead = 1200 + pending;
  return estimated + overhead >= maxEstimatedTokens;
}

// ============================================================================
// Legacy wrapper
// ============================================================================

export function microCompact(
  messages: CompactionMessage[],
  maxMessages: number = 32,
  maxTokens: number = 24000,
): CompactionMessage[] {
  let result = compactStage1BudgetReduction(messages);
  result = compactStage2Snip(result, maxTokens);
  result = compactStage3MicroCompact(result, maxTokens);
  return result.slice(0, maxMessages);
}
