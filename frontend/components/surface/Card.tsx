import type { HTMLAttributes } from "react";


import { cx } from "./utils";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: "article" | "section" | "div";
  elevated?: boolean;
}

export function Card({ as = "article", className, elevated = false, ...props }: CardProps) {
  const Tag = as;
  return <Tag {...props} className={cx("surface-root surface-card", className)} data-elevated={elevated} />;
}

export function CardHeader(props: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("surface-card-header", props.className)} />;
}

export function CardBody(props: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("surface-card-body", props.className)} />;
}

export function CardFooter(props: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("surface-card-footer", props.className)} />;
}
