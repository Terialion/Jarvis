// Semantic tool display formatting — inspired by OpenClaw's TOOL_DISPLAY_CONFIG

type ToolDisplay = { label: string; detailKeys: string[] };

const TOOL_DISPLAY: Record<string, ToolDisplay> = {
  bash: { label: 'Bash', detailKeys: ['command'] },
  read: { label: 'Read', detailKeys: ['path', 'file_path'] },
  write: { label: 'Write', detailKeys: ['path', 'file_path'] },
  edit: { label: 'Edit', detailKeys: ['path', 'file_path'] },
  glob: { label: 'Glob', detailKeys: ['pattern'] },
  grep: { label: 'Grep', detailKeys: ['pattern', 'path'] },
  web_search: { label: 'Web Search', detailKeys: ['query'] },
  web_fetch: { label: 'Web Fetch', detailKeys: ['url'] },
  task_create: { label: 'Create Task', detailKeys: ['subject'] },
  task_update: { label: 'Update Task', detailKeys: ['taskId'] },
  task_list: { label: 'List Tasks', detailKeys: [] },
  task_get: { label: 'Get Task', detailKeys: ['taskId'] },
  task_output: { label: 'Task Output', detailKeys: ['taskId'] },
  task_stop: { label: 'Stop Task', detailKeys: ['taskId'] },
  enter_plan_mode: { label: 'Plan', detailKeys: [] },
  exit_plan_mode: { label: 'Exit Plan', detailKeys: [] },
  notebook_edit: { label: 'Notebook', detailKeys: ['notebook_path'] },
  cron_create: { label: 'Create Cron', detailKeys: ['cron'] },
  cron_delete: { label: 'Delete Cron', detailKeys: [] },
  cron_list: { label: 'List Crons', detailKeys: [] },
  schedule_wakeup: { label: 'Wakeup', detailKeys: [] },
  enter_worktree: { label: 'Enter Worktree', detailKeys: [] },
  exit_worktree: { label: 'Exit Worktree', detailKeys: [] },
  memory_search: { label: 'Memory', detailKeys: ['query'] },
  memory_get: { label: 'Memory', detailKeys: ['name', 'path'] },
  ask_user_question: { label: 'Ask', detailKeys: [] },
  skill: { label: 'Skill', detailKeys: [] },
  'skill.load': { label: 'Skill', detailKeys: ['skill'] },
  agent: { label: 'Agent', detailKeys: ['description'] },
  list_mcp_resources: { label: 'MCP', detailKeys: [] },
  read_mcp_resource: { label: 'MCP', detailKeys: ['server', 'uri'] },
  mcp_healthcheck: { label: 'MCP Healthcheck', detailKeys: [] },
  mcp_bootstrap: { label: 'MCP Setup', detailKeys: ['server'] },
  plugin_bootstrap: { label: 'Plugin Setup', detailKeys: ['pluginName', 'server'] },
};

// ---- Shell word splitting (OpenClaw tool-display-common:4-95) ----

function stripOuterQuotes(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length >= 2 && ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'")))) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function splitShellWords(input: string, maxWords = 48): string[] {
  if (!input) return [];
  const words: string[] = [];
  let current = '';
  let quote: string | undefined;
  let escaped = false;
  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (escaped) { current += char; escaped = false; continue; }
    if (char === '\\') { escaped = true; continue; }
    if (quote) {
      if (char === quote) quote = undefined;
      else current += char;
      continue;
    }
    if (char === '"' || char === "'") { quote = char; continue; }
    if (/\s/.test(char)) {
      if (!current) continue;
      words.push(current);
      if (words.length >= maxWords) return words;
      current = '';
      continue;
    }
    current += char;
  }
  if (current) words.push(current);
  return words;
}

function binaryName(token?: string): string | undefined {
  if (!token) return;
  const cleaned = stripOuterQuotes(token) ?? token;
  return (cleaned.split(/[/\\]/).at(-1) ?? cleaned).toLowerCase();
}

