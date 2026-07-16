import type { HTMLAttributes } from "react";

import "./core-ui.css";
import type { UISize, UIStatusTone } from "./types";
import { cx } from "./utils";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: UIStatusTone;
  size?: Extract<UISize, "sm" | "md">;
}

export function Badge({ className, tone = "neutral", size = "md", ...props }: BadgeProps) {
  return <span {...props} className={cx("ui-badge", `ui-badge-${size}`, `ui-badge-${tone}`, className)} />;
}
