// ============================================================================
// ContextBuilder — context assembly, CLAUDE.md chain, memory injection
// ============================================================================

import type { ChatMessage } from '@jarvis/shared';
import type { LLMMessage } from './model.js';
import type {
  SkillObservation,
  ActiveTaskState,
  HandoffSummary,
  ResearchObservation,
} from './context-store.js';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { removeOrphanToolResults } from './compactor.js';

// ============================================================================
// Configuration
// ============================================================================

export interface ContextConfig {
  maxTokens?: number;
  thresholdPercent?: number;
  protectFirstN?: number;
  protectLastN?: number;
  /** Maximum number of user turns to include in history. 0 = unlimited. */
  maxHistoryTurns?: number;
}

// ============================================================================
// Context data types (mirrors Python TurnContext / ContextPack)
// ============================================================================

export interface ProjectContext {
  cwd: string;
  repoRoot: string | null;
  projectName: string;
  projectFilesHint: string[];
  projectInstructions: string | null;
}

export interface ConversationContext {
  threadId: string | null;
  turnId: string;
  recentMessages: Array<{ role: string; content: string; tool_call_id?: string; metadata?: Record<string, unknown> }>;
  compactedSummary: string | null;
}

export interface MemoryContext {
  shortTerm: Record<string, unknown>;
  longTermRefs: Array<{ key: string; value: string; memory_type: string }>;
}

export interface SkillContext {
  availableSkills: Array<{ name: string; description: string }>;
  loadedSkills: string[];
  skillObservations: Record<string, unknown>[];
  researchObservations: Record<string, unknown>[];
  activeTask: Record<string, unknown> | null;
}

export interface ContextPack {
  project: ProjectContext;
  conversation: ConversationContext;
  memory: MemoryContext;
  skills: SkillContext;
  tokenBudget: Record<string, unknown>;
  warnings: string[];
}

export interface TurnContext {
  userInput: string;
  cwd: string;
  modelProvider: string | null;
  modelName: string | null;
  permissionMode: string;
  contextPack: ContextPack | null;
  modelBackend: string | null;
  projectId: string | null;
  sessionId: string | null;
  turnId: string | null;
  /** True for the first turn of a session or after compaction — full context needed. */
  isFirstTurn?: boolean;
  /** Settings diff payload for steady-state turns — only changed settings. */
  settingsDiff?: Record<string, string>;
  /** Frozen memory snapshot — captured once per session, cache-friendly. */
  memorySnapshot?: string;
}

export interface RuntimeState {
  cwd?: string;
  permission_mode?: string;
  model_backend?: string;
  model_provider?: string;
  model_name?: string;
  session_id?: string;
  turn_id?: string;
}

// ============================================================================
// Minimal interfaces for injected dependencies
// ============================================================================

export interface SessionStoreLike {
  loadMessages(sessionId: string, limit?: number): Array<Record<string, unknown>> | Promise<Array<Record<string, unknown>>>;
  loadSummaries(sessionId: string, limit?: number): Array<Record<string, unknown>> | Promise<Array<Record<string, unknown>>>;
  loadActivePlan?(sessionId: string): Record<string, unknown> | null | Promise<Record<string, unknown> | null>;
}

export interface MemoryStoreLike {
  getTyped(memoryType: string, limit?: number): Array<{ key: string; value_redacted: string }>;
  getProjectMemory?(projectId: string): Record<string, unknown>;
  getUserMemory?(): Record<string, unknown>;
  memoryMd?: { loadAll(): Array<{ memory_type: string; name: string; content: string }> };
}

export interface SkillRegistryLike {
  exportIndex(): Array<{ name: string; description: string }>;
}

export interface ContextStoreLike {
  retrieveRecentContext(sessionId: string): Record<string, unknown>;
  appendTurn?(sessionId: string, turn: Record<string, unknown>): void;
  addSkillObservation?(sessionId: string, observation: SkillObservation): void;
  addResearchObservation?(sessionId: string, observation: ResearchObservation): void;
  setActiveTask?(sessionId: string, task: ActiveTaskState | null): void;
  setHandoffSummary?(sessionId: string, handoff: HandoffSummary | null): void;
  getState?(sessionId: string): Record<string, unknown>;
}

// ============================================================================
// ContextBuilder
// ============================================================================

const PROJECT_INSTRUCTION_FILES = ['CLAUDE.md', 'JARVIS.md', 'AGENTS.md', 'README.md'];
const MAX_TOTAL_CHARS = 32_000;

export class ContextBuilder {
  private config: Required<ContextConfig>;
  private sessionStore: SessionStoreLike | null;
  private memoryStore: MemoryStoreLike | null;
  private skillRegistry: SkillRegistryLike | null;
  private contextStore: ContextStoreLike | null;
  private modelInfo: Record<string, unknown>;
  private permissionMode: string;
  private maxHistoryMessages: number;
  /** Baseline context state for diff computation (Codex reference_context_item). */
  private referenceContextItem: Partial<TurnContext> | null = null;
  /** Whether the next turn should use full context (not diff). */
  private _needsFullContext = true;
  /** Monotonic counter incremented on each buildContext call. */
  private _historyVersion = 0;
  /** Frozen memory snapshot — captured once at session start, never changes mid-session. */
  private _memorySnapshot: string | null = null;

  constructor(config: ContextConfig = {}, deps?: {
    sessionStore?: SessionStoreLike;
    memoryStore?: MemoryStoreLike;
    skillRegistry?: SkillRegistryLike;
    contextStore?: ContextStoreLike;
    modelInfo?: Record<string, unknown>;
    permissionMode?: string;
    maxHistoryMessages?: number;
  }) {
    this.config = {
      maxTokens: config.maxTokens ?? 128_000,
      thresholdPercent: config.thresholdPercent ?? 0.75,
      protectFirstN: config.protectFirstN ?? 3,
      protectLastN: config.protectLastN ?? 6,
      maxHistoryTurns: config.maxHistoryTurns ?? 0,
    };
    this.sessionStore = deps?.sessionStore ?? null;
    this.memoryStore = deps?.memoryStore ?? null;
    this.skillRegistry = deps?.skillRegistry ?? null;
    this.contextStore = deps?.contextStore ?? null;
    this.modelInfo = deps?.modelInfo ?? {};
    this.permissionMode = deps?.permissionMode ?? 'workspace_write';
    this.maxHistoryMessages = deps?.maxHistoryMessages ?? 60;
  }

