import type { CSSProperties, HTMLAttributes } from "react";

import "./layout.css";
import { cx, type SpaceToken, spaceVar } from "./utils";
import type { ResponsiveColumns } from "./types";

export interface GridProps extends HTMLAttributes<HTMLDivElement> {
  columns?: ResponsiveColumns;
  gap?: SpaceToken;
}

export function Grid({ className, style, columns, gap = "4", ...props }: GridProps) {
  const mergedStyle: CSSProperties = {
    ...style,
    ["--layout-grid-gap" as string]: spaceVar(gap),
    ["--layout-grid-cols-mobile" as string]: columns?.mobile ?? 1,
    ["--layout-grid-cols-sm" as string]: columns?.sm,
    ["--layout-grid-cols-md" as string]: columns?.md,
    ["--layout-grid-cols-lg" as string]: columns?.lg,
  };

  return <div {...props} className={cx("layout-grid", className)} style={mergedStyle} />;
}
