// ============================================================================
// HookRegistry — lifecycle hook registration and execution
// ============================================================================

import type {
  HookSpec,
  HookStage,
  HookContext,
  HookResult,
  HookMatcher,
} from './models.js';

// ============================================================================
// HookRegistry
// ============================================================================

export class HookRegistry {
  private hooks: HookSpec[] = [];

  // ========================================================================
  // Registration
  // ========================================================================

  /** Register a hook spec. Hooks fire in registration order. */
  register(spec: HookSpec): void {
    this.hooks.push(spec);
  }

  /** Remove a hook by name. Returns true if it was found and removed. */
  unregister(name: string): boolean {
    const idx = this.hooks.findIndex((h) => h.name === name);
    if (idx === -1) return false;
    this.hooks.splice(idx, 1);
    return true;
  }

  /** Remove all registered hooks. */
  clear(): void {
    this.hooks.length = 0;
  }

  /** Number of registered hooks. */
  get size(): number {
    return this.hooks.length;
  }

  /** List hook names, optionally filtered by stage. */
  list(stage?: HookStage): string[] {
    const filtered = stage
      ? this.hooks.filter((h) => h.stage === stage)
      : this.hooks;
    return filtered.map((h) => h.name);
  }

  // ========================================================================
  // Execution
  // ========================================================================

  /**
   * Run all hooks for a given stage with the provided context.
   *
   * Each hook's matcher (if present) must match the context for the hook to fire.
   * Execution stops at the first denial — subsequent hooks are skipped.
   *
   * Returns the first denial result, or an allow result if all hooks allow.
   */
  async run(stage: HookStage, context: HookContext = {}): Promise<HookResult> {
    for (const hook of this.hooks) {
      if (hook.stage !== stage) continue;

      // Check matcher
      if (hook.matcher && !this._matches(hook.matcher, context)) {
        continue;
      }

      const result = await hook.handler(context);

      // Short-circuit on denial
      if (!result.allowed) {
        return result;
      }
    }

    return { allowed: true };
  }

  // ========================================================================
  // Convenience: pre/post tool use
  // ========================================================================

  /**
   * Run pre_tool_use hooks. Returns first denial or allowed.
   */
  async runPreToolUse(context: HookContext): Promise<HookResult> {
    return this.run('pre_tool_use', context);
  }

  /**
   * Run post_tool_use hooks. Errors are swallowed (audit-only).
   * Never denies — post_tool_use is observational.
   */
  async runPostToolUse(context: HookContext): Promise<HookResult> {
    try {
      return await this.run('post_tool_use', context);
    } catch {
      return { allowed: true };
    }
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private _matches(matcher: HookMatcher, context: HookContext): boolean {
    if (matcher.toolName !== undefined && matcher.toolName !== context.toolName) {
      return false;
    }
    return true;
  }
}
