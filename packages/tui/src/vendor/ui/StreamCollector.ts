// ============================================================================
// StreamCollector — newline-gated markdown stream accumulator (Codex pattern)
// ============================================================================
// Accumulates streaming text and only commits completed logical lines.
// Partial lines at the end of the buffer are held until a newline arrives.

export class StreamCollector {
  private buffer = '';
  private committedLineCount = 0;

  /** Push a token into the buffer. */
  pushDelta(delta: string): void {
    this.buffer += delta;
  }

  /** Commit all complete lines since the last commit. */
  commitCompleteLines(): string[] {
    const lastNewlineIdx = this.buffer.lastIndexOf('\n');
    if (lastNewlineIdx === -1) return [];

    const source = this.buffer.slice(0, lastNewlineIdx + 1);
    const lines = source.split('\n');
    // Last element is empty (trailing newline) — remove it
    if (lines.length > 0 && lines[lines.length - 1] === '') {
      lines.pop();
    }

    const completeLineCount = lines.length;
    if (this.committedLineCount >= completeLineCount) return [];

    const newLines = lines.slice(this.committedLineCount);
    this.committedLineCount = completeLineCount;
    return newLines;
  }

  /**
   * Drain all buffered content (including partial lines at end).
   * Resets the collector state. Call when streaming ends.
   */
  finalizeAndDrain(): string {
    const result = this.buffer;
    this.buffer = '';
    this.committedLineCount = 0;
    return result;
  }

  /** Whether there are any committed (newline-terminated) lines. */
  hasCommittedLines(): boolean {
    return this.committedLineCount > 0;
  }

  /** Current incomplete line at the end of buffer. */
  currentPartialLine(): string {
    const lastNewlineIdx = this.buffer.lastIndexOf('\n');
    return lastNewlineIdx === -1
      ? this.buffer
      : this.buffer.slice(lastNewlineIdx + 1);
  }

  /** Clear all state. */
  clear(): void {
    this.buffer = '';
    this.committedLineCount = 0;
  }
}