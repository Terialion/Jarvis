// ============================================================================
// ComponentLoader — load components from discovered plugins
// ============================================================================

import * as fs from 'node:fs';
import * as path from 'node:path';
import type { PluginEntry, PluginCommand } from './models.js';

export class ComponentLoader {
  /**
   * Load slash-command definitions from .md files in a plugin's commands directory.
   * Each .md file must have YAML frontmatter with `name` and `description` fields.
   */
  loadCommands(entry: PluginEntry): PluginCommand[] {
    const commands: PluginCommand[] = [];

    if (!entry.manifest.commands) return commands;

    const cmdDir = path.join(entry.rootDir, entry.manifest.commands);
    if (!fs.existsSync(cmdDir)) return commands;

    let files: fs.Dirent[];
    try {
      files = fs.readdirSync(cmdDir, { withFileTypes: true });
    } catch {
      return commands;
    }

    for (const f of files) {
      if (!f.isFile() || !f.name.endsWith('.md')) continue;

      const filePath = path.join(cmdDir, f.name);
      const raw = fs.readFileSync(filePath, 'utf-8');

      // Parse YAML frontmatter (between --- delimiters)
      const parsed = this._parseFrontmatter(raw);

      if (parsed.name) {
        commands.push({
          name: parsed.name,
          description: parsed.description ?? '',
          source: entry.manifest.name,
          body: parsed.body ?? raw,
        });
      }
    }

    return commands;
  }

  /**
   * Load hook configurations from hooks.json in a plugin's hooks directory.
   */
  loadHooks(entry: PluginEntry): Record<string, unknown>[] {
    if (!entry.manifest.hooks) return [];

    const hooksPath = path.join(entry.rootDir, entry.manifest.hooks, 'hooks.json');
    if (!fs.existsSync(hooksPath)) return [];

    try {
      const raw = fs.readFileSync(hooksPath, 'utf-8');
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : (parsed.hooks ?? []);
    } catch {
      return [];
    }
  }

  /**
   * Load MCP server config from a plugin's mcpServers directory.
   */
  loadMcpConfig(entry: PluginEntry): Record<string, unknown> | null {
    if (!entry.manifest.mcpServers) return null;

    const mcpPath = path.join(entry.rootDir, entry.manifest.mcpServers, '.mcp.json');
    if (!fs.existsSync(mcpPath)) return null;

    try {
      return JSON.parse(fs.readFileSync(mcpPath, 'utf-8'));
    } catch {
      return null;
    }
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private _parseFrontmatter(
    raw: string,
  ): { name?: string; description?: string; body?: string } {
    const lines = raw.split('\n');
    if (lines[0]?.trim() !== '---') return {};

    const endIdx = lines.findIndex((l, i) => i > 0 && l.trim() === '---');
    if (endIdx === -1) return {};

    const fmLines = lines.slice(1, endIdx);
    const fm: Record<string, string> = {};

    let currentKey = '';
    for (const line of fmLines) {
      const match = line.match(/^(\w[\w\s]*?):\s*(.*)$/);
      if (match) {
        currentKey = match[1].trim();
        fm[currentKey] = match[2].trim();
      } else if (currentKey) {
        fm[currentKey] += '\n' + line;
      }
    }

    return {
      name: fm['name'],
      description: fm['description'],
      body: lines.slice(endIdx + 1).join('\n').trim(),
    };
  }
}
