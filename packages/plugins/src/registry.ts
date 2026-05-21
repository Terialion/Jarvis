// ============================================================================
// PluginRegistry — discover plugins and load their components
// ============================================================================

import { PluginDiscovery, type DiscoveryOptions } from './discovery.js';
import { ComponentLoader } from './loader.js';
import type { PluginEntry, PluginCommand } from './models.js';

export class PluginRegistry {
  private discovery: PluginDiscovery;
  private loader: ComponentLoader;
  private plugins: Map<string, PluginEntry> = new Map();
  private commands: PluginCommand[] = [];
  private loaded = false;

  constructor() {
    this.discovery = new PluginDiscovery();
    this.loader = new ComponentLoader();
  }

  /**
   * Discover all plugins and load their components.
   * Idempotent — subsequent calls are no-ops unless reload() is called.
   */
  loadAll(options: DiscoveryOptions = {}): void {
    if (this.loaded) return;

    const entries = this.discovery.discover(options);

    for (const entry of entries) {
      this.plugins.set(entry.manifest.name, entry);
      this.commands.push(...this.loader.loadCommands(entry));
    }

    this.loaded = true;
  }

  /** Force re-discovery and re-load on next loadAll(). */
  reload(): void {
    this.discovery.clearCache();
    this.plugins.clear();
    this.commands = [];
    this.loaded = false;
  }

  // ========================================================================
  // Query methods
  // ========================================================================

  /** List all slash-command definitions from all plugins. */
  listCommands(): PluginCommand[] {
    return this.commands;
  }

  /** List plugin names that provide skill directories. */
  listSkillDirs(): string[] {
    return [...this.plugins.values()]
      .filter((p) => p.manifest.skills)
      .map((p) => p.manifest.name);
  }

  /** Get all hook configs from loaded plugins. */
  listHookConfigs(): Array<{ plugin: string; hooks: Record<string, unknown>[] }> {
    const result: Array<{ plugin: string; hooks: Record<string, unknown>[] }> = [];
    for (const [, entry] of this.plugins) {
      const hooks = this.loader.loadHooks(entry);
      if (hooks.length > 0) {
        result.push({ plugin: entry.manifest.name, hooks });
      }
    }
    return result;
  }

  /** Get all MCP server configs from loaded plugins. */
  listMcpConfigs(): Array<{ plugin: string; config: Record<string, unknown> }> {
    const result: Array<{ plugin: string; config: Record<string, unknown> }> = [];
    for (const [, entry] of this.plugins) {
      const cfg = this.loader.loadMcpConfig(entry);
      if (cfg) {
        result.push({ plugin: entry.manifest.name, config: cfg });
      }
    }
    return result;
  }

  /** Get a specific plugin by name. */
  getPlugin(name: string): PluginEntry | undefined {
    return this.plugins.get(name);
  }

  /** Number of loaded plugins. */
  get size(): number {
    return this.plugins.size;
  }
}
