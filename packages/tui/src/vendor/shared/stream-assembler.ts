// ============================================================================
// TuiStreamAssembler — ported from OpenClaw (tui-LVkXuSWn.js:2629-2700)
// Pure state management for streaming model output. Zero framework deps.
// ============================================================================

// ---- Message block types (compatible with Jarvis MessageContent) ----

interface ContentBlock {
  type?: string;
  text?: string;
  thinking?: string;
  [key: string]: unknown;
}

interface MessageRecord {
  role?: string;
  content?: string | ContentBlock[];
  stopReason?: string;
  errorMessage?: string;
}

// ---- RunState ----

interface RunState {
  thinkingText: string;
  contentText: string;
  contentBlocks: string[];
  sawNonTextContentBlocks: boolean;
  displayText: string;
}

// ---- Boundary-drop detection (OpenClaw:2580-2628) ----

function extractTextBlocksAndSignals(message: MessageRecord): {
  textBlocks: string[];
  sawNonTextContentBlocks: boolean;
} {
  if (!message || typeof message !== 'object') {
    return { textBlocks: [], sawNonTextContentBlocks: false };
  }
  const content = message.content;
  if (typeof content === 'string') {
    const text = content.trim();
    return { textBlocks: text ? [text] : [], sawNonTextContentBlocks: false };
  }
  if (!Array.isArray(content)) {
    return { textBlocks: [], sawNonTextContentBlocks: false };
  }
  const textBlocks: string[] = [];
  let sawNonTextContentBlocks = false;
  for (const block of content) {
    if (!block || typeof block !== 'object') continue;
    if (block.type === 'text' && typeof block.text === 'string') {
      const text = block.text.trim();
      if (text) textBlocks.push(text);
      continue;
    }
    if (typeof block.type === 'string' && block.type !== 'thinking') {
      sawNonTextContentBlocks = true;
    }
  }
  return { textBlocks, sawNonTextContentBlocks };
}

function isDroppedBoundaryTextBlockSubset(params: {
  streamedTextBlocks: string[];
  finalTextBlocks: string[];
}): boolean {
  const { streamedTextBlocks, finalTextBlocks } = params;
  if (finalTextBlocks.length === 0 || finalTextBlocks.length >= streamedTextBlocks.length) {
    return false;
  }
  // Check prefix match
  if (finalTextBlocks.every((block, index) => streamedTextBlocks[index] === block)) {
    return true;
  }
  // Check suffix match
  const suffixStart = streamedTextBlocks.length - finalTextBlocks.length;
  return finalTextBlocks.every(
    (block, index) => streamedTextBlocks[suffixStart + index] === block,
  );
}

interface ShouldPreserveParams {
  boundaryDropMode: 'off' | 'streamed-or-incoming' | 'streamed-only';
  streamedSawNonTextContentBlocks: boolean;
  incomingSawNonTextContentBlocks?: boolean;
  streamedTextBlocks: string[];
  nextContentBlocks: string[];
}

function shouldPreserveBoundaryDroppedText(params: ShouldPreserveParams): boolean {
  if (params.boundaryDropMode === 'off') return false;
  const sawNonText =
    params.boundaryDropMode === 'streamed-or-incoming'
      ? params.streamedSawNonTextContentBlocks || (params.incomingSawNonTextContentBlocks ?? false)
      : params.streamedSawNonTextContentBlocks;
  if (!sawNonText) return false;
  return isDroppedBoundaryTextBlockSubset({
    streamedTextBlocks: params.streamedTextBlocks,
    finalTextBlocks: params.nextContentBlocks,
  });
}

// ---- Message extraction (OpenClaw:807-843) ----

/** Extract thinking blocks from message content. */
export function extractThinkingFromMessage(message: MessageRecord): string {
  if (!message || typeof message !== 'object') return '';
  const content = message.content;
  if (typeof content === 'string') return '';
  if (!Array.isArray(content)) return '';

  const parts: string[] = [];
  for (const block of content) {
    if (!block || typeof block !== 'object') continue;
    // Jarvis uses `text` field, OpenClaw uses `thinking` field — support both
    if (block.type === 'thinking') {
      const value = typeof block.text === 'string' ? block.text
        : typeof (block as Record<string, unknown>).thinking === 'string'
          ? (block as Record<string, unknown>).thinking as string
          : '';
      if (value.trim()) parts.push(value.trim());
    }
  }
  return parts.join('\n').trim();
}

/** Extract text content blocks from message (excludes thinking). */
export function extractContentFromMessage(
  message: MessageRecord,
  _extractAssistantVisibleText?: (record: MessageRecord) => string | undefined,
): string {
  if (!message || typeof message !== 'object') return '';
  const content = message.content;
  if (typeof content === 'string') return content.trim();
  if (!Array.isArray(content)) return '';

  const parts: string[] = [];
  for (const block of content) {
    if (!block || typeof block !== 'object') continue;
    if (block.type === 'text' && typeof block.text === 'string') {
      const text = block.text.trim();
      if (text) parts.push(text);
    }
  }
  return parts.join('\n').trim();
}

