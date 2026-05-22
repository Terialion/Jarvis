// ============================================================================
// ContextStore — in-memory session state for skill observations & active tasks
// Python ref: src/jarvis/agent/context_store.py
// ============================================================================

// ============================================================================
// State types (mirrors Python skill_context + web/research_context dataclasses)
// ============================================================================

export interface SkillObservation {
  skill_name: string;
  summary: string;
  facts: Record<string, unknown>;
  related_files: string[];
  tool_calls: string[];
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

// ============================================================================
// SessionContextState
// ============================================================================

export interface SessionContextState {
  recentTurns: Array<Record<string, unknown>>;
  skillObservations: SkillObservation[];
  researchObservations: ResearchObservation[];
  projectFacts: Record<string, unknown>;
  activeTask: ActiveTaskState | null;
  handoffSummary: HandoffSummary | null;
}

// ============================================================================
// Minimal interfaces for injected stores
// ============================================================================

export interface MemoryStoreLike {
  getTyped?(memoryType: string, limit?: number): Array<{ key: string; value_redacted: string }>;
  getProjectMemory?(projectId: string): Record<string, unknown>;
  getUserMemory?(): Record<string, unknown>;
}

export interface SessionStoreLike {
  getRecentTurns(sessionId: string, limit?: number): Promise<Array<Record<string, unknown>>>;
  getSkillObs?(sessionId: string, limit?: number): Promise<Array<Record<string, unknown>>>;
  getResearchObs?(sessionId: string, limit?: number): Promise<Array<Record<string, unknown>>>;
  getActiveTask?(sessionId: string): Promise<Record<string, unknown> | null>;
  getHandoff?(sessionId: string): Promise<Record<string, unknown> | null>;
  getProjectFacts?(sessionId: string, projectId?: string | null): Promise<Record<string, unknown> | null>;
  getSkillObservations?(sessionId: string, limit?: number): Promise<Array<Record<string, unknown>>>;
  getResearchObservations?(sessionId: string, limit?: number): Promise<Array<Record<string, unknown>>>;
  getHandoffSummary?(sessionId: string): Promise<Record<string, unknown> | null>;
}

// ============================================================================
// ContextStore
// ============================================================================

export class ContextStore {
  private _sessions: Map<string, SessionContextState> = new Map();
  private sessionStore: SessionStoreLike | null;
  private memoryStore: MemoryStoreLike | null;

  constructor(opts?: {
    sessionStore?: SessionStoreLike | null;
    memoryStore?: MemoryStoreLike | null;
  }) {
    this.sessionStore = opts?.sessionStore ?? null;
    this.memoryStore = opts?.memoryStore ?? null;
  }

  getState(sessionId: string): SessionContextState {
    const key = sessionId || 'default';
    if (!this._sessions.has(key)) {
      this._sessions.set(key, {
        recentTurns: [],
        skillObservations: [],
        researchObservations: [],
        projectFacts: {},
        activeTask: null,
        handoffSummary: null,
      });
      if (this.sessionStore) {
        this._hydrateFromSession(key).catch(() => { /* best-effort */ });
      }
    }
    return this._sessions.get(key)!;
  }

  appendTurn(sessionId: string, turn: Record<string, unknown>): void {
    const state = this.getState(sessionId);
    state.recentTurns.push({ ...turn });
    state.recentTurns = state.recentTurns.slice(-20);
  }

  addSkillObservation(sessionId: string, observation: SkillObservation): void {
    const state = this.getState(sessionId);
    state.skillObservations.push(observation);
    state.skillObservations = state.skillObservations.slice(-20);
    for (const filePath of observation.related_files) {
      const recentFiles = (state.projectFacts['recent_files'] as string[]) ?? [];
      if (!recentFiles.includes(filePath)) {
        recentFiles.push(filePath);
      }
      state.projectFacts['recent_files'] = recentFiles;
    }
  }

