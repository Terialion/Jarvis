// ============================================================================
// ResponseComposer — human + machine summary composition
// ConversationSummarizer — heuristic conversation summarization
// ============================================================================

import type { ChatMessage, ToolResult } from '@jarvis/shared';

// ============================================================================
// Types
// ============================================================================

export interface ConversationSummary {
  goal: string;
  progress: string;
  decisions: string[];
  resolvedQuestions: string[];
  pendingQuestions: string[];
  files: string[];
  remainingWork: string;
}

export interface SummaryConfig {
  /** Maximum characters for the compact summary string */
  maxSummaryChars?: number;
}

export interface ComposeOptions {
  finalAnswer: string;
  toolResults: ToolResult[];
  stopReason: string;
  outputType?: string;
  clarification?: Record<string, unknown>;
  availableSkills?: string[];
  loadedSkills?: string[];
  skillLoadsCount?: number;
  skillsUsed?: string[];
  skillCallsCount?: number;
  skillResults?: Record<string, unknown>[];
  activeTask?: Record<string, unknown>;
  handoffSummary?: Record<string, unknown>;
  previousSummaries?: Record<string, unknown>[];
  contextReuse?: boolean;
  skillObservations?: Record<string, unknown>[];
  researchObservations?: Record<string, unknown>[];
}

// ============================================================================
// ResponseComposer
// ============================================================================

export class ResponseComposer {
  compose(opts: ComposeOptions): Record<string, unknown> {
    const {
      finalAnswer,
      toolResults,
      stopReason,
      outputType = 'answer',
      availableSkills,
      loadedSkills,
      skillLoadsCount,
      skillsUsed,
      skillCallsCount,
      skillResults,
      activeTask,
      handoffSummary,
      previousSummaries,
      contextReuse = false,
      skillObservations,
      researchObservations,
    } = opts;

    const toolsUsed: string[] = [];
    const filesChanged: string[] = [];
    const commandsRun: string[] = [];
    const testsRun: string[] = [];
    const risks: string[] = [];

    for (const result of toolResults) {
      toolsUsed.push(result.name);
      const md = result.data ?? {};
      const changedFiles = Array.isArray(md['changed_files']) ? md['changed_files'] : [];
      filesChanged.push(...changedFiles.map(String));
      const cmds = Array.isArray(md['commands_run']) ? md['commands_run'] : [];
      commandsRun.push(...cmds.map(String));
      const tests = Array.isArray(md['tests_run']) ? md['tests_run'] : [];
      testsRun.push(...tests.map(String));
      if (!result.ok && result.error) {
        risks.push(`${result.name}: ${result.error}`);
      }
    }

    let outcome = 'completed';
    if (['max_steps', 'timeout', 'approval_required', 'no_progress'].includes(stopReason)) {
      outcome = 'partial';
    }
    if (!finalAnswer) {
      outcome = 'failed';
    }

    const conclusion = finalAnswer || 'No final answer produced.';

    const humanParts = [
      `Conclusion:\n- ${conclusion}`,
      `What was done:\n- Called ${toolsUsed.length} tool(s)`,
      `Tools used:\n- ${toolsUsed.length > 0 ? toolsUsed.join(', ') : 'none'}`,
      `Files changed:\n- ${filesChanged.length > 0 ? filesChanged.join(', ') : 'none'}`,
      `Test results:\n- ${testsRun.length > 0 ? testsRun.join(', ') : 'none'}`,
      `Risks and incomplete items:\n- ${risks.length > 0 ? risks.join('; ') : 'none'}`,
      `Next steps:\n- ${outcome !== 'completed' ? 'Fix the stop_reason issue then retry.' : 'None — task completed.'}`,
    ];
    const human = humanParts.join('\n');

    const builtHandoff: Record<string, unknown> = {
      user_goal: conclusion.slice(0, 160),
      current_state: outcome,
      last_action: toolsUsed.slice(-3).join(', ') || 'no tools called',
      modified_files: [...new Set(filesChanged)].slice(0, 10),
      completed_work: toolsUsed.map((t) => `Called ${t}`),
      remaining_work: [],
      context_to_keep: [...new Set(filesChanged)].slice(0, 5),
      risks,
    };
    if (handoffSummary && typeof handoffSummary === 'object') {
      for (const [k, v] of Object.entries(handoffSummary)) {
        if (v) builtHandoff[k] = v;
      }
    }

    const accumulatedContext = ResponseComposer._buildAccumulatedContext(previousSummaries);

    const machine: Record<string, unknown> = {
      outcome,
      output_type: outputType,
      tools_used: toolsUsed,
      files_changed: filesChanged,
      commands_run: commandsRun,
      tests_run: testsRun,
      risks,
      stop_reason: stopReason,
      handoff_summary: conclusion.slice(0, 400),
      available_skills: availableSkills ?? [],
      loaded_skills: loadedSkills ?? [],
      skill_loads_count: skillLoadsCount ?? 0,
      skills_used: skillsUsed ?? [],
      skill_calls_count: skillCallsCount ?? 0,
      skill_results_count: (skillResults ?? []).length,
      skill_results: skillResults ?? [],
      context_reuse: contextReuse,
      active_task: activeTask ?? {},
      handoff_summary_obj: builtHandoff,
      accumulated_context: accumulatedContext,
      skill_observations: skillObservations ?? [],
      research_observations: researchObservations ?? [],
    };

    if (opts.clarification) {
      machine['needs_user_clarification'] = true;
      machine['missing_fields'] = (opts.clarification['missing_fields'] as string[]) ?? [];
      machine['clarification_question'] = String(opts.clarification['question'] ?? '').trim();
    }

    return { human, machine };
  }

