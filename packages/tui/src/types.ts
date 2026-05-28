import type { TuiPresentationMode } from './presentation/contracts.js';
import type { JarvisReasoningEffort } from '@jarvis/shared';

export interface TUIOptions {
  model: string;
  apiKey?: string;
  baseURL?: string;
  reasoningEffort?: JarvisReasoningEffort;
  maxTurns: number;
  systemPrompt?: string;
  forceOnboarding?: boolean;
  presentationMode?: TuiPresentationMode;
  debugHooks?: TUIDebugHooks;
}

export type TUIDebugEvent =
  | {
      type: "run_started";
      prompt: string;
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
      type: "run_completed";
      prompt: string;
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
      elapsedMs: number;
      tokenEvents: number;
      tokenChars: number;
      reasoningEvents: number;
      reasoningChars: number;
      toolStarts: number;
      toolEnds: number;
      hadStreamingContent: boolean;
      hadStreamingThinking: boolean;
      error: string;
      isAbort: boolean;
      timestamp: number;
    };

export interface TUIDebugHooks {
  onEvent?: (event: TUIDebugEvent) => void;
}
