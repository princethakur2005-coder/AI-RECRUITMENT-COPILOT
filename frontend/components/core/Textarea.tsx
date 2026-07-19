import { forwardRef, useId } from "react";
import type { TextareaHTMLAttributes } from "react";


import type { UISize } from "./types";
import { cx } from "./utils";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  size?: UISize;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, id, label, hint, size = "md", ...props },
  ref,
) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const hintId = hint ? `${inputId}-hint` : undefined;

  return (
    <div className="ui-field ui-root">
      {label ? <label className="ui-label" htmlFor={inputId}>{label}</label> : null}
      <textarea
        {...props}
        ref={ref}
        id={inputId}
        className={cx("ui-control ui-textarea ui-focus-ring", `ui-textarea-${size}`, className)}
        aria-describedby={hintId}
      />
      {hint ? <div className="ui-help" id={hintId}>{hint}</div> : null}
    </div>
  );
});
