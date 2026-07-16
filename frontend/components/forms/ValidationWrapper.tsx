import type { ReactNode } from "react";

import { cx } from "../core/utils";
import "./forms.css";

export interface ValidationWrapperProps {
  error?: ReactNode;
  id?: string;
  className?: string;
}

export function ValidationWrapper({ error, id, className }: ValidationWrapperProps) {
  if (!error) {
    return null;
  }

  return (
    <p id={id} role="alert" className={cx("form-root form-validation", className)}>
      {error}
    </p>
  );
}
