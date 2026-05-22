import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { parseCLIArgs, bootstrap, printHelp } from '../main.js';
import { SlashCommandRegistry, registerBuiltinCommands } from '../commands.js';

// ============================================================================
// parseCLIArgs
// ============================================================================

describe('parseCLIArgs', () => {
  it('parses default values', () => {
    const opts = parseCLIArgs(['node', 'jarvis']);
    expect(opts.model).toBe('deepseek-chat');
    expect(opts.maxTurns).toBe(30);
    expect(opts.oneShot).toBeUndefined();
  });

  it('parses --model', () => {
    const opts = parseCLIArgs(['node', 'jarvis', '--model', 'gpt-4o']);
    expect(opts.model).toBe('gpt-4o');
  });

  it('parses -m short flag', () => {
    const opts = parseCLIArgs(['node', 'jarvis', '-m', 'claude-opus']);
    expect(opts.model).toBe('claude-opus');
  });

  it('parses -p / --prompt for one-shot', () => {
    const opts = parseCLIArgs([
      'node',
      'jarvis',
      '-p',
      'What is TypeScript?',
    ]);
    expect(opts.oneShot).toBe('What is TypeScript?');
  });

  it('parses --max-turns', () => {
    const opts = parseCLIArgs(['node', 'jarvis', '--max-turns', '10']);
    expect(opts.maxTurns).toBe(10);
  });

  it('parses --api-key', () => {
    const opts = parseCLIArgs([
      'node',
      'jarvis',
      '--api-key',
      'sk-custom',
    ]);
    expect(opts.apiKey).toBe('sk-custom');
  });

  it('parses --base-url', () => {
    const opts = parseCLIArgs([
      'node',
      'jarvis',
      '--base-url',
      'https://api.openai.com/v1',
    ]);
    expect(opts.baseURL).toBe('https://api.openai.com/v1');
  });

  it('uses env vars as defaults', () => {
    process.env['JARVIS_MODEL'] = 'env-model';
    const opts = parseCLIArgs(['node', 'jarvis']);
    expect(opts.model).toBe('env-model');
    delete process.env['JARVIS_MODEL'];
  });

  it('--help flag is parsed', () => {
    const opts = parseCLIArgs(['node', 'jarvis', '--help']);
    // help flag doesn't affect CLIOptions, just parsed
    expect(opts.model).toBeDefined();
  });
});

// ============================================================================
// bootstrap
// ============================================================================

describe('bootstrap', () => {
  it('creates CLI context with all components', () => {
    const ctx = bootstrap({
      model: 'test-model',
      apiKey: 'sk-test',
      maxTurns: 10,
    });

    expect(ctx.provider).toBeDefined();
    expect(ctx.tools).toBeDefined();
    expect(ctx.hooks).toBeDefined();
    expect(ctx.commands).toBeDefined();
    expect(ctx.cmdContext.model).toBe('test-model');
    expect(ctx.cmdContext.cwd).toBeDefined();
  });

  it('setConfig updates model', () => {
    const ctx = bootstrap({
      model: 'test-model',
      apiKey: 'sk-test',
      maxTurns: 10,
    });

    expect(ctx.cmdContext.model).toBe('test-model');
    ctx.cmdContext.setConfig?.('model', 'new-model');
    expect(ctx.cmdContext.model).toBe('new-model');
  });
});

// ============================================================================
// printHelp
// ============================================================================

describe('printHelp', () => {
  it('returns help text with options', () => {
    const help = printHelp();
    expect(help).toContain('Jarvis');
    expect(help).toContain('--model');
    expect(help).toContain('--help');
    expect(help).toContain('--prompt');
  });
});

// ============================================================================
// SlashCommandRegistry
// ============================================================================

