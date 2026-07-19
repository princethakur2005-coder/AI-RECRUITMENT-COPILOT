import type { ReactNode } from "react";

import { Spinner } from "../core/Spinner";


export interface LoadingStateProps {
  title?: string;
  description?: string;
  indicator?: ReactNode;
}

export function LoadingState({
  title = "Loading",
  description = "Please wait while data is loading.",
  indicator,
}: LoadingStateProps) {
  return (
    <section className="dd-root dd-state" role="status" aria-live="polite">
      <div aria-hidden="true">{indicator ?? <Spinner size="lg" />}</div>
      <h3 className="dd-state-title">{title}</h3>
      <p className="dd-state-description">{description}</p>
    </section>
  );
}
