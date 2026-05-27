// ============================================================================
// AgentRegistry — identity registration and discovery (Codex AgentRegistry pattern)
// ============================================================================

import type { AgentIdentity } from './models.js';

export type { AgentIdentity } from './models.js';

export class AgentRegistry {
  private agents: Map<string, AgentIdentity> = new Map();

  /** Register a new agent identity. Throws if agentId already exists. */
  register(identity: AgentIdentity): void {
    if (this.agents.has(identity.agentId)) {
      throw new Error(`Agent ${identity.agentId} already registered`);
    }
    this.agents.set(identity.agentId, { ...identity });
  }

  /** Remove an agent from the registry. */
  unregister(agentId: string): boolean {
    return this.agents.delete(agentId);
  }

  /** Get an agent by ID. */
  get(agentId: string): AgentIdentity | undefined {
    return this.agents.get(agentId);
  }

  /** Update fields on an existing agent. */
  update(agentId: string, partial: Partial<Omit<AgentIdentity, 'agentId' | 'registeredAt'>>): void {
    const existing = this.agents.get(agentId);
    if (!existing) {
      throw new Error(`Agent ${agentId} not found`);
    }
    Object.assign(existing, partial);
  }

  /** List all registered agents. */
  listAll(): AgentIdentity[] {
    return [...this.agents.values()];
  }

  /** List agents by parent ID. */
  listByParent(parentId: string | null): AgentIdentity[] {
    return [...this.agents.values()].filter((a) => a.parentId === parentId);
  }

  /** List agents at a specific depth level. */
  listByDepth(depth: number): AgentIdentity[] {
    return [...this.agents.values()].filter((a) => a.depth === depth);
  }

  /** List peers — agents with the same parent. */
  listPeers(agentId: string): AgentIdentity[] {
    const agent = this.agents.get(agentId);
    if (!agent) return [];
    return this.listByParent(agent.parentId).filter((a) => a.agentId !== agentId);
  }

  /** Get the parent of an agent. */
  getSupervisor(agentId: string): AgentIdentity | undefined {
    const agent = this.agents.get(agentId);
    if (!agent || !agent.parentId) return undefined;
    return this.agents.get(agent.parentId);
  }

  /** List all subordinates (direct children) of an agent. */
  listSubordinates(agentId: string): AgentIdentity[] {
    return this.listByParent(agentId);
  }

  /** Get the full path from root to this agent. */
  getPath(agentId: string): AgentIdentity[] {
    const path: AgentIdentity[] = [];
    let current = this.agents.get(agentId);
    while (current) {
      path.unshift(current);
      current = current.parentId ? this.agents.get(current.parentId) : undefined;
    }
    return path;
  }

  /** Number of registered agents. */
  get size(): number {
    return this.agents.size;
  }

  /** Remove all agents. */
  clear(): void {
    this.agents.clear();
  }
}