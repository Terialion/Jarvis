import { execSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { McpServerConfig } from '@jarvis/mcp';

export function getGitBranch(cwd: string): string | null {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', { cwd, encoding: 'utf-8', timeout: 3000 }).trim() || null;
  } catch {
    return null;
  }
}

export function discoverPluginSkillDirs(projectRoot: string): string[] {
  const roots = [
    join(projectRoot, '.jarvis', 'plugins'),
    join(process.env['USERPROFILE'] ?? '', '.jarvis', 'plugins'),
  ];
  const dirs: string[] = [];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    try {
      for (const entry of readdirSync(root, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const skillDir = join(root, entry.name, 'skills');
        if (existsSync(skillDir)) dirs.push(skillDir);
      }
    } catch { /* ignore */ }
  }
  return dirs;
}

export function discoverPluginMcpServers(projectRoot: string): Array<{ id: string; plugin: string; config: McpServerConfig }> {
  const result: Array<{ id: string; plugin: string; config: McpServerConfig }> = [];
  const pluginsDir = join(projectRoot, '.jarvis', 'plugins');
  if (!existsSync(pluginsDir)) return result;
  try {
    for (const entry of readdirSync(pluginsDir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const mcpPath = join(pluginsDir, entry.name, 'mcp.json');
      if (!existsSync(mcpPath)) continue;
      try {
        const raw = JSON.parse(readFileSync(mcpPath, 'utf-8'));
        const servers = raw?.mcpServers ?? raw?.servers ?? {};
        for (const [id, cfg] of Object.entries(servers)) {
          result.push({ id, plugin: entry.name, config: cfg as McpServerConfig });
        }
      } catch { /* ignore parse errors */ }
    }
  } catch { /* ignore */ }
  return result;
}

export function discoverUserMcpServers(projectRoot: string): Array<{ id: string; plugin?: string; config: McpServerConfig }> {
  const result: Array<{ id: string; plugin?: string; config: McpServerConfig }> = [];
  const userPath = join(process.env['USERPROFILE'] ?? '', '.jarvis', 'mcp.json');
  if (existsSync(userPath)) {
    try {
      const raw = JSON.parse(readFileSync(userPath, 'utf-8'));
      const servers = raw?.mcpServers ?? raw?.servers ?? {};
      for (const [id, cfg] of Object.entries(servers)) {
        result.push({ id, config: cfg as McpServerConfig });
      }
    } catch { /* ignore */ }
  }
  return result;
}

export function discoverProjectMcpServers(projectRoot: string): Array<{ id: string; plugin?: string; config: McpServerConfig }> {
  const result: Array<{ id: string; plugin?: string; config: McpServerConfig }> = [];
  const projectPath = join(projectRoot, '.jarvis', 'mcp.json');
  if (existsSync(projectPath)) {
    try {
      const raw = JSON.parse(readFileSync(projectPath, 'utf-8'));
      const servers = raw?.mcpServers ?? raw?.servers ?? {};
      for (const [id, cfg] of Object.entries(servers)) {
        result.push({ id, config: cfg as McpServerConfig });
      }
    } catch { /* ignore */ }
  }
  return result;
}
