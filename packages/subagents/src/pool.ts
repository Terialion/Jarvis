// ============================================================================
// SubagentPool — manage concurrent subagent execution
// ============================================================================

import type { SubagentConfig, SubagentHandle, SubagentResult, SubagentStatus } from './models.js';
import { AgentMailbox } from '@jarvis/agent';

// ============================================================================
// SubagentPool
// ============================================================================

export class SubagentPool {
  private agents: Map<string, SubagentHandle> = new Map();
  private mailboxes: Map<string, AgentMailbox> = new Map();
  private runner: ((config: SubagentConfig, mailbox: AgentMailbox) => Promise<SubagentResult>) | null = null;
  private notifications: Array<{ agentId: string; status: SubagentStatus; result?: SubagentResult }> = [];
  private activeCount = 0;
  private pending: Array<() => void> = [];

  /** Maximum concurrent subagents (default 4, matches Codex agent_max_threads). */
  readonly maxConcurrent: number;

  /** Default nesting depth for subagents. Set before submitting. */
  defaultDepth = 0;

  /** Parent mailbox — subagent results auto-delivered here on completion. */
  private parentMailbox: AgentMailbox | null = null;

  constructor(maxConcurrent = 4) {
    this.maxConcurrent = Math.max(1, maxConcurrent);
  }

  /**
   * Set the parent mailbox where all subagent results are auto-delivered.
   * This enables asynchronous spawn: parent spawns → returns immediately →
   * results arrive automatically in parent's mailbox.
   */
  setParentMailbox(mailbox: AgentMailbox): void {
    this.parentMailbox = mailbox;
  }

  // ========================================================================
  // Configuration
  // ========================================================================

  /**
   * Set the runner function that executes subagent tasks.
   * Called once before any subagents are submitted.
   */
  setRunner(fn: (config: SubagentConfig, mailbox: AgentMailbox) => Promise<SubagentResult>): void {
    this.runner = fn;
  }

  /** Get the mailbox for a specific subagent. */
  getMailbox(agentId: string): AgentMailbox | undefined {
    return this.mailboxes.get(agentId);
  }

  // ========================================================================
  // Submit
  // ========================================================================

  /**
   * Submit a subagent for execution.
   * Returns a handle immediately. The subagent runs asynchronously.
   * Multiple subagents run concurrently up to maxConcurrent.
   */
  submit(config: SubagentConfig): SubagentHandle {
    if (!this.runner) {
      throw new Error('SubagentPool: no runner configured. Call setRunner() first.');
    }

    if (this.agents.has(config.agentId)) {
      throw new Error(`Subagent ${config.agentId} already exists`);
    }

    let resolveCompletion: (result: SubagentResult) => void;
    const completion = new Promise<SubagentResult>((resolve) => {
      resolveCompletion = resolve;
    });

    let cancelled = false;

    const handle: SubagentHandle = {
      agentId: config.agentId,
      status: 'pending',
      completion,
      cancel: () => {
        cancelled = true;
        this._updateStatus(config.agentId, 'cancelled', {
          agentId: config.agentId,
          status: 'cancelled',
          error: 'Cancelled',
        });
        resolveCompletion!({
          agentId: config.agentId,
          status: 'cancelled',
          error: 'Cancelled',
        });
      },
    };

    this.agents.set(config.agentId, handle);

    // Create a dedicated mailbox for this subagent
    const mailbox = new AgentMailbox();
    this.mailboxes.set(config.agentId, mailbox);

    // Start async execution (respects maxConcurrent)
    this._execute(config, handle, mailbox, resolveCompletion!, cancelled);

    return handle;
  }

  // ========================================================================
  // Query
  // ========================================================================

  /** List all subagents with their current status. */
  listAgents(): Array<{ agentId: string; status: SubagentStatus }> {
    return [...this.agents.values()].map((h) => ({
      agentId: h.agentId,
      status: h.status,
    }));
  }

