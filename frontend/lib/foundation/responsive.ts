export const responsiveBreakpoints = {
  xs: 360,
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  xxl: 1536,
} as const;

export type BreakpointKey = keyof typeof responsiveBreakpoints;

export function up(bp: BreakpointKey): string {
  return `(min-width: ${responsiveBreakpoints[bp]}px)`;
}

export function down(bp: BreakpointKey): string {
  return `(max-width: ${responsiveBreakpoints[bp] - 0.02}px)`;
}

export function between(minBp: BreakpointKey, maxBp: BreakpointKey): string {
  const min = responsiveBreakpoints[minBp];
  const max = responsiveBreakpoints[maxBp] - 0.02;
  return `(min-width: ${min}px) and (max-width: ${max}px)`;
}

export function matchesMediaQuery(query: string): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia(query).matches;
}