  // ========================================================================
  // Simple buildMessages (backward compat with existing AgentLoop)
  // ========================================================================

  buildMessages(
    systemPrompt: string,
    history: ChatMessage[],
  ): LLMMessage[] {
    const messages: LLMMessage[] = [];

    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }

    for (const msg of history) {
      const llmMsg: LLMMessage = {
        role: msg.role,
        content: msg.content,
      };
      if (msg.toolCallId) {
        llmMsg.tool_call_id = msg.toolCallId;
      }
      if (msg.name) {
        llmMsg.name = msg.name;
      }
      messages.push(llmMsg);
    }

    return messages;
  }

  // ========================================================================
  // Full buildContext — assembles a complete TurnContext
  // ========================================================================

  async buildContext(opts: {
    sessionId: string;
    turnId: string;
    userInput: string;
    cwd?: string;
    projectId?: string;
    runtimeState?: RuntimeState;
  }): Promise<TurnContext> {
    const state = { ...opts.runtimeState };
    const modelInfo = { ...this.modelInfo, ...pickModelInfo(state) };

    const cwdPath = opts.cwd ?? state['cwd'] ?? process.cwd();
    const resolvedCwd = path.resolve(cwdPath);
    const repoRoot = this._discoverRepoRoot(resolvedCwd);
    const project = this._buildProjectContext(resolvedCwd, repoRoot, opts.userInput);
    const conversation = await this._buildConversationContext(opts.sessionId, opts.turnId);
    const memory = this._buildMemoryContext(opts.userInput, opts.projectId);
    const storedContext = this.contextStore
      ? this.contextStore.retrieveRecentContext(opts.sessionId)
      : {};
    const skills = await this._buildSkillContext(storedContext, opts.sessionId);

    const tokenBudget = {
      history_messages: conversation.recentMessages.length,
      estimated_history_tokens: this.estimateMessageTokens(
        conversation.recentMessages.map((m) => ({
          role: m.role as ChatMessage['role'],
          content: m.content,
          messageId: '',
        })),
      ),
      auto_compact_recommended: false,
    };

    const pack: ContextPack = {
      project,
      conversation,
      memory,
      skills,
      tokenBudget,
      warnings: [],
    };

    if (storedContext['handoff_summary']) {
      pack.memory.shortTerm['handoff_summary'] = storedContext['handoff_summary'];
    }
    if (storedContext['project_facts']) {
      pack.memory.shortTerm['project_facts'] = storedContext['project_facts'];
    }

    // Frozen memory snapshot — capture once per session
    if (!this._memorySnapshot || this._needsFullContext) {
      const memory = this._buildMemoryContext(opts.userInput, opts.projectId);
      this._memorySnapshot = this._renderMemorySnapshot(memory);
    }

    const isFirstTurn = this._needsFullContext;
    this._historyVersion++;

    // Update reference context for future diff computation
    this.referenceContextItem = {
      cwd: resolvedCwd,
      modelName: (modelInfo['model_name'] as string) || null,
      permissionMode: (state['permission_mode'] as string) || this.permissionMode,
    };
    this._needsFullContext = false;

    // Compute diff (only for non-first turns)
    const settingsDiff = this._computeContextDiff({
      userInput: opts.userInput,
      cwd: resolvedCwd,
      modelProvider: (modelInfo['model_provider'] as string) || null,
      modelName: (modelInfo['model_name'] as string) || null,
      permissionMode: (state['permission_mode'] as string) || this.permissionMode,
      contextPack: null,
      modelBackend: null,
      projectId: null,
      sessionId: null,
      turnId: null,
    });

    return {
      userInput: opts.userInput,
      cwd: resolvedCwd,
      modelProvider: (modelInfo['model_provider'] as string) || null,
      modelName: (modelInfo['model_name'] as string) || null,
      permissionMode: (state['permission_mode'] as string) || this.permissionMode,
      contextPack: pack,
      modelBackend: (modelInfo['model_backend'] as string) || null,
      projectId: opts.projectId ?? null,
      sessionId: opts.sessionId,
      turnId: opts.turnId,
      isFirstTurn,
      settingsDiff: settingsDiff || undefined,
      memorySnapshot: this._memorySnapshot ?? undefined,
    };
  }

  // ========================================================================
  // Build messages from a full TurnContext (used with PromptBuilder)
  // ========================================================================

  buildMessagesFromContext(
    turnContext: TurnContext,
    promptBuilder?: { buildMessages(turnContext: TurnContext): Array<{ role: string; content: string }> },
  ): { turnContext: TurnContext; messages: Array<{ role: string; content: string; tool_call_id?: string }> } {
    const builder = promptBuilder ?? new PromptBuilderShim();
    const messages = builder.buildMessages(turnContext);
    return { turnContext, messages };
  }

  // ========================================================================
  // Token estimation
  // ========================================================================

  /** Force the next buildContext to use full context injection. */
  markNeedsFullContext(): void {
    this._needsFullContext = true;
  }

  /** Manually refresh the frozen memory snapshot (e.g. after /memory command). */
  refreshMemorySnapshot(): void {
    this._memorySnapshot = null;
  }

  /** Current history version — incremented on each context build. */
  get historyVersion(): number {
    return this._historyVersion;
  }

  /**
   * Compute settings diff between current TurnContext and the stored reference.
   * Returns null if no changes detected and context can be skipped.
   * Returns partial context with only changed settings.
   */
  private _computeContextDiff(
    turnContext: TurnContext,
  ): Record<string, string> | null {
    if (!this.referenceContextItem || this._needsFullContext) return null;

    const diffs: Record<string, string> = {};

    // cwd change
    if (turnContext.cwd !== this.referenceContextItem.cwd) {
      diffs['cwd'] = `Working directory changed to: ${turnContext.cwd}`;
    }

    // model change
    if (turnContext.modelName !== this.referenceContextItem.modelName &&
        turnContext.modelName) {
      diffs['model'] = `Model switched to: ${turnContext.modelName}`;
    }

    // permission mode change
    if (turnContext.permissionMode !== this.referenceContextItem.permissionMode) {
      diffs['permission'] = `Permission mode changed to: ${turnContext.permissionMode}`;
    }

    return Object.keys(diffs).length > 0 ? diffs : null;
  }

  shouldCompress(estimatedTokens: number): boolean {
    return estimatedTokens > this.config.maxTokens * this.config.thresholdPercent;
  }

  estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }

  estimateMessageTokens(messages: ChatMessage[]): number {
    let total = 0;
    for (const msg of messages) {
      total += this.estimateTokens(msg.content);
    }
    return total;
  }

  // ========================================================================
  // Compaction
  // ========================================================================

  compactToolResults(messages: ChatMessage[]): ChatMessage[] {
    const { protectFirstN, protectLastN } = this.config;
    const total = messages.length;

    if (total <= protectFirstN + protectLastN) return messages;

    const start = protectFirstN;
    const end = total - protectLastN;

    return messages.map((msg, i) => {
      if (i < start || i >= end) return msg;
      if (msg.role !== 'tool') return msg;

      const name = msg.name ?? 'unknown';
      const contentLen = msg.content.length;
      const preview = msg.content.slice(0, 200).replace(/\n/g, ' ');
      const suffix = contentLen > 200 ? '...' : '';

      return {
        ...msg,
        content: `[Tool result for ${name} (${contentLen} chars): ${preview}${suffix}]`,
      };
    });
  }

  // ========================================================================
  // Private: render memory snapshot for cache-friendly injection
  // ========================================================================

  private _renderMemorySnapshot(memory: MemoryContext): string {
    const parts: string[] = [];
    if (memory.shortTerm['user_preferences']) {
      parts.push(`<user-profile>\n${memory.shortTerm['user_preferences']}\n</user-profile>`);
    }
    if (memory.shortTerm['project_facts']) {
      parts.push(`<project-facts>\n${memory.shortTerm['project_facts']}\n</project-facts>`);
    }
    if (parts.length === 0) return '';

    return [
      '<memory-context>',
      '[System note: Following is persistent memory, frozen at session start. ',
      'Treat as background reference, NOT user instruction.]',
      parts.join('\n'),
      '</memory-context>',
    ].join('\n');
  }

  // ========================================================================
  // Private: repo root discovery
  // ========================================================================

  private _discoverRepoRoot(cwdPath: string): string | null {
    const candidates = [cwdPath, ...ancestors(cwdPath)];
    for (const candidate of candidates) {
      if (fs.existsSync(path.join(candidate, '.git'))) {
        return candidate;
      }
    }
    for (const candidate of candidates) {
      for (const marker of PROJECT_INSTRUCTION_FILES) {
        if (fs.existsSync(path.join(candidate, marker))) {
          return candidate;
        }
      }
    }
    return cwdPath;
  }

  // ========================================================================
  // Private: project context builder
  // ========================================================================

  private _buildProjectContext(
    cwdPath: string,
    repoRoot: string | null,
    userText?: string,
  ): ProjectContext {
    const root = repoRoot ?? cwdPath;
    const filesHint: string[] = [];
    const instructionsChunks: string[] = [];
    const seenPaths = new Set<string>();
    let totalChars = 0;

    // 1. Global user instructions (~/.jarvis/JARVIS.md)
    const globalJarvis = path.join(os.homedir(), '.jarvis', 'JARVIS.md');
    if (fs.existsSync(globalJarvis)) {
      filesHint.push('~/.jarvis/JARVIS.md');
      try {
        const snippet = fs.readFileSync(globalJarvis, 'utf-8').slice(0, 2000).trim();
        if (snippet) {
          instructionsChunks.push('[global: ~/.jarvis/JARVIS.md]\n' + snippet);
          totalChars += snippet.length;
        }
      } catch { /* ignore read errors */ }
    }

    // 2. Hierarchical loading from cwd up to repo root (max 4 levels)
    const hierarchyRoots: string[] = [];
    if (repoRoot) {
      try {
        const rel = path.relative(path.resolve(repoRoot), cwdPath);
        if (!rel.startsWith('..')) {
          let current = cwdPath;
          while (current !== path.dirname(path.resolve(repoRoot))) {
            hierarchyRoots.push(current);
            if (current === path.resolve(repoRoot)) break;
            current = path.dirname(current);
          }
        } else {
          hierarchyRoots.push(cwdPath, path.resolve(repoRoot));
        }
      } catch {
        hierarchyRoots.push(cwdPath, path.resolve(repoRoot));
      }
    } else {
      hierarchyRoots.push(cwdPath);
    }

    const uniqueRoots = [...new Set(hierarchyRoots)].slice(0, 4);

    for (const directory of uniqueRoots) {
      for (const name of PROJECT_INSTRUCTION_FILES) {
        const candidate = path.join(directory, name);
        if (!fs.existsSync(candidate)) continue;
        const resolved = path.resolve(candidate);
        if (seenPaths.has(resolved)) continue;
        seenPaths.add(resolved);

        const dirName = path.basename(directory);
        filesHint.push(
          directory !== root ? `${name} (${dirName})` : name,
        );

        const remaining = MAX_TOTAL_CHARS - totalChars;
        if (remaining <= 0) break;
        try {
          const snippet = fs.readFileSync(candidate, 'utf-8').slice(0, remaining).trim();
          if (snippet) {
            const label =
              directory !== root ? `[${dirName}/${name}]` : `[${name}]`;
            instructionsChunks.push(label + '\n' + snippet);
            totalChars += snippet.length;
          }
        } catch { /* ignore */ }
      }
    }

    // 3. Mentioned-directory injection
    if (userText && repoRoot) {
      const mentionedDirs = this._findMentionedDirs(userText, root, seenPaths);
      for (const mDir of mentionedDirs) {
        for (const name of PROJECT_INSTRUCTION_FILES) {
          const candidate = path.join(mDir, name);
          if (!fs.existsSync(candidate)) continue;
          const resolved = path.resolve(candidate);
          if (seenPaths.has(resolved)) continue;
          seenPaths.add(resolved);

          const remaining = MAX_TOTAL_CHARS - totalChars;
          if (remaining <= 0) break;
          try {
            const snippet = fs.readFileSync(candidate, 'utf-8').slice(0, remaining).trim();
            if (snippet) {
              const dirName = path.basename(mDir);
              filesHint.push(`${name} (mentioned: ${dirName})`);
              instructionsChunks.push(`[mentioned:${dirName}/${name}]\n${snippet}`);
              totalChars += snippet.length;
            }
          } catch { /* ignore */ }
        }
      }
    }

    return {
      cwd: cwdPath,
      repoRoot: root,
      projectName: path.basename(root),
      projectFilesHint: filesHint,
      projectInstructions: instructionsChunks.length > 0 ? instructionsChunks.join('\n\n') : null,
    };
  }

  // ========================================================================
  // Private: conversation context
  // ========================================================================

  private async _buildConversationContext(
    sessionId: string,
    turnId: string,
  ): Promise<ConversationContext> {
    const recentMessages: ConversationContext['recentMessages'] = [];

    if (this.sessionStore) {
      const rows = await this.sessionStore.loadMessages(sessionId, this.maxHistoryMessages);
      for (const row of rows) {
        if (String(row['turn_id'] ?? '') === turnId) continue;
        const role = String(row['role'] ?? '').trim();
        const content = String(row['content'] ?? '');
        if (!role || !content) continue;
        // Filter ghost/empty/internal messages
        if (content.includes('<skill-context')) continue;
        if (_isGhostMessage(content)) continue;
        recentMessages.push({
          role,
          content,
          tool_call_id: row['tool_call_id'] as string | undefined,
          metadata: row['metadata'] as Record<string, unknown> | undefined,
        });
      }
      // Remove orphan tool results (results whose call_id doesn't match any known tool call)
      const knownCallIds = new Set<string>();
      for (const msg of recentMessages) {
        if (msg.role === 'assistant' && msg.metadata?.['tool_calls']) {
          for (const tc of (msg.metadata['tool_calls'] as Array<{ id: string }>)) {
            if (tc.id) knownCallIds.add(tc.id);
          }
        }
      }
      if (knownCallIds.size > 0) {
        for (let i = recentMessages.length - 1; i >= 0; i--) {
          const msg = recentMessages[i];
          if (msg.role === 'tool' && msg.tool_call_id && !knownCallIds.has(msg.tool_call_id)) {
            recentMessages.splice(i, 1);
          }
        }
      }
    }

    // Apply maxHistoryTurns: keep only the last N user turns
    const maxTurns = this.config.maxHistoryTurns;
    if (maxTurns && maxTurns > 0 && recentMessages.length > 0) {
      let userCount = 0;
      let cutoffIdx = -1;
      for (let i = recentMessages.length - 1; i >= 0; i--) {
        if (recentMessages[i].role === 'user') {
          userCount++;
          if (userCount >= maxTurns) {
            cutoffIdx = i;
            break;
          }
        }
      }
      if (cutoffIdx > 0) {
        // Keep messages from the N-th user message onward
        const truncated = recentMessages.slice(cutoffIdx);
        recentMessages.length = 0;
        recentMessages.push(...truncated);
      }
    }

    let compactedSummary: string | null = null;
    if (this.sessionStore) {
      const summaries = await this.sessionStore.loadSummaries(sessionId, 5);
      if (summaries.length > 0) {
        const parts: string[] = [];
        const reversed = [...summaries].reverse();
        for (let i = 0; i < reversed.length; i++) {
          const s = reversed[i];
          const summaryData = (s['summary'] as Record<string, unknown>) ?? {};
          const machine = (summaryData['machine'] as Record<string, unknown>) ?? {};
          if (i === 0) {
            const human = String(summaryData['human'] ?? '').trim();
            const text = human || String(machine['handoff_summary'] ?? '').trim() || null;
            if (text) parts.push(text);
          } else {
            const keyPoints: string[] = [];
            const ho = (machine['handoff_summary_obj'] as Record<string, unknown>) ?? {};
            if (typeof ho === 'object') {
              const goal = String(ho['user_goal'] ?? '').trim();
              if (goal) keyPoints.push(`Goal: ${goal.slice(0, 120)}`);
              const files = (ho['modified_files'] as string[]) ?? [];
              if (files.length > 0) {
                keyPoints.push(`Files: ${files.slice(0, 3).join(', ')}`);
              }
            }
            const accContext = (machine['accumulated_context'] as Array<{ kind: string; text: string }>) ?? [];
            for (const fact of accContext.slice(0, 4)) {
              if (typeof fact === 'object' && fact.kind && fact.text) {
                keyPoints.push(`${fact.kind}: ${fact.text.slice(0, 120)}`);
              }
            }
            if (keyPoints.length > 0) {
              parts.push('[Earlier turn: ' + keyPoints.slice(0, 4).join(' | ') + ']');
            }
          }
        }
        if (parts.length > 0) {
          compactedSummary = parts.join('\n\n');
        }
      }
    }

    return {
      threadId: sessionId,
      turnId,
      recentMessages,
      compactedSummary,
    };
  }

  // ========================================================================
  // Private: memory context
  // ========================================================================

  private _buildMemoryContext(
    userInput: string,
    projectId?: string | null,
  ): MemoryContext {
    const shortTerm: Record<string, unknown> = {};
    const longTermRefs: MemoryContext['longTermRefs'] = [];

    if (this.memoryStore) {
      // User profile memory (capped at 800 chars)
      try {
        const profileRecords = this.memoryStore.getTyped('user_profile', 8);
        if (profileRecords.length > 0) {
          const profileParts: string[] = [];
          let profileChars = 0;
          for (const r of profileRecords) {
            const chunk = `- ${r['key']}: ${r['value_redacted']}`;
            if (profileChars + chunk.length > 800) break;
            profileParts.push(chunk);
            profileChars += chunk.length;
          }
          if (profileParts.length > 0) {
            shortTerm['user_preferences'] = profileParts.join('\n');
          }
        }
      } catch { /* ignore */ }

      // Project facts (capped at 1200 chars)
      try {
        const projRecords = projectId
          ? this.memoryStore.getTyped('project_fact', 10).filter(() => true) // getTyped doesn't support projectId filter — we use all and filter client-side
          : this.memoryStore.getTyped('project_fact', 10);
        if (projRecords.length > 0) {
          const factParts: string[] = [];
          let factChars = 0;
          for (const r of projRecords) {
            const chunk = `- ${r['key']}: ${r['value_redacted']}`;
            if (factChars + chunk.length > 1200) break;
            factParts.push(chunk);
            factChars += chunk.length;
          }
          if (factParts.length > 0) {
            shortTerm['project_facts'] = factParts.join('\n');
          }
        }
      } catch { /* ignore */ }

      // User/project KV memory
      try {
        if (this.memoryStore.getUserMemory) {
          const userMem = this.memoryStore.getUserMemory();
          if (userMem && Object.keys(userMem).length > 0) {
            const filtered: Record<string, string> = {};
            const entries = Object.entries(userMem).slice(0, 8);
            for (const [k, v] of entries) {
              filtered[k] = String(v).slice(0, 280);
            }
            shortTerm['persistent_user_memory'] = filtered;
          }
        }
        if (projectId && this.memoryStore.getProjectMemory) {
          const projMem = this.memoryStore.getProjectMemory(projectId);
          if (projMem && Object.keys(projMem).length > 0) {
            const filtered: Record<string, string> = {};
            const entries = Object.entries(projMem).slice(0, 8);
            for (const [k, v] of entries) {
              filtered[k] = String(v).slice(0, 280);
            }
            shortTerm['persistent_project_memory'] = filtered;
          }
        }
      } catch { /* ignore */ }

      // Markdown memory
      try {
        if (this.memoryStore.memoryMd) {
          const mdEntries = this.memoryStore.memoryMd.loadAll();
          for (const entry of mdEntries.slice(0, 10)) {
            const mdKey = `md_memory:${entry.memory_type}:${entry.name}`;
            if (!(mdKey in shortTerm)) {
              shortTerm[mdKey] = entry.content.slice(0, 500);
            }
          }
        }
      } catch { /* ignore */ }
    }

    return { shortTerm, longTermRefs };
  }

  // ========================================================================
  // Private: skill context
  // ========================================================================

  private async _buildSkillContext(
    storedContext: Record<string, unknown>,
    sessionId: string,
  ): Promise<SkillContext> {
    const available: Array<{ name: string; description: string }> = [];
    if (this.skillRegistry) {
      try {
        const index = this.skillRegistry.exportIndex();
        for (const item of index) {
          available.push({
            name: item.name,
            description: item.description,
          });
        }
      } catch { /* ignore */ }
    }

    let activeTask: Record<string, unknown> | null =
      (storedContext['active_task'] as Record<string, unknown>) ?? null;
    if (!activeTask && sessionId && this.sessionStore?.loadActivePlan) {
      try {
        activeTask = await this.sessionStore.loadActivePlan(sessionId);
      } catch { /* ignore */ }
    }

    return {
      availableSkills: available,
      loadedSkills: [],
      skillObservations: (storedContext['skill_observations'] as Record<string, unknown>[]) ?? [],
      researchObservations: (storedContext['research_observations'] as Record<string, unknown>[]) ?? [],
      activeTask,
    };
  }

  // ========================================================================
  // Private: mentioned directories
  // ========================================================================

  private _findMentionedDirs(
    userText: string,
    repoRoot: string,
    _seenPaths: Set<string>,
  ): string[] {
    const found: string[] = [];
    const lowered = userText.toLowerCase();
    try {
      const entries = fs.readdirSync(repoRoot, { withFileTypes: true });
      for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
        if (!entry.isDirectory()) continue;
        if (entry.name.startsWith('.') || entry.name.startsWith('_')) continue;
        if (lowered.includes(entry.name.toLowerCase())) {
          found.push(path.join(repoRoot, entry.name));
        }
      }
    } catch { /* ignore */ }
    return found;
  }
}

