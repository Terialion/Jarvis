import { execSync } from 'node:child_process';
import { readFileSync, existsSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { platform, arch, totalmem, freemem, uptime } from 'node:os';
import type { Message } from '../vendor/ui/MessageList.js';
import type { SkillRegistry } from '@jarvis/skills';
import { ConversationSummarizer, parseModelName, buildSystemPrompt as buildSystemPromptFn, addUserModel, removeUserModel, findModel } from '@jarvis/agent';
import { renderSlashResultText, type ChatMessage, type SlashResult } from '@jarvis/shared';
import {
  JARVIS_REASONING_EFFORTS,
  loadJarvisConfig,
  saveJarvisConfig,
  getJarvisConfigPath,
  normalizeJarvisReasoningEffort,
} from '@jarvis/shared';
import { buildContextPanelLines, resolveContextMode, type SkillTokenEntry, type ToolTokenEntry } from '../context-panel.js';
import { saveSettings, type UserSettings } from '../settings-store.js';
import { estimateTokensFromText, estimateMemoryEntries } from '../utils/token-estimation.js';
import { formatMcpDiagnostics, refreshMcpStatuses } from '../utils/mcp-diagnostics.js';
import { REVIEW_PROMPT, SECURITY_REVIEW_PROMPT, INIT_CLAUDE_MD_TEMPLATE } from '../system-prompt.js';
import { makeSysMsg, type SlashCommandDef, type SlashCommandCtx, type REPLCommandDef, type LiveContextUsage } from './types.js';
import { resolveModelCredentials } from '../utils/credentials.js';

export { makeSysMsg };
export type { SlashCommandDef, SlashCommandCtx, REPLCommandDef, LiveContextUsage };

function toSlashText(result: SlashResult): string {
  return renderSlashResultText(result);
}

export const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    name: 'help',
    description: 'Show available commands',
    usage: '/help',
    handler: (_args, _ctx) => {
      return [
        {
          kind: 'section',
          title: 'Available commands',
          lines: SLASH_COMMANDS.map((cmd) => `/${cmd.name} - ${cmd.description}`),
        },
      ];
    },
  },
  {
    name: 'clear',
    description: 'Clear conversation history and start a new session',
    usage: '/clear',
    handler: async (_args, ctx) => {
      ctx.historyRef.current = [];
      ctx.modifiedFilesRef.current = new Set();
      ctx.setMessages([]);
      if (ctx.store) {
        const sid = `session_${crypto.randomUUID().slice(0, 12)}`;
        await ctx.store.createSession(sid, { cwd: ctx.cwd });
        ctx.sid = sid;
      }
      return 'Conversation cleared. New session started.';
    },
  },
  {
    name: 'sessions',
    description: 'List recent sessions for this directory',
    usage: '/sessions',
    handler: async (_args, ctx) => {
      if (ctx.store) {
        const sessionIds = await ctx.store.listSessions();
        const lines: string[] = [];
        for (const id of sessionIds.slice(-10).reverse()) {
          try {
            const sc = await ctx.store.getSidecar(id);
            const cwd = sc.cwd ?? '?';
            const title = sc.title ?? '(no title)';
            const updated = sc.updated_at.slice(0, 19).replace('T', ' ');
            const marker = id === ctx.sid ? ' *' : '  ';
            const shortId = id.slice(-16);
            lines.push(`${marker} ${shortId}  ${updated}  ${cwd}  ${title}`);
          } catch {
            lines.push(`    ${id.slice(-16)}  (no sidecar)`);
          }
        }
        if (lines.length > 0) return `Sessions (recent first, * = current):\n\n${lines.join('\n')}`;
        return 'No sessions found.';
      }
      try {
        const sessionsDir = join(process.cwd(), '.jarvis', 'sessions');
        if (existsSync(sessionsDir)) {
          const files = readdirSync(sessionsDir, { withFileTypes: true })
            .filter((f) => f.isFile() && f.name.endsWith('.json'))
            .slice(-10).reverse();
          if (files.length === 0) return 'No sessions found in .jarvis/sessions/.';
          let output = `Sessions from .jarvis/sessions/ (${files.length}):\n\n`;
          for (const f of files) {
            output += `  ${f.name.replace('.json', '')}\n`;
          }
          return output.trim();
        }
      } catch { /* ignore */ }
      return 'No session store available and no .jarvis/sessions/ directory found.';
    },
  },
  {
    name: 'diff',
    description: 'Show uncommitted git changes',
    usage: '/diff',
    handler: (_args, ctx) => {
      try {
        const stat = execSync('git diff --stat', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 });
        if (!stat.trim()) return 'No uncommitted changes.';
        const diff = execSync('git diff', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 });
        const truncated = diff.length > 16000 ? diff.slice(0, 16000) + '\n... (truncated)' : diff;
        return truncated || 'No changes.';
      } catch (e) {
        return `Error running git diff: ${e instanceof Error ? e.message : String(e)}`;
      }
    },
  },
  {
    name: 'context',
    description: 'Show current session context info',
    usage: '/context [mcp|memory|skills|tools|all]',
    handler: (args, ctx) => {
      try { ctx.getAgent(); } catch { /* best-effort init */ }
      const msgCount = ctx.historyRef.current.length;
      const totalChars = ctx.historyRef.current.reduce((sum, m) => sum + m.content.length, 0);
      const messageTokens = Math.ceil(totalChars / 4);
      const snapshot = ctx.tokenTrackerRef.current?.snapshot();
      const live = ctx.liveContextUsageRef.current;
      const contextWindow = live?.contextWindow ?? snapshot?.contextWindow ?? 200_000;
      const shortSid = (ctx.sid ?? 'none').slice(-16);
      const modelName = parseModelName(ctx.modelRef.current).cleanName;
      const defaultSystemPrompt = buildSystemPromptFn(modelName);
      const systemPromptText = ctx.systemPromptRef.current?.trim()
        ? `${defaultSystemPrompt}\n\n${ctx.systemPromptRef.current}`
        : defaultSystemPrompt;
      const systemPromptTokens = estimateTokensFromText(systemPromptText);
      const memoryEntries = estimateMemoryEntries(ctx.cwd);
      const skillEntries: SkillTokenEntry[] = (ctx.skills?.listLoadable() ?? []).map((skill) => ({
        name: skill.name,
        source: skill.source,
        tokens: estimateTokensFromText(`${skill.name}\n${skill.description}`),
      }));
      const allToolSchemas = ctx.toolsRef.current?.getDefinitions() ?? [];
      const toolEntries: ToolTokenEntry[] = allToolSchemas.map((schema) => {
        const fn = (schema as { function?: { name?: string } }).function?.name ?? 'unknown';
        const serialized = JSON.stringify(schema);
        return { name: fn, tokens: estimateTokensFromText(serialized), isMcp: typeof fn === 'string' && fn.toLowerCase().includes('mcp') };
      });
      const memoryTokens = memoryEntries.reduce((acc, item) => acc + item.tokens, 0);
      const skillTokens = skillEntries.reduce((acc, item) => acc + item.tokens, 0);
      const toolTokens = toolEntries.reduce((acc, item) => acc + item.tokens, 0);
      const estimatedTotalTokens = live?.estimatedTotalTokens ?? (systemPromptTokens + toolTokens + memoryTokens + skillTokens + messageTokens);
      const resolvedSystemPromptTokens = live?.systemPromptTokens ?? systemPromptTokens;
      const resolvedMessageTokens = live?.conversationTokens ?? messageTokens;
      return [
        {
          kind: 'text',
          text: buildContextPanelLines({
            mode: resolveContextMode(args), modelName, sessionId: shortSid, messageCount: msgCount,
            uiMessageCount: ctx.messages.length, contextWindow, estimatedTotalTokens,
            providerReportedTokens: live?.usedTokens ?? snapshot?.totalTokens,
            systemPromptTokens: resolvedSystemPromptTokens, messageTokens: resolvedMessageTokens,
            projectContextTokens: live?.projectContextTokens, systemToolsTokens: live?.toolSchemasTokens,
            mcpToolsTokens: live?.mcpToolsTokens, memoryTokens: live?.memoryTokens,
            skillsTokens: live?.skillsTokens, conversationTokens: live?.conversationTokens,
            memoryEntries, skillEntries, toolEntries,
            mcpConfigured: ctx.mcpConfiguredRef.current.map((e) => ({ id: e.id, plugin: e.plugin, command: e.config.command })),
            mcpStatuses: ctx.mcpStatusesRef.current.map((s) => ({ id: s.id, state: s.state, serverName: s.serverName, toolCount: s.toolCount, resourceCount: s.resourceCount, error: s.error })),
          }).join('\n'),
        },
      ];
    },
  },
  {
    name: 'compact',
    description: 'Summarize conversation history to free context space',
    usage: '/compact',
    handler: (_args, ctx) => {
      const history = ctx.historyRef.current;
      if (history.length < 6) return 'Not enough messages to compact.';
      const summarizer = new ConversationSummarizer({ maxSummaryChars: 2000 });
      const summary = summarizer.summarize(history);
      const compacted = summarizer.compactSummary(summary);
      const lastUserIdx = history.length - 2;
      const lastMessages = history.slice(Math.max(0, lastUserIdx));
      const compactMsg: ChatMessage = { role: 'system', content: `<conversation-summary>\n${compacted}\n</conversation-summary>`, messageId: `compact_${Date.now()}` };
      ctx.historyRef.current = [compactMsg, ...lastMessages];
      return `Compacted ${history.length} messages into a summary (${compacted.length} chars). Kept last exchange.`;
    },
  },
  {
    name: 'model',
    description: 'Show or set the current model. /model add <slug> <name> <provider> <ctx> to register a custom model.',
    usage: '/model [model-name | add <slug> <name> <provider> <ctx> | remove <slug>]',
    handler: (args, ctx) => {
      if (args[0] === 'add' && args.length >= 5) {
        const [, slug, ...rest] = args;
        const ctxWindow = parseInt(rest[rest.length - 1]!, 10);
        const provider = rest[rest.length - 2]!;
        const displayName = rest.slice(0, -2).join(' ');
        if (!slug || !displayName || !provider || isNaN(ctxWindow)) {
          return 'Usage: /model add <slug> <display-name> <provider> <context-window>\nExample: /model add qwen3.5-thinking "Qwen 3.5 Thinking" qwen 128000';
        }
        const added = addUserModel({ slug, displayName, provider, contextWindow: ctxWindow, maxContextWindow: ctxWindow });
        return added ? `Model "${displayName}" (${slug}) added to user catalog. Use /model to select it.` : `Model "${slug}" already exists in the catalog.`;
      }
      if (args[0] === 'remove' && args.length >= 2) {
        const slug = args[1]!;
        const removed = removeUserModel(slug);
        return removed ? `Model "${slug}" removed from user catalog.` : `Model "${slug}" not found in user catalog (built-in models cannot be removed).`;
      }
      if (args.length > 0) {
        ctx.modelRef.current = args[0];
        // Save both model and active_model to ensure it takes effect
        saveSettings({ model: args[0], active_model: args[0] });

        // Resolve provider credentials for the new model
        const creds = resolveModelCredentials(args[0]);
        ctx.apiKeyRef.current = creds.apiKey;
        ctx.baseURLRef.current = creds.baseURL;

        const providerName = findModel(args[0])?.provider;

        ctx.invalidateAgent();
        ctx.onModelChange?.(); // Trigger re-render for status bar
        return `Model set to: ${args[0]} (provider: ${providerName ?? 'default'}, effective on next turn)`;
      }
      return `Current model: ${parseModelName(ctx.modelRef.current).cleanName}`;
    },
  },
  {
    name: 'review',
    description: 'Code-review uncommitted changes',
    usage: '/review',
    handler: async (_args, ctx) => {
      let diff: string;
      try { diff = execSync('git diff', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 }); } catch { return 'Error: could not run git diff.'; }
      if (!diff.trim()) return 'No uncommitted changes to review.';
      const truncated = diff.length > 12000 ? diff.slice(0, 12000) + '\n... (truncated)' : diff;
      ctx.setIsLoading(true);
      try {
        const agent = ctx.getAgent();
        const result = await agent.runTurn(`${REVIEW_PROMPT}\n\n---\n${truncated}\n---`);
        return result.finalAnswer || 'Review complete (no text response).';
      } catch (e) { return `Review failed: ${e instanceof Error ? e.message : String(e)}`; }
      finally { ctx.setIsLoading(false); }
    },
  },
  {
    name: 'memory',
    description: 'Show or search project memory',
    usage: '/memory [search-term]',
    handler: (_args, ctx) => {
      const searchTerm = _args.join(' ').toLowerCase();
      const sources: string[] = [];
      const claudeMdPath = join(ctx.cwd, 'CLAUDE.md');
      if (existsSync(claudeMdPath)) {
        const content = readFileSync(claudeMdPath, 'utf-8');
        if (!searchTerm) { sources.push(`CLAUDE.md (${content.length} chars)`); }
        else if (content.toLowerCase().includes(searchTerm)) {
          const lines = content.split('\n').filter((l) => l.toLowerCase().includes(searchTerm));
          sources.push(`CLAUDE.md matches:\n${lines.slice(0, 10).map((l) => `  ${l.trim()}`).join('\n')}`);
        }
      }
      const memDir = join(ctx.cwd, '.jarvis', 'memory');
      if (existsSync(memDir)) {
        try {
          for (const f of readdirSync(memDir)) {
            if (!f.endsWith('.md')) continue;
            const content = readFileSync(join(memDir, f), 'utf-8');
            if (!searchTerm) { sources.push(`.jarvis/memory/${f} (${content.length} chars)`); }
            else if (content.toLowerCase().includes(searchTerm)) {
              const lines = content.split('\n').filter((l) => l.toLowerCase().includes(searchTerm));
              sources.push(`.jarvis/memory/${f} matches:\n${lines.slice(0, 10).map((l) => `  ${l.trim()}`).join('\n')}`);
            }
          }
        } catch { /* ignore */ }
      }
      if (sources.length === 0) return searchTerm ? `No memory entries matching "${searchTerm}".` : 'No memory files found (CLAUDE.md or .jarvis/memory/).';
      return sources.join('\n\n');
    },
  },
  {
    name: 'rewind',
    description: 'Restore files modified by agent to their git state',
    usage: '/rewind',
    handler: (_args, ctx) => {
      const files = [...ctx.modifiedFilesRef.current];
      if (files.length === 0) return 'No files have been modified by the agent in this session.';
      try {
        for (const f of files) { execSync(`git checkout -- "${f}"`, { cwd: ctx.cwd, encoding: 'utf-8', timeout: 5000 }); }
        ctx.modifiedFilesRef.current = new Set();
        return `Restored ${files.length} file(s):\n${files.map((f) => `  ${f}`).join('\n')}`;
      } catch (e) { return `Rewind failed: ${e instanceof Error ? e.message : String(e)}`; }
    },
  },
  {
    name: 'doctor',
    description: 'Run environment diagnostics',
    usage: '/doctor',
    handler: (_args, ctx) => {
      const lines: string[] = ['Environment diagnostics:\n'];
      lines.push(`Platform: ${platform()} ${arch()}`, `Node.js: ${process.version}`, `CWD: ${ctx.cwd}`);
      try { lines.push(`npm: ${execSync('npm --version', { encoding: 'utf-8', timeout: 5000 }).trim()}`); } catch { lines.push('npm: (not found)'); }
      try { lines.push(`Git: ${execSync('git --version', { encoding: 'utf-8', timeout: 5000 }).trim()}`); } catch { lines.push('Git: (not found)'); }
      try {
        const total = totalmem(), free = freemem(), used = total - free;
        const gb = (n: number) => (n / 1024 ** 3).toFixed(1);
        lines.push(`Memory: ${gb(used)}GB / ${gb(total)}GB (${Math.round((used / total) * 100)}%)`);
      } catch { lines.push('Memory: (unavailable)'); }
      try {
        const up = uptime(); lines.push(`Uptime: ${Math.floor(up / 3600)}h ${Math.floor((up % 3600) / 60)}m`);
      } catch { lines.push('Uptime: (unavailable)'); }
      try { lines.push(`Git changes: ${execSync('git status --short', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 5000 }).split('\n').filter(Boolean).length} file(s)`); }
      catch { lines.push('Git: (not a repo or error)'); }
      return lines.join('\n');
    },
  },
  {
    name: 'mcp',
    description: 'Show MCP server diagnostics',
    usage: '/mcp [full]',
    handler: async (args, ctx) => {
      try { ctx.getAgent(); } catch { /* best-effort */ }
      const mode = (args[0] ?? '').toLowerCase();
      if (mode === 'reload') {
        const client = ctx.mcpClientRef?.current;
        if (client) client.disconnectAll();
        ctx.invalidateAgent();
        return 'MCP connections reset. Reconnect on next prompt.';
      }
      let statuses = ctx.mcpStatusesRef.current;
      if (statuses.length === 0 || statuses.every((s) => s.state === 'connecting' || s.state === 'retrying')) {
        statuses = await refreshMcpStatuses(ctx);
      }
      if (mode === 'full') {
        return [
          {
            kind: 'text',
            text: formatMcpDiagnostics(ctx.mcpConfiguredRef.current, statuses, ctx.mcpClientRef.current),
          },
        ];
      }
      const totalCount = statuses.length;
      const readyCount = statuses.filter((s) => s.state === 'ready' || s.state === 'degraded').length;
      const firstError = statuses.find((s) => s.error)?.error;
      if (totalCount === 0) return 'No MCP servers configured. Run mcp_bootstrap to add one, then restart Jarvis.';
      if (firstError) return `Pinned MCP summary under status line (${readyCount}/${totalCount} ready). First error: ${firstError}. Run /mcp full for full diagnostics table.`;
      return `Pinned MCP summary under status line (${readyCount}/${totalCount} ready). Run /mcp full for full diagnostics table.`;
    },
  },
  {
    name: 'config',
    description: 'Show or set configuration',
    usage: '/config [key] [value]',
    handler: (args, ctx) => {
      const userConfig = loadJarvisConfig();
      const configPath = getJarvisConfigPath();
      const maskSecret = (value?: string) => (value ? `${value.slice(0, 4)}...${value.slice(-4)}` : '(not set)');
      if (args.length === 0) {
        const providerKeys = userConfig.providers ? Object.keys(userConfig.providers) : [];
        const lines = ['Current configuration:\n',
          `  config-path  = ${configPath}`, `  model       = ${ctx.modelRef.current}`,
          `  base-url    = ${ctx.baseURLRef.current ?? '(not set)'}`, `  api-key     = ${maskSecret(ctx.apiKeyRef.current)}`,
          `  effort      = ${ctx.reasoningEffortRef.current}`, `  max-turns   = ${ctx.maxTurns}`,
          `  output-style = ${ctx.outputStyleRef.current}`, `  permissions = ${ctx.permissionModeRef.current}`,
          `  system-prompt = ${ctx.systemPromptRef.current ? '(configured)' : '(not set)'}`,
          `  session     = ${(ctx.sid ?? 'none').slice(-16)}`, `  cwd         = ${ctx.cwd}`];
        if (providerKeys.length > 0) {
          lines.push('', `Providers (${providerKeys.join(', ')}):`);
          for (const [name, p] of Object.entries(userConfig.providers ?? {})) {
            lines.push(`  ${name}: base-url=${p.base_url ?? '(inherit)'}, api-key=${maskSecret(p.api_key)}`);
          }
        }
        lines.push('', 'Stored user config:',
          `  active-model = ${userConfig.active_model ?? userConfig.model ?? '(not set)'}`,
          `  base-url    = ${userConfig.base_url ?? '(not set)'}`, `  api-key     = ${maskSecret(userConfig.api_key)}`,
          `  effort      = ${userConfig.reasoning_effort ?? '(not set)'}`, `  max-turns   = ${userConfig.max_turns ?? '(not set)'}`,
          `  output-style = ${userConfig.output_style ?? '(not set)'}`, `  permissions = ${userConfig.permission_mode ?? '(not set)'}`,
          `  system-prompt = ${userConfig.system_prompt ? '(configured)' : '(not set)'}`);
        return lines.join('\n');
      }
      const key = args[0].toLowerCase();
      const value = args.slice(1).join(' ').trim();
      if (key === 'model') {
        if (!value) return `model = ${ctx.modelRef.current}`;
        ctx.modelRef.current = value; saveJarvisConfig({ active_model: value });

        const creds = resolveModelCredentials(value);
        ctx.apiKeyRef.current = creds.apiKey;
        ctx.baseURLRef.current = creds.baseURL;

        const providerName = findModel(value)?.provider;
        ctx.invalidateAgent();
        ctx.onModelChange?.();
        return `model = ${value} (provider: ${providerName ?? 'default'}, effective next turn)`;
      }
      if (key === 'base-url') { if (!value) return `base-url = ${ctx.baseURLRef.current ?? '(not set)'}`; ctx.baseURLRef.current = value; saveJarvisConfig({ base_url: value }); return `base-url = ${value} (effective next launch)`; }
      if (key === 'api-key') { if (!value) return `api-key = ${maskSecret(ctx.apiKeyRef.current)}`; ctx.apiKeyRef.current = value; saveJarvisConfig({ api_key: value }); return 'api-key saved (effective next launch)'; }
      if (key === 'effort' || key === 'reasoning-effort') {
        if (!value) return `effort = ${ctx.reasoningEffortRef.current}`;
        const normalized = normalizeJarvisReasoningEffort(value);
        if (!normalized) return `Invalid effort. Options: ${JARVIS_REASONING_EFFORTS.join(', ')}`;
        ctx.reasoningEffortRef.current = normalized; saveSettings({ reasoning_effort: normalized }); ctx.invalidateAgent();
        return `effort = ${normalized} (effective next turn)`;
      }
      if (key === 'output-style') {
        if (!value) return `output-style = ${ctx.outputStyleRef.current}`;
        if (!['default', 'concise', 'verbose'].includes(value)) return 'Invalid style. Options: default, concise, verbose';
        ctx.outputStyleRef.current = value; saveSettings({ output_style: value as UserSettings['output_style'] }); return `output-style = ${value}`;
      }
      if (key === 'permissions') {
        if (!value) return `permissions = ${ctx.permissionModeRef.current}`;
        if (!['workspace_write', 'accept_edits', 'bypass'].includes(value)) return 'Invalid permission mode. Options: workspace_write, accept_edits, bypass';
        ctx.permissionModeRef.current = value; saveSettings({ permission_mode: value as UserSettings['permission_mode'] }); return `permissions = ${value}`;
      }
      if (key === 'max-turns') {
        if (!value) return `max-turns = ${ctx.maxTurns}`;
        const parsed = Number.parseInt(value, 10);
        if (!Number.isFinite(parsed) || parsed <= 0) return 'max-turns must be a positive integer.';
        saveSettings({ max_turns: parsed }); return `max-turns = ${parsed} (effective next launch)`;
      }
      if (key === 'system-prompt') {
        if (!value) return `system-prompt = ${ctx.systemPromptRef.current ? '(configured)' : '(not set)'}`;
        ctx.systemPromptRef.current = value; saveJarvisConfig({ system_prompt: value }); return 'system-prompt saved (effective next launch)';
      }
      return 'Unknown config key. Available: model, base-url, api-key, effort, output-style, permissions, max-turns, system-prompt';
    },
  },
  {
    name: 'mode',
    description: 'Show or switch permission mode (like CC/Codex)',
    usage: '/mode [suggest|auto-edit|full-auto|plan]',
    handler: (args, ctx) => {
      const MODE_MAP: Record<string, { perm: string; label: string; description: string }> = {
        'suggest': { perm: 'workspace_write', label: 'suggest', description: 'All changes require approval (default)' },
        'auto-edit': { perm: 'accept_edits', label: 'auto-edit', description: 'File edits auto-approved, bash needs approval' },
        'full-auto': { perm: 'bypass', label: 'full-auto', description: 'Everything auto-approved (use with caution)' },
        'plan': { perm: 'workspace_write', label: 'plan', description: 'Read-only exploration, no writes allowed' },
        'workspace_write': { perm: 'workspace_write', label: 'suggest', description: 'All changes require approval' },
        'accept_edits': { perm: 'accept_edits', label: 'auto-edit', description: 'File edits auto-approved' },
        'bypass': { perm: 'bypass', label: 'full-auto', description: 'Everything auto-approved' },
      };
      const reverseMap: Record<string, string> = { 'workspace_write': 'suggest', 'accept_edits': 'auto-edit', 'bypass': 'full-auto' };
      if (args.length === 0) {
        const current = reverseMap[ctx.permissionModeRef.current] ?? ctx.permissionModeRef.current;
        return `Current mode: ${current}\n\nAvailable modes:\n  suggest     - All changes require approval (default)\n  auto-edit   - File edits auto-approved, bash needs approval\n  full-auto   - Everything auto-approved (use with caution)\n  plan        - Read-only exploration, no writes allowed\n\nUsage: /mode <name>`;
      }
      const input = args[0].toLowerCase();
      const entry = MODE_MAP[input];
      if (!entry) return `Unknown mode "${input}". Options: suggest, auto-edit, full-auto, plan`;
      ctx.permissionModeRef.current = entry.perm; saveSettings({ permission_mode: entry.perm as UserSettings['permission_mode'] }); ctx.invalidateAgent();
      return `Mode: ${entry.label} - ${entry.description}`;
    },
  },
  {
    name: 'effort',
    description: 'Show or set reasoning effort',
    usage: '/effort [auto|low|medium|high|xhigh|max]',
    handler: (args, ctx) => {
      if (args.length === 0) return `Reasoning effort: ${ctx.reasoningEffortRef.current} (available: ${JARVIS_REASONING_EFFORTS.join(', ')})`;
      const normalized = normalizeJarvisReasoningEffort(args[0]);
      if (!normalized) return `Invalid effort "${args[0]}". Options: ${JARVIS_REASONING_EFFORTS.join(', ')}`;
      ctx.reasoningEffortRef.current = normalized; saveSettings({ reasoning_effort: normalized }); ctx.invalidateAgent();
      return `Reasoning effort set to: ${normalized} (effective next turn)`;
    },
  },
  {
    name: 'output-style',
    description: 'Set output style: default, concise, or verbose',
    usage: '/output-style [default|concise|verbose]',
    handler: (args, ctx) => {
      const validStyles = ['default', 'concise', 'verbose'];
      if (args.length === 0) return `Output style: ${ctx.outputStyleRef.current} (available: ${validStyles.join(', ')})`;
      const style = args[0].toLowerCase();
      if (!validStyles.includes(style)) return `Invalid style "${style}". Options: ${validStyles.join(', ')}`;
      ctx.outputStyleRef.current = style; saveSettings({ output_style: style as UserSettings['output_style'] });
      return `Output style set to: ${style}`;
    },
  },
  {
    name: 'security-review',
    description: 'Security audit of uncommitted changes',
    usage: '/security-review',
    handler: async (_args, ctx) => {
      let diff: string;
      try { diff = execSync('git diff', { cwd: ctx.cwd, encoding: 'utf-8', timeout: 10000 }); } catch { return 'Error: could not run git diff.'; }
      if (!diff.trim()) return 'No uncommitted changes to audit.';
      const truncated = diff.length > 12000 ? diff.slice(0, 12000) + '\n... (truncated)' : diff;
      ctx.setIsLoading(true);
      try {
        const agent = ctx.getAgent();
        const result = await agent.runTurn(`${SECURITY_REVIEW_PROMPT}\n\n---\n${truncated}\n---`);
        return result.finalAnswer || 'Security review complete (no text response).';
      } catch (e) { return `Security review failed: ${e instanceof Error ? e.message : String(e)}`; }
      finally { ctx.setIsLoading(false); }
    },
  },
  {
    name: 'init',
    description: 'Initialize project with CLAUDE.md and .jarvis config',
    usage: '/init',
    handler: (_args, ctx) => {
      const created: string[] = [];
      const claudeMd = join(ctx.cwd, 'CLAUDE.md');
      const jarvisDir = join(ctx.cwd, '.jarvis');
      try {
        if (!existsSync(claudeMd)) { writeFileSync(claudeMd, INIT_CLAUDE_MD_TEMPLATE, 'utf-8'); created.push('CLAUDE.md'); }
        else created.push('CLAUDE.md (already exists, skipped)');
      } catch (e) { created.push(`CLAUDE.md (error: ${e instanceof Error ? e.message : String(e)})`); }
      try {
        if (!existsSync(jarvisDir)) { mkdirSync(jarvisDir, { recursive: true }); created.push('.jarvis/'); }
        else created.push('.jarvis/ (already exists)');
      } catch (e) { created.push(`.jarvis/ (error: ${e instanceof Error ? e.message : String(e)})`); }
      return `Project initialized:\n${created.map((f) => `  ${f}`).join('\n')}`;
    },
  },
  {
    name: 'permissions',
    description: 'Show or set tool permission mode',
    usage: '/permissions [workspace_write|accept_edits|bypass]',
    handler: (args, ctx) => {
      const modes = ['workspace_write', 'accept_edits', 'bypass'];
      if (args.length === 0) return `Permission mode: ${ctx.permissionModeRef.current}\nAvailable: ${modes.join(', ')}`;
      const mode = args[0].toLowerCase();
      if (!modes.includes(mode)) return `Invalid mode "${mode}". Options: ${modes.join(', ')}`;
      ctx.permissionModeRef.current = mode; saveSettings({ permission_mode: mode as UserSettings['permission_mode'] });
      return `Permission mode set to: ${mode}`;
    },
  },
  {
    name: 'skills',
    description: 'List available skills with descriptions',
    usage: '/skills [search]',
    handler: (_args, ctx) => {
      if (!ctx.skills) return 'Skills not loaded yet.';
      const all = ctx.skills.listLoadable();
      const search = _args.join(' ').toLowerCase();
      const filtered = search ? all.filter((s) => s.name.toLowerCase().includes(search) || s.description.toLowerCase().includes(search)) : all;
      if (filtered.length === 0) return `No skills matching "${search}".`;
      const lines = filtered.map((s) => {
        const tagStr = s.tags?.length ? ` [${s.tags.join(', ')}]` : '';
        return `  ${s.name}${tagStr} - ${s.description}`;
      });
      const header = search ? `Skills matching "${search}" (${filtered.length}):` : `Available skills (${filtered.length}):`;
      return `${header}\n\n${lines.join('\n')}`;
    },
  },
];