  /** Wait for a specific subagent to complete. */
  async waitAgent(agentId: string, timeoutMs?: number): Promise<SubagentResult> {
    const handle = this.agents.get(agentId);
    if (!handle) {
      throw new Error(`Subagent ${agentId} not found`);
    }

    if (timeoutMs) {
      const timeout = new Promise<SubagentResult>((_, reject) =>
        setTimeout(() => reject(new Error(`Timeout waiting for ${agentId}`)), timeoutMs),
      );
      return Promise.race([handle.completion, timeout]);
    }

    return handle.completion;
  }

  /** Get the number of currently active (pending/running) subagents. */
  getActiveCount(): number {
    let count = 0;
    for (const h of this.agents.values()) {
      if (h.status === 'pending' || h.status === 'running') count++;
    }
    return count;
  }

  /** Drain any accumulated notifications. */
  drainNotifications(): Array<{
    agentId: string;
    status: SubagentStatus;
    result?: SubagentResult;
  }> {
    const drained = [...this.notifications];
    this.notifications = [];
    return drained;
  }

  /** Remove all completed/failed/cancelled agents and shut down. */
  shutdown(): void {
    for (const [, handle] of this.agents) {
      if (handle.status === 'pending' || handle.status === 'running') {
        handle.cancel();
      }
    }
    this.agents.clear();
    this.mailboxes.clear();
    this.notifications = [];
    this.pending = [];
    this.activeCount = 0;
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private async _acquireSlot(): Promise<void> {
    if (this.activeCount < this.maxConcurrent) {
      this.activeCount++;
      return;
    }

    // Queue up — wait for a slot to open
    return new Promise<void>((resolve) => {
      this.pending.push(() => {
        this.activeCount++;
        resolve();
      });
    });
  }

  private _releaseSlot(): void {
    this.activeCount--;
    // Unblock next pending subagent
    const next = this.pending.shift();
    if (next) {
      // Release on next microtick so stack doesn't grow unbounded
      setImmediate(next);
    }
  }

  private async _execute(
    config: SubagentConfig,
    handle: SubagentHandle,
    mailbox: AgentMailbox,
    resolve: (result: SubagentResult) => void,
    cancelled: boolean,
  ): Promise<void> {
    // Wait for concurrency slot (non-blocking)
    await this._acquireSlot();

    if (cancelled) {
      this._releaseSlot();
      return;
    }

    this._updateStatus(config.agentId, 'running');

    try {
      const result = await this.runner!(config, mailbox);
      if (!cancelled) {
        this._updateStatus(config.agentId, result.status, result);
        resolve(result);

        // Auto-deliver result to parent mailbox (Codex completion watcher pattern)
        if (this.parentMailbox) {
          const summary = result.answer || result.error || '(no output)';
          this.parentMailbox.deliver(
            config.agentId,
            `[Subagent ${result.status}]\nTask: ${config.task.slice(0, 100)}\nResult: ${summary.slice(0, 500)}`,
            true,
          );
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      const failedResult: SubagentResult = {
        agentId: config.agentId,
        status: 'failed',
        error: errMsg,
      };
      if (!cancelled) {
        this._updateStatus(config.agentId, 'failed', failedResult);
        resolve(failedResult);
      }
    } finally {
      this.mailboxes.delete(config.agentId);
      this._releaseSlot();
    }
  }

  /** External callback for TUI agent store updates. */
  onStatusUpdate?: (entry: { agentId: string; status: string; role?: string; depth?: number; task?: string }) => void;

  private _updateStatus(
    agentId: string,
    status: SubagentStatus,
    result?: SubagentResult,
  ): void {
    const handle = this.agents.get(agentId);
    if (handle) {
      (handle as { status: SubagentStatus }).status = status;
    }
    this.notifications.push({ agentId, status, result });
    this.onStatusUpdate?.({ agentId, status });
  }
}