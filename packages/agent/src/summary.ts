// ============================================================================
// ConversationSummarizer — summarizes conversation history for context
// ============================================================================

import type { ChatMessage } from '@jarvis/shared';

// ============================================================================
// Configuration
// ============================================================================

export interface SummaryConfig {
  /** Maximum characters for the compact summary string */
  maxSummaryChars?: number;
}

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

// ============================================================================
// ConversationSummarizer
// ============================================================================

export class ConversationSummarizer {
  private config: Required<SummaryConfig>;

  constructor(config: SummaryConfig = {}) {
    this.config = {
      maxSummaryChars: config.maxSummaryChars ?? 2_000,
    };
  }

  // ========================================================================
  // Generate a structured summary from messages
  // ========================================================================

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

    // Extract user messages for goal detection
    const userMessages = messages.filter((m) => m.role === 'user');
    const firstUserMessage = userMessages[0]?.content ?? '';

    // Extract assistant messages for progress
    const assistantMessages = messages.filter((m) => m.role === 'assistant');
    const lastAssistantContent =
      assistantMessages[assistantMessages.length - 1]?.content ?? '';

    // Estimate goal from first user message (truncated)
    const goal = firstUserMessage.length > 300
      ? firstUserMessage.slice(0, 300) + '...'
      : firstUserMessage;

    // Track files mentioned across all messages
    // Longest extensions first to prevent partial matches (js vs json, ts vs tsx)
    const filePattern = /(?:^|\s)(?:\/[\w./-]+|[\w./-]+\.(?:json|tsx|jsx|yaml|toml|html|yml|css|bat|ps1|txt|ts|js|py|md|sh))/g;
    const files = new Set<string>();
    for (const msg of messages) {
      const matches = msg.content.match(filePattern);
      if (matches) {
        for (const m of matches) {
          files.add(m.trim());
        }
      }
    }

    // Detect questions (non-greedy to handle multiple ? on one line)
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

    // Separate into resolved (early) and pending (late) questions
    const midPoint = Math.floor(questions.length / 2);
    const resolvedQuestions = questions.slice(0, midPoint);
    const pendingQuestions = questions.slice(midPoint);

    // Detect decisions (lines with "decision:", "decided:", "will use", "going to")
    const decisionPattern = /^.*\b(?:decision|decided|will use|going to|chose|chosen|opted for)\b.*$/gim;
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

    // Progress: summarize from assistant messages
    const turnCount = messages.filter((m) => m.role === 'assistant').length;
    const toolCallCount = messages.filter((m) => m.role === 'tool').length;
    const progress = `${turnCount} assistant response(s), ${toolCallCount} tool result(s)`;

    // Remaining work from last assistant
    const remainingWork = lastAssistantContent.length > 500
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

  // ========================================================================
  // Generate a compact string summary
  // ========================================================================

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

    // Truncate to maxChars
    if (result.length > maxChars) {
      result = result.slice(0, maxChars - 3) + '...';
    }

    return result;
  }
}
