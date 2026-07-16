import type { FormHTMLAttributes } from "react";

import { cx } from "../core/utils";
import "./forms.css";

export interface FormWrapperProps extends FormHTMLAttributes<HTMLFormElement> {
  columns?: 1 | 2 | 3;
}

export function FormWrapper({ className, columns = 1, children, ...props }: FormWrapperProps) {
  return (
    <form {...props} className={cx("form-root form-wrapper", className)}>
      <div className="form-row" data-columns={columns}>
        {children}
      </div>
    </form>
  );
}
