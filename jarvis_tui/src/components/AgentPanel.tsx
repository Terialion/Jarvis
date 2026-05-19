import React from "react";
import { Box, Text } from "ink";
import type { SubagentInfo } from "../types.js";

interface AgentPanelProps {
  agents: SubagentInfo[];
  visible: boolean;
}

const STATUS_MAP: Record<string, { icon: string; color: string }> = {
  running: { icon: "●", color: "green" },
  completed: { icon: "✓", color: "green" },
  failed: { icon: "✗", color: "red" },
  cancelled: { icon: "✗", color: "yellow" },
  pending: { icon: "○", color: "gray" },
};

const AgentRow: React.FC<{ agent: SubagentInfo }> = ({ agent }) => {
  const st = STATUS_MAP[agent.status] ?? { icon: "?", color: "gray" };
  const progress = agent.max_steps > 0 ? Math.min(agent.steps / agent.max_steps, 1) : 0;
  const barLen = 8;
  const filled = Math.round(progress * barLen);
  const bar = "█".repeat(filled) + "░".repeat(barLen - filled);

  return (
    <Box flexDirection="row">
      <Text color={st.color}>{st.icon} </Text>
      <Text>{agent.agent_id.slice(0, 14)} </Text>
      <Text dimColor>{agent.agent_type.padEnd(12)} </Text>
      <Text>[{bar}] </Text>
      <Text>
        {agent.status === "completed" ? "✓" : `${agent.steps}/${agent.max_steps}`}
      </Text>
    </Box>
  );
};

export const AgentPanel: React.FC<AgentPanelProps> = ({ agents, visible }) => {
  if (!visible) return null;

  const active = agents.filter((a) => a.status === "running");
  const others = agents.filter((a) => a.status !== "running");

  if (agents.length === 0) return null;

  return (
    <Box
      flexDirection="column"
      borderStyle="single"
      borderColor="gray"
      paddingLeft={1}
      paddingRight={1}
      marginBottom={1}
    >
      <Text bold>
        Agents ({active.length} active)
      </Text>
      {[...active, ...others].slice(0, 10).map((a) => (
        <AgentRow key={a.agent_id} agent={a} />
      ))}
    </Box>
  );
};
