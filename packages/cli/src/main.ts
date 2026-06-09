#!/usr/bin/env node
// ============================================================================
// CLI main — argument parsing, agent bootstrap, and one-shot / interactive loop
// ============================================================================

import * as path from 'node:path';
import * as fs from 'node:fs';
import * as os from 'node:os';
import { parseArgs } from 'node:util';
import { LLMProvider, AgentLoop, AgentMailbox } from '@jarvis/agent';
import { ToolRegistry, allBuiltinTools, createToolRuntime, createSkillLoadTool, createSkillTool, createAgentTool, createListMcpResourcesTool, createReadMcpResourceTool, createMcpStatusTool, createMcpHealthcheckTool, createMcpToolEntries, webSearchTool, webFetchTool, createWebSearchTool, createWebFetchHandler, tryCreateTavilySearch, tryCreateTavilyFetch } from '@jarvis/tools';
import { HookRegistry } from '@jarvis/hooks';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import { SubagentPool, SubagentRunner } from '@jarvis/subagents';
import { MCPClient, connectMcpServers, type McpServerConfig } from '@jarvis/mcp';
import { PluginRegistry } from '@jarvis/plugins';
import { MarkdownMemoryStore } from '@jarvis/store';
import { createMemorySearchHandler, createMemoryGetHandler, createMemoryWriteHandler, createMemoryDeleteHandler } from '@jarvis/agent';
import { SlashCommandRegistry, registerBuiltinCommands } from './commands.js';
import type { CommandContext } from './commands.js';
import {
  getJarvisConfigPath,
  loadJarvisConfig,
  normalizeJarvisReasoningEffort,
  resolveJarvisConfigDefaults,
  type JarvisReasoningEffort,
  type JarvisConfig,
  type ProviderConfig,
  type SandboxSettings,
} from '@jarvis/shared';
import { findModel } from '@jarvis/agent';

// ============================================================================
// Types
// ============================================================================

export interface CLIOptions {
  model: string;
  apiKey?: string;
  baseURL?: string;
  reasoningEffort: JarvisReasoningEffort;
  maxTurns: number;
  systemPrompt?: string;
  oneShot?: string;
  fullscreen?: boolean;
  configure?: boolean;
}

export interface CLIContext {
  options: CLIOptions;
  provider: LLMProvider;
  mailbox: AgentMailbox;
  tools: ToolRegistry;
  hooks: HookRegistry;
  commands: SlashCommandRegistry;
  cmdContext: CommandContext;
  skills: SkillRegistry;
  /** Resolves when all MCP servers have finished connecting (or failed). */
  mcpReady: Promise<Array<{ id: string; state: string; toolCount?: number }>>;
}

// ============================================================================
// Provider resolution
// ============================================================================

/**
 * Resolve API credentials for a model by looking up its provider in the
 * config's `providers` map. Falls back to top-level api_key/base_url.
 */
export function resolveProviderForModel(
  modelName: string,
  config: JarvisConfig,
): ProviderConfig {
  const catalogEntry = findModel(modelName);
  const providerName = catalogEntry?.provider;

  // Try providers map first
  if (providerName && config.providers?.[providerName]) {
    const p = config.providers[providerName];
    return {
      api_key: p.api_key ?? config.api_key ?? process.env['JARVIS_LLM_API_KEY'] ?? process.env['OPENAI_API_KEY'],
      base_url: p.base_url ?? config.base_url ?? process.env['JARVIS_LLM_BASE_URL'] ?? process.env['JARVIS_BASE_URL'],
    };
  }

  // Fallback to flat config / env
  return {
    api_key: config.api_key ?? process.env['JARVIS_LLM_API_KEY'] ?? process.env['OPENAI_API_KEY'],
    base_url: config.base_url ?? process.env['JARVIS_LLM_BASE_URL'] ?? process.env['JARVIS_BASE_URL'] ?? 'https://api.deepseek.com/v1',
  };
}

// ============================================================================
// Argument parsing
// ============================================================================

