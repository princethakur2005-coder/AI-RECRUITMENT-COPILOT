import type { HTMLAttributes } from "react";

import { cx } from "../core/utils";
import type { MotionBaseProps } from "./types";


export interface MotionScaleProps extends MotionBaseProps, Omit<HTMLAttributes<HTMLElement>, "children"> {
  fromScale?: number;
}

export function MotionScale({
  active = true,
  durationMs = 220,
  fromScale = 0.96,
  className,
  style,
  children,
  as = "div",
  ...props
}: MotionScaleProps) {
  const Tag = as;
  return (
    <Tag
      {...props}
      className={cx("motion-root motion-scale", className)}
      data-active={active}
      style={{
        ...style,
        ["--motion-duration" as string]: `${durationMs}ms`,
        ["--motion-scale-from" as string]: `${fromScale}`,
      }}
    >
      {children}
    </Tag>
  );
}
