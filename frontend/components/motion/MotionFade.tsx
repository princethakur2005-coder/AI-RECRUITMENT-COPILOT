import type { HTMLAttributes } from "react";

import { cx } from "../core/utils";
import type { MotionBaseProps } from "./types";


export interface MotionFadeProps extends MotionBaseProps, Omit<HTMLAttributes<HTMLElement>, "children"> {}

export function MotionFade({
  active = true,
  durationMs = 220,
  className,
  style,
  children,
  as = "div",
  ...props
}: MotionFadeProps) {
  const Tag = as;
  return (
    <Tag
      {...props}
      className={cx("motion-root motion-fade", className)}
      data-active={active}
      style={{
        ...style,
        ["--motion-duration" as string]: `${durationMs}ms`,
      }}
    >
      {children}
    </Tag>
  );
}
