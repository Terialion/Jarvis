// ============================================================================
// AgentRegistry unit tests
// ============================================================================
// pnpm vitest packages/subagents/src/__tests__/registry.test.ts

import { describe, expect, it, beforeEach } from 'vitest';
import { AgentRegistry } from '../registry.js';
import type { AgentIdentity } from '../models.js';

function makeAgent(overrides: Partial<AgentIdentity> = {}): AgentIdentity {
  return {
    agentId: 'agent-1',
    role: 'developer',
    parentId: null,
    depth: 0,
    agentType: 'general',
    capabilities: ['bash', 'file_read'],
    registeredAt: Date.now(),
    ...overrides,
  };
}

describe('AgentRegistry', () => {
  let reg: AgentRegistry;

  beforeEach(() => {
    reg = new AgentRegistry();
  });

  describe('register', () => {
    it('registers an agent and makes it retrievable', () => {
      reg.register(makeAgent({ agentId: 'a1' }));
      expect(reg.get('a1')).toBeDefined();
      expect(reg.get('a1')!.role).toBe('developer');
    });

    it('throws on duplicate agentId', () => {
      reg.register(makeAgent({ agentId: 'dup' }));
      expect(() => reg.register(makeAgent({ agentId: 'dup' }))).toThrow('already registered');
    });

    it('stores a copy, not the original reference', () => {
      const orig = makeAgent({ agentId: 'a1' });
      reg.register(orig);
      orig.role = 'changed';
      expect(reg.get('a1')!.role).toBe('developer');
    });
  });

  describe('unregister', () => {
    it('removes an agent', () => {
      reg.register(makeAgent({ agentId: 'a1' }));
      expect(reg.unregister('a1')).toBe(true);
      expect(reg.get('a1')).toBeUndefined();
    });

    it('returns false for unknown agent', () => {
      expect(reg.unregister('nope')).toBe(false);
    });
  });

  describe('update', () => {
    it('mutates existing agent fields', () => {
      reg.register(makeAgent({ agentId: 'a1', role: 'developer' }));
      reg.update('a1', { role: 'qa' });
      expect(reg.get('a1')!.role).toBe('qa');
    });

    it('throws for unknown agent', () => {
      expect(() => reg.update('nope', { role: 'x' })).toThrow('not found');
    });
  });

  describe('listAll', () => {
    it('returns all registered agents', () => {
      reg.register(makeAgent({ agentId: 'a' }));
      reg.register(makeAgent({ agentId: 'b' }));
      expect(reg.listAll()).toHaveLength(2);
    });
  });

  describe('listByParent', () => {
    it('returns children of a specific parent', () => {
      reg.register(makeAgent({ agentId: 'super', parentId: null, depth: 0 }));
      reg.register(makeAgent({ agentId: 'child1', parentId: 'super', depth: 1 }));
      reg.register(makeAgent({ agentId: 'child2', parentId: 'super', depth: 1 }));
      reg.register(makeAgent({ agentId: 'orphan', parentId: null, depth: 0 }));

      const children = reg.listByParent('super');
      expect(children).toHaveLength(2);
      expect(children.map((c) => c.agentId).sort()).toEqual(['child1', 'child2']);
    });
  });

  describe('listByDepth', () => {
    it('returns agents at a specific depth', () => {
      reg.register(makeAgent({ agentId: 'root', depth: 0, parentId: null }));
      reg.register(makeAgent({ agentId: 'dev1', depth: 1, parentId: 'root' }));
      reg.register(makeAgent({ agentId: 'dev2', depth: 1, parentId: 'root' }));
      reg.register(makeAgent({ agentId: 'sub1', depth: 2, parentId: 'dev1' }));

      expect(reg.listByDepth(0)).toHaveLength(1);
      expect(reg.listByDepth(1)).toHaveLength(2);
      expect(reg.listByDepth(2)).toHaveLength(1);
    });
  });

  describe('listPeers', () => {
    it('returns siblings (same parent, excluding self)', () => {
      reg.register(makeAgent({ agentId: 'super', parentId: null, depth: 0 }));
      reg.register(makeAgent({ agentId: 'dev1', parentId: 'super', depth: 1 }));
      reg.register(makeAgent({ agentId: 'dev2', parentId: 'super', depth: 1 }));
      reg.register(makeAgent({ agentId: 'qa1', parentId: 'super', depth: 1 }));

      const peers = reg.listPeers('dev1');
      expect(peers).toHaveLength(2);
      expect(peers.map((p) => p.agentId).sort()).toEqual(['dev2', 'qa1']);
    });

    it('returns empty for agents with no parent', () => {
      reg.register(makeAgent({ agentId: 'root', parentId: null, depth: 0 }));
      expect(reg.listPeers('root')).toEqual([]);
    });

    it('returns empty for unknown agent', () => {
      expect(reg.listPeers('nope')).toEqual([]);
    });
  });

  describe('getSupervisor', () => {
    it('returns the parent agent', () => {
      reg.register(makeAgent({ agentId: 'boss', parentId: null, depth: 0 }));
      reg.register(makeAgent({ agentId: 'worker', parentId: 'boss', depth: 1 }));

      const sup = reg.getSupervisor('worker');
      expect(sup).toBeDefined();
      expect(sup!.agentId).toBe('boss');
    });

    it('returns undefined for root agents', () => {
      reg.register(makeAgent({ agentId: 'root', parentId: null, depth: 0 }));
      expect(reg.getSupervisor('root')).toBeUndefined();
    });
  });

  describe('listSubordinates', () => {
    it('returns direct children', () => {
      reg.register(makeAgent({ agentId: 'super', depth: 0, parentId: null }));
      reg.register(makeAgent({ agentId: 'c1', depth: 1, parentId: 'super' }));
      reg.register(makeAgent({ agentId: 'c2', depth: 1, parentId: 'super' }));
      reg.register(makeAgent({ agentId: 'gc1', depth: 2, parentId: 'c1' }));

      const subs = reg.listSubordinates('super');
      expect(subs).toHaveLength(2);
      expect(subs.map((s) => s.agentId).sort()).toEqual(['c1', 'c2']);
    });
  });

  describe('getPath', () => {
    it('returns the full path from root', () => {
      reg.register(makeAgent({ agentId: 'root', depth: 0, parentId: null }));
      reg.register(makeAgent({ agentId: 'dept', depth: 1, parentId: 'root' }));
      reg.register(makeAgent({ agentId: 'dev', depth: 2, parentId: 'dept' }));

      const path = reg.getPath('dev');
      expect(path.map((a) => a.agentId)).toEqual(['root', 'dept', 'dev']);
    });

    it('returns single-element array for root agent', () => {
      reg.register(makeAgent({ agentId: 'root', depth: 0, parentId: null }));
      const path = reg.getPath('root');
      expect(path.map((a) => a.agentId)).toEqual(['root']);
    });
  });

  describe('size and clear', () => {
    it('tracks count and clears', () => {
      expect(reg.size).toBe(0);
      reg.register(makeAgent({ agentId: 'a' }));
      reg.register(makeAgent({ agentId: 'b' }));
      expect(reg.size).toBe(2);
      reg.clear();
      expect(reg.size).toBe(0);
      expect(reg.listAll()).toEqual([]);
    });
  });
});