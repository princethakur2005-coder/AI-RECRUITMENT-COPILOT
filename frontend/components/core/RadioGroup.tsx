import { useId } from "react";

import "./core-ui.css";

export interface RadioOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

export interface RadioGroupProps {
  name: string;
  label?: string;
  value?: string;
  options: RadioOption[];
  onChange?: (value: string) => void;
  orientation?: "vertical" | "horizontal";
  disabled?: boolean;
}

export function RadioGroup({
  name,
  label,
  value,
  options,
  onChange,
  orientation = "vertical",
  disabled,
}: RadioGroupProps) {
  const fallbackId = useId();

  return (
    <fieldset className="ui-field ui-root" style={{ border: "0", padding: 0, margin: 0 }}>
      {label ? <legend className="ui-label">{label}</legend> : null}
      <div
        className="ui-radio-group"
        style={{
          gridAutoFlow: orientation === "horizontal" ? "column" : "row",
          justifyContent: orientation === "horizontal" ? "start" : undefined,
        }}
      >
        {options.map((option, index) => {
          const radioId = `${fallbackId}-${index}`;
          return (
            <label key={option.value} className="ui-check-wrap" htmlFor={radioId}>
              <input
                id={radioId}
                className="ui-radio ui-focus-ring"
                type="radio"
                name={name}
                value={option.value}
                checked={value === option.value}
                disabled={disabled || option.disabled}
                onChange={(event) => onChange?.(event.target.value)}
              />
              <span>
                <span>{option.label}</span>
                {option.description ? <span className="ui-help" style={{ display: "block" }}>{option.description}</span> : null}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
