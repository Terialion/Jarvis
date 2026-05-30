import { execSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import type { ToolEntry } from '../registry.js';

type PluginManifest = {
  name: string;
  version: string;
  enabled?: boolean;
  description?: string;
  mcpServers?: string;
  skills?: string;
  commands?: string;
  hooks?: string;
};

type McpServerConfig = {
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
};

type McpConfigFile = {
  servers?: Record<string, McpServerConfig>;
};

type PluginBootstrapSource = 'npm' | 'github' | 'local';

type PluginMarketEntry = {
  pluginName: string;
  source: PluginBootstrapSource;
  server?: string;
  npmPackage?: string;
  githubRepo?: string;
  localPath?: string;
  pluginDir: string;
  updatedAt: string;
};

type PluginMarketIndex = {
  version: 1;
  entries: PluginMarketEntry[];
};

const PRESET_PACKAGES: Record<string, string> = {
  filesystem: '@modelcontextprotocol/server-filesystem',
  memory: '@modelcontextprotocol/server-memory',
};

const PRESET_CATALOG: Array<{
  server: string;
  defaultPluginName: string;
  npmPackage: string;
  source: 'npm';
  notes: string;
}> = [
  {
    server: 'filesystem',
    defaultPluginName: 'mcp-filesystem',
    npmPackage: '@modelcontextprotocol/server-filesystem',
    source: 'npm',
    notes: 'Expose local directories as MCP resources/tools.',
  },
  {
    server: 'memory',
    defaultPluginName: 'mcp-memory',
    npmPackage: '@modelcontextprotocol/server-memory',
    source: 'npm',
    notes: 'In-memory state MCP server for quick prototyping.',
  },
];

export const pluginBootstrapSchema = {
  type: 'function',
  function: {
    name: 'plugin_bootstrap',
    description: 'Install and configure plugin sources (npm/github/local), plus maintain plugin market index.',
    parameters: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['bootstrap', 'list_catalog', 'list_index'],
          description: 'bootstrap (default), list_catalog, or list_index.',
        },
        source: {
          type: 'string',
          enum: ['npm', 'github', 'local'],
          description: 'Plugin source type. Defaults to npm.',
        },
        pluginName: {
          type: 'string',
          description: 'Plugin directory/manifest name to create or update.',
        },
        server: {
          type: 'string',
          description: 'MCP server preset, e.g. filesystem or memory.',
        },
        serverId: {
          type: 'string',
          description: 'Server id in .mcp.json (default: server).',
        },
        npmPackage: {
          type: 'string',
          description: 'Optional npm package override.',
        },
        githubRepo: {
          type: 'string',
          description: 'GitHub repo URL or owner/repo (used when source=github).',
        },
        localPath: {
          type: 'string',
          description: 'Local plugin directory path (used when source=local).',
        },
        roots: {
          type: 'array',
          items: { type: 'string' },
          description: 'Optional root directories passed to MCP server command.',
        },
        force: {
          type: 'boolean',
          description: 'If true, allow bootstrap into a non-empty plugin target directory.',
        },
      },
      required: [],
    },
  },
} as const;

function ensureJarvisDir(): string {
  const dir = join(homedir(), '.jarvis');
  mkdirSync(dir, { recursive: true });
  return dir;
}

function getPluginMarketIndexPath(): string {
  return join(ensureJarvisDir(), 'plugin-market-index.json');
}

function loadMarketIndex(): PluginMarketIndex {
  const path = getPluginMarketIndexPath();
  if (!existsSync(path)) return { version: 1, entries: [] };
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as PluginMarketIndex;
    if (parsed.version === 1 && Array.isArray(parsed.entries)) return parsed;
  } catch {
    // ignore invalid file
  }
  return { version: 1, entries: [] };
}

function saveMarketIndex(index: PluginMarketIndex): void {
  const path = getPluginMarketIndexPath();
  writeFileSync(path, `${JSON.stringify(index, null, 2)}\n`, 'utf8');
}

function upsertMarketEntry(entry: PluginMarketEntry): PluginMarketIndex {
  const index = loadMarketIndex();
  const nextEntries = index.entries.filter((item) => item.pluginName !== entry.pluginName);
  nextEntries.push(entry);
  const next: PluginMarketIndex = { version: 1, entries: nextEntries };
  saveMarketIndex(next);
  return next;
}