function optionValue(words: string[], names: string[]): string | undefined {
  const lookup = new Set(names);
  for (let i = 0; i < words.length; i++) {
    const token = words[i];
    if (!token) continue;
    if (lookup.has(token)) {
      const value = words[i + 1];
      if (value && !value.startsWith('-')) return value;
      continue;
    }
    for (const name of names) {
      if (name.startsWith('--') && token.startsWith(`${name}=`)) return token.slice(name.length + 1);
    }
  }
}

function positionalArgs(words: string[], from = 1, optionsWithValue: string[] = []): string[] {
  const args: string[] = [];
  const takesValue = new Set(optionsWithValue);
  for (let i = from; i < words.length; i++) {
    const token = words[i];
    if (!token) continue;
    if (token === '--') {
      for (let j = i + 1; j < words.length; j++) { const c = words[j]; if (c) args.push(c); }
      break;
    }
    if (token.startsWith('--')) {
      if (token.includes('=')) continue;
      if (takesValue.has(token)) i += 1;
      continue;
    }
    if (token.startsWith('-')) {
      if (takesValue.has(token)) i += 1;
      continue;
    }
    args.push(token);
  }
  return args;
}

function firstPositional(words: string[], from = 1, optionsWithValue: string[] = []): string | undefined {
  return positionalArgs(words, from, optionsWithValue)[0];
}

function trimLeadingEnv(words: string[]): string[] {
  if (words.length === 0) return words;
  let index = 0;
  if (binaryName(words[0]) === 'env') {
    index = 1;
    while (index < words.length) {
      const token = words[index];
      if (!token) break;
      if (token.startsWith('-')) { index += 1; continue; }
      if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(token)) { index += 1; continue; }
      break;
    }
    return words.slice(index);
  }
  while (index < words.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[index])) index += 1;
  return words.slice(index);
}

function unwrapShellWrapper(command: string): string {
  const words = splitShellWords(command, 10);
  if (words.length < 3) return command;
  const bin = binaryName(words[0]);
  if (!(bin === 'bash' || bin === 'sh' || bin === 'zsh' || bin === 'fish')) return command;
  const flagIndex = words.findIndex((token, i) => i > 0 && (token === '-c' || token === '-lc' || token === '-ic'));
  if (flagIndex === -1) return command;
  const inner = words.slice(flagIndex + 1).join(' ').trim();
  return inner ? stripOuterQuotes(inner) ?? command : command;
}

// ---- Stage/pipeline detection (OpenClaw:152-183) ----

function scanTopLevelChars(command: string, visit: (char: string, index: number) => boolean | void): void {
  let quote: string | undefined;
  let escaped = false;
  for (let i = 0; i < command.length; i++) {
    const char = command[i];
    if (escaped) { escaped = false; continue; }
    if (char === '\\') { escaped = true; continue; }
    if (quote) {
      if (char === quote) quote = undefined;
      continue;
    }
    if (char === '"' || char === "'") { quote = char; continue; }
    if (visit(char, i) === false) return;
  }
}

function splitTopLevelStages(command: string): string[] {
  const parts: string[] = [];
  let start = 0;
  scanTopLevelChars(command, (char, index) => {
    if (char === ';') { parts.push(command.slice(start, index)); start = index + 1; return true; }
    if ((char === '&' || char === '|') && command[index + 1] === char) { parts.push(command.slice(start, index)); start = index + 2; return true; }
    return true;
  });
  parts.push(command.slice(start));
  return parts.map((p) => p.trim()).filter((p) => p.length > 0);
}

function splitTopLevelPipes(command: string): string[] {
  const parts: string[] = [];
  let start = 0;
  scanTopLevelChars(command, (char, index) => {
    if (char === '|' && command[index - 1] !== '|' && command[index + 1] !== '|') { parts.push(command.slice(start, index)); start = index + 1; }
    return true;
  });
  parts.push(command.slice(start));
  return parts.map((p) => p.trim()).filter((p) => p.length > 0);
}

// ---- Preamble stripping (OpenClaw:184-237) ----

