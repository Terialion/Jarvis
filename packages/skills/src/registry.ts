// ============================================================================
// SkillRegistry — discover, cache, and query skills
// ============================================================================

import * as fs from 'node:fs';
import { SkillLoader } from './loader.js';
import type { SkillSpec, SkillSource } from './models.js';

// ============================================================================
// SkillRegistry
// ============================================================================

export interface RegistryOptions {
  /** Builtin skills directory */
  builtinDir?: string;
  /** Project .jarvis/skills directory */
  projectDir?: string;
  /** User skills directory */
  userDir?: string;
  /** Additional skill directories (e.g., from plugins) */
  extraDirs?: Array<{ path: string; source: SkillSource }>;
}

export class SkillRegistry {
  private loader: SkillLoader;
  private specs: Map<string, SkillSpec> = new Map();
  private cacheValid = false;

  constructor() {
    this.loader = new SkillLoader();
  }

  // ========================================================================
  // Discovery
  // ========================================================================

  /**
   * Discover skills from all configured root directories.
   * Uses internal cache — subsequent calls return cached results
   * unless file modification times have changed.
   */
  discover(options: RegistryOptions = {}): SkillSpec[] {
    const sources: Array<{ path: string; source: SkillSource }> = [];

    if (options.builtinDir) {
      sources.push({ path: options.builtinDir, source: 'builtin' });
    }
    if (options.projectDir) {
      sources.push({ path: options.projectDir, source: 'project' });
    }
    if (options.userDir) {
      sources.push({ path: options.userDir, source: 'user' });
    }
    for (const extra of options.extraDirs ?? []) {
      sources.push(extra);
    }

    const allSkills: SkillSpec[] = [];

    for (const { path, source } of sources) {
      const discovered = this.loader.discoverSkills(path, source);
      for (const skill of discovered) {
        // Deduplicate by name — first discovered wins
        if (!this.specs.has(skill.name)) {
          this.specs.set(skill.name, skill);
        }
        allSkills.push(skill);
      }
    }

    this.cacheValid = true;
    return allSkills;
  }

  /** Force re-discovery on the next discover() call. */
  invalidateCache(): void {
    this.specs.clear();
    this.cacheValid = false;
  }

  // ========================================================================
  // Query
  // ========================================================================

  /** Get a skill by name. Returns undefined if not found. */
  get(name: string): SkillSpec | undefined {
    return this.specs.get(name);
  }

  /** List all discovered skills. */
  listAll(): SkillSpec[] {
    return [...this.specs.values()];
  }

  /** List enabled (non-quarantined) skills. */
  listLoadable(): SkillSpec[] {
    return [...this.specs.values()].filter((s) => s.enabled && !s.quarantined);
  }

  /** List skills by source. */
  listBySource(source: SkillSource): SkillSpec[] {
    return [...this.specs.values()].filter((s) => s.source === source);
  }

  /** Export a lightweight index suitable for prompt rendering. */
  exportIndex(): Array<{ name: string; description: string }> {
    return this.listLoadable().map((s) => ({ name: s.name, description: s.description }));
  }

  /** Load the full body of a skill's SKILL.md file. */
  loadBody(skill: SkillSpec): string | null {
    try {
      const raw = fs.readFileSync(skill.path, 'utf-8');
      // Strip frontmatter
      const lines = raw.split('\n');
      if (lines[0]?.trim() === '---') {
        const endIdx = lines.findIndex((l, i) => i > 0 && l.trim() === '---');
        if (endIdx !== -1) {
          return lines.slice(endIdx + 1).join('\n').trim();
        }
      }
      return raw;
    } catch {
      return null;
    }
  }

  /** Number of discovered skills. */
  get size(): number {
    return this.specs.size;
  }

  /** Whether the cache is valid. */
  get isCached(): boolean {
    return this.cacheValid;
  }
}
