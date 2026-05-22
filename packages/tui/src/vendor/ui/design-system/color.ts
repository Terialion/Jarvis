import type { Color } from "../../ink-renderer/index.js";
import { type ColorType, colorize } from "../../ink-renderer/index.js";
import { getTheme, type Theme, type ThemeName } from "./ThemeProvider";

/**
 * Curried theme-aware color function. Resolves theme keys to raw color
 * values before delegating to the ink renderer's colorize.
 */
export function color(
  c: keyof Theme | Color | undefined,
  theme: ThemeName,
  type: ColorType = "foreground",
): (text: string) => string {
  return (text) => {
    if (!c) {
      return text;
    }
    if (
      c.startsWith("rgb(") ||
      c.startsWith("#") ||
      c.startsWith("ansi256(") ||
      c.startsWith("ansi:")
    ) {
      return colorize(text, c, type);
    }
    return colorize(text, getTheme(theme)[c as keyof Theme], type);
  };
}
