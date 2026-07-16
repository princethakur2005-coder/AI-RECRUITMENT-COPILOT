import type { CSSProperties, ReactNode } from "react";

export interface MotionBaseProps {
  active?: boolean;
  durationMs?: number;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
  as?: "div" | "section" | "article" | "span";
}