export function parseCLIArgs(argv: string[] = process.argv): CLIOptions {
  const userConfig = loadJarvisConfig();
  const resolvedDefaults = resolveJarvisConfigDefaults(userConfig);
  const activeModel = userConfig.active_model ?? userConfig.model ?? process.env['JARVIS_LLM_MODEL'] ?? process.env['JARVIS_MODEL'] ?? 'deepseek-v4-pro';
  const resolved = resolveProviderForModel(activeModel, userConfig);

  const { values } = parseArgs({
    args: argv,
    options: {
      model: {
        type: 'string',
        short: 'm',
        default: activeModel,
      },
      'api-key': {
        type: 'string',
        default: resolved.api_key,
      },
      'base-url': {
        type: 'string',
        default: resolved.base_url,
      },
      effort: {
        type: 'string',
        default: resolvedDefaults.reasoning_effort,
      },
      'max-turns': {
        type: 'string',
        default: String(userConfig.max_turns ?? 30),
      },
      'system-prompt': {
        type: 'string',
        default: userConfig.system_prompt,
      },
      prompt: {
        type: 'string',
        short: 'p',
      },
      help: {
        type: 'boolean',
        short: 'h',
        default: false,
      },
      configure: {
        type: 'boolean',
        default: false,
      },
      fullscreen: {
        type: 'boolean',
        short: 'f',
        default: false,
      },
    },
    allowPositionals: true,
  });

  return {
    model: values['model'] as string,
    apiKey: values['api-key'] as string | undefined,
    baseURL: values['base-url'] as string,
    reasoningEffort:
      normalizeJarvisReasoningEffort(values['effort'] as string | undefined) ?? resolvedDefaults.reasoning_effort,
    maxTurns: parseInt(values['max-turns'] as string, 10) || 30,
    systemPrompt: values['system-prompt'] as string | undefined,
    oneShot: values['prompt'] as string | undefined,
    fullscreen: values['fullscreen'] as boolean,
    configure: Boolean(values['configure']),
  };
}

// ============================================================================
// .env loading
// ============================================================================

/**
 * Load key=value pairs from a .env file into process.env.
 * Only sets variables that are not already present in process.env.
 * Skips comments (#) and empty lines.
 */
export function loadEnvFile(filePath: string): void {
  if (!fs.existsSync(filePath)) return;

  const raw = fs.readFileSync(filePath, 'utf-8');
  const lines = raw.replace(/\r/g, '').split('\n');

  for (const line of lines) {
    const trimmed = line.trim();
    // Skip comments and empty lines
    if (!trimmed || trimmed.startsWith('#')) continue;

    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;

    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();

    if (key && !(key in process.env)) {
      process.env[key] = value;
    }
  }
}

/**
 * Walk up from cwd to find the project root, then load .env.
 */
export function loadProjectEnv(): void {
  const root = findProjectRoot();
  const envPath = path.join(root, '.env');
  loadEnvFile(envPath);

  if (process.env['JARVIS_DEBUG']) {
    console.error('[env] Loaded .env from %s', envPath);
    console.error('[env] JARVIS_LLM_API_KEY=%s', process.env['JARVIS_LLM_API_KEY'] ? '***' : '(not set)');
    console.error('[env] JARVIS_LLM_BASE_URL=%s', process.env['JARVIS_LLM_BASE_URL'] ?? '(not set)');
    console.error('[env] JARVIS_LLM_MODEL=%s', process.env['JARVIS_LLM_MODEL'] ?? '(not set)');
  }
}

// ============================================================================
// Skill discovery
// ============================================================================

export function findProjectRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 10; i++) {
    if (
      fs.existsSync(path.join(dir, 'pnpm-workspace.yaml')) ||
      path.basename(dir).toLowerCase() === 'jarvis' ||
      dir === path.parse(dir).root
    ) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return process.cwd();
}