function isChdirCommand(head: string): boolean {
  const bin = binaryName(splitShellWords(head, 2)[0]);
  return bin === 'cd' || bin === 'pushd' || bin === 'popd';
}

function stripShellPreamble(command: string): { command: string; chdirPath?: string } {
  let rest = command.trim();
  let chdirPath: string | undefined;
  for (let i = 0; i < 4; i++) {
    let first: { index: number; length: number; isOr?: boolean } | undefined;
    scanTopLevelChars(rest, (char, idx) => {
      if (char === '&' && rest[idx + 1] === '&') { first = { index: idx, length: 2 }; return false; }
      if (char === '|' && rest[idx + 1] === '|') { first = { index: idx, length: 2, isOr: true }; return false; }
      if (char === ';' || char === '\n') { first = { index: idx, length: 1 }; return false; }
    });
    const head = (first ? rest.slice(0, first.index) : rest).trim();
    const isChdir = (first ? !first.isOr : i > 0) && isChdirCommand(head);
    if (!(head.startsWith('set ') || head.startsWith('export ') || head.startsWith('unset ') || isChdir)) break;
    if (isChdir) chdirPath = undefined; // popd or cd with unknown target
    rest = first ? rest.slice(first.index + first.length).trimStart() : '';
    if (!rest) break;
  }
  return { command: rest.trim(), chdirPath };
}

// ---- Main command summarization (OpenClaw:240-548) ----

