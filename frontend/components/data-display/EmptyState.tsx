import type { ReactNode } from "react";

import { Button } from "../core/Button";


export interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({
  title = "No data found",
  description = "There is nothing to display yet.",
  icon,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <section className="dd-root dd-state" role="status" aria-live="polite">
      {icon ? <div aria-hidden="true">{icon}</div> : null}
      <h3 className="dd-state-title">{title}</h3>
      <p className="dd-state-description">{description}</p>
      {actionLabel ? (
        <div>
          <Button variant="secondary" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