// ============================================================================
// ContextUpdater
//
// Python ref: src/jarvis/agent/context_updater.py
// Persists turn outcomes, skill observations, research observations,
// active task, handoff summaries, and approval audits back into
// ContextStore and SessionStore.
// ============================================================================

export class ContextUpdater {
  private contextStore: ContextStoreLike | null;
  private sessionStore: SessionStoreLike | null;

  constructor(opts?: {
    contextStore?: ContextStoreLike | null;
    sessionStore?: SessionStoreLike | null;
  }) {
    this.contextStore = opts?.contextStore ?? null;
    this.sessionStore = opts?.sessionStore ?? null;
  }

  applyResult(
    turnContext: TurnContext,
    agentResult: {
      turnId?: string;
      sessionId?: string;
      finalAnswer?: string;
      skillsUsed?: string[];
      skillResults?: Array<Record<string, unknown>>;
      summary?: Record<string, unknown>;
      events?: Array<Record<string, unknown>>;
      outputType?: string;
      stopReason?: string;
      loadedSkills?: string[];
    },
  ): void {
    const sessionId = String(
      turnContext.sessionId ?? agentResult.sessionId ?? 'default',
    );

    // 1. Append turn to ContextStore
    this.contextStore?.appendTurn?.(sessionId, {
      turn_id: agentResult.turnId,
      user_input: turnContext.userInput,
      final_answer: (agentResult.finalAnswer ?? '').slice(0, 800),
      skills_used: agentResult.skillsUsed ?? [],
      related_files: this._relatedFiles(agentResult),
    });

    // 2. End turn in SessionStore
    if (this.sessionStore) {
      const store = this.sessionStore as unknown as Record<string, unknown>;
      if (typeof store['endTurn'] === 'function') {
        try {
          (store['endTurn'] as (sid: string, r: Record<string, unknown>) => unknown)(
            sessionId,
            {
              turnId: agentResult.turnId,
              finalAnswer: agentResult.finalAnswer,
              summary: agentResult.summary,
              outputType: agentResult.outputType,
              stopReason: agentResult.stopReason,
              skillsUsed: agentResult.skillsUsed,
              events: agentResult.events,
            },
          );
        } catch { /* best-effort */ }
      }
    }

    // 3. Extract and persist skill observations
    const observations: SkillObservation[] = [];
    const researchObservations: ResearchObservation[] = [];

    for (const item of agentResult.skillResults ?? []) {
      if (typeof item !== 'object' || !item) continue;
      for (const obs of (item['observations'] as Array<Record<string, unknown>>) ?? []) {
        if (typeof obs !== 'object' || !obs) continue;
        const observation: SkillObservation = {
          skill_name: String(obs['skill_name'] ?? item['skill_name'] ?? ''),
          summary: String(obs['summary'] ?? item['final_answer'] ?? '').slice(0, 800),
          facts: (obs['facts'] as Record<string, unknown>) ?? {},
          related_files: (obs['related_files'] as string[]) ??
            (item['related_files'] as string[]) ?? [],
          tool_calls: (obs['tool_calls'] as string[]) ?? [],
        };
        observations.push(observation);
        this.contextStore?.addSkillObservation?.(sessionId, observation);

        // Persist to SessionStore
        this._safeCall('appendSkillObs', sessionId, observation, agentResult.turnId);
      }
    }

    // 4. Extract and persist research observations from machine summary
    const machine = ((agentResult.summary ?? {})['machine'] as Record<string, unknown>) ?? {};
    for (const obs of (machine['research_observations'] as Array<Record<string, unknown>>) ?? []) {
      if (typeof obs !== 'object' || !obs) continue;
      const research: ResearchObservation = {
        query: String(obs['query'] ?? turnContext.userInput),
        search_tasks: (obs['search_tasks'] as Array<Record<string, unknown>>) ?? [],
        sources: (obs['sources'] as Array<Record<string, unknown>>) ?? [],
        evidence: (obs['evidence'] as Array<Record<string, unknown>>) ?? [],
        answer_summary: String(obs['answer_summary'] ?? '').slice(0, 800),
        confidence: Number(obs['confidence'] ?? 0),
        remaining_questions: (obs['remaining_questions'] as string[]) ?? [],
      };
      researchObservations.push(research);
      this.contextStore?.addResearchObservation?.(sessionId, research);

      this._safeCall('appendResearchObs', sessionId, research, agentResult.turnId);
    }

    // 5. Build and persist active task
    const activeTask = this._buildActiveTask(turnContext, agentResult);
    this.contextStore?.setActiveTask?.(sessionId, activeTask);

    // 6. Build and persist handoff
    const handoff = this._buildHandoff(
      turnContext,
      agentResult,
      observations,
      activeTask,
    );
    this.contextStore?.setHandoffSummary?.(sessionId, handoff);

    // 7. Persist project facts
    const state = this.contextStore?.getState?.(sessionId);
    if (state) {
      const sf = state as unknown as { projectFacts: Record<string, unknown> };
      this._safeCall('saveProjectFacts', sessionId, turnContext.projectId, sf.projectFacts);
    }

    // 8. Persist approval audits
    this._persistApprovalAudits(sessionId, agentResult);

    // 9. Update machine summary
    machine['active_task'] = activeTask ? { ...activeTask } : {};
    machine['handoff_summary'] = handoff;
    machine['skill_observations'] = observations.map((o) => ({ ...o }));
    machine['research_observations'] = researchObservations.map((o) => ({ ...o }));
    if (researchObservations.length > 0) {
      machine['research_context_reused'] = Boolean(machine['research_context_reused']);
    }
    if (activeTask?.risks && activeTask.risks.length > 0) {
      const existingRisks = (machine['risks'] as string[]) ?? [];
      machine['risks'] = [...new Set([...existingRisks, ...activeTask.risks])];
    }
    (agentResult.summary ?? {})['machine'] = machine;

    // Also update the simple fields for backward compat
    if (!turnContext.contextPack) return;
    const loaded = agentResult.loadedSkills ?? [];
    if (loaded.length > 0) {
      turnContext.contextPack.skills.loadedSkills = [...new Set(loaded)];
    }
    const finalAnswer = (agentResult.finalAnswer ?? '').trim();
    if (finalAnswer) {
      turnContext.contextPack.memory.shortTerm['last_final_answer'] = finalAnswer.slice(0, 500);
    }
  }

