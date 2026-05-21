// ============================================================================
// Environment Detection
// ============================================================================

import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';

/**
 * Detect the runtime platform.
 */
export function detectPlatform(): 'windows' | 'linux' | 'macos' {
  const plat = process.platform;
  if (plat === 'win32') return 'windows';
  if (plat === 'darwin') return 'macos';
  return 'linux';
}

/**
 * Check if running inside Windows Subsystem for Linux.
 *
 * Detects WSL by checking for:
 * - WSL-specific files in /proc/sys/fs/binfmt_misc/
 * - WSL_DISTRO_NAME environment variable
 * - "microsoft" or "WSL" in uname output (via filesystem)
 */
export function isWSL(): boolean {
  const platform = process.platform;
  if (platform !== 'linux') return false;

  // WSL interop marker file
  if (existsSync('/proc/sys/fs/binfmt_misc/WSLInterop')) {
    return true;
  }

  // Environment variable set by WSL
  if (process.env.WSL_DISTRO_NAME) {
    return true;
  }

  return false;
}

/**
 * Check if running inside a container (Docker / Podman).
 *
 * Detection is best-effort and checks:
 * - Presence of /.dockerenv file
 * - container environment variable
 * - /proc/1/cgroup for docker/podman/container references
 */
export function isContainer(): boolean {
  // Docker creates this file
  if (existsSync('/.dockerenv')) {
    return true;
  }

  // Podman and some Docker setups set this env var
  if (process.env.container) {
    return true;
  }

  // Check cgroup for container runtime references
  try {
    const cgroup = readFileSync('/proc/1/cgroup', 'utf-8');
    const cgroupLower = cgroup.toLowerCase();
    if (
      cgroupLower.includes('docker') ||
      cgroupLower.includes('podman') ||
      cgroupLower.includes('containerd') ||
      cgroupLower.includes('/lxc/') ||
      cgroupLower.includes('/kubepods/')
    ) {
      return true;
    }
  } catch {
    // /proc/1/cgroup doesn't exist or isn't readable — not a container
  }

  return false;
}

/**
 * Get the Jarvis home directory.
 *
 * Uses the JARVIS_HOME environment variable if set,
 * otherwise falls back to ~/.jarvis.
 */
export function getJarvisHome(): string {
  if (process.env.JARVIS_HOME) {
    return process.env.JARVIS_HOME;
  }
  return `${homedir()}/.jarvis`;
}

/**
 * Get the default shell for the current platform.
 *
 * Respects the SHELL environment variable on Unix-like systems.
 * Falls back to platform-appropriate defaults.
 */
export function getDefaultShell(): string {
  // Respect SHELL env var if set
  const shellEnv = process.env.SHELL;
  if (shellEnv) {
    return shellEnv;
  }

  const platform = detectPlatform();

  switch (platform) {
    case 'windows':
      // PowerShell is preferred on modern Windows
      return 'powershell.exe';
    case 'linux':
    case 'macos':
      return '/bin/sh';
  }
}
