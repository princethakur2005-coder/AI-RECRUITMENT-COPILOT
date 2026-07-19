import type { ReactNode } from "react";



export interface TimelineItem {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  timestamp?: string;
  meta?: ReactNode;
}

export interface TimelineProps {
  items: TimelineItem[];
}

export function Timeline({ items }: TimelineProps) {
  return (
    <ol className="dd-root dd-timeline" aria-label="Timeline">
      {items.map((item) => (
        <li key={item.id} className="dd-timeline-item">
          <span className="dd-timeline-marker" aria-hidden="true" />
          <div className="dd-timeline-content">
            <h4 className="dd-timeline-title">{item.title}</h4>
            {item.description ? <p className="dd-timeline-meta">{item.description}</p> : null}
            {item.timestamp || item.meta ? (
              <p className="dd-timeline-meta">
                {item.timestamp ? <time dateTime={item.timestamp}>{item.timestamp}</time> : null}
                {item.timestamp && item.meta ? " • " : null}
                {item.meta}
              </p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
