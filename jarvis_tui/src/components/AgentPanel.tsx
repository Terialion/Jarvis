/**
 * AgentPanel — collapsible subagent status rows.
 *
 * Claude Code / Codex style: no border, dots for status, dimmed completed agents.
 */
import React from "react";
import { Box, Text } from "ink";
import type { SubagentInfo } from "../types.js";

interface AgentPanelProps {
  agents: SubagentInfo[];
  visible: boolean;
}

const STATUS_STYLE: Record<string, { icon: string; color: string }> = {
  running: { icon: "●", color: "green" },
  completed: { icon: "✓", color: "green" },
  failed: { icon: "✗", color: "red" },
  cancelled: { icon: "✗", color: "yellow" },
  pending: { icon: "○", color: "gray" },
};

const AgentRow: React.FC<{ agent: SubagentInfo }> = ({ agent }) => {
  const st = STATUS_STYLE[agent.status] ?? { icon: "?", color: "gray" };
  const isActive = agent.status === "running";
  const progress = agent.max_steps > 0 ? Math.min(agent.steps / agent.max_steps, 1) : 0;
  const barLen = 8;
  const filled = Math.round(progress * barLen);
  const bar = "█".repeat(filled) + "░".repeat(barLen - filled);

  return (
    <Box flexDirection="row">
      <Text color={isActive ? st.color : undefined}>{st.icon} </Text>
      <Text dimColor={!isActive}>
        {agent.agent_id.slice(0, 14).padEnd(15)}
        {agent.agent_type.padEnd(14)}[{bar}]{" "}
        {agent.status === "completed" ? "done" : agent.status === "running" ? `${agent.steps}/${agent.max_steps}` : agent.status}
      </Text>
    </Box>
  );
};

export const AgentPanel: React.FC<AgentPanelProps> = ({ agents, visible }) => {
  if (!visible || agents.length === 0) return null;

  const active = agents.filter((a) => a.status === "running");
  const others = agents.filter((a) => a.status !== "running");

  return (
    <Box flexDirection="column" marginBottom={1} paddingLeft={1}>
      <Text dimColor>
        Agents ({active.length} active) · Ctrl+A to close
      </Text>
      {[...active, ...others].slice(0, 10).map((a) => (
        <AgentRow key={a.agent_id} agent={a} />
      ))}
    </Box>
  );
};
