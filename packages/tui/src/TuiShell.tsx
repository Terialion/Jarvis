import type React from "react";
import { AlternateScreen } from "./vendor/ink-renderer/index.js";
import { KeybindingSetup } from "./vendor/ui/keybindings/KeybindingProviderSetup.js";

type TuiShellProps = {
  children: React.ReactNode;
  /** When true, skip alternate screen — render on main screen with native scrollback. */
  mainScreen?: boolean;
};

/**
 * Shell for the interactive TUI.
 *
 * By default wraps children in AlternateScreen (fullscreen with mouse tracking).
 * When mainScreen is true, renders directly on the main screen — output goes to
 * stdout, native terminal scrollback works, no alternate buffer.
 */
export function TuiShell({ children, mainScreen }: TuiShellProps): React.ReactNode {
  if (mainScreen) {
    return (
      <KeybindingSetup>
        {children}
      </KeybindingSetup>
    );
  }

  return (
    <KeybindingSetup>
      <AlternateScreen mouseTracking>{children}</AlternateScreen>
    </KeybindingSetup>
  );
}
