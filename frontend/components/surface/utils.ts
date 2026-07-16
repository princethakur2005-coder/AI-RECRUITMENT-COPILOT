import { useEffect, useId, useState } from "react";

export { cx } from "../core/utils";

export function useControllableState<T>(params: {
  value?: T;
  defaultValue: T;
  onChange?: (next: T) => void;
}) {
  const { value, defaultValue, onChange } = params;
  const [internal, setInternal] = useState<T>(defaultValue);
  const isControlled = value !== undefined;
  const current = isControlled ? (value as T) : internal;

  const setValue = (next: T) => {
    if (!isControlled) {
      setInternal(next);
    }
    onChange?.(next);
  };

  return [current, setValue] as const;
}

export function useEscape(handler: () => void, active: boolean): void {
  useEffect(() => {
    if (!active) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handler();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [active, handler]);
}

export function useStableId(prefix: string): string {
  const reactId = useId();
  return `${prefix}-${reactId.replace(/[:]/g, "")}`;
}
