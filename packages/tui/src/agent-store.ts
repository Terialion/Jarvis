// ============================================================================
// AgentStore — global state bridge between SubagentPool and TUI
// ============================================================================
// SubagentPool pushes status updates here. TUI subscribes via React hook.

import type { AgentStatusEntry } from './vendor/ui/AgentsPanel.js';

type Listener = () => void;

class AgentStoreImpl {
  private agents: Map<string, AgentStatusEntry> = new Map();
  private listeners: Set<Listener> = new Set();

  /** Update or add an agent status entry. Preserves startedAt from first upsert. */
  upsert(entry: AgentStatusEntry): void {
    const existing = this.agents.get(entry.agentId);
    if (existing?.startedAt && !entry.startedAt) {
      entry.startedAt = existing.startedAt;
    }
    this.agents.set(entry.agentId, entry);
    this.notify();
  }

  /** Remove an agent. */
  remove(agentId: string): void {
    this.agents.delete(agentId);
    this.notify();
  }

  /** Get all agents snapshot. */
  getSnapshot(): AgentStatusEntry[] {
    return [...this.agents.values()];
  }

  /** Subscribe to changes. Returns unsubscribe function. */
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  /** Clear all agents. */
  clear(): void {
    this.agents.clear();
    this.notify();
  }

  private notify(): void {
    for (const l of this.listeners) {
      try { l(); } catch { /* ignore */ }
    }
  }
}

/** Singleton agent store — shared between SubagentPool and TUI. */
export const agentStore = new AgentStoreImpl();