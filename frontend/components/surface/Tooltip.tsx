import { cloneElement, isValidElement, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import "./surface.css";
import { useStableId } from "./utils";

export interface TooltipProps {
  content: ReactNode;
  children: ReactElement;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (next: boolean) => void;
}

export function Tooltip({ content, children, open, defaultOpen = false, onOpenChange }: TooltipProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isControlled = open !== undefined;
  const visible = isControlled ? open : internalOpen;
  const tooltipId = useStableId("tooltip");

  const setVisible = (next: boolean) => {
    if (!isControlled) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  };

  if (!isValidElement(children)) {
    return null;
  }

  const child = cloneElement(children, {
    "aria-describedby": visible ? tooltipId : undefined,
    onMouseEnter: (event: MouseEvent) => {
      const original = (children.props as { onMouseEnter?: (e: MouseEvent) => void }).onMouseEnter;
      original?.(event);
      setVisible(true);
    },
    onMouseLeave: (event: MouseEvent) => {
      const original = (children.props as { onMouseLeave?: (e: MouseEvent) => void }).onMouseLeave;
      original?.(event);
      setVisible(false);
    },
    onFocus: (event: FocusEvent) => {
      const original = (children.props as { onFocus?: (e: FocusEvent) => void }).onFocus;
      original?.(event);
      setVisible(true);
    },
    onBlur: (event: FocusEvent) => {
      const original = (children.props as { onBlur?: (e: FocusEvent) => void }).onBlur;
      original?.(event);
      setVisible(false);
    },
  } as Record<string, unknown>);

  return (
    <span className="surface-root surface-tooltip-wrap">
      {child}
      {visible ? (
        <span id={tooltipId} role="tooltip" className="surface-tooltip">
          {content}
        </span>
      ) : null}
    </span>
  );
}