function ensurePackageInstalled(pkg: string): { installed: boolean; installCommand?: string } {
  try {
    execSync(`npm ls -g ${pkg} --depth=0`, { stdio: 'ignore' });
    return { installed: true };
  } catch {
    const cmd = `npm install -g ${pkg}`;
    execSync(cmd, { stdio: 'ignore' });
    return { installed: true, installCommand: cmd };
  }
}

function ensurePluginDir(pluginName: string): string {
  const root = join(homedir(), '.jarvis', 'plugins', pluginName);
  mkdirSync(root, { recursive: true });
  return root;
}

function isDirectoryEmpty(dir: string): boolean {
  if (!existsSync(dir)) return true;
  return readdirSync(dir).length === 0;
}

function readManifest(path: string, fallbackName: string): PluginManifest {
  if (!existsSync(path)) {
    return {
      name: fallbackName,
      version: '0.1.0',
      enabled: true,
      mcpServers: 'mcp',
    };
  }
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as PluginManifest;
    return {
      name: parsed.name || fallbackName,
      version: parsed.version || '0.1.0',
      enabled: parsed.enabled !== false,
      description: parsed.description,
      mcpServers: parsed.mcpServers || 'mcp',
      skills: parsed.skills,
      commands: parsed.commands,
      hooks: parsed.hooks,
    };
  } catch {
    return {
      name: fallbackName,
      version: '0.1.0',
      enabled: true,
      mcpServers: 'mcp',
    };
  }
}

function normalizeGithubRepo(input: string): string {
  const raw = input.trim();
  if (!raw) return raw;
  if (raw.startsWith('http://') || raw.startsWith('https://') || raw.startsWith('git@')) return raw;
  return `https://github.com/${raw}.git`;
}

function bootstrapFromGithub(pluginDir: string, githubRepo: string, force: boolean): { cloneCommand: string } {
  if (!force && !isDirectoryEmpty(pluginDir)) {
    throw new Error(`Plugin directory is not empty: ${pluginDir}. Pass force=true to reuse it.`);
  }
  const repo = normalizeGithubRepo(githubRepo);
  const cloneCommand = `git clone --depth=1 "${repo}" "${pluginDir}"`;
  execSync(cloneCommand, { stdio: 'ignore' });
  return { cloneCommand };
}

function bootstrapFromLocal(pluginDir: string, localPath: string, force: boolean): void {
  if (!existsSync(localPath)) {
    throw new Error(`Local plugin path does not exist: ${localPath}`);
  }
  if (!force && !isDirectoryEmpty(pluginDir)) {
    throw new Error(`Plugin directory is not empty: ${pluginDir}. Pass force=true to reuse it.`);
  }
  cpSync(localPath, pluginDir, { recursive: true, force: true });
}

function upsertMcpServer(
  pluginDir: string,
  manifest: PluginManifest,
  serverId: string,
  npmPackage: string,
  roots: string[],
): { mcpPath: string; serverConfig: McpServerConfig } {
  const mcpDir = join(pluginDir, manifest.mcpServers || 'mcp');
  mkdirSync(mcpDir, { recursive: true });
  const mcpPath = join(mcpDir, '.mcp.json');
  let mcpConfig: McpConfigFile = {};
  if (existsSync(mcpPath)) {
    try {
      mcpConfig = JSON.parse(readFileSync(mcpPath, 'utf8')) as McpConfigFile;
    } catch {
      mcpConfig = {};
    }
  }

  const serverConfig: McpServerConfig = {
    command: 'npx',
    args: ['-y', npmPackage, ...roots],
    cwd: process.cwd(),
  };
  const serverMap = mcpConfig.servers ?? {};
  serverMap[serverId] = serverConfig;
  mcpConfig.servers = serverMap;
  writeFileSync(mcpPath, `${JSON.stringify(mcpConfig, null, 2)}\n`, 'utf8');
  return { mcpPath, serverConfig };
}

