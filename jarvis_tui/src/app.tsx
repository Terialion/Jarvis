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
import type { PythonEvent, Message, ToolInfo, AskUserEvent, ModelChunk } from "./types.js";

// ── Helpers ────────────────────────────────────────────────────────

let _msgId = 0;
function nextId(): string {
  return `msg-${++_msgId}`;
}

function parseToolArgs(name: string, args: string): string {
  // Shorten tool arguments for display
  const maxLen = 60;
  if (args.length <= maxLen) return args;
  return args.slice(0, maxLen) + "...";
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

  // Track seen tool IDs to avoid duplicates
  const seenToolIds = useRef<Set<string>>(new Set());
  const turnStartTime = useRef<number>(0);

  // Refs for accumulated streaming state — always current, never stale
  const answerAccum = useRef("");
  const thinkingAccum = useRef("");
  const toolsAccum = useRef<ToolInfo[]>([]);

  // ── Initialize bridge ───────────────────────────────────────────

  useEffect(() => {
    const b = new JarvisBridge();
    bridge.current = b;

    // Wire up event handlers
    b.on("init", (ev: PythonEvent) => {
      if (ev.type === "init") {
        // Update model/git info from backend
        setConnected(true);
      }
    });

    b.on("chunk", (ev: PythonEvent) => {
      if (ev.type !== "chunk") return;
      handleChunk(ev.data as ModelChunk);
    });

    b.on("done", (ev: PythonEvent) => {
      if (ev.type !== "done") return;
      handleDone();
    });

    b.on("ask_user", (_ev: PythonEvent) => {
      // TODO: render a modal for user interaction
      // For now, auto-approve
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

    // Start the Python backend
    b.start(pythonPath, projectRoot);
    setConnected(true);

    // If there's an initial prompt, send it
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
        if (text) {
          answerAccum.current += text;
          setCurrentAnswer((prev) => prev + text);
        }
        break;
      }
      case "reasoning_delta":
      case "progress_delta": {
        const text = (chunk.reasoning_delta ?? chunk.progress_delta ?? "");
        if (text) {
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
        break;
      }
      case "done": {
        handleDone();
        break;
      }
    }
  }, []);

  // ── Done handling ───────────────────────────────────────────────

  const handleDone = useCallback(() => {
    const answer = answerAccum.current.trim();
    const thinking = thinkingAccum.current.trim();
    const tools = [...toolsAccum.current];

    // Finalize the current streaming message into message history
    if (answer || thinking) {
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

    // Save toggle data for the last turn
    setLastThinking(thinkingAccum.current);
    setLastToolsList([...toolsAccum.current]);

    // Reset streaming state
    answerAccum.current = "";
    thinkingAccum.current = "";
    toolsAccum.current = [];
    setCurrentAnswer("");
    setCurrentThinking("");
    setCurrentTools([]);
    setIsStreaming(false);
    seenToolIds.current.clear();

    // Compute latency
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

      // Reset streaming state for new turn
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

      // Add user message
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "user",
          content: text,
          timestamp: Date.now(),
        },
      ]);

      // Send to backend
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
  });

  // ── Render ──────────────────────────────────────────────────────

  return (
    <Box flexDirection="column" height={process.stdout.rows}>
      {/* Fixed top: status bar */}
      <StatusBar
        modelName={modelName}
        gitBranch={gitBranch}
        latency={latency}
        tokenCount={tokenCount}
        cost={cost}
        permissionMode={mode}
        isStreaming={isStreaming}
      />

      {/* Flexible middle: messages (flexGrow=1 fills remaining space) */}
      <MessageList
        messages={messages}
        currentAnswer={currentAnswer}
        currentThinking={currentThinking}
        currentTools={currentTools}
        thinkingExpanded={thinkingExpanded}
        toolsExpanded={toolsExpanded}
      />

      {/* Toggle hints */}
      <ToggleBlock
        hasThinking={!!lastThinking}
        hasTools={lastToolsList.length > 0}
        thinkingExpanded={thinkingExpanded}
        toolsExpanded={toolsExpanded}
      />

      {/* Fixed bottom: input bar */}
      <PromptInput
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
      />

      {/* Footer keybindings hint */}
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
