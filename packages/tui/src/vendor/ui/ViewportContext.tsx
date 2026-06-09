import React, { createContext, useContext, useMemo, type ReactNode } from "react";
import type { ViewportAction, ViewportMode, ViewportState } from "./viewport-controller.js";

export type ViewportContextValue = ViewportState & {
  dispatch: (action: ViewportAction) => void;
  stopFollowingOutput: (mode?: Exclude<ViewportMode, "following">) => void;
  resumeFollowingOutput: () => void;
  handleBottomAction: () => void;
};

const ViewportContext = createContext<ViewportContextValue | null>(null);

export function ViewportProvider({
  value,
  children,
}: {
  value: ViewportContextValue;
  children?: ReactNode;
}): ReactNode {
  const memoized = useMemo(() => value, [value]);
  return <ViewportContext.Provider value={memoized}>{children}</ViewportContext.Provider>;
}

export function useViewportContext(): ViewportContextValue {
  const value = useContext(ViewportContext);
  if (!value) {
    throw new Error("ViewportContext is not available");
  }
  return value;
}
