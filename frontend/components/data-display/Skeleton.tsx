import type { HTMLAttributes } from "react";

import { cx } from "../core/utils";


export interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string;
  height?: string;
  circle?: boolean;
}

export function Skeleton({ className, width = "100%", height = "1rem", circle = false, style, ...props }: SkeletonProps) {
  return (
    <div
      {...props}
      aria-hidden="true"
      className={cx("dd-root dd-skeleton", className)}
      style={{
        width,
        height,
        borderRadius: circle ? "var(--radius-pill)" : undefined,
        ...style,
      }}
    />
  );
}
