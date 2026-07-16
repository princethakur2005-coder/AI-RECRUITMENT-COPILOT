import type { ReactNode } from "react";

import { Button } from "../core/Button";
import "./data-display.css";

export interface ErrorStateProps {
  title?: string;
  description?: string;
  icon?: ReactNode;
  retryLabel?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Something went wrong",
  description = "An error occurred while loading this data.",
  icon,
  retryLabel = "Try again",
  onRetry,
}: ErrorStateProps) {
  return (
    <section className="dd-root dd-state" role="alert" aria-live="assertive">
      {icon ? <div aria-hidden="true">{icon}</div> : null}
      <h3 className="dd-state-title">{title}</h3>
      <p className="dd-state-description">{description}</p>
      {onRetry ? (
        <div>
          <Button variant="danger" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
