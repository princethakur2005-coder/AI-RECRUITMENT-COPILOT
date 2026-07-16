import { useId } from "react";

import "./core-ui.css";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange?: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  id?: string;
}

export function Switch({ checked, onCheckedChange, label, description, disabled, id }: SwitchProps) {
  const fallbackId = useId();
  const switchId = id ?? fallbackId;

  return (
    <div className="ui-switch-wrap ui-root">
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        data-checked={checked}
        className="ui-switch ui-focus-ring"
        onClick={() => onCheckedChange?.(!checked)}
      >
        <span className="ui-switch-thumb" />
      </button>
      <label htmlFor={switchId}>
        <span>{label}</span>
        {description ? <span className="ui-help" style={{ display: "block" }}>{description}</span> : null}
      </label>
    </div>
  );
}
