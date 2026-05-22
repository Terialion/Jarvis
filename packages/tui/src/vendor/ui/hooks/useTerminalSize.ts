import { TerminalSizeContext } from "../../ink-renderer/index.js";
import { useContext } from "react";

export type TerminalSize = {
  columns: number;
  rows: number;
};

export function useTerminalSize(): TerminalSize {
  const size = useContext(TerminalSizeContext);

  if (!size) {
    throw new Error("useTerminalSize must be used within an Ink App component");
  }

  return size;
}
