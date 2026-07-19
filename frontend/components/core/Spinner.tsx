import type { HTMLAttributes } from "react";


import type { UISize, UIStatusTone } from "./types";
import { cx } from "./utils";

export interface SpinnerProps extends HTMLAttributes<HTMLSpanElement> {
  size?: UISize;
  tone?: UIStatusTone;
  label?: string;
}

export function Spinner({ className, size = "md", tone = "brand", label = "Loading", ...props }: SpinnerProps) {
  return (
    <span
      {...props}
      className={cx("ui-spinner", `ui-spinner-${size}`, `ui-spinner-${tone}`, className)}
      role="status"
      aria-label={label}
    />
  );
}