export function createSkillRegistry(projectRoot?: string): SkillRegistry {
  const registry = new SkillRegistry();
  const root = projectRoot ?? findProjectRoot();
  const builtinSkillsDir = path.join(root, 'skills');
  const projectSkillsDir = path.join(root, '.jarvis', 'skills');
  const userPluginsDir = path.join(os.homedir(), '.jarvis', 'plugins');
  const pluginRegistry = new PluginRegistry();
  pluginRegistry.loadAll({ projectRoot: root, userPluginsDir });
  for (const issue of pluginRegistry.listIssues()) {
    if (process.env['JARVIS_DEBUG']) {
      console.error(`[plugins] ${issue.level} ${issue.code}: ${issue.message}`);
    }
  }
  const pluginSkillExtraDirs = pluginRegistry
    .listSkillDirs()
    .map((pluginName) => pluginRegistry.getPlugin(pluginName))
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
    .map((entry) => ({
      path: path.join(entry.rootDir, entry.manifest.skills ?? 'skills'),
      source: 'plugin' as const,
    }));

  const skills = registry.discover({
    builtinDir: builtinSkillsDir,
    projectDir: projectSkillsDir,
    extraDirs: pluginSkillExtraDirs,
  });

  if (process.env['JARVIS_DEBUG']) {
    console.error('[skills] Discovered %d skill(s) from %s + %s', skills.length, builtinSkillsDir, projectSkillsDir);
    if (pluginSkillExtraDirs.length > 0) {
      console.error('[skills] Plugin skill dirs: %s', pluginSkillExtraDirs.map((d) => d.path).join(', '));
    }
    for (const s of skills) {
      console.error('[skills]   - %s (tags: %s)', s.name, s.tags?.join(', ') ?? 'none');
    }
  }

  return registry;
}

export function collectPluginMcpServers(projectRoot: string): Array<{ id: string; plugin: string; config: McpServerConfig }> {
  const userPluginsDir = path.join(os.homedir(), '.jarvis', 'plugins');
  const pluginRegistry = new PluginRegistry();
  pluginRegistry.loadAll({ projectRoot, userPluginsDir });
  const servers: Array<{ id: string; plugin: string; config: McpServerConfig }> = [];
  for (const cfg of pluginRegistry.listMcpConfigs()) {
    const serverMap = (cfg.config['servers'] ?? {}) as Record<string, McpServerConfig>;
    for (const [id, server] of Object.entries(serverMap)) {
      if (!server || typeof server.command !== 'string' || !server.command.trim()) continue;
      servers.push({
        id,
        plugin: cfg.plugin,
        config: {
          ...server,
          cwd: server.cwd ?? projectRoot,
        },
      });
    }
  }
  return servers;
}

export function collectUserMcpServers(projectRoot: string): Array<{ id: string; plugin?: string; config: McpServerConfig }> {
  const configPath = path.join(os.homedir(), '.jarvis', 'mcp_server_config.json');
  if (!fs.existsSync(configPath)) return [];
  try {
    const raw = JSON.parse(fs.readFileSync(configPath, 'utf8')) as {
      mcpServers?: Record<string, McpServerConfig>;
      servers?: Record<string, McpServerConfig>;
    };
    const serverMap = raw.mcpServers ?? raw.servers ?? {};
    const out: Array<{ id: string; plugin?: string; config: McpServerConfig }> = [];
    for (const [id, cfg] of Object.entries(serverMap)) {
      if (!cfg || typeof cfg.command !== 'string' || !cfg.command.trim()) continue;
      out.push({
        id,
        config: {
          ...cfg,
          cwd: cfg.cwd ?? projectRoot,
        },
      });
    }
    return out;
  } catch {
    return [];
  }
}

export function registerSkillCommands(
  commands: SlashCommandRegistry,
  skills: SkillRegistry,
): void {
  for (const skill of skills.listLoadable()) {
    // Prefer explicit slashCommand, fall back to skill name (CC/Codex convention)
    const cmdName = skill.slashCommand || skill.name;
    commands.register({
      name: cmdName,
      description: skill.description,
      usage: `/${cmdName}`,
      category: 'skills',
      execute: async (_args, _ctx) => {
        return `Skill "${skill.name}" activated. Your next message will be processed with this skill's instructions.`;
      },
    });
  }
}

