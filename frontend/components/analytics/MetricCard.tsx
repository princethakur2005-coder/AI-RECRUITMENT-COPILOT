import type { HTMLAttributes, ReactNode } from "react";

import { Badge } from "../core/Badge";
import { Card, CardBody } from "../surface/Card";
import { cx } from "../core/utils";


export interface MetricCardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  label: ReactNode;
  value: ReactNode;
  meta?: ReactNode;
  trendLabel?: ReactNode;
  trendTone?: "neutral" | "brand" | "success" | "warning" | "danger";
}

export function MetricCard({
  label,
  value,
  meta,
  trendLabel,
  trendTone = "neutral",
  className,
  ...props
}: MetricCardProps) {
  return (
    <Card className={cx("an-root", className)} {...props}>
      <CardBody>
        <p className="an-metric-label">{label}</p>
        <p className="an-metric-value">{value}</p>
        {meta ? <p className="an-metric-meta">{meta}</p> : null}
        {trendLabel ? (
          <div>
            <Badge tone={trendTone} size="sm">
              {trendLabel}
            </Badge>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
