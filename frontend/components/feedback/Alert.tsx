import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "../core/utils";
import "./feedback.css";

export type AlertTone = "neutral" | "success" | "warning" | "danger" | "info";

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  title?: ReactNode;
  description?: ReactNode;
  tone?: AlertTone;
}

export function Alert({ className, title, description, tone = "neutral", children, ...props }: AlertProps) {
  return (
    <section {...props} className={cx("fb-root fb-alert", className)} data-tone={tone} role="status" aria-live="polite">
      {title ? <h4 className="fb-alert-title">{title}</h4> : null}
      {description ? <p className="fb-alert-description">{description}</p> : null}
      {children}
    </section>
  );
}