  private static _buildAccumulatedContext(
    previousSummaries?: Record<string, unknown>[],
  ): Record<string, unknown>[] {
    if (!previousSummaries || previousSummaries.length === 0) return [];
    const facts: Record<string, unknown>[] = [];
    const seenGoals = new Set<string>();
    const seenFiles = new Set<string>();
    for (const s of previousSummaries) {
      const sm = (s['summary'] as Record<string, unknown>) ?? {};
      const machine = (sm['machine'] as Record<string, unknown>) ?? {};
      if (typeof machine !== 'object') continue;
      const ho = (machine['handoff_summary_obj'] as Record<string, unknown>) ?? {};
      if (typeof ho === 'object') {
        const goal = String(ho['user_goal'] ?? '').trim();
        if (goal && !seenGoals.has(goal)) {
          seenGoals.add(goal);
          facts.push({ kind: 'goal', text: goal.slice(0, 200) });
        }
        const files = (ho['modified_files'] as string[]) ?? [];
        for (const f of files.slice(0, 3)) {
          const fStr = String(f);
          if (fStr && !seenFiles.has(fStr)) {
            seenFiles.add(fStr);
            facts.push({ kind: 'file', text: fStr });
          }
        }
        const works = (ho['completed_work'] as string[]) ?? [];
        for (const w of works.slice(0, 2)) {
          const wStr = String(w);
          if (wStr) facts.push({ kind: 'work', text: wStr.slice(0, 200) });
        }
      }
      const prevFacts = (machine['accumulated_context'] as Record<string, unknown>[]) ?? [];
      for (const fact of prevFacts) {
        if (typeof fact === 'object' && !facts.includes(fact)) {
          facts.push(fact);
        }
      }
    }
    return facts.slice(0, 20);
  }
}

// ============================================================================
// ConversationSummarizer (heuristic — kept for backward compat)
// ============================================================================

export class ConversationSummarizer {
  private config: Required<SummaryConfig>;

  constructor(config: SummaryConfig = {}) {
    this.config = {
      maxSummaryChars: config.maxSummaryChars ?? 2_000,
    };
  }

  summarize(messages: ChatMessage[]): ConversationSummary {
    if (messages.length === 0) {
      return {
        goal: 'No conversation yet',
        progress: '',
        decisions: [],
        resolvedQuestions: [],
        pendingQuestions: [],
        files: [],
        remainingWork: '',
      };
    }

    const userMessages = messages.filter((m) => m.role === 'user');
    const firstUserMessage = userMessages[0]?.content ?? '';

    const assistantMessages = messages.filter((m) => m.role === 'assistant');
    const lastAssistantContent =
      assistantMessages[assistantMessages.length - 1]?.content ?? '';

    const goal =
      firstUserMessage.length > 300
        ? firstUserMessage.slice(0, 300) + '...'
        : firstUserMessage;

    const filePattern =
      /(?:^|\s)(?:\/[\w./-]+|[\w./-]+\.(?:json|tsx|jsx|yaml|toml|html|yml|css|bat|ps1|txt|ts|js|py|md|sh))/g;
    const files = new Set<string>();
    for (const msg of messages) {
      const matches = msg.content.match(filePattern);
      if (matches) {
        for (const m of matches) {
          files.add(m.trim());
        }
      }
    }

    const questionPattern = /[^.?]+[?]/g;
    const questions: string[] = [];
    for (const msg of messages) {
      const matches = msg.content.match(questionPattern);
      if (matches) {
        for (const m of matches) {
          const q = m.trim();
          if (q && !questions.includes(q)) {
            questions.push(q);
          }
        }
      }
    }

    const midPoint = Math.floor(questions.length / 2);
    const resolvedQuestions = questions.slice(0, midPoint);
    const pendingQuestions = questions.slice(midPoint);

    const decisionPattern =
      /^.*\b(?:decision|decided|will use|going to|chose|chosen|opted for)\b.*$/gim;
    const decisions: string[] = [];
    for (const msg of messages) {
      const matches = msg.content.match(decisionPattern);
      if (matches) {
        for (const m of matches) {
          const d = m.trim();
          if (d && !decisions.includes(d)) {
            decisions.push(d);
          }
        }
      }
    }

    const turnCount = messages.filter((m) => m.role === 'assistant').length;
    const toolCallCount = messages.filter((m) => m.role === 'tool').length;
    const progress = `${turnCount} assistant response(s), ${toolCallCount} tool result(s)`;

    const remainingWork =
      lastAssistantContent.length > 500
        ? lastAssistantContent.slice(0, 500) + '...'
        : lastAssistantContent;

    return {
      goal,
      progress,
      decisions,
      resolvedQuestions,
      pendingQuestions,
      files: [...files].slice(0, 20),
      remainingWork,
    };
  }

  compactSummary(summary: ConversationSummary): string {
    const maxChars = this.config.maxSummaryChars;

    let result = '';

    result += `Goal: ${summary.goal}\n`;
    result += `Progress: ${summary.progress}\n`;

    if (summary.decisions.length > 0) {
      result += `Decisions:\n`;
      for (const d of summary.decisions) {
        result += `  - ${d}\n`;
      }
    }

    if (summary.resolvedQuestions.length > 0) {
      result += `Resolved:\n`;
      for (const q of summary.resolvedQuestions) {
        result += `  - ${q}\n`;
      }
    }

    if (summary.pendingQuestions.length > 0) {
      result += `Pending:\n`;
      for (const q of summary.pendingQuestions) {
        result += `  - ${q}\n`;
      }
    }

    if (summary.files.length > 0) {
      result += `Files: ${summary.files.join(', ')}\n`;
    }

    if (summary.remainingWork) {
      result += `Remaining: ${summary.remainingWork}\n`;
    }

    if (result.length > maxChars) {
      result = result.slice(0, maxChars - 3) + '...';
    }

    return result;
  }
}
