// ============================================================================
// Markdown-based memory store — human-editable .md files with frontmatter
// ============================================================================

import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';
import { createHash } from 'node:crypto';

// ============================================================================
// Types
// ============================================================================

export interface MemoryEntry {
  /** Unique key, becomes filename (sanitized). */
  name: string;
  /** Short description. */
  description: string;
  /** Category: user, feedback, project, reference. */
  memoryType: 'user' | 'feedback' | 'project' | 'reference';
  /** Markdown body content. */
  content: string;
  /** File path — set during load. */
  filePath?: string;
}

// ============================================================================
// Frontmatter parsing / formatting
// ============================================================================

/**
 * Parse YAML-like frontmatter from markdown text.
 * Returns meta key:value pairs and the body.
 */
function parseFrontmatter(text: string): {
  meta: Record<string, string>;
  body: string;
} {
  const lines = text.split('\n');
  if (lines.length === 0 || lines[0].trim() !== '---') {
    return { meta: {}, body: text };
  }

  let endIdx = 1;
  const meta: Record<string, string> = {};
  while (endIdx < lines.length) {
    const line = lines[endIdx].trim();
    if (line === '---') {
      endIdx++;
      break;
    }
    if (line.includes(':')) {
      const colonIdx = line.indexOf(':');
      const key = line.slice(0, colonIdx).trim();
      const val = line.slice(colonIdx + 1).trim();
      meta[key] = val;
    }
    endIdx++;
  }

  const body = lines
    .slice(endIdx)
    .join('\n')
    .trim();
  return { meta, body };
}

/**
 * Format an entry as markdown with frontmatter.
 * Keys are written in order: name, description, type.
 */
function formatFrontmatter(
  meta: Record<string, string>,
  body: string,
): string {
  const headerLines = ['---'];
  const orderedKeys = ['name', 'description', 'type', 'content_hash', 'updated_at'];
  for (const key of orderedKeys) {
    if (key in meta) {
      headerLines.push(`${key}: ${meta[key]}`);
    }
  }
  for (const key of Object.keys(meta)) {
    if (!orderedKeys.includes(key)) {
      headerLines.push(`${key}: ${meta[key]}`);
    }
  }
  headerLines.push('---');
  headerLines.push(''); // blank line before body
  headerLines.push(body);
  return headerLines.join('\n') + '\n';
}

// ============================================================================
// Helpers
// ============================================================================

function resolveHome(filePath: string): string {
  if (filePath.startsWith('~/')) {
    return path.join(os.homedir(), filePath.slice(2));
  }
  return filePath;
}

class Mutex {
  private _locked = false;
  private _queue: Array<() => void> = [];

  async acquire(): Promise<void> {
    if (!this._locked) {
      this._locked = true;
      return;
    }
    return new Promise<void>((resolve) => {
      this._queue.push(resolve);
    });
  }

  release(): void {
    if (this._queue.length > 0) {
      this._queue.shift()!();
    } else {
      this._locked = false;
    }
  }
}

// ============================================================================
// MarkdownMemoryStore
// ============================================================================

export class MarkdownMemoryStore {
  private readonly baseDir: string;
  readonly indexPath: string;
  private readonly _writeLock = new Mutex();

  constructor(baseDir: string = '~/.jarvis/memory') {
    this.baseDir = resolveHome(baseDir);
    this.indexPath = path.join(this.baseDir, 'MEMORY.md');
  }

  // ── Read ────────────────────────────────────────────────────────────

  /** Load all memory entries from markdown files. */
  async loadAll(): Promise<MemoryEntry[]> {
    const entries: MemoryEntry[] = [];
    try {
      await fs.mkdir(this.baseDir, { recursive: true });
    } catch {
      // Directory may already exist
    }

    let files: string[];
    try {
      files = await fs.readdir(this.baseDir);
    } catch {
      return entries;
    }

    for (const file of files.sort()) {
      if (!file.endsWith('.md')) continue;
      if (file === 'MEMORY.md' || file === 'index.md') continue;

      const filePath = path.join(this.baseDir, file);
      try {
        const text = await fs.readFile(filePath, 'utf-8');
        const { meta, body } = parseFrontmatter(text);
        if (meta.name) {
          entries.push({
            name: meta.name,
            description: meta.description || '',
            memoryType: (meta.type as MemoryEntry['memoryType']) || 'project',
            content: body,
            filePath,
          });
        }
      } catch {
        // Skip unreadable files (matches Python behavior)
      }
    }
    return entries;
  }

  /**
   * Compute SHA-256 content hash for deduplication.
   */
  static hashContent(content: string): string {
    return createHash('sha256').update(content).digest('hex').slice(0, 16);
  }

  /**
   * Compute temporal decay weight based on days since update.
   * Formula: max(0.1, 1.0 - (daysSince / halfLifeDays) * 0.9)
   */
  static computeDecayWeight(updatedAt: string, halfLifeDays: number = 14): number {
    if (!updatedAt) return 0.5;
    const updated = new Date(updatedAt).getTime();
    if (isNaN(updated)) return 0.5;
    const daysSince = (Date.now() - updated) / (1000 * 60 * 60 * 24);
    return Math.max(0.1, 1.0 - (daysSince / halfLifeDays) * 0.9);
  }

