// ============================================================================
// ToolRegistry — tool registration, lookup, and dispatch
// ============================================================================

/** Context passed to tool handlers during execution. */
export interface ToolContext {
  taskId?: string;
  sessionId?: string;
  signal?: AbortSignal;
}

/** A tool handler function. Returns a JSON string (or Promise<string> for async). */
export type ToolHandler = (
  args: Record<string, unknown>,
  context: ToolContext,
) => string | Promise<string>;

/** Descriptor for a registered tool. */
export interface ToolEntry {
  /** Unique tool name, e.g. "bash", "read_file" */
  name: string;
  /** Group name, e.g. "terminal", "file", "web" */
  toolset: string;
  /** OpenAI-format JSON Schema (includes name + parameters) */
  schema: Record<string, unknown>;
  /** Tool handler function */
  handler: ToolHandler;
  /** Availability check — if returns false, tool is hidden from definitions */
  checkFn?: () => boolean;
  /** Env vars that must be set for availability */
  requiresEnv?: string[];
  /** If true, handler returns Promise<string> */
  isAsync?: boolean;
  /** Human-readable description (falls back to schema.function.description) */
  description?: string;
  /** UI icon (emoji) */
  emoji?: string;
  /** Per-tool output size cap in characters */
  maxResultSizeChars?: number;
}

// ============================================================================
// ToolRegistry
// ============================================================================

export class ToolRegistry {
  private tools: Map<string, ToolEntry> = new Map();

  /**
   * Register a tool. Throws on duplicate unless both toolsets start with "mcp-"
   * (MCP override: later registration silently replaces earlier).
   */
  register(entry: ToolEntry): void {
    const existing = this.tools.get(entry.name);
    if (existing) {
      const isMcpOverride =
        existing.toolset.startsWith('mcp-') && entry.toolset.startsWith('mcp-');
      if (!isMcpOverride) {
        throw new Error(
          `Tool "${entry.name}" is already registered (toolset: "${existing.toolset}")`,
        );
      }
      // MCP override: silently replace
    }
    this.tools.set(entry.name, entry);
  }

  /** Look up a tool entry by name. */
  getEntry(name: string): ToolEntry | undefined {
    return this.tools.get(name);
  }

  /**
   * Dispatch a tool call. Calls the handler and returns its JSON result string.
   * Catches ALL exceptions and returns a JSON error object instead.
   * NEVER throws.
   */
  async dispatch(
    name: string,
    args: Record<string, unknown>,
    context: ToolContext = {},
  ): Promise<string> {
    const entry = this.tools.get(name);
    if (!entry) {
      return JSON.stringify({ error: `Tool not found: "${name}"` });
    }

    try {
      const result = entry.isAsync
        ? await entry.handler(args, context)
        : await Promise.resolve(entry.handler(args, context));
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `Tool execution failed: ${message}` });
    }
  }

  /**
   * Return OpenAI-format tool definitions.
   * Filters by checkFn availability and optional toolNames whitelist.
   * Returns: [{ type: "function", function: { name, description, parameters } }]
   */
  getDefinitions(toolNames?: string[]): Record<string, unknown>[] {
    const filtered = toolNames
      ? toolNames.map((n) => this.tools.get(n)).filter(Boolean) as ToolEntry[]
      : Array.from(this.tools.values());

    return filtered
      .filter((entry) => this.isAvailable(entry))
      .map((entry) => entry.schema);
  }

  /** Get all registered tool names. */
  getAllToolNames(): string[] {
    return Array.from(this.tools.keys());
  }

  /** Get tool names belonging to a toolset. */
  getToolNamesByToolset(toolset: string): string[] {
    const names: string[] = [];
    for (const [name, entry] of this.tools) {
      if (entry.toolset === toolset) {
        names.push(name);
      }
    }
    return names;
  }

  /** Number of registered tools. */
  size(): number {
    return this.tools.size;
  }

  // ---- private helpers ----

  /** Check whether a tool is available (checkFn passes, env vars set). */
  private isAvailable(entry: ToolEntry): boolean {
    // Check env var requirements
    if (entry.requiresEnv) {
      for (const envName of entry.requiresEnv) {
        if (!process.env[envName]) {
          return false;
        }
      }
    }
    // Check custom checkFn
    if (entry.checkFn) {
      return entry.checkFn();
    }
    return true;
  }
}
