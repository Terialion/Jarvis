import { randomUUID } from "node:crypto";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { REPL } from "./vendor/ui/REPL.js";
import type { Message } from "./vendor/ui/MessageList.js";
import type { TUIDebugEvent, TUIDebugHooks } from "./types.js";

export type ReplayFixtureScenario =
  | "tool-heavy-answer"
  | "tool-heavy-answer-long-tail"
  | "phase-diagnostic-finalize-timeout"
  | "phase-diagnostic-no-progress"
  | "tool-heavy-finalize-timeout"
  | "tool-heavy-no-progress";

type ReplayFixtureAppProps = {
  prompt: string;
  scenario: ReplayFixtureScenario;
  debugHooks?: TUIDebugHooks;
};

function createMessageId(prefix: string): string {
  return `${prefix}_${randomUUID()}`;
}

function emitDebug(debugHooks: TUIDebugHooks | undefined, event: TUIDebugEvent): void {
  debugHooks?.onEvent?.(event);
}

function buildLineAppendix(prefix: string, count: number): string {
  return Array.from({ length: count }, (_, index) => `${prefix} ${index + 1}. This line exists to force the transcript viewport to grow and reflow.`).join("\n");
}

export function ReplayFixtureApp({
  prompt,
  scenario,
  debugHooks,
}: ReplayFixtureAppProps): React.ReactNode {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingThinking, setStreamingThinking] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runningRef = useRef(false);

  const clearTimers = useCallback(() => {
    for (const timer of timeoutsRef.current) {
      clearTimeout(timer);
    }
    timeoutsRef.current = [];
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const schedule = useCallback((delayMs: number, fn: () => void) => {
    const timer = setTimeout(fn, delayMs);
    timeoutsRef.current.push(timer);
  }, []);

  const runToolHeavyAnswerScenario = useCallback((submittedPrompt: string, mode: ReplayFixtureScenario) => {
    const runStartedAt = Date.now();
    const runId = `fixture-run-${randomUUID()}`;
    const bashCallId = `bash_${randomUUID()}`;
    const mcpCallId = `mcp_${randomUUID()}`;
    const userMessageId = createMessageId("user");
    const bashMessageId = createMessageId("tool");
    const mcpMessageId = createMessageId("tool");
    const assistantMessageId = createMessageId("assistant");
    const baseAnswerChunks = [
      [
        "好，我们先把这条链拆开。",
        "",
        "第一，`Thought / MCP / bash` 这类块已经基本不抢视口了，说明 `history/selection` 状态机和工具块的 mounted-range clamp 已经收紧了一层。",
        "它们现在更多只是在追加内容，而不会立刻把历史浏览中的 viewport 强推到底部。",
        "这一点跟你前面体感里的“thought 和 tool 没那么容易抢屏”是对得上的。",
        "",
        buildLineAppendix("follow guard", 10),
        "",
      ].join("\n"),
      [
        "第二，真正还会把视口带跑的，往往是 `Answer` 流式阶段自己的高度持续增长。",
        "这时候 markdown 重排、段落折行、虚拟列表 range 变化、以及 renderer 里的临时 clamp 都会连续发生。",
        "如果其中任意一步把“为了绘制当前帧而算出来的 paint scrollTop”误当成了“应该持久写回的 scrollTop”，你在中间阅读时就会被拉动。",
        "所以我们不能只盯 followOutput，还得把 `paintScrollTop / clampedToMaxScroll / mountedRangeClamp` 这几条都拉出来看。",
        "",
        buildLineAppendix("answer growth", 12),
        "",
      ].join("\n"),
      [
        "第三，这条 fixture replay 现在就是专门模拟这种 answer stream。",
        "前面先给两段工具输出和 reasoning，让 transcript 真正变高；",
        "中间再让 answer 分块长段落持续刷新；",
        "同时在脚本里插入 `pageup`，逼它进入 history mode；",
        "最后再用结构化诊断去看 scrollTop 有没有在 answer flush 之后被外部改写。",
        "",
        buildLineAppendix("history mode replay", 10),
        "",
      ].join("\n"),
      [
        "如果后面我们在这条本地回放里复现到了漂移，下一步就可以非常明确地判断：",
        "到底是 clamp 误持久化、range 重算抖动、还是别的底部布局变化在抢你的视口。",
        "这样就不用再靠“看起来像是 sticky scroll”这种模糊猜测了。",
        "这也是我现在优先把离线 fixture 补起来的原因。",
        "",
        buildLineAppendix("final diagnostics", 10),
      ].join("\n"),
    ];
    const answerChunks =
      mode === "tool-heavy-answer-long-tail"
        ? [
            ...baseAnswerChunks,
            [
              "",
              "第四，为了把这条回放做成真正的压力测试，我们故意让后半段 answer 再慢一些。",
              "这样一来，如果 viewport 真的是因为 live answer 后半段的高度重算而抢位，就会在 history mode 期间留下明确证据。",
              buildLineAppendix("tail stream stability", 16),
              "",
            ].join("\n"),
            [
              "最后这段继续强调：viewport 稳定性不能依赖 live answer 的偶然渲染顺序。",
              "如果输出刷新仍然抢 viewport，history mode 里就应该看到 `scrollTop / paintScrollTop / rangeStart` 的异常变化。",
              buildLineAppendix("tail stream diagnostics", 18),
              "",
            ].join("\n"),
          ]
        : baseAnswerChunks;
    const chunkDelayMs = mode === "tool-heavy-answer-long-tail" ? 900 : 420;
    const finalizeDelayMs = mode === "tool-heavy-answer-long-tail" ? 900 : 220;
    let streamed = "";

    runningRef.current = true;
    clearTimers();
    setElapsedMs(0);
    setMessages([
      { id: userMessageId, role: "user", content: submittedPrompt, timestamp: Date.now() },
    ]);
    setIsLoading(true);
    setStreamingThinking("I am setting up a local fixture replay that simulates tool-heavy output before the answer stream starts.");
    setStreamingContent(null);

    emitDebug(debugHooks, { type: "run_started", prompt: submittedPrompt, timestamp: Date.now() });
    emitDebug(debugHooks, { type: "message_id_emitted", messageId: userMessageId, kind: "user", timestamp: Date.now() });

    intervalRef.current = setInterval(() => {
      setElapsedMs(Date.now() - runStartedAt);
    }, 120);

    schedule(180, () => {
      setMessages((current) => [
        ...current,
        {
          id: bashMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "Bash",
              input: JSON.stringify({ command: "rg -n \"viewport|selection|followOutput\" packages/tui/src -g \"*.ts*\"" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, { type: "tool_started", toolName: "Bash", callId: bashCallId, timestamp: Date.now() });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "Bash",
        callId: bashCallId,
        timestamp: Date.now(),
      });
    });

    schedule(980, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === bashMessageId
            ? {
                ...message,
                content: [
                    {
                      type: "tool_use",
                      toolName: "Bash",
                      input: JSON.stringify({ command: "rg -n \"viewport|selection|followOutput\" packages/tui/src -g \"*.ts*\"" }),
                      result: [
                        "packages/tui/src/vendor/ui/REPL.tsx: shouldAutoScrollToBottomOnContentUpdate",
                        "packages/tui/src/vendor/ui/REPL.tsx: getRemainingScrollDistance",
                        "packages/tui/src/vendor/ui/REPL.tsx: onViewportDebugEvent payload",
                        "packages/tui/src/vendor/ui/TranscriptViewport.tsx: shouldExposeMountedRangeClamp",
                        "packages/tui/src/vendor/ui/TranscriptViewport.tsx: shouldRefreshViewportSnapshotAfterLayout",
                        "packages/tui/src/vendor/ink-renderer/render-node-to-output.ts: shouldClampScrollTopForPaint",
                        "packages/tui/src/vendor/ink-renderer/render-node-to-output.ts: shouldPersistScrollTopAfterClamp",
                        buildLineAppendix("bash viewport trace", 12),
                      ].join("\n"),
                      status: "success",
                      durationMs: 800,
                    },
                ],
              }
            : message,
        ),
      );
      setStreamingThinking("The shell search confirms the viewport controller and transcript virtualization paths. Next I am simulating an MCP-style read so the transcript gets multiple dynamic-height updates.");
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "Bash",
        callId: bashCallId,
        ok: true,
        durationMs: 800,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "Bash",
        callId: bashCallId,
        ok: true,
        resultLength: 164,
        timestamp: Date.now(),
      });
    });

    schedule(1280, () => {
      setMessages((current) => [
        ...current,
        {
          id: mcpMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "MCP(secure-filesystem-server/read_text_file)",
              input: JSON.stringify({ path: "packages/tui/src/vendor/ui/REPL.tsx" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, {
        type: "tool_started",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        timestamp: Date.now(),
      });
    });

    schedule(2240, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === mcpMessageId
            ? {
                ...message,
                content: [
                    {
                      type: "tool_use",
                      toolName: "MCP(secure-filesystem-server/read_text_file)",
                      input: JSON.stringify({ path: "packages/tui/src/vendor/ui/REPL.tsx" }),
                      result: [
                        "const shouldAutoScroll = shouldAutoScrollToBottomOnContentUpdate(...)",
                        "const handle = scrollRef.current",
                        "const payload = { paintScrollTop, clampedToMaxScroll, usedPaintClamp, usedMountedRangeClamp }",
                        "if (snapshotKey === lastViewportDebugRef.current) return",
                        "dispatchViewport({ type: \"user_scrolled\" })",
                        "dispatchViewport({ type: \"scroll_draining_changed\", scrollDraining: true })",
                        "dispatchViewport({ type: \"resume_follow\" })",
                        buildLineAppendix("mcp viewport trace", 12),
                      ].join("\n"),
                      status: "success",
                      durationMs: 920,
                    },
                ],
              }
            : message,
        ),
      );
      setStreamingThinking("Now the fixture is entering the answer streaming phase. This is the part that used to be most likely to persist a bad clamp and yank the viewport.");
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        ok: true,
        durationMs: 920,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        ok: true,
        resultLength: 159,
        timestamp: Date.now(),
      });
    });

    schedule(2640, () => {
      setStreamingThinking(null);
      setStreamingContent("");
      emitDebug(debugHooks, {
        type: "stream_run_started",
        runId,
        prompt: submittedPrompt,
        timestamp: Date.now(),
      });
    });

    answerChunks.forEach((chunk, index) => {
      schedule(3000 + index * chunkDelayMs, () => {
        streamed += chunk;
        setStreamingContent(streamed);
        emitDebug(debugHooks, {
          type: "stream_chunk_flushed",
          runId,
          chunkLength: chunk.length,
          displayLength: streamed.length,
          sourceLength: streamed.length,
          timestamp: Date.now(),
        });
      });
    });

    schedule(3000 + answerChunks.length * chunkDelayMs + finalizeDelayMs, () => {
      setMessages((current) => [
        ...current,
        {
          id: assistantMessageId,
          role: "assistant",
          content: streamed,
          timestamp: Date.now(),
        },
      ]);
      setStreamingContent(null);
      setStreamingThinking(null);
      setIsLoading(false);
      setElapsedMs(Date.now() - runStartedAt);
      clearTimers();
      runningRef.current = false;

      emitDebug(debugHooks, {
        type: "stream_finalized",
        runId,
        reason: "turn_complete",
        finalAnswerLength: streamed.length,
        committedTextLength: streamed.length,
        replacedStreamed: true,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "stream_committed",
        runId,
        messageId: assistantMessageId,
        textLength: streamed.length,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "message_id_emitted",
        messageId: assistantMessageId,
        kind: "assistant",
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "stream_cleared",
        runId,
        reason: "turn_complete",
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "run_completed",
        prompt: submittedPrompt,
        turnState: "completed",
        elapsedMs: Date.now() - runStartedAt,
        finalAnswerLength: streamed.length,
        finalAnswerPreview: streamed.slice(0, 80),
        finalAnswerTail: streamed.slice(-80),
        reasoningLength: 0,
        streamedContentLength: streamed.length,
        committedStreamingLength: streamed.length,
        tokenEvents: 0,
        tokenChars: 0,
        reasoningEvents: 0,
        reasoningChars: 0,
        toolStarts: 2,
        toolEnds: 2,
        hadStreamingContent: true,
        hadStreamingThinking: true,
        toolResultCount: 2,
        stopReason: "completed",
        turnsUsed: 1,
        toolResults: [
          { name: "Bash", ok: true, contentLength: 164 },
          { name: "MCP(secure-filesystem-server/read_text_file)", ok: true, contentLength: 159 },
        ],
        newMessageCount: 4,
        timestamp: Date.now(),
      });
    });
  }, [clearTimers, debugHooks, schedule]);

  const runPhaseDiagnosticScenario = useCallback((
    submittedPrompt: string,
    mode: "phase-diagnostic-finalize-timeout" | "phase-diagnostic-no-progress",
  ) => {
    const runStartedAt = Date.now();
    const runId = `fixture-run-${randomUUID()}`;
    const toolCallId = `diag_${randomUUID()}`;
    const userMessageId = createMessageId("user");
    const toolMessageId = createMessageId("tool");
    const assistantMessageId = createMessageId("assistant");
    const isFinalizeTimeout = mode === "phase-diagnostic-finalize-timeout";
    const finalText = isFinalizeTimeout
      ? "Stopped after repeated empty finalize steps and reported finalize_timeout."
      : "Stopped after repeated low-progress steps and reported no_progress.";

    runningRef.current = true;
    clearTimers();
    setElapsedMs(0);
    setMessages([
      { id: userMessageId, role: "user", content: submittedPrompt, timestamp: Date.now() },
    ]);
    setIsLoading(true);
    setStreamingThinking(
      isFinalizeTimeout
        ? "The fixture is simulating a collected-results finalize path that never produces a real answer."
        : "The fixture is simulating repeated no-op tool reuse so the loop should stop with no_progress.",
    );
    setStreamingContent(null);

    emitDebug(debugHooks, { type: "run_started", prompt: submittedPrompt, timestamp: Date.now() });
    emitDebug(debugHooks, { type: "message_id_emitted", messageId: userMessageId, kind: "user", timestamp: Date.now() });

    intervalRef.current = setInterval(() => {
      setElapsedMs(Date.now() - runStartedAt);
    }, 120);

    schedule(120, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "analyze",
        detail: "entered_analysis",
        step: 2,
        timestamp: Date.now(),
      });
    });

    schedule(220, () => {
      setMessages((current) => [
        ...current,
        {
          id: toolMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "Bash",
              input: JSON.stringify({ command: "rg -n \"finalize|no_progress\" packages/agent/src/loop.ts" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, { type: "tool_started", toolName: "Bash", callId: toolCallId, timestamp: Date.now() });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "Bash",
        callId: toolCallId,
        timestamp: Date.now(),
      });
    });

    schedule(760, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === toolMessageId
            ? {
                ...message,
                content: [
                  {
                    type: "tool_use",
                    toolName: "Bash",
                    input: JSON.stringify({ command: "rg -n \"finalize|no_progress\" packages/agent/src/loop.ts" }),
                    result: [
                      "packages/agent/src/loop.ts: enterFinalize('stagnation')",
                      "packages/agent/src/loop.ts: empty_step_during_finalize",
                      "packages/agent/src/loop.ts: no_progress_hard_stop",
                    ].join("\n"),
                    status: "success",
                    durationMs: 540,
                  },
                ],
              }
            : message,
        ),
      );
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "Bash",
        callId: toolCallId,
        ok: true,
        durationMs: 540,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "Bash",
        callId: toolCallId,
        ok: true,
        resultLength: 120,
        timestamp: Date.now(),
      });
    });

    if (isFinalizeTimeout) {
      schedule(1080, () => {
        emitDebug(debugHooks, {
          type: "turn_phase",
          phase: "finalize",
          detail: "enter_finalize",
          finalizeReason: "stagnation",
          timestamp: Date.now(),
        });
        setStreamingThinking("The fixture has entered finalize mode and is now simulating empty finalize steps.");
      });
      schedule(1420, () => {
        emitDebug(debugHooks, {
          type: "turn_phase",
          phase: "finalize",
          detail: "empty_step_during_finalize",
          finalizeReason: "stagnation",
          finalizeAttempts: 1,
          step: 3,
          timestamp: Date.now(),
        });
      });
      schedule(1760, () => {
        emitDebug(debugHooks, {
          type: "turn_phase",
          phase: "finalize",
          detail: "forcing_markdown_answer",
          finalizeReason: "stagnation",
          finalizeAttempts: 1,
          step: 3,
          timestamp: Date.now(),
        });
      });
      schedule(2100, () => {
        emitDebug(debugHooks, {
          type: "turn_phase",
          phase: "finalize",
          detail: "empty_step_during_finalize",
          finalizeReason: "stagnation",
          finalizeAttempts: 2,
          step: 4,
          timestamp: Date.now(),
        });
      });
    } else {
      schedule(1280, () => {
        emitDebug(debugHooks, {
          type: "turn_phase",
          phase: "analyze",
          detail: "no_progress_hard_stop",
          noProgressCount: 5,
          step: 5,
          timestamp: Date.now(),
        });
      });
    }

    schedule(isFinalizeTimeout ? 2520 : 1780, () => {
      setMessages((current) => [
        ...current,
        {
          id: assistantMessageId,
          role: "assistant",
          content: finalText,
          timestamp: Date.now(),
        },
      ]);
      setStreamingThinking(null);
      setStreamingContent(null);
      setIsLoading(false);
      setElapsedMs(Date.now() - runStartedAt);
      clearTimers();
      runningRef.current = false;

      emitDebug(debugHooks, {
        type: "message_id_emitted",
        messageId: assistantMessageId,
        kind: "assistant",
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "run_completed",
        prompt: submittedPrompt,
        turnState: isFinalizeTimeout ? "timed_out" : "blocked",
        elapsedMs: Date.now() - runStartedAt,
        finalAnswerLength: finalText.length,
        finalAnswerPreview: finalText.slice(0, 80),
        finalAnswerTail: finalText.slice(-80),
        reasoningLength: 0,
        streamedContentLength: 0,
        committedStreamingLength: 0,
        tokenEvents: 0,
        tokenChars: 0,
        reasoningEvents: 0,
        reasoningChars: 0,
        toolStarts: 1,
        toolEnds: 1,
        hadStreamingContent: false,
        hadStreamingThinking: true,
        toolResultCount: 1,
        stopReason: isFinalizeTimeout ? "finalize_timeout" : "no_progress",
        turnsUsed: 1,
        toolResults: [
          { name: "Bash", ok: true, contentLength: 120 },
        ],
        newMessageCount: 3,
        timestamp: Date.now(),
      });
    });
  }, [clearTimers, debugHooks, schedule]);

  const runToolHeavyFinalizeTimeoutScenario = useCallback((submittedPrompt: string) => {
    const runStartedAt = Date.now();
    const toolRunId = `fixture-run-${randomUUID()}`;
    const bashCallId = `bash_${randomUUID()}`;
    const mcpCallId = `mcp_${randomUUID()}`;
    const userMessageId = createMessageId("user");
    const bashMessageId = createMessageId("tool");
    const mcpMessageId = createMessageId("tool");
    const assistantMessageId = createMessageId("assistant");
    const finalText = "The tool-heavy investigation completed, but the answer finalize path stalled and ended in finalize_timeout.";

    runningRef.current = true;
    clearTimers();
    setElapsedMs(0);
    setMessages([
      { id: userMessageId, role: "user", content: submittedPrompt, timestamp: Date.now() },
    ]);
    setIsLoading(true);
    setStreamingThinking("The fixture is simulating a real tool-heavy investigation before a delayed finalize timeout.");
    setStreamingContent(null);

    emitDebug(debugHooks, { type: "run_started", prompt: submittedPrompt, timestamp: Date.now() });
    emitDebug(debugHooks, { type: "message_id_emitted", messageId: userMessageId, kind: "user", timestamp: Date.now() });

    intervalRef.current = setInterval(() => {
      setElapsedMs(Date.now() - runStartedAt);
    }, 120);

    schedule(120, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "analyze",
        detail: "entered_analysis",
        step: 2,
        timestamp: Date.now(),
      });
    });

    schedule(180, () => {
      setMessages((current) => [
        ...current,
        {
          id: bashMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "Bash",
              input: JSON.stringify({ command: "rg -n \"finalize|no_progress|turn:phase\" packages/{agent,tui}/src -g \"*.ts*\"" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, { type: "tool_started", toolName: "Bash", callId: bashCallId, timestamp: Date.now() });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "Bash",
        callId: bashCallId,
        timestamp: Date.now(),
      });
    });

    schedule(980, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === bashMessageId
            ? {
                ...message,
                content: [
                  {
                    type: "tool_use",
                    toolName: "Bash",
                    input: JSON.stringify({ command: "rg -n \"finalize|no_progress|turn:phase\" packages/{agent,tui}/src -g \"*.ts*\"" }),
                    result: [
                      "packages/agent/src/loop.ts: retry_after_tool_intent_during_finalize",
                      "packages/agent/src/loop.ts: empty_step_during_finalize",
                      "packages/tui/src/replay.ts: summarizeTurnPhaseDebugEvents",
                      buildLineAppendix("tool-heavy finalize trace", 10),
                    ].join("\n"),
                    status: "success",
                    durationMs: 800,
                  },
                ],
              }
            : message,
        ),
      );
      setStreamingThinking("The first read-only tool completed. The fixture is now simulating a second inspection pass before the finalization stall.");
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "Bash",
        callId: bashCallId,
        ok: true,
        durationMs: 800,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "Bash",
        callId: bashCallId,
        ok: true,
        resultLength: 180,
        timestamp: Date.now(),
      });
    });

    schedule(1240, () => {
      setMessages((current) => [
        ...current,
        {
          id: mcpMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "MCP(secure-filesystem-server/read_text_file)",
              input: JSON.stringify({ path: "packages/agent/src/loop.ts" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, {
        type: "tool_started",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        timestamp: Date.now(),
      });
    });

    schedule(2140, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === mcpMessageId
            ? {
                ...message,
                content: [
                  {
                    type: "tool_use",
                    toolName: "MCP(secure-filesystem-server/read_text_file)",
                    input: JSON.stringify({ path: "packages/agent/src/loop.ts" }),
                    result: [
                      "enterFinalize('stagnation')",
                      "emitTurnPhase('finalize', 'enter_finalize')",
                      "emitTurnPhase('finalize', 'empty_step_during_finalize')",
                      buildLineAppendix("post-tool finalize stall", 10),
                    ].join("\n"),
                    status: "success",
                    durationMs: 900,
                  },
                ],
              }
            : message,
        ),
      );
      setStreamingThinking("Both tools are done. The fixture is now simulating the bad long-tail path where finalize keeps stalling after tool completion.");
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        ok: true,
        durationMs: 900,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        ok: true,
        resultLength: 210,
        timestamp: Date.now(),
      });
    });

    schedule(2500, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "finalize",
        detail: "enter_finalize",
        finalizeReason: "stagnation",
        step: 3,
        timestamp: Date.now(),
      });
    });
    schedule(3000, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "finalize",
        detail: "empty_step_during_finalize",
        finalizeReason: "stagnation",
        finalizeAttempts: 1,
        step: 4,
        timestamp: Date.now(),
      });
    });
    schedule(3400, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "finalize",
        detail: "forcing_markdown_answer",
        finalizeReason: "stagnation",
        finalizeAttempts: 1,
        step: 4,
        timestamp: Date.now(),
      });
    });
    schedule(3900, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "finalize",
        detail: "empty_step_during_finalize",
        finalizeReason: "stagnation",
        finalizeAttempts: 2,
        step: 5,
        timestamp: Date.now(),
      });
    });

    schedule(4700, () => {
      setMessages((current) => [
        ...current,
        {
          id: assistantMessageId,
          role: "assistant",
          content: finalText,
          timestamp: Date.now(),
        },
      ]);
      setStreamingThinking(null);
      setStreamingContent(null);
      setIsLoading(false);
      setElapsedMs(Date.now() - runStartedAt);
      clearTimers();
      runningRef.current = false;

      emitDebug(debugHooks, {
        type: "message_id_emitted",
        messageId: assistantMessageId,
        kind: "assistant",
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "run_completed",
        prompt: submittedPrompt,
        turnState: "timed_out",
        elapsedMs: Date.now() - runStartedAt,
        finalAnswerLength: finalText.length,
        finalAnswerPreview: finalText.slice(0, 80),
        finalAnswerTail: finalText.slice(-80),
        reasoningLength: 0,
        streamedContentLength: 0,
        committedStreamingLength: 0,
        tokenEvents: 0,
        tokenChars: 0,
        reasoningEvents: 0,
        reasoningChars: 0,
        toolStarts: 2,
        toolEnds: 2,
        hadStreamingContent: false,
        hadStreamingThinking: true,
        toolResultCount: 2,
        stopReason: "finalize_timeout",
        turnsUsed: 1,
        toolResults: [
          { name: "Bash", ok: true, contentLength: 180 },
          { name: "MCP(secure-filesystem-server/read_text_file)", ok: true, contentLength: 210 },
        ],
        newMessageCount: 4,
        timestamp: Date.now(),
      });
    });
  }, [clearTimers, debugHooks, schedule]);

  const runToolHeavyNoProgressScenario = useCallback((submittedPrompt: string) => {
    const runStartedAt = Date.now();
    const bashCallId = `bash_${randomUUID()}`;
    const mcpCallId = `mcp_${randomUUID()}`;
    const userMessageId = createMessageId("user");
    const bashMessageId = createMessageId("tool");
    const mcpMessageId = createMessageId("tool");
    const assistantMessageId = createMessageId("assistant");
    const finalText = "The tool-heavy investigation completed, but the loop made no further progress and ended in no_progress.";

    runningRef.current = true;
    clearTimers();
    setElapsedMs(0);
    setMessages([
      { id: userMessageId, role: "user", content: submittedPrompt, timestamp: Date.now() },
    ]);
    setIsLoading(true);
    setStreamingThinking("The fixture is simulating a tool-heavy investigation that later stalls without meaningful post-tool progress.");
    setStreamingContent(null);

    emitDebug(debugHooks, { type: "run_started", prompt: submittedPrompt, timestamp: Date.now() });
    emitDebug(debugHooks, { type: "message_id_emitted", messageId: userMessageId, kind: "user", timestamp: Date.now() });

    intervalRef.current = setInterval(() => {
      setElapsedMs(Date.now() - runStartedAt);
    }, 120);

    schedule(120, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "analyze",
        detail: "entered_analysis",
        step: 2,
        timestamp: Date.now(),
      });
    });

    schedule(180, () => {
      setMessages((current) => [
        ...current,
        {
          id: bashMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "Bash",
              input: JSON.stringify({ command: "rg -n \"no_progress|turn:phase|stagnation\" packages/{agent,tui}/src -g \"*.ts*\"" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, { type: "tool_started", toolName: "Bash", callId: bashCallId, timestamp: Date.now() });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "Bash",
        callId: bashCallId,
        timestamp: Date.now(),
      });
    });

    schedule(980, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === bashMessageId
            ? {
                ...message,
                content: [
                  {
                    type: "tool_use",
                    toolName: "Bash",
                    input: JSON.stringify({ command: "rg -n \"no_progress|turn:phase|stagnation\" packages/{agent,tui}/src -g \"*.ts*\"" }),
                    result: [
                      "packages/agent/src/loop.ts: no_progress_hard_stop",
                      "packages/agent/src/loop.ts: stagnationCount",
                      "packages/tui/src/replay.ts: turnPhaseSummary",
                      buildLineAppendix("tool-heavy no-progress trace", 10),
                    ].join("\n"),
                    status: "success",
                    durationMs: 800,
                  },
                ],
              }
            : message,
        ),
      );
      setStreamingThinking("The first read-only tool completed. The fixture is simulating a second inspection pass before the no-progress stop.");
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "Bash",
        callId: bashCallId,
        ok: true,
        durationMs: 800,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "Bash",
        callId: bashCallId,
        ok: true,
        resultLength: 170,
        timestamp: Date.now(),
      });
    });

    schedule(1240, () => {
      setMessages((current) => [
        ...current,
        {
          id: mcpMessageId,
          role: "assistant",
          content: [
            {
              type: "tool_use",
              toolName: "MCP(secure-filesystem-server/read_text_file)",
              input: JSON.stringify({ path: "packages/agent/src/loop.ts" }),
              status: "running",
            },
          ],
          timestamp: Date.now(),
        },
      ]);
      emitDebug(debugHooks, {
        type: "tool_started",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_started",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        timestamp: Date.now(),
      });
    });

    schedule(2140, () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === mcpMessageId
            ? {
                ...message,
                content: [
                  {
                    type: "tool_use",
                    toolName: "MCP(secure-filesystem-server/read_text_file)",
                    input: JSON.stringify({ path: "packages/agent/src/loop.ts" }),
                    result: [
                      "progressScore <= 0",
                      "noProgressCount >= 5",
                      "emitTurnPhase(phase, 'no_progress_hard_stop')",
                      buildLineAppendix("post-tool no-progress stall", 10),
                    ].join("\n"),
                    status: "success",
                    durationMs: 900,
                  },
                ],
              }
            : message,
        ),
      );
      setStreamingThinking("Both tools are done. The fixture is now simulating the bad long-tail path where no useful post-tool progress happens.");
      emitDebug(debugHooks, {
        type: "tool_runtime_state",
        stage: "dispatch_completed",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        ok: true,
        durationMs: 900,
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "tool_finished",
        toolName: "MCP(secure-filesystem-server/read_text_file)",
        callId: mcpCallId,
        ok: true,
        resultLength: 180,
        timestamp: Date.now(),
      });
    });

    schedule(2920, () => {
      emitDebug(debugHooks, {
        type: "turn_phase",
        phase: "analyze",
        detail: "no_progress_hard_stop",
        noProgressCount: 5,
        step: 5,
        timestamp: Date.now(),
      });
    });

    schedule(3780, () => {
      setMessages((current) => [
        ...current,
        {
          id: assistantMessageId,
          role: "assistant",
          content: finalText,
          timestamp: Date.now(),
        },
      ]);
      setStreamingThinking(null);
      setStreamingContent(null);
      setIsLoading(false);
      setElapsedMs(Date.now() - runStartedAt);
      clearTimers();
      runningRef.current = false;

      emitDebug(debugHooks, {
        type: "message_id_emitted",
        messageId: assistantMessageId,
        kind: "assistant",
        timestamp: Date.now(),
      });
      emitDebug(debugHooks, {
        type: "run_completed",
        prompt: submittedPrompt,
        turnState: "blocked",
        elapsedMs: Date.now() - runStartedAt,
        finalAnswerLength: finalText.length,
        finalAnswerPreview: finalText.slice(0, 80),
        finalAnswerTail: finalText.slice(-80),
        reasoningLength: 0,
        streamedContentLength: 0,
        committedStreamingLength: 0,
        tokenEvents: 0,
        tokenChars: 0,
        reasoningEvents: 0,
        reasoningChars: 0,
        toolStarts: 2,
        toolEnds: 2,
        hadStreamingContent: false,
        hadStreamingThinking: true,
        toolResultCount: 2,
        stopReason: "no_progress",
        turnsUsed: 1,
        toolResults: [
          { name: "Bash", ok: true, contentLength: 170 },
          { name: "MCP(secure-filesystem-server/read_text_file)", ok: true, contentLength: 180 },
        ],
        newMessageCount: 4,
        timestamp: Date.now(),
      });
    });
  }, [clearTimers, debugHooks, schedule]);

  const handleSubmit = useCallback((submittedPrompt: string) => {
    if (runningRef.current) {
      return;
    }

    switch (scenario) {
      case "tool-heavy-answer":
        runToolHeavyAnswerScenario(submittedPrompt || prompt, scenario);
        break;
      case "tool-heavy-answer-long-tail":
        runToolHeavyAnswerScenario(submittedPrompt || prompt, scenario);
        break;
      case "phase-diagnostic-finalize-timeout":
      case "phase-diagnostic-no-progress":
        runPhaseDiagnosticScenario(submittedPrompt || prompt, scenario);
        break;
      case "tool-heavy-finalize-timeout":
        runToolHeavyFinalizeTimeoutScenario(submittedPrompt || prompt);
        break;
      case "tool-heavy-no-progress":
        runToolHeavyNoProgressScenario(submittedPrompt || prompt);
        break;
      default:
        break;
    }
  }, [prompt, runPhaseDiagnosticScenario, runToolHeavyAnswerScenario, runToolHeavyFinalizeTimeoutScenario, runToolHeavyNoProgressScenario, scenario]);

  const statusSegments = useMemo(() => [
    { content: "fixture replay", color: "cyan" as const },
    { content: scenario, color: "gray" as const },
    { content: isLoading ? "Working" : "Ready", color: isLoading ? "yellow" as const : "green" as const },
  ], [isLoading, scenario]);

  return (
    <REPL
      onSubmit={handleSubmit}
      messages={messages}
      isLoading={isLoading}
      streamingThinking={streamingThinking}
      streamingContent={streamingContent}
      streamingElapsedMs={elapsedMs}
      presentationMode="claude"
      model={`fixture:${scenario}`}
      statusSegments={statusSegments}
      statusDetailLines={[]}
      onViewportDebugEvent={(event) => {
        if (event.debugType === "manual_scroll") {
          emitDebug(debugHooks, {
            type: "viewport_manual_scroll",
            action: event.action ?? "scroll_by",
            delta: event.delta,
            targetTop: event.targetTop,
            timestamp: Date.now(),
          });
          return;
        }

        emitDebug(debugHooks, {
          type: "viewport_state",
          ...event,
          timestamp: Date.now(),
        });
      }}
      placeholder="Replay fixture prompt"
    />
  );
}
