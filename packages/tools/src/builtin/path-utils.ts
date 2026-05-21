import { resolve, relative, sep } from 'node:path';

/**
 * Resolve a file path safely. If workspaceRoot is provided, the resolved
 * path must be within that directory (prevents path traversal attacks).
 * Accepts both relative (`./foo`) and absolute paths.
 */
export function resolveSafePath(
  filePath: string,
  workspaceRoot?: string,
): { ok: true; path: string } | { ok: false; error: string } {
  if (!filePath) {
    return { ok: false, error: 'No path provided' };
  }

  const absPath = resolve(filePath);

  if (workspaceRoot) {
    const absRoot = resolve(workspaceRoot);
    const rel = relative(absRoot, absPath);

    if (rel.startsWith('..') || rel.startsWith(`${sep}..`)) {
      return {
        ok: false,
        error: `Path traversal denied: "${filePath}" is outside the workspace root`,
      };
    }
  }

  return { ok: true, path: absPath };
}

/** Default max file size for read operations (10 MB). */
export const MAX_READ_SIZE = 10 * 1024 * 1024;
