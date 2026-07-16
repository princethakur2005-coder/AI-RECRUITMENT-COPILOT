import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import { Button } from "../core/Button";
import { cx, useControllableState } from "../surface/utils";
import "./feedback.css";

export interface ToastItem {
  id: string;
  title?: ReactNode;
  description?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

interface ToastContextValue {
  items: ToastItem[];
  remove: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export interface ToastProviderProps {
  value?: ToastItem[];
  defaultValue?: ToastItem[];
  onValueChange?: (next: ToastItem[]) => void;
  children?: ReactNode;
}

export function ToastProvider({ value, defaultValue = [], onValueChange, children }: ToastProviderProps) {
  const [items, setItems] = useControllableState<ToastItem[]>({
    value,
    defaultValue,
    onChange: onValueChange,
  });

  const remove = (id: string) => {
    setItems(items.filter((item) => item.id !== id));
  };

  return <ToastContext.Provider value={{ items, remove }}>{children}</ToastContext.Provider>;
}

export interface ToastViewportProps {
  className?: string;
}

export function ToastViewport({ className }: ToastViewportProps) {
  const context = useContext(ToastContext);
  if (!context) {
    return null;
  }

  return (
    <section className={cx("fb-root fb-toast-region", className)} aria-live="polite" aria-label="Notifications">
      {context.items.map((item) => (
        <article key={item.id} className="fb-toast" role="status">
          {item.title ? <h4 className="fb-toast-title">{item.title}</h4> : null}
          {item.description ? <p className="fb-toast-description">{item.description}</p> : null}
          <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
            {item.actionLabel ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  item.onAction?.();
                }}
              >
                {item.actionLabel}
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={() => context.remove(item.id)}>
              Dismiss
            </Button>
          </div>
        </article>
      ))}
    </section>
  );
}
