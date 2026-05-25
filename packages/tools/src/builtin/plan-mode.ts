// ============================================================================
// Plan Mode tools — enter and exit structured planning mode
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- enter_plan_mode ----

export const enterPlanModeSchema = toOpenAITool({
  name: 'enter_plan_mode',
  description:
    'Enter plan mode to explore the codebase and design an implementation approach before writing code. Use this when the task is non-trivial and would benefit from upfront design. In plan mode, you should: 1) thoroughly explore the codebase, 2) understand existing patterns, 3) design an approach, 4) present the plan for user approval before implementing.',
  parameters: {
    type: 'object',
    properties: {
      task: {
        type: 'string',
        description: 'Brief description of the task to plan.',
      },
    },
    required: ['task'],
  },
});

const enterPlanModeHandler: ToolHandler = (args) => {
  const task = (args as { task: string }).task;
  return JSON.stringify({
    plan_mode: true,
    message: `Entering plan mode for: ${task}. Explore the codebase, identify the key files and patterns, then present a clear implementation plan. Do NOT write implementation code yet — only exploration and design. Use exit_plan_mode when the plan is ready for user review.`,
  });
};

// ---- exit_plan_mode ----

export const exitPlanModeSchema = toOpenAITool({
  name: 'exit_plan_mode',
  description:
    'Exit plan mode and present the plan for user approval. The plan should be clear, actionable, and reference specific files and changes. After calling this, wait for user feedback before implementing.',
  parameters: {
    type: 'object',
    properties: {
      summary: {
        type: 'string',
        description: 'One-line summary of the plan.',
      },
      steps: {
        type: 'array',
        minItems: 1,
        items: {
          type: 'object',
          properties: {
            step: { type: 'string', description: 'Step description.' },
            files: {
              type: 'array',
              items: { type: 'string' },
              description: 'Files that will be modified.',
            },
            verification: {
              type: 'string',
              description: 'How to verify this step is correct.',
            },
          },
          required: ['step'],
        },
        description: 'Ordered implementation steps.',
      },
    },
    required: ['summary'],
  },
});

const exitPlanModeHandler: ToolHandler = (args) => {
  const params = args as { summary: string; steps?: Array<{ step: string; files?: string[]; verification?: string }> };
  const steps = params.steps ?? [];
  const planLines = [
    `## Plan: ${params.summary}`,
    '',
    ...steps.map((s, i) => {
      const files = s.files?.length ? ` [${s.files.join(', ')}]` : '';
      const verify = s.verification ? ` → verify: ${s.verification}` : '';
      return `${i + 1}. ${s.step}${files}${verify}`;
    }),
  ];

  return JSON.stringify({
    plan_mode: false,
    message: planLines.join('\n'),
  });
};

// ---- entries ----

export const enterPlanModeTool: ToolEntry = {
  name: 'enter_plan_mode',
  toolset: 'orchestration',
  schema: enterPlanModeSchema,
  handler: enterPlanModeHandler,
  emoji: '📐',
  description: 'Enter planning mode to design before implementing.',
};

export const exitPlanModeTool: ToolEntry = {
  name: 'exit_plan_mode',
  toolset: 'orchestration',
  schema: exitPlanModeSchema,
  handler: exitPlanModeHandler,
  emoji: '📋',
  description: 'Exit planning mode with a structured implementation plan.',
};
