import type { HTMLAttributes } from "react";

import { Button } from "../core/Button";
import { cx } from "../core/utils";
import "./forms.css";

export interface FormActionsProps extends HTMLAttributes<HTMLDivElement> {
  submitLabel?: string;
  cancelLabel?: string;
  onCancel?: () => void;
  submitting?: boolean;
  submitDisabled?: boolean;
}

export function FormActions({
  className,
  submitLabel = "Save",
  cancelLabel,
  onCancel,
  submitting,
  submitDisabled,
  children,
  ...props
}: FormActionsProps) {
  return (
    <div {...props} className={cx("form-root form-actions", className)}>
      {children}
      {cancelLabel ? (
        <Button type="button" variant="secondary" onClick={onCancel}>
          {cancelLabel}
        </Button>
      ) : null}
      <Button type="submit" variant="primary" disabled={submitDisabled || submitting}>
        {submitting ? "Saving..." : submitLabel}
      </Button>
    </div>
  );
}
