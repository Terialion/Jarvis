/**
 * Semver comparison utilities.
 * Uses npm semver package with static ESM import to avoid CJS require() issues.
 */
import semver from "semver";

export function gt(a: string, b: string): boolean {
  return semver.gt(a, b) ?? false;
}

export function gte(a: string, b: string): boolean {
  return semver.gte(a, b) ?? false;
}

export function lt(a: string, b: string): boolean {
  return semver.lt(a, b) ?? false;
}

export function lte(a: string, b: string): boolean {
  return semver.lte(a, b) ?? false;
}

export function satisfies(version: string, range: string): boolean {
  return semver.satisfies(version, range);
}

export function order(a: string, b: string): -1 | 0 | 1 {
  return (semver as any).compare(a, b) ?? 0;
}
