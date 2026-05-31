import { MCPClient } from './client.js';
import { StdioMCPTransport } from './stdio-transport.js';
import { execSync } from 'node:child_process';

export type McpServerConfig = {
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  /** Connection timeout in seconds (default 30) */
  connect_timeout?: number;
  /** Per-tool-call request timeout in seconds (default 60) */
  request_timeout?: number;
  /** Whether this server is enabled (default true) */
  enabled?: boolean;
  /** Tool filtering: only include these tools */
  tools_include?: string[];
  /** Tool filtering: exclude these tools */
  tools_exclude?: string[];
};

export type McpConnectionState = 'connecting' | 'ready' | 'degraded' | 'retrying' | 'failed';

export type McpConnectionStatus = {
  id: string;
  plugin?: string;
  state: McpConnectionState;
  serverName?: string;
  toolCount?: number;
  resourceCount?: number;
  error?: string;
};

function isPnpmLikeCommand(command: string): boolean {
  const normalized = command.trim().toLowerCase().replace(/\\/g, '/');
  return (
    normalized === 'pnpm'
    || normalized.endsWith('/pnpm')
    || normalized.endsWith('/pnpm.cmd')
    || normalized.endsWith('/pnpm.exe')
  );
}

function shouldRetryWithNpxFallback(server: { config: McpServerConfig }, errorMessage: string): boolean {
  const command = server.config.command.trim();
  const args = server.config.args ?? [];
  return (
    isPnpmLikeCommand(command) &&
    args.length >= 2 &&
    String(args[0]).toLowerCase() === 'dlx' &&
    errorMessage.includes('ENOENT')
  );
}

function toNpxFallbackConfig(config: McpServerConfig): McpServerConfig {
  const args = config.args ?? [];
  const pkg = args[1] ?? '';
  const rest = args.slice(2);
  return {
    ...config,
    command: 'npx',
    args: ['-y', pkg, ...rest],
  };
}

