// ============================================================================
// SubagentPool — manage concurrent subagent execution
// ============================================================================

import type { SubagentConfig, SubagentHandle, SubagentResult, SubagentStatus } from './models.js';

// ============================================================================
// SubagentPool
// ============================================================================

export class SubagentPool {
  private agents: Map<string, SubagentHandle> = new Map();
  private runner: ((config: SubagentConfig) => Promise<SubagentResult>) | null = null;
  private notifications: Array<{ agentId: string; status: SubagentStatus; result?: SubagentResult }> = [];
  private lock = false;

  // ========================================================================
  // Configuration
  // ========================================================================

  /**
   * Set the runner function that executes subagent tasks.
   * Called once before any subagents are submitted.
   */
  setRunner(fn: (config: SubagentConfig) => Promise<SubagentResult>): void {
    this.runner = fn;
  }

  // ========================================================================
  // Submit
  // ========================================================================

  /**
   * Submit a subagent for execution.
   * Returns a handle immediately. The subagent runs asynchronously.
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

    // Start async execution
    this._execute(config, handle, resolveCompletion!, cancelled);

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
  activeCount(): number {
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
    for (const [id, handle] of this.agents) {
      if (handle.status === 'pending' || handle.status === 'running') {
        handle.cancel();
      }
    }
    this.agents.clear();
    this.notifications = [];
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private async _execute(
    config: SubagentConfig,
    handle: SubagentHandle,
    resolve: (result: SubagentResult) => void,
    cancelled: boolean,
  ): Promise<void> {
    // Serialize starts to avoid races
    while (this.lock) {
      await new Promise((r) => setTimeout(r, 5));
    }
    this.lock = true;

    if (cancelled) {
      this.lock = false;
      return;
    }

    this._updateStatus(config.agentId, 'running');
    this.lock = false;

    try {
      const result = await this.runner!(config);
      if (!cancelled) {
        this._updateStatus(config.agentId, result.status, result);
        resolve(result);
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
    }
  }

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
  }
}
