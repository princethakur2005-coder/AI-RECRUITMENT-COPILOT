import type { HTMLAttributes } from "react";


import { cx } from "./utils";

export interface ContentContainerProps extends HTMLAttributes<HTMLDivElement> {
  fluid?: boolean;
}

export function ContentContainer({ className, fluid = false, ...props }: ContentContainerProps) {
  return <div {...props} className={cx("layout-content-container", className)} data-fluid={fluid} />;
}
