import { useEffect } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

import "./surface.css";
import { cx, useEscape, useStableId } from "./utils";

export interface DrawerProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: "left" | "right";
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  closeOnOverlayClick?: boolean;
  closeOnEscape?: boolean;
  className?: string;
}

export function Drawer({
  open,
  onOpenChange,
  side = "right",
  title,
  description,
  children,
  footer,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  className,
}: DrawerProps) {
  const titleId = useStableId("drawer-title");
  const descriptionId = useStableId("drawer-description");

  useEscape(() => {
    if (closeOnEscape) {
      onOpenChange?.(false);
    }
  }, open);

  useEffect(() => {
    if (!open || typeof document === "undefined") {
      return;
    }

    const { body } = document;
    const previousOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    return () => {
      body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open || typeof document === "undefined") {
    return null;
  }

  const layer = (
    <div className="surface-drawer-wrap">
      <div
        className="surface-drawer-overlay"
        onClick={() => {
          if (closeOnOverlayClick) {
            onOpenChange?.(false);
          }
        }}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descriptionId : undefined}
        className={cx("surface-root surface-drawer surface-focus-ring", className)}
        data-side={side}
        tabIndex={-1}
      >
        {title || description ? (
          <header className="surface-drawer-header">
            <div>
              {title ? <h2 id={titleId} style={{ margin: 0 }}>{title}</h2> : null}
              {description ? (
                <p id={descriptionId} style={{ margin: "var(--space-1) 0 0", color: "var(--color-text-secondary)" }}>
                  {description}
                </p>
              ) : null}
            </div>
          </header>
        ) : null}
        <div className="surface-drawer-body">{children}</div>
        {footer ? <footer className="surface-drawer-footer">{footer}</footer> : null}
      </section>
    </div>
  );

  return createPortal(layer, document.body);
}
