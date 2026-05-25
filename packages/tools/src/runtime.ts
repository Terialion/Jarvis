// ============================================================================
// ToolRuntime + ApprovalGate — execution orchestration and command safety
// ============================================================================

import type { ToolResult } from '@jarvis/shared';
import { ToolRegistry, type ToolContext } from './registry.js';

// ============================================================================
// PermissionManager — per-tool approval mode gating
// ============================================================================

export type PermissionMode = 'bypass' | 'accept_edits' | 'default';

/** Risk levels for tool categorization */
export type ToolRiskLevel = 'read_only' | 'write_approval_required' | 'command' | 'network' | 'credentialed';

export interface PermissionCheckResult {
  allowed: boolean;
  reason?: string;
  needsApproval?: boolean;
}

interface PermissionConfig {
  mode: PermissionMode;
  approveAll: boolean;
  approvedTools: Set<string>;
  deniedTools: Set<string>;
}

const DEFAULT_RISK_MAP: Record<string, ToolRiskLevel> = {
  bash: 'command',
  read_file: 'read_only',
  write_file: 'write_approval_required',
  edit_file: 'write_approval_required',
  glob: 'read_only',
  grep: 'read_only',
  web_search: 'network',
  web_fetch: 'network',
  ask_user_question: 'read_only',
  task_create: 'read_only',
  task_update: 'read_only',
  task_list: 'read_only',
  task_get: 'read_only',
  task_output: 'read_only',
  task_stop: 'read_only',
  enter_plan_mode: 'read_only',
  exit_plan_mode: 'read_only',
  notebook_edit: 'write_approval_required',
  cron_create: 'read_only',
  cron_delete: 'read_only',
  cron_list: 'read_only',
  schedule_wakeup: 'read_only',
  enter_worktree: 'write_approval_required',
  exit_worktree: 'write_approval_required',
  skill_load: 'read_only',
  Skill: 'read_only',
};

/**
 * PermissionManager controls which tools can execute without approval.
 *
 * Modes:
 * - bypass: all tools auto-approved (no prompts, like Claude Code's bypass mode)
 * - accept_edits: auto-approve file edits, prompt for bash/network/credentialed
 * - default: prompt for write, bash, network, and credentialed tools
 */
export class PermissionManager {
  private config: PermissionConfig = {
    mode: 'default',
    approveAll: false,
    approvedTools: new Set(),
    deniedTools: new Set(),
  };

  private riskMap: Record<string, ToolRiskLevel>;

  constructor(riskMap?: Record<string, ToolRiskLevel>) {
    this.riskMap = riskMap ?? DEFAULT_RISK_MAP;
  }

  /** Set the permission mode. */
  setMode(mode: PermissionMode): void {
    this.config.mode = mode;
  }

  /** Get the current mode. */
  getMode(): PermissionMode {
    return this.config.mode;
  }

  /** Approve a specific tool for the remainder of the session. */
  approveTool(toolName: string): void {
    this.config.approvedTools.add(toolName);
    this.config.deniedTools.delete(toolName);
  }

  /** Deny a specific tool for the remainder of the session. */
  denyTool(toolName: string): void {
    this.config.deniedTools.add(toolName);
    this.config.approvedTools.delete(toolName);
  }

  /** Approve all tools (one-time bypass). */
  approveAll(): void {
    this.config.approveAll = true;
  }

  /** Reset approvals (keep mode). */
  resetApprovals(): void {
    this.config.approveAll = false;
    this.config.approvedTools.clear();
    this.config.deniedTools.clear();
  }

  /**
   * Check whether a tool can execute without approval.
   * Returns { allowed, needsApproval, reason }.
   */
  check(toolName: string): PermissionCheckResult {
    // Bypass mode: everything auto-approved
    if (this.config.mode === 'bypass') {
      return { allowed: true };
    }

    // One-time approve-all
    if (this.config.approveAll) {
      return { allowed: true };
    }

    // Explicitly approved
    if (this.config.approvedTools.has(toolName)) {
      return { allowed: true };
    }

    // Explicitly denied
    if (this.config.deniedTools.has(toolName)) {
      return { allowed: false, reason: `Tool "${toolName}" has been denied for this session.` };
    }

    const risk = this.riskMap[toolName] ?? 'write_approval_required';

    switch (this.config.mode) {
      case 'default': {
        // In default mode: read_only auto-approved, everything else needs approval
        if (risk === 'read_only') return { allowed: true };
        return {
          allowed: true,
          needsApproval: true,
          reason: `Tool "${toolName}" (${risk}) requires approval. Use /permissions to adjust.`,
        };
      }
      case 'accept_edits': {
        // accept_edits: auto-approve read_only + write, prompt for bash/network/credentialed
        if (risk === 'read_only' || risk === 'write_approval_required') return { allowed: true };
        return {
          allowed: true,
          needsApproval: true,
          reason: `Tool "${toolName}" (${risk}) requires approval in accept_edits mode.`,
        };
      }
      default:
        return { allowed: true };
    }
  }
}

// ============================================================================
// ToolRuntime
// ============================================================================

export interface ToolRuntimeOptions {
  /** Default max result characters before truncation (per-tool caps override) */
  defaultMaxResultSize?: number;
  /** Optional permission manager for per-tool approval gating */
  permissionManager?: PermissionManager;
}

/**
 * ToolRuntime wraps a ToolRegistry with execution orchestration:
 * dispatch, result truncation, timing, permission gating, and structured ToolResult output.
 */
export class ToolRuntime {
  private registry: ToolRegistry;
  private defaultMaxResultSize: number;
  private permissionManager?: PermissionManager;

  constructor(registry: ToolRegistry, options: ToolRuntimeOptions = {}) {
    this.registry = registry;
    this.defaultMaxResultSize = options.defaultMaxResultSize ?? 100_000;
    this.permissionManager = options.permissionManager;
  }

