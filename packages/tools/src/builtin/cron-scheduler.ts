// ============================================================================
// Cron scheduler — lightweight in-process job scheduler using setTimeout
// Supports 5-field cron expressions and one-shot timers
// ============================================================================

export interface CronJob {
  id: string;
  cron: string;
  prompt: string;
  recurring: boolean;
  durable: boolean;
  createdAt: number;
  nextFireAt: number;
  firesLeft: number; // -1 = unlimited
}

type CronStore = Map<string, CronJob>;

// ---- cron expression parser (5-field: minute hour dom month dow) ----

function cronNext(cron: string, from: Date = new Date()): Date | null {
  const fields = cron.trim().split(/\s+/);
  if (fields.length !== 5) return null;

  const [minF, hourF, domF, monthF, dowF] = fields;

  const now = new Date(from);
  now.setSeconds(0, 0);
  now.setMinutes(now.getMinutes() + 1); // start next minute

  // Try up to 2 years ahead
  const maxDate = new Date(now);
  maxDate.setFullYear(maxDate.getFullYear() + 2);

  for (const d = new Date(now); d <= maxDate; d.setMinutes(d.getMinutes() + 1)) {
    if (!fieldMatches(minF, d.getMinutes(), 0, 59)) continue;
    if (!fieldMatches(hourF, d.getHours(), 0, 23)) continue;
    if (!fieldMatches(domF, d.getDate(), 1, 31)) continue;
    if (!fieldMatches(monthF, d.getMonth() + 1, 1, 12)) continue;
    if (!fieldMatches(dowF, d.getDay(), 0, 6)) continue;
    return new Date(d);
  }

  return null;
}

function fieldMatches(field: string, value: number, min: number, max: number): boolean {
  if (field === '*') return true;

  for (const part of field.split(',')) {
    const p = part.trim();
    if (p.includes('/')) {
      // Step: */5 or 1-30/5
      const [range, stepStr] = p.split('/');
      const step = parseInt(stepStr, 10);
      if (isNaN(step) || step < 1) continue;
      const [rangeStart, rangeEnd] = range === '*'
        ? [min, max]
        : range.split('-').map((s) => parseInt(s, 10));
      if (isNaN(rangeStart)) continue;
      const end = isNaN(rangeEnd ?? NaN) ? rangeStart : (rangeEnd ?? max);
      for (let v = rangeStart; v <= end; v += step) {
        if (v === value) return true;
      }
    } else if (p.includes('-')) {
      const [start, end] = p.split('-').map((s) => parseInt(s, 10));
      if (isNaN(start) || isNaN(end)) continue;
      if (value >= start && value <= end) return true;
    } else {
      if (parseInt(p, 10) === value) return true;
    }
  }

  return false;
}

// ---- scheduler ----

export class CronScheduler {
  private jobs: CronStore = new Map();
  private timers: Map<string, NodeJS.Timeout> = new Map();
  private seq = 0;
  private onFire?: (job: CronJob) => void;

  /** Register a callback invoked when a job fires. */
  onFireCallback(fn: (job: CronJob) => void): void {
    this.onFire = fn;
  }

  /** Schedule a new job. Returns the job ID. */
  schedule(
    cron: string,
    prompt: string,
    recurring: boolean,
    durable: boolean,
  ): string | null {
    const nextFire = cronNext(cron);
    if (!nextFire) return null;

    const id = `cron_${++this.seq}`;
    const maxFires = 7 * 24 * 60; // auto-expire at ~10,080 fires (~7 days for minutely)
    const job: CronJob = {
      id,
      cron,
      prompt,
      recurring,
      durable,
      createdAt: Date.now(),
      nextFireAt: nextFire.getTime(),
      firesLeft: recurring ? maxFires : 1,
    };

    this.jobs.set(id, job);
    this._scheduleTimer(job);
    return id;
  }

  /** Cancel and remove a job by ID. */
  cancel(id: string): boolean {
    const timer = this.timers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(id);
    }
    return this.jobs.delete(id);
  }

  /** List all active jobs. */
  list(): CronJob[] {
    return [...this.jobs.values()];
  }

  /** Get a single job by ID. */
  get(id: string): CronJob | undefined {
    return this.jobs.get(id);
  }

  /** Clean up all jobs and timers. */
  destroy(): void {
    for (const timer of this.timers.values()) {
      clearTimeout(timer);
    }
    this.timers.clear();
    this.jobs.clear();
  }

  // ---- internal ----

  private _scheduleTimer(job: CronJob): void {
    const existing = this.timers.get(job.id);
    if (existing) clearTimeout(existing);

    const delay = Math.max(0, job.nextFireAt - Date.now());
    const timer = setTimeout(() => this._fire(job.id), delay);
    this.timers.set(job.id, timer);
  }

  private _fire(jobId: string): void {
    const job = this.jobs.get(jobId);
    if (!job) return;

    this.timers.delete(jobId);

    // Notify listener
    this.onFire?.(job);

    job.firesLeft--;

    if (job.firesLeft <= 0) {
      this.jobs.delete(jobId);
      return;
    }

    // Schedule next fire for recurring jobs
    if (job.recurring) {
      const next = cronNext(job.cron);
      if (next) {
        job.nextFireAt = next.getTime();
        this._scheduleTimer(job);
      } else {
        this.jobs.delete(jobId);
      }
    } else {
      this.jobs.delete(jobId);
    }
  }
}

/** Shared singleton for the process. */
let instance: CronScheduler | null = null;

export function getCronScheduler(): CronScheduler {
  if (!instance) {
    instance = new CronScheduler();
  }
  return instance;
}
