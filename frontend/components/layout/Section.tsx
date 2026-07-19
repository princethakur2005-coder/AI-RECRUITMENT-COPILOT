import type { HTMLAttributes } from "react";


import { cx } from "./utils";

export interface SectionProps extends HTMLAttributes<HTMLElement> {
  elevated?: boolean;
  as?: "section" | "article" | "div";
}

export function Section({ className, elevated = false, as = "section", ...props }: SectionProps) {
  const Tag = as;
  return <Tag {...props} className={cx("layout-section", className)} data-elevated={elevated} />;
}
