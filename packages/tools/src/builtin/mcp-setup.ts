import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import type { ToolEntry } from '../registry.js';

const FILESYSTEM_PKG = '@modelcontextprotocol/server-filesystem';

export const mcpBootstrapSchema = {
  type: 'function',
  function: {
    name: 'mcp_bootstrap',
    description: 'Install and configure a commonly used MCP server automatically (currently filesystem).',
    parameters: {
      type: 'object',
      properties: {
        server: {
          type: 'string',
          enum: ['filesystem'],
          description: 'MCP server preset to install/configure.',
        },
        roots: {
          type: 'array',
          items: { type: 'string' },
          description: 'Allowed root directories for filesystem MCP. Defaults to current working directory.',
        },
      },
      required: ['server'],
    },
  },
} as const;

type McpServerConfig = {
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
};

type McpConfigFile = {
  mcpServers?: Record<string, McpServerConfig>;
  servers?: Record<string, McpServerConfig>;
};

function ensureFilesystemServerInstalled(): { installed: boolean; installCommand?: string } {
  try {
    execSync(`npm ls -g ${FILESYSTEM_PKG} --depth=0`, { stdio: 'ignore' });
    return { installed: true };
  } catch {
    const cmd = `npm install -g ${FILESYSTEM_PKG}`;
    execSync(cmd, { stdio: 'ignore' });
    return { installed: true, installCommand: cmd };
  }
}

function upsertFilesystemConfig(roots: string[]): { configPath: string; serverConfig: McpServerConfig } {
  const jarvisDir = join(homedir(), '.jarvis');
  if (!existsSync(jarvisDir)) {
    mkdirSync(jarvisDir, { recursive: true });
  }

  const configPath = join(jarvisDir, 'mcp_server_config.json');
  let config: McpConfigFile = {};
  if (existsSync(configPath)) {
    try {
      config = JSON.parse(readFileSync(configPath, 'utf8')) as McpConfigFile;
    } catch {
      config = {};
    }
  }

  const normalizedRoots = roots.length > 0 ? roots : [process.cwd()];
  const serverConfig: McpServerConfig = {
    command: 'npx',
    args: ['-y', FILESYSTEM_PKG, ...normalizedRoots],
    cwd: process.cwd(),
  };

  const currentServers = config.mcpServers ?? config.servers ?? {};
  const next: McpConfigFile = {
    ...config,
    mcpServers: {
      ...currentServers,
      filesystem: serverConfig,
    },
  };
  delete next.servers;

  writeFileSync(configPath, `${JSON.stringify(next, null, 2)}\n`, 'utf8');
  return { configPath, serverConfig };
}

export const mcpBootstrapTool: ToolEntry = {
  name: 'mcp_bootstrap',
  toolset: 'mcp',
  description: 'Bootstrap MCP by installing/configuring common servers.',
  schema: mcpBootstrapSchema,
  isAsync: false,
  handler: (args) => {
    const server = String(args.server ?? '').trim().toLowerCase();
    if (server !== 'filesystem') {
      return JSON.stringify({
        ok: false,
        error: 'Only server=filesystem is supported right now.',
      });
    }

    const roots = Array.isArray(args.roots)
      ? args.roots.map((value) => String(value).trim()).filter(Boolean)
      : [];

    const install = ensureFilesystemServerInstalled();
    const config = upsertFilesystemConfig(roots);

    return JSON.stringify({
      ok: true,
      server: 'filesystem',
      package: FILESYSTEM_PKG,
      installed: install.installed,
      installCommand: install.installCommand,
      configPath: config.configPath,
      config: config.serverConfig,
      roots: roots.length > 0 ? roots : [process.cwd()],
      nextStep: 'Restart Jarvis session or run mcp_status/list_mcp_resources in a fresh turn.',
    });
  },
};

