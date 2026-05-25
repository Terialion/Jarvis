// ============================================================================
// Cron tools — CronCreate, CronDelete, CronList, ScheduleWakeup
// Uses the shared CronScheduler singleton
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import { getCronScheduler } from './cron-scheduler.js';

// ---- cron_create ----

export const cronCreateSchema = toOpenAITool({
  name: 'cron_create',
  description:
    'Schedule a prompt to be enqueued at a future time. Uses standard 5-field cron (minute hour day-of-month month day-of-week) in local time. For one-shot reminders, set recurring=false. For recurring tasks (every N minutes, hourly, daily), set recurring=true. Jobs auto-expire after 7 days.',
  parameters: {
    type: 'object',
    properties: {
      cron: {
        type: 'string',
        description: '5-field cron expression: "M H DoM Mon DoW" (e.g. "*/5 * * * *" = every 5 min, "0 9 * * *" = 9am daily, "30 14 28 2 *" = Feb 28 at 2:30pm once).',
      },
      prompt: {
        type: 'string',
        description: 'The prompt to enqueue at each fire time.',
      },
      recurring: {
        type: 'boolean',
        default: true,
        description: 'true = fire on every cron match; false = fire once then auto-delete.',
      },
      durable: {
        type: 'boolean',
        default: false,
        description: 'true = persist to disk and survive restarts; false = in-memory only.',
      },
    },
    required: ['cron', 'prompt'],
  },
});

const cronCreateHandler: ToolHandler = (args, _context) => {
  const cron = String(args.cron ?? '').trim();
  const prompt = String(args.prompt ?? '').trim();
  const recurring = args.recurring !== false;
  const durable = args.durable === true;

  if (!cron || !prompt) {
    return JSON.stringify({ error: 'Missing required parameters: cron and prompt' });
  }

  const fields = cron.split(/\s+/);
  if (fields.length !== 5) {
    return JSON.stringify({ error: 'Cron expression must have exactly 5 fields: minute hour day-of-month month day-of-week' });
  }

  const scheduler = getCronScheduler();
  const id = scheduler.schedule(cron, prompt, recurring, durable);

  if (!id) {
    return JSON.stringify({ error: `Could not compute next fire time for cron: "${cron}"` });
  }

  const job = scheduler.get(id)!;
  return JSON.stringify({
    jobId: id,
    cron: job.cron,
    nextFireAt: new Date(job.nextFireAt).toISOString(),
    recurring: job.recurring,
    message: `Job "${id}" scheduled. Next fire: ${new Date(job.nextFireAt).toISOString()}`,
  });
};

// ---- cron_delete ----

export const cronDeleteSchema = toOpenAITool({
  name: 'cron_delete',
  description: 'Cancel a previously scheduled cron job by its job ID.',
  parameters: {
    type: 'object',
    properties: {
      id: {
        type: 'string',
        description: 'Job ID returned by cron_create.',
      },
    },
    required: ['id'],
  },
});

const cronDeleteHandler: ToolHandler = (args, _context) => {
  const id = String(args.id ?? '').trim();
  if (!id) {
    return JSON.stringify({ error: 'Missing required parameter: id' });
  }

  const scheduler = getCronScheduler();
  const ok = scheduler.cancel(id);

  return JSON.stringify(
    ok
      ? { message: `Job "${id}" cancelled.` }
      : { error: `Job "${id}" not found.` },
  );
};

// ---- cron_list ----

export const cronListSchema = toOpenAITool({
  name: 'cron_list',
  description: 'List all scheduled cron jobs.',
  parameters: {
    type: 'object',
    properties: {},
  },
});

const cronListHandler: ToolHandler = (_args, _context) => {
  const scheduler = getCronScheduler();
  const jobs = scheduler.list();

  if (jobs.length === 0) {
    return JSON.stringify({
      jobs: [],
      message: 'No scheduled jobs.',
    });
  }

  return JSON.stringify({
    jobs: jobs.map((j) => ({
      id: j.id,
      cron: j.cron,
      nextFireAt: new Date(j.nextFireAt).toISOString(),
      recurring: j.recurring,
      durable: j.durable,
      promptPreview: j.prompt.slice(0, 100),
    })),
  });
};

// ---- schedule_wakeup ----

export const scheduleWakeupSchema = toOpenAITool({
  name: 'schedule_wakeup',
  description:
    'Schedule when to resume work in a dynamic loop. Use for self-paced iterations where the next wakeup time depends on what is being waited on. The runtime clamps delaySeconds to [60, 3600].',
  parameters: {
    type: 'object',
    properties: {
      delaySeconds: {
        type: 'number',
        description: 'Seconds from now to wake up (clamped to 60-3600).',
      },
      reason: {
        type: 'string',
        description: 'One short sentence explaining the chosen delay.',
      },
      prompt: {
        type: 'string',
        description: 'The prompt to enqueue at wakeup time.',
      },
    },
    required: ['delaySeconds', 'reason', 'prompt'],
  },
});

const scheduleWakeupHandler: ToolHandler = (args, _context) => {
  const delaySeconds = Math.max(60, Math.min(3600, Number(args.delaySeconds ?? 300)));
  const reason = String(args.reason ?? '').trim();
  const prompt = String(args.prompt ?? '').trim();

  if (!reason || !prompt) {
    return JSON.stringify({ error: 'Missing required parameters: reason and prompt' });
  }

  // Schedule as a one-shot cron: compute target time as "M H DoM Mon DoW"
  const target = new Date(Date.now() + delaySeconds * 1000);
  const cronExpr = `${target.getMinutes()} ${target.getHours()} ${target.getDate()} ${target.getMonth() + 1} *`;

  const scheduler = getCronScheduler();
  const id = scheduler.schedule(cronExpr, prompt, false, false);

  if (!id) {
    return JSON.stringify({ error: 'Failed to schedule wakeup.' });
  }

  return JSON.stringify({
    wakeupId: id,
    delaySeconds,
    reason,
    fireAt: target.toISOString(),
    message: `Wakeup scheduled in ${delaySeconds}s: ${reason}`,
  });
};

// ---- entries ----

export const cronCreateTool: ToolEntry = {
  name: 'cron_create',
  toolset: 'orchestration',
  schema: cronCreateSchema,
  handler: cronCreateHandler,
  emoji: '⏰',
  description: 'Schedule a recurring or one-shot cron job.',
};

export const cronDeleteTool: ToolEntry = {
  name: 'cron_delete',
  toolset: 'orchestration',
  schema: cronDeleteSchema,
  handler: cronDeleteHandler,
  emoji: '❌',
  description: 'Cancel a scheduled cron job.',
};

export const cronListTool: ToolEntry = {
  name: 'cron_list',
  toolset: 'orchestration',
  schema: cronListSchema,
  handler: cronListHandler,
  emoji: '📅',
  description: 'List all scheduled cron jobs.',
};

export const scheduleWakeupTool: ToolEntry = {
  name: 'schedule_wakeup',
  toolset: 'orchestration',
  schema: scheduleWakeupSchema,
  handler: scheduleWakeupHandler,
  emoji: '🔔',
  description: 'Schedule a one-shot delayed wakeup for loop pacing.',
};
