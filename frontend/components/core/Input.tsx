import { forwardRef, useId } from "react";
import type { InputHTMLAttributes } from "react";

import "./core-ui.css";
import type { UISize } from "./types";
import { cx } from "./utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  size?: UISize;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, id, label, hint, size = "md", ...props },
  ref,
) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const hintId = hint ? `${inputId}-hint` : undefined;

  return (
    <div className="ui-field ui-root">
      {label ? <label className="ui-label" htmlFor={inputId}>{label}</label> : null}
      <input
        {...props}
        ref={ref}
        id={inputId}
        className={cx("ui-control ui-input ui-focus-ring", `ui-input-${size}`, className)}
        aria-describedby={hintId}
      />
      {hint ? <div className="ui-help" id={hintId}>{hint}</div> : null}
    </div>
  );
});
