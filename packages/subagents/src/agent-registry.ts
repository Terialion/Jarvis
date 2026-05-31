// ============================================================================
// Agent Registry — scan .jarvis/agents/*.md for agent definitions
// ============================================================================
//
// Each .md file uses YAML frontmatter to define agent metadata:
//
// ---
// name: researcher
// description: "Deep research agent"
// model: "deepseek-v3"
// reasoning_effort: "high"
// tools: [read_file, glob, grep, web_search]
// blocked_tools: [bash, write_file]
// max_steps: 30
// permission_mode: "auto-edit"
// ---
//
// System prompt is the markdown body after frontmatter.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, basename } from 'node:path';

export interface AgentDefinition {
  /** Unique agent name (from filename or frontmatter name) */
  name: string;
  /** Human-readable description */
  description: string;
  /** Model override for this agent */
  model?: string;
  /** Reasoning effort override */
  reasoningEffort?: string;
  /** Allowed tools (null = all tools) */
  tools: string[] | null;
  /** Blocked tools (always blocked regardless of tools list) */
  blockedTools: string[];
  /** Max steps for this agent */
  maxSteps?: number;
  /** Permission mode override */
  permissionMode?: string;
  /** System prompt (markdown body) */
  systemPrompt: string;
  /** Source file path */
  source: string;
}

/** Parse YAML frontmatter from a markdown file. Returns null if no frontmatter. */
function parseFrontmatter(content: string): { attrs: Record<string, unknown>; body: string } | null {
  const trimmed = content.trimStart();
  if (!trimmed.startsWith('---')) return null;

  const endIdx = trimmed.indexOf('\n---', 3);
  if (endIdx === -1) return null;

  const yamlBlock = trimmed.slice(3, endIdx).trim();
  const body = trimmed.slice(endIdx + 4).trim();

  // Simple YAML parser — handles key: value pairs and key: [array]
  const attrs: Record<string, unknown> = {};
  for (const line of yamlBlock.split('\n')) {
    const match = line.match(/^(\w+):\s*(.+)$/);
    if (!match) continue;
    const [, key, rawValue] = match;
    const val = rawValue.trim();

    // Array: [a, b, c]
    if (val.startsWith('[') && val.endsWith(']')) {
      attrs[key] = val.slice(1, -1).split(',').map((s) => s.trim().replace(/^["']|["']$/g, ''));
      continue;
    }

    // Quoted string
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      attrs[key] = val.slice(1, -1);
      continue;
    }

    // Number
    if (/^\d+$/.test(val)) {
      attrs[key] = parseInt(val, 10);
      continue;
    }

    // Boolean
    if (val === 'true') { attrs[key] = true; continue; }
    if (val === 'false') { attrs[key] = false; continue; }

    // Plain string
    attrs[key] = val;
  }

  return { attrs, body };
}

/**
 * Scan a directory for agent definition .md files.
 * Returns parsed AgentDefinition array.
 */
export function discoverAgents(dir: string): AgentDefinition[] {
  if (!existsSync(dir)) return [];

  const files = readdirSync(dir).filter((f) => f.endsWith('.md'));
  const agents: AgentDefinition[] = [];

  for (const file of files) {
    try {
      const filePath = join(dir, file);
      const content = readFileSync(filePath, 'utf-8');
      const parsed = parseFrontmatter(content);
      if (!parsed) continue;

      const { attrs, body } = parsed;
      const name = (attrs['name'] as string) ?? basename(file, '.md');

      const toolsRaw = attrs['tools'];
      const tools = Array.isArray(toolsRaw) ? toolsRaw as string[] : null;

      const blockedRaw = attrs['blocked_tools'];
      const blockedTools = Array.isArray(blockedRaw) ? blockedRaw as string[] : [];

      agents.push({
        name,
        description: (attrs['description'] as string) ?? '',
        model: attrs['model'] as string | undefined,
        reasoningEffort: attrs['reasoning_effort'] as string | undefined,
        tools,
        blockedTools,
        maxSteps: typeof attrs['max_steps'] === 'number' ? attrs['max_steps'] as number : undefined,
        permissionMode: attrs['permission_mode'] as string | undefined,
        systemPrompt: body,
        source: filePath,
      });
    } catch {
      // Skip files that can't be read/parsed
    }
  }

  return agents;
}

/**
 * Merge multiple agent directories (project > user > builtin).
 * Later entries override earlier ones with the same name.
 */
export function mergeAgentDirectories(...dirs: string[]): Map<string, AgentDefinition> {
  const agents = new Map<string, AgentDefinition>();
  for (const dir of dirs) {
    for (const agent of discoverAgents(dir)) {
      agents.set(agent.name, agent);
    }
  }
  return agents;
}