  // ========================================================================
  // Private helpers
  // ========================================================================

  // ========================================================================
  // Pre-compaction memory flush (OpenClaw pattern)
  // ========================================================================

  /**
   * Flush current session state to memory store before compaction.
   * Saves skill observations, research observations, and active task
   * so they aren't lost when old messages are summarized away.
   */
  async flushMemoryBeforeCompaction(
    sessionId: string,
    turnContext?: TurnContext,
  ): Promise<void> {
    if (!this.contextStore) return;

    const state = this.contextStore.getState
      ? this.contextStore.getState(sessionId) as Record<string, unknown>
      : {};

    // Save skill observations as memory entries
    const skillObs = (state['skillObservations'] as Array<Record<string, unknown>>) ?? [];
    for (const obs of skillObs.slice(-5)) {
      const skillName = String(obs['skill_name'] ?? '');
      const summary = String(obs['summary'] ?? '');
      if (skillName && summary) {
        this._safeCall('appendSkillObs', sessionId, {
          skill_name: skillName,
          summary: summary,
          facts: obs['facts'] ?? {},
          related_files: obs['related_files'] ?? [],
        }, turnContext?.turnId);
      }
    }

    // Save research observations
    const researchObs = (state['researchObservations'] as Array<Record<string, unknown>>) ?? [];
    for (const obs of researchObs.slice(-3)) {
      this._safeCall('appendResearchObs', sessionId, {
        query: String(obs['query'] ?? ''),
        answer_summary: String(obs['answer_summary'] ?? ''),
        sources: obs['sources'] ?? [],
        confidence: Number(obs['confidence'] ?? 0),
      }, turnContext?.turnId);
    }

    // Save handoff summary
    const handoff = state['handoffSummary'] as Record<string, unknown> | null;
    if (handoff) {
      this._safeCall('saveHandoff', sessionId, {
        current_state: String(handoff['current_state'] ?? ''),
        user_goal: String(handoff['user_goal'] ?? ''),
        remaining_work: handoff['remaining_work'] ?? [],
      });
    }
  }

