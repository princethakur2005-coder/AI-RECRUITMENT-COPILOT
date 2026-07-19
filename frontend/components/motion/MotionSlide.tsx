import type { HTMLAttributes } from "react";

import { cx } from "../core/utils";
import type { MotionBaseProps } from "./types";


export interface MotionSlideProps extends MotionBaseProps, Omit<HTMLAttributes<HTMLElement>, "children"> {
  distancePx?: number;
}

export function MotionSlide({
  active = true,
  durationMs = 240,
  distancePx = 8,
  className,
  style,
  children,
  as = "div",
  ...props
}: MotionSlideProps) {
  const Tag = as;
  return (
    <Tag
      {...props}
      className={cx("motion-root motion-slide-up", className)}
      data-active={active}
      style={{
        ...style,
        ["--motion-duration" as string]: `${durationMs}ms`,
        ["--motion-distance" as string]: `${distancePx}px`,
      }}
    >
      {children}
    </Tag>
  );
}
