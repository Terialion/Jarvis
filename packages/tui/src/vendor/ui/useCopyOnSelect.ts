import { useEffect, useRef } from "react";
import type { useSelection } from "../ink-renderer/index.js";

type SelectionApi = ReturnType<typeof useSelection>;

export function useCopyOnSelect(
  selection: SelectionApi,
  isActive: boolean,
  onCopied?: (text: string) => void,
): void {
  const copiedRef = useRef(false);
  const onCopiedRef = useRef(onCopied);
  onCopiedRef.current = onCopied;

  useEffect(() => {
    if (!isActive) return;

    const unsubscribe = selection.subscribe(() => {
      const state = selection.getState();
      const hasSelection = selection.hasSelection();

      if (state?.isDragging) {
        copiedRef.current = false;
        return;
      }

      if (!hasSelection) {
        copiedRef.current = false;
        return;
      }

      if (copiedRef.current) return;

      const text = selection.copySelectionNoClear();
      copiedRef.current = true;
      if (!text || !text.trim()) return;
      onCopiedRef.current?.(text);
    });

    return unsubscribe;
  }, [isActive, selection]);
}
