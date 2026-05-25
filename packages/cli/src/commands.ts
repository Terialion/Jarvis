// ============================================================================
// SlashCommandRegistry — built-in slash commands for the CLI
// ============================================================================

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

function parentDir(p: string): string {
  const sep = p.includes('\\') ? '\\' : '/';
  const parts = p.split(sep);
  parts.pop();
  return parts.join(sep) || sep;
}

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
      return executeMemorySearch(_args);
    },
  });

  // --- Sessions ---
  registry.register({
    name: 'sessions',
    description: 'List recent sessions',
    usage: '/sessions',
    category: 'session',
    execute: async (_args, _ctx) => {
      return executeSessionList(_ctx);
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

// ============================================================================
// /memory implementation
// ============================================================================

function findMemoryDir(): string | null {
  // Check project-local memory first, then global user memory
  const cwd = process.cwd();
  // Walk up from cwd to find .claude/projects/<project>/memory
  let dir = cwd;
  for (let i = 0; i < 10; i++) {
    const claudeDir = join(dir, '.claude');
    if (existsSync(claudeDir)) {
      // Check for project-specific memory
      try {
        const projectsDir = join(claudeDir, 'projects');
        if (existsSync(projectsDir)) {
          const entries = readdirSync(projectsDir, { withFileTypes: true });
          for (const entry of entries) {
            if (entry.isDirectory()) {
              const memPath = join(projectsDir, entry.name, 'memory');
              if (existsSync(memPath)) return memPath;
            }
          }
        }
      } catch { /* continue */ }
    }
    const parent = parentDir(dir);
    if (parent === dir) break;
    dir = parent;
  }

  // Fallback: global user memory
  const userMem = join(homedir(), '.claude', 'memory');
  if (existsSync(userMem)) return userMem;

  return null;
}

function executeMemorySearch(args: string[]): string {
  const memDir = findMemoryDir();
  if (!memDir) {
    return 'No memory directory found. Create memories by asking Claude to remember things.';
  }

  try {
    const indexFile = join(memDir, 'MEMORY.md');
    const allFiles = readdirSync(memDir, { withFileTypes: true })
      .filter((f) => f.isFile() && f.name.endsWith('.md'))
      .map((f) => f.name);

    if (allFiles.length === 0) {
      return 'No memory entries found. Create memories by asking Claude to remember things.';
    }

    const searchTerm = args.join(' ').toLowerCase().trim();

    if (!searchTerm) {
      // List all memories
      let output = 'Memory entries:\n\n';
      for (const file of allFiles) {
        try {
          const content = readFileSync(join(memDir, file), 'utf-8');
          const firstLine = content.split('\n')[0]?.replace(/^#+\s*/, '') ?? file;
          output += `  ${file} — ${firstLine.slice(0, 80)}\n`;
        } catch {
          output += `  ${file}\n`;
        }
      }
      return output.trim() || 'No memory entries found.';
    }

    // Search mode
    let output = `Memory search results for "${searchTerm}":\n\n`;
    let found = 0;
    for (const file of allFiles) {
      try {
        const content = readFileSync(join(memDir, file), 'utf-8');
        if (content.toLowerCase().includes(searchTerm)) {
          found++;
          const lines = content.split('\n');
          const title = lines[0]?.replace(/^#+\s*/, '') ?? file;
          const matchLines = lines
            .map((l, i) => (l.toLowerCase().includes(searchTerm) ? `    ${i + 1}: ${l.trim().slice(0, 100)}` : null))
            .filter(Boolean)
            .slice(0, 3);
          output += `  ${file} — ${title.slice(0, 80)}\n`;
          output += `${matchLines.join('\n')}\n\n`;
        }
      } catch { /* skip unreadable files */ }
    }

    if (found === 0) {
      return `No memory entries matching "${searchTerm}" found.`;
    }

    return output.trim();
  } catch (err) {
    return `Error reading memory: ${err instanceof Error ? err.message : String(err)}`;
  }
}

// ============================================================================
// /sessions implementation
// ============================================================================

function findSessionsDir(): string | null {
  const cwd = process.cwd();
  let dir = cwd;
  for (let i = 0; i < 10; i++) {
    const claudeDir = join(dir, '.claude');
    if (existsSync(claudeDir)) {
      const sessionsDir = join(claudeDir, 'sessions');
      if (existsSync(sessionsDir)) return sessionsDir;
    }
    const parent = parentDir(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

async function executeSessionList(_ctx: CommandContext): Promise<string> {
  const sessionsDir = findSessionsDir();

  if (!sessionsDir) {
    // Try the store package as fallback
    try {
      // Dynamic import to avoid hard dependency on store package
      const sessionsApi = await tryLoadSessionsFromStore();
      if (sessionsApi) return sessionsApi;
    } catch { /* fall through */ }
    return 'No sessions directory found. Sessions are stored in .claude/sessions/.';
  }

  try {
    const files = readdirSync(sessionsDir, { withFileTypes: true })
      .filter((f) => f.isFile() && f.name.endsWith('.json'))
      .map((f) => {
        const stat = readFileSync(join(sessionsDir, f.name), 'utf-8');
        try {
          const session = JSON.parse(stat) as Record<string, unknown>;
          return {
            name: f.name.replace('.json', ''),
            mtime: f.name, // modified time from filename if it's a timestamp
            turns: Array.isArray(session['messages']) ? session['messages'].length : '?',
            model: session['model'] ?? '?',
          };
        } catch {
          return { name: f.name.replace('.json', ''), mtime: '?', turns: '?', model: '?' };
        }
      })
      .slice(0, 20);

    if (files.length === 0) {
      return 'No sessions found.';
    }

    let output = `Recent sessions (${files.length}):\n\n`;
    for (const s of files) {
      output += `  ${s.name} — ${s.turns} turns, model: ${s.model}\n`;
    }
    return output.trim();
  } catch (err) {
    return `Error reading sessions: ${err instanceof Error ? err.message : String(err)}`;
  }
}

async function tryLoadSessionsFromStore(): Promise<string | null> {
  // Attempt to use the @jarvis/store session provider if available
  try {
    const { SessionStore } = await import('@jarvis/store');
    const store = new SessionStore();
    if (typeof (store as unknown as Record<string, unknown>)['listRecent'] === 'function') {
      const sessions = await (store as unknown as { listRecent: (limit: number) => Promise<Array<{ id: string; turnCount: number; modelName: string; updatedAt: string }>> }).listRecent(20);
      if (sessions.length === 0) return 'No sessions found.';
      let output = `Recent sessions (${sessions.length}):\n\n`;
      for (const s of sessions) {
        output += `  ${s.id} — ${s.turnCount} turns, model: ${s.modelName}, updated: ${s.updatedAt}\n`;
      }
      return output.trim();
    }
  } catch { /* store not available */ }
  return null;
}
