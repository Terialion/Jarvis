/**
 * File scanner for @ file reference feature.
 * Scans the working directory and returns file/directory entries for the picker.
 */

import { readdir, stat } from "node:fs/promises";
import { join, relative, sep } from "node:path";

export type FileEntry = {
  /** Relative path from cwd, using forward slashes */
  path: string;
  /** True if this entry is a directory */
  isDir: boolean;
};

/** Directories to always skip during scanning */
const IGNORED_DIRS = new Set([
  "node_modules",
  ".git",
  ".turbo",
  ".cache",
  "dist",
  "__pycache__",
  ".next",
  ".nuxt",
  "coverage",
  ".pytest_cache",
  ".jarvis",
]);

/** File extensions to deprioritize (shown at bottom of results) */
const LOW_PRIORITY_EXTS = new Set([
  ".map",
  ".d.ts",
  ".lock",
]);

const DEFAULT_MAX_DEPTH = 3;
const DEFAULT_MAX_RESULTS = 50;

/**
 * Scan a directory recursively and return file/directory entries.
 * Results are sorted: directories first, then files alphabetically.
 * Low-priority files (.map, .d.ts, .lock) are pushed to the end.
 */
export async function scanFiles(
  cwd: string,
  query: string = "",
  maxResults: number = DEFAULT_MAX_RESULTS,
  maxDepth: number = DEFAULT_MAX_DEPTH,
): Promise<FileEntry[]> {
  const results: FileEntry[] = [];
  const normalizedQuery = query.toLowerCase().replace(/\\/g, "/");

  // When there's no query (empty or whitespace), only show root-level entries (like Claude Code)
  const hasQuery = normalizedQuery.trim().length > 0;
  const effectiveMaxDepth = hasQuery ? maxDepth : 0;

  async function walk(dir: string, depth: number): Promise<void> {
    if (depth > effectiveMaxDepth || results.length >= maxResults) return;

    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return; // skip unreadable directories
    }

    for (const entry of entries) {
      if (results.length >= maxResults) return;

      // Skip ignored directories
      if (IGNORED_DIRS.has(entry.name)) continue;

      // Skip hidden files/dirs (starting with .) unless query starts with .
      if (entry.name.startsWith(".") && !normalizedQuery.startsWith(".")) continue;

      const fullPath = join(dir, entry.name);
      const relPath = relative(cwd, fullPath).replace(/\\/g, "/");
      const isDir = entry.isDirectory();

      // Check if this entry matches the query
      const matchesQuery =
        !normalizedQuery ||
        relPath.toLowerCase().includes(normalizedQuery) ||
        entry.name.toLowerCase().includes(normalizedQuery);

      if (matchesQuery) {
        results.push({ path: relPath, isDir });
      }

      // Recurse into directories
      if (isDir) {
        await walk(fullPath, depth + 1);
      }
    }
  }

  await walk(cwd, 0);

  // Sort: directories first, then files. Within each group, shorter paths first (top-level first), then alphabetical.
  // Low-priority files go last.
  results.sort((a, b) => {
    // Directories first
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;

    // Low-priority files last
    const aLow = isLowPriority(a.path);
    const bLow = isLowPriority(b.path);
    if (aLow !== bLow) return aLow ? 1 : -1;

    // Shorter paths first (top-level entries before nested ones)
    const aDepth = a.path.split("/").length;
    const bDepth = b.path.split("/").length;
    if (aDepth !== bDepth) return aDepth - bDepth;

    // Alphabetical within same depth
    return a.path.localeCompare(b.path);
  });

  return results;
}

function isLowPriority(path: string): boolean {
  for (const ext of LOW_PRIORITY_EXTS) {
    if (path.endsWith(ext)) return true;
  }
  return false;
}
