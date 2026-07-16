import type { HTMLAttributes } from "react";

import { cx } from "../core/utils";
import "./feedback.css";

export interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  value: number;
  max?: number;
  label?: string;
}

export function Progress({ className, value, max = 100, label = "Progress", ...props }: ProgressProps) {
  const clamped = Math.max(0, Math.min(value, max));
  const percent = max > 0 ? (clamped / max) * 100 : 0;

  return (
    <div className="fb-root">
      <div className="fb-progress" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={clamped} aria-label={label}>
        <div {...props} className={cx("fb-progress-value", className)} style={{ width: `${percent}%`, ...(props.style ?? {}) }} />
      </div>
    </div>
  );
}
