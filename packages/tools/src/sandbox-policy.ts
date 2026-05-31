// ============================================================================
// Sandbox Policy — restricted local mode command safety
// ============================================================================
// Provides command classification, path boundary enforcement, and network
// awareness for the bash tool. No Docker dependency — pure regex + path checks.
// ============================================================================

import * as path from 'node:path';
import * as fs from 'node:fs';

// ============================================================================
// Types
// ============================================================================

export type CommandRisk = 'safe' | 'caution' | 'dangerous' | 'blocked';

export interface SandboxPolicyConfig {
  /** Project root — all file ops must stay within this boundary. */
  projectRoot: string;
  /** Allow network commands (curl, wget, git fetch). Default: true */
  allowNetwork?: boolean;
  /** Allow commands outside project root. Default: false */
  allowOutsideProject?: boolean;
  /** Extra blocked patterns (regex strings) */
  extraBlockedPatterns?: string[];
  /** Extra allowed patterns that bypass caution checks */
  extraAllowedPatterns?: string[];
}

export interface CommandCheckResult {
  risk: CommandRisk;
  reason?: string;
  /** Human-readable description of what the command does */
  description?: string;
}

// ============================================================================
// Command classification patterns
// ============================================================================

interface PatternEntry {
  pattern: RegExp;
  risk: CommandRisk;
  reason: string;
}

