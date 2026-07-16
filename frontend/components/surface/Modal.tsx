import { useEffect } from "react";
import type { HTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";

import "./surface.css";
import { cx, useEscape, useStableId } from "./utils";

export interface ModalProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  closeOnOverlayClick?: boolean;
  closeOnEscape?: boolean;
  className?: string;
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  className,
}: ModalProps) {
  const titleId = useStableId("modal-title");
  const descriptionId = useStableId("modal-description");

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
    <div
      className="surface-overlay"
      onMouseDown={(event) => {
        if (closeOnOverlayClick && event.target === event.currentTarget) {
          onOpenChange?.(false);
        }
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descriptionId : undefined}
        className={cx("surface-root surface-layer surface-focus-ring", className)}
        tabIndex={-1}
      >
        {title || description ? (
          <header className="surface-layer-header">
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
        <div className="surface-layer-body">{children}</div>
        {footer ? <footer className="surface-layer-footer">{footer}</footer> : null}
      </section>
    </div>
  );

  return createPortal(layer, document.body);
}

export function ModalBody(props: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("surface-layer-body", props.className)} />;
}

export function ModalFooter(props: HTMLAttributes<HTMLDivElement>) {
  return <footer {...props} className={cx("surface-layer-footer", props.className)} />;
}
