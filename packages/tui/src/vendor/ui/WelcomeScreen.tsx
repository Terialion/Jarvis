import { Box, Text } from "../ink-renderer/index.js";
import type React from "react";
import { getStableKeys } from "./utils/stableKeys";

const DEFAULT_COLOR = "#DA7756";

export type WelcomeScreenProps = {
  appName: string;
  subtitle?: string;
  version?: string;
  tips?: string[];
  logo?: React.ReactNode;
  model?: string;
  color?: string;
};

export function ArcReactorLogo({ color = DEFAULT_COLOR }: { color?: string }): React.ReactNode {
  return (
    <Box flexDirection="column">
      <Text color={color}>{"   ▄████████▄   "}</Text>
      <Text color={color}>{" ▄███▀    ▀███▄ "}</Text>
      <Text color={color}>{"▐███  ▄▀▀▄  ███▌"}</Text>
      <Text color={color}>{"████ ▐█  █▌ ████"}</Text>
      <Text color={color}>{"████  ▀▄▄▀  ████"}</Text>
      <Text color={color}>{" ███▄      ▄███"}</Text>
      <Text color={color}>{"  ▀██████████▀  "}</Text>
      <Text color={color}>{"    ▀██████▀   "}</Text>
    </Box>
  );
}

/** @deprecated Use ArcReactorLogo instead */
export function ClawdLogo({ color = DEFAULT_COLOR }: { color?: string }): React.ReactNode {
  return <ArcReactorLogo color={color} />;
}

export function WelcomeScreen({
  appName,
  subtitle,
  version,
  tips,
  logo,
  model,
  color = DEFAULT_COLOR,
}: WelcomeScreenProps): React.ReactNode {
  const logoNode = logo ?? <ArcReactorLogo color={color} />;
  const tipKeys = tips ? getStableKeys(tips, (tip) => tip) : [];

  return (
    <Box flexDirection="column" marginTop={1} marginLeft={1}>
      <Box flexDirection="row" gap={2} alignItems="center">
        {logoNode}
        <Box flexDirection="column">
          <Box flexDirection="row" gap={1}>
            <Text bold color={color}>
              {appName}
            </Text>
            {version && <Text dimColor>{`v${version}`}</Text>}
          </Box>
          {subtitle && <Text dimColor>{subtitle}</Text>}
          {model && <Text dimColor>{model}</Text>}
        </Box>
      </Box>

      {tips && tips.length > 0 && (
        <Box flexDirection="row" marginTop={1}>
          {tips.map((tip, index) => (
            <Box key={tipKeys[index]} flexDirection="row">
              {index > 0 && <Text dimColor> · </Text>}
              <Text dimColor>{tip}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
