import { createContext, useContext } from "react";
import type { HTMLAttributes, ReactNode } from "react";

import "./surface.css";
import { cx, useControllableState, useStableId } from "./utils";

interface AccordionContextValue {
  openValues: string[];
  toggle: (value: string) => void;
  baseId: string;
}

const AccordionContext = createContext<AccordionContextValue | null>(null);

function useAccordionContext(): AccordionContextValue {
  const context = useContext(AccordionContext);
  if (!context) {
    throw new Error("Accordion components must be used within Accordion.Root");
  }
  return context;
}

export interface AccordionRootProps {
  value?: string[];
  defaultValue?: string[];
  onValueChange?: (next: string[]) => void;
  multiple?: boolean;
  children?: ReactNode;
  className?: string;
}

function AccordionRoot({
  value,
  defaultValue = [],
  onValueChange,
  multiple = false,
  children,
  className,
}: AccordionRootProps) {
  const [openValues, setOpenValues] = useControllableState<string[]>({
    value,
    defaultValue,
    onChange: onValueChange,
  });
  const baseId = useStableId("accordion");

  const toggle = (itemValue: string) => {
    const exists = openValues.includes(itemValue);
    if (exists) {
      setOpenValues(openValues.filter((valueItem) => valueItem !== itemValue));
      return;
    }

    if (multiple) {
      setOpenValues([...openValues, itemValue]);
      return;
    }

    setOpenValues([itemValue]);
  };

  return (
    <AccordionContext.Provider value={{ openValues, toggle, baseId }}>
      <div className={cx("surface-root surface-accordion", className)}>{children}</div>
    </AccordionContext.Provider>
  );
}

export interface AccordionItemProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
  children?: ReactNode;
}

function AccordionItem({ value, className, children, ...props }: AccordionItemProps) {
  const { openValues } = useAccordionContext();
  const open = openValues.includes(value);

  return (
    <div {...props} className={cx("surface-accordion-item", className)} data-open={open} data-value={value}>
      {children}
    </div>
  );
}

export interface AccordionTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  value: string;
  indicator?: ReactNode;
}

function AccordionTrigger({ value, className, children, indicator, ...props }: AccordionTriggerProps) {
  const { openValues, toggle, baseId } = useAccordionContext();
  const open = openValues.includes(value);
  const triggerId = `${baseId}-trigger-${value}`;
  const panelId = `${baseId}-panel-${value}`;

  return (
    <button
      {...props}
      id={triggerId}
      type="button"
      aria-expanded={open}
      aria-controls={panelId}
      className={cx("surface-accordion-trigger surface-focus-ring", className)}
      onClick={(event) => {
        props.onClick?.(event);
        if (!event.defaultPrevented) {
          toggle(value);
        }
      }}
    >
      <span>{children}</span>
      <span aria-hidden="true">{indicator ?? (open ? "-" : "+")}</span>
    </button>
  );
}

export interface AccordionPanelProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
}

function AccordionPanel({ value, className, children, ...props }: AccordionPanelProps) {
  const { openValues, baseId } = useAccordionContext();
  const open = openValues.includes(value);
  const triggerId = `${baseId}-trigger-${value}`;
  const panelId = `${baseId}-panel-${value}`;

  if (!open) {
    return null;
  }

  return (
    <div {...props} id={panelId} role="region" aria-labelledby={triggerId} className={cx("surface-accordion-panel", className)}>
      {children}
    </div>
  );
}

export const Accordion = {
  Root: AccordionRoot,
  Item: AccordionItem,
  Trigger: AccordionTrigger,
  Panel: AccordionPanel,
};