  /** Write a memory entry to a .md file and update MEMORY.md index. */
  async write(entry: MemoryEntry): Promise<string> {
    await this._writeLock.acquire();
    try {
      const safeName = this.sanitizeName(entry.name);
      const fileName = `${safeName}.md`;
      const filePath = path.join(this.baseDir, fileName);

      const contentHash = MarkdownMemoryStore.hashContent(entry.content);
      const now = new Date().toISOString();

      // Dedup: check if entry with same content hash already exists
      const existing = await this._findByHash(contentHash);
      if (existing) {
        // Update timestamp but don't rewrite identical content
        const existingMeta: Record<string, string> = {
          name: entry.name,
          description: entry.description,
          type: entry.memoryType,
          content_hash: contentHash,
          updated_at: now,
        };
        await fs.mkdir(this.baseDir, { recursive: true });
        await fs.writeFile(
          filePath,
          formatFrontmatter(existingMeta, entry.content),
          'utf-8',
        );
        await this._updateIndex(entry, fileName);
        return filePath;
      }

      const meta: Record<string, string> = {
        name: entry.name,
        description: entry.description,
        type: entry.memoryType,
        content_hash: contentHash,
        updated_at: now,
      };

      await fs.mkdir(this.baseDir, { recursive: true });
      await fs.writeFile(
        filePath,
        formatFrontmatter(meta, entry.content),
        'utf-8',
      );

      await this._updateIndex(entry, fileName);
      return filePath;
    } finally {
      this._writeLock.release();
    }
  }

  /**
   * Load all entries with temporal decay weights applied.
   * Returns entries sorted by (relevance_boost * decayWeight) descending.
   */
  async loadWithDecay(): Promise<Array<MemoryEntry & { contentHash: string; decayWeight: number }>> {
    const entries = await this.loadAll();
    return entries
      .map((e) => {
        const updatedAt = (e as unknown as Record<string, unknown>)['updated_at'] as string ?? '';
        return {
          ...e,
          contentHash: (e as unknown as Record<string, unknown>)['content_hash'] as string ?? '',
          decayWeight: MarkdownMemoryStore.computeDecayWeight(updatedAt),
        };
      })
      .sort((a, b) => b.decayWeight - a.decayWeight);
  }

  /** Find an entry by content hash, returns the file path if found. */
  private async _findByHash(hash: string): Promise<string | null> {
    try {
      const entries = await this.loadAll();
      for (const entry of entries) {
        const entryHash = (entry as unknown as Record<string, unknown>)['content_hash'] as string;
        if (entryHash === hash && entry.filePath) {
          return entry.filePath;
        }
      }
    } catch { /* ignore */ }
    return null;
  }

  /** Delete a memory entry file and remove from MEMORY.md index. */
  async delete(name: string): Promise<void> {
    await this._writeLock.acquire();
    try {
      const safeName = this.sanitizeName(name);
      const fileName = `${safeName}.md`;
      const filePath = path.join(this.baseDir, fileName);

      await fs.unlink(filePath).catch(() => {
        /* ok if doesn't exist */
      });

      await this._removeFromIndex(fileName);
    } finally {
      this._writeLock.release();
    }
  }

  /** Search across name, description, and content (substring match). */
  async search(query: string): Promise<MemoryEntry[]> {
    if (!query) return [];
    const terms = query.toLowerCase().split(/\s+/);
    const results: MemoryEntry[] = [];
    for (const entry of await this.loadAll()) {
      const text = `${entry.name} ${entry.description} ${entry.content}`.toLowerCase();
      if (terms.every((term) => text.includes(term))) {
        results.push(entry);
      }
    }
    return results;
  }

  /** Sanitize a name for use as a filename. */
  sanitizeName(name: string): string {
    return name.replace(/[/\\ :]/g, '_').replace(/\s+/g, '_');
  }

  // ── Index management ────────────────────────────────────────────────

  private async _updateIndex(entry: MemoryEntry, fileName: string): Promise<void> {
    const hook = entry.description
      ? entry.description.slice(0, 100)
      : '(no description)';
    const newLine = `- [${entry.name}](${fileName}) — ${hook}`;

    let lines: string[] = [];
    try {
      const existing = await fs.readFile(this.indexPath, 'utf-8');
      lines = existing.split('\n');
    } catch {
      // No index yet — start fresh
    }

    const marker = `](${fileName})`;
    let replaced = false;
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes(marker)) {
        lines[i] = newLine;
        replaced = true;
        break;
      }
    }

    if (!replaced) {
      // Remove trailing blank lines before appending
      while (lines.length > 0 && !lines[lines.length - 1].trim()) {
        lines.pop();
      }
      lines.push(newLine);
      lines.push(''); // trailing newline
    }

    await fs.writeFile(this.indexPath, lines.join('\n'), 'utf-8');
  }

  private async _removeFromIndex(fileName: string): Promise<void> {
    try {
      const existing = await fs.readFile(this.indexPath, 'utf-8');
      const marker = `](${fileName})`;
      const lines = existing.split('\n').filter((l) => !l.includes(marker));
      await fs.writeFile(this.indexPath, lines.join('\n'), 'utf-8');
    } catch {
      // No index to update
    }
  }

  // ── Static helpers (public for external use) ────────────────────────

  static parseFrontmatter(text: string): {
    meta: Record<string, string>;
    body: string;
  } {
    return parseFrontmatter(text);
  }

  static formatFrontmatter(meta: Record<string, string>, body: string): string {
    return formatFrontmatter(meta, body);
  }
}
