import type { HTMLAttributes, ReactNode } from "react";

import { Card, CardBody, CardHeader } from "../surface/Card";
import { cx } from "../core/utils";


export interface ChartWrapperProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  toolbar?: ReactNode;
  children?: ReactNode;
  as?: "section" | "article" | "div";
}

export function ChartWrapper({
  title,
  description,
  toolbar,
  children,
  className,
  as = "section",
  ...props
}: ChartWrapperProps) {
  return (
    <Card as={as} className={cx("an-root an-chart-wrap", className)} {...props}>
      <CardHeader>
        <div className="an-widget-header">
          <div>
            <h3 className="an-widget-title">{title}</h3>
            {description ? <p className="an-widget-description">{description}</p> : null}
          </div>
          {toolbar ? <div>{toolbar}</div> : null}
        </div>
      </CardHeader>
      <CardBody>
        <div className="an-chart-surface" role="img" aria-label={typeof title === "string" ? `${title} chart` : "Chart area"}>
          {children}
        </div>
      </CardBody>
    </Card>
  );
}
