/**
 * App — main TUI application component.
 *
 * Claude Code-style inline output: completed messages go into <Static> so
 * they accumulate in the terminal scrollback. The dynamic Ink frame only
 * renders the current streaming content, status bar, and input area at the
 * bottom of the terminal.
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import { Box, Text, Static, useInput, useApp } from "ink";
import { StatusBar } from "./components/StatusBar.js";
import { MessageList } from "./components/MessageList.js";
import { MarkdownRenderer } from "./components/MarkdownRenderer.js";
import { PromptInput } from "./components/PromptInput.js";
import { ToggleBlock } from "./components/ToggleBlock.js";
import { JarvisBridge } from "./bridge.js";
import { AgentPanel } from "./components/AgentPanel.js";
import type { PythonEvent, Message, ToolInfo, ModelChunk, SubagentInfo, ContextUsageEvent, FileChange } from "./types.js";

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

const TOOL_RESULT_RE = /^\n?\[(?:Tool `([^`]+)`|skill\.load `([^`]+)`):\s*(.*)\]$/s;

function isToolResultText(text: string): boolean {
  return /^\n?\[(?:Tool `[^`]+`|skill\.load `[^`]+`):\s/.test(text);
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
    spawn_agent: "Spawn",
    wait_agent: "Wait",
    list_agents: "ListAgents",
    close_agent: "Close",
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
  version: string;
}

export const App: React.FC<AppProps> = ({
  pythonPath,
  projectRoot,
  modelName,
  gitBranch,
  permissionMode,
  initialPrompt,
  version,
}) => {
  const { exit } = useApp();
  const bridge = useRef<JarvisBridge | null>(null);

  // ── State ──────────────────────────────────────────────────────

  const [messages, setMessages] = useState<Message[]>([]);
  const [currentAnswer, setCurrentAnswer] = useState("");
  const [currentThinking, setCurrentThinking] = useState("");
  const [currentTools, setCurrentTools] = useState<ToolInfo[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [latency, setLatency] = useState("");
  const [tokenCount, setTokenCount] = useState(0);
  const [cost, setCost] = useState(0);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [mode, setMode] = useState(permissionMode);
  const [lastThinking, setLastThinking] = useState("");
  const [lastToolsList, setLastToolsList] = useState<ToolInfo[]>([]);
  const [connected, setConnected] = useState(false);
  const [agentPanelVisible, setAgentPanelVisible] = useState(false);
  const [subagents, setSubagents] = useState<SubagentInfo[]>([]);
  const [activeTool, setActiveTool] = useState("");
  const [contextUsed, setContextUsed] = useState(0);
  const [contextWindow, setContextWindow] = useState(0);
  const [fileChanges, setFileChanges] = useState<FileChange[]>([]);

  const seenToolIds = useRef<Set<string>>(new Set());
  const turnStartTime = useRef<number>(0);
  const turnActive = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Refs for accumulated streaming state
  const answerAccum = useRef("");
  const thinkingAccum = useRef("");
  const toolsAccum = useRef<ToolInfo[]>([]);
  const hadToolCall = useRef(false);
  const hadReasoning = useRef(false);

  // ── Streaming timer ────────────────────────────────────────────

  useEffect(() => {
    if (isStreaming === true) {
      timerRef.current = setInterval(() => {
        if (!turnActive.current) return;
        if (turnStartTime.current > 0) {
          const elapsed = (Date.now() - turnStartTime.current) / 1000;
          if (elapsed >= 3600) {
            const h = Math.floor(elapsed / 3600);
            const m = Math.floor((elapsed % 3600) / 60);
            const s = Math.floor(elapsed % 60);
            setLatency(`${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`);
          } else if (elapsed >= 60) {
            const min = Math.floor(elapsed / 60);
            const sec = Math.floor(elapsed % 60);
            setLatency(`${min}m ${String(sec).padStart(2, "0")}s`);
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

  // ── Initialize bridge ─────────────────────────────────────────

  useEffect(() => {
    const b = new JarvisBridge();
    bridge.current = b;

    b.on("init", (ev: PythonEvent) => {
      if (ev.type === "init") setConnected(true);
    });

    b.on("chunk", (ev: PythonEvent) => {
      if (ev.type !== "chunk") return;
      handleChunk(ev.data as ModelChunk);
    });

    b.on("done", (ev: PythonEvent) => {
      if (ev.type !== "done") return;
      handleDone(ev.finish_reason, ev.token_count, ev.cost);
    });

    b.on("context_usage", (ev: PythonEvent) => {
      if (ev.type === "context_usage") {
        setContextUsed(ev.data.used_tokens);
        setContextWindow(ev.data.context_window);
      }
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

  // ── Chunk handling ───────────────────────────────────────────

  const handleChunk = useCallback((chunk: ModelChunk) => {
    switch (chunk.kind) {
      case "text_delta": {
        const text = chunk.text_delta ?? "";
        if (!text) break;
        // Tool result — update the corresponding tool entry with result + status
        if (isToolResultText(text)) {
          const m = text.match(TOOL_RESULT_RE);
          if (m) {
            const toolName = m[1] || m[2] || "";
            const result = (m[3] || "").trim();
            setCurrentTools((prev) =>
              prev.map((t) =>
                t.name === toolName || t.display === toolName
                  ? { ...t, status: "ok" as const, result: result.slice(0, 500) }
                  : t
              )
            );
            toolsAccum.current = toolsAccum.current.map((t) =>
              t.name === toolName || t.display === toolName
                ? { ...t, status: "ok" as const, result: result.slice(0, 500) }
                : t
            );
          }
          break;
        }
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
        if (text === "__phase_thinking__") {
          // Transition from tool-execution to LLM-thinking phase.
          // Move current tools to completed so the TUI shows "Thinking..."
          // instead of stale tool names during LLM wait.
          if (toolsAccum.current.length > 0) {
            setLastToolsList([...toolsAccum.current]);
          }
          toolsAccum.current = [];
          setCurrentTools([]);
          setActiveTool("");
          break;
        }
        if (text) {
          const isFirstReasoning = !hadReasoning.current;
          hadReasoning.current = true;
          thinkingAccum.current += text;
          setCurrentThinking((prev) => prev + text);
          if (isFirstReasoning) setThinkingExpanded(true);
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
        const tool: ToolInfo = { name, display, args, status: "running" as const };
        const isFirstToolCall = !hadToolCall.current;
        toolsAccum.current = [...toolsAccum.current, tool];
        setCurrentTools((prev) => [...prev, tool]);
        setActiveTool(display);
        hadToolCall.current = true;
        if (isFirstToolCall) setToolsExpanded(true);
        break;
      }
      case "file_change": {
        const fc = chunk.file_change;
        if (fc) {
          setFileChanges((prev) => [...prev, fc]);
        }
        break;
      }
      case "done": {
        handleDone(chunk.finish_reason);
        break;
      }
    }
  }, []);

  // ── Done handling ─────────────────────────────────────────────

  const handleDone = useCallback((finishReason?: string, tokenCountFromBackend?: number, costFromBackend?: number) => {
    turnActive.current = false;
    const answer = answerAccum.current.trim();
    let thinking = thinkingAccum.current.trim();
    const tools = [...toolsAccum.current];

    if (tokenCountFromBackend != null) setTokenCount(tokenCountFromBackend);
    if (costFromBackend != null) setCost(costFromBackend);

    // Clear streaming state BEFORE adding to Static messages.
    // This prevents Ink from rendering the same answer in both
    // MessageList (streaming) and Static (completed) simultaneously.
    answerAccum.current = "";
    thinkingAccum.current = "";
    toolsAccum.current = [];
    hadToolCall.current = false;
    hadReasoning.current = false;
    setCurrentAnswer("");
    setCurrentThinking("");
    setCurrentTools([]);
    setFileChanges([]);
    setActiveTool("");
    setIsStreaming(false);
    seenToolIds.current.clear();

    const isFailure = finishReason && finishReason !== "stop" && finishReason !== "completed";

    if (isFailure && !answer) {
      const reasonLabel = finishReason === "timeout" ? "Turn timed out"
        : finishReason === "max_steps" ? "Reached max steps"
        : finishReason === "error" ? "Agent error"
        : `Stopped: ${finishReason}`;
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "system",
          content: `[${reasonLabel}]`,
          thinking: thinking || undefined,
          tools: tools.length > 0 ? tools : undefined,
          timestamp: Date.now(),
        },
      ]);
      thinking = "";
    } else if (answer) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: answer,
          thinking: thinking || undefined,
          tools: tools.length > 0 ? tools : undefined,
          timestamp: Date.now(),
        },
      ]);
    } else if (thinking) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "system",
          content: "[Model produced reasoning but no answer — try lowering reasoning effort or increasing max_tokens]",
          thinking: thinking,
          timestamp: Date.now(),
        },
      ]);
    }

    setLastThinking(thinking);
    setLastToolsList(tools);

    if (turnStartTime.current > 0) {
      const elapsed = (Date.now() - turnStartTime.current) / 1000;
      if (elapsed >= 3600) {
        const h = Math.floor(elapsed / 3600);
        const m = Math.floor((elapsed % 3600) / 60);
        const s = Math.floor(elapsed % 60);
        setLatency(`${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`);
      } else if (elapsed >= 60) {
        const min = Math.floor(elapsed / 60);
        const sec = Math.floor(elapsed % 60);
        setLatency(`${min}m ${String(sec).padStart(2, "0")}s`);
      } else {
        setLatency(`${elapsed.toFixed(1)}s`);
      }
      turnStartTime.current = 0;
    }
  }, []);

  // ── Input handling ────────────────────────────────────────────

  const handleSubmit = useCallback(
    (text: string) => {
      if (!bridge.current?.running) return;

      answerAccum.current = "";
      thinkingAccum.current = "";
      toolsAccum.current = [];
      setCurrentAnswer("");
      setCurrentThinking("");
      setCurrentTools([]);
      setFileChanges([]);
      setActiveTool("");
      setThinkingExpanded(false);
      setToolsExpanded(false);
      setIsStreaming(true);
      setLatency("");
      turnActive.current = true;
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

  // ── Keyboard shortcuts ────────────────────────────────────────

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
      if (currentThinking || lastThinking) setThinkingExpanded((prev) => !prev);
    }
    if (key.ctrl && input === "o") {
      if (currentTools.length > 0 || lastToolsList.length > 0) setToolsExpanded((prev) => !prev);
    }
    if (key.ctrl && input === "a") {
      setAgentPanelVisible((prev) => !prev);
    }
    if (key.shift && key.tab) {
      const modes = ["default", "plan", "accept_edits"];
      const idx = modes.indexOf(mode);
      setMode(modes[(idx + 1) % modes.length]);
    }
  });

  // ── Render ────────────────────────────────────────────────────

  // Completed messages go into <Static> — they accumulate in the
  // terminal scrollback like regular command output. The terminal's
  // native scrollback handles scrolling; no virtual scrolling needed.
  const staticItems = messages.map((msg) => ({ key: msg.id, ...msg }));

  return (
    <Box flexDirection="column">
      {/* Completed messages — permanent in terminal scrollback */}
      <Static items={staticItems}>
        {(msg: Message) => (
          <Box key={msg.id} flexDirection="column" marginBottom={1}>
            {msg.role === "user" ? (
              <Text dimColor>❯ {msg.content}</Text>
            ) : (
              <MarkdownRenderer content={msg.content} />
            )}
          </Box>
        )}
      </Static>

      {/* Dynamic frame: status + agent panel + streaming + input */}
      <StatusBar
        modelName={modelName}
        latency={latency}
        tokenCount={tokenCount}
        cost={cost}
        isStreaming={isStreaming}
        activeTool={activeTool || undefined}
        activeAgents={subagents.filter(a => a.status === "running").length}
        contextUsed={contextUsed}
        contextWindow={contextWindow}
      />

      <AgentPanel agents={subagents} visible={agentPanelVisible} />

      <MessageList
        currentAnswer={currentAnswer}
        currentThinking={currentThinking}
        currentTools={currentTools}
        thinkingExpanded={thinkingExpanded}
        toolsExpanded={toolsExpanded}
        isStreaming={isStreaming}
        fileChanges={fileChanges}
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

      {/* Footer — minimal hints */}
      <Box height={1} flexShrink={0} paddingX={1}>
        <Text dimColor>
          {connected ? "●" : "○"} Ctrl+C {isStreaming ? "cancel" : "exit"}
          {" · "}Ctrl+T thinking
          {" · "}Ctrl+O tools
          {" · "}Ctrl+A agents
          {" · "}Shift+Tab {mode}
        </Text>
      </Box>
    </Box>
  );
};
