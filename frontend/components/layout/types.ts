import type { CSSProperties, ReactNode } from "react";

export interface LayoutChildrenProps {
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export interface ResponsiveColumns {
  mobile?: number;
  sm?: number;
  md?: number;
  lg?: number;
}
