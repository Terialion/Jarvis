import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { MCPClient, StdioMCPTransport } from '@jarvis/mcp';
import { PluginRegistry } from '@jarvis/plugins';
import { SkillRegistry } from '@jarvis/skills';

function ensureSmokePlugin(projectRoot: string): string {
  const pluginRoot = join(projectRoot, '.jarvis', 'plugins', 'common-mcp-smoke');
  mkdirSync(join(pluginRoot, 'skills'), { recursive: true });
  mkdirSync(join(pluginRoot, 'mcp'), { recursive: true });

  writeFileSync(
    join(pluginRoot, 'plugin.json'),
    JSON.stringify(
      {
        name: 'common-mcp-smoke',
        version: '0.1.0',
        description: 'Smoke plugin for real MCP integration checks',
        skills: 'skills',
        mcpServers: 'mcp',
      },
      null,
      2,
    ),
    'utf8',
  );

  writeFileSync(
    join(pluginRoot, 'skills', 'SKILL.md'),
    [
      '---',
      'name: mcp-smoke-helper',
      'description: Helper skill for MCP smoke validation.',
      '---',
      '# MCP Smoke Helper',
      '',
      'Use MCP status and MCP tools to verify connectivity.',
    ].join('\n'),
    'utf8',
  );

  const mcpConfig = {
    servers: {
      filesystem: {
        command: 'pnpm',
        args: ['dlx', '@modelcontextprotocol/server-filesystem', projectRoot],
      },
      memory: {
        command: 'pnpm',
        args: ['dlx', '@modelcontextprotocol/server-memory'],
      },
    },
  };
  writeFileSync(join(pluginRoot, 'mcp', '.mcp.json'), JSON.stringify(mcpConfig, null, 2), 'utf8');
  return pluginRoot;
}

async function main(): Promise<void> {
  const projectRoot = resolve(process.cwd());
  const pluginRoot = ensureSmokePlugin(projectRoot);
  console.log(`[plugin] prepared: ${pluginRoot}`);

  const pluginRegistry = new PluginRegistry();
  pluginRegistry.loadAll({
    projectRoot,
    userPluginsDir: join(process.env['USERPROFILE'] ?? '', '.jarvis', 'plugins'),
  });

  const plugin = pluginRegistry.getPlugin('common-mcp-smoke');
  if (!plugin) {
    throw new Error('Plugin common-mcp-smoke was not discovered');
  }
  console.log(`[plugin] discovered: ${plugin.manifest.name}@${plugin.manifest.version}`);

  const skillRegistry = new SkillRegistry();
  skillRegistry.discover({
    extraDirs: [{ path: join(plugin.rootDir, 'skills'), source: 'plugin' }],
  });
  const hasSkill = Boolean(skillRegistry.get('mcp-smoke-helper'));
  console.log(`[plugin] skill loaded: ${hasSkill ? 'yes' : 'no'}`);

  const mcpConfigs = pluginRegistry.listMcpConfigs();
  const smokeConfig = mcpConfigs.find((cfg) => cfg.plugin === 'common-mcp-smoke');
  if (!smokeConfig) {
    throw new Error('Plugin mcp config not found');
  }
  const servers = (smokeConfig.config['servers'] as Record<string, { command: string; args?: string[] }>) ?? {};

  const client = new MCPClient();
  const connections = [];
  for (const [name, server] of Object.entries(servers)) {
    const transport = new StdioMCPTransport(server.command, server.args ?? [], projectRoot);
    const conn = await client.connect(transport);
    connections.push(conn);
    console.log(
      `[mcp] connected ${name}: server=${conn.serverInfo?.name ?? 'unknown'} tools=${conn.tools.length} resources=${conn.resources.length}`,
    );
  }

  const fsConn = connections.find((c) => (c.serverInfo?.name ?? '').includes('filesystem'));
  if (fsConn) {
    const res = await client.callTool(fsConn, 'list_allowed_directories', {});
    console.log(`[mcp] filesystem list_allowed_directories: ${JSON.stringify(res).slice(0, 180)}...`);
  }

  const memConn = connections.find((c) => (c.serverInfo?.name ?? '').includes('memory'));
  if (memConn) {
    const res = await client.callTool(memConn, 'read_graph', {});
    console.log(`[mcp] memory read_graph: ${JSON.stringify(res).slice(0, 180)}...`);
  }

  client.disconnectAll();
  console.log('[done] MCP + plugin smoke test passed');
}

main().catch((error) => {
  console.error('[error]', error instanceof Error ? error.message : String(error));
  process.exit(1);
});

