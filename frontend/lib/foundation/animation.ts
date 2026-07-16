export const animationDurations = {
  instant: 0,
  fast: 150,
  normal: 220,
  slow: 320,
} as const;

export const animationEasings = {
  standard: "cubic-bezier(0.2, 0, 0, 1)",
  decelerate: "cubic-bezier(0, 0, 0, 1)",
  accelerate: "cubic-bezier(0.4, 0, 1, 1)",
} as const;

export function withMotionDuration(durationMs: number): Record<string, string> {
  return {
    ["--motion-duration" as string]: `${Math.max(0, durationMs)}ms`,
  };
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