// Always blocked — no override possible
const BLOCKED: PatternEntry[] = [
  { pattern: /rm\s+-[a-z]*r[a-z]*f[a-z]*\s+\/\s*(?:$|[;&|])/, risk: 'blocked', reason: 'rm -rf / (root filesystem wipe)' },
  { pattern: /rm\s+-[a-z]*f[a-z]*r[a-z]*\s+\/\s*(?:$|[;&|])/, risk: 'blocked', reason: 'rm -fr / (root filesystem wipe)' },
  { pattern: /\bmkfs\b/, risk: 'blocked', reason: 'formatting filesystem (mkfs)' },
  { pattern: /dd\s+.*if=.*of=\/dev\//, risk: 'blocked', reason: 'raw write to block device (dd to /dev/)' },
  { pattern: /[:(][\s)]*[{][\s)]*[|:]/i, risk: 'blocked', reason: 'fork bomb detected' },
  { pattern: /\bfork\s*bomb\b/i, risk: 'blocked', reason: 'fork bomb' },
  { pattern: />\s*\/dev\/sd[a-z]/, risk: 'blocked', reason: 'direct write to disk device' },
  { pattern: /\bshutdown\b|\breboot\b|\binit\s+0/, risk: 'blocked', reason: 'system shutdown/reboot' },
];

// Dangerous — require explicit approval
const DANGEROUS: PatternEntry[] = [
  { pattern: /rm\s+.*-[a-z]*r/, risk: 'dangerous', reason: 'recursive file removal (rm -r)' },
  { pattern: /rm\s+.*--recursive/, risk: 'dangerous', reason: 'recursive file removal (rm --recursive)' },
  { pattern: /\bsudo\b/, risk: 'dangerous', reason: 'privilege escalation (sudo)' },
  { pattern: /chmod\s+.*777/, risk: 'dangerous', reason: 'world-writable permissions (chmod 777)' },
  { pattern: /chmod\s+.*-R\s+777/, risk: 'dangerous', reason: 'recursive world-writable permissions' },
  { pattern: /chown\s+.*-R/, risk: 'dangerous', reason: 'recursive ownership change (chown -R)' },
  { pattern: /[|>]\s*\/dev\//, risk: 'dangerous', reason: 'redirect to device file' },
  { pattern: /\bcurl\b.+\|\s*(?:ba)?sh\b/i, risk: 'dangerous', reason: 'curl piped to shell (remote code execution)' },
  { pattern: /\bwget\b.+\|\s*(?:ba)?sh\b/i, risk: 'dangerous', reason: 'wget piped to shell (remote code execution)' },
  { pattern: /\bcurl\b.+\|\s*sudo\b/i, risk: 'dangerous', reason: 'curl piped to sudo' },
  { pattern: /\b(?:nc|ncat|netcat)\s+-[a-z]*l/, risk: 'dangerous', reason: 'network listener (potential backdoor)' },
  { pattern: /\bpython3?\s+-m\s+http\.server/, risk: 'dangerous', reason: 'Python HTTP server (opens port)' },
  { pattern: /\bkill\s+-9\s+1\b/, risk: 'dangerous', reason: 'killing PID 1 (init)' },
  { pattern: /\bkillall\b/, risk: 'dangerous', reason: 'killing all processes by name' },
  { pattern: /\bpkill\b/, risk: 'dangerous', reason: 'killing processes by pattern' },
  { pattern: />\s*\/etc\//, risk: 'dangerous', reason: 'writing to /etc/ (system config)' },
  { pattern: /rm\s+.*\.(bashrc|zshrc|profile|ssh)/, risk: 'dangerous', reason: 'removing shell/SSH config files' },
];

// Caution — flagged but generally allowed
const CAUTION: PatternEntry[] = [
  { pattern: /\brm\b/, risk: 'caution', reason: 'file removal (rm)' },
  { pattern: /\bmv\b.*\/dev\/null/, risk: 'caution', reason: 'moving to /dev/null (effective delete)' },
  { pattern: /\bgit\s+clean\b/, risk: 'caution', reason: 'git clean (removes untracked files)' },
  { pattern: /\bgit\s+reset\s+--hard/, risk: 'caution', reason: 'git reset --hard (discards changes)' },
  { pattern: /\bgit\s+push\s+.*--force/, risk: 'caution', reason: 'force push (git push --force)' },
  { pattern: /\bgit\s+checkout\s+--\s+\./, risk: 'caution', reason: 'discard all local changes' },
  { pattern: /\bnpm\s+(?:ci|install)\s+.*--force/, risk: 'caution', reason: 'forced npm install' },
  { pattern: /\bpip\s+install\b/, risk: 'caution', reason: 'pip install (modifies Python env)' },
  { pattern: /\bnpm\s+uninstall\b/, risk: 'caution', reason: 'npm uninstall' },
];

// Network commands — flagged when network is restricted
const NETWORK: PatternEntry[] = [
  { pattern: /\bcurl\b/, risk: 'caution', reason: 'HTTP request (curl)' },
  { pattern: /\bwget\b/, risk: 'caution', reason: 'HTTP request (wget)' },
  { pattern: /\bgit\s+(?:clone|fetch|pull|push|remote)/, risk: 'caution', reason: 'git network operation' },
  { pattern: /\bnpm\s+(?:install|ci|publish|update)\b/, risk: 'caution', reason: 'npm network operation' },
  { pattern: /\byarn\s+(?:add|install)\b/, risk: 'caution', reason: 'yarn network operation' },
  { pattern: /\bpip\s+install\b/, risk: 'caution', reason: 'pip network operation' },
  { pattern: /\bdocker\s+(?:pull|push)\b/, risk: 'caution', reason: 'docker network operation' },
  { pattern: /\bssh\b/, risk: 'caution', reason: 'SSH connection' },
  { pattern: /\bscp\b/, risk: 'caution', reason: 'SCP file transfer' },
  { pattern: /\brsync\b.*:/, risk: 'caution', reason: 'rsync remote sync' },
];

// ============================================================================
// Path boundary checking
// ============================================================================

/** Extract file paths that a command references (heuristic). */
function extractPaths(command: string): string[] {
  const paths: string[] = [];

  // Match common path patterns
  // Absolute paths
  const absPaths = command.match(/(?:^|\s)(\/[^\s;&|]+)/g);
  if (absPaths) paths.push(...absPaths.map((p) => p.trim()));

  // Redirect targets
  const redirects = command.match(/>\s*(\/[^\s;&|]+)/g);
  if (redirects) paths.push(...redirects.map((p) => p.replace(/^>\s*/, '').trim()));

  return [...new Set(paths)];
}

function normalizePath(p: string): string {
  return path.resolve(p).replace(/\\/g, '/');
}

/** Check if a path is within the project boundary. */
function isWithinBoundary(filePath: string, projectRoot: string): boolean {
  const normalizedFile = normalizePath(filePath);
  const normalizedRoot = normalizePath(projectRoot);
  return normalizedFile.startsWith(normalizedRoot + '/') || normalizedFile === normalizedRoot;
}

/** Well-known safe paths outside project root that should be allowed. */
const SAFE_OUTSIDE_PATHS = [
  '/tmp/',
  '/var/tmp/',
  process.env.HOME || '/root',
  process.env.USERPROFILE || '',
].filter(Boolean);

function isSafeOutsidePath(filePath: string): boolean {
  const normalized = normalizePath(filePath);
  return SAFE_OUTSIDE_PATHS.some((safe) => normalized.startsWith(normalizePath(safe) + '/') || normalized === normalizePath(safe));
}

// ============================================================================
// Main check function
// ============================================================================

/**
 * Check a shell command against the sandbox policy.
 * Returns the risk level and reason.
 */
export function checkCommand(command: string, config: SandboxPolicyConfig): CommandCheckResult {
  const trimmed = command.trim();

  // Empty command
  if (!trimmed) {
    return { risk: 'safe', description: 'empty command' };
  }

  // Strip leading env vars and time prefix for pattern matching
  // e.g. "FOO=bar NODE_ENV=production npm test" → "npm test"
  const stripped = trimmed
    .replace(/^(\w+=\S+\s+)+/, '')     // leading env vars
    .replace(/^time\s+/, '')            // time prefix
    .replace(/^nice\s+(-\d+\s+)?/, '')  // nice prefix
    .replace(/^\d+\s+/, '');            // leading number (fd redirect)

  // === BLOCKED patterns (always denied) ===
  for (const entry of BLOCKED) {
    if (entry.pattern.test(trimmed) || entry.pattern.test(stripped)) {
      return { risk: 'blocked', reason: entry.reason };
    }
  }

  // Extra blocked patterns from config
  if (config.extraBlockedPatterns) {
    for (const pattern of config.extraBlockedPatterns) {
      try {
        if (new RegExp(pattern, 'i').test(trimmed)) {
          return { risk: 'blocked', reason: `matches blocked pattern: ${pattern}` };
        }
      } catch { /* invalid regex, skip */ }
    }
  }

  // Extra allowed patterns bypass remaining checks
  if (config.extraAllowedPatterns) {
    for (const pattern of config.extraAllowedPatterns) {
      try {
        if (new RegExp(pattern, 'i').test(trimmed)) {
          return { risk: 'safe', description: 'matches allowed pattern' };
        }
      } catch { /* invalid regex, skip */ }
    }
  }

  // === DANGEROUS patterns ===
  for (const entry of DANGEROUS) {
    if (entry.pattern.test(trimmed) || entry.pattern.test(stripped)) {
      return { risk: 'dangerous', reason: entry.reason };
    }
  }

  // === Path boundary check ===
  if (!config.allowOutsideProject) {
    const paths = extractPaths(trimmed);
    for (const p of paths) {
      if (!isWithinBoundary(p, config.projectRoot) && !isSafeOutsidePath(p)) {
        return {
          risk: 'dangerous',
          reason: `path outside project boundary: ${p}`,
        };
      }
    }
  }

  // === Network commands ===
  if (!config.allowNetwork) {
    for (const entry of NETWORK) {
      if (entry.pattern.test(trimmed) || entry.pattern.test(stripped)) {
        return { risk: 'caution', reason: `network: ${entry.reason}` };
      }
    }
  }

  // === CAUTION patterns ===
  for (const entry of CAUTION) {
    if (entry.pattern.test(trimmed) || entry.pattern.test(stripped)) {
      return { risk: 'caution', reason: entry.reason };
    }
  }

  return { risk: 'safe', description: classifyCommand(stripped) };
}

// ============================================================================
// Command classification for logging
// ============================================================================

function classifyCommand(command: string): string {
  const first = command.split(/\s+/)[0]?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    ls: 'list directory',
    cat: 'read file',
    head: 'read file (head)',
    tail: 'read file (tail)',
    wc: 'word count',
    find: 'find files',
    grep: 'search text',
    rg: 'search text (ripgrep)',
    echo: 'print text',
    pwd: 'print working directory',
    cd: 'change directory',
    which: 'locate command',
    type: 'command type',
    file: 'file type info',
    stat: 'file info',
    du: 'disk usage',
    df: 'disk free',
    ps: 'process list',
    top: 'process monitor',
    whoami: 'current user',
    date: 'current date',
    env: 'environment vars',
    printenv: 'print env var',
    git: 'git command',
    node: 'run node',
    npx: 'run npx',
    npm: 'npm command',
    python: 'run python',
    python3: 'run python3',
    tsc: 'typescript compile',
    vitest: 'run tests',
    jest: 'run tests',
    cargo: 'rust build',
    make: 'build',
    cmake: 'build',
  };
  return map[first] ?? 'shell command';
}

// ============================================================================
// Sandbox policy factory
// ============================================================================

export interface SandboxConfig {
  enabled: boolean;
  allowNetwork: boolean;
  allowOutsideProject: boolean;
  extraBlockedPatterns: string[];
  extraAllowedPatterns: string[];
}

const DEFAULT_SANDBOX_CONFIG: SandboxConfig = {
  enabled: true,
  allowNetwork: true,
  allowOutsideProject: false,
  extraBlockedPatterns: [],
  extraAllowedPatterns: [],
};

/**
 * Create a SandboxPolicyConfig from user config and project root.
 */
export function createSandboxPolicy(
  projectRoot: string,
  userSandbox?: Partial<SandboxConfig>,
): SandboxPolicyConfig | null {
  const merged = { ...DEFAULT_SANDBOX_CONFIG, ...userSandbox };
  if (!merged.enabled) return null;

  return {
    projectRoot,
    allowNetwork: merged.allowNetwork,
    allowOutsideProject: merged.allowOutsideProject,
    extraBlockedPatterns: merged.extraBlockedPatterns,
    extraAllowedPatterns: merged.extraAllowedPatterns,
  };
}