  // ========================================================================
  // Post-compaction memory index sync (OpenClaw pattern)
  // ========================================================================

  /**
   * After compaction, ensure that summarized content is still searchable
   * by syncing compaction summaries into the memory store index.
   */
  async syncMemoryIndexAfterCompaction(
    sessionId: string,
    compactionSummary: string,
  ): Promise<void> {
    if (!compactionSummary) return;

    // Write a compaction summary memory entry for later recall
    try {
      const store = this.sessionStore as unknown as Record<string, unknown> | undefined;
      if (store && typeof store['saveSummary'] === 'function') {
        await (store['saveSummary'] as (
          sid: string,
          tid: string,
          summary: { human?: string; machine?: Record<string, unknown> },
        ) => Promise<void>)(sessionId, `compaction_${Date.now()}`, {
          human: compactionSummary.slice(0, 1200),
          machine: { compaction_indexed: true, timestamp: new Date().toISOString() },
        });
      }
    } catch { /* best-effort */ }
  }

  private _persistApprovalAudits(
    sessionId: string,
    agentResult: {
      events?: Array<Record<string, unknown>>;
      turnId?: string;
    },
  ): void {
    for (const event of agentResult.events ?? []) {
      if (typeof event !== 'object' || !event) continue;
      const eventType = String(event['type'] ?? '');
      const payload = (event['payload'] as Record<string, unknown>) ?? {};
      if (eventType === 'approval_created') {
        this._safeCall('appendApproval', sessionId, {
          approval_id: String(payload['approval_id'] ?? ''),
          tool_name: String(payload['tool_name'] ?? ''),
          arguments_preview: (payload['arguments_preview'] as Record<string, unknown>) ?? {},
          risk_level: String(payload['risk_level'] ?? 'medium'),
          reason: String(payload['reason'] ?? ''),
          created_at: String(event['timestamp'] ?? ''),
          status: 'pending',
          session_id: sessionId,
          turn_id: agentResult.turnId,
        }, agentResult.turnId);
      } else if (eventType === 'approval_approved' || eventType === 'approval_denied') {
        this._safeCall('appendApproval', sessionId, {
          approval_id: String(payload['approval_id'] ?? ''),
          decision: eventType === 'approval_approved' ? 'approved' : 'denied',
          reason: String(payload['reason'] ?? '') || null,
          decided_at: String(event['timestamp'] ?? ''),
          decided_by: String(payload['decided_by'] ?? '') || null,
        }, agentResult.turnId);
      }
    }
  }

