import type { CSSProperties, HTMLAttributes } from "react";


import { cx, type SpaceToken, spaceVar } from "./utils";

export interface StackProps extends HTMLAttributes<HTMLDivElement> {
  gap?: SpaceToken;
}

export function Stack({ className, style, gap = "4", ...props }: StackProps) {
  const mergedStyle: CSSProperties = {
    ...style,
    ["--layout-stack-gap" as string]: spaceVar(gap),
  };

  return <div {...props} className={cx("layout-stack", className)} style={mergedStyle} />;
}