export const pluginBootstrapTool: ToolEntry = {
  name: 'plugin_bootstrap',
  toolset: 'plugin',
  description: 'Install/enable plugin wrappers and MCP server wiring automatically.',
  schema: pluginBootstrapSchema,
  isAsync: false,
  handler: (args) => {
    const action = String(args.action ?? 'bootstrap').trim().toLowerCase();
    if (action === 'list_catalog') {
      return JSON.stringify({
        ok: true,
        catalog: PRESET_CATALOG,
        indexPath: getPluginMarketIndexPath(),
      });
    }
    if (action === 'list_index') {
      const index = loadMarketIndex();
      return JSON.stringify({
        ok: true,
        indexPath: getPluginMarketIndexPath(),
        count: index.entries.length,
        entries: index.entries,
      });
    }

    const source = String(args.source ?? 'npm').trim().toLowerCase() as PluginBootstrapSource;
    if (!['npm', 'github', 'local'].includes(source)) {
      return JSON.stringify({ ok: false, error: 'source must be one of: npm, github, local' });
    }

    const server = String(args.server ?? '').trim().toLowerCase();
    const defaultsFromServer = PRESET_CATALOG.find((item) => item.server === server);
    const pluginName = String(args.pluginName ?? defaultsFromServer?.defaultPluginName ?? '').trim();
    const serverId = String(args.serverId ?? server).trim();
    const force = args.force === true;

    if (!pluginName) {
      return JSON.stringify({ ok: false, error: 'pluginName is required (or pass a known server preset).' });
    }

    const pluginDir = ensurePluginDir(pluginName);
    let installCommand: string | undefined;
    let cloneCommand: string | undefined;
    let npmPackage: string | undefined;
    const roots = Array.isArray(args.roots)
      ? args.roots.map((v) => String(v).trim()).filter(Boolean)
      : [];

    try {
      if (source === 'npm') {
        const presetPackage = PRESET_PACKAGES[server];
        npmPackage = String(args.npmPackage ?? presetPackage ?? '').trim();
        if (!npmPackage) {
          return JSON.stringify({
            ok: false,
            error: `Unknown preset "${server}". Pass npmPackage explicitly for source=npm.`,
          });
        }
        const install = ensurePackageInstalled(npmPackage);
        installCommand = install.installCommand;
      } else if (source === 'github') {
        const githubRepo = String(args.githubRepo ?? '').trim();
        if (!githubRepo) {
          return JSON.stringify({ ok: false, error: 'githubRepo is required when source=github.' });
        }
        const result = bootstrapFromGithub(pluginDir, githubRepo, force);
        cloneCommand = result.cloneCommand;
      } else if (source === 'local') {
        const localPath = String(args.localPath ?? '').trim();
        if (!localPath) {
          return JSON.stringify({ ok: false, error: 'localPath is required when source=local.' });
        }
        bootstrapFromLocal(pluginDir, localPath, force);
      }
    } catch (error) {
      return JSON.stringify({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }

    const manifestPath = join(pluginDir, 'plugin.json');
    const manifest = readManifest(manifestPath, pluginName);
    manifest.enabled = true;
    manifest.mcpServers = manifest.mcpServers || 'mcp';
    if (!manifest.description) {
      manifest.description = `Auto-bootstrapped plugin (${source})`;
    }
    writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');

    let mcpPath: string | undefined;
    let serverConfig: McpServerConfig | undefined;
    if (server && serverId) {
      const packageForMcp = npmPackage
        ?? String(args.npmPackage ?? PRESET_PACKAGES[server] ?? '').trim();
      if (packageForMcp) {
        const mcpResult = upsertMcpServer(pluginDir, manifest, serverId, packageForMcp, roots);
        mcpPath = mcpResult.mcpPath;
        serverConfig = mcpResult.serverConfig;
      }
    }

    const marketEntry: PluginMarketEntry = {
      pluginName,
      source,
      server: server || undefined,
      npmPackage,
      githubRepo: source === 'github' ? String(args.githubRepo ?? '').trim() : undefined,
      localPath: source === 'local' ? String(args.localPath ?? '').trim() : undefined,
      pluginDir,
      updatedAt: new Date().toISOString(),
    };
    const index = upsertMarketEntry(marketEntry);

    return JSON.stringify({
      ok: true,
      source,
      pluginName,
      pluginDir,
      manifestPath,
      mcpPath,
      serverId: serverId || undefined,
      server: server || undefined,
      npmPackage,
      installCommand,
      cloneCommand,
      serverConfig,
      indexPath: getPluginMarketIndexPath(),
      indexCount: index.entries.length,
      nextStep: 'Restart Jarvis session to reload plugin registry and reconnect MCP servers.',
      healthcheckHint: 'Run /mcp or call mcp_healthcheck after restart.',
    });
  },
};