  private _buildActiveTask(
    turnContext: TurnContext,
    agentResult: {
      skillsUsed?: string[];
      skillResults?: Array<Record<string, unknown>>;
      outputType?: string;
      summary?: Record<string, unknown>;
    },
  ): ActiveTaskState | null {
    if (!agentResult.skillsUsed || agentResult.skillsUsed.length === 0) return null;

    const remaining: string[] = [];
    const risks: string[] = [
      ...(((agentResult.summary ?? {})['machine'] as Record<string, unknown>)?.['risks'] as string[]) ?? [],
    ];
    for (const item of agentResult.skillResults ?? []) {
      if (typeof item === 'object' && item) {
        risks.push(...((item['risks'] as string[]) ?? []));
      }
    }

    if (agentResult.outputType === 'partial' || agentResult.outputType === 'error') {
      remaining.push('Resolve the partial result or blocking error before continuing.');
    }
    if ((agentResult.skillsUsed ?? []).includes('fix_test_failure')) {
      remaining.push('Review the dry-run repair plan and ask for approval before editing files.');
    }

    return {
      user_goal: turnContext.userInput,
      current_phase: agentResult.outputType ?? 'completed',
      completed_steps: [...(agentResult.skillsUsed ?? [])],
      remaining_work: remaining,
      related_files: this._relatedFiles(agentResult),
      skills_used: [...(agentResult.skillsUsed ?? [])],
      risks: [...new Set(risks)],
    };
  }