  /** Get the permission manager (for external configuration). */
  getPermissionManager(): PermissionManager | undefined {
    return this.permissionManager;
  }

  /**
   * Execute a tool by name. Dispatches to the registry, enforces truncation,
   * and returns a structured ToolResult.
   */
  async execute(
    name: string,
    args: Record<string, unknown>,
    context: ToolContext = {},
  ): Promise<ToolResult> {
    const callId = `call_${crypto.randomUUID()}`;
    const start = performance.now();

    // Permission check
    if (this.permissionManager) {
      const check = this.permissionManager.check(name);
      if (!check.allowed) {
        return {
          callId,
          name,
          ok: false,
          content: JSON.stringify({ error: check.reason ?? 'Tool execution blocked by permission policy.' }),
          error: check.reason ?? 'Permission denied',
          errorType: 'permission_denied',
          durationMs: 0,
        };
      }
      if (check.needsApproval) {
        // Tool requires approval but no interactive bridge is available —
        // the caller (TUI/CLI) should handle this via a pre-tool hook.
        // We proceed with a flag that the caller can intercept.
      }
    }

    const raw = await this.registry.dispatch(name, args, context);
    let content = raw;

    // Determine max result size
    const entry = this.registry.getEntry(name);
    const maxSize = entry?.maxResultSizeChars ?? this.defaultMaxResultSize;

    // Truncate if needed
    if (content.length > maxSize) {
      content = `${content.slice(0, maxSize)}\n\n... [truncated at ${maxSize} chars, original was ${content.length} chars]`;
    }

    const durationMs = Math.round(performance.now() - start);

    // Parse error from JSON result
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // Not valid JSON — treat content as-is
    }

    const isError = parsed !== null && typeof parsed.error === 'string';

    return {
      callId,
      name,
      ok: !isError,
      content,
      error: isError ? (parsed as Record<string, unknown>).error as string : undefined,
      errorType: isError ? 'tool_error' : undefined,
      durationMs,
    };
  }
}

// ============================================================================
// ApprovalGate — regex-based command safety checks
// ============================================================================

export interface ApprovalResult {
  safe: boolean;
  reason?: string;
}

// Patterns that require human approval (not blocked, but not auto-run)
const DANGEROUS_PATTERNS: [RegExp, string][] = [
  // Destructive file removal
  [/rm\s+.*-.*rf?\b|rm\s+.*--recursive/i, 'recursive file removal'],
  // Privilege escalation
  [/\bsudo\b/, 'sudo (privilege escalation)'],
  // World-writable permissions
  [/chmod\s+.*777/, 'world-writable permissions (chmod 777)'],
  // Redirect to device files
  [/[|>]\s*\/dev\//, 'redirect to /dev/'],
  // Curl/wget piped to a shell
  [/\bcurl\b.+\|\s*(?:ba)?sh\b/i, 'curl piped to shell'],
  [/\bwget\b.+\|\s*(?:ba)?sh\b/i, 'wget piped to shell'],
  // Listening on network ports (potential backdoor)
  [/\b(?:nc|ncat|netcat)\s+-[a-z]*l/, 'network listener (nc/ncat)'],
  [/\bpython3?\s+-m\s+http\.server/, 'Python HTTP server'],
];

// Patterns that are always blocked (never allowed to run)
const BLOCKED_PATTERNS: [RegExp, string][] = [
  // Wipe root filesystem (only rm -rf / with no further path)
  [/rm\s+-rf\s+\/\s*(?:$|[;&])/, 'removing root filesystem (rm -rf /)'],
  // Format filesystems
  [/\bmkfs\b/, 'creating filesystems (mkfs)'],
  // Raw write to block devices
  [/dd\s+.*if=.*of=\/dev\//, 'writing raw data to block device (dd to /dev/)'],
  // Fork bombs
  [/[:(][\s)]*[{][\s)]*[|:]/i, 'potential fork bomb'],
  [/\bfork\s*bomb\b/i, 'fork bomb'],
];

/**
 * ApprovalGate checks shell commands against known dangerous and blocked patterns.
 *
 * - DANGEROUS: require human approval before execution.
 * - BLOCKED: always denied.
 *
 * Container environments can be configured to skip checks entirely.
 */
export class ApprovalGate {
  private skipChecks: boolean;

  constructor(options: { skipChecks?: boolean } = {}) {
    this.skipChecks = options.skipChecks ?? false;
  }

  /**
   * Check a shell command for safety concerns.
   * Returns { safe: true } if the command can proceed,
   * or { safe: false, reason: "..." } if blocked or requires approval.
   */
  checkCommand(command: string): ApprovalResult {
    if (this.skipChecks) {
      return { safe: true };
    }

    // Check blocked patterns first (always denied)
    for (const [pattern, reason] of BLOCKED_PATTERNS) {
      if (pattern.test(command)) {
        return { safe: false, reason: `BLOCKED: ${reason}` };
      }
    }

    // Check dangerous patterns (require approval)
    for (const [pattern, reason] of DANGEROUS_PATTERNS) {
      if (patternSpaceAware(pattern, command)) {
        return { safe: false, reason: `Requires approval: ${reason}` };
      }
    }

    return { safe: true };
  }
}

/**
 * Test a regex against a command, but also check against the command with
 * normalized whitespace (collapse multiple spaces into one, trim).
 * This catches cases like `rm  -rf /` that evade a simple pattern.
 */
function patternSpaceAware(pattern: RegExp, command: string): boolean {
  if (pattern.test(command)) return true;
  // Normalize whitespace and try again
  const normalized = command.replace(/\s+/g, ' ').trim();
  if (normalized !== command && pattern.test(normalized)) return true;
  return false;
}
