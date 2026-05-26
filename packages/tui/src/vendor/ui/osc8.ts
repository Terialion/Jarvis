// ============================================================================
// OSC 8 hyperlink support (OpenClaw pattern)
// ============================================================================

/** Check if the terminal supports OSC 8 hyperlinks. */
export function supportsOsc8(): boolean {
  // Most modern terminals support OSC 8: iTerm2, Windows Terminal, Kitty,
  // WezTerm, Ghostty, VSCode terminal, Warp, Konsole 22.04+
  // Do a basic check: skip environments known to not support it
  if (process.env['TERM_PROGRAM'] === 'Apple_Terminal') return false;
  if (process.env['TMUX'] && !process.env['TMUX_VERSION']) return false;
  return true;
}

/**
 * Wrap text in an OSC 8 hyperlink escape sequence.
 * Format: OSC 8 ; params ; uri ST  text  OSC 8 ; ; ST
 */
export function osc8Link(url: string, text: string): string {
  if (!url || !text) return text;
  // Strip any existing OSC 8 sequences from url and text
  const cleanUrl = url.replace(/\x1b\]8;.*?\x07/g, '').replace(/\x1b\]8;.*?\x1b\\/g, '');
  const cleanText = text.replace(/\x1b\]8;.*?\x07/g, '').replace(/\x1b\]8;.*?\x1b\\/g, '');
  return `\x1b]8;;${cleanUrl}\x07${cleanText}\x1b]8;;\x07`;
}

/**
 * Wrap a bare URL to make it clickable. Uses the URL itself as display text.
 */
export function makeClickableUrl(url: string): string {
  return osc8Link(url, url);
}

/**
 * Post-process text to add OSC 8 links for bare URLs and [text](url) patterns.
 */
export function addOsc8Links(text: string): string {
  if (!supportsOsc8()) return text;

  // Match [text](url) markdown links
  const mdLinkRe = /\[([^\]]+)\]\((\bhttps?:\/\/[^\s)]+)\)/g;
  let result = text.replace(mdLinkRe, (_match, label, url) => {
    return osc8Link(url, label);
  });

  // Match bare https? URLs (not already inside OSC 8)
  result = result.replace(
    /(?<!\x1b\]8;;)(\bhttps?:\/\/[^\s\x1b]+)/g,
    (url) => osc8Link(url, url),
  );

  return result;
}
