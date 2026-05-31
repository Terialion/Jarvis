// ============================================================================
// Config Watcher — hot-reload config files without restart
// ============================================================================
//
// Watches user and project config files for changes and notifies listeners.
// Debounces rapid writes (e.g. editor save) with a 500ms window.

import { watch, type FSWatcher } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';

export type ConfigChangeType = 'user' | 'project' | 'mcp';

export interface ConfigChangeEvent {
  type: ConfigChangeType;
  path: string;
  content: string;
}

export type ConfigChangeListener = (event: ConfigChangeEvent) => void;

export class ConfigWatcher {
  private watchers: FSWatcher[] = [];
  private listeners: ConfigChangeListener[] = [];
  private debounceTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private lastContent = new Map<string, string>();

  constructor(
    private projectRoot: string = process.cwd(),
  ) {}

  /** Start watching config files. */
  start(): void {
    const home = process.env['HOME'] ?? process.env['USERPROFILE'] ?? '';

    // User config: ~/.jarvis/config.json
    const userConfigPath = join(home, '.jarvis', 'config.json');
    this.watchFile(userConfigPath, 'user');

    // User MCP config: ~/.jarvis/mcp_server_config.json
    const userMcpPath = join(home, '.jarvis', 'mcp_server_config.json');
    this.watchFile(userMcpPath, 'mcp');

    // Project config: .jarvis/config.json
    const projectConfigPath = join(this.projectRoot, '.jarvis', 'config.json');
    this.watchFile(projectConfigPath, 'user');

    // Project MCP config: .jarvis/mcp.json
    const projectMcpPath = join(this.projectRoot, '.jarvis', 'mcp.json');
    this.watchFile(projectMcpPath, 'mcp');
  }

  /** Register a listener for config changes. */
  onChange(listener: ConfigChangeListener): void {
    this.listeners.push(listener);
  }

  /** Stop watching all files. */
  stop(): void {
    for (const w of this.watchers) {
      try { w.close(); } catch {}
    }
    this.watchers = [];
    for (const timer of this.debounceTimers.values()) {
      clearTimeout(timer);
    }
    this.debounceTimers.clear();
  }

  private watchFile(filePath: string, type: ConfigChangeType): void {
    if (!existsSync(filePath)) return;

    try {
      const watcher = watch(filePath, { persistent: false }, (eventType) => {
        if (eventType === 'change') {
          this.debouncedRead(filePath, type);
        }
      });
      watcher.on('error', () => {
        // File may have been deleted — ignore
      });
      this.watchers.push(watcher);
    } catch {
      // File may not exist yet — ignore
    }
  }

  private debouncedRead(filePath: string, type: ConfigChangeType): void {
    const existing = this.debounceTimers.get(filePath);
    if (existing) clearTimeout(existing);

    this.debounceTimers.set(filePath, setTimeout(async () => {
      this.debounceTimers.delete(filePath);
      try {
        const content = await readFile(filePath, 'utf-8');
        // Skip if content hasn't actually changed
        if (this.lastContent.get(filePath) === content) return;
        this.lastContent.set(filePath, content);

        const event: ConfigChangeEvent = { type, path: filePath, content };
        for (const listener of this.listeners) {
          try { listener(event); } catch {}
        }
      } catch {
        // File may have been deleted — ignore
      }
    }, 500));
  }
}
