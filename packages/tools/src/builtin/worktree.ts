// ============================================================================
// Worktree tools — EnterWorktree and ExitWorktree for git worktree isolation
// ============================================================================

import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- helpers ----

function git(args: string, cwd?: string): string {
  try {
    return execSync(`git ${args}`, {
      cwd: cwd ?? process.cwd(),
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch (err: unknown) {
    const msg = (err as { stderr?: string; message?: string }).stderr
      ?? (err as Error).message
      ?? String(err);
    throw new Error(`git ${args.split(' ')[0]} failed: ${msg}`);
  }
}

function isGitRepo(): boolean {
  try {
    git('rev-parse --git-dir');
    return true;
  } catch {
    return false;
  }
}

// ---- enter_worktree ----

export const enterWorktreeSchema = toOpenAITool({
  name: 'enter_worktree',
  description:
    'Create a temporary git worktree for isolated work. The worktree is created inside .claude/worktrees/ on a new branch. Use for feature work that needs isolation from the current workspace.',
  parameters: {
    type: 'object',
    properties: {
      name: {
        type: 'string',
        description: 'Optional name for the new worktree. Random name generated if omitted. Max 64 chars, alphanumeric + dot/underscore/dash.',
      },
      path: {
        type: 'string',
        description: 'Optional path to an existing worktree to enter (registered in git worktree list). Mutually exclusive with name.',
      },
    },
  },
});

const enterWorktreeHandler: ToolHandler = (args, _context) => {
  const worktreeName = typeof args.name === 'string' ? args.name.trim() : undefined;
  const existingPath = typeof args.path === 'string' ? args.path.trim() : undefined;

  if (!isGitRepo()) {
    return JSON.stringify({ error: 'Not in a git repository. Worktrees require a git repo.' });
  }

  // Enter an existing worktree
  if (existingPath) {
    const absPath = resolve(existingPath);
    if (!existsSync(absPath)) {
      return JSON.stringify({ error: `Path does not exist: ${absPath}` });
    }

    try {
      const listed = git('worktree list --porcelain');
      const isRegistered = listed.includes(absPath.replace(/\\/g, '/'));
      if (!isRegistered) {
        return JSON.stringify({ error: `Path is not a registered git worktree: ${absPath}` });
      }
    } catch {
      return JSON.stringify({ error: 'Failed to verify worktree registration.' });
    }

    return JSON.stringify({
      worktreePath: absPath,
      message: `Entered existing worktree at: ${absPath}`,
    });
  }

  // Create a new worktree
  const name = worktreeName ?? `wt_${crypto.randomUUID().slice(0, 8)}`;
  if (name.length > 64 || !/^[a-zA-Z0-9._/-]+$/.test(name)) {
    return JSON.stringify({ error: 'Invalid worktree name. Max 64 chars, alphanumeric + dot/underscore/dash/slash.' });
  }

  try {
    const repoRoot = git('rev-parse --show-toplevel');
    const worktreesDir = `${repoRoot}/.claude/worktrees`;
    const targetPath = `${worktreesDir}/${name}`;

    if (existsSync(targetPath)) {
      return JSON.stringify({ error: `Worktree path already exists: ${targetPath}` });
    }

    git(`worktree add "${targetPath}" -b "${name}"`);
    return JSON.stringify({
      worktreePath: targetPath,
      branch: name,
      message: `Created worktree at: ${targetPath} on branch "${name}".`,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to create worktree: ${msg}` });
  }
};

// ---- exit_worktree ----

export const exitWorktreeSchema = toOpenAITool({
  name: 'exit_worktree',
  description:
    'Exit a worktree session and optionally remove the worktree. Use action="keep" to leave it intact, or action="remove" to delete the worktree directory and branch.',
  parameters: {
    type: 'object',
    properties: {
      action: {
        type: 'string',
        enum: ['keep', 'remove'],
        description: '"keep" leaves the worktree on disk; "remove" deletes it. Default: "keep".',
      },
      discard_changes: {
        type: 'boolean',
        default: false,
        description: 'Required true when action="remove" and there are uncommitted changes.',
      },
      worktree_path: {
        type: 'string',
        description: 'Path to the worktree to exit.',
      },
    },
    required: ['action'],
  },
});

const exitWorktreeHandler: ToolHandler = (args, _context) => {
  const action = (['keep', 'remove'] as const).includes(args.action as never)
    ? (args.action as 'keep' | 'remove')
    : 'keep';
  const worktreePath = typeof args.worktree_path === 'string' ? args.worktree_path.trim() : undefined;
  const discardChanges = args.discard_changes === true;

  if (!worktreePath) {
    return JSON.stringify({ error: 'Missing required parameter: worktree_path' });
  }

  const absPath = resolve(worktreePath);

  if (!existsSync(absPath)) {
    return JSON.stringify({ error: `Worktree path does not exist: ${absPath}` });
  }

  if (action === 'keep') {
    return JSON.stringify({
      message: `Worktree left intact at: ${absPath}`,
    });
  }

  // action === 'remove'
  try {
    // Check for uncommitted changes
    if (!discardChanges) {
      try {
        const status = git('status --porcelain', absPath);
        if (status.trim()) {
          return JSON.stringify({
            error: `Worktree has uncommitted changes. Use discard_changes=true to force removal, or commit/push first.\nChanges:\n${status}`,
          });
        }
      } catch { /* proceed */ }
    }

    const branch = git('rev-parse --abbrev-ref HEAD', absPath);
    git(`worktree remove "${absPath}"${discardChanges ? ' --force' : ''}`);
    // Delete the branch if it's a worktree branch
    try {
      git(`branch -D "${branch}"`);
    } catch { /* branch may not exist or already deleted */ }

    return JSON.stringify({
      message: `Worktree removed: ${absPath}`,
      branch,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to remove worktree: ${msg}` });
  }
};

// ---- entries ----

export const enterWorktreeTool: ToolEntry = {
  name: 'enter_worktree',
  toolset: 'orchestration',
  schema: enterWorktreeSchema,
  handler: enterWorktreeHandler,
  isAsync: true,
  emoji: '🌿',
  description: 'Create or enter an isolated git worktree.',
};

export const exitWorktreeTool: ToolEntry = {
  name: 'exit_worktree',
  toolset: 'orchestration',
  schema: exitWorktreeSchema,
  handler: exitWorktreeHandler,
  isAsync: true,
  emoji: '🚪',
  description: 'Exit and optionally remove a git worktree.',
};