describe('SlashCommandRegistry', () => {
  let registry: SlashCommandRegistry;

  beforeEach(() => {
    registry = new SlashCommandRegistry();
  });

  it('registers and lists commands', () => {
    registry.register({
      name: 'test',
      description: 'A test command',
      execute: () => 'ok',
    });

    expect(registry.size).toBe(1);
    expect(registry.list()).toEqual(['test']);
  });

  it('executes a registered command', async () => {
    registry.register({
      name: 'hello',
      description: 'Say hello',
      execute: () => 'Hello, world!',
    });

    const result = await registry.execute('hello', [], {
      cwd: '/tmp',
    });

    expect(result).toBe('Hello, world!');
  });

  it('returns null for unknown command', async () => {
    const result = await registry.execute('unknown', [], {
      cwd: '/tmp',
    });
    expect(result).toBeNull();
  });

  it('passes args to command', async () => {
    registry.register({
      name: 'echo',
      description: 'Echo args',
      execute: (args) => args.join(' '),
    });

    const result = await registry.execute('echo', ['a', 'b', 'c'], {
      cwd: '/tmp',
    });
    expect(result).toBe('a b c');
  });

  it('groups commands by category', () => {
    registry.register({
      name: 'cmd1',
      description: 'One',
      category: 'a',
      execute: () => '1',
    });
    registry.register({
      name: 'cmd2',
      description: 'Two',
      category: 'b',
      execute: () => '2',
    });
    registry.register({
      name: 'cmd3',
      description: 'Three',
      category: 'a',
      execute: () => '3',
    });

    const grouped = registry.grouped();
    expect(grouped.size).toBe(2);
    expect(grouped.get('a')?.length).toBe(2);
    expect(grouped.get('b')?.length).toBe(1);
  });

  it('default category is general', () => {
    registry.register({
      name: 'x',
      description: 'X',
      execute: () => 'x',
    });

    const grouped = registry.grouped();
    expect(grouped.get('general')?.length).toBe(1);
  });

  it('get returns undefined for missing command', () => {
    expect(registry.get('nope')).toBeUndefined();
  });

  it('get returns the command for existing name', () => {
    registry.register({
      name: 'mycmd',
      description: 'My command',
      execute: () => 'done',
    });

    const cmd = registry.get('mycmd');
    expect(cmd).toBeDefined();
    expect(cmd!.name).toBe('mycmd');
  });

  it('supports async execute handlers', async () => {
    registry.register({
      name: 'async-cmd',
      description: 'Async',
      execute: async () => {
        return 'async result';
      },
    });

    const result = await registry.execute('async-cmd', [], {
      cwd: '/tmp',
    });
    expect(result).toBe('async result');
  });
});

// ============================================================================
// Built-in commands
// ============================================================================

describe('built-in commands', () => {
  let registry: SlashCommandRegistry;
  let ctx: { cwd: string; sessionId?: string; model?: string; setConfig?: (k: string, v: string) => string };

  beforeEach(() => {
    registry = new SlashCommandRegistry();
    registerBuiltinCommands(registry);
    ctx = {
      cwd: '/test',
      sessionId: 'sess-1',
      model: 'test-model',
      setConfig: (k, v) => {
        if (k === 'model') {
          ctx.model = v;
          return v;
        }
        return '';
      },
    };
  });

  it('/help lists all commands', async () => {
    const result = await registry.execute('help', [], ctx);
    expect(result).toContain('/help');
    expect(result).toContain('/model');
    expect(result).toContain('/clear');
    expect(result).toContain('/exit');
    expect(result).toContain('/status');
  });

  it('/model shows current model', async () => {
    const result = await registry.execute('model', [], ctx);
    expect(result).toContain('test-model');
  });

  it('/model sets new model', async () => {
    const result = await registry.execute('model', ['gpt-4o'], ctx);
    expect(result).toContain('gpt-4o');
    expect(ctx.model).toBe('gpt-4o');
  });

  it('/clear returns message', async () => {
    const result = await registry.execute('clear', [], ctx);
    expect(result).toBe('Conversation cleared.');
  });

  it('/exit returns goodbye', async () => {
    const result = await registry.execute('exit', [], ctx);
    expect(result).toBe('Goodbye.');
  });

  it('/status shows session info', async () => {
    const result = await registry.execute('status', [], ctx);
    expect(result).toContain('sess-1');
    expect(result).toContain('test-model');
    expect(result).toContain('/test');
  });

  it('/memory returns placeholder', async () => {
    const result = await registry.execute('memory', [], ctx);
    expect(result).toContain('not yet implemented');
  });

  it('/sessions returns placeholder', async () => {
    const result = await registry.execute('sessions', [], ctx);
    expect(result).toContain('not yet implemented');
  });

  it('has 7 built-in commands', () => {
    expect(registry.size).toBe(7);
  });

  it('all built-in commands execute without error', async () => {
    for (const name of registry.list()) {
      const result = await registry.execute(name, [], ctx);
      expect(result).toBeTruthy();
    }
  });
});
