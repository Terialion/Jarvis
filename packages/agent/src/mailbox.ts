// ============================================================================
// AgentMailbox — per-agent message inbox (Codex mailbox pattern)
// ============================================================================

export interface MailItem {
  senderId: string;
  message: string;
  triggerTurn: boolean;
  timestamp: number;
}

export class AgentMailbox {
  private pending: MailItem[] = [];
  private listeners: Array<() => void> = [];

  /** Deliver a message to this mailbox. */
  deliver(senderId: string, message: string, triggerTurn = false): void {
    this.pending.push({
      senderId,
      message,
      triggerTurn,
      timestamp: Date.now(),
    });
    // Notify listeners (e.g. AgentLoop waiting for new messages)
    for (const cb of this.listeners) {
      try { cb(); } catch { /* fire-and-forget */ }
    }
  }

  /** View pending messages without removing them. */
  poll(): readonly MailItem[] {
    return this.pending;
  }

  /** Retrieve and clear all pending messages. */
  drain(): MailItem[] {
    const items = this.pending;
    this.pending = [];
    return items;
  }

  /** Check if there are pending messages. */
  hasPending(): boolean {
    return this.pending.length > 0;
  }

  /** Check if any pending message has triggerTurn set. */
  hasPendingTriggerTurn(): boolean {
    return this.pending.some((m) => m.triggerTurn);
  }

  /** Clear all pending messages. */
  clear(): void {
    this.pending = [];
  }

  /** Number of pending messages. */
  get size(): number {
    return this.pending.length;
  }

  /** Register a listener called when new messages arrive. */
  onMessage(cb: () => void): () => void {
    this.listeners.push(cb);
    return () => {
      const idx = this.listeners.indexOf(cb);
      if (idx >= 0) this.listeners.splice(idx, 1);
    };
  }
}