export function resolveSlashCommand(input: string): { command: SlashCommandDef; args: string[] } | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) return null;
  const parts = trimmed.slice(1).split(/\s+/);
  const name = parts[0]?.toLowerCase();
  const args = parts.slice(1);
  const command = SLASH_COMMANDS.find((c) => c.name === name) ?? null;
  return command ? { command, args } : null;
}

export function buildReplCommands(
  ctx: SlashCommandCtx,
  setMessages: (v: Message[] | ((prev: Message[]) => Message[])) => void,
  skills?: SkillRegistry | null,
  setModelSelectorOpen?: (open: boolean) => void,
  setEffortSelectorOpen?: (open: boolean) => void,
  setHelpPopupOpen?: (open: boolean) => void,
): REPLCommandDef[] {
  const builtins = SLASH_COMMANDS.map((cmd) => {
    if (cmd.name === 'help') {
      return {
        name: cmd.name, description: cmd.description,
        onExecute: (rawArgs: string, fullInput: string) => {
          if (setHelpPopupOpen) { setHelpPopupOpen(true); return; }
          const userMsg: Message = { id: `cmd_${Date.now()}`, role: 'user', content: fullInput, timestamp: Date.now() };
          const result = cmd.handler(rawArgs ? rawArgs.split(/\s+/) : [], ctx);
          if (result instanceof Promise) { result.then((value) => setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(value))])); }
          else { setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(result))]); }
        },
      };
    }
    if (cmd.name === 'effort') {
      return {
        name: cmd.name, description: cmd.description,
        onExecute: (rawArgs: string, fullInput: string) => {
          const userMsg: Message = { id: `cmd_${Date.now()}`, role: 'user', content: fullInput, timestamp: Date.now() };
          const args = rawArgs ? rawArgs.split(/\s+/) : [];
          if (args.length === 0 && setEffortSelectorOpen) { setMessages((prev) => [...prev, userMsg]); setEffortSelectorOpen(true); return; }
          const result = cmd.handler(args, ctx);
          if (result instanceof Promise) { result.then((value) => setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(value))])); }
          else { setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(result))]); }
        },
      };
    }
    if (cmd.name === 'model') {
      return {
        name: cmd.name, description: cmd.description,
        onExecute: (rawArgs: string, fullInput: string) => {
          const userMsg: Message = { id: `cmd_${Date.now()}`, role: 'user', content: fullInput, timestamp: Date.now() };
          const args = rawArgs ? rawArgs.split(/\s+/) : [];
          if (args.length === 0 && setModelSelectorOpen) { setMessages((prev) => [...prev, userMsg]); setModelSelectorOpen(true); return; }
          const result = cmd.handler(args, ctx);
          if (result instanceof Promise) { result.then((value) => setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(value))])); }
          else { setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(result))]); }
        },
      };
    }
    return {
      name: cmd.name, description: cmd.description,
      onExecute: (rawArgs: string, fullInput: string) => {
        const userMsg: Message = { id: `cmd_${Date.now()}`, role: 'user', content: fullInput, timestamp: Date.now() };
        const args = rawArgs ? rawArgs.split(/\s+/) : [];
        const result = cmd.handler(args, ctx);
        if (result instanceof Promise) { result.then((value) => setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(value))])); }
        else { setMessages((prev) => [...prev, userMsg, makeSysMsg(toSlashText(result))]); }
      },
    };
  });

  if (skills) {
    const seen = new Set(builtins.map((c) => c.name));
    const skillCmds = skills.listLoadable()
      .filter((s) => { const cmdName = s.slashCommand || s.name; return !seen.has(cmdName); })
      .map((s) => {
        const cmdName = s.slashCommand || s.name;
        seen.add(cmdName);
        return {
          name: cmdName, description: s.description,
          onExecute: (_rawArgs: string, fullInput: string) => {
            const userMsg: Message = { id: `cmd_${Date.now()}`, role: 'user', content: fullInput, timestamp: Date.now() };
            setMessages((prev) => [...prev, userMsg, makeSysMsg(`Skill "${s.name}" activated. Your next message will be processed with this skill's instructions.`)]);
          },
        };
      });
    return [...builtins, ...skillCmds];
  }
  return builtins;
}
