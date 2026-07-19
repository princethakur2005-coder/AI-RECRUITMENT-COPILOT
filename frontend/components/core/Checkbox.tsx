import { forwardRef, useId } from "react";
import type { InputHTMLAttributes } from "react";



export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  description?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { id, label, description, ...props },
  ref,
) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;

  return (
    <label className="ui-check-wrap ui-root" htmlFor={inputId}>
      <input {...props} ref={ref} id={inputId} className="ui-checkbox ui-focus-ring" type="checkbox" />
      <span>
        <span>{label}</span>
        {description ? <span className="ui-help" style={{ display: "block" }}>{description}</span> : null}
      </span>
    </label>
  );
});
