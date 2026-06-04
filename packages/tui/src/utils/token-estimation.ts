import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { estimateTokens, type TokenTracker } from '@jarvis/agent';
import type { McpConnectionStatus } from '@jarvis/mcp';
import type { MemoryTokenEntry } from '../context-panel.js';
import type { StatusDetailLine } from '../vendor/ui/REPL.js';

export function estimateTokensFromText(text: string | undefined): number {
  return estimateTokens(text);
}

export function estimateMemoryEntries(cwd: string): MemoryTokenEntry[] {
  const entries: MemoryTokenEntry[] = [];
  const claudePath = join(cwd, 'CLAUDE.md');
  if (existsSync(claudePath)) {
    entries.push({
      path: 'CLAUDE.md',
      tokens: estimateTokensFromText(readFileSync(claudePath, 'utf8')),
    });
  }
  const memoryDir = join(cwd, '.jarvis', 'memory');
  if (existsSync(memoryDir)) {
    try {
      const files = readdirSync(memoryDir).filter((f) => f.endsWith('.md'));
      for (const file of files) {
        entries.push({
          path: `.jarvis/memory/${file}`,
          tokens: estimateTokensFromText(readFileSync(join(memoryDir, file), 'utf8')),
        });
      }
    } catch {
      // ignore memory read errors
    }
  }
  return entries;
}

export function buildContextProgressBar(percentRemaining?: number): StatusDetailLine | null {
  if (percentRemaining === undefined || !Number.isFinite(percentRemaining)) {
    return { content: 'CTX [░░░░░░░░░░░░░░░░░░] used 0% | left 100%', color: 'gray' };
  }
  const width = 18;
  const left = Math.max(0, Math.min(100, percentRemaining));
  const used = Math.max(0, 100 - left);
  const filled = Math.round((used / 100) * width);
  const bar = `${'█'.repeat(filled)}${'░'.repeat(Math.max(0, width - filled))}`;
  const color: StatusDetailLine['color'] =
    used < 60 ? 'green' : used < 85 ? 'yellow' : 'red';
  return { content: `CTX [${bar}] used ${used.toFixed(1)}% | left ${left.toFixed(1)}%`, color };
}

export function estimateTurnTokenCount(stats: {
  trackerStartBlended: number;
  tokenChars: number;
  reasoningChars: number;
} | null, tracker: TokenTracker | null): number | undefined {
  if (!stats) return undefined;
  const blendedDelta = Math.max(0, (tracker?.totalBlended ?? 0) - stats.trackerStartBlended);
  if (blendedDelta > 0) return blendedDelta;

  const approxFromChars = Math.round((stats.tokenChars + stats.reasoningChars) / 4);
  return approxFromChars > 0 ? approxFromChars : undefined;
}

export function buildMcpFooterLines(
  statuses: McpConnectionStatus[],
): StatusDetailLine[] {
  if (statuses.length === 0) {
    return [{
      segments: [
        { content: '[MCP --]', color: 'gray' },
        { content: 'waiting for status', color: 'gray' },
      ],
      emphasis: true,
    }];
  }
  const ok = statuses.filter((s) => s.state === 'ready' || s.state === 'degraded');
  const failed = statuses.filter((s) => s.state === 'failed');
  const firstError = failed[0]?.error;
  const summaryColor: StatusDetailLine['color'] = failed.length > 0 ? 'red' : 'green';
  const summary = `[MCP ${ok.length}/${statuses.length}]`;
  if (!firstError) {
    return [{
      segments: [
        { content: summary, color: summaryColor },
        { content: failed.length > 0 ? 'issues detected' : 'all servers healthy', color: summaryColor },
      ],
      emphasis: true,
    }];
  }
  const compactError = firstError.length > 92 ? `${firstError.slice(0, 92)}...` : firstError;
  return [
    {
      segments: [
        { content: summary, color: summaryColor },
        { content: 'startup error', color: 'red' },
      ],
      emphasis: true,
    },
    { content: `[MCP ERR] ${compactError}`, color: 'red' },
  ];
}