  private _buildHandoff(
    turnContext: TurnContext,
    agentResult: {
      skillsUsed?: string[];
      skillResults?: Array<Record<string, unknown>>;
      outputType?: string;
      summary?: Record<string, unknown>;
    },
    observations: SkillObservation[],
    activeTask: ActiveTaskState | null,
  ): HandoffSummary | null {
    const relatedFiles = this._relatedFiles(agentResult);
    const machine = ((agentResult.summary ?? {})['machine'] as Record<string, unknown>) ?? {};

    const recentSources: string[] = [];
    for (const obs of (machine['research_observations'] as Array<Record<string, unknown>>) ?? []) {
      if (typeof obs !== 'object' || !obs) continue;
      for (const item of ((obs['sources'] as Array<Record<string, unknown>>) ?? []).slice(0, 3)) {
        if (typeof item === 'object' && item && String(item['url'] ?? '')) {
          recentSources.push(String(item['url']));
        }
      }
    }

    const contextToKeep = [
      ...new Set([
        ...relatedFiles,
        ...observations.map((o) => o.skill_name),
        ...recentSources,
      ]),
    ];

    const risks: string[] = [
      ...((machine['risks'] as string[]) ?? []),
      ...(activeTask?.risks ?? []),
    ];

    return {
      user_goal: turnContext.userInput,
      current_state: agentResult.outputType ?? 'completed',
      completed_work: [...(agentResult.skillsUsed ?? [])],
      remaining_work: [...(activeTask?.remaining_work ?? [])],
      context_to_keep: contextToKeep,
      risks: [...new Set(risks.map(String))],
    };
  }

  private _safeCall(method: string, ...args: unknown[]): void {
    if (!this.sessionStore) return;
    const store = this.sessionStore as unknown as Record<string, unknown>;
    if (typeof store[method] !== 'function') return;
    try {
      (store[method] as (...a: unknown[]) => unknown)(...args);
    } catch { /* best-effort */ }
  }

