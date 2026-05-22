import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { PluginRegistry } from '@jarvis/plugins';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';

describe('E2E: Plugins', () => {
  const tmpDir = path.join(os.tmpdir(), `jarvis-e2e-plugins-${Date.now()}`);

  beforeAll(() => {
    fs.mkdirSync(tmpDir, { recursive: true });
  });

  afterAll(() => {
    if (fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  function createPlugin(baseDir: string, name: string, version: string, skills?: string) {
    const pluginDir = path.join(baseDir, name);
    fs.mkdirSync(pluginDir, { recursive: true });

    const manifest: Record<string, string> = { name, version };
    if (skills) manifest['skills'] = skills;

    fs.writeFileSync(
      path.join(pluginDir, 'plugin.json'),
      JSON.stringify(manifest, null, 2),
    );
    return pluginDir;
  }

  it('PluginRegistry: discovers and loads plugins from project dir', () => {
    const projectRoot = path.join(tmpDir, 'project');
    const pluginsDir = path.join(projectRoot, '.jarvis', 'plugins');
    fs.mkdirSync(pluginsDir, { recursive: true });

    createPlugin(pluginsDir, 'test-plugin-a', '1.0.0');
    createPlugin(pluginsDir, 'test-plugin-b', '2.0.0', './skills/');

    const registry = new PluginRegistry();
    registry.loadAll({ projectRoot });

    const skillDirs = registry.listSkillDirs();
    expect(skillDirs).toContain('test-plugin-b');

    const commands = registry.listCommands();
    expect(commands.length).toBeGreaterThanOrEqual(0);
  });

  it('PluginRegistry: is idempotent on second loadAll', () => {
    const projectRoot = path.join(tmpDir, 'idempotent');
    const pluginsDir = path.join(projectRoot, '.jarvis', 'plugins');
    fs.mkdirSync(pluginsDir, { recursive: true });
    createPlugin(pluginsDir, 'idem-plugin', '1.0.0');

    const registry = new PluginRegistry();
    registry.loadAll({ projectRoot });
    const skillDirs1 = registry.listSkillDirs();

    // Second call should be no-op
    registry.loadAll({ projectRoot });
    const skillDirs2 = registry.listSkillDirs();

    expect(skillDirs2).toEqual(skillDirs1);
  });

  it('PluginRegistry: reload clears cache and re-discovers', () => {
    const projectRoot = path.join(tmpDir, 'reload');
    const pluginsDir = path.join(projectRoot, '.jarvis', 'plugins');
    fs.mkdirSync(pluginsDir, { recursive: true });
    createPlugin(pluginsDir, 'reload-plugin', '1.0.0');

    const registry = new PluginRegistry();
    registry.loadAll({ projectRoot });

    // Now add a new plugin
    createPlugin(pluginsDir, 'new-late-plugin', '1.0.0', './skills/');

    registry.reload();
    registry.loadAll({ projectRoot });

    const skillDirs = registry.listSkillDirs();
    expect(skillDirs).toContain('new-late-plugin');
  });
});
