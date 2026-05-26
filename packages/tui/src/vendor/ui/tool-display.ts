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
};

// Parse bash commands into human-readable summaries (OpenClaw resolveExecDetail pattern)
function summarizeBash(args: Record<string, unknown>): string | null {
  const raw = typeof args.command === 'string' ? args.command.trim() : null;
  if (!raw) return null;
  let cmd = raw;
  const shMatch = cmd.match(/^(?:bash|sh|zsh)\s+-c\s+['"](.+?)['"]\s*$/);
  if (shMatch) cmd = shMatch[1];
  const bin = cmd.split(/\s/)[0]?.replace(/^.*[/\\]/, '')?.toLowerCase() ?? '';
  const rest = cmd.slice(bin.length).trim();
  if (bin === 'git') {
    const sub = rest.split(/\s/)[0];
    const map: Record<string, string> = {
      status: 'check status', diff: 'check diff', log: 'view history',
      checkout: 'switch branch', switch: 'switch branch', commit: 'commit',
      pull: 'pull', push: 'push', fetch: 'fetch', merge: 'merge',
      rebase: 'rebase', add: 'stage', restore: 'restore', reset: 'reset',
      stash: 'stash', branch: 'list branches',
    };
    if (sub && map[sub]) return `git ${map[sub]}`;
    return `git ${sub || 'command'}`;
  }
  if (bin === 'npm' || bin === 'pnpm' || bin === 'yarn' || bin === 'bun') {
    const sub = rest.split(/\s/)[0];
    const map: Record<string, string> = {
      install: 'install', test: 'run tests', build: 'build',
      start: 'start', lint: 'lint', run: 'run script',
    };
    if (sub && map[sub]) return `${bin} ${map[sub]}`;
    return `${bin} ${sub || ''}`.trim();
  }
  if (bin === 'ls') return 'list files';
  if (bin === 'cat') return rest ? `show ${rest.split(/\s/)[0]}` : 'show file';
  if (bin === 'grep' || bin === 'rg') return 'search text';
  if (bin === 'find') return 'find files';
  if (bin === 'head' || bin === 'tail') return `show ${bin}`;
  if (bin === 'mkdir') return 'create folder';
  if (bin === 'rm') return 'remove files';
  if (bin === 'cp' || bin === 'mv') return `${bin} files`;
  if (bin === 'echo' || bin === 'printf') return 'print';
  if (bin === 'curl' || bin === 'wget') return 'fetch url';
  if (bin === 'node') return 'run node';
  if (bin === 'python' || bin === 'python3') return 'run python';
  if (bin === 'npx') return `npx ${rest.split(/\s/)[0] || ''}`.trim();
  if (bin === 'tsc') return 'type check';
  if (bin === 'vitest') return 'run tests';
  if (bin === 'eslint') return 'lint';
  return rest ? `${bin} ${rest.slice(0, 60)}` : `run ${bin}`;
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