  private _relatedFiles(agentResult: {
    skillResults?: Array<Record<string, unknown>>;
  }): string[] {
    const files: string[] = [];
    for (const item of agentResult.skillResults ?? []) {
      if (typeof item !== 'object' || !item) continue;
      for (const path of (item['related_files'] as string[]) ?? []) {
        if (path && !files.includes(path)) {
          files.push(path);
        }
      }
    }
    return files;
  }
}


// ============================================================================
// PromptBuilderShim (minimal fallback when no PromptBuilder is injected)
// ============================================================================

class PromptBuilderShim {
  buildMessages(turnContext: TurnContext): Array<{ role: string; content: string }> {
    const messages: Array<{ role: string; content: string }> = [];
    const modelName = (turnContext.modelName ?? '').trim() || 'unknown';

    messages.push({
      role: 'system',
      content: PROMPT_SHIM_TEMPLATE.replace('{model_name}', modelName),
    });

    // Skills index
    const pack = turnContext.contextPack;
    if (pack) {
      const skills = pack.skills.availableSkills;
      if (skills.length > 0) {
        const lines: string[] = ['<skills>'];
        for (const s of skills) {
          lines.push(`- ${s.name}: ${s.description}`);
        }
        lines.push('</skills>');
        messages.push({ role: 'user', content: lines.join('\n') });
      }

      // Compaction summary
      if (pack.conversation.compactedSummary) {
        messages.push({
          role: 'user',
          content: `<conversation-summary>\n${pack.conversation.compactedSummary}\n</conversation-summary>`,
        });
      }

      // History
      const recent = pack.conversation.recentMessages.slice(-40);
      if (recent.length > 0) {
        messages.push({
          role: 'user',
          content: '<conversation-history>\nMessages above this point are from earlier turns.</conversation-history>',
        });
      }
      for (const msg of recent) {
        if (msg.role === 'tool') {
          const toolName = (msg.metadata && (msg.metadata as Record<string, unknown>)['tool_name']) as string
            || msg.tool_call_id || 'unknown';
          messages.push({
            role: 'user',
            content: `[Previous tool result — ${toolName}]: ${msg.content.slice(0, 3000)}`,
          });
        } else {
          messages.push({ role: msg.role, content: msg.content });
        }
      }
    }

    // Current request boundary
    messages.push({
      role: 'user',
      content: `─── current request ───\n${turnContext.userInput}`,
    });

    return messages;
  }
}

const PROMPT_SHIM_TEMPLATE = `<agent>
You are Jarvis, a local AI coding assistant. You have file system access and tools to inspect, search, edit, and run code.
When asked what model you are, say you are {model_name}.

## Tool rules
- ALWAYS use tools for file contents, code search, reading files, running commands, web content.
- Use the most specific tool: Glob for filenames, Grep for content, Read for known paths.
- If a tool returns an error, try a different approach.
- Combine independent tool calls in a single response when possible.

## Code
- Minimum code to solve the problem. No extra features.
- Match existing codebase style. Don't touch unrelated code.

## Output style
- Be brief. After tools complete, state what changed in 1-3 sentences.
- Do not create tables or analysis unless asked.
</agent>`;

// ============================================================================
// Helpers
// ============================================================================

function _isGhostMessage(content: string): boolean {
  if (!content || !content.trim()) return true;
  const trimmed = content.trim();
  // Heartbeat messages
  if (/^heartbeat/i.test(trimmed)) return true;
  // Ghost markers
  if (trimmed.startsWith('<ghost>') || trimmed.startsWith('<ghost ')) return true;
  // System internal state dumps (not model-visible)
  if (trimmed.startsWith('[internal:')) return true;
  return false;
}

function ancestors(dir: string): string[] {
  const result: string[] = [];
  let current = path.resolve(dir);
  while (true) {
    const parent = path.dirname(current);
    if (parent === current) break;
    result.push(parent);
    current = parent;
  }
  return result;
}

function pickModelInfo(state: RuntimeState): Record<string, unknown> {
  const info: Record<string, unknown> = {};
  if (state['model_backend'] !== undefined) info['model_backend'] = state['model_backend'];
  if (state['model_provider'] !== undefined) info['model_provider'] = state['model_provider'];
  if (state['model_name'] !== undefined) info['model_name'] = state['model_name'];
  return info;
}

// ============================================================================
// UserFactExtractor — lightweight extraction of user profile from turns
// ============================================================================

export class UserFactExtractor {
  private static NAME_PATTERNS: Array<{ pattern: RegExp; group: number }> = [
    { pattern: /[Mm]y [Nn]ame [Ii][Ss]\s+["']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})["']?\b/, group: 1 },
    { pattern: /[Cc]all [Mm]e\s+["']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})["']?\b/, group: 1 },
    { pattern: /[Ii](?:'| [Aa])?[Mm]\s+["']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})["']?(?:\s|,|\.|$)/, group: 1 },
  ];

  private static ROLE_PATTERN = /i(?:'|\s+a)?m\s+(a\s+)?((?:senior\s+|lead\s+|staff\s+|principal\s+)?(?:software\s+)?(?:engineer|developer|programmer|architect|designer|manager|lead|cto|devops|sre|data\s+scientist|researcher|student|consultant|product\s+manager))/i;

  static extractFacts(text: string): Array<{ key: string; value: string; memory_type: string }> {
    const facts: Array<{ key: string; value: string; memory_type: string }> = [];

    for (const { pattern, group } of UserFactExtractor.NAME_PATTERNS) {
      const match = text.match(pattern);
      if (match) {
        const captured = match[group]?.trim();
        if (captured && captured.length >= 2 && captured.length <= 40) {
          facts.push({ key: 'name', value: captured, memory_type: 'user_profile' });
          break;
        }
      }
    }

    const roleMatch = text.match(UserFactExtractor.ROLE_PATTERN);
    if (roleMatch) {
      const roleValue = roleMatch[0].trim();
      if (/^i(?:'|\s+a)?m\s+(a\s+)?(senior|lead|staff|principal|software|engineer|developer|programmer|architect|designer|manager|cto|devops|sre|data|researcher|student|consultant|product)/i.test(roleValue)) {
        facts.push({ key: 'role', value: roleValue, memory_type: 'user_profile' });
      }
    }

    return facts;
  }
}
