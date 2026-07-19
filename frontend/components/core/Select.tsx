import { forwardRef, useId } from "react";
import type { SelectHTMLAttributes } from "react";


import type { UISize } from "./types";
import { cx } from "./utils";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?: string;
  hint?: string;
  size?: UISize;
  options: SelectOption[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, id, label, hint, size = "md", options, placeholder, ...props },
  ref,
) {
  const fallbackId = useId();
  const selectId = id ?? fallbackId;
  const hintId = hint ? `${selectId}-hint` : undefined;

  return (
    <div className="ui-field ui-root">
      {label ? <label className="ui-label" htmlFor={selectId}>{label}</label> : null}
      <select
        {...props}
        ref={ref}
        id={selectId}
        className={cx("ui-control ui-select ui-focus-ring", `ui-select-${size}`, className)}
        aria-describedby={hintId}
      >
        {placeholder ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <div className="ui-help" id={hintId}>{hint}</div> : null}
    </div>
  );
});
