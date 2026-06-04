// ============================================================================
// Plan Mode tools - enter and exit structured planning mode (CC-style)
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- Plan Review Bridge (CC-style interactive approval) ----
// The TUI sets this bridge so exit_plan_mode can show an interactive review
// surface. The bridge returns the user's choice: "proceed", "edit", or "cancel".

export interface PlanReviewRequest {
  summary: string;
  steps: Array<{ step: string; files?: string[]; verification?: string }>;
  allowedPrompts?: Array<{ tool: string; prompt: string }>;
}

export type PlanReviewCallback = (
  plan: PlanReviewRequest,
) => Promise<'proceed' | 'edit' | 'cancel'>;

let planReviewBridge: PlanReviewCallback | null = null;

export function setPlanReviewBridge(fn: PlanReviewCallback | null): void {
  planReviewBridge = fn;
}

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
    message: `Entering plan mode for: ${task}. Explore the codebase, identify the key files and patterns, then present a clear implementation plan. Do NOT write implementation code yet - only exploration and design. Use exit_plan_mode when the plan is ready for user review.`,
  });
};

// ---- exit_plan_mode ----

export const exitPlanModeSchema = toOpenAITool({
  name: 'exit_plan_mode',
  description:
    'Exit plan mode and present the plan for user approval. The plan should be clear, actionable, and reference specific files and changes. After calling this, the user will be shown an interactive review UI with options to Proceed, Edit, or Cancel. Wait for the user choice before taking further action.',
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
      allowedPrompts: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            tool: { type: 'string', enum: ['Bash'] },
            prompt: { type: 'string' },
          },
          required: ['tool', 'prompt'],
        },
        description: 'Prompt-based permissions needed to implement the plan.',
      },
    },
    required: ['summary'],
  },
});

const exitPlanModeHandler: ToolHandler = async (args) => {
  const params = args as {
    summary: string;
    steps?: Array<{ step: string; files?: string[]; verification?: string }>;
    allowedPrompts?: Array<{ tool: string; prompt: string }>;
  };
  const steps = params.steps ?? [];
  const allowedPrompts = params.allowedPrompts ?? [];

  const planLines = [
    `## Plan: ${params.summary}`,
    '',
    ...steps.map((step, index) => {
      const files = step.files?.length ? ` [${step.files.join(', ')}]` : '';
      const verify = step.verification ? ` -> verify: ${step.verification}` : '';
      return `${index + 1}. ${step.step}${files}${verify}`;
    }),
    ...(allowedPrompts.length > 0
      ? ['', '## Required permissions', ...allowedPrompts.map((prompt) => `- **${prompt.tool}**: ${prompt.prompt}`)]
      : []),
  ];

  if (planReviewBridge) {
    const choice = await planReviewBridge({
      summary: params.summary,
      steps,
      allowedPrompts: allowedPrompts.length > 0 ? allowedPrompts : undefined,
    });

    if (choice === 'cancel') {
      return JSON.stringify({
        plan_mode: false,
        status: 'cancelled',
        message:
          `${planLines.join('\n')}\n\n` +
          '**Plan cancelled by user.** Return to exploration or ask the user for clarification.',
      });
    }

    if (choice === 'edit') {
      return JSON.stringify({
        plan_mode: false,
        status: 'needs_edit',
        message:
          `${planLines.join('\n')}\n\n` +
          '**User requested edits to this plan.** Ask the user what changes they would like, update the plan, then call exit_plan_mode again.',
      });
    }

    return JSON.stringify({
      plan_mode: false,
      status: 'approved',
      message:
        `${planLines.join('\n')}\n\n` +
        '**Plan approved.** You may now implement the plan. Follow the steps in order.',
      allowedPrompts: allowedPrompts.length > 0 ? allowedPrompts : undefined,
    });
  }

  return JSON.stringify({
    plan_mode: false,
    message: planLines.join('\n'),
    allowedPrompts: allowedPrompts.length > 0 ? allowedPrompts : undefined,
  });
};

// ---- entries ----

export const enterPlanModeTool: ToolEntry = {
  name: 'enter_plan_mode',
  toolset: 'orchestration',
  schema: enterPlanModeSchema,
  handler: enterPlanModeHandler,
  emoji: 'P',
  description: 'Enter planning mode to design before implementing.',
};

export const exitPlanModeTool: ToolEntry = {
  name: 'exit_plan_mode',
  toolset: 'orchestration',
  schema: exitPlanModeSchema,
  handler: exitPlanModeHandler,
  isAsync: true,
  emoji: 'R',
  description: 'Exit planning mode with a structured implementation plan for user review.',
};
