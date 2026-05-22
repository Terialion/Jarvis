// ============================================================================
// SlashCommandRegistry — built-in slash commands for the CLI
// ============================================================================

// ============================================================================
// Types
// ============================================================================

export interface SlashCommand {
  /** Command name without leading slash */
  name: string;
  /** Short description shown in /help */
  description: string;
  /** Usage string, e.g. "/model <name>" */
  usage?: string;
  /** Category for grouping in help */
  category?: string;
  /** Execute the command. Returns the output string. */
  execute: (args: string[], context: CommandContext) => Promise<string> | string;
}

export interface CommandContext {
  /** Current working directory */
  cwd: string;
  /** Current session ID */
  sessionId?: string;
  /** Current model name */
  model?: string;
  /** Set a runtime config value and return the new value */
  setConfig?: (key: string, value: string) => string;
}

// ============================================================================
// SlashCommandRegistry
// ============================================================================

export class SlashCommandRegistry {
  private commands: Map<string, SlashCommand> = new Map();

  register(command: SlashCommand): void {
    this.commands.set(command.name, command);
  }

  get(name: string): SlashCommand | undefined {
    return this.commands.get(name);
  }

  /** List all registered command names. */
  list(): string[] {
    return [...this.commands.keys()];
  }

  /** List commands grouped by category. */
  grouped(): Map<string, SlashCommand[]> {
    const groups = new Map<string, SlashCommand[]>();
    for (const cmd of this.commands.values()) {
      const cat = cmd.category ?? 'general';
      const list = groups.get(cat) ?? [];
      list.push(cmd);
      groups.set(cat, list);
    }
    return groups;
  }

  /** Execute a slash command. Returns output string or null if not found. */
  async execute(
    name: string,
    args: string[],
    context: CommandContext,
  ): Promise<string | null> {
    const command = this.commands.get(name);
    if (!command) return null;
    return command.execute(args, context);
  }

  /** Number of registered commands. */
  get size(): number {
    return this.commands.size;
  }
}

// ============================================================================
// Built-in commands
// ============================================================================

export function registerBuiltinCommands(registry: SlashCommandRegistry): void {
  // --- Help ---
  registry.register({
    name: 'help',
    description: 'Show available commands',
    usage: '/help [command]',
    category: 'general',
    execute: (_args, _ctx) => {
      const grouped = registry.grouped();
      let output = 'Available commands:\n\n';
      for (const [category, cmds] of grouped) {
        output += `  ${category}:\n`;
        for (const cmd of cmds) {
          output += `    /${cmd.name} — ${cmd.description}\n`;
        }
        output += '\n';
      }
      return output.trim();
    },
  });

  // --- Model ---
  registry.register({
    name: 'model',
    description: 'Show or set the current model',
    usage: '/model [model-name]',
    category: 'config',
    execute: (args, ctx) => {
      if (args.length > 0 && ctx.setConfig) {
        const newModel = ctx.setConfig('model', args[0]);
        return `Model set to: ${newModel}`;
      }
      return `Current model: ${ctx.model ?? 'not set'}`;
    },
  });

  // --- Clear ---
  registry.register({
    name: 'clear',
    description: 'Clear the conversation history',
    usage: '/clear',
    category: 'session',
    execute: () => 'Conversation cleared.',
  });

  // --- Exit ---
  registry.register({
    name: 'exit',
    description: 'Exit the CLI',
    usage: '/exit',
    category: 'session',
    execute: () => 'Goodbye.',
  });

  // --- Memory ---
  registry.register({
    name: 'memory',
    description: 'Show or search memory entries',
    usage: '/memory [search-term]',
    category: 'session',
    execute: (_args, _ctx) => {
      return 'Memory search not yet implemented.';
    },
  });

  // --- Sessions ---
  registry.register({
    name: 'sessions',
    description: 'List recent sessions',
    usage: '/sessions',
    category: 'session',
    execute: (_args, _ctx) => {
      return 'Session listing not yet implemented.';
    },
  });

  // --- Status ---
  registry.register({
    name: 'status',
    description: 'Show current session status',
    usage: '/status',
    category: 'session',
    execute: (_args, ctx) => {
      return [
        `Session: ${ctx.sessionId ?? 'none'}`,
        `Model: ${ctx.model ?? 'not set'}`,
        `CWD: ${ctx.cwd}`,
      ].join('\n');
    },
  });
}
