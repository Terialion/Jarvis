// ============================================================================
// AskUserQuestion tool — ask the user questions to gather preferences
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';

// ---- callback bridge ----
// The TUI sets this ref so the tool can delegate rendering to the React layer.
// { resolve } is stored when the tool is waiting for an answer; the TUI calls
// resolve(answers) when the user submits, unblocking the tool.
export type AskUserQuestionCallback = (
  questions: AskQuestionDef[],
) => Promise<Record<string, string>>;

let askBridge: AskUserQuestionCallback | null = null;

export function setAskUserQuestionBridge(fn: AskUserQuestionCallback | null): void {
  askBridge = fn;
}

// ---- types ----

export interface AskQuestionOption {
  label: string;
  description: string;
}

export interface AskQuestionDef {
  question: string;
  header: string;
  options: AskQuestionOption[];
  multiSelect?: boolean;
}

// ---- schema ----

export const askUserQuestionSchema = toOpenAITool({
  name: 'ask_user_question',
  description:
    'Ask the user one or more questions to clarify requirements, gather preferences, or confirm decisions before proceeding. Use this when the user\'s request is ambiguous or when there are multiple valid approaches.',
  parameters: {
    type: 'object',
    properties: {
      questions: {
        type: 'array',
        minItems: 1,
        maxItems: 4,
        description: 'Questions to ask the user (1-4).',
        items: {
          type: 'object',
          properties: {
            question: {
              type: 'string',
              description: 'The complete question to ask. Be specific and end with a question mark.',
            },
            header: {
              type: 'string',
              description: 'Short label (max 12 chars), e.g. "Auth method", "Library".',
            },
            options: {
              type: 'array',
              minItems: 2,
              maxItems: 4,
              items: {
                type: 'object',
                properties: {
                  label: { type: 'string', description: 'Display text (1-5 words).' },
                  description: {
                    type: 'string',
                    description: 'What this option means or what will happen.',
                  },
                },
                required: ['label', 'description'],
              },
            },
            multiSelect: {
              type: 'boolean',
              description: 'Allow multiple answers to be selected (default false).',
            },
          },
          required: ['question', 'header', 'options'],
        },
      },
    },
    required: ['questions'],
  },
});

// ---- handler ----

const askUserQuestionHandler: ToolHandler = async (
  args,
  _context,
) => {
  const questions = (args as { questions?: AskQuestionDef[] }).questions;
  if (!questions || questions.length === 0) {
    return JSON.stringify({ error: 'No questions provided.' });
  }

  if (!askBridge) {
    return JSON.stringify({
      error: 'Interactive questions are not supported in this mode (no TUI bridge).',
    });
  }

  try {
    const answers = await askBridge(questions);
    return JSON.stringify({ answers });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Question cancelled: ${message}` });
  }
};

// ---- entry ----

export const askUserQuestionTool: ToolEntry = {
  name: 'ask_user_question',
  toolset: 'interactive',
  schema: askUserQuestionSchema,
  handler: askUserQuestionHandler,
  isAsync: true,
  emoji: '❓',
  description: 'Ask the user clarifying questions with structured options.',
};
