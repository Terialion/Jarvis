import type React from "react";
import { AlternateScreen } from "./vendor/ink-renderer/index.js";
import { KeybindingSetup } from "./vendor/ui/keybindings/KeybindingProviderSetup.js";

type TuiShellProps = {
  children: React.ReactNode;
};

/**
 * Fullscreen shell for the interactive TUI.
 *
 * Onboarding can stay on the main screen, but once the user enters the
 * normal chat workflow we switch to alt-screen ownership with shared
 * keybinding resolution and mouse tracking.
 */
export function TuiShell({ children }: TuiShellProps): React.ReactNode {
  return (
    <KeybindingSetup>
      <AlternateScreen mouseTracking>{children}</AlternateScreen>
    </KeybindingSetup>
  );
}
