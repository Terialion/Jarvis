// ============================================================================
// ToolRuntime + ApprovalGate — execution orchestration and command safety
// ============================================================================

import type { ToolResult } from '@jarvis/shared';
import { ToolRegistry, type ToolContext } from './registry.js';

// ============================================================================
// ToolRuntime
// ============================================================================

export interface ToolRuntimeOptions {
  /** Default max result characters before truncation (per-tool caps override) */
  defaultMaxResultSize?: number;
}

/**
 * ToolRuntime wraps a ToolRegistry with execution orchestration:
 * dispatch, result truncation, timing, and structured ToolResult output.
 */
export class ToolRuntime {
  private registry: ToolRegistry;
  private defaultMaxResultSize: number;

  constructor(registry: ToolRegistry, options: ToolRuntimeOptions = {}) {
    this.registry = registry;
    this.defaultMaxResultSize = options.defaultMaxResultSize ?? 100_000;
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