// ---- Composition (OpenClaw:769-776) ----

export function composeThinkingAndContent(params: {
  thinkingText?: string;
  contentText?: string;
  showThinking?: boolean;
}): string {
  const thinkingText = params.thinkingText?.trim() ?? '';
  const contentText = params.contentText?.trim() ?? '';
  const parts: string[] = [];
  if (params.showThinking && thinkingText) {
    parts.push(`[thinking]\n${thinkingText}`);
  }
  if (contentText) parts.push(contentText);
  return parts.join('\n\n').trim();
}

// ---- Final assist resolution (OpenClaw:760-768) ----

function resolveFinalAssistantText(params: {
  finalText?: string;
  streamedText?: string;
  errorMessage?: string;
}): string {
  const finalText = params.finalText ?? '';
  if (finalText.trim()) return finalText;
  const streamedText = params.streamedText ?? '';
  if (streamedText.trim()) return streamedText;
  const errorMessage = params.errorMessage ?? '';
  if (errorMessage.trim()) return `Error: ${errorMessage}`;
  return '(no output)';
}

// ---- TuiStreamAssembler (OpenClaw:2629-2700) ----

interface IngestOptions {
  boundaryDropMode?: 'off' | 'streamed-or-incoming' | 'streamed-only';
}

export class TuiStreamAssembler {
  private runs = new Map<string, RunState>();

  private getOrCreateRun(runId: string): RunState {
    let state = this.runs.get(runId);
    if (!state) {
      state = {
        thinkingText: '',
        contentText: '',
        contentBlocks: [],
        sawNonTextContentBlocks: false,
        displayText: '',
      };
      this.runs.set(runId, state);
    }
    return state;
  }

  private updateRunState(
    state: RunState,
    message: MessageRecord,
    showThinking: boolean,
    opts?: IngestOptions,
  ): void {
    const thinkingText = extractThinkingFromMessage(message);
    const contentText = extractContentFromMessage(message);
    const { textBlocks, sawNonTextContentBlocks } = extractTextBlocksAndSignals(message);

    if (thinkingText) state.thinkingText = thinkingText;
    if (contentText) {
      const nextContentBlocks = textBlocks.length > 0 ? textBlocks : [contentText];
      if (
        !shouldPreserveBoundaryDroppedText({
          boundaryDropMode: opts?.boundaryDropMode ?? 'off',
          streamedSawNonTextContentBlocks: state.sawNonTextContentBlocks,
          incomingSawNonTextContentBlocks: sawNonTextContentBlocks,
          streamedTextBlocks: state.contentBlocks,
          nextContentBlocks,
        })
      ) {
        state.contentText = contentText;
        state.contentBlocks = nextContentBlocks;
      }
    }
    if (sawNonTextContentBlocks) state.sawNonTextContentBlocks = true;

    state.displayText = composeThinkingAndContent({
      thinkingText: state.thinkingText,
      contentText: state.contentText,
      showThinking,
    });
  }

  /** Process a streaming delta. Returns new displayText or null if unchanged. */
  ingestDelta(runId: string, message: MessageRecord, showThinking: boolean): string | null {
    const state = this.getOrCreateRun(runId);
    const previousDisplayText = state.displayText;
    this.updateRunState(state, message, showThinking, {
      boundaryDropMode: 'streamed-or-incoming',
    });
    if (!state.displayText || state.displayText === previousDisplayText) return null;
    return state.displayText;
  }

  /** Finalize a run. Returns the final display text. */
  finalize(
    runId: string,
    message: MessageRecord,
    showThinking: boolean,
    errorMessage?: string,
  ): string {
    const state = this.getOrCreateRun(runId);
    const streamedDisplayText = state.displayText;
    const streamedTextBlocks = [...state.contentBlocks];
    const streamedSawNonTextContentBlocks = state.sawNonTextContentBlocks;

    this.updateRunState(state, message, showThinking, { boundaryDropMode: 'streamed-only' });
    const finalComposed = state.displayText;

    const finalText = resolveFinalAssistantText({
      finalText:
        streamedSawNonTextContentBlocks &&
        isDroppedBoundaryTextBlockSubset({
          streamedTextBlocks,
          finalTextBlocks: state.contentBlocks,
        })
          ? streamedDisplayText
          : finalComposed,
      streamedText: streamedDisplayText,
      errorMessage,
    });

    this.runs.delete(runId);
    return finalText;
  }

  /** Drop a run (e.g., on abort). */
  drop(runId: string): void {
    this.runs.delete(runId);
  }

  /** Get the number of active runs. */
  get activeRuns(): number {
    return this.runs.size;
  }
}