// ============================================================================
// Web tool wiring
// ============================================================================

export function registerWebTools(tools: ToolRegistry): void {
  const tavilySearch = tryCreateTavilySearch();
  const tavilyFetch = tryCreateTavilyFetch();
  if (tavilySearch) { tools.register(createWebSearchTool(tavilySearch)); }
  else { tools.register(webSearchTool); }
  if (tavilyFetch) { tools.register({ ...webFetchTool, handler: createWebFetchHandler(tavilyFetch) }); }
  else { tools.register(webFetchTool); }
}

// ============================================================================
// Bootstrap
// ============================================================================

export function bootstrap(options: CLIOptions): CLIContext {
  const userConfig = loadJarvisConfig();

  // LLM Provider
  const provider = new LLMProvider({
    model: options.model,
    apiKey: options.apiKey,
    baseURL: options.baseURL,
    reasoningEffort: options.reasoningEffort,
    maxRetries: 3,
    timeout: 120_000,
  });

  // Tool registry — register all builtin tools
  const tools = new ToolRegistry();
  for (const tool of allBuiltinTools) {
    tools.register(tool);
  }
  registerWebTools(tools);

  // Memory search/get tools
  const memoryStore = new MarkdownMemoryStore();
  tools.register({
    name: 'memory_search',
    toolset: 'memory',
    description: 'Search persistent memory entries by keyword',
    isAsync: true,
    schema: {
      type: 'function',
      function: {
        name: 'memory_search',
        description: 'Search persistent memory entries by keyword',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'Search query' },
            maxResults: { type: 'number', description: 'Max results (default 5)' },
            memoryType: { type: 'string', description: 'Filter by type: user, project, feedback, reference' },
          },
          required: ['query'],
        },
      },
    },
    handler: (args: Record<string, unknown>) => createMemorySearchHandler(memoryStore)(args),
  });
  tools.register({
    name: 'memory_get',
    toolset: 'memory',
    description: 'Read a specific memory entry by name',
    isAsync: true,
    schema: {
      type: 'function',
      function: {
        name: 'memory_get',
        description: 'Read a specific memory entry by name',
        parameters: {
          type: 'object',
          properties: {
            name: { type: 'string', description: 'Memory entry name' },
          },
          required: ['name'],
        },
      },
    },
    handler: (args: Record<string, unknown>) => createMemoryGetHandler(memoryStore)(args),
  });
  tools.register({
    name: 'memory_write',
    toolset: 'memory',
    description: 'Save important information to persistent memory (user preferences, project facts, decisions, schedules)',
    isAsync: true,
    schema: {
      type: 'function',
      function: {
        name: 'memory_write',
        description: 'Save important information to persistent memory. Use this proactively when the user mentions preferences, schedules, ideas, corrections, or important facts.',
        parameters: {
          type: 'object',
          properties: {
            name: { type: 'string', description: 'Short kebab-case name for this memory (e.g., prefers-vim, deploy-friday, identity-timezone)' },
            description: { type: 'string', description: 'One-line summary of what this memory contains' },
            content: { type: 'string', description: 'The full memory content in markdown' },
            memoryType: { type: 'string', description: 'Category: user (identity, preferences, habits, schedule, ideas), project (facts, architecture, conventions), feedback (corrections), reference (external info)' },
            tags: { type: 'array', items: { type: 'string' }, description: 'Fine-grained tags: identity, preferences, habits, schedule, ideas, code-style, architecture, conventions, research' },
          },
          required: ['name', 'content'],
        },
      },
    },
    handler: (args: Record<string, unknown>) => createMemoryWriteHandler(memoryStore)(args),
  });
  tools.register({
    name: 'memory_delete',
    toolset: 'memory',
    description: 'Delete an outdated or conflicting memory entry',
    isAsync: true,
    schema: {
      type: 'function',
      function: {
        name: 'memory_delete',
        description: 'Delete a memory entry by name. Use when you find conflicting memories or when the user corrects outdated information.',
        parameters: {
          type: 'object',
          properties: {
            name: { type: 'string', description: 'Name of the memory entry to delete' },
            reason: { type: 'string', description: 'Why this memory is being deleted (for audit)' },
          },
          required: ['name'],
        },
      },
    },
    handler: (args: Record<string, unknown>) => createMemoryDeleteHandler(memoryStore)(args),
  });

  // Skills
  const skills = createSkillRegistry();

  // Register skill tools (load + direct invocation)
  tools.register(createSkillLoadTool(skills));
  tools.register(createSkillTool(skills));

  // MCP client — wire resource + dynamic tool exposure
  const mcpClient = new MCPClient();
  tools.register(createListMcpResourcesTool(mcpClient));
  tools.register(createReadMcpResourceTool(mcpClient));
  tools.register(createMcpStatusTool(mcpClient));
  tools.register(createMcpHealthcheckTool(mcpClient));
  const projectRoot = findProjectRoot();
  const mcpServers = [
    ...collectUserMcpServers(projectRoot),
    ...collectPluginMcpServers(projectRoot),
  ];
  const mcpReady = mcpServers.length > 0
    ? connectMcpServers(mcpClient, mcpServers).then((statuses) => {
        if (process.env['JARVIS_DEBUG']) {
          for (const status of statuses) {
            const detail = status.state === 'failed'
              ? `error=${status.error ?? 'unknown'}`
              : `server=${status.serverName ?? status.id} tools=${status.toolCount ?? 0} resources=${status.resourceCount ?? 0}`;
            console.error(`[mcp] ${status.state} ${status.plugin ? `${status.plugin}:` : ''}${status.id} ${detail}`);
          }
        }
        return statuses.map((s) => ({ id: s.id, state: s.state, toolCount: s.toolCount }));
      })
    : Promise.resolve([]);
  for (const mcpTool of createMcpToolEntries(mcpClient)) {
    tools.register(mcpTool);
  }

  // Subagent pool — wire Agent tool for subagent spawning
  const hooks = new HookRegistry();
  const mailbox = new AgentMailbox();
  const subagentPool = new SubagentPool();
  subagentPool.setParentMailbox(mailbox);
  const subagentRunner = new SubagentRunner({
    createAgentLoop: ({
      agentId,
      allowedTools,
      maxSteps,
      depth,
      mailbox,
      systemPrompt,
    }) => {
      const subTools = new ToolRegistry();
      for (const tool of allBuiltinTools) {
        if (!allowedTools || allowedTools.includes(tool.name)) {
          subTools.register(tool);
        }
      }
      subTools.register(createSkillLoadTool(skills));
      subTools.register(createSkillTool(skills));

      const subRuntime = createToolRuntime(subTools, { permissionMode: 'workspace_write' });
      return new AgentLoop({
        model: { model: options.model, reasoningEffort: options.reasoningEffort },
        maxTurns: maxSteps,
        maxSteps,
        systemPrompt,
        tools: subTools,
        toolRuntime: subRuntime,
        provider: new LLMProvider({
          model: options.model,
          apiKey: options.apiKey,
          baseURL: options.baseURL,
          reasoningEffort: options.reasoningEffort,
        }),
        skillRegistry: skills,
        skillExecutor: new SkillExecutor(skills),
        hooks,
        mailbox,
        permissionMode: 'workspace_write',
        projectRoot: process.cwd(),
      });
    },
  });
  subagentPool.setRunner((config, mailbox) => subagentRunner.run(config, mailbox));
  tools.register(createAgentTool(subagentPool));

  // Slash commands
  const commands = new SlashCommandRegistry();
  registerBuiltinCommands(commands);
  registerSkillCommands(commands, skills);

  const cmdContext: CommandContext = {
    cwd: process.cwd(),
    model: options.model,
    sessionId: undefined,
    setConfig: (key: string, value: string) => {
      if (key === 'model') {
        options.model = value;
        cmdContext.model = value;
        return value;
      }
      return '';
    },
  };

  return { options, provider, mailbox, tools, hooks, commands, cmdContext, skills, mcpReady };
}

