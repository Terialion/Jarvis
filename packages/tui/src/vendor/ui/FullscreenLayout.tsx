import { Box } from "../ink-renderer/index.js";
import React, { type ReactNode } from "react";
import { PromptOverlayProvider, usePromptOverlaySlots } from "./PromptOverlayContext.js";

function FullscreenLayoutBody({
  scrollable,
  bottom,
}: {
  scrollable: ReactNode;
  bottom?: ReactNode;
}): ReactNode {
  const { overlay, modal, bottomFloat, bottomReplacement } = usePromptOverlaySlots();

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box flexGrow={1} flexShrink={1}>
        {scrollable}
      </Box>

      {overlay ? (
        <Box flexDirection="column" flexShrink={0}>
          {overlay}
        </Box>
      ) : null}

      {bottomFloat ? (
        <Box flexDirection="column" flexShrink={0}>
          {bottomFloat}
        </Box>
      ) : null}

      {bottomReplacement ? (
        <Box flexDirection="column" flexShrink={0}>
          {bottomReplacement}
        </Box>
      ) : bottom ? (
        <Box flexDirection="column" flexShrink={0}>
          {bottom}
        </Box>
      ) : null}

      {modal ? (
        <Box flexDirection="column" flexShrink={0}>
          {modal}
        </Box>
      ) : null}
    </Box>
  );
}

export function FullscreenLayout({
  scrollable,
  bottom,
  children,
}: {
  scrollable: ReactNode;
  bottom?: ReactNode;
  children?: ReactNode;
}): ReactNode {
  return (
    <PromptOverlayProvider>
      {children}
      <FullscreenLayoutBody scrollable={scrollable} bottom={bottom} />
    </PromptOverlayProvider>
  );
}
