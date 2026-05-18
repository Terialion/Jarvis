/**
 * App — main TUI application component.
 *
 * Layout (Yoga Flexbox via Ink <Box>):
 * ┌─────────────────────────────┐
 * │ StatusBar (fixed top)       │ flexShrink=0
 * ├─────────────────────────────┤
 * │ MessageList (scrollable)    │ flexGrow=1 (fills available space)
 * ├─────────────────────────────┤
 * │ ToggleBlock (hints)        │ flexShrink=0
 * ├─────────────────────────────┤
 * │ PromptInput (fixed bottom)  │ flexShrink=0
 * ├─────────────────────────────┤
 * │ Footer (keybindings)       │ flexShrink=0
 * └─────────────────────────────┘
 *
 * The input bar "sticks" to the bottom naturally because:
 * - The outer Box has height = terminal rows (full screen)
 * - MessageList has flexGrow=1 (consumes all remaining space)
 * - PromptInput has flexShrink=0 (stays at intrinsic height)
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import { Box, Text, useInput, useApp } from "ink";
import { StatusBar } from "./components/StatusBar.js";
import { MessageList } from "./components/MessageList.js";
import { PromptInput } from "./components/PromptInput.js";
import { ToggleBlock } from "./components/ToggleBlock.js";
import { JarvisBridge } from "./bridge.js";
import type { PythonEvent, Message, ToolInfo, ModelChunk } from "./types.js";

// ── Helpers ────────────────────────────────────────────────────────

let _msgId = 0;
function nextId(): string {
  return `msg-${++_msgId}`;
}

function parseToolArgs(name: string, args: string): string {
  const firstLine = args.split("\n")[0];
  const maxLen = 80;
  if (firstLine.length <= maxLen) return firstLine;
  return firstLine.slice(0, maxLen) + "…";
}

const TOOL_TEXT_RE = /^\n?\[(?:Tool `[^`]+`|skill\.load `[^`]+`):\s/;

function isToolResultText(text: string): boolean {
  return TOOL_TEXT_RE.test(text);
}

function mapToolDisplay(name: string): string {
  const display: Record<string, string> = {
    bash: "Bash",
    file_read: "Read",
    file_write: "Write",
    file_edit: "Edit",
    glob: "Glob",
    grep: "Grep",
    web_search: "WebSearch",
    web_fetch: "WebFetch",
    task: "Task",
    ask: "AskUser",
    "command_runner.run": "Run",
    "skill_loader.load": "Skill",
    "skill_loader.run": "Skill",
    "web_search.search": "Search",
    "web_fetch.fetch": "Fetch",
  };
  return display[name] ?? name.split(".").pop() ?? name;
}

// ── App ────────────────────────────────────────────────────────────

interface AppProps {
  pythonPath: string;
  projectRoot: string;
  modelName: string;
  gitBranch: string;
  permissionMode: string;
  initialPrompt?: string;
}

export const App: React.FC<AppProps> = ({
  pythonPath,
  projectRoot,
  modelName,
  gitBranch,
  permissionMode,
  initialPrompt,
}) => {
  const { exit } = useApp();
  const bridge = useRef<JarvisBridge | null>(null);

  // ── State ──────────────────────────────────────────────────────

  const [messages, setMessages] = useState<Message[]>([]);
  const [currentAnswer, setCurrentAnswer] = useState("");
  const [currentThinking, setCurrentThinking] = useState("");
  const [currentTools, setCurrentTools] = useState<ToolInfo[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [latency, setLatency] = useState("");
  const [tokenCount, setTokenCount] = useState(0);
  const [cost, setCost] = useState(0);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [mode, setMode] = useState(permissionMode);
  const [lastThinking, setLastThinking] = useState("");
  const [lastToolsList, setLastToolsList] = useState<ToolInfo[]>([]);
  const [connected, setConnected] = useState(false);
  const [scrollOffset, setScrollOffset] = useState(0);

  // Track seen tool IDs to avoid duplicates
  const seenToolIds = useRef<Set<string>>(new Set());
  const turnStartTime = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Refs for accumulated streaming state — always current, never stale
  const answerAccum = useRef("");
  const thinkingAccum = useRef("");
  const toolsAccum = useRef<ToolInfo[]>([]);
  const hadToolCall = useRef(false);
  const hadReasoning = useRef(false);

  // ── Streaming timer — updates latency every second ──────────────

  useEffect(() => {
    if (isStreaming) {
      timerRef.current = setInterval(() => {
        if (turnStartTime.current > 0) {
          const elapsed = (Date.now() - turnStartTime.current) / 1000;
          if (elapsed >= 60) {
            const min = Math.floor(elapsed / 60);
            const sec = Math.floor(elapsed % 60);
            setLatency(`${min}m ${sec}s`);
          } else {
            setLatency(`${elapsed.toFixed(0)}s`);
          }
        }
      }, 1000);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isStreaming]);

  // ── Initialize bridge ───────────────────────────────────────────

  useEffect(() => {
    const b = new JarvisBridge();
    bridge.current = b;

    b.on("init", (ev: PythonEvent) => {
      if (ev.type === "init") {
        setConnected(true);
      }
    });

    b.on("chunk", (ev: PythonEvent) => {
      if (ev.type !== "chunk") return;
      handleChunk(ev.data as ModelChunk);
    });

    b.on("done", (ev: PythonEvent) => {
      if (ev.type !== "done") return;
      handleDone(ev.token_count, ev.cost);
    });

    b.on("ask_user", (_ev: PythonEvent) => {
      b.send({ type: "ask_user_response", answers: {} });
    });

    b.on("closed", (code: number | null) => {
      setConnected(false);
      if (code !== 0 && code !== null) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "system",
            content: `[Backend exited with code ${code}]`,
            timestamp: Date.now(),
          },
        ]);
      }
    });

    b.start(pythonPath, projectRoot);
    setConnected(true);

    if (initialPrompt) {
      handleSubmit(initialPrompt);
    }

    return () => {
      b.stop();
    };
  }, []);

  // ── Chunk handling ─────────────────────────────────────────────

  const handleChunk = useCallback((chunk: ModelChunk) => {
    switch (chunk.kind) {
      case "text_delta": {
        const text = chunk.text_delta ?? "";
        if (!text) break;
        if (isToolResultText(text)) break;
        if (hadToolCall.current) {
          answerAccum.current += text;
          setCurrentAnswer((prev) => prev + text);
        } else if (hadReasoning.current) {
          answerAccum.current += text;
          setCurrentAnswer((prev) => prev + text);
        } else {
          thinkingAccum.current += text;
          setCurrentThinking((prev) => prev + text);
        }
        break;
      }
      case "reasoning_delta":
      case "progress_delta": {
        const text = (chunk.reasoning_delta ?? chunk.progress_delta ?? "");
        if (text) {
          hadReasoning.current = true;
          thinkingAccum.current += text;
          setCurrentThinking((prev) => prev + text);
        }
        break;
      }
      case "tool_call_delta": {
        const callId = chunk.tool_call_id ?? "";
        const name = chunk.tool_name ?? "";
        if (!name) break;
        if (callId && seenToolIds.current.has(callId)) break;
        if (callId) seenToolIds.current.add(callId);

        const display = mapToolDisplay(name);
        const args = parseToolArgs(name, chunk.tool_arguments_delta ?? "");
        const tool: ToolInfo = { name, display, args, status: "ok" as const };
        toolsAccum.current = [...toolsAccum.current, tool];
        setCurrentTools((prev) => [...prev, tool]);
        hadToolCall.current = true;
        setToolsExpanded(true);
        break;
      }
      case "done": {
        handleDone();
        break;
      }
    }
  }, []);

  // ── Done handling ───────────────────────────────────────────────

  const handleDone = useCallback((tokenCountFromBackend?: number, costFromBackend?: number) => {
    const answer = answerAccum.current.trim();
    let thinking = thinkingAccum.current.trim();
    const tools = [...toolsAccum.current];

    // Track token count and cost from backend
    if (tokenCountFromBackend != null) setTokenCount(tokenCountFromBackend);
    if (costFromBackend != null) setCost(costFromBackend);

    if (!hadToolCall.current && thinking && !answer) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: thinking,
          timestamp: Date.now(),
        },
      ]);
      thinking = "";
    } else if (answer || thinking) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: answer || thinking,
          thinking: thinking || undefined,
          tools: tools.length > 0 ? tools : undefined,
          timestamp: Date.now(),
        },
      ]);
    }

    setLastThinking(thinking);
    setLastToolsList(tools);

    // Reset streaming state
    answerAccum.current = "";
    thinkingAccum.current = "";
    toolsAccum.current = [];
    hadToolCall.current = false;
    hadReasoning.current = false;
    setCurrentAnswer("");
    setCurrentThinking("");
    setCurrentTools([]);
    setIsStreaming(false);
    seenToolIds.current.clear();

    if (turnStartTime.current > 0) {
      const elapsed = (Date.now() - turnStartTime.current) / 1000;
      setLatency(`${elapsed.toFixed(1)}s`);
      turnStartTime.current = 0;
    }
  }, []);

  // ── Input handling ──────────────────────────────────────────────

  const handleSubmit = useCallback(
    (text: string) => {
      if (!bridge.current?.running) return;

      answerAccum.current = "";
      thinkingAccum.current = "";
      toolsAccum.current = [];
      setCurrentAnswer("");
      setCurrentThinking("");
      setCurrentTools([]);
      setThinkingExpanded(false);
      setToolsExpanded(false);
      setIsStreaming(true);
      setStatusText("Thinking...");
      setLatency("");
      turnStartTime.current = Date.now();
      seenToolIds.current.clear();
      hadToolCall.current = false;
      hadReasoning.current = false;

      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "user",
          content: text,
          timestamp: Date.now(),
        },
      ]);

      bridge.current.send({ type: "input", text });
    },
    [],
  );

  // ── Keyboard shortcuts ──────────────────────────────────────────

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      if (isStreaming) {
        bridge.current?.send({ type: "cancel" });
        handleDone();
      } else {
        exit();
      }
    }
    if (key.ctrl && input === "t") {
      if (lastThinking) setThinkingExpanded((prev) => !prev);
    }
    if (key.ctrl && input === "o") {
      if (lastToolsList.length > 0) setToolsExpanded((prev) => !prev);
    }
    if (key.shift && key.tab) {
      const modes = ["default", "plan", "accept_edits"];
      const idx = modes.indexOf(mode);
      setMode(modes[(idx + 1) % modes.length]);
    }
    if (key.pageUp) {
      setScrollOffset((prev) => prev + 5);
    }
    if (key.pageDown) {
      setScrollOffset((prev) => Math.max(0, prev - 5));
    }
  });

  // ── Render ──────────────────────────────────────────────────────

  const hasContent = messages.length > 0 || !!(currentAnswer || currentThinking || currentTools.length > 0);

  return (
    <Box flexDirection="column" height={hasContent ? Math.max(10, (process.stdout.rows ?? 50) - 1) : undefined}>
      <StatusBar
        modelName={modelName}
        projectRoot={projectRoot}
        gitBranch={gitBranch}
        latency={latency}
        tokenCount={tokenCount}
        cost={cost}
        permissionMode={mode}
        isStreaming={isStreaming}
      />

      <MessageList
        messages={messages}
        currentAnswer={currentAnswer}
        currentThinking={currentThinking}
        currentTools={currentTools}
        thinkingExpanded={thinkingExpanded}
        toolsExpanded={toolsExpanded}
        scrollOffset={scrollOffset}
        setScrollOffset={setScrollOffset}
      />

      <ToggleBlock
        hasThinking={!!lastThinking}
        hasTools={lastToolsList.length > 0}
        thinkingExpanded={thinkingExpanded}
        toolsExpanded={toolsExpanded}
      />

      <PromptInput
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
      />

      <Box height={1} flexShrink={0}>
        <Text dimColor>
          {"  "}
          {connected ? "●" : "○"} {connected ? "Ready" : "Connecting..."}
          {" · "}Ctrl+C {isStreaming ? "cancel" : "exit"}
          {" · "}Ctrl+T thinking
          {" · "}Ctrl+O tools
          {" · "}Shift+Tab mode
        </Text>
      </Box>
    </Box>
  );
};
