import type { TuiPresentationMode } from './presentation/contracts.js';
import type { JarvisReasoningEffort } from '@jarvis/shared';
import type { AgentTurnState } from '@jarvis/agent';

export interface TUIOptions {
  model: string;
  apiKey?: string;
  baseURL?: string;
  reasoningEffort?: JarvisReasoningEffort;
  maxTurns: number;
  maxSteps?: number;
  timeoutS?: number;
  toolTimeoutS?: number;
  systemPrompt?: string;
  forceOnboarding?: boolean;
  presentationMode?: TuiPresentationMode;
  debugHooks?: TUIDebugHooks;
  /** When true, render on the main screen (no alternate buffer). Native terminal scrollback works. */
  mainScreen?: boolean;
}

export type TUIDebugEvent =
  | {
      type: "run_started";
      prompt: string;
      timestamp: number;
    }
  | {
      type: "stream_run_started";
      runId: string;
      prompt: string;
      timestamp: number;
    }
  | {
      type: "stream_chunk_flushed";
      runId: string;
      chunkLength: number;
      displayLength: number;
      sourceLength: number;
      timestamp: number;
    }
  | {
      type: "stream_finalized";
      runId: string;
      reason: "tool_boundary" | "turn_complete" | "error" | "abort" | "cleanup";
      finalAnswerLength: number;
      committedTextLength: number;
      replacedStreamed: boolean;
      timestamp: number;
    }
  | {
      type: "stream_committed";
      runId: string;
      messageId: string;
      textLength: number;
      timestamp: number;
    }
  | {
      type: "stream_cleared";
      runId: string;
      reason: "tool_boundary" | "turn_complete" | "error" | "abort" | "cleanup";
      timestamp: number;
    }
  | {
      type: "message_id_emitted";
      messageId: string;
      kind: "user" | "assistant" | "thinking" | "error";
      timestamp: number;
    }
  | {
      type: "tool_started";
      toolName: string;
      callId: string;
      timestamp: number;
    }
  | {
      type: "tool_finished";
      toolName: string;
      callId: string;
      ok: boolean;
      resultLength: number;
      timestamp: number;
    }
  | {
      type: "tool_runtime_state";
      stage:
        | "approval_requested"
        | "approval_granted"
        | "approval_denied"
        | "dispatch_started"
        | "dispatch_completed"
        | "dispatch_failed";
      toolName: string;
      callId: string;
      argsKey?: string;
      risk?: string;
      ok?: boolean;
      reason?: string;
      durationMs?: number;
      timestamp: number;
    }
  | {
      type: "turn_phase";
      phase: "discover" | "analyze" | "finalize";
      detail: string;
      step?: number;
      finalizeReason?: "stagnation" | "rejections" | null;
      finalizeAttempts?: number;
      toolCallsSoFar?: number;
      toolCallCount?: number;
      retryWithToolInstructionCount?: number;
      noProgressCount?: number;
      timestamp: number;
    }
  | {
      type: "run_completed";
      prompt: string;
      turnState: AgentTurnState;
      elapsedMs: number;
      finalAnswerLength: number;
      finalAnswerPreview: string;
      finalAnswerTail: string;
      reasoningLength: number;
      streamedContentLength: number;
      committedStreamingLength: number;
      tokenEvents: number;
      tokenChars: number;
      reasoningEvents: number;
      reasoningChars: number;
      toolStarts: number;
      toolEnds: number;
      hadStreamingContent: boolean;
      hadStreamingThinking: boolean;
      toolResultCount: number;
      stopReason: string;
      turnsUsed: number;
      toolResults: Array<{
        name: string;
        ok: boolean;
        contentLength: number;
        error?: string;
      }>;
      newMessageCount: number;
      timestamp: number;
    }
  | {
      type: "run_failed";
      prompt: string;
      turnState: AgentTurnState;
      elapsedMs: number;
      tokenEvents?: number;
      tokenChars?: number;
      reasoningEvents?: number;
      reasoningChars?: number;
      toolStarts?: number;
      toolEnds?: number;
      hadStreamingContent?: boolean;
      hadStreamingThinking?: boolean;
      error: string;
      stopReason?: string;
      isAbort?: boolean;
      timestamp: number;
    }
  | {
      type: "viewport_state";
      mode: "following" | "history" | "selection";
      followOutput: boolean;
      hasSelection: boolean;
      interactivePromptActive: boolean;
      isLoading: boolean;
      scrollTop: number;
  scrollHeight: number;
  viewportHeight: number;
      pendingScrollDelta: number;
      remainingScrollDistance: number;
      clampMin?: number;
      clampMax?: number;
      paintScrollTop?: number;
      clampedToMaxScroll?: number;
      usedPaintClamp?: boolean;
      usedMountedRangeClamp?: boolean;
      followedThisFrame?: boolean;
      mutationSource?: string;
      liveAnswerLength?: number;
      liveThinkingLength?: number;
      transcriptItemCount?: number;
      transcriptTotalHeight?: number;
      transcriptRangeStart?: number;
      transcriptRangeEnd?: number;
      timestamp: number;
    }
  | {
      type: "viewport_manual_scroll";
      action: "scroll_by" | "scroll_to_top" | "scroll_to_bottom";
      delta?: number;
      targetTop?: number;
      timestamp: number;
    };

export interface TUIDebugHooks {
  onEvent?: (event: TUIDebugEvent) => void;
}
