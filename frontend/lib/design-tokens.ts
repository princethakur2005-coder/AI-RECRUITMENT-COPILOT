export type ThemeMode = "light" | "dark";

export const breakpoints = {
  xs: "360px",
  sm: "640px",
  md: "768px",
  lg: "1024px",
  xl: "1280px",
  xxl: "1536px",
} as const;

export const typography = {
  fontFamily: {
    sans: '"Manrope", "Segoe UI", system-ui, -apple-system, sans-serif',
    mono: '"JetBrains Mono", "Cascadia Code", ui-monospace, monospace',
  },
  fontSize: {
    xs: "0.75rem",
    sm: "0.875rem",
    md: "1rem",
    lg: "1.125rem",
    xl: "1.25rem",
    "2xl": "1.5rem",
    "3xl": "1.875rem",
    "4xl": "2.25rem",
  },
  lineHeight: {
    tight: 1.2,
    normal: 1.5,
    relaxed: 1.7,
  },
  fontWeight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
} as const;

export const spacing = {
  0: "0",
  1: "0.25rem",
  2: "0.5rem",
  3: "0.75rem",
  4: "1rem",
  5: "1.25rem",
  6: "1.5rem",
  8: "2rem",
  10: "2.5rem",
  12: "3rem",
  16: "4rem",
  20: "5rem",
} as const;

export const radius = {
  none: "0",
  sm: "0.25rem",
  md: "0.5rem",
  lg: "0.75rem",
  xl: "1rem",
  pill: "999px",
} as const;

export const shadows = {
  xs: "0 1px 2px rgb(15 23 42 / 0.06)",
  sm: "0 2px 8px rgb(15 23 42 / 0.08)",
  md: "0 8px 24px rgb(15 23 42 / 0.12)",
  lg: "0 16px 40px rgb(15 23 42 / 0.16)",
} as const;

export const zIndex = {
  base: 0,
  dropdown: 1000,
  sticky: 1020,
  overlay: 1040,
  modal: 1060,
  toast: 1080,
  tooltip: 1100,
} as const;

export const colorPalette = {
  neutral: {
    50: "#f8fafc",
    100: "#f1f5f9",
    200: "#e2e8f0",
    300: "#cbd5e1",
    400: "#94a3b8",
    500: "#64748b",
    600: "#475569",
    700: "#334155",
    800: "#1e293b",
    900: "#0f172a",
  },
  brand: {
    50: "#ecfeff",
    100: "#cffafe",
    200: "#a5f3fc",
    300: "#67e8f9",
    400: "#22d3ee",
    500: "#06b6d4",
    600: "#0891b2",
    700: "#0e7490",
    800: "#155e75",
    900: "#164e63",
  },
  status: {
    success: "#16a34a",
    warning: "#d97706",
    danger: "#dc2626",
    info: "#0284c7",
  },
} as const;

export const semanticTokens = {
  light: {
    bgCanvas: "var(--color-bg-canvas)",
    bgSurface: "var(--color-bg-surface)",
    bgMuted: "var(--color-bg-muted)",
    textPrimary: "var(--color-text-primary)",
    textSecondary: "var(--color-text-secondary)",
    textMuted: "var(--color-text-muted)",
    borderSubtle: "var(--color-border-subtle)",
    borderStrong: "var(--color-border-strong)",
    actionPrimaryBg: "var(--color-action-primary-bg)",
    actionPrimaryBgHover: "var(--color-action-primary-bg-hover)",
    actionPrimaryText: "var(--color-action-primary-text)",
  },
  dark: {
    bgCanvas: "var(--color-bg-canvas)",
    bgSurface: "var(--color-bg-surface)",
    bgMuted: "var(--color-bg-muted)",
    textPrimary: "var(--color-text-primary)",
    textSecondary: "var(--color-text-secondary)",
    textMuted: "var(--color-text-muted)",
    borderSubtle: "var(--color-border-subtle)",
    borderStrong: "var(--color-border-strong)",
    actionPrimaryBg: "var(--color-action-primary-bg)",
    actionPrimaryBgHover: "var(--color-action-primary-bg-hover)",
    actionPrimaryText: "var(--color-action-primary-text)",
  },
} as const;
