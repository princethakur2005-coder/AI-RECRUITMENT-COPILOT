import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "../core/utils";


export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

export interface StatusIndicatorProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone;
  label?: ReactNode;
}

export function StatusIndicator({ className, tone = "neutral", label, ...props }: StatusIndicatorProps) {
  return (
    <span {...props} className={cx("fb-root fb-status", className)} data-tone={tone}>
      <span className="fb-status-dot" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
