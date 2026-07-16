import { createContext, useContext } from "react";
import type { HTMLAttributes, ReactNode } from "react";

import "./surface.css";
import { cx, useControllableState, useEscape, useStableId } from "./utils";

interface PopoverContextValue {
  open: boolean;
  setOpen: (next: boolean) => void;
  contentId: string;
}

const PopoverContext = createContext<PopoverContextValue | null>(null);

function usePopoverContext(): PopoverContextValue {
  const context = useContext(PopoverContext);
  if (!context) {
    throw new Error("Popover components must be used within Popover.Root");
  }
  return context;
}

export interface PopoverRootProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (next: boolean) => void;
  children?: ReactNode;
}

function PopoverRoot({ open, defaultOpen = false, onOpenChange, children }: PopoverRootProps) {
  const [currentOpen, setCurrentOpen] = useControllableState<boolean>({
    value: open,
    defaultValue: defaultOpen,
    onChange: onOpenChange,
  });
  const contentId = useStableId("popover-content");

  useEscape(() => setCurrentOpen(false), currentOpen);

  return (
    <PopoverContext.Provider value={{ open: currentOpen, setOpen: setCurrentOpen, contentId }}>
      <span className="surface-root surface-popover-wrap">{children}</span>
    </PopoverContext.Provider>
  );
}

export interface PopoverTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
  children?: ReactNode;
}

function PopoverTrigger({ asChild = false, children, className, ...props }: PopoverTriggerProps) {
  const { open, setOpen, contentId } = usePopoverContext();

  if (asChild) {
    return (
      <span
        role="button"
        tabIndex={0}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={contentId}
        className={className}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen(!open);
          }
        }}
      >
        {children}
      </span>
    );
  }

  return (
    <button
      {...props}
      type="button"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={contentId}
      className={cx("surface-focus-ring", className)}
      onClick={(event) => {
        props.onClick?.(event);
        if (!event.defaultPrevented) {
          setOpen(!open);
        }
      }}
    >
      {children}
    </button>
  );
}

export interface PopoverContentProps extends HTMLAttributes<HTMLDivElement> {
  side?: "top" | "bottom";
  align?: "start" | "end";
}

function PopoverContent({ className, side = "bottom", align = "start", children, ...props }: PopoverContentProps) {
  const { open, contentId } = usePopoverContext();

  if (!open) {
    return null;
  }

  return (
    <div
      {...props}
      id={contentId}
      role="dialog"
      className={cx("surface-popover-content", className)}
      data-side={side}
      data-align={align}
    >
      {children}
    </div>
  );
}

export const Popover = {
  Root: PopoverRoot,
  Trigger: PopoverTrigger,
  Content: PopoverContent,
};