function summarizeKnownExec(words: string[]): string {
  if (words.length === 0) return 'run command';
  const bin = binaryName(words[0]) ?? 'command';

  // Git
  if (bin === 'git') {
    const globalWithValue = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace', '--config-env']);
    let sub: string | undefined;
    for (let i = 1; i < words.length; i++) {
      const token = words[i];
      if (!token) continue;
      if (token === '--') { sub = firstPositional(words, i + 1); break; }
      if (token.startsWith('--')) { if (token.includes('=')) continue; if (globalWithValue.has(token)) i += 1; continue; }
      if (token.startsWith('-')) { if (globalWithValue.has(token)) i += 1; continue; }
      sub = token; break;
    }
    const map: Record<string, string> = {
      status: 'check git status', diff: 'check git diff', log: 'view git history',
      show: 'show git object', branch: 'list git branches', checkout: 'switch git branch',
      switch: 'switch git branch', commit: 'create git commit', pull: 'pull git changes',
      push: 'push git changes', fetch: 'fetch git changes', merge: 'merge git changes',
      rebase: 'rebase git branch', add: 'stage git changes', restore: 'restore git files',
      reset: 'reset git state', stash: 'stash git changes',
    };
    if (sub && map[sub]) return map[sub];
    if (!sub || sub.startsWith('/') || sub.startsWith('~') || sub.includes('/')) return 'run git command';
    return `run git ${sub}`;
  }

  // Grep
  if (bin === 'grep' || bin === 'rg' || bin === 'ripgrep') {
    const optsWithVal = ['-e', '--regexp', '-f', '--file', '-m', '--max-count', '-A', '--after-context', '-B', '--before-context', '-C', '--context'];
    const positional = positionalArgs(words, 1, optsWithVal);
    const pattern = optionValue(words, ['-e', '--regexp']) ?? positional[0];
    const target = positional.length > 1 ? positional.at(-1) : undefined;
    if (pattern) return target ? `search "${pattern}" in ${target}` : `search "${pattern}"`;
    return 'search text';
  }

  // Find
  if (bin === 'find') {
    const path = words[1] && !words[1].startsWith('-') ? words[1] : '.';
    const name = optionValue(words, ['-name', '-iname']);
    return name ? `find files named "${name}" in ${path}` : `find files in ${path}`;
  }

  // ls
  if (bin === 'ls') { const target = firstPositional(words, 1); return target ? `list files in ${target}` : 'list files'; }

  // head/tail
  if (bin === 'head' || bin === 'tail') {
    const lines = optionValue(words, ['-n', '--lines']) ?? words.slice(1).find((t) => /^-\d+$/.test(t))?.slice(1);
    const positional = positionalArgs(words, 1, ['-n', '--lines']);
    let target = positional.at(-1);
    if (target && /^\d+$/.test(target) && positional.length === 1) target = undefined;
    const side = bin === 'head' ? 'first' : 'last';
    const unit = lines === '1' ? 'line' : 'lines';
    if (lines && target) return `show ${side} ${lines} ${unit} of ${target}`;
    if (lines) return `show ${side} ${lines} ${unit}`;
    if (target) return `show ${target}`;
    return `show ${bin} output`;
  }

  // cat
  if (bin === 'cat') { const target = firstPositional(words, 1); return target ? `show ${target}` : 'show output'; }

  // sed
  if (bin === 'sed') {
    const expression = optionValue(words, ['-e', '--expression']);
    const positional = positionalArgs(words, 1, ['-e', '--expression', '-f', '--file']);
    const script = expression ?? positional[0];
    const target = expression ? positional[0] : positional[1];
    if (script) {
      const compact = (stripOuterQuotes(script) ?? script).replace(/\s+/g, '');
      if (/^\d+,\d+p$/.test(compact)) return target ? `print lines from ${target}` : 'print lines';
      if (/^\d+p$/.test(compact)) return target ? `print line from ${target}` : 'print line';
    }
    return target ? `run sed on ${target}` : 'run sed';
  }

  // echo/printf
  if (bin === 'echo' || bin === 'printf') return 'print text';

  // cp/mv
  if (bin === 'cp' || bin === 'mv') {
    const positional = positionalArgs(words, 1, ['-t', '--target-directory', '-S', '--suffix']);
    const src = positional[0]; const dst = positional[1];
    const action = bin === 'cp' ? 'copy' : 'move';
    if (src && dst) return `${action} ${src} to ${dst}`;
    if (src) return `${action} ${src}`;
    return `${action} files`;
  }

  // rm/mkdir/touch
  if (bin === 'rm') { const t = firstPositional(words, 1); return t ? `remove ${t}` : 'remove files'; }
  if (bin === 'mkdir') { const t = firstPositional(words, 1); return t ? `create folder ${t}` : 'create folder'; }
  if (bin === 'touch') { const t = firstPositional(words, 1); return t ? `create file ${t}` : 'create file'; }

  // curl/wget
  if (bin === 'curl' || bin === 'wget') {
    const url = words.find((t) => /^https?:\/\//i.test(t));
    return url ? `fetch ${url}` : 'fetch url';
  }

  // Package managers
  if (bin === 'npm' || bin === 'pnpm' || bin === 'yarn' || bin === 'bun') {
    const positional = positionalArgs(words, 1, ['--prefix', '-C', '--cwd', '--config']);
    const sub = positional[0] ?? 'command';
    const map: Record<string, string> = {
      install: 'install dependencies', test: 'run tests', build: 'run build',
      start: 'start app', lint: 'run lint', run: positional[1] ? `run ${positional[1]}` : 'run script',
    };
    if (sub && map[sub]) return map[sub];
    return `${bin} ${sub}`;
  }

  // Interpreters
  if (bin === 'node' || bin === 'python' || bin === 'python3' || bin === 'ruby' || bin === 'php') {
    const script = firstPositional(words, 1, bin === 'node' ? ['-e', '--eval', '-m'] : ['-c', '-e', '--eval', '-m']);
    if (!script) return `run ${bin}`;
    return `run ${bin} ${script}`;
  }

  // npx / tsc / vitest / eslint
  if (bin === 'npx') return `npx ${words.slice(1).find((w) => !w.startsWith('-')) || ''}`.trim();
  if (bin === 'tsc') return 'type check';
  if (bin === 'vitest') return 'run tests';
  if (bin === 'eslint') return 'lint code';

  // Generic
  const arg = firstPositional(words, 1);
  if (!arg || arg.length > 48) return `run ${bin}`;
  return /^[A-Za-z0-9._/-]+$/.test(arg) ? `run ${bin} ${arg}` : `run ${bin}`;
}

function summarizePipeline(stage: string): string {
  const pipeline = splitTopLevelPipes(stage);
  if (pipeline.length > 1) {
    const first = summarizeKnownExec(trimLeadingEnv(splitShellWords(pipeline[0])));
    const last = summarizeKnownExec(trimLeadingEnv(splitShellWords(pipeline[pipeline.length - 1])));
    return `${first} | ${last}${pipeline.length > 2 ? ` (+${pipeline.length - 2})` : ''}`;
  }
  return summarizeKnownExec(trimLeadingEnv(splitShellWords(stage)));
}

function compactRawCommand(raw: string, maxLength = 120): string {
  const oneLine = raw.replace(/\s*\n\s*/g, ' ').replace(/\s{2,}/g, ' ').trim();
  if (oneLine.length <= maxLength) return oneLine;
  return `${oneLine.slice(0, Math.max(0, maxLength - 1))}…`;
}

// Parse bash commands into human-readable summaries (OpenClaw resolveExecDetail pattern)
function summarizeBash(args: Record<string, unknown>): string | null {
  const raw = typeof args.command === 'string' ? args.command.trim() : null;
  if (!raw) return null;
  const unwrapped = unwrapShellWrapper(raw);
  const { command: cleaned } = stripShellPreamble(unwrapped);
  if (!cleaned) return null;
  const stages = splitTopLevelStages(cleaned);
  if (stages.length === 0) return null;
  const summaries = stages.map((s) => summarizePipeline(s));
  return summaries.length === 1 ? summaries[0] : summaries.join(' → ');
}

function resolvePath(args: Record<string, unknown>): string | null {
  for (const key of ['file_path', 'path']) {
    const v = args[key];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return null;
}

function resolveDetail(toolName: string, args: Record<string, unknown>): string | null {
  if (toolName === 'bash') return summarizeBash(args);
  if (toolName === 'read') {
    const path = resolvePath(args);
    if (!path) return null;
    const offset = typeof args.offset === 'number' && args.offset > 0 ? Math.floor(args.offset) : undefined;
    const limit = typeof args.limit === 'number' && args.limit > 0 ? Math.floor(args.limit) : undefined;
    if (offset !== undefined && limit !== undefined) return `L${offset}-${offset + limit - 1} ${path}`;
    if (offset !== undefined) return `from L${offset} ${path}`;
    if (limit !== undefined) return `first ${limit}L ${path}`;
    return path;
  }
  if (toolName === 'write' || toolName === 'edit') {
    const path = resolvePath(args);
    const content = (typeof args.content === 'string' ? args.content :
      typeof args.new_string === 'string' ? args.new_string : null);
    if (path && content) return `${path} (${content.length}c)`;
    if (path) return path;
    return null;
  }
  if (toolName === 'grep') {
    const pattern = typeof args.pattern === 'string' ? args.pattern : null;
    const path = typeof args.path === 'string' ? args.path : null;
    if (pattern && path) return `"${pattern.slice(0, 40)}" in ${path}`;
    if (pattern) return `"${pattern.slice(0, 60)}"`;
    return null;
  }
  if (toolName === 'glob') return typeof args.pattern === 'string' ? args.pattern : null;
  if (toolName === 'web_search') return typeof args.query === 'string' ? args.query.slice(0, 80) : null;
  if (toolName === 'web_fetch') return typeof args.url === 'string' ? args.url.slice(0, 80) : null;
  const config = TOOL_DISPLAY[toolName];
  if (config?.detailKeys) {
    for (const key of config.detailKeys) {
      const value = args[key];
      if (typeof value === 'string' && value.trim()) return value.trim().slice(0, 80);
    }
  }
  return null;
}

export function formatToolLine(toolName: string, args: Record<string, unknown> | undefined): string {
  const config = TOOL_DISPLAY[toolName];
  const label = config?.label ?? toolName.replace(/_/g, ' ');
  const detail = args ? resolveDetail(toolName, args) : null;
  return detail ? `${label}: ${detail}` : label;
}

export function formatDuration(ms: number): string {
  ms = Math.max(0, ms); // guard against clock skew
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}
