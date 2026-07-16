import type { HTMLAttributes, ReactNode } from "react";

import { Progress } from "../feedback/Progress";
import { StatusIndicator, type StatusTone } from "../feedback/StatusIndicator";
import { Card, CardBody } from "../surface/Card";
import { cx } from "../core/utils";
import "./analytics.css";

export interface KPICardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  label: ReactNode;
  value: ReactNode;
  progress?: number;
  progressMax?: number;
  statusLabel?: ReactNode;
  statusTone?: StatusTone;
  helperText?: ReactNode;
}

export function KPICard({
  label,
  value,
  progress,
  progressMax = 100,
  statusLabel,
  statusTone = "neutral",
  helperText,
  className,
  ...props
}: KPICardProps) {
  return (
    <Card className={cx("an-root", className)} {...props}>
      <CardBody>
        <p className="an-metric-label">{label}</p>
        <p className="an-metric-value">{value}</p>
        {typeof progress === "number" ? <Progress value={progress} max={progressMax} label="KPI progress" /> : null}
        {statusLabel ? <StatusIndicator tone={statusTone} label={statusLabel} /> : null}
        {helperText ? <p className="an-metric-meta">{helperText}</p> : null}
      </CardBody>
    </Card>
  );
}
