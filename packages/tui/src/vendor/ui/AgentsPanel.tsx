import { Box, ScrollBox, Text } from "../ink-renderer/index.js";
import type React from "react";
import { useEffect, useMemo, useState } from "react";

export interface AgentStatusEntry {
  agentId: string;
  status: string;
  role: string;
  depth: number;
  parentId: string | null;
  task?: string;
  toolCount?: number;
  elapsedMs?: number;
  startedAt?: number;
}

function statusGlyph(status: string): { glyph: string; color: string } {
  switch (status) {
    case "running":
      return { glyph: "●", color: "#E6B450" };
    case "pending":
      return { glyph: "○", color: "#808080" };
    case "completed":
      return { glyph: "✓", color: "#5FAF5F" };
    case "failed":
      return { glyph: "✕", color: "#D75F5F" };
    case "cancelled":
      return { glyph: "◌", color: "#D7AF00" };
    default:
      return { glyph: "○", color: "#808080" };
  }
}

function formatElapsed(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function compactTask(task?: string, width = 60): string {
  if (!task) return "";
  const trimmed = task.replace(/\s+/g, " ").trim();
  return trimmed.length > width ? `${trimmed.slice(0, width - 3)}...` : trimmed;
}

interface TreeNode {
  agent: AgentStatusEntry;
  children: TreeNode[];
}

function buildTree(agents: AgentStatusEntry[]): TreeNode[] {
  const byParent = new Map<string | null, TreeNode[]>();
  for (const agent of agents) {
    const key = agent.parentId;
    if (!byParent.has(key)) byParent.set(key, []);
    byParent.get(key)!.push({ agent, children: [] });
  }

  function fillChildren(nodes: TreeNode[]): void {
    for (const node of nodes) {
      const children = byParent.get(node.agent.agentId) || [];
      node.children = children;
      fillChildren(children);
    }
  }

  const roots = byParent.get(null) || [];
  fillChildren(roots);
  return roots;
}

function treeToRows(
  nodes: TreeNode[],
  depth: number,
): Array<{ node: TreeNode; id: string; depth: number }> {
  const rows: Array<{ node: TreeNode; id: string; depth: number }> = [];
  for (const node of nodes) {
    rows.push({ node, id: node.agent.agentId, depth });
    rows.push(...treeToRows(node.children, depth + 1));
  }
  return rows;
}

export type AgentsPanelProps = {
  agents: AgentStatusEntry[];
  visible: boolean;
  onClose: () => void;
};

export function AgentsPanel({ agents, visible }: AgentsPanelProps): React.ReactNode {
  if (!visible) return null;

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const rows = useMemo(() => treeToRows(buildTree(agents), 0), [agents]);

  useEffect(() => {
    if (selectedIndex >= rows.length) {
      setSelectedIndex(Math.max(0, rows.length - 1));
    }
  }, [rows.length, selectedIndex]);

  const running = agents.filter((agent) => agent.status === "running").length;
  const completed = agents.filter((agent) => agent.status === "completed").length;
  const failed = agents.filter((agent) => agent.status === "failed").length;

  if (agents.length === 0) {
    return (
      <Box flexDirection="column" marginTop={1} padding={1} borderStyle="single" borderColor="#808080">
        <Box>
          <Text dimColor>Agents (0 active)</Text>
          <Text> </Text>
          <Text dimColor>Ctrl+G to close</Text>
        </Box>
        <Box marginTop={1}>
          <Text dimColor>No active agents. Use the Agent tool to spawn subagents.</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginTop={1} paddingX={1} borderStyle="single" borderColor="#808080">
      <Box>
        <Text bold color="#E6B450">Agents</Text>
        <Text dimColor> ({agents.length} total</Text>
        {running > 0 && (
          <>
            <Text dimColor>, </Text>
            <Text color="#E6B450">{running} running</Text>
          </>
        )}
        {completed > 0 && (
          <>
            <Text dimColor>, </Text>
            <Text color="#5FAF5F">{completed} done</Text>
          </>
        )}
        {failed > 0 && (
          <>
            <Text dimColor>, </Text>
            <Text color="#D75F5F">{failed} failed</Text>
          </>
        )}
        <Text dimColor>)</Text>
        <Text> </Text>
        <Text dimColor>q close · j/k navigate</Text>
      </Box>

      <ScrollBox flexDirection="column" marginTop={1} maxHeight={Math.min(rows.length + 1, 16)}>
        {rows.map(({ node, depth, id }, index) => {
          const { glyph, color } = statusGlyph(node.agent.status);
          const indent = "  ".repeat(depth);
          const connector =
            depth > 0 ? (index < rows.length - 1 && rows[index + 1]?.depth >= depth ? "├─ " : "└─ ") : "";
          const selected = index === selectedIndex;
          const elapsed = node.agent.startedAt ? now - node.agent.startedAt : undefined;
          const taskPreview = compactTask(node.agent.task, 40);
          const toolsInfo = node.agent.toolCount ? ` · ${node.agent.toolCount}t` : "";

          return (
            <Box key={id}>
              {selected ? <Text color="#E6B450">› </Text> : <Text>  </Text>}
              <Text color={color}>{glyph}</Text>
              <Text> {indent}{connector}</Text>
              <Text bold={selected} color={selected ? "#E6B450" : undefined}>
                {node.agent.agentId}
              </Text>
              <Text dimColor> ({node.agent.role})</Text>
              {elapsed && node.agent.status === "running" && (
                <Text dimColor> {formatElapsed(elapsed)}</Text>
              )}
              <Text dimColor>{toolsInfo}</Text>
              {taskPreview && <Text dimColor> - {taskPreview}</Text>}
            </Box>
          );
        })}
      </ScrollBox>
    </Box>
  );
}
