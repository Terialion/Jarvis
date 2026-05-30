// ============================================================================
// PluginDiscovery — scan filesystem for plugin manifests
// ============================================================================

import * as fs from 'node:fs';
import * as path from 'node:path';
import type { PluginManifest, PluginEntry } from './models.js';

export interface DiscoveryOptions {
  /** Project root for project-scoped plugins */
  projectRoot?: string;
  /** User plugins directory */
  userPluginsDir?: string;
  /** Additional directories from JARVIS_PLUGIN_DIRS env var */
  extraDirs?: string[];
}

export class PluginDiscovery {
  private cache: PluginEntry[] | null = null;

  /**
   * Discover plugins across project, user, and system scopes.
   * Searches up to 3 directory levels deep for plugin.json manifests.
   */
  discover(options: DiscoveryOptions = {}): PluginEntry[] {
    if (this.cache) return this.cache;

    const entries: PluginEntry[] = [];

    // Project scope: .jarvis/plugins/ in project root
    if (options.projectRoot) {
      const projectPlugins = path.join(options.projectRoot, '.jarvis', 'plugins');
      this._scanDir(projectPlugins, 'project', entries);
    }

    // User scope
    if (options.userPluginsDir) {
      this._scanDir(options.userPluginsDir, 'user', entries);
    }

    // Extra dirs (from env)
    for (const dir of options.extraDirs ?? []) {
      this._scanDir(dir, 'user', entries);
    }

    this.cache = entries;
    return entries;
  }

  /** Clear the internal cache so next discover() re-scans. */
  clearCache(): void {
    this.cache = null;
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private _scanDir(
    dir: string,
    source: PluginEntry['source'],
    entries: PluginEntry[],
    depth = 0,
  ): void {
    if (depth > 3) return;
    if (!fs.existsSync(dir)) return;

    let dirents: fs.Dirent[];
    try {
      dirents = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const d of dirents) {
      if (!d.isDirectory()) continue;
      const full = path.join(dir, d.name);

      // Check for plugin.json directly in this directory
      const manifestPath = path.join(full, 'plugin.json');
      if (fs.existsSync(manifestPath)) {
        try {
          const raw = fs.readFileSync(manifestPath, 'utf-8');
          const manifest: PluginManifest = JSON.parse(raw);
          if (manifest.name) {
            entries.push({ rootDir: full, manifest, source });
          }
        } catch {
          // Invalid JSON — skip
        }
      }

      // Recurse into subdirectories
      this._scanDir(full, source, entries, depth + 1);
    }
  }
}