  addResearchObservation(sessionId: string, observation: ResearchObservation): void {
    const state = this.getState(sessionId);
    state.researchObservations.push(observation);
    state.researchObservations = state.researchObservations.slice(-20);
    for (const item of observation.sources) {
      if (typeof item !== 'object' || !item) continue;
      const url = String((item as Record<string, unknown>)['url'] ?? '').trim();
      if (!url) continue;
      const recentSources = (state.projectFacts['recent_sources'] as string[]) ?? [];
      if (!recentSources.includes(url)) {
        recentSources.push(url);
      }
      state.projectFacts['recent_sources'] = recentSources;
    }
  }

  retrieveRecentContext(
    sessionId: string,
    limit: number = 8,
  ): Record<string, unknown> {
    const state = this.getState(sessionId);
    const userMemory =
      this.memoryStore?.getUserMemory?.() ?? {};
    return {
      recent_turns: state.recentTurns.slice(-limit),
      skill_observations: state.skillObservations.slice(-limit).map((o) => ({ ...o })),
      research_observations: state.researchObservations.slice(-limit).map((o) => ({ ...o })),
      project_facts: { ...state.projectFacts },
      active_task: state.activeTask ? { ...state.activeTask } : null,
      handoff_summary: state.handoffSummary ? { ...state.handoffSummary } : null,
      persistent_user_memory: { ...userMemory },
    };
  }

  retrieveSkillObservation(
    sessionId: string,
    opts?: { skillName?: string | null; relatedFile?: string | null },
  ): SkillObservation | null {
    const observations = [...this.getState(sessionId).skillObservations].reverse();
    for (const obs of observations) {
      if (opts?.skillName && obs.skill_name !== opts.skillName) continue;
      if (opts?.relatedFile && !obs.related_files.includes(opts.relatedFile)) continue;
      return obs;
    }
    if (observations.length > 0 && !opts?.skillName && !opts?.relatedFile) {
      return observations[0];
    }
    return null;
  }

  retrieveResearchObservation(sessionId: string): ResearchObservation | null {
    const observations = [...this.getState(sessionId).researchObservations].reverse();
    return observations.length > 0 ? observations[0] : null;
  }

  setActiveTask(sessionId: string, task: ActiveTaskState | null): void {
    this.getState(sessionId).activeTask = task;
  }

  setHandoffSummary(sessionId: string, handoff: HandoffSummary | null): void {
    this.getState(sessionId).handoffSummary = handoff;
  }

  clear(sessionId?: string | null): void {
    if (sessionId == null) {
      this._sessions.clear();
    } else {
      this._sessions.delete(String(sessionId));
    }
  }

  async hydrateThread(
    threadId: string,
    projectId?: string | null,
  ): Promise<Record<string, unknown>> {
    const state = await this._hydrateFromSession(threadId, projectId);
    return {
      thread_id: String(threadId),
      recent_turns: [...state.recentTurns],
      skill_observations: state.skillObservations.map((o) => ({ ...o })),
      research_observations: state.researchObservations.map((o) => ({ ...o })),
      project_facts: { ...state.projectFacts },
      active_task: state.activeTask ? { ...state.activeTask } : null,
      handoff_summary: state.handoffSummary ? { ...state.handoffSummary } : null,
    };
  }

  // ============================================================================
  // Private: hydrate from SessionStore
  // ============================================================================

