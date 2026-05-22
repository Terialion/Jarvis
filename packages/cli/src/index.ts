// ============================================================================
// @jarvis/cli — CLI entry point, argument parsing, and slash commands
// ============================================================================

export {
  parseCLIArgs,
  bootstrap,
  printHelp,
  runOneShot,
  main,
} from './main.js';
export type { CLIOptions, CLIContext } from './main.js';

export {
  SlashCommandRegistry,
  registerBuiltinCommands,
} from './commands.js';
export type { SlashCommand, CommandContext } from './commands.js';
