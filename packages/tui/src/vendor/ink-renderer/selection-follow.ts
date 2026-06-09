export function shouldTranslateSelectionOnFollow(input: {
  selectionModeActive: boolean;
  hasAnchor: boolean;
  anchorRow: number | null;
  focusRow: number | null;
  viewportTop: number;
  viewportBottom: number;
}): boolean {
  const { selectionModeActive, hasAnchor, anchorRow, focusRow, viewportTop, viewportBottom } = input;

  if (selectionModeActive) return false;
  if (!hasAnchor || anchorRow == null) return false;
  if (anchorRow < viewportTop || anchorRow > viewportBottom) return false;
  if (focusRow == null) return true;
  return focusRow >= viewportTop && focusRow <= viewportBottom;
}
