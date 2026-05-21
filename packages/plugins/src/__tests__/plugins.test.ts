import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { PluginRegistry } from '../registry.js';
import { PluginDiscovery } from '../discovery.js';
import { ComponentLoader } from '../loader.js';

// ============================================================================
// Helpers
// ============================================================================

let tmpDir: string;

function createPlugin(root: string, name: string, manifest: Record<string, unknown>) {
  const pluginDir = path.join(root, name);
  fs.mkdirSync(pluginDir, { recursive: true });
  fs.writeFileSync(
    path.join(pluginDir, 'plugin.json'),
    JSON.stringify(manifest, null, 2),
  );
  return pluginDir;
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-plugins-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

// ============================================================================
// PluginDiscovery
// ============================================================================

describe('PluginDiscovery', () => {
  it('discovers plugins from a directory', () => {
    createPlugin(tmpDir, 'test-plugin', {
      name: 'test-plugin',
      version: '1.0.0',
      description: 'A test plugin',
    });

    const discovery = new PluginDiscovery();
    const entries = discovery.discover({ userPluginsDir: tmpDir });

    expect(entries).toHaveLength(1);
    expect(entries[0].manifest.name).toBe('test-plugin');
    expect(entries[0].manifest.version).toBe('1.0.0');
    expect(entries[0].source).toBe('user');
  });

  it('discovers plugins in subdirectories (up to 3 levels)', () => {
    const nested = path.join(tmpDir, 'a', 'b', 'c');
    fs.mkdirSync(nested, { recursive: true });
    fs.writeFileSync(
      path.join(nested, 'plugin.json'),
      JSON.stringify({ name: 'deep-plugin', version: '2.0.0' }),
    );

    const discovery = new PluginDiscovery();
    const entries = discovery.discover({ userPluginsDir: tmpDir });

    expect(entries).toHaveLength(1);
    expect(entries[0].manifest.name).toBe('deep-plugin');
  });

  it('returns empty array for non-existent directory', () => {
    const discovery = new PluginDiscovery();
    const entries = discovery.discover({
      userPluginsDir: path.join(tmpDir, 'nope'),
    });
    expect(entries).toEqual([]);
  });

  it('skips invalid plugin.json', () => {
    const pluginDir = path.join(tmpDir, 'bad-plugin');
    fs.mkdirSync(pluginDir, { recursive: true });
    fs.writeFileSync(path.join(pluginDir, 'plugin.json'), 'not json');

    const discovery = new PluginDiscovery();
    const entries = discovery.discover({ userPluginsDir: tmpDir });
    expect(entries).toEqual([]);
  });

  it('deduplicates by name', () => {
    createPlugin(path.join(tmpDir, 'a'), 'my-plugin', {
      name: 'my-plugin',
      version: '1.0.0',
    });
    createPlugin(path.join(tmpDir, 'b'), 'my-plugin', {
      name: 'my-plugin',
      version: '2.0.0',
    });

    const discovery = new PluginDiscovery();
    const entries = discovery.discover({ userPluginsDir: tmpDir });
    expect(entries).toHaveLength(1);
  });

  it('caches results', () => {
    createPlugin(tmpDir, 'p1', { name: 'p1', version: '1.0.0' });

    const discovery = new PluginDiscovery();
    const first = discovery.discover({ userPluginsDir: tmpDir });

    // Add another plugin — shouldn't be discovered because of cache
    createPlugin(tmpDir, 'p2', { name: 'p2', version: '1.0.0' });
    const second = discovery.discover({ userPluginsDir: tmpDir });

    expect(second).toHaveLength(1); // cached, so p2 not seen
  });

  it('clearCache forces re-discovery', () => {
    const discovery = new PluginDiscovery();
    discovery.discover({ userPluginsDir: tmpDir });

    createPlugin(tmpDir, 'late', { name: 'late', version: '1.0.0' });
    discovery.clearCache();

    const entries = discovery.discover({ userPluginsDir: tmpDir });
    expect(entries).toHaveLength(1);
    expect(entries[0].manifest.name).toBe('late');
  });
});

// ============================================================================
// ComponentLoader — commands
// ============================================================================

describe('ComponentLoader', () => {
  it('loads commands from .md files with frontmatter', () => {
    const pluginDir = createPlugin(tmpDir, 'cmd-plugin', {
      name: 'cmd-plugin',
      version: '1.0.0',
      commands: 'commands',
    });

    const cmdDir = path.join(pluginDir, 'commands');
    fs.mkdirSync(cmdDir, { recursive: true });
    fs.writeFileSync(
      path.join(cmdDir, 'hello.md'),
      [
        '---',
        'name: hello',
        'description: Say hello',
        '---',
        '# Hello',
        'This is the hello command body.',
      ].join('\n'),
    );

    const loader = new ComponentLoader();
    const entry = {
      rootDir: pluginDir,
      manifest: {
        name: 'cmd-plugin',
        version: '1.0.0',
        commands: 'commands',
      },
      source: 'user' as const,
    };

    const commands = loader.loadCommands(entry);
    expect(commands).toHaveLength(1);
    expect(commands[0].name).toBe('hello');
    expect(commands[0].description).toBe('Say hello');
    expect(commands[0].source).toBe('cmd-plugin');
    expect(commands[0].body).toContain('# Hello');
  });

  it('returns empty array when commands dir does not exist', () => {
    const loader = new ComponentLoader();
    const entry = {
      rootDir: tmpDir,
      manifest: { name: 'x', version: '1.0.0' },
      source: 'user' as const,
    };
    expect(loader.loadCommands(entry)).toEqual([]);
  });

  it('skips .md files without name in frontmatter', () => {
    const pluginDir = createPlugin(tmpDir, 'bad-cmd', {
      name: 'bad-cmd',
      version: '1.0.0',
      commands: 'commands',
    });

    const cmdDir = path.join(pluginDir, 'commands');
    fs.mkdirSync(cmdDir, { recursive: true });
    fs.writeFileSync(path.join(cmdDir, 'noname.md'), 'just content, no frontmatter');

    const loader = new ComponentLoader();
    const entry = {
      rootDir: pluginDir,
      manifest: {
        name: 'bad-cmd',
        version: '1.0.0',
        commands: 'commands',
      },
      source: 'user' as const,
    };

    const commands = loader.loadCommands(entry);
    expect(commands).toEqual([]);
  });

  it('loads hooks.json from hooks directory', () => {
    const pluginDir = createPlugin(tmpDir, 'hook-plugin', {
      name: 'hook-plugin',
      version: '1.0.0',
      hooks: 'hooks',
    });

    const hooksDir = path.join(pluginDir, 'hooks');
    fs.mkdirSync(hooksDir, { recursive: true });
    fs.writeFileSync(
      path.join(hooksDir, 'hooks.json'),
      JSON.stringify([
        { name: 'pre-bash', stage: 'pre_tool_use', toolName: 'bash' },
      ]),
    );

    const loader = new ComponentLoader();
    const entry = {
      rootDir: pluginDir,
      manifest: {
        name: 'hook-plugin',
        version: '1.0.0',
        hooks: 'hooks',
      },
      source: 'user' as const,
    };

    const hooks = loader.loadHooks(entry);
    expect(hooks).toHaveLength(1);
    expect(hooks[0].name).toBe('pre-bash');
  });

  it('loadHooks returns empty when no hooks dir', () => {
    const loader = new ComponentLoader();
    expect(
      loader.loadHooks({
        rootDir: tmpDir,
        manifest: { name: 'x', version: '1.0.0' },
        source: 'user',
      }),
    ).toEqual([]);
  });

  it('loads MCP config from .mcp.json', () => {
    const pluginDir = createPlugin(tmpDir, 'mcp-plugin', {
      name: 'mcp-plugin',
      version: '1.0.0',
      mcpServers: 'mcp',
    });

    const mcpDir = path.join(pluginDir, 'mcp');
    fs.mkdirSync(mcpDir, { recursive: true });
    fs.writeFileSync(
      path.join(mcpDir, '.mcp.json'),
      JSON.stringify({ servers: { local: { command: 'node', args: ['server.js'] } } }),
    );

    const loader = new ComponentLoader();
    const entry = {
      rootDir: pluginDir,
      manifest: {
        name: 'mcp-plugin',
        version: '1.0.0',
        mcpServers: 'mcp',
      },
      source: 'user' as const,
    };

    const cfg = loader.loadMcpConfig(entry);
    expect(cfg).not.toBeNull();
    expect((cfg as Record<string, unknown>).servers).toBeDefined();
  });

  it('loadMcpConfig returns null when no mcp config file', () => {
    const loader = new ComponentLoader();
    expect(
      loader.loadMcpConfig({
        rootDir: tmpDir,
        manifest: { name: 'x', version: '1.0.0' },
        source: 'user',
      }),
    ).toBeNull();
  });
});

// ============================================================================
// PluginRegistry
// ============================================================================

describe('PluginRegistry', () => {
  it('loads plugins and exposes commands', () => {
    const pluginDir = createPlugin(tmpDir, 'my-plugin', {
      name: 'my-plugin',
      version: '1.0.0',
      commands: 'cmds',
    });

    const cmdDir = path.join(pluginDir, 'cmds');
    fs.mkdirSync(cmdDir, { recursive: true });
    fs.writeFileSync(
      path.join(cmdDir, 'greet.md'),
      '---\nname: greet\ndescription: A greeting\n---\nHello!',
    );

    const registry = new PluginRegistry();
    registry.loadAll({ userPluginsDir: tmpDir });

    expect(registry.size).toBe(1);
    expect(registry.getPlugin('my-plugin')).toBeDefined();

    const cmds = registry.listCommands();
    expect(cmds).toHaveLength(1);
    expect(cmds[0].name).toBe('greet');
  });

  it('loadAll is idempotent', () => {
    createPlugin(tmpDir, 'p1', { name: 'p1', version: '1.0.0' });

    const registry = new PluginRegistry();
    registry.loadAll({ userPluginsDir: tmpDir });
    registry.loadAll({ userPluginsDir: tmpDir });

    expect(registry.size).toBe(1); // not double-counted
  });

  it('reload clears and re-discovers', () => {
    const registry = new PluginRegistry();
    registry.loadAll({ userPluginsDir: tmpDir });
    expect(registry.size).toBe(0);

    registry.reload();
    createPlugin(tmpDir, 'late-plugin', { name: 'late-plugin', version: '1.0.0' });
    registry.loadAll({ userPluginsDir: tmpDir });
    expect(registry.size).toBe(1);
  });

  it('listSkillDirs returns plugin names with skills configured', () => {
    createPlugin(tmpDir, 'skill-plugin', {
      name: 'skill-plugin',
      version: '1.0.0',
      skills: 'my-skills',
    });

    const registry = new PluginRegistry();
    registry.loadAll({ userPluginsDir: tmpDir });

    expect(registry.listSkillDirs()).toEqual(['skill-plugin']);
  });

  it('listMcpConfigs returns MCP configs', () => {
    const pluginDir = createPlugin(tmpDir, 'mcp-p', {
      name: 'mcp-p',
      version: '1.0.0',
      mcpServers: 'mcp',
    });

    const mcpDir = path.join(pluginDir, 'mcp');
    fs.mkdirSync(mcpDir, { recursive: true });
    fs.writeFileSync(path.join(mcpDir, '.mcp.json'), JSON.stringify({ key: 'val' }));

    const registry = new PluginRegistry();
    registry.loadAll({ userPluginsDir: tmpDir });

    const cfgs = registry.listMcpConfigs();
    expect(cfgs).toHaveLength(1);
    expect(cfgs[0].plugin).toBe('mcp-p');
  });

  it('listHookConfigs returns hook configs', () => {
    const pluginDir = createPlugin(tmpDir, 'hook-p', {
      name: 'hook-p',
      version: '1.0.0',
      hooks: 'hooks',
    });

    const hooksDir = path.join(pluginDir, 'hooks');
    fs.mkdirSync(hooksDir, { recursive: true });
    fs.writeFileSync(
      path.join(hooksDir, 'hooks.json'),
      JSON.stringify([{ name: 'h1', stage: 'pre_tool_use' }]),
    );

    const registry = new PluginRegistry();
    registry.loadAll({ userPluginsDir: tmpDir });

    const hooks = registry.listHookConfigs();
    expect(hooks).toHaveLength(1);
    expect(hooks[0].plugin).toBe('hook-p');
    expect(hooks[0].hooks).toHaveLength(1);
  });
});