  private async _hydrateFromSession(
    threadId: string,
    projectId?: string | null,
  ): Promise<SessionContextState> {
    const key = String(threadId);
    if (!this._sessions.has(key)) {
      this._sessions.set(key, {
        recentTurns: [],
        skillObservations: [],
        researchObservations: [],
        projectFacts: {},
        activeTask: null,
        handoffSummary: null,
      });
    }
    const state = this._sessions.get(key)!;

    if (!this.sessionStore) return state;

    try {
      // Restore recent turns
      const turns = await this.sessionStore.getRecentTurns(key, 12);
      state.recentTurns = turns.map((row) => ({
        turn_id: row['turn_id'],
        user_input: row['input_redacted'],
        final_answer: row['output_summary_redacted'],
        skills_used: (row['metadata'] as Record<string, unknown>)?.['skills_used'] ?? [],
        related_files: [],
      }));

      // Restore skill observations
      const getObs = this.sessionStore.getSkillObs ?? this.sessionStore.getSkillObservations;
      if (getObs) {
        const skillRows = await getObs.call(this.sessionStore, key, 12);
        state.skillObservations = skillRows.map((row) => ({
          skill_name: String(row['skill_name'] ?? ''),
          summary: String(row['summary_redacted'] ?? ''),
          facts: ((row['metadata'] as Record<string, unknown>)?.['facts'] as Record<string, unknown>) ?? {},
          related_files: (row['related_files'] as string[]) ?? [],
          tool_calls: (((row['metadata'] as Record<string, unknown>)?.['tool_calls'] as string[]) ?? []),
          created_at: String(row['created_at'] ?? ''),
        }));
      }

      // Restore research observations
      const getResearchObs = this.sessionStore.getResearchObs ?? this.sessionStore.getResearchObservations;
      if (getResearchObs) {
        const researchRows = await getResearchObs.call(this.sessionStore, key, 8);
        state.researchObservations = researchRows.map((row) => ({
          query: String(row['query_redacted'] ?? ''),
          search_tasks: (((row['metadata'] as Record<string, unknown>)?.['search_tasks'] as Array<Record<string, unknown>>) ?? []),
          sources: (row['sources_redacted'] as Array<Record<string, unknown>>) ?? [],
          evidence: (row['evidence_redacted'] as Array<Record<string, unknown>>) ?? [],
          answer_summary: String(row['answer_summary_redacted'] ?? ''),
          confidence: Number(row['confidence'] ?? 0),
          remaining_questions: (((row['metadata'] as Record<string, unknown>)?.['remaining_questions'] as string[]) ?? []),
          created_at: String(row['created_at'] ?? ''),
        }));
      }

      // Restore active task
      if (this.sessionStore.getActiveTask) {
        const activeTask = await this.sessionStore.getActiveTask(key);
        if (activeTask) {
          const meta = (activeTask['metadata'] as Record<string, unknown>) ?? {};
          state.activeTask = {
            task_id: String(meta['task_id'] ?? `task_${threadId}`),
            user_goal: String(meta['user_goal'] ?? activeTask['summary_redacted'] ?? ''),
            current_phase: String(meta['current_phase'] ?? 'resumed'),
            completed_steps: (meta['completed_steps'] as string[]) ?? [],
            remaining_work: (activeTask['remaining_work'] as string[]) ?? [],
            related_files: (activeTask['related_files'] as string[]) ?? [],
            skills_used: (meta['skills_used'] as string[]) ?? [],
            risks: (meta['risks'] as string[]) ?? [],
          };
        }
      }

      // Restore handoff
      const getHs = this.sessionStore.getHandoff ?? this.sessionStore.getHandoffSummary;
      if (getHs) {
        const handoff = await getHs.call(this.sessionStore, key);
        if (handoff) {
          const meta = (handoff['metadata'] as Record<string, unknown>) ?? {};
          state.handoffSummary = {
            user_goal: String(meta['user_goal'] ?? ''),
            current_state: String(meta['current_state'] ?? handoff['summary_redacted'] ?? ''),
            completed_work: (meta['completed_work'] as string[]) ?? [],
            remaining_work: (meta['remaining_work'] as string[]) ?? [],
            context_to_keep: (meta['context_to_keep'] as string[]) ?? [],
            risks: (handoff['risks'] as string[]) ?? [],
          };
        }
      }

      // Restore project facts
      if (this.sessionStore.getProjectFacts) {
        const facts = await this.sessionStore.getProjectFacts(key, projectId);
        if (facts) {
          state.projectFacts['persistent_project_facts'] = facts['facts_redacted'] ?? [];
        }
      }

      // Restore persistent memories
      if (this.memoryStore) {
        if (this.memoryStore.getUserMemory) {
          state.projectFacts['persistent_user_memory'] = this.memoryStore.getUserMemory();
        }
        if (projectId && this.memoryStore.getProjectMemory) {
          state.projectFacts['persistent_project_memory'] = this.memoryStore.getProjectMemory(projectId);
        }
      }
    } catch {
      // Hydration is best-effort
    }

    return state;
  }
}
