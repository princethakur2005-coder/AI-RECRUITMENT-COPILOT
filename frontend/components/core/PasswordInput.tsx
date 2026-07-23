import { forwardRef, useId, useState } from "react";
import type { InputHTMLAttributes } from "react";


import type { UISize } from "./types";
import { cx } from "./utils";

export interface PasswordInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  hint?: string;
  uiSize?: UISize;
  showToggleLabel?: string;
  hideToggleLabel?: string;
}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(function PasswordInput(
  {
    className,
    id,
    label,
    hint,
    uiSize = "md",
    showToggleLabel = "Show password",
    hideToggleLabel = "Hide password",
    ...props
  },
  ref,
) {
  const [visible, setVisible] = useState(false);
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const hintId = hint ? `${inputId}-hint` : undefined;

  return (
    <div className="ui-field ui-root">
      {label ? <label className="ui-label" htmlFor={inputId}>{label}</label> : null}
      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
        <input
          {...props}
          ref={ref}
          id={inputId}
          type={visible ? "text" : "password"}
          className={cx("ui-control ui-input ui-focus-ring", `ui-input-${uiSize}`, className)}
          aria-describedby={hintId}
        />
        <button
          type="button"
          className="ui-btn ui-btn-secondary ui-btn-sm ui-focus-ring"
          aria-label={visible ? hideToggleLabel : showToggleLabel}
          onClick={() => setVisible((prev) => !prev)}
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
      {hint ? <div className="ui-help" id={hintId}>{hint}</div> : null}
    </div>
  );
});