// ============================================================================
// Print help
// ============================================================================

export function printHelp(): string {
  const configPath = getJarvisConfigPath();
  return [
    'Jarvis — AI coding assistant (TypeScript)',
    '',
    'Usage: jarvis [options]',
    '',
    'Options:',
    '  -m, --model <name>       Model to use (default: deepseek-v4-pro)',
    '  --api-key <key>           API key (config or env fallback)',
    '  --base-url <url>          API base URL (config or env fallback)',
    '  --effort <level>          Reasoning effort: auto|low|medium|high|xhigh|max',
    '  --max-turns <n>           Max conversation turns (default: 30)',
    '  --system-prompt <text>    System prompt override',
    '  -p, --prompt <text>       One-shot: run a single prompt and exit',
    '  -f, --fullscreen          Fullscreen mode (alternate screen buffer)',
    '  --configure               Run the first-run setup flow',
    '  -h, --help                Show this help',
    '',
    `User config: ${configPath}`,
    '.env is still supported as a fallback, but ~/.jarvis/config.json is preferred.',
    '',
    'If --prompt is provided, Jarvis runs in one-shot mode and exits.',
    'Otherwise, it starts an interactive session (TUI).',
  ].join('\n');
}

// ============================================================================
// One-shot run (no TUI)
// ============================================================================