function canResolveCommand(command: string): boolean {
  try {
    if (process.platform === 'win32') {
      const escaped = command.replace(/"/g, '\\"');
      const out = execSync(`where "${escaped}"`, { encoding: 'utf8' }).trim();
      return out.length > 0;
    }
    const out = execSync(`command -v ${command}`, { encoding: 'utf8', shell: '/bin/sh' }).trim();
    return out.length > 0;
  } catch {
    return false;
  }
}

function normalizeConfigForPlatform(config: McpServerConfig): { config: McpServerConfig; normalized: boolean; note?: string } {
  if (process.platform !== 'win32') {
    return { config, normalized: false };
  }
  const args = config.args ?? [];
  if (!isPnpmLikeCommand(config.command) || args.length < 2 || String(args[0]).toLowerCase() !== 'dlx') {
    return { config, normalized: false };
  }
  // On Windows, plugin configs frequently reference pnpm paths that are missing.
  // Prefer npx fallback up-front when pnpm cannot be resolved.
  if (!canResolveCommand('pnpm')) {
    return {
      config: toNpxFallbackConfig(config),
      normalized: true,
      note: 'pnpm not found on PATH; switched to npx fallback',
    };
  }
  return { config, normalized: false };
}

// ---- Dangerous env keys that must not be forwarded to MCP subprocesses ----
const DANGEROUS_ENV_KEYS = new Set([
  'NODE_OPTIONS', 'NODE_PATH',
  'PYTHONSTARTUP', 'PYTHONPATH', 'PYTHONHOME',
  'RUBYOPT', 'RUBYLIB',
  'SHELLOPTS', 'BASH_ENV',
  'LD_PRELOAD', 'LD_LIBRARY_PATH',
  'DYLD_INSERT_LIBRARIES', 'DYLD_LIBRARY_PATH',
]);

/** Filter env to safe baseline + user-specified vars. Strips dangerous keys. */
function filterSafeEnv(userEnv?: Record<string, string>): Record<string, string> {
  const safeKeys = ['PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'TERM', 'SHELL', 'TMPDIR', 'TEMP', 'TMP'];
  const safe: Record<string, string> = {};
  for (const key of safeKeys) {
    const val = process.env[key];
    if (val !== undefined) safe[key] = val;
  }
  // Pass through XDG_* vars (Linux desktop conventions)
  for (const [key, val] of Object.entries(process.env)) {
    if (key.startsWith('XDG_') && val !== undefined) safe[key] = val;
  }
  // Merge user-specified env (filtering dangerous keys)
  if (userEnv) {
    for (const [key, val] of Object.entries(userEnv)) {
      if (!DANGEROUS_ENV_KEYS.has(key.toUpperCase())) {
        safe[key] = val;
      }
    }
  }
  return safe;
}

/** Interpolate ${VAR_NAME} in string values from process.env */
function interpolateEnvVars(val: string): string {
  return val.replace(/\$\{(\w+)\}/g, (_, name: string) => process.env[name] ?? '');
}

/** Deep-interpolate ${VAR_NAME} in all string values of an object */
function interpolateEnv(obj: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(obj)) {
    out[k] = interpolateEnvVars(v);
  }
  return out;
}

const DEFAULT_CONNECT_TIMEOUT_SEC = 30;
const DEFAULT_REQUEST_TIMEOUT_SEC = 60;

export async function connectMcpServers(
  client: MCPClient,
  servers: Array<{ id: string; plugin?: string; config: McpServerConfig }>,
): Promise<McpConnectionStatus[]> {
  const statuses: McpConnectionStatus[] = [];
  for (const server of servers) {
    // Skip disabled servers
    if (server.config.enabled === false) {
      statuses.push({
        id: server.id,
        plugin: server.plugin,
        state: 'failed',
        error: 'disabled',
      });
      continue;
    }

    const connectTimeoutMs = (server.config.connect_timeout ?? DEFAULT_CONNECT_TIMEOUT_SEC) * 1000;
    const requestTimeoutMs = (server.config.request_timeout ?? DEFAULT_REQUEST_TIMEOUT_SEC) * 1000;

    const status: McpConnectionStatus = {
      id: server.id,
      plugin: server.plugin,
      state: 'connecting',
    };
    statuses.push(status);

    try {
      const normalized = normalizeConfigForPlatform(server.config);
      const safeEnv = filterSafeEnv(
        normalized.config.env ? interpolateEnv(normalized.config.env) : undefined,
      );
      const transport = new StdioMCPTransport(
        normalized.config.command,
        normalized.config.args ?? [],
        normalized.config.cwd,
        safeEnv,
        server.id,
      );
      const conn = await withTimeout(
        client.connect(transport),
        connectTimeoutMs,
        `MCP connect timed out after ${connectTimeoutMs}ms: ${server.id}`,
      );
      conn.serverName = server.id;
      conn.requestTimeoutMs = requestTimeoutMs;
      status.state = conn.tools.length > 0 || conn.resources.length > 0 ? 'ready' : 'degraded';
      status.serverName = conn.serverInfo?.name ?? server.id;
      status.toolCount = conn.tools.length;
      status.resourceCount = conn.resources.length;
      if (normalized.normalized && normalized.note) {
        status.error = normalized.note;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (shouldRetryWithNpxFallback(server, message)) {
        status.state = 'retrying';
        try {
          const fallback = toNpxFallbackConfig(server.config);
          const safeEnv = filterSafeEnv(
            fallback.env ? interpolateEnv(fallback.env) : undefined,
          );
          const transport = new StdioMCPTransport(
            fallback.command,
            fallback.args ?? [],
            fallback.cwd,
            safeEnv,
            server.id,
          );
          const conn = await withTimeout(
            client.connect(transport),
            connectTimeoutMs,
            `MCP connect timed out after ${connectTimeoutMs}ms: ${server.id}`,
          );
          conn.serverName = server.id;
          conn.requestTimeoutMs = requestTimeoutMs;
          status.state = conn.tools.length > 0 || conn.resources.length > 0 ? 'ready' : 'degraded';
          status.serverName = conn.serverInfo?.name ?? server.id;
          status.toolCount = conn.tools.length;
          status.resourceCount = conn.resources.length;
          status.error = 'Recovered from pnpm ENOENT via npx fallback';
          continue;
        } catch (retryError) {
          const retryMessage = retryError instanceof Error ? retryError.message : String(retryError);
          status.state = 'failed';
          status.error = `${message}; npx fallback failed: ${retryMessage}`;
          continue;
        }
      }
      status.state = 'failed';
      status.error = message;
    }
  }
  return statuses;
}

function withTimeout<T>(promise: Promise<T>, ms: number, msg: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(msg)), ms);
    promise.then(
      (val) => { clearTimeout(timer); resolve(val); },
      (err) => { clearTimeout(timer); reject(err); },
    );
  });
}
