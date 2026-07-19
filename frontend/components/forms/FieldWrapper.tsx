import { useId } from "react";
import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "../core/utils";


export interface FieldWrapperRenderProps {
  id: string;
  describedBy?: string;
  invalid?: boolean;
}

export interface FieldWrapperProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  label?: ReactNode;
  description?: ReactNode;
  required?: boolean;
  error?: ReactNode;
  children: ReactNode | ((props: FieldWrapperRenderProps) => ReactNode);
  htmlFor?: string;
}

export function FieldWrapper({
  className,
  label,
  description,
  required,
  error,
  children,
  htmlFor,
  ...props
}: FieldWrapperProps) {
  const generatedId = useId();
  const fieldId = htmlFor ?? generatedId;
  const descriptionId = description ? `${fieldId}-description` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(" ") || undefined;

  const renderProps: FieldWrapperRenderProps = {
    id: fieldId,
    describedBy,
    invalid: Boolean(error),
  };

  return (
    <div {...props} className={cx("form-root form-field", className)}>
      {label ? (
        <label className="form-field-label" htmlFor={fieldId}>
          {label}
          {required ? <span aria-hidden="true"> *</span> : null}
        </label>
      ) : null}
      {typeof children === "function" ? children(renderProps) : children}
      {description ? (
        <p className="form-field-description" id={descriptionId}>
          {description}
        </p>
      ) : null}
      {error ? (
        <p className="form-validation" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