export async function runOneShot(options: CLIOptions): Promise<string> {
  const ctx = bootstrap(options);
  const oneShotConfig = loadJarvisConfig();
  const runtime = createToolRuntime(ctx.tools, {
    permissionMode: 'workspace_write',
    sandbox: oneShotConfig.sandbox,
    projectRoot: process.cwd(),
  });

  const loop = new AgentLoop({
    model: { model: options.model, reasoningEffort: options.reasoningEffort },
    maxTurns: options.maxTurns,
    systemPrompt: options.systemPrompt,
    tools: ctx.tools,
    toolRuntime: runtime,
    provider: ctx.provider,
    mailbox: ctx.mailbox,
    skillRegistry: ctx.skills,
    skillExecutor: new SkillExecutor(ctx.skills),
    hooks: ctx.hooks,
  });

  const result = await loop.runTurn(options.oneShot ?? 'Hello');
  return result.finalAnswer;
}

// ============================================================================
// Main entry point
// ============================================================================

export async function main(argv: string[] = process.argv): Promise<void> {
  // Load .env from project root before anything else
  loadProjectEnv();

  const wantsHelp = argv.includes('--help') || argv.includes('-h');
  const wantsOneShot = argv.includes('--prompt') || argv.includes('-p');
  const wantsConfigure = argv.includes('--configure');

  const options = parseCLIArgs(argv);

  if ((argv.includes('--help') || argv.includes('-h'))) {
    console.log(printHelp());
    return;
  }

  if (options.oneShot) {
    try {
      const answer = await runOneShot(options);
      console.log(answer);
    } catch (err) {
      console.error('Error:', err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
    return;
  }

  // Interactive mode: launch TUI (main-screen or fullscreen)
  try {
    const { renderTUI } = await import('@jarvis/tui');
    await renderTUI({
      model: options.model,
      apiKey: options.apiKey,
      baseURL: options.baseURL,
      reasoningEffort: options.reasoningEffort,
      maxTurns: options.maxTurns,
      systemPrompt: options.systemPrompt,
      forceOnboarding: wantsConfigure,
      mainScreen: !options.fullscreen,
    });
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ERR_MODULE_NOT_FOUND') {
      console.error('TUI module not found. Install @jarvis/tui to use interactive mode.');
      process.exit(1);
    }
    throw err;
  }
}

// Self-executing entry point when run directly
const isMain = process.argv[1] && (
  process.argv[1].endsWith('/main.ts') ||
  process.argv[1].endsWith('/main.js') ||
  process.argv[1].endsWith('\\main.ts') ||
  process.argv[1].endsWith('\\main.js')
);
if (isMain) {
  main().catch((err) => {
    console.error('Fatal error:', err instanceof Error ? err.message : String(err));
    process.exit(1);
  });
}